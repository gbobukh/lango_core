"""
FIND action operations: oidh_match (legacy FIND_OIDH) and lookup_in_tree (resolve ids in any hierarchical JSON tree).
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Any, Callable

from .utils import _resolve_path, _MISSING

logger = logging.getLogger(__name__)

OFFER_INDICES_RE = re.compile(
    r'rules\[(\d+)\]\.paths\[(\d+)\]\.offers\[(\d+)\]'
)
PATH_INDICES_RE = re.compile(
    r'rules\[(\d+)\]\.paths\[(\d+)\]'
)
RULE_INDEX_RE = re.compile(
    r'rules\[(\d+)\]'
)

LOGICAL_ID_KEYS = ('root_id', 'rule_id', 'path_id', 'offer_id')


def _tree_root_id_field(tree_cfg: dict) -> str:
    return (
        tree_cfg.get('root_id_field')
        or tree_cfg.get('campaign_id_field')  # legacy alias
        or 'id'
    )


def _normalize_output_map(raw: dict | None) -> dict[str, str]:
    defaults = {
        'root_id': 'root_id',
        'rule_id': 'rule_id',
        'path_id': 'path_id',
        'offer_id': 'offer_id',
    }
    if not raw:
        return defaults
    merged = {**defaults, **raw}
    if 'campaign_id' in raw and 'root_id' not in raw:
        merged['root_id'] = raw['campaign_id']
    return merged


def run_find(
    *,
    config: dict,
    context: dict,
    resolve_variable: Callable[[str], Any],
    log_func: Callable[[str], None] | None = None,
    err_prefix: str = '',
) -> Any:
    operation = (config.get('operation') or '').strip().lower()
    if operation == 'lookup_in_tree':
        return run_lookup_in_tree(
            config=config,
            context=context,
            resolve_variable=resolve_variable,
            log_func=log_func,
            err_prefix=err_prefix,
        )
    if operation in ('', 'oidh_match'):
        return run_oidh_match(
            config=config,
            context=context,
            resolve_variable=resolve_variable,
            log_func=log_func,
            err_prefix=err_prefix,
        )
    raise ValueError(f"{err_prefix}FIND unsupported operation {operation!r}")


def run_oidh_match(
    *,
    config: dict,
    context: dict,
    resolve_variable: Callable[[str], Any],
    log_func: Callable[[str], None] | None = None,
    err_prefix: str = '',
) -> list:
    """Legacy FIND_OIDH: match input items to OIDH rules by criteria overlap."""
    input_name = config.get('input')
    rules_name = config.get('rules')
    output_rule_id_key = config.get('output_rule_id_key', 'matched_rule_id')
    output_rule_name_key = config.get('output_rule_name_key', 'matched_rule_name')
    input_campaign_id_field = config.get('input_campaign_id_field', 'cmp_id')
    iterator_campaign_id_field = config.get('iterator_campaign_id_field', 'id')

    input_list = resolve_variable(input_name)
    if input_list is None:
        raise ValueError(f"{err_prefix}FIND input '{input_name}' not found in context.")
    if not isinstance(input_list, list):
        raise ValueError(
            f"{err_prefix}FIND input '{input_name}' must be a list, got {type(input_list)}"
        )

    iterator_item = context.get('item')
    if isinstance(iterator_item, dict):
        current_campaign_id = iterator_item.get(iterator_campaign_id_field)
        if current_campaign_id is not None:
            current_campaign_id = str(current_campaign_id)
            input_list = [
                x
                for x in input_list
                if isinstance(x, dict)
                and str(x.get(input_campaign_id_field)) == current_campaign_id
            ]
            logger.info(
                'FIND oidh_match: filtered input by %s=%s -> %s items',
                input_campaign_id_field,
                current_campaign_id,
                len(input_list),
            )

    rules_list = resolve_variable(rules_name)
    if rules_list is None:
        raise ValueError(f"{err_prefix}FIND rules '{rules_name}' not found in context.")
    if not isinstance(rules_list, list):
        raise ValueError(
            f"{err_prefix}FIND rules '{rules_name}' must be a list, got {type(rules_list)}"
        )

    def _is_numeric(v):
        if isinstance(v, (int, float)):
            return True
        if isinstance(v, str):
            try:
                float(v)
                return True
            except (ValueError, TypeError):
                pass
        return False

    def _item_non_numeric_values(item):
        if not isinstance(item, dict):
            return set()
        out = set()
        for v in item.values():
            if _is_numeric(v):
                continue
            out.add(v)
        return out

    def _rule_values(rule):
        if not isinstance(rule, dict):
            return set()
        criteria = rule.get('criteria') or []
        out = set()
        for c in criteria if isinstance(criteria, list) else []:
            if not isinstance(c, dict):
                continue
            vals = c.get('values')
            if isinstance(vals, list):
                out.update(vals)
        return out

    result = []
    for item in input_list:
        new_item = dict(item) if isinstance(item, dict) else {}
        item_vals = _item_non_numeric_values(new_item)
        if not rules_list:
            new_item[output_rule_id_key] = None
            new_item[output_rule_name_key] = None
            result.append(new_item)
            continue

        rule_values_list = [_rule_values(r) for r in rules_list]
        counts = [sum(1 for v in item_vals if v in rv) for rv in rule_values_list]

        max_n = max(counts) if counts else 0
        if max_n == 0:
            new_item[output_rule_id_key] = None
            new_item[output_rule_name_key] = None
        else:
            indices_with_max = [i for i, c in enumerate(counts) if c == max_n]
            if len(indices_with_max) == 1:
                chosen = rules_list[indices_with_max[0]]
                new_item[output_rule_id_key] = (
                    chosen.get('id') if isinstance(chosen, dict) else None
                )
                new_item[output_rule_name_key] = (
                    chosen.get('name') if isinstance(chosen, dict) else None
                )
            else:
                min_criteria = min(len(rule_values_list[i]) for i in indices_with_max)
                narrowed = [
                    i for i in indices_with_max if len(rule_values_list[i]) == min_criteria
                ]
                candidates_info = [
                    f"rule '{rules_list[i].get('name', '?')}' (id={rules_list[i].get('id')}): "
                    f"{counts[i]} matches / {len(rule_values_list[i])} criteria = "
                    f"{counts[i] / len(rule_values_list[i]):.0%}"
                    for i in indices_with_max
                ]
                if len(narrowed) == 1:
                    chosen = rules_list[narrowed[0]]
                    new_item[output_rule_id_key] = (
                        chosen.get('id') if isinstance(chosen, dict) else None
                    )
                    new_item[output_rule_name_key] = (
                        chosen.get('name') if isinstance(chosen, dict) else None
                    )
                    if log_func:
                        log_func(
                            f"FIND oidh_match tie-break: item_vals={item_vals} | "
                            f"candidates: {candidates_info} -> chose '{chosen.get('name')}'"
                        )
                else:
                    new_item[output_rule_id_key] = None
                    new_item[output_rule_name_key] = None
                    if log_func:
                        log_func(
                            f"FIND oidh_match unresolved tie: item_vals={item_vals} | "
                            f"candidates: {candidates_info}"
                        )
        result.append(new_item)

    logger.info(
        'FIND oidh_match: processed %s items from %r, rules from %r',
        len(result),
        input_name,
        rules_name,
    )
    return result


def _normalize_tree_root(source: Any, source_list_index: int | None) -> dict | None:
    if source is None:
        return None
    if isinstance(source, list):
        if not source:
            return None
        idx = 0 if source_list_index is None else int(source_list_index)
        if idx < 0 or idx >= len(source):
            return None
        source = source[idx]
    return source if isinstance(source, dict) else None


def _parse_indices(path: str, scope: str) -> tuple[int | None, int | None, int | None]:
    if not path or not isinstance(path, str):
        return None, None, None
    m_offer = OFFER_INDICES_RE.search(path)
    if m_offer:
        return int(m_offer.group(1)), int(m_offer.group(2)), int(m_offer.group(3))
    m_path = PATH_INDICES_RE.search(path)
    if m_path:
        return int(m_path.group(1)), int(m_path.group(2)), None
    m_rule = RULE_INDEX_RE.search(path)
    if m_rule:
        return int(m_rule.group(1)), None, None
    return None, None, None


def _lookup_ids_from_tree(
    root: dict,
    tree_cfg: dict,
    rule_idx: int | None,
    path_idx: int | None,
    offer_idx: int | None,
) -> dict[str, Any]:
    rules_path = tree_cfg.get('rules_path') or 'customRotation.rules'
    paths_segment = tree_cfg.get('paths_segment') or 'paths'
    offers_segment = tree_cfg.get('offers_segment') or 'offers'
    path_id_field = tree_cfg.get('path_id_field') or 'id'
    offer_id_field = tree_cfg.get('offer_id_field') or 'offerId'
    rule_id_field = tree_cfg.get('rule_id_field') or 'id'
    root_id_field = _tree_root_id_field(tree_cfg)

    out: dict[str, Any] = {
        'root_id': root.get(root_id_field),
        'rule_id': None,
        'path_id': None,
        'offer_id': None,
    }

    rules = _resolve_path(root, rules_path)
    if rules is _MISSING or not isinstance(rules, list) or rule_idx is None:
        return out
    if rule_idx < 0 or rule_idx >= len(rules):
        return out
    rule = rules[rule_idx]
    if not isinstance(rule, dict):
        return out
    out['rule_id'] = rule.get(rule_id_field)

    if path_idx is None:
        return out
    paths = rule.get(paths_segment)
    if not isinstance(paths, list) or path_idx < 0 or path_idx >= len(paths):
        return out
    path_obj = paths[path_idx]
    if not isinstance(path_obj, dict):
        return out
    out['path_id'] = path_obj.get(path_id_field)

    if offer_idx is None:
        return out
    offers = path_obj.get(offers_segment)
    if not isinstance(offers, list) or offer_idx < 0 or offer_idx >= len(offers):
        return out
    offer = offers[offer_idx]
    if isinstance(offer, dict):
        out['offer_id'] = offer.get(offer_id_field)
    return out


def _lookup_ids_from_stats(
    stats: Any,
    branch_key_template: str,
    rule_idx: int | None,
    path_idx: int | None,
    offer_idx: int | None,
    *,
    paths_ids_field: str = 'paths_ids',
    offers_ids_field: str = 'offers_ids',
    rules_ids_field: str = 'rules_ids',
    rule_key_template: str | None = None,
) -> dict[str, Any]:
    from .resolve_hierarchical_disables import _extract_by_branch

    out: dict[str, Any] = {
        'root_id': None,
        'rule_id': None,
        'path_id': None,
        'offer_id': None,
    }
    by_branch = _extract_by_branch(stats)
    if rule_idx is None or path_idx is None:
        if rule_idx is not None and rule_key_template:
            rule_key = rule_key_template.format(r=rule_idx)
            row = by_branch.get(rule_key)
            if isinstance(row, dict):
                rules_ids = row.get(rules_ids_field)
                if isinstance(rules_ids, list) and rules_ids:
                    out['rule_id'] = rules_ids[0]
        return out

    branch_key = branch_key_template.format(r=rule_idx, p=path_idx)
    row = by_branch.get(branch_key)
    if not isinstance(row, dict):
        return out

    paths_ids = row.get(paths_ids_field)
    if isinstance(paths_ids, list) and 0 <= path_idx < len(paths_ids):
        out['path_id'] = paths_ids[path_idx]

    offers_ids = row.get(offers_ids_field)
    if offer_idx is not None and isinstance(offers_ids, list) and 0 <= offer_idx < len(offers_ids):
        out['offer_id'] = offers_ids[offer_idx]

    if rule_key_template:
        rule_key = rule_key_template.format(r=rule_idx)
        rule_row = by_branch.get(rule_key)
        if isinstance(rule_row, dict):
            rules_ids = rule_row.get(rules_ids_field)
            if isinstance(rules_ids, list) and rules_ids:
                out['rule_id'] = rules_ids[0]

    return out


def run_lookup_in_tree(
    *,
    config: dict,
    context: dict,
    resolve_variable: Callable[[str], Any],
    log_func: Callable[[str], None] | None = None,
    err_prefix: str = '',
) -> list:
    """For each input row, parse path indices and attach root/rule/path/leaf API ids from a source tree."""
    input_name = config.get('input')
    source_name = config.get('source')
    path_field = config.get('path_field') or 'path'
    scope_field = config.get('scope_field') or 'scope'
    source_list_index = config.get('source_list_index')
    if source_list_index is not None:
        source_list_index = int(source_list_index)

    tree_cfg = config.get('tree') or {}
    output_map = _normalize_output_map(config.get('output'))
    stats_cfg = config.get('stats') or {}

    input_list = resolve_variable(input_name)
    if input_list is None:
        raise ValueError(f"{err_prefix}FIND input '{input_name}' not found in context.")
    if not isinstance(input_list, list):
        raise ValueError(
            f"{err_prefix}FIND input '{input_name}' must be a list, got {type(input_list)}"
        )

    source_raw = resolve_variable(source_name)
    if source_raw is None:
        raise ValueError(f"{err_prefix}FIND source '{source_name}' not found in context.")
    root = _normalize_tree_root(source_raw, source_list_index)
    if root is None:
        raise ValueError(
            f"{err_prefix}FIND source '{source_name}' must resolve to a dict "
            f'(optional source_list_index), got {type(source_raw)}'
        )

    stats_raw = None
    if stats_cfg.get('stats_path'):
        stats_raw = resolve_variable(stats_cfg['stats_path'])

    branch_tpl = stats_cfg.get('stats_branch_key_template') or tree_cfg.get(
        'stats_branch_key_template'
    )
    rule_tpl = stats_cfg.get('stats_rule_key_template') or tree_cfg.get('stats_rule_key_template')

    enriched = 0
    missing = 0
    result = []

    for item in input_list:
        new_item = copy.deepcopy(item) if isinstance(item, dict) else {}
        path_val = new_item.get(path_field) if isinstance(new_item, dict) else None
        scope = (
            (new_item.get(scope_field) or '').strip().lower()
            if isinstance(new_item, dict)
            else ''
        )

        rule_idx, path_idx, offer_idx = _parse_indices(str(path_val or ''), scope)

        ids = _lookup_ids_from_tree(root, tree_cfg, rule_idx, path_idx, offer_idx)

        if stats_raw is not None and branch_tpl:
            stats_ids = _lookup_ids_from_stats(
                stats_raw,
                branch_tpl,
                rule_idx,
                path_idx,
                offer_idx,
                paths_ids_field=stats_cfg.get('paths_ids_field') or 'paths_ids',
                offers_ids_field=stats_cfg.get('offers_ids_field') or 'offers_ids',
                rules_ids_field=stats_cfg.get('rules_ids_field') or 'rules_ids',
                rule_key_template=rule_tpl,
            )
            for key in LOGICAL_ID_KEYS:
                if ids.get(key) is None and stats_ids.get(key) is not None:
                    ids[key] = stats_ids[key]

        if scope == 'offer':
            keys_to_write = LOGICAL_ID_KEYS
        elif scope == 'path':
            keys_to_write = ('root_id', 'rule_id', 'path_id')
        elif scope == 'rule':
            keys_to_write = ('root_id', 'rule_id')
        else:
            keys_to_write = LOGICAL_ID_KEYS

        had_any = False
        for logical_key in keys_to_write:
            out_key = output_map.get(logical_key, logical_key)
            val = ids.get(logical_key)
            new_item[out_key] = val
            if val is not None:
                had_any = True

        if had_any:
            enriched += 1
        else:
            missing += 1
        result.append(new_item)

    msg = (
        f'FIND lookup_in_tree: processed {len(result)} items from {input_name!r}, '
        f'enriched={enriched} missing_ids={missing}'
    )
    logger.info(msg)
    if log_func:
        log_func(msg)
    return result
