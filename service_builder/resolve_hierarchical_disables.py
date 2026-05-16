"""
RESOLVE_HIERARCHICAL_DISABLES: escalate offer-level disable plans using tree branch stats.

Ensures at least one active child remains at each hierarchy level (offer -> path -> rule).
"""
from __future__ import annotations

import re
from typing import Any


OFFER_ENABLED_PATH_RE = re.compile(
    r'^customRotation\.rules\[(\d+)\]\.paths\[(\d+)\]\.offers\[(\d+)\]\.enabled$'
)

DEFAULT_BRANCH_KEY_TEMPLATE = 'customRotation.rules[{r}].paths[{p}]'
DEFAULT_RULE_KEY_TEMPLATE = 'customRotation.rules[{r}]'


def _extract_changes_list(raw: Any) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        if len(raw) == 1 and isinstance(raw[0], dict) and isinstance(raw[0].get('changes'), list):
            return raw[0]['changes']
        return raw
    if isinstance(raw, dict):
        if isinstance(raw.get('changes'), list):
            return raw['changes']
    return []


def _extract_by_branch(stats: Any) -> dict:
    if stats is None:
        return {}
    if isinstance(stats, list) and len(stats) == 1 and isinstance(stats[0], dict):
        stats = stats[0]
    if isinstance(stats, dict):
        by_branch = stats.get('by_branch')
        if isinstance(by_branch, dict):
            return by_branch
    return {}


def _branch_key(template: str, rule_idx: int, path_idx: int) -> str:
    return template.format(r=rule_idx, p=path_idx)


def _rule_key(template: str, rule_idx: int) -> str:
    return template.format(r=rule_idx)


def _path_scope(rule_idx: int, path_idx: int) -> str:
    return f'customRotation.rules[{rule_idx}].paths[{path_idx}]'


def _rule_scope(rule_idx: int) -> str:
    return f'customRotation.rules[{rule_idx}]'


def _int_metric(branch_row: dict, field: str, default: int = 0) -> int:
    val = branch_row.get(field)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def resolve_hierarchical_disables(
    *,
    context: dict,
    config: dict,
    log_func=None,
) -> dict:
    """
    Read stats + proposed changes from context, write safe_disable_ops and guard_report.

    Returns the guard_report dict (also written to context[report_path]).
    """
    tree_cfg = config.get('tree') or {}
    input_cfg = config.get('input') or {}
    policy = config.get('policy') or {}
    output_cfg = config.get('output') or {}

    stats_path = tree_cfg.get('stats_path') or 'branch_stats'
    branch_key_template = tree_cfg.get('stats_branch_key_template') or DEFAULT_BRANCH_KEY_TEMPLATE
    rule_key_template = tree_cfg.get('stats_rule_key_template') or DEFAULT_RULE_KEY_TEMPLATE
    offers_field = tree_cfg.get('offers_enabled_field') or 'offers_enabled'
    paths_field = tree_cfg.get('paths_enabled_field') or 'paths_enabled'

    changes_path = input_cfg.get('changes_path') or 'proposed_changes'
    path_field = input_cfg.get('path_field') or 'path'

    min_active = int(policy.get('min_active_children') or 1)
    multi_change_policy = (policy.get('multi_change_policy') or 'simulate_counters').lower()

    resolved_path = output_cfg.get('resolved_operations_path') or 'safe_disable_ops'
    report_path = output_cfg.get('report_path') or 'guard_report'

    stats_raw = _resolve_context_path(context, stats_path)
    changes_raw = _resolve_context_path(context, changes_path)
    by_branch = _extract_by_branch(stats_raw)
    changes = _extract_changes_list(changes_raw)

    offer_remaining: dict[str, int] = {}
    path_remaining: dict[str, int] = {}

    branch_key_re = re.compile(
        r'^customRotation\.rules\[(\d+)\]\.paths\[(\d+)\]$'
    )
    for branch_key, row in by_branch.items():
        if not isinstance(row, dict):
            continue
        offer_remaining[branch_key] = _int_metric(row, offers_field)
        rule_path_m = branch_key_re.match(branch_key)
        if rule_path_m:
            r_idx = int(rule_path_m.group(1))
            rule_key = _rule_key(rule_key_template, r_idx)
            if rule_key not in path_remaining:
                path_remaining[rule_key] = _int_metric(row, paths_field)

    resolved_ops: list[dict] = []
    details: list[dict] = []
    offer_level = path_level = rule_level = rejected = 0

    for source_index, entry in enumerate(changes):
        if not isinstance(entry, dict):
            rejected += 1
            details.append(
                {
                    'source_index': source_index,
                    'status': 'rejected',
                    'reason': 'invalid_change_entry',
                    'note': 'Change entry must be an object.',
                }
            )
            continue

        path = entry.get(path_field)
        if not isinstance(path, str) or not path.strip():
            rejected += 1
            details.append(
                {
                    'source_index': source_index,
                    'status': 'rejected',
                    'reason': 'missing_path',
                    'note': 'Change entry has no path field.',
                }
            )
            continue

        path = path.strip()
        m = OFFER_ENABLED_PATH_RE.match(path)
        if not m:
            rejected += 1
            details.append(
                {
                    'source_index': source_index,
                    'requested': path,
                    'status': 'rejected',
                    'reason': 'path_not_offer_enabled',
                    'note': 'Path does not match offer.enabled pattern.',
                }
            )
            continue

        rule_idx = int(m.group(1))
        path_idx = int(m.group(2))
        offer_idx = int(m.group(3))
        branch_key = _branch_key(branch_key_template, rule_idx, path_idx)
        rule_key = _rule_key(rule_key_template, rule_idx)

        branch_row = by_branch.get(branch_key) or {}
        offers_before = offer_remaining.get(branch_key, _int_metric(branch_row, offers_field))
        paths_before = path_remaining.get(
            rule_key, _int_metric(branch_row, paths_field)
        )

        detail: dict[str, Any] = {
            'source_index': source_index,
            'requested': path,
            'offers_enabled_before': offers_before,
            'paths_enabled_before': paths_before,
        }

        resolved_scope = 'offer'
        resolved_target = path
        escalation = None
        note = None

        if offers_before <= min_active:
            resolved_scope = 'path'
            resolved_target = _path_scope(rule_idx, path_idx)
            escalation = 'offer_to_path'
            note = (
                'Only one active offer on path; cannot disable offer alone. '
                'Escalated to path scope.'
            )
            if paths_before <= min_active:
                resolved_scope = 'rule'
                resolved_target = _rule_scope(rule_idx)
                escalation = 'path_to_rule'
                note = (
                    'Only one active path on rule; cannot disable path alone. '
                    'Escalated to rule scope.'
                )

        detail['resolved_scope'] = resolved_scope
        detail['resolved_target'] = resolved_target
        if escalation:
            detail['escalation'] = escalation
        if note:
            detail['note'] = note

        op: dict[str, Any] = {
            'scope': resolved_scope,
            'source_change_index': source_index,
        }

        if resolved_scope == 'offer':
            op['op'] = entry.get('op') or 'replace'
            op['path'] = path
            op['after'] = entry.get('after', False)
            offer_level += 1
        elif resolved_scope == 'path':
            op['op'] = 'disable_path'
            op['path'] = resolved_target
            op['escalated_from'] = path
            op['reason'] = 'offers_enabled_at_or_below_min_active'
            path_level += 1
        else:
            op['op'] = 'pause_rule'
            op['path'] = resolved_target
            op['escalated_from'] = path
            op['reason'] = 'paths_enabled_at_or_below_min_active'
            rule_level += 1

        resolved_ops.append(op)
        detail['status'] = 'resolved'
        details.append(detail)

        if multi_change_policy == 'simulate_counters':
            if resolved_scope == 'offer':
                offer_remaining[branch_key] = max(0, offers_before - 1)
            elif resolved_scope == 'path':
                offer_remaining[branch_key] = 0
                path_remaining[rule_key] = max(0, paths_before - 1)
            else:
                offer_remaining[branch_key] = 0
                path_remaining[rule_key] = 0

    report = {
        'summary': {
            'input_changes': len(changes),
            'resolved_operations': len(resolved_ops),
            'offer_level': offer_level,
            'path_level': path_level,
            'rule_level': rule_level,
            'rejected': rejected,
            'multi_change_policy': multi_change_policy,
        },
        'details': details,
    }

    context[resolved_path] = resolved_ops
    context[report_path] = report

    if log_func:
        log_func(
            'RESOLVE_HIERARCHICAL_DISABLES: '
            f"resolved={len(resolved_ops)} offer={offer_level} path={path_level} "
            f"rule={rule_level} rejected={rejected}"
        )

    return report


def _resolve_context_path(context: dict, path: str) -> Any:
    if not path or not isinstance(path, str):
        return None
    path = path.strip()
    if path.startswith('context.'):
        path = path[len('context.') :]
    parts = path.split('.')
    cur: Any = context
    for part in parts:
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur
