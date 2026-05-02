import json
import re
import time
from dataclasses import dataclass


@dataclass
class _BatchStepAdapter:
    method: object
    argument_mapping: dict
    auth_context_variable: str = "auth_id"


class ApiBatchRunner:
    """
    Executes API_BATCH scenario step configuration.
    """

    ENTITY_BY_NODE = {
        "rules": "rule",
        "paths": "path",
        "offers": "offer",
    }

    FIELD_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def __init__(self, scenario_runner, step):
        self.runner = scenario_runner
        self.step = step
        self.config = step.action_config or {}

    def _get_by_path(self, ctx, path):
        if not path:
            return None
        parts = [p for p in str(path).split(".") if p]
        cur = ctx
        for part in parts:
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]$", part)
            if m:
                key = m.group(1)
                idx = int(m.group(2))
                if isinstance(cur, dict):
                    cur = cur.get(key)
                else:
                    cur = getattr(cur, key, None)
                if not isinstance(cur, list) or idx >= len(cur):
                    return None
                cur = cur[idx]
                continue
            if isinstance(cur, dict):
                cur = cur.get(part)
            elif isinstance(cur, list) and part.isdigit():
                idx = int(part)
                cur = cur[idx] if idx < len(cur) else None
            else:
                cur = getattr(cur, part, None)
            if cur is None:
                return None
        return cur

    def _tokenize_path(self, path):
        raw = str(path or "").strip()
        raw = re.sub(r"^\[(\d+)\]", r"root[\1]", raw)
        parts = [p for p in raw.split(".") if p]
        out = []
        for part in parts:
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$", part)
            if not m:
                continue
            node = m.group(1)
            idx = m.group(2)
            out.append((node, int(idx) if idx is not None else None))
        return out

    def _derive_entity_and_indexes(self, op, graph_cfg):
        entity_alias = (graph_cfg or {}).get("entity_alias") or {}
        entity_nodes = (graph_cfg or {}).get("entity_nodes") or ["rules", "paths", "offers"]
        node_to_entity = {**self.ENTITY_BY_NODE, **entity_alias}
        tokens = self._tokenize_path(op.get("path"))

        field_filters = set((graph_cfg or {}).get("field_filters") or [])
        if field_filters and tokens:
            last_node, _ = tokens[-1]
            if self.FIELD_TOKEN_RE.match(last_node) and last_node in field_filters:
                tokens = tokens[:-1]

        indexes = {}
        leaf_entity = None
        for node, idx in tokens:
            if node in entity_nodes:
                alias = node_to_entity.get(node, node)
                leaf_entity = alias
                if idx is not None:
                    indexes[alias] = idx
        return leaf_entity, indexes

    def _resolve_template(self, template, local_context, *, strict=False):
        from .utils import _resolve_template

        hint = f"Scenario '{self.runner.scenario.name}' API_BATCH step {self.step.order}"
        return _resolve_template(
            template,
            local_context,
            raise_on_missing=strict,
            context_hint=hint,
        )

    def _resolve_index_to_id(self, op_ctx, index_to_id):
        resolved = {}
        for key, template in (index_to_id or {}).items():
            if not isinstance(template, str):
                resolved[key] = template
                continue
            val = self._resolve_template(template, op_ctx, strict=True)
            if isinstance(val, str):
                trimmed = val.strip()
                if trimmed.startswith("{") or trimmed.startswith("["):
                    try:
                        val = json.loads(trimmed)
                    except json.JSONDecodeError:
                        pass
            resolved[key] = val
        return resolved

    def _resolve_method_by_ref(self, route):
        method_id = route.get("method_id")
        method_ref = route.get("method_ref", "")
        if method_id:
            from .models import ServiceMethod

            return ServiceMethod.objects.get(pk=method_id)
        if isinstance(method_ref, str) and method_ref.startswith("method://"):
            method_name = method_ref.split("method://", 1)[1].split(".")[-1]
            from .models import ServiceMethod

            return ServiceMethod.objects.get(name=method_name)
        return None

    def _build_method_args(self, mapping, op_ctx):
        args = {}
        for arg_name, raw_value in (mapping or {}).items():
            if isinstance(raw_value, str) and "{{" in raw_value:
                val = self._resolve_template(raw_value, op_ctx, strict=True)
                if isinstance(val, str):
                    trimmed = val.strip()
                    if trimmed.startswith("{") or trimmed.startswith("["):
                        try:
                            val = json.loads(trimmed)
                        except json.JSONDecodeError:
                            pass
                args[arg_name] = val
            else:
                args[arg_name] = raw_value
        return args

    def execute(self):
        source_cfg = self.config.get("source") or {}
        source_path = source_cfg.get("value")
        ops = self._get_by_path(self.runner.context, source_path)
        if not isinstance(ops, list):
            raise ValueError(f"API_BATCH source must resolve to list: {source_path}")

        max_ops = int((self.config.get("execution") or {}).get("max_ops") or 500)
        dry_run = bool((self.config.get("execution") or {}).get("dry_run"))
        continue_on_error = bool((self.config.get("execution") or {}).get("continue_on_error", True))
        on_route_missing = ((self.config.get("error_policy") or {}).get("on_route_missing") or "skip").lower()
        on_mapping_error = ((self.config.get("error_policy") or {}).get("on_mapping_error") or "fail_op").lower()
        output_var = ((self.config.get("report") or {}).get("output_variable") or "batch_report")

        graph_cfg = self.config.get("path_graph") or {}
        routes = ((self.config.get("routing") or {}).get("methods") or [])
        route_map = {r.get("entity"): r for r in routes if r.get("entity")}
        index_to_id = self.config.get("index_to_id") or {}
        auth_var = (self.step.auth_context_variable or "auth_id")

        limited_ops = ops[:max_ops]
        report_ops = []
        succeeded = failed = skipped = 0
        started = time.time()

        for idx, op in enumerate(limited_ops):
            op_started = time.time()
            row = {
                "index": idx,
                "path": op.get("path"),
                "status": "skipped",
                "leaf_entity": None,
                "route_method": None,
                "resolved_ids": {},
                "error": None,
                "attempts": 0,
            }
            try:
                leaf_entity, indexes = self._derive_entity_and_indexes(op, graph_cfg)
                row["leaf_entity"] = leaf_entity
                op_ctx = {
                    **self.runner.context,
                    "context": self.runner.context,
                    "item": self.runner.context.get((graph_cfg.get("root") or "item")),
                    "op": {
                        **op,
                        "_leaf_entity": leaf_entity,
                        "_idx": indexes,
                    },
                }
                if leaf_entity is None or leaf_entity not in route_map:
                    if on_route_missing == "skip":
                        skipped += 1
                        row["status"] = "skipped"
                        row["error"] = "route_missing"
                        report_ops.append(row)
                        continue
                    raise ValueError(f"No route for entity '{leaf_entity}'")

                route = route_map[leaf_entity]
                method = self._resolve_method_by_ref(route)
                if method is None:
                    raise ValueError(f"Route method unresolved for entity '{leaf_entity}'")
                row["route_method"] = method.name

                resolved_ids = self._resolve_index_to_id(op_ctx, index_to_id)
                row["resolved_ids"] = resolved_ids
                op_ctx["op"].update(resolved_ids)

                method_args = self._build_method_args(route.get("argument_mapping") or {}, op_ctx)
                for required_arg in (method.arguments or []):
                    if required_arg not in method_args:
                        raise ValueError(f"Missing mapped arg '{required_arg}' for method '{method.name}'")

                if dry_run:
                    row["status"] = "success"
                    row["request"] = method_args
                    succeeded += 1
                    report_ops.append(row)
                    continue

                temp_step = _BatchStepAdapter(
                    method=method,
                    argument_mapping=method_args,
                    auth_context_variable=auth_var,
                )
                row["attempts"] = 1
                result = self.runner._execute_api_step(temp_step)
                row["status"] = "success"
                row["response"] = result
                row["request"] = method_args
                succeeded += 1
            except Exception as exc:
                row["status"] = "failed"
                row["error"] = str(exc)
                failed += 1
                if on_mapping_error == "fail_batch" or not continue_on_error:
                    row["duration_ms"] = int((time.time() - op_started) * 1000)
                    report_ops.append(row)
                    break
            row["duration_ms"] = int((time.time() - op_started) * 1000)
            report_ops.append(row)

        finished = time.time()
        report = {
            "summary": {
                "total": len(limited_ops),
                "executed": succeeded + failed,
                "succeeded": succeeded,
                "failed": failed,
                "skipped": skipped,
                "dry_run": dry_run,
            },
            "operations": report_ops,
            "timing": {
                "duration_ms": int((finished - started) * 1000),
            },
        }
        self.runner.context[output_var] = report
        self.runner.log(f"API_BATCH completed: {report['summary']}")
        return report
