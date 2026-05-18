import logging
import copy
import re

from .utils import _resolve_path_part, _resolve_path, _set_path, _MISSING
from .find_actions import run_find as _run_find_impl

logger = logging.getLogger(__name__)

class ActionRunner:
    """
    Dispatcher for executing non-API actions within a Scenario.
    """
    
    def __init__(self, context, log_func=None):
        self.context = context
        self._log_func = log_func

    def _log(self, msg):
        if self._log_func:
            self._log_func(msg)
        logger.info(msg)

    def _err_prefix(self):
        """Returns scenario/step context for error messages."""
        if not getattr(self, 'current_step', None):
            return ""
        s = getattr(self.current_step, 'scenario', None)
        name = s.name if s else "?"
        order = getattr(self.current_step, 'order', '?')
        atype = getattr(self.current_step, 'action_type', None) or 'ACTION'
        return f"Scenario '{name}' Step {order} ({atype}): "

    def run(self, step):
        """
        Executes the action defined in the ScenarioStep.
        Returns the result of the action.
        """
        self.current_step = step
        action_type = step.action_type
        config = step.action_config or {}
        
        if action_type == 'MERGE':
            return self._run_merge(config)
        elif action_type == 'FILTER':
            return self._run_filter(config)
        elif action_type == 'TRANSFORM':
            return self._run_transform(config)
        elif action_type == 'DIFF_OBJECTS':
            return self._run_diff_objects(config)
        elif action_type == 'TREE_STATS_BY_PATHS':
            return self._run_tree_stats_by_paths(config)
        elif action_type == 'ENRICH':
            return self._run_enrich(config)
        elif action_type == 'HIERARCHICAL_FLATTEN':
            return self._run_hierarchical_flatten(config)
        elif action_type == 'MULTI_HIERARCHICAL_FLATTEN':
            return self._run_multi_hierarchical_flatten(config)
        elif action_type == 'GROUP_BY':
            return self._run_group_by(config)
        elif action_type == 'FLATTEN_COLLECTION':
            return self._run_flatten_collection(config)
        elif action_type in ('FIND', 'FIND_OIDH'):
            return self._run_find(config)
        elif action_type == 'BUILD_OIDH_BLACKLIST':
            return self._run_build_oidh_blacklist(config)
        elif action_type == 'DICT_TO_LIST':
            return self._run_dict_to_list(config)
        elif action_type == 'RESOLVE_HIERARCHICAL_DISABLES':
            return self._run_resolve_hierarchical_disables(config)
        else:
            raise ValueError(f"{self._err_prefix()}Unknown action type: {action_type}")

    def _resolve_variable(self, var_name):
        """
        Resolves a variable from the context.
        Supports dot notation and bracket indices (e.g. 'context.users', 'item.data.geos[0].code').
        """
        if not isinstance(var_name, str):
            return var_name
            
        if '.' in var_name:
            parts = var_name.split('.')
            root = parts[0]
            if root == 'context':
                parts = parts[1:]
                root = parts[0]
            val = self.context.get(root, _MISSING)
            for part in parts[1:]:
                val = _resolve_path_part(val, part)
                if val is _MISSING:
                    return None
            return val if val is not _MISSING else None
        return self.context.get(var_name)

    def _run_merge(self, config):
        """
        Merges two lists of dictionaries.
        Config params:
        - input_a: Variable name for List A
        - input_b: Variable name for List B
        - join_key: Key to join on (legacy)
        - join_key_a: Key on List A (legacy, used when join_rules absent)
        - join_key_b: Key on List B (legacy, used when join_rules absent)
        - match_type: 'exact' (default), 'contains_a_in_b', 'contains_b_in_a' (legacy)
        - join_rules: List of {join_key_a, join_key_b, match_type} — all must match (AND)
        - how: 'inner' (default) or 'left'
        - fill_unmatched_with_zero: If true and how=left, unmatched items get right-side fields = 0 (default: false)
        """
        input_a_name = config.get('input_a')
        input_b_name = config.get('input_b')
        how = config.get('how', 'inner').lower()
        fill_unmatched_with_zero = config.get('fill_unmatched_with_zero', False)

        list_a = self._resolve_variable(input_a_name)
        list_b = self._resolve_variable(input_b_name)

        if not isinstance(list_a, list):
            raise ValueError(f"{self._err_prefix()}Merge input_a '{input_a_name}' must be a list, got {type(list_a)}")
        if not isinstance(list_b, list):
            raise ValueError(f"{self._err_prefix()}Merge input_b '{input_b_name}' must be a list, got {type(list_b)}")

        # Build join_rules: use join_rules if present, else legacy single-key
        join_rules = config.get('join_rules')
        if join_rules:
            rules = []
            for r in join_rules:
                key_a = r.get('join_key_a')
                key_b = r.get('join_key_b')
                if not key_a or not key_b:
                    raise ValueError(f"{self._err_prefix()}Each join rule must have join_key_a and join_key_b")
                resolved_a = self._resolve_variable(key_a)
                if resolved_a and isinstance(resolved_a, str):
                    key_a = resolved_a
                resolved_b = self._resolve_variable(key_b)
                if resolved_b and isinstance(resolved_b, str):
                    key_b = resolved_b
                rules.append({
                    'join_key_a': key_a,
                    'join_key_b': key_b,
                    'match_type': r.get('match_type', 'exact'),
                })
        else:
            legacy_key = config.get('join_key')
            join_key_a = config.get('join_key_a', legacy_key)
            join_key_b = config.get('join_key_b', legacy_key)
            if not join_key_a or not join_key_b:
                raise ValueError(f"{self._err_prefix()}Merge action requires 'join_rules' or 'join_key'/'join_key_a/b'")
            resolved_a = self._resolve_variable(join_key_a)
            if resolved_a and isinstance(resolved_a, str):
                join_key_a = resolved_a
            resolved_b = self._resolve_variable(join_key_b)
            if resolved_b and isinstance(resolved_b, str):
                join_key_b = resolved_b
            rules = [{'join_key_a': join_key_a, 'join_key_b': join_key_b, 'match_type': config.get('match_type', 'exact')}]

        # Collect all keys from list_b for fill_unmatched_with_zero
        right_keys = set()
        if fill_unmatched_with_zero and how == 'left':
            for item in list_b:
                if isinstance(item, dict):
                    right_keys.update(item.keys())

        def _item_matches_all_rules(item_a, item_b):
            for rule in rules:
                key_a, key_b = rule['join_key_a'], rule['join_key_b']
                mt = rule['match_type']
                val_a = item_a.get(key_a)
                val_b = item_b.get(key_b)
                val_a_str = str(val_a) if val_a is not None else ""
                val_b_str = str(val_b) if val_b is not None else ""
                ok = False
                if mt == 'exact':
                    ok = (val_a is not None and val_b is not None and str(val_a) == str(val_b))
                elif mt == 'contains_a_in_b':
                    ok = bool(val_a_str and val_a_str in val_b_str)
                elif mt == 'contains_b_in_a':
                    ok = bool(val_b_str and val_b_str in val_a_str)
                if not ok:
                    return False
            return True

        merged_list = []
        for item_a in list_a:
            if not isinstance(item_a, dict):
                continue

            found_match = None
            for item_b in list_b:
                if isinstance(item_b, dict) and _item_matches_all_rules(item_a, item_b):
                    found_match = item_b
                    break

            if found_match:
                new_item = copy.deepcopy(item_a)
                new_item.update(found_match)
                merged_list.append(new_item)
            elif how == 'left':
                new_item = copy.deepcopy(item_a)
                if fill_unmatched_with_zero and right_keys:
                    new_item.update({k: 0 for k in right_keys})
                merged_list.append(new_item)

        return merged_list

    def _run_filter(self, config):
        """
        Filters a list of dictionaries.
        Config params:
        - input: Variable name (e.g. 'context.campaigns')
        - match: 'all' (AND) or 'any' (OR). Default 'all'.
        - filters: List of dicts:
            - field: Field to check (e.g. 'status')
            - operator: '==', '!=', '>', '<', '>=', '<=', 'contains', 'in'
            - value: Value to compare against
        """
        input_name = config.get('input')
        match_mode = config.get('match', 'all').lower()
        filters = config.get('filters', [])
        
        data_list = self._resolve_variable(input_name)
        
        if not isinstance(data_list, list):
            raise ValueError(f"{self._err_prefix()}Filter input '{input_name}' must be a list, got {type(data_list)}")
            
        filtered_list = []
        
        for item in data_list:
            if not isinstance(item, dict):
                continue
                
            match_count = 0
            for f in filters:
                field = f.get('field')
                op = f.get('operator')
                target_val = f.get('value')
                
                # Resolve item value (support dot notation?)
                # For simplicity, supporting only direct keys or dot notation via helper if we wanted.
                # Let's support simple keys for now. 
                # Actually, item.get(field) handles simple keys. 
                # If we want nested, we'd need a helper. Let's do simple get.
                item_val = item.get(field)
                
                is_match = False
                
                try:
                    if op == '==':
                        is_match = (str(item_val) == str(target_val))
                    elif op == '!=':
                        is_match = (str(item_val) != str(target_val))
                    elif op == '>':
                        is_match = (float(item_val) > float(target_val))
                    elif op == '<':
                        is_match = (float(item_val) < float(target_val))
                    elif op == '>=':
                        is_match = (float(item_val) >= float(target_val))
                    elif op == '<=':
                         is_match = (float(item_val) <= float(target_val))
                    elif op == 'contains':
                        is_match = (str(target_val) in str(item_val))
                    elif op == 'in':
                        # target_val should be a list/string?
                        # If target_val is "active,paused" (comma string)
                        is_match = (str(item_val) in str(target_val))
                except (ValueError, TypeError):
                    is_match = False
                
                if is_match:
                    match_count += 1
            
            if match_mode == 'all':
                if match_count == len(filters):
                    filtered_list.append(item)
            elif match_mode == 'any':
                if match_count > 0:
                    filtered_list.append(item)
                    
        return filtered_list

    def _run_diff_objects(self, config):
        """
        Compares two objects from context and returns path-based differences.

        Config:
        - input_a: Variable name for object A (before)
        - input_b: Variable name for object B (after)
        - ignore_paths: Optional list of path prefixes to ignore
        - include_paths: Optional list of path prefixes to include (empty = all)
        - max_changes: Max number of change entries to return (default 1000)
        """
        input_a_name = config.get('input_a')
        input_b_name = config.get('input_b')
        if not input_a_name or not input_b_name:
            raise ValueError(f"{self._err_prefix()}DIFF_OBJECTS requires 'input_a' and 'input_b'.")

        obj_a = self._resolve_variable(input_a_name)
        obj_b = self._resolve_variable(input_b_name)

        if obj_a is None:
            raise ValueError(f"{self._err_prefix()}DIFF_OBJECTS input_a '{input_a_name}' not found in context.")
        if obj_b is None:
            raise ValueError(f"{self._err_prefix()}DIFF_OBJECTS input_b '{input_b_name}' not found in context.")

        ignore_paths = config.get('ignore_paths') or []
        include_paths = config.get('include_paths') or []
        max_changes = config.get('max_changes', 1000)
        try:
            max_changes = int(max_changes)
        except (TypeError, ValueError):
            max_changes = 1000
        if max_changes < 1:
            max_changes = 1

        def _normalize_paths(values):
            if not isinstance(values, list):
                return []
            normalized = []
            for v in values:
                if isinstance(v, str):
                    s = v.strip()
                    if s:
                        normalized.append(s)
            return normalized

        ignore_paths = _normalize_paths(ignore_paths)
        include_paths = _normalize_paths(include_paths)

        def _is_same_or_prefix(base, path):
            if base == path:
                return True
            return path.startswith(f"{base}.") or path.startswith(f"{base}[")

        def _is_prefix_of(base, path):
            # True when "base" can contain descendants of "path"
            if not path:
                return True
            if base == path:
                return True
            return base.startswith(f"{path}.") or base.startswith(f"{path}[")

        def _is_ignored(path):
            return any(_is_same_or_prefix(ignored, path) for ignored in ignore_paths)

        def _is_selected(path):
            if _is_ignored(path):
                return False
            if not include_paths:
                return True
            return any(_is_same_or_prefix(included, path) for included in include_paths)

        def _can_descend(path):
            if _is_ignored(path):
                return False
            if not include_paths:
                return True
            return any(_is_prefix_of(included, path) for included in include_paths)

        changes = []
        summary = {
            'replacements_count': 0,
            'additions_count': 0,
            'removals_count': 0,
        }
        truncated = False

        def _record(op, path, before_val, after_val):
            nonlocal truncated
            if not _is_selected(path):
                return
            if len(changes) >= max_changes:
                truncated = True
                return
            changes.append({
                'op': op,
                'path': path,
                'before': copy.deepcopy(before_val),
                'after': copy.deepcopy(after_val),
            })
            if op == 'replace':
                summary['replacements_count'] += 1
            elif op == 'add':
                summary['additions_count'] += 1
            elif op == 'remove':
                summary['removals_count'] += 1

        def _diff(a, b, path=''):
            nonlocal truncated
            if truncated or not _can_descend(path):
                return

            if isinstance(a, dict) and isinstance(b, dict):
                all_keys = set(a.keys()) | set(b.keys())
                for key in sorted(all_keys):
                    if truncated:
                        return
                    child_path = f"{path}.{key}" if path else str(key)
                    in_a = key in a
                    in_b = key in b
                    if in_a and not in_b:
                        _record('remove', child_path, a[key], None)
                    elif not in_a and in_b:
                        _record('add', child_path, None, b[key])
                    else:
                        _diff(a[key], b[key], child_path)
                return

            if isinstance(a, list) and isinstance(b, list):
                max_len = max(len(a), len(b))
                for idx in range(max_len):
                    if truncated:
                        return
                    child_path = f"{path}[{idx}]" if path else f"[{idx}]"
                    in_a = idx < len(a)
                    in_b = idx < len(b)
                    if in_a and not in_b:
                        _record('remove', child_path, a[idx], None)
                    elif not in_a and in_b:
                        _record('add', child_path, None, b[idx])
                    else:
                        _diff(a[idx], b[idx], child_path)
                return

            if a != b:
                _record('replace', path or '$', a, b)

        _diff(obj_a, obj_b)

        changes_count = len(changes)
        result = {
            'equal': changes_count == 0 and not truncated,
            'truncated': truncated,
            'max_changes': max_changes,
            'changes_count': changes_count,
            'summary': summary,
            'changes': changes,
        }
        self._log(
            f"DIFF_OBJECTS: compared '{input_a_name}' vs '{input_b_name}', "
            f"changes={changes_count}, truncated={truncated}"
        )
        return result

    def _run_dict_to_list(self, config):
        """
        Converts a dictionary to a list of dicts (one per key).
        Config params:
        - input: Variable path to the dict (e.g. 'context.domain_report.attributes.last_analysis_results')
        - key_field: Name of the output field for the dict key (default 'key')
        - value_fields: Optional list of keys to copy from each value; if omitted, all keys from the value dict are copied.
        - extra_fields: Optional dict {output_field_name: context_path} to add to each item (e.g. {"id": "item.id"}).
        """
        input_name = config.get('input')
        key_field = config.get('key_field', 'key')
        value_fields = config.get('value_fields')
        extra_fields = config.get('extra_fields') or {}

        if not input_name:
            raise ValueError(f"{self._err_prefix()}DICT_TO_LIST requires 'input' (variable path to the dict).")

        data = self._resolve_variable(input_name)
        if not isinstance(data, dict):
            raise ValueError(
                f"{self._err_prefix()}DICT_TO_LIST input '{input_name}' must be a dict, got {type(data)}"
            )

        result = []
        for k, v in data.items():
            item = {key_field: k}
            if isinstance(v, dict):
                if value_fields:
                    for f in value_fields:
                        item[f] = v.get(f)
                else:
                    item.update(copy.copy(v))
            else:
                item['value'] = v
            for out_key, path in extra_fields.items():
                if path is not None and str(path).strip():
                    item[out_key] = self._resolve_variable(str(path).strip())
            result.append(item)

        self._log(f"DICT_TO_LIST: {len(result)} items from '{input_name}'")
        return result

    def _run_resolve_hierarchical_disables(self, config):
        from .resolve_hierarchical_disables import resolve_hierarchical_disables

        if not isinstance(config, dict):
            raise ValueError(
                f"{self._err_prefix()}RESOLVE_HIERARCHICAL_DISABLES action_config must be an object."
            )
        return resolve_hierarchical_disables(
            context=self.context,
            config=config,
            log_func=self._log,
        )

    def _run_tree_stats_by_paths_legacy(self, config):
        """
        Computes branch-level leaf stats from changed JSON paths.

        This action is analysis-only and does not mutate state.

        Config:
        - state_input: variable path to source JSON object (required)
        - paths_input: variable path to changed paths payload (required)
        - path_field: field name when paths_input resolves to list of objects (default: 'path')
        - branch_spec: {
            branch_level_node: node name to anchor branch (required, e.g. 'paths'),
            leaf_collection: child collection on branch (required, e.g. 'offers'),
            leaf_id_field: optional field name to export leaf ids (e.g. 'offerId'),
            leaf_flags: optional list of boolean-ish flags to compute enabled leaves (e.g. ['enabled'])
          }
        - metrics: {
            count_total_leaves: bool,
            count_enabled_leaves: bool
          }
        """
        state_input = config.get('state_input')
        paths_input = config.get('paths_input')
        path_field = config.get('path_field', 'path')
        branch_spec = config.get('branch_spec') or {}
        metrics = config.get('metrics') or {}

        if not state_input:
            raise ValueError(f"{self._err_prefix()}TREE_STATS_BY_PATHS requires 'state_input'.")
        if not paths_input:
            raise ValueError(f"{self._err_prefix()}TREE_STATS_BY_PATHS requires 'paths_input'.")
        if not isinstance(branch_spec, dict):
            raise ValueError(f"{self._err_prefix()}TREE_STATS_BY_PATHS 'branch_spec' must be an object.")

        branch_level_node = branch_spec.get('branch_level_node')
        leaf_collection = branch_spec.get('leaf_collection')
        leaf_id_field = branch_spec.get('leaf_id_field')
        leaf_flags = branch_spec.get('leaf_flags') or []
        if not isinstance(leaf_flags, list):
            raise ValueError(f"{self._err_prefix()}TREE_STATS_BY_PATHS 'leaf_flags' must be a list.")

        if not branch_level_node or not isinstance(branch_level_node, str):
            raise ValueError(
                f"{self._err_prefix()}TREE_STATS_BY_PATHS requires branch_spec.branch_level_node (string)."
            )
        if not leaf_collection or not isinstance(leaf_collection, str):
            raise ValueError(
                f"{self._err_prefix()}TREE_STATS_BY_PATHS requires branch_spec.leaf_collection (string)."
            )

        state_obj = self._resolve_variable(state_input)
        if not isinstance(state_obj, dict):
            raise ValueError(
                f"{self._err_prefix()}TREE_STATS_BY_PATHS state_input '{state_input}' must resolve to object."
            )

        raw_paths = self._resolve_variable(paths_input)
        if raw_paths is None:
            raise ValueError(
                f"{self._err_prefix()}TREE_STATS_BY_PATHS paths_input '{paths_input}' was not found in context."
            )

        def _extract_path_entries(value):
            if isinstance(value, dict) and isinstance(value.get('changes'), list):
                return value.get('changes')
            if isinstance(value, list):
                return value
            return []

        path_entries = _extract_path_entries(raw_paths)
        normalized_paths = []
        unresolved = []

        for entry in path_entries:
            if isinstance(entry, str):
                p = entry.strip()
            elif isinstance(entry, dict):
                p_val = entry.get(path_field)
                p = p_val.strip() if isinstance(p_val, str) else ''
            else:
                p = ''

            if p:
                normalized_paths.append(p)
            else:
                unresolved.append({'input_path': None, 'reason': 'invalid_path_entry'})

        def _tokenize(path):
            tokens = []
            buf = []
            i = 0
            while i < len(path):
                ch = path[i]
                if ch == '.':
                    if buf:
                        tokens.append(''.join(buf))
                        buf = []
                    i += 1
                    continue
                if ch == '[':
                    if buf:
                        tokens.append(''.join(buf))
                        buf = []
                    end = path.find(']', i)
                    if end == -1:
                        return []
                    tokens.append(path[i:end + 1])
                    i = end + 1
                    continue
                buf.append(ch)
                i += 1
            if buf:
                tokens.append(''.join(buf))
            return [t for t in tokens if t]

        def _tokens_to_path(tokens):
            out = ''
            for tok in tokens:
                if tok.startswith('['):
                    out += tok
                else:
                    out = tok if not out else f"{out}.{tok}"
            return out

        def _normalize_bool(v):
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return v != 0
            if isinstance(v, str):
                return v.strip().lower() in ('1', 'true', 'yes', 'on')
            return False

        def _extract_branch_path(input_path):
            tokens = _tokenize(input_path)
            if not tokens:
                return None, 'invalid_path'
            try:
                idx = tokens.index(branch_level_node)
            except ValueError:
                return None, 'branch_level_node_not_found'
            end_idx = idx
            if idx + 1 < len(tokens) and tokens[idx + 1].startswith('['):
                end_idx = idx + 1
            return _tokens_to_path(tokens[:end_idx + 1]), None

        seen_branches = set()
        branch_paths = []
        for input_path in normalized_paths:
            branch_path, err = _extract_branch_path(input_path)
            if err:
                unresolved.append({'input_path': input_path, 'reason': err})
                continue
            if not branch_path:
                unresolved.append({'input_path': input_path, 'reason': 'invalid_path'})
                continue
            if branch_path not in seen_branches:
                seen_branches.add(branch_path)
                branch_paths.append((input_path, branch_path))

        count_total = bool(metrics.get('count_total_leaves', True))
        count_enabled = bool(metrics.get('count_enabled_leaves', True))

        branches = []
        for source_path, branch_path in branch_paths:
            branch_obj = _resolve_path(state_obj, branch_path)
            if branch_obj is _MISSING:
                unresolved.append({'input_path': source_path, 'reason': 'branch_not_found'})
                continue
            if not isinstance(branch_obj, dict):
                unresolved.append({'input_path': source_path, 'reason': 'branch_not_object'})
                continue

            leaves = branch_obj.get(leaf_collection, _MISSING)
            if leaves is _MISSING:
                unresolved.append({'input_path': source_path, 'reason': 'leaf_collection_not_found'})
                continue
            if not isinstance(leaves, list):
                unresolved.append({'input_path': source_path, 'reason': 'leaf_collection_not_list'})
                continue

            branch_info = {'branch_path': branch_path}
            if count_total:
                branch_info['total_leaves'] = len(leaves)
            if count_enabled:
                enabled_count = 0
                for leaf in leaves:
                    if not isinstance(leaf, dict):
                        continue
                    if not leaf_flags:
                        continue
                    if all(_normalize_bool(_resolve_path(leaf, flag)) for flag in leaf_flags):
                        enabled_count += 1
                branch_info['enabled_leaves'] = enabled_count
            if leaf_id_field:
                branch_info['leaf_ids'] = [
                    leaf.get(leaf_id_field)
                    for leaf in leaves
                    if isinstance(leaf, dict) and leaf_id_field in leaf
                ]
            branches.append(branch_info)

        result = {
            'summary': {
                'requested_paths': len(normalized_paths),
                'resolved_branches': len(branches),
                'unresolved_paths': len(unresolved),
            },
            'branches': branches,
            'unresolved': unresolved,
        }
        self._log(
            f"TREE_STATS_BY_PATHS: requested_paths={len(normalized_paths)}, "
            f"resolved_branches={len(branches)}, unresolved={len(unresolved)}"
        )
        return result

    def _run_tree_stats_by_paths(self, config):
        """
        TREE_STATS_BY_PATHS returns a reshaped payload:

        - ``by_branch``: object keyed by resolved branch_path; each value has only repeatable
          blocks `{prefix}_path`, `{prefix}_total`, `{prefix}_enabled`, `{prefix}_ids``.
        - Leaf collection (from branch_spec.leaf_collection) always gets a block using the
          sanitized collection name as prefix (e.g. ``offers_*``).

        Intermediate levels are optional ``node_metrics`` entries::

            {"name": "rules", "segment": "rules", "path_style": "upto_named_token",
             "item_flags": ["enabled"], "item_id_field": null}
            {"name": "paths", "segment": "paths", "path_style": "parent_plus_named_token",
             "item_flags": ["enabled"], "item_id_field": null}

        path_style:
          - ``upto_named_token`` — slice branch_path tokens up through the first literal
            ``segment`` (e.g. ``… .rules`` for the rules array).
          - ``parent_plus_named_token`` — slice tokens before ``segment``, then append
            ``segment`` (e.g. ``… .rules[N].paths`` for sibling paths arrays).

        If ``segment`` is omitted for ``parent_plus_named_token``, branch_spec.branch_level_node
        is used.
        """
        result = self._run_tree_stats_by_paths_legacy(config)

        branches = result.get('branches')
        if not isinstance(branches, list):
            return result

        summary = result.get('summary')
        unresolved = result.get('unresolved')
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(unresolved, list):
            unresolved = []

        state_input = config.get('state_input')
        state_obj = self._resolve_variable(state_input)
        if not isinstance(state_obj, dict):
            summary_out = dict(summary)
            summary_out['resolved_branches'] = 0
            payload = {'summary': summary_out, 'by_branch': {}, 'unresolved': unresolved}
            self._log(
                "TREE_STATS_BY_PATHS: state_input not a dict — empty by_branch"
            )
            return payload

        branch_spec = config.get('branch_spec') or {}
        branch_level_node = branch_spec.get('branch_level_node')
        if not isinstance(branch_level_node, str) or not branch_level_node.strip():
            summary_out = dict(summary)
            summary_out['resolved_branches'] = 0
            payload = {'summary': summary_out, 'by_branch': {}, 'unresolved': unresolved}
            self._log(
                "TREE_STATS_BY_PATHS: missing branch_level_node — empty by_branch"
            )
            return payload
        branch_level_node = branch_level_node.strip()

        leaf_collection = branch_spec.get('leaf_collection')
        if not isinstance(leaf_collection, str) or not leaf_collection.strip():
            summary_out = dict(summary)
            summary_out['resolved_branches'] = 0
            payload = {'summary': summary_out, 'by_branch': {}, 'unresolved': unresolved}
            return payload
        leaf_collection = leaf_collection.strip()
        leaf_flags = branch_spec.get('leaf_flags') or []
        if not isinstance(leaf_flags, list):
            leaf_flags = []
        leaf_id_field = branch_spec.get('leaf_id_field')

        def _tokenize(path):
            if not isinstance(path, str):
                return []
            tokens = []
            buf = []
            i = 0
            while i < len(path):
                ch = path[i]
                if ch == '.':
                    if buf:
                        tokens.append(''.join(buf))
                        buf = []
                    i += 1
                    continue
                if ch == '[':
                    if buf:
                        tokens.append(''.join(buf))
                        buf = []
                    end = path.find(']', i)
                    if end == -1:
                        return []
                    tokens.append(path[i : end + 1])
                    i = end + 1
                    continue
                buf.append(ch)
                i += 1
            if buf:
                tokens.append(''.join(buf))
            return [t for t in tokens if t]

        def _tokens_to_path(tokens):
            out = ''
            for tok in tokens:
                if tok.startswith('['):
                    out += tok
                else:
                    out = tok if not out else f"{out}.{tok}"
            return out

        def _normalize_bool(v):
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return v != 0
            if isinstance(v, str):
                return v.strip().lower() in ('1', 'true', 'yes', 'on')
            return False

        def _safe_prefix(s):
            if not isinstance(s, str):
                return ''
            return re.sub(r'[^a-z0-9_]', '_', s.strip().lower())

        def _collection_path(branch_tokens, path_style, segment):
            if segment not in branch_tokens:
                return None
            i = branch_tokens.index(segment)
            if path_style == 'upto_named_token':
                return _tokens_to_path(branch_tokens[: i + 1])
            if path_style == 'parent_plus_named_token':
                return _tokens_to_path(branch_tokens[:i] + [segment])
            return None

        def _summarize_collection(coll, item_flags, id_field):
            """Totals + enabled leaf count (logical AND across item_flags) + IDs (field or index)."""
            if not isinstance(coll, list):
                return 0, 0, []
            flags = item_flags if isinstance(item_flags, list) else []
            total = len(coll)
            enabled = 0
            ids = []
            for idx, item in enumerate(coll):
                if isinstance(item, dict):
                    if flags:
                        if all(
                            _normalize_bool(_resolve_path(item, f.strip()))
                            for f in flags
                            if isinstance(f, str) and f.strip()
                        ):
                            enabled += 1
                    if id_field and isinstance(id_field, str) and id_field.strip() and id_field in item:
                        ids.append(item.get(id_field))
                    else:
                        ids.append(idx)
                else:
                    ids.append(idx)
            return total, enabled, ids

        raw_metrics = config.get('node_metrics')
        node_specs = []
        if isinstance(raw_metrics, list):
            for m in raw_metrics:
                if not isinstance(m, dict):
                    continue
                name_p = _safe_prefix(m.get('name'))
                path_style = (m.get('path_style') or '').strip()
                seg = m.get('segment')
                segment = seg.strip() if isinstance(seg, str) and seg.strip() else None
                item_flags = m.get('item_flags', ['enabled'])
                if not isinstance(item_flags, list):
                    item_flags = ['enabled']
                id_field = m.get('item_id_field')

                if not name_p or path_style not in ('upto_named_token', 'parent_plus_named_token'):
                    continue
                if not segment:
                    if path_style == 'parent_plus_named_token':
                        segment = branch_level_node
                    else:
                        continue
                node_specs.append(
                    {
                        'prefix': name_p,
                        'path_style': path_style,
                        'segment': segment,
                        'item_flags': item_flags,
                        'item_id_field': id_field if isinstance(id_field, str) and id_field.strip() else None,
                    }
                )

        leaf_prefix = _safe_prefix(leaf_collection) or leaf_collection.lower()

        by_branch = {}

        def _summarize_leaf_block(branch_path, branch_obj):
            coll_path_str = f"{branch_path}.{leaf_collection}"
            leaves = (
                branch_obj.get(leaf_collection, _MISSING) if isinstance(branch_obj, dict) else _MISSING
            )
            if leaves is _MISSING or not isinstance(leaves, list):
                return {}

            lt, le, lids = _summarize_collection(leaves, leaf_flags, leaf_id_field)
            return {
                f'{leaf_prefix}_path': coll_path_str,
                f'{leaf_prefix}_total': lt,
                f'{leaf_prefix}_enabled': le,
                f'{leaf_prefix}_ids': lids,
            }

        for branch_info in branches:
            if not isinstance(branch_info, dict):
                continue
            branch_path = branch_info.get('branch_path')
            if not isinstance(branch_path, str) or not branch_path:
                continue

            branch_obj = _resolve_path(state_obj, branch_path)
            if branch_obj is _MISSING or not isinstance(branch_obj, dict):
                continue

            block = _summarize_leaf_block(branch_path, branch_obj)

            bp_tokens = _tokenize(branch_path)
            if not bp_tokens:
                by_branch[branch_path] = block
                continue

            for spec in node_specs:
                coll_path_str = _collection_path(bp_tokens, spec['path_style'], spec['segment'])
                if not coll_path_str:
                    continue
                coll_holder = _resolve_path(state_obj, coll_path_str)
                if coll_holder is _MISSING or not isinstance(coll_holder, list):
                    continue

                ct, ce, cids = _summarize_collection(
                    coll_holder, spec['item_flags'], spec['item_id_field']
                )
                pfx = spec['prefix']
                block[f'{pfx}_path'] = coll_path_str
                block[f'{pfx}_total'] = ct
                block[f'{pfx}_enabled'] = ce
                block[f'{pfx}_ids'] = cids

            by_branch[branch_path] = block

        summary_out = dict(summary)
        summary_out['resolved_branches'] = len(by_branch)
        payload = {'summary': summary_out, 'by_branch': by_branch, 'unresolved': unresolved}
        self._log(
            f"TREE_STATS_BY_PATHS: requested_paths={summary_out.get('requested_paths')}, "
            f"resolved_branches={len(by_branch)}, "
            f"unresolved={summary_out.get('unresolved_paths')}"
        )
        return payload

    def _run_transform(self, config):
        """
        Transforms a list of dictionaries.
        Config params:
        - input: Variable name (e.g. 'context.stats')
        - rename: Dict of {old_key: new_key}
        """
        input_name = config.get('input')
        operation = (config.get('operation') or '').strip().lower()
        rename_map = config.get('rename', {})
        calculate_map = config.get('calculate', {})
        select_fields = config.get('select')

        if operation in ('update_nested_by_predicate', 'count_nested_by_predicate'):
            if not input_name:
                raise ValueError(
                    f"{self._err_prefix()}Transform operation '{operation}' requires 'input'."
                )

            root_obj = self._resolve_variable(input_name)
            if isinstance(root_obj, list):
                if len(root_obj) == 1 and isinstance(root_obj[0], dict):
                    root_obj = root_obj[0]
                elif not root_obj:
                    root_obj = {}
                else:
                    raise ValueError(
                        f"{self._err_prefix()}Transform operation '{operation}' requires a single dict "
                        f"or one-element list, got list(len={len(root_obj)})."
                    )
            if not isinstance(root_obj, dict):
                raise ValueError(
                    f"{self._err_prefix()}Transform operation '{operation}' requires dict input, got {type(root_obj)}"
                )

            scope_path = config.get('scope_path') or ''
            target_collections = config.get('target_collections') or []
            predicate = config.get('predicate') or {}
            patch = config.get('patch') or {}
            match_mode = (config.get('match_mode') or 'all').strip().lower()

            if not isinstance(target_collections, list) or not target_collections:
                raise ValueError(f"{self._err_prefix()}update_nested_by_predicate requires non-empty list 'target_collections'.")
            if not isinstance(predicate, dict):
                raise ValueError(f"{self._err_prefix()}{operation} requires object 'predicate'.")
            if operation == 'update_nested_by_predicate':
                if not isinstance(patch, dict) or not patch:
                    raise ValueError(f"{self._err_prefix()}update_nested_by_predicate requires non-empty object 'patch'.")
                result_obj = copy.deepcopy(root_obj)
            else:
                result_obj = root_obj

            def _resolve_scope_nodes():
                if not scope_path:
                    return [(result_obj, '')]
                scope_val = _resolve_path(result_obj, scope_path)
                if scope_val is _MISSING:
                    return []
                if isinstance(scope_val, list):
                    out = []
                    for idx, node in enumerate(scope_val):
                        path = f"{scope_path}[{idx}]"
                        out.append((node, path))
                    return out
                return [(scope_val, scope_path)]

            def _walk_collection_pattern(base_node, base_path, pattern):
                segments = [s for s in str(pattern).split('.') if s]
                current = [(base_node, base_path)]
                for seg in segments:
                    next_items = []
                    is_list_segment = seg.endswith('[]')
                    key = seg[:-2] if is_list_segment else seg
                    for node, node_path in current:
                        if not isinstance(node, dict):
                            continue
                        child = node.get(key, _MISSING)
                        child_path = f"{node_path}.{key}" if node_path else key
                        if child is _MISSING:
                            continue
                        if is_list_segment:
                            if isinstance(child, list):
                                for idx, item in enumerate(child):
                                    next_items.append((item, f"{child_path}[{idx}]"))
                        else:
                            next_items.append((child, child_path))
                    current = next_items
                return current

            def _resolve_template_value(value):
                if isinstance(value, str):
                    m = re.fullmatch(r'\s*\{\{\s*([^}]+?)\s*\}\}\s*', value)
                    if m:
                        var_name = m.group(1).strip()
                        resolved = self._resolve_variable(var_name)
                        if resolved is not None:
                            return resolved
                return value

            def _evaluate_condition(cond, item):
                field = cond.get('field')
                op = cond.get('op', '==')
                if not field:
                    return False
                item_val = _resolve_path(item, str(field))
                if item_val is _MISSING:
                    return False
                if 'value_from' in cond:
                    target_val = self._resolve_variable(cond.get('value_from'))
                else:
                    target_val = cond.get('value')
                target_val = _resolve_template_value(target_val)

                if op == '==':
                    return item_val == target_val
                if op == '!=':
                    return item_val != target_val
                if op == 'in':
                    return item_val in target_val if isinstance(target_val, (list, tuple, set, str)) else False
                if op == 'contains':
                    return str(target_val) in str(item_val)
                raise ValueError(f"{self._err_prefix()}Unsupported predicate op '{op}' in update_nested_by_predicate.")

            def _matches(item):
                if not isinstance(item, dict):
                    return False
                conditions = predicate.get('conditions')
                if not conditions:
                    conditions = [predicate]
                results = [_evaluate_condition(c, item) for c in conditions if isinstance(c, dict)]
                if not results:
                    return False
                if match_mode == 'any':
                    return any(results)
                return all(results)

            matched_count = 0
            updated_count = 0
            for scope_node, scope_node_path in _resolve_scope_nodes():
                for pattern in target_collections:
                    for candidate, candidate_path in _walk_collection_pattern(scope_node, scope_node_path, pattern):
                        if _matches(candidate):
                            matched_count += 1
                            if operation == 'update_nested_by_predicate' and isinstance(candidate, dict):
                                changed = False
                                for patch_key, patch_value in patch.items():
                                    resolved_patch = _resolve_template_value(patch_value)
                                    old_val = candidate.get(patch_key, _MISSING)
                                    if old_val is _MISSING or old_val != resolved_patch:
                                        candidate[patch_key] = resolved_patch
                                        changed = True
                                if changed:
                                    updated_count += 1

            if operation == 'count_nested_by_predicate':
                self._log(
                    f"TRANSFORM count_nested_by_predicate: matched={matched_count}, input='{input_name}'"
                )
                return {'matched_count': matched_count}

            self._log(
                f"TRANSFORM update_nested_by_predicate: matched={matched_count}, updated={updated_count}, input='{input_name}'"
            )
            return result_obj

        if operation == 'count_flag_in_scenario_results':
            input_name = config.get('input')
            flag_name = config.get('context_flag') or 'offer_enabled_in_campaign'
            id_field = config.get('id_context_field') or 'id'
            entries = self._resolve_variable(input_name)
            if entries is None:
                raise ValueError(
                    f"{self._err_prefix()}count_flag_in_scenario_results input '{input_name}' not found in context."
                )
            if not isinstance(entries, list):
                raise ValueError(
                    f"{self._err_prefix()}count_flag_in_scenario_results input must be a list, got {type(entries)}"
                )
            still_active_ids = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if entry.get('success') is False:
                    continue
                ctx = entry.get('context') or entry.get('context_variables') or {}
                if not isinstance(ctx, dict):
                    continue
                if not ctx.get(flag_name):
                    continue
                campaign_id = ctx.get(id_field)
                if campaign_id is None and isinstance(entry.get('item'), dict):
                    campaign_id = entry['item'].get('id')
                still_active_ids.append(campaign_id)
            summary = {
                'still_active_count': len(still_active_ids),
                'still_active_campaign_ids': still_active_ids,
                'offer_still_active_anywhere': len(still_active_ids) > 0,
            }
            self._log(
                'TRANSFORM count_flag_in_scenario_results: '
                f"still_active_count={summary['still_active_count']}"
            )
            return summary
        
        # GLOBAL CALCULATION MODE (No Input List)
        if not input_name:
            if not calculate_map:
                raise ValueError(f"{self._err_prefix()}Transform Action requires 'input' list OR 'calculate' map.")
            
            from .safe_eval import SafeEvaluator
            evaluator = SafeEvaluator(context=self.context)
            
            result_obj = {}
            for target_field, expression in calculate_map.items():
                 try:
                     val = evaluator.evaluate(expression)
                     result_obj[target_field] = val
                     # Allow subsequent calculations to use this result
                     evaluator.context[target_field] = val
                 except Exception as e:
                     raise ValueError(f"{self._err_prefix()}Error calculating '{target_field}': {e}")
            
            # If there's only one calculation key and it matches the intended output name? 
            # No, let's return a clean dictionary.
            return result_obj

        data_list = self._resolve_variable(input_name)
        
        if not isinstance(data_list, list):
             raise ValueError(f"{self._err_prefix()}Transform input '{input_name}' must be a list, got {type(data_list)}")
             
        # Initialize SafeEvaluator if calculation is needed
        evaluator = None
        base_context = {}
        if calculate_map:
            from .safe_eval import SafeEvaluator
            # We initialize one evaluator and update its context per item
            # Initialize with global context to allow access to global variables
            evaluator = SafeEvaluator(context=self.context.copy())
            base_context = evaluator.context.copy()
             
        transformed_list = []
        for item in data_list:
            if not isinstance(item, dict):
                continue
                
            new_item = copy.deepcopy(item)
            
            # Application of Rename
            for old_key, new_key in rename_map.items():
                if old_key in new_item:
                    new_item[new_key] = new_item.pop(old_key)
            
            # Application of Calculation
            if calculate_map and evaluator:
                # Prepare context: Base functions + Item fields
                # We interpret field values as variables
                # Note: We must be careful about overwriting functions (e.g. if item has 'len')
                # But item fields take precedence for calculation usually.
                
                # Optimized context update
                # We start with base context (funcs) and update with item
                eval_ctx = base_context.copy()
                eval_ctx.update(new_item)
                
                # Enhanced Context: Add 'val' helper to get item value by key name
                # Useful when key is dynamic: float(val(tracker.keys.CLICKS))
                def get_item_val(key_name):
                    val = new_item.get(key_name)
                    # logger.info(f"DEBUG: val('{key_name}') -> {val} (Type: {type(val)})")
                    return val
                
                eval_ctx['val'] = get_item_val
                
                evaluator.context = eval_ctx
                
                for target_field, expression in calculate_map.items():
                    try:
                        val = evaluator.evaluate(expression)
                        new_item[target_field] = val
                    except Exception as e:
                        logger.warning(f"Calculation failed for field '{target_field}': {e}. Expression: {expression}")
                        # Dump context keys for debugging (filtered)
                        debug_keys = {k: v for k, v in eval_ctx.items() if isinstance(v, (str, int, float))}
                        logger.info(f"DEBUG Context for '{target_field}': {debug_keys}")
                        new_item[target_field] = None
            
            # Application of Selection (Projection)
            if select_fields:
                if not isinstance(select_fields, list):
                    # Trying to be helpful if user passed a string "a,b" ?
                    # But strict typing is safer. Let's assume list.
                    logger.warning(f"Transform 'select' must be a list, got {type(select_fields)}. Ignoring.")
                else:
                    filtered_item = {}
                    for field in select_fields:
                        # Resolve Dynamic Key Name (e.g. tracker.keys.CAMPAIGN_ID)
                        real_field = field
                        resolved = self._resolve_variable(field)
                        if resolved and isinstance(resolved, str):
                            real_field = resolved
                            
                        if real_field in new_item:
                            filtered_item[real_field] = new_item[real_field]
                        else:
                            # Optional: Check if we want to rename it?
                            # For now, just keeping the value under the resolved key name
                            pass
                            
                    new_item = filtered_item

            transformed_list.append(new_item)
            
        return transformed_list

    def _run_enrich(self, config):
        """
        Enriches (updates) a list of dictionaries by joining with another list
        and extending a nested list field with items from source.
        
        Config:
        - input: Target list variable (e.g. 'context.campaigns')
        - source: Source list variable (e.g. 'context.optimization_data')
        - join: Dict {target_key: source_key} — supports nested paths (e.g. 'data.id': 'cmp_id')
        - update_field: Field in target item to extend (e.g. 'data.excluded_sources'). Supports nested paths.
        - operation: 'extend' (default) or 'set_field'. 'append' is removed — use extend for both single values and lists.
        - set_field: (for operation 'set_field') Target field to set with a single dict (e.g. 'customRotation'). Supports nested paths.
        - source_select: (for operation 'set_field') List of keys to take from the matched source item (e.g. ['id', 'defaultPaths', 'rules']). First matching source is used.
        - mapping: Dict defining structure of new items.
                   Values starting with 'source.' or 'target.' are resolved dynamically (supports nested paths, e.g. 'source.data.adspace').
        - value_key: If set, extend only with new_obj[value_key] (e.g. int/str or list) instead of full dict.
                     Use when update_field is a list of primitives, not dicts.
                     When value_key points to a list, extends with deduplication (only adds values not already present).
        - unique_keys: List of keys to check for duplicates (when extending with dicts).
                       Ignored when value_key is set (uniqueness by value itself).
        """
        target_list_name = config.get('input')
        source_list_name = config.get('source')
        join_config = config.get('join', {})
        update_field = config.get('update_field')
        set_field = config.get('set_field')
        source_select = config.get('source_select')
        operation = config.get('operation', 'extend')
        if operation == 'append':
            raise ValueError(
                f"{self._err_prefix()}ENRICH operation 'append' is removed. Use 'extend' instead."
            )
        if operation == 'set_field':
            if not set_field or not source_select or not isinstance(source_select, list):
                raise ValueError(
                    f"{self._err_prefix()}ENRICH operation 'set_field' requires 'set_field' and 'source_select' (list of keys)."
                )
        elif operation != 'extend':
            raise ValueError(
                f"{self._err_prefix()}ENRICH operation must be 'extend' or 'set_field', got '{operation}'."
            )
        if operation == 'extend' and not update_field:
            raise ValueError(
                f"{self._err_prefix()}ENRICH operation 'extend' requires 'update_field'."
            )
        mapping = config.get('mapping', {})
        value_key = config.get('value_key')
        unique_keys = config.get('unique_keys', [])

        target_list = self._resolve_variable(target_list_name)
        source_list = self._resolve_variable(source_list_name)
        
        if not isinstance(target_list, list):
             raise ValueError(f"{self._err_prefix()}Enrich input '{target_list_name}' must be a list, got {type(target_list)}")
        if not isinstance(source_list, list):
             raise ValueError(f"{self._err_prefix()}Enrich source '{source_list_name}' must be a list, got {type(source_list)}")
        if not join_config:
             raise ValueError(f"{self._err_prefix()}Enrich action requires 'join' configuration")
             
        target_key_field = list(join_config.keys())[0]
        source_key_field = list(join_config.values())[0]

        logger.info(f"ENRICH Config: Target={target_list_name}, Source={source_list_name}, Join={target_key_field}:{source_key_field}")

        # 1. Index Source by Key
        source_map = {}
        for item in source_list:
            if isinstance(item, dict):
                val = _resolve_path(item, source_key_field)
                val = val if val is not _MISSING else None
                key_val = str(val) if val is not None else None
                if key_val:
                    if key_val not in source_map:
                        source_map[key_val] = []
                    source_map[key_val].append(item)
        
        logger.info(f"Source Map built with {len(source_map)} keys.")

        result_list = []
        updates_count = 0

        # 2. Process Target List
        for item in target_list:
            if not isinstance(item, dict):
                result_list.append(item) # Copy non-dict items as is?
                continue
                
            # Deep copy to avoid modifying original context variable in-place
            new_item = copy.deepcopy(item)
            
            key_val_raw = _resolve_path(new_item, target_key_field)
            key_val = str(key_val_raw) if key_val_raw is not _MISSING else None
            matching_source_items = source_map.get(key_val, [])

            if operation == 'set_field' and matching_source_items:
                # Take first matching source item; build dict with only source_select keys; set on target
                first_source = matching_source_items[0]
                value_dict = {}
                for k in source_select:
                    v = _resolve_path(first_source, k)
                    value_dict[k] = v if v is not _MISSING else None
                _set_path(new_item, set_field, value_dict)
                updates_count += 1
                logger.info(f"Set field '{set_field}' for item (key={key_val}) from source (keys={source_select}).")
            elif matching_source_items and operation == 'extend':
                # Ensure update_field is a list (supports nested paths like data.excluded_sources)
                current_list = _resolve_path(new_item, update_field)
                if current_list is _MISSING or current_list is None:
                    _set_path(new_item, update_field, [])
                    current_list = _resolve_path(new_item, update_field)
                elif not isinstance(current_list, list):
                    logger.warning(f"Field '{update_field}' is not a list. Resetting to empty list.")
                    _set_path(new_item, update_field, [])
                    current_list = _resolve_path(new_item, update_field)
                initial_len = len(current_list)
                
                for source_item in matching_source_items:
                    # Create new object
                    new_obj = {}
                    # Determine processing order
                    field_order = config.get('field_order', [])
                    mapping_keys = list(mapping.keys())
                    # Order: explicitly ordered keys first, then the rest
                    ordered_keys = [k for k in field_order if k in mapping_keys] + [k for k in mapping_keys if k not in field_order]

                    for map_key in ordered_keys:
                        map_val = mapping[map_key]
                        if isinstance(map_val, str):
                            if map_val.startswith('source.'):
                                field = map_val.split('.', 1)[1]
                                val = _resolve_path(source_item, field)
                                new_obj[map_key] = val if val is not _MISSING else None
                            elif map_val.startswith('target.'):
                                field = map_val.split('.', 1)[1]
                                val = _resolve_path(new_item, field)
                                new_obj[map_key] = val if val is not _MISSING else None
                            elif map_val == '@TIMESTAMP':
                                import time
                                new_obj[map_key] = int(time.time() * 1000)
                            else:
                                new_obj[map_key] = map_val
                        else:
                            new_obj[map_key] = map_val
                    
                    # Resolve value to extend: full dict or single value or list (when value_key)
                    if value_key is not None:
                        append_val = new_obj.get(value_key)
                        if append_val is None:
                            continue  # Skip when value_key points to missing/None
                        if isinstance(append_val, list):
                            # List: extend with deduplication — only add values not already present
                            current_list.extend([v for v in append_val if v not in current_list])
                            continue
                        is_duplicate = append_val in current_list
                    else:
                        append_val = new_obj
                        is_duplicate = False
                        if unique_keys:
                            for existing in current_list:
                                match_count = 0
                                for u_key in unique_keys:
                                    val_existing = str(existing.get(u_key)) if isinstance(existing, dict) else str(existing)
                                    val_new = str(new_obj.get(u_key))
                                    if val_existing == val_new:
                                        match_count += 1
                                if match_count == len(unique_keys):
                                    is_duplicate = True
                                    if val_new == 'None':
                                        logger.warning(f"Duplicate found with Key=None. Might be missing field '{unique_keys}' in source?")
                                    break

                    if not is_duplicate and operation == 'extend':
                        current_list.extend([append_val])
                
                if len(current_list) > initial_len:
                    updates_count += 1
                    logger.info(f"Updated item {key_val}: Added {len(current_list) - initial_len} items.")
            
            # Process Root Mapping (update parent object fields)
            root_mapping = config.get('root_mapping', {})
            if root_mapping:
                for map_key, map_val in root_mapping.items():
                    if map_val == '@TIMESTAMP':
                        import time
                        new_item[map_key] = int(time.time() * 1000)
                    else:
                        new_item[map_key] = map_val

            result_list.append(new_item)
            
        logger.info(f"Enrichment complete. Updated {updates_count} items.")
        return result_list

    def _run_hierarchical_flatten(self, config):
        """
        Flattens a hierarchical list: parent (level 1) → child (level 2).
        For each child, adds parent's name as t2; child's name as t7.
        Returns only child items with t2 and t7 set.

        Config:
        - input: Variable name (e.g. 'tXtX')
        - level_key: Key for level ('level', default)
        - parent_level: Value for parent ('1', default)
        - child_level: Value for child ('2', default)
        - name_key: Key for name ('name', default)
        - parent_key: Output key for parent name ('t2', default)
        - child_key: Output key for child name ('t7', default)
        """
        input_name = config.get('input')
        level_key = config.get('level_key', 'level')
        parent_level = config.get('parent_level', '1')
        child_level = config.get('child_level', '2')
        name_key = config.get('name_key', 'name')
        parent_key = config.get('parent_key', 't2')
        child_key = config.get('child_key', 't7')

        input_list = self._resolve_variable(input_name)
        if not isinstance(input_list, list):
            raise ValueError(
                f"{self._err_prefix()}HIERARCHICAL_FLATTEN input '{input_name}' must be a list, got {type(input_list)}"
            )

        current_t2 = None
        result = []
        for item in input_list:
            if not isinstance(item, dict):
                continue
            level_val = str(item.get(level_key, ''))
            if level_val == parent_level:
                current_t2 = item.get(name_key)
            elif level_val == child_level:
                new_item = copy.deepcopy(item)
                new_item[child_key] = item.get(name_key)
                new_item[parent_key] = current_t2
                result.append(new_item)

        logger.info(f"HIERARCHICAL_FLATTEN: {len(result)} child items from '{input_name}'")
        return result

    def _run_multi_hierarchical_flatten(self, config):
        """
        Flattens a multi-level hierarchical list (e.g. 5 levels).
        Input: flat list of items, each with level_key (e.g. 'level') and name_key (e.g. 'name').
        Levels must be ordered root→leaf in the list (e.g. level 1, then 2, then 3...).
        Output: each leaf item (or every item if output_leaf_only=False) with ancestor
        names added as output_keys (e.g. t1, t2, t3, t4, t5).

        Config:
        - input: Variable name (e.g. 'context.tXtX')
        - level_key: Key for level ('level', default)
        - name_key: Key for name ('name', default)
        - levels: List of level values in order, e.g. ['1', '2', '3', '4', '5']
        - output_keys: List of output keys for each level, e.g. ['t1', 't2', 't3', 't4', 't5']
        - output_leaf_only: If True (default), only emit items at the last level; else emit every item.
        - extra_outputs: Optional list of {level, source_field, output_key} to add fields from
          ancestor levels. E.g. [{"level": "1", "source_field": "entity_id", "output_key": "cmp_id"},
          {"level": "4", "source_field": "entity_id", "output_key": "offer_id"}]
        """
        input_name = config.get('input')
        level_key = config.get('level_key', 'level')
        name_key = config.get('name_key', 'name')
        levels = config.get('levels')
        output_keys = config.get('output_keys')
        output_leaf_only = config.get('output_leaf_only', True)
        extra_outputs = config.get('extra_outputs') or []

        if not levels or not isinstance(levels, list):
            raise ValueError(
                f"{self._err_prefix()}MULTI_HIERARCHICAL_FLATTEN requires 'levels' (list, e.g. ['1','2','3','4','5'])"
            )
        if not output_keys or not isinstance(output_keys, list) or len(output_keys) != len(levels):
            raise ValueError(
                f"{self._err_prefix()}MULTI_HIERARCHICAL_FLATTEN requires 'output_keys' (list, same length as 'levels')"
            )

        input_list = self._resolve_variable(input_name)
        if not isinstance(input_list, list):
            raise ValueError(
                f"{self._err_prefix()}MULTI_HIERARCHICAL_FLATTEN input '{input_name}' must be a list, got {type(input_list)}"
            )

        current = {}
        current_items = {}  # level -> full item (for extra_outputs)
        result = []
        for item in input_list:
            if not isinstance(item, dict):
                continue
            level_val = str(item.get(level_key, ''))
            if level_val not in levels:
                continue
            idx = levels.index(level_val)
            for i in range(idx + 1, len(levels)):
                lv = levels[i]
                current.pop(lv, None)
                current_items.pop(lv, None)
            current[level_val] = item.get(name_key)
            current_items[level_val] = item

            is_leaf = idx == len(levels) - 1
            if output_leaf_only and not is_leaf:
                continue

            new_item = copy.deepcopy(item)
            for i, lv in enumerate(levels):
                if lv in current:
                    new_item[output_keys[i]] = current[lv]
            for spec in extra_outputs:
                if not isinstance(spec, dict):
                    continue
                lv = str(spec.get('level', ''))
                src = spec.get('source_field')
                out_key = spec.get('output_key')
                if lv and src and out_key and lv in current_items:
                    new_item[out_key] = current_items[lv].get(src)
            result.append(new_item)

        logger.info(
            f"MULTI_HIERARCHICAL_FLATTEN: {len(result)} items from '{input_name}' (levels={levels})"
        )
        return result

    def _run_flatten_collection(self, config):
        """
        Expands a list field into multiple rows (unnest/explode).
        For each input item, creates one output row per element in the list field.

        Config:
        - input: Variable name (e.g. 'item' when iterating, or 'context.black_list')
        - list_field: Field containing the array (e.g. 'source')
        - parent_key: Key to copy from parent to each row (e.g. 'campaignId')
        - item_key: Output key for the list element (e.g. 'referer')
        """
        input_name = config.get('input')
        list_field = config.get('list_field', 'source')
        parent_key = config.get('parent_key', 'campaignId')
        item_key = config.get('item_key', 'referer')

        input_val = self._resolve_variable(input_name)
        if input_val is None:
            raise ValueError(
                f"{self._err_prefix()}FLATTEN_COLLECTION input '{input_name}' not found in context."
            )
        # Support single object (e.g. 'item' when iterating)
        if not isinstance(input_val, list):
            input_list = [input_val] if isinstance(input_val, dict) else []
        else:
            input_list = input_val

        result = []
        for parent in input_list:
            if not isinstance(parent, dict):
                continue
            list_vals = parent.get(list_field)
            if not isinstance(list_vals, (list, tuple)):
                continue
            parent_val = parent.get(parent_key)
            for val in list_vals:
                result.append({parent_key: parent_val, item_key: val})

        logger.info(f"FLATTEN_COLLECTION: {len(result)} rows from '{input_name}' (list_field={list_field})")
        return result

    def _run_find(self, config):
        """
        FIND dispatcher: oidh_match (default) vs lookup_in_tree. Legacy step type FIND_OIDH
        is still accepted in run() but is not exposed as a model choice.
        """
        return _run_find_impl(
            config=config,
            context=self.context,
            resolve_variable=self._resolve_variable,
            log_func=self._log,
            err_prefix=self._err_prefix(),
        )

    def _run_build_oidh_blacklist(self, config):
        """
        Build OIDH blacklist and remaining offers from OIDH list and campaigns current state.

        From campaigns_current_state: for each (cmp_id, rule_id) build the set of offer_ids
        (from customRotation.rules[].paths[].offers[].offerId). From OIDH list: collect
        excluded offer_ids and unique (device_type, os, t2) per (cmp_id, matched_rule_id).
        Remaining = rule_offers - excluded. If remaining is empty, add (cmp_id, device_type, os, t2)
        to blacklist for each unique triple. Also output remaining_offers per (cmp_id, device_type, os, t2).

        Config:
        - input_oidh: Variable name for OIDH list (items: cmp_id, matched_rule_id, offer_id, device_type, os, t2)
        - input_campaigns_state: Variable name for campaigns list (each: id, customRotation.rules; rule: id, paths; path: offers; offer: offerId)
        Returns: {"blacklist": [...], "remaining_offers": [...]}. Store in step output variable.
        """
        input_oidh_name = config.get('input_oidh') or config.get('input')
        input_campaigns_name = config.get('input_campaigns_state')

        if not input_oidh_name or not input_campaigns_name:
            raise ValueError(
                f"{self._err_prefix()}BUILD_OIDH_BLACKLIST requires 'input_oidh' and 'input_campaigns_state'."
            )

        oidh_list = self._resolve_variable(input_oidh_name)
        campaigns_list = self._resolve_variable(input_campaigns_name)

        if oidh_list is None:
            raise ValueError(
                f"{self._err_prefix()}BUILD_OIDH_BLACKLIST input_oidh '{input_oidh_name}' not found in context."
            )
        if not isinstance(oidh_list, list):
            raise ValueError(
                f"{self._err_prefix()}BUILD_OIDH_BLACKLIST input_oidh must be a list, got {type(oidh_list)}"
            )
        if campaigns_list is None:
            raise ValueError(
                f"{self._err_prefix()}BUILD_OIDH_BLACKLIST input_campaigns_state '{input_campaigns_name}' not found in context."
            )
        if not isinstance(campaigns_list, list):
            raise ValueError(
                f"{self._err_prefix()}BUILD_OIDH_BLACKLIST input_campaigns_state must be a list, got {type(campaigns_list)}"
            )

        def _nk(v):
            return str(v) if v is not None else None

        # 1. Build rule_offers[(cmp_id, rule_id)] from campaigns_current_state
        rule_offers = {}
        for camp in campaigns_list:
            if not isinstance(camp, dict):
                continue
            cmp_id = _nk(camp.get('id'))
            if not cmp_id:
                continue
            custom = camp.get('customRotation') or {}
            rules = custom.get('rules') if isinstance(custom, dict) else []
            if not isinstance(rules, list):
                continue
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                rule_id = _nk(rule.get('id'))
                if not rule_id:
                    continue
                paths = rule.get('paths') or []
                if not isinstance(paths, list):
                    continue
                offer_ids = set()
                for path in paths:
                    if not isinstance(path, dict):
                        continue
                    offers = path.get('offers') or []
                    if not isinstance(offers, list):
                        continue
                    for off in offers:
                        if isinstance(off, dict) and off.get('offerId') is not None:
                            offer_ids.add(_nk(off.get('offerId')))
                rule_offers[(cmp_id, rule_id)] = offer_ids

        # 2. Process OIDH: excluded and triples per (cmp_id, rule_id)
        excluded = {}
        triples = {}
        for item in oidh_list:
            if not isinstance(item, dict):
                continue
            cmp_id = _nk(item.get('cmp_id'))
            rule_id = _nk(item.get('matched_rule_id'))
            offer_id = _nk(item.get('offer_id'))
            device_type = item.get('device_type')
            os_val = item.get('os')
            t2_val = item.get('t2')
            if not cmp_id or rule_id is None:
                continue
            key = (cmp_id, rule_id)
            if key not in excluded:
                excluded[key] = set()
                triples[key] = set()
            if offer_id:
                excluded[key].add(offer_id)
            triples[key].add((device_type, os_val, t2_val))

        # 3. Build blacklist and remaining_offers
        blacklist = []
        remaining_offers = []
        for key in excluded:
            cmp_id, rule_id = key
            offers = rule_offers.get(key, set())
            rem = offers - excluded[key]
            if rem:
                for (d, o, t) in triples[key]:
                    remaining_offers.append({
                        'cmp_id': cmp_id,
                        'device_type': d,
                        'os': o,
                        't2': t,
                        'remaining_offer_ids': list(rem),
                    })
            if not rem:
                for (d, o, t) in triples[key]:
                    blacklist.append({
                        'cmp_id': cmp_id,
                        'device_type': d,
                        'os': o,
                        't2': t,
                    })

        logger.info(
            f"BUILD_OIDH_BLACKLIST: blacklist={len(blacklist)} entries, remaining_offers={len(remaining_offers)} rows "
            f"(from '{input_oidh_name}', '{input_campaigns_name}')"
        )
        return {'blacklist': blacklist, 'remaining_offers': remaining_offers}

    def _run_group_by(self, config):
        """
        Groups a list by key(s) and aggregates other fields.

        Config:
        - input: Variable name (e.g. 'traffic_source_stats_to1_blacklist')
        - group_by: Key or list of keys to group by. Supports Global Variables
          (e.g. 'traffic_source_tracker_obj.keys.CAMPAIGN_ID_IN_STATS' -> 'campaignId')
        - aggregate: Dict {output_field: {op, field}}.
          op: 'collect'|'list', 'sum', 'avg', 'min', 'max', 'count', 'first', 'last', 'concat', 'count_distinct'
          field: source field name (supports Global Variables)
        """
        input_name = config.get('input')
        group_by = config.get('group_by')
        aggregate = config.get('aggregate', {})

        input_list = self._resolve_variable(input_name)
        if not isinstance(input_list, list):
            raise ValueError(
                f"{self._err_prefix()}GROUP_BY input '{input_name}' must be a list, got {type(input_list)}"
            )
        if not group_by:
            raise ValueError(f"{self._err_prefix()}GROUP_BY requires 'group_by'")
        if not aggregate:
            raise ValueError(f"{self._err_prefix()}GROUP_BY requires 'aggregate'")

        group_keys = [group_by] if isinstance(group_by, str) else list(group_by)
        # Resolve Global Variables (e.g. traffic_source_tracker_obj.keys.CAMPAIGN_ID_IN_STATS -> campaignId)
        resolved_group_keys = []
        for k in group_keys:
            resolved = self._resolve_variable(k)
            resolved_group_keys.append(resolved if (resolved and isinstance(resolved, str)) else k)

        def _group_key(item):
            return tuple(item.get(rk) for rk in resolved_group_keys)

        groups = {}
        for item in input_list:
            if not isinstance(item, dict):
                continue
            key = _group_key(item)
            if key not in groups:
                groups[key] = []
            groups[key].append(item)

        result = []
        for key, items in groups.items():
            out = {}
            for i, rk in enumerate(resolved_group_keys):
                out[rk] = key[i]
            for out_field, agg_spec in aggregate.items():
                if not isinstance(agg_spec, dict):
                    continue
                op = (agg_spec.get('op') or '').lower()
                field = agg_spec.get('field', out_field)
                resolved_field = self._resolve_variable(field)
                real_field = resolved_field if (resolved_field and isinstance(resolved_field, str)) else field
                vals = [it.get(real_field) for it in items if real_field in it]
                if op in ('collect', 'list'):
                    out[out_field] = vals
                elif op == 'sum':
                    out[out_field] = sum(v for v in vals if isinstance(v, (int, float)))
                elif op in ('avg', 'mean'):
                    nums = [v for v in vals if isinstance(v, (int, float))]
                    out[out_field] = sum(nums) / len(nums) if nums else None
                elif op == 'min':
                    nums = [v for v in vals if isinstance(v, (int, float))]
                    out[out_field] = min(nums) if nums else None
                elif op == 'max':
                    nums = [v for v in vals if isinstance(v, (int, float))]
                    out[out_field] = max(nums) if nums else None
                elif op == 'count':
                    out[out_field] = len(vals)
                elif op == 'first':
                    out[out_field] = vals[0] if vals else None
                elif op == 'last':
                    out[out_field] = vals[-1] if vals else None
                elif op == 'concat':
                    out[out_field] = ''.join(str(v) for v in vals)
                elif op == 'count_distinct':
                    out[out_field] = len(set(v for v in vals if v is not None))
                else:
                    logger.warning(f"GROUP_BY unknown op '{op}', using collect")
                    out[out_field] = vals
            result.append(out)

        logger.info(f"GROUP_BY: {len(result)} groups from '{input_name}'")
        return result
