"""
ScenarioRunner, WorkflowRunner, and utilities for executing scenarios/workflows.
"""
import json
import re
import requests
from datetime import datetime
from django.apps import apps
from .models import Scenario, ScenarioStep, Workflow, WorkflowStep, ServiceMethod
from .rate_limit import ApiRateLimiter

# Sentinel to distinguish "key missing" from "value is None"
_MISSING = object()


def _sanitize_request_for_logs(url, headers, auth_obj=None):
    """
    Mask URL/header sensitive data before storing in execution logs.
    """
    safe_url = url
    safe_headers = headers or {}
    try:
        from integrations.utils import _mask_sensitive, _mask_url_sensitive
        sensitive_values = []
        if auth_obj:
            creds = auth_obj.get_credentials() or {}
            if isinstance(creds, dict):
                sensitive_values.extend(creds.values())
        if isinstance(headers, dict):
            sensitive_values.extend(headers.values())
        safe_url = _mask_url_sensitive(url, sensitive_values)
        safe_headers = _mask_sensitive(headers if isinstance(headers, dict) else {})
    except Exception:
        pass
    return safe_url, safe_headers


def _resolve_tracker_for_variant(step, context):
    """
    Derive Tracker for BusinessActionVariant selection from context.
    Uses step.tracker_from_argument: the workflow argument name (e.g. source_auth_obj)
    that holds ApiAuthID. From ApiAuthID we get .tracker.
    Falls back to context['tracker_id'] for legacy.
    Returns Tracker instance or None.
    """
    arg_name = getattr(step, 'tracker_from_argument', None) or ''
    return _resolve_tracker_from_arg_name(arg_name, context)


def _resolve_tracker_from_arg_name(arg_name, context):
    """Resolve Tracker from context by arg name (ApiAuthID) or tracker_id. Returns Tracker or None."""
    from integrations.models import ApiAuthID, Tracker
    if arg_name:
        val = context.get(arg_name)
        if val is not None:
            if hasattr(val, 'tracker'):
                return val.tracker
            try:
                pk = int(val) if isinstance(val, (int, str)) and str(val).strip().isdigit() else None
                if pk is not None:
                    auth = ApiAuthID.objects.get(pk=pk)
                    return auth.tracker
            except (ApiAuthID.DoesNotExist, ValueError, TypeError):
                pass
    tracker_id = context.get('tracker_id')
    if tracker_id:
        try:
            return Tracker.objects.get(pk=int(tracker_id))
        except (Tracker.DoesNotExist, ValueError, TypeError):
            pass
    return None


def _resolve_path_part(val, part):
    """
    Resolve one path segment (e.g. 'geos', 'geos[0]', '0') against val.
    Supports key[index] for dict key followed by list index.
    Returns _MISSING when key/index does not exist, None when value is null.
    """
    if val is None or val is _MISSING:
        return _MISSING
    m = re.match(r'^(\w+)\[(\d+)\]$', str(part))
    if m:
        key, idx = m.group(1), int(m.group(2))
        if isinstance(val, dict):
            val = val.get(key, _MISSING)
        elif isinstance(val, list):
            try:
                val = val[int(key)]
            except (ValueError, IndexError):
                return _MISSING
        elif hasattr(val, key):
            val = getattr(val, key)
        else:
            return _MISSING
        if val is _MISSING:
            return _MISSING
        if isinstance(val, list):
            try:
                return val[idx]
            except IndexError:
                return _MISSING
        return val
    if isinstance(val, dict):
        return val.get(part, _MISSING)
    if isinstance(val, list):
        try:
            return val[int(part)]
        except (ValueError, IndexError):
            return _MISSING
    if val is not None and hasattr(val, part):
        return getattr(val, part)
    return _MISSING


def _resolve_path(obj, path):
    """
    Resolve a dotted path within obj. Supports bracket notation for array indices
    (e.g. 'data.geos[0].code'). Returns _MISSING when path not found.
    """
    if not path or not isinstance(path, str):
        return _MISSING
    parts = path.split('.')
    val = obj
    for part in parts:
        val = _resolve_path_part(val, part)
        if val is _MISSING:
            return _MISSING
    return val


def _set_path(obj, path, value):
    """
    Set value at path, creating intermediate dicts as needed.
    Supports simple dotted paths (e.g. 'data.excluded_sources').
    """
    if not path or not isinstance(path, str):
        return
    parts = path.split('.')
    current = obj
    for part in parts[:-1]:
        if part not in current or not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _contract_type_hint(spec):
    if not isinstance(spec, dict):
        return "untyped"
    t = str(spec.get("type") or "").strip().lower()
    if not t:
        return "untyped"
    if t == "array":
        it = str(spec.get("items_type") or "").strip().lower()
        return f"array<{it}>" if it else "array"
    return t


def _coerce_scalar(value, target_type):
    t = (target_type or "").strip().lower()
    if not t:
        return value, False

    if t == "string":
        if isinstance(value, str):
            return value, False
        return str(value), True

    if t == "integer":
        if isinstance(value, bool):
            raise ValueError("boolean cannot be coerced to integer")
        if isinstance(value, int):
            return value, False
        if isinstance(value, float):
            if value.is_integer():
                return int(value), True
            raise ValueError("non-integer number cannot be coerced to integer")
        if isinstance(value, str):
            s = value.strip()
            if re.fullmatch(r"[-+]?\d+", s):
                return int(s), True
            raise ValueError("string is not a valid integer")
        raise ValueError(f"type '{type(value).__name__}' cannot be coerced to integer")

    if t == "number":
        if isinstance(value, bool):
            raise ValueError("boolean cannot be coerced to number")
        if isinstance(value, (int, float)):
            return value, False
        if isinstance(value, str):
            s = value.strip()
            try:
                return float(s), True
            except ValueError:
                raise ValueError("string is not a valid number")
        raise ValueError(f"type '{type(value).__name__}' cannot be coerced to number")

    if t == "boolean":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "y", "on"):
                return True, True
            if s in ("false", "0", "no", "n", "off"):
                return False, True
            raise ValueError("string is not a valid boolean")
        raise ValueError(f"type '{type(value).__name__}' cannot be coerced to boolean")

    if t == "object":
        if isinstance(value, dict):
            return value, False
        if isinstance(value, str):
            s = value.strip()
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                raise ValueError("string is not valid JSON object")
            if isinstance(parsed, dict):
                return parsed, True
            raise ValueError("JSON value is not an object")
        raise ValueError(f"type '{type(value).__name__}' cannot be coerced to object")

    # Unknown type: keep as-is for forward compatibility.
    return value, False


def _coerce_contract_value(value, spec):
    if not isinstance(spec, dict):
        return value, False
    nullable = spec.get("nullable", True)
    if value is None:
        if nullable:
            return None, False
        raise ValueError("null is not allowed")

    t = str(spec.get("type") or "").strip().lower()
    if not t:
        return value, False

    if t == "array":
        items_type = str(spec.get("items_type") or "").strip().lower()
        changed = False
        arr = value
        if isinstance(arr, str):
            s = arr.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    arr = json.loads(s)
                    changed = True
                except json.JSONDecodeError:
                    pass
        if not isinstance(arr, list):
            arr = [arr]
            changed = True

        if items_type:
            coerced_items = []
            for item in arr:
                coerced_item, item_changed = _coerce_scalar(item, items_type)
                coerced_items.append(coerced_item)
                changed = changed or item_changed
            arr = coerced_items
        return arr, changed

    return _coerce_scalar(value, t)


def _apply_payload_value_types(method, method_args, log_func=None):
    specs = getattr(method, "payload_value_types", None) or {}
    if not isinstance(specs, dict):
        return method_args

    for arg_name, value in list(method_args.items()):
        spec = specs.get(arg_name)
        if not isinstance(spec, dict):
            continue
        before_type = type(value).__name__
        try:
            coerced_value, changed = _coerce_contract_value(value, spec)
        except ValueError as exc:
            expected = _contract_type_hint(spec)
            raise ValueError(
                f"Type coercion failed for '{arg_name}': expected {expected}, got {before_type}. {exc}"
            )
        method_args[arg_name] = coerced_value
        if changed and log_func:
            expected = _contract_type_hint(spec)
            after_type = type(coerced_value).__name__
            log_func(f"Coerced '{arg_name}' to {expected} ({before_type} -> {after_type})")
    return method_args


from .actions import ActionRunner


def format_value_with_config(value, config):
    """Format a value according to config (e.g. for return_key)."""
    if not config:
        return value
    if isinstance(config, dict) and 'date_format' in config:
        # Simplified - could use strftime
        return value
    return value


def _describe_output_value(value):
    """Compact output-value description for logs (without dumping payload)."""
    value_type = type(value).__name__
    if isinstance(value, (list, tuple, dict, set, str, bytes)):
        return f"type={value_type}, size={len(value)}"
    return f"type={value_type}"


def _format_output_value_preview(value):
    """Serialize full output value for logs (no truncation)."""
    try:
        text = json.dumps(value, ensure_ascii=True, default=str)
    except Exception:
        text = str(value)
    return text


def _log_output_variable(log_func, var_name, value):
    """Emit output-variable logs in runtime order."""
    log_func(f"Output variable set: {var_name} ({_describe_output_value(value)})")
    log_func(f"Output variable value: {var_name} = {_format_output_value_preview(value)}")


def _resolve_template(template, context, *, raise_on_missing=False, context_hint=''):
    """
    Resolve {{ var }} or {{ var.sub }} or {{ var.sub[0].key }} from context.
    Supports bracket notation for list indices (e.g. geos[0], devices[0].id).
    If template is exactly {{ var }} and value is dict/list, pass as-is (no str conversion).
    Otherwise replace and return string (for json.loads if needed).
    When raise_on_missing=True and variable not found, raises ValueError with context_hint.
    """
    def _get_val(var_name):
        if '.' in var_name:
            parts = var_name.split('.')
            val = context.get(parts[0], _MISSING)
            for part in parts[1:]:
                val = _resolve_path_part(val, part)
                if val is _MISSING:
                    break
        else:
            val = context.get(var_name, _MISSING)
        return val

    def _resolve_var(var_name, do_raise):
        val = _get_val(var_name)
        if val is _MISSING and do_raise:
            raise ValueError(
                f"Variable '{var_name}' not found in context."
                + (f" {context_hint}" if context_hint else "")
            )
        return val if val is not _MISSING else None

    if not isinstance(template, str) or '{{' not in template:
        return template
    # Single variable: {{ var }} or {{ var.sub }}
    match = re.fullmatch(r'\s*\{\{\s*([^}]+?)\s*\}\}\s*', template.strip())
    if match:
        var_name = match.group(1).strip()
        val = _resolve_var(var_name, raise_on_missing)
        if val is not None and isinstance(val, (dict, list)):
            return val  # Pass as-is, no str()
        return val if val is not None else ''
    # Multiple {{ }} or interpolation
    def replace(m):
        var_name = m.group(1).strip()
        val = _resolve_var(var_name, raise_on_missing)
        if val is not None and isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val) if val is not None else ''
    return re.sub(r'\{\{\s*(.+?)\s*\}\}', replace, template)


def _apply_output_mapping(result, output_mapping, context_hint=''):
    """
    Apply output_mapping: resolve templates against scenario result context,
    return dict of {output_name: resolved_value}.
    output_mapping format: {"ActionOutput": "{{ ScenarioReturn }}"}
    """
    if not output_mapping:
        return {}
    # Resolve against scenario's context (result is from ScenarioRunner.run())
    scenario_ctx = result.get('context', result) if isinstance(result, dict) else {}
    if isinstance(result, dict) and 'context' not in result:
        scenario_ctx = result  # fallback: use result itself
    mapped = {}
    for output_name, template in output_mapping.items():
        if isinstance(template, str) and '{{' in template:
            hint = f"{context_hint} output_mapping '{output_name}': {template}" if context_hint else f"output_mapping '{output_name}': {template}"
            val = _resolve_template(template, scenario_ctx, raise_on_missing=True, context_hint=hint)
            mapped[output_name] = val
        else:
            mapped[output_name] = template
    return mapped


class ScenarioRunner:
    """Executes a Scenario (sequence of API calls and actions)."""

    _SENTINEL = object()

    def __init__(self, scenario_id, initial_context):
        self.scenario = Scenario.objects.get(pk=scenario_id)
        self.context = dict(initial_context) if initial_context else {}
        self.logs = []
        self.external_requests = []
        self.rate_limiter = ApiRateLimiter(log_func=self.log)

    def log(self, msg):
        self.logs.append(msg)

    def _get_context_value(self, var_name):
        if '.' in var_name:
            parts = var_name.split('.')
            val = self.context.get(parts[0], _MISSING)
            for part in parts[1:]:
                val = _resolve_path_part(val, part)
                if val is _MISSING:
                    return self._SENTINEL
            return val
        return self.context.get(var_name, self._SENTINEL)

    def _set_json_value(self, d, path, value):
        parts = path.split('.')
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value

    @staticmethod
    def _extract_json_path(data, path):
        """Extract a value from nested dict/list using dot-notation path (e.g. 'meta.total', 'paging.cursors.after')."""
        if not path or not isinstance(data, dict):
            return None
        val = data
        for part in path.split('.'):
            if isinstance(val, dict):
                val = val.get(part)
            elif isinstance(val, list) and part.isdigit():
                idx = int(part)
                val = val[idx] if idx < len(val) else None
            else:
                return None
            if val is None:
                return None
        return val

    @staticmethod
    def _get_pagination_safety_limit():
        from integrations.models import SystemConfig
        try:
            cfg = SystemConfig.objects.filter(key='pagination_safety_limit').first()
            if cfg and isinstance(cfg.value, int):
                return cfg.value
            if cfg and isinstance(cfg.value, dict):
                return cfg.value.get('value', 200)
        except Exception:
            pass
        return 200

    def _resolve_model_args(self):
        """
        Resolve model-type arguments from primitives (pk) to actual model instances.
        Uses scenario.arguments with type='model', model='app.modelname', lookup='field'.
        """
        for arg in self.scenario.arguments or []:
            if not isinstance(arg, dict) or arg.get('type') != 'model':
                continue
            var_name = arg.get('name')
            model_path = arg.get('model')
            lookup = arg.get('lookup') or 'pk'
            if not var_name or not model_path:
                continue
            val = self.context.get(var_name)
            if val is None:
                continue
            # Already a model instance (has _meta)
            if hasattr(val, '_meta'):
                continue
            try:
                parts = model_path.split('.')
                if len(parts) != 2:
                    continue
                app_label, model_name = parts[0], parts[1].lower()
                Model = apps.get_model(app_label, model_name)
            except (LookupError, ValueError):
                self.log(f"Warning: Cannot resolve model '{model_path}' for '{var_name}'")
                continue
            try:
                if isinstance(val, int) or (isinstance(val, str) and str(val).strip().isdigit()):
                    obj = Model.objects.get(pk=int(val))
                elif lookup:
                    obj = Model.objects.get(**{lookup: val})
                else:
                    continue
                self.context[var_name] = obj
                self.log(f"Resolved {var_name} to {Model.__name__} instance (pk={obj.pk})")
            except Model.DoesNotExist:
                self.log(f"Error: {model_path} with {lookup}='{val}' not found.")
            except Exception as e:
                self.log(f"Warning: Failed to resolve {var_name}: {e}")

    def _resolve_auth_variables(self):
        """
        Resolve auth context variables (auth_id, source_auth, etc.) to ApiAuthID objects.
        Auth variables in context must always be objects, never pk.
        """
        import integrations.models
        ApiAuthID = integrations.models.ApiAuthID
        steps = self.scenario.steps.filter(is_active=True).order_by('order')
        auth_vars = set()
        for step in steps:
            auth_var = getattr(step, 'auth_context_variable', None) or 'auth_id'
            auth_vars.add(auth_var)
        # Also resolve auth_id if view injected it
        if self.context.get('auth_id') is not None:
            auth_vars.add('auth_id')
        for var_name in auth_vars:
            val = self.context.get(var_name)
            if val is None:
                continue
            if hasattr(val, '_meta'):
                continue
            try:
                pk = int(val) if isinstance(val, (int, str)) and str(val).strip().isdigit() else None
                if pk is not None:
                    obj = ApiAuthID.objects.get(pk=pk)
                    self.context[var_name] = obj
                    self.log(f"Resolved {var_name} to ApiAuthID instance (pk={obj.pk})")
            except ApiAuthID.DoesNotExist:
                self.log(f"Error: ApiAuthID with pk={val} not found.")
            except (ValueError, TypeError):
                pass

    def _step_err_prefix(self, step):
        """Returns scenario/step context for error messages."""
        name = getattr(self.scenario, 'name', '?')
        order = getattr(step, 'order', '?')
        if step.step_type == 'API_CALL':
            step_name = getattr(step.method, 'name', 'API') if step.method else 'API_CALL'
        else:
            step_name = getattr(step, 'action_type', None) or 'ACTION'
        return f"Scenario '{name}' Step {order} ({step_name}): "

    def _apply_response_injection(self, step, result):
        """
        Apply response_modification: inject context values INTO the response.
        Format: {"json_path": "context_var"} e.g. {"data.statistics[].cmp_id": "item.id"}
        Supports path[].field to add field to each element in array.
        """
        modifications = getattr(step, 'response_modification', None) or {}
        if not modifications:
            return
        for json_path, context_var in modifications.items():
            if not json_path or not context_var:
                continue
            val = self._get_context_value(str(context_var).strip())
            if val is self._SENTINEL:
                prefix = self._step_err_prefix(step)
                raise ValueError(f"{prefix}Response injection '{json_path}': variable '{context_var}' not found in context.")
            # Support path[].field - add field to each element in array
            if '[].' in json_path:
                array_path, field_name = json_path.split('[].', 1)
                if array_path:
                    parts = array_path.split('.')
                    obj = result if isinstance(result, dict) else None
                    for part in parts:
                        if obj is None or not isinstance(obj, dict):
                            break
                        obj = obj.get(part)
                else:
                    obj = result if isinstance(result, list) else None
                if isinstance(obj, list):
                    for elem in obj:
                        if isinstance(elem, dict):
                            elem[field_name] = val
                    self.log(f"Response injection: added {field_name}={val} to {len(obj)} elements in {array_path or 'root'}")
            elif isinstance(result, dict):
                self._set_json_value(result, json_path, val)
                self.log(f"Response injection: set {json_path} = {val}")

    def _apply_context_extraction(self, step, result):
        """Apply context_extraction: evaluate expressions with result/context, store in context."""
        extraction = getattr(step, 'context_extraction', None) or {}
        if not extraction:
            return
        from .safe_eval import SafeEvaluator
        eval_context = {**self.context, 'result': result, 'context': self.context}
        if step.output_variable_name:
            eval_context[step.output_variable_name] = result
        evaluator = SafeEvaluator(context=eval_context)
        for var_name, expression in extraction.items():
            if not expression or not str(expression).strip():
                continue
            try:
                val = evaluator.evaluate(str(expression))
                self.context[var_name] = val
                self.log(f"Context extraction: {var_name} = {val}")
            except Exception as e:
                prefix = self._step_err_prefix(step)
                raise ValueError(f"{prefix}context_extraction '{var_name}': {e}") from e

    def _check_success_condition(self, step, result):
        """Evaluate success_condition; if False, raise with condition_error_message."""
        condition = getattr(step, 'success_condition', None) or ''
        if not condition or not str(condition).strip():
            return
        from .safe_eval import SafeEvaluator
        eval_context = {**self.context, 'result': result, 'context': self.context}
        if step.output_variable_name:
            eval_context[step.output_variable_name] = result
        evaluator = SafeEvaluator(context=eval_context)
        try:
            passed = evaluator.evaluate(str(condition))
        except Exception as e:
            prefix = self._step_err_prefix(step)
            raise ValueError(f"{prefix}success_condition evaluation failed: {e}") from e
        if not passed:
            msg = getattr(step, 'condition_error_message', None) or f"Success condition failed: {condition}"
            prefix = self._step_err_prefix(step)
            raise ValueError(f"{prefix}{msg}")

    def run(self):
        self.log(f"Starting scenario: {self.scenario.name}")
        self._resolve_model_args()
        self._resolve_auth_variables()
        self.log(f"Initial Context: {self.context}")

        steps = self.scenario.steps.filter(is_active=True).order_by('order')
        for step in steps:
            try:
                # Resolve iterator: if step has iterator_variable, run for each item
                items_to_run = None
                if getattr(step, 'iterator_variable', None):
                    raw_items = self.context.get(step.iterator_variable)
                    if isinstance(raw_items, (list, tuple)):
                        items_to_run = list(raw_items)
                    else:
                        self.log(f"Warning: iterator_variable '{step.iterator_variable}' is not a list (got {type(raw_items).__name__}), skipping step")
                        items_to_run = []
                if items_to_run is None:
                    items_to_run = [None]  # single run

                results = []
                for idx, item in enumerate(items_to_run):
                    if item is not None:
                        self.log(f"  Iteration {idx + 1}/{len(items_to_run)} (item from {step.iterator_variable})")
                    # Add item to context for this iteration (for {{ item.campaignId }} etc.)
                    if item is not None:
                        self.context['item'] = item
                    elif 'item' in self.context:
                        self.context.pop('item', None)

                    if step.step_type == 'API_CALL':
                        result = self._execute_api_step(step)
                    elif step.step_type == 'API_BATCH':
                        from .api_batch import ApiBatchRunner
                        batch_runner = ApiBatchRunner(self, step)
                        result = batch_runner.execute()
                    else:
                        action_runner = ActionRunner(self.context, log_func=self.log)
                        result = action_runner.run(step)

                    self._apply_response_injection(step, result)
                    self._apply_context_extraction(step, result)
                    self._check_success_condition(step, result)

                    if getattr(self, '_result_from_error_handler', False):
                        self._result_from_error_handler = False
                    else:
                        if isinstance(result, list):
                            results.extend(result)
                        else:
                            results.append(result)

                if step.output_variable_name and results:
                    self.context[step.output_variable_name] = results
                    _log_output_variable(self.log, step.output_variable_name, results)
            except Exception as e:
                prefix = self._step_err_prefix(step)
                msg = f"{prefix}{e}"
                try:
                    raise type(e)(msg) from e
                except TypeError:
                    raise RuntimeError(msg) from e

        return {
            'success': True,
            'context': self.context,
            'context_variables': self.context,
            'logs': self.logs,
            'external_requests': self.external_requests,
            'api_calls': self.external_requests,
        }

    def _execute_api_step(self, step):
        import integrations.models
        method = step.method
        if not method:
            raise Exception("Step type is API_CALL but no method is defined.")

        auth_var = getattr(step, 'auth_context_variable', None) or 'auth_id'
        auth_obj = self.context.get(auth_var)

        self.log(f"Running Method: {method.name}")

        mapping = step.argument_mapping or {}
        expected_method_args = set(method.arguments or [])
        extra_mapping_keys = sorted(set(mapping.keys()) - expected_method_args)
        if extra_mapping_keys:
            self.log(
                f"Warning: ignored stale argument_mapping keys for method '{method.name}': {', '.join(extra_mapping_keys)}"
            )
        method_args = {}
        for arg_name in method.arguments:
            if arg_name in mapping:
                raw_value = mapping[arg_name]
                if isinstance(raw_value, str) and ('{{' in raw_value or '{' in raw_value):
                    exact_match = re.fullmatch(r'\{\{\s*([^}]+?)\s*\}\}', raw_value.strip())
                    if exact_match:
                        var_name = exact_match.group(1).strip()
                        val = self._get_context_value(var_name)
                        if val is not self._SENTINEL:
                            method_args[arg_name] = val
                        else:
                            prefix = self._step_err_prefix(step)
                            raise ValueError(f"{prefix}Variable '{var_name}' not found in context.")
                    elif '{{' in raw_value:
                        def replace_match(match):
                            var_name = match.group(1).strip()
                            val = self._get_context_value(var_name)
                            if val is self._SENTINEL:
                                prefix = self._step_err_prefix(step)
                                raise ValueError(f"{prefix}Variable '{var_name}' not found in context.")
                            return str(val)
                        resolved_value = re.sub(r'\{\{\s*(.+?)\s*\}\}', replace_match, raw_value)
                        if (resolved_value.strip().startswith('{') and resolved_value.strip().endswith('}')) or \
                           (resolved_value.strip().startswith('[') and resolved_value.strip().endswith(']')):
                            try:
                                method_args[arg_name] = json.loads(resolved_value)
                            except json.JSONDecodeError:
                                method_args[arg_name] = resolved_value
                        else:
                            method_args[arg_name] = resolved_value
                    else:
                        method_args[arg_name] = raw_value
                elif isinstance(raw_value, str) and raw_value in self.context:
                    method_args[arg_name] = self.context[raw_value]
                else:
                    try:
                        method_args[arg_name] = json.loads(raw_value)
                    except (json.JSONDecodeError, TypeError):
                        method_args[arg_name] = raw_value
            else:
                if arg_name == 'payload':
                    has_body_args = any(k.startswith('body.') for k in mapping.keys())
                    if has_body_args:
                        continue
                if arg_name.startswith('body.'):
                    continue
                raise Exception(f"Argument '{arg_name}' is not mapped")

        method_args = _apply_payload_value_types(method, method_args, log_func=self.log)

        endpoint = method.service_endpoint
        # Apply date formatting for params with date roles (e.g. Binom Y-m-d H:i:s)
        tracker = endpoint.tracker
        ep_config = endpoint.api_configuration or {}
        tr_config = getattr(tracker, 'api_configuration', None) or {}
        param_roles = ep_config.get('param_roles', {})
        date_formats = tr_config.get('date_formats', {
            'date_start': '%Y-%m-%d 00:00:00',
            'date_end': '%Y-%m-%d 23:59:59',
        })
        for arg_name in list(method_args.keys()):
            role = param_roles.get(arg_name)
            if role in date_formats:
                val = method_args[arg_name]
                if isinstance(val, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', val.strip()):
                    try:
                        dt = datetime.strptime(val.strip(), '%Y-%m-%d')
                        method_args[arg_name] = dt.strftime(date_formats[role])
                    except (ValueError, TypeError):
                        pass

        url = endpoint.endpoint

        for arg, val in method_args.items():
            if arg == 'payload':
                continue
            if f"{{{arg}}}" in url:
                url = url.replace(f"{{{arg}}}", str(val))
            elif f"%{arg}%" in url:
                url = url.replace(f"%{arg}%", str(val))

        if not url.startswith('http'):
            if not auth_obj:
                raise Exception(
                    f"Invalid URL '{url}': No scheme supplied. "
                    f"Relative URLs require auth. Step '{method.name}' uses auth_context_variable='{auth_var}'"
                    f" but this variable is not in context. Ensure it is propagated via input_mapping "
                    f"(workflow → business action → scenario → step)."
                )
            base_url = (auth_obj.request_url or '').strip().rstrip('/')
            if not base_url or not base_url.startswith('http'):
                raise Exception(
                    f"ApiAuthID '{auth_obj.account_name}' (pk={auth_obj.pk}) has empty or invalid request_url. "
                    f"Please set the base URL (e.g. https://api.example.com) in the Auth ID configuration."
                )
            url = f"{base_url}/{url.lstrip('/')}"
            self.log(f"Prepended base URL from Auth ID: {base_url}")

        payload_data = None
        if 'payload' in method_args:
            payload_data = method_args['payload']
            if isinstance(payload_data, str):
                try:
                    payload_data = json.loads(payload_data)
                except json.JSONDecodeError:
                    pass
        body_args = {k: v for k, v in method_args.items() if k.startswith('body.')}
        if body_args:
            if payload_data is None:
                payload_data = {}
            elif not isinstance(payload_data, dict):
                body_args = {}
            for key, value in body_args.items():
                path = key[5:]
                if path:
                    self._set_json_value(payload_data, path, value)

        headers = {}
        if auth_obj:
            try:
                from integrations.utils import apply_auth_to_request
                url, headers = apply_auth_to_request(auth_obj, url, headers=headers, log_func=self.log)
                self.log(f"Injected Auth Headers for type: {auth_obj.auth_type.name}")
            except Exception as e:
                self.log(f"Error injecting auth headers: {e}")

        req_kwargs = {'method': endpoint.method, 'url': url, 'headers': headers}
        if payload_data is not None:
            req_kwargs['json'] = payload_data

        pagination = ep_config.get('pagination')
        if pagination and isinstance(pagination, dict) and pagination.get('strategy'):
            return self._do_paginated_request(req_kwargs, method, pagination, step, auth_obj=auth_obj)

        return self._do_single_request(req_kwargs, method, step, auth_obj=auth_obj)

    def _apply_error_handlers(self, response, result, step):
        """
        If step has error_handlers and response is not ok, check handlers.
        Returns (value_to_return, handled). If handled is True, caller should return value_to_return instead of raising.
        """
        if response.ok:
            return (None, False)
        handlers = getattr(step, 'error_handlers', None) or []
        if not handlers:
            return (None, False)
        status_code = response.status_code
        for h in handlers:
            codes = h.get('status_codes') or []
            if not isinstance(codes, list):
                codes = [codes]
            if status_code not in codes:
                continue
            body_match = h.get('body_match')
            if body_match and isinstance(body_match, dict):
                if not isinstance(result, dict):
                    continue
                match_ok = True
                for path, expected in body_match.items():
                    val = self._extract_json_path(result, path)
                    if val != expected:
                        match_ok = False
                        break
                if not match_ok:
                    continue
            action = h.get('action') or 'return_body'
            if action == 'skip':
                self._result_from_error_handler = True
                self.log(f"Error handler matched (status={status_code}): skip (no output for this iteration)")
                return ({}, True)
            if action == 'return_body':
                self.log(f"Error handler matched (status={status_code}): returning response body")
                return (result, True)
            if action == 'return_value':
                value = h.get('value')
                if value is not None:
                    value = self._resolve_error_handler_value(value)
                self.log(f"Error handler matched (status={status_code}): returning configured value")
                return (value, True)
        return (None, False)

    def _resolve_error_handler_value(self, obj):
        """Recursively resolve {{ context.path }} placeholders in value (dict/list/str)."""
        if isinstance(obj, str):
            if '{{' not in obj:
                return obj
            exact = re.fullmatch(r'\s*\{\{\s*([^}]+?)\s*\}\}\s*', obj.strip())
            if exact:
                var_name = exact.group(1).strip()
                val = self._get_context_value(var_name)
                if val is not self._SENTINEL:
                    return val
                return obj
            def replace(m):
                var_name = m.group(1).strip()
                val = self._get_context_value(var_name)
                if val is self._SENTINEL:
                    return m.group(0)
                return str(val)
            return re.sub(r'\{\{\s*([^}]+?)\s*\}\}', replace, obj)
        if isinstance(obj, dict):
            return {k: self._resolve_error_handler_value(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_error_handler_value(x) for x in obj]
        return obj

    def _do_single_request(self, req_kwargs, method, step=None, auth_obj=None):
        """Execute a single HTTP request, record it, and apply return_key extraction."""
        safe_url, safe_headers = _sanitize_request_for_logs(
            req_kwargs.get('url'),
            req_kwargs.get('headers', {}),
            auth_obj=auth_obj,
        )
        ext_req = {
            'step': method.name,
            'step_name': method.name,
            'url': safe_url,
            'method': req_kwargs['method'],
            'request_body': req_kwargs.get('json'),
            'request_payload': req_kwargs.get('json'),
            'request_headers': safe_headers,
            'response_status': 'pending',
        }
        self.external_requests.append(ext_req)

        self.rate_limiter.acquire(req_kwargs.get('url', ''), auth_obj=auth_obj)
        response = requests.request(**req_kwargs)

        ext_req['response_status'] = response.status_code
        ext_req['response_headers'] = dict(response.headers)
        try:
            ext_req['response_body'] = response.json()
        except Exception:
            ext_req['response_body'] = response.text[:2000] if response.text else ''

        self.log(f"Response Status: {response.status_code}")
        try:
            result = response.json()
        except Exception:
            result = response.text

        if not response.ok:
            if step:
                handler_value, handled = self._apply_error_handlers(response, result, step)
                if handled:
                    return handler_value
            self.log(f"Response Body: {response.text[:500]}...")
            raise Exception(f"HTTP {response.status_code}: {response.text}")

        self.log(f"Method executed successfully. Result: {result}")

        if method.return_key and isinstance(result, dict):
            parts = method.return_key.split('.')
            val = result
            for p in parts:
                val = val.get(p) if isinstance(val, dict) else None
            if val is not None:
                result = val
                size = len(val) if isinstance(val, (list, dict)) else None
                self.log(f"Extracted return_key '{method.return_key}': {type(val).__name__}" + (f" ({size} items)" if size is not None else ""))

        return result

    def _do_paginated_request(self, req_kwargs, method, pagination, step=None, auth_obj=None):
        """
        Execute multiple HTTP requests following the endpoint's pagination strategy,
        accumulating results into a single list.

        Supported strategies: offset, page, cursor, link_header.
        Stop conditions (checked in order):
          1. Empty page (0 items)
          2. has_more_path present and falsy
          3. Page size < effective_page_size (from first response)
          4. Safety limit reached
        """
        from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

        strategy = pagination['strategy']
        data_path = pagination.get('data_path')
        has_more_path = pagination.get('has_more_path')
        safety_limit = self._get_pagination_safety_limit()

        all_items = []
        effective_page_size = None
        page_num = 0

        self.log(f"Auto-pagination enabled (strategy: {strategy})")

        while True:
            if page_num >= safety_limit:
                self.log(f"Pagination safety limit reached ({safety_limit} pages). Stopping.")
                break

            safe_url, safe_headers = _sanitize_request_for_logs(
                req_kwargs.get('url'),
                req_kwargs.get('headers', {}),
                auth_obj=auth_obj,
            )
            ext_req = {
                'step': method.name,
                'step_name': f"{method.name} [page {page_num + 1}]",
                'url': safe_url,
                'method': req_kwargs['method'],
                'request_body': req_kwargs.get('json'),
                'request_payload': req_kwargs.get('json'),
                'request_headers': safe_headers,
                'response_status': 'pending',
            }
            self.external_requests.append(ext_req)

            self.rate_limiter.acquire(req_kwargs.get('url', ''), auth_obj=auth_obj)
            response = requests.request(**req_kwargs)

            ext_req['response_status'] = response.status_code
            ext_req['response_headers'] = dict(response.headers)
            try:
                ext_req['response_body'] = response.json()
            except Exception:
                ext_req['response_body'] = response.text[:2000] if response.text else ''

            if not response.ok:
                try:
                    raw_result = response.json()
                except Exception:
                    raw_result = response.text
                if step:
                    handler_value, handled = self._apply_error_handlers(response, raw_result, step)
                    if handled:
                        return handler_value
                self.log(f"Pagination page {page_num + 1}: HTTP {response.status_code}")
                raise Exception(f"HTTP {response.status_code}: {response.text}")

            try:
                raw_result = response.json()
            except Exception:
                self.log(f"Pagination page {page_num + 1}: non-JSON response, stopping.")
                break

            page_data = self._extract_json_path(raw_result, data_path) if data_path else raw_result
            if not isinstance(page_data, list):
                if page_num == 0:
                    self.log(f"Pagination: data_path '{data_path}' did not resolve to a list on first page. Returning raw result.")
                    return page_data
                break

            page_len = len(page_data)
            all_items.extend(page_data)
            self.log(f"  Page {page_num + 1}: {page_len} items (total collected: {len(all_items)})")

            if page_len == 0:
                break

            if effective_page_size is None:
                effective_page_size = page_len

            # --- Stop condition: has_more_path ---
            if has_more_path:
                has_more = self._extract_json_path(raw_result, has_more_path)
                if not has_more:
                    self.log(f"  has_more_path '{has_more_path}' is falsy. Stopping.")
                    break

            # --- Stop condition: page smaller than effective_page_size ---
            if page_len < effective_page_size:
                self.log(f"  Page size {page_len} < effective page size {effective_page_size}. Last page reached.")
                break

            # --- Advance pagination parameters for next request ---
            page_num += 1

            if strategy == 'offset':
                offset_param = pagination.get('offset_param', 'offset')
                limit_param = pagination.get('limit_param', 'limit')
                default_limit = pagination.get('default_limit', effective_page_size)
                new_offset = page_num * effective_page_size
                req_kwargs = self._update_request_param(req_kwargs, offset_param, new_offset)
                req_kwargs = self._update_request_param(req_kwargs, limit_param, default_limit)

            elif strategy == 'page':
                page_param = pagination.get('page_param', 'page')
                start_page = pagination.get('start_page', 1)
                req_kwargs = self._update_request_param(req_kwargs, page_param, start_page + page_num)

            elif strategy == 'cursor':
                cursor_param = pagination.get('cursor_param', 'cursor')
                cursor_response_path = pagination.get('cursor_response_path')
                next_cursor = self._extract_json_path(raw_result, cursor_response_path) if cursor_response_path else None
                if not next_cursor:
                    self.log(f"  No next cursor at '{cursor_response_path}'. Stopping.")
                    break
                req_kwargs = self._update_request_param(req_kwargs, cursor_param, next_cursor)

            elif strategy == 'link_header':
                link_header = response.headers.get('Link', '')
                next_url = self._parse_link_header_next(link_header)
                if not next_url:
                    self.log(f"  No 'next' link in Link header. Stopping.")
                    break
                req_kwargs['url'] = next_url

        self.log(f"Pagination complete: {page_num + 1} pages, {len(all_items)} total items.")
        self.log(f"Method executed successfully. Result: {all_items}")
        return all_items

    @staticmethod
    def _update_request_param(req_kwargs, param_name, value):
        """Update or add a query parameter in the request URL."""
        from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
        parsed = urlparse(req_kwargs['url'])
        params = parse_qs(parsed.query, keep_blank_values=True)
        params[param_name] = [str(value)]
        new_query = urlencode(params, doseq=True)
        req_kwargs['url'] = urlunparse(parsed._replace(query=new_query))
        return req_kwargs

    @staticmethod
    def _parse_link_header_next(link_header):
        """Extract the URL with rel='next' from an HTTP Link header."""
        if not link_header:
            return None
        import re as _re
        for part in link_header.split(','):
            match = _re.match(r'\s*<([^>]+)>\s*;\s*rel="next"', part.strip())
            if match:
                return match.group(1)
        return None


class WorkflowRunner:
    """Executes a Workflow (orchestrates Scenarios)."""

    def __init__(self, workflow_id, initial_context):
        self.workflow = Workflow.objects.get(pk=workflow_id)
        self.context = dict(initial_context) if initial_context else {}
        self.logs = []
        self.external_requests = []

    def log(self, msg):
        self.logs.append(msg)

    def _resolve_model_args(self):
        """Resolve model-type arguments from workflow.arguments (pk → model instance)."""
        for arg in self.workflow.arguments or []:
            if not isinstance(arg, dict) or arg.get('type') != 'model':
                continue
            var_name = arg.get('name')
            model_path = arg.get('model')
            lookup = arg.get('lookup') or 'pk'
            if not var_name or not model_path:
                continue
            val = self.context.get(var_name)
            if val is None:
                continue
            if hasattr(val, '_meta'):
                continue
            try:
                parts = model_path.split('.')
                if len(parts) != 2:
                    continue
                app_label, model_name = parts[0], parts[1].lower()
                Model = apps.get_model(app_label, model_name)
            except (LookupError, ValueError):
                self.log(f"Warning: Cannot resolve model '{model_path}' for '{var_name}'")
                continue
            try:
                if isinstance(val, int) or (isinstance(val, str) and str(val).strip().isdigit()):
                    obj = Model.objects.get(pk=int(val))
                elif lookup:
                    obj = Model.objects.get(**{lookup: val})
                else:
                    continue
                self.context[var_name] = obj
                self.log(f"Resolved {var_name} to {Model.__name__} instance (pk={obj.pk})")
            except Model.DoesNotExist:
                self.log(f"Error: {model_path} with {lookup}='{val}' not found.")
            except Exception as e:
                self.log(f"Warning: Failed to resolve {var_name}: {e}")

    def _resolve_auth_variables(self):
        """Resolve auth variables (source_auth_obj, domestic_tracker_auth_obj, auth_id) to ApiAuthID."""
        import integrations.models
        ApiAuthID = integrations.models.ApiAuthID
        auth_var_names = {'source_auth_obj', 'domestic_tracker_auth_obj', 'auth_id'}
        for var_name in auth_var_names:
            val = self.context.get(var_name)
            if val is None:
                continue
            if hasattr(val, '_meta'):
                continue
            try:
                pk = int(val) if isinstance(val, (int, str)) and str(val).strip().isdigit() else None
                if pk is not None:
                    obj = ApiAuthID.objects.get(pk=pk)
                    self.context[var_name] = obj
                    self.log(f"Resolved {var_name} to ApiAuthID instance (pk={obj.pk})")
            except ApiAuthID.DoesNotExist:
                self.log(f"Error: ApiAuthID with pk={val} not found.")
            except (ValueError, TypeError):
                pass

    @staticmethod
    def _extract_argument_names(arguments):
        names = set()
        for arg in arguments or []:
            if isinstance(arg, dict):
                name = arg.get('name')
                if name:
                    names.add(name)
            elif isinstance(arg, str) and arg:
                names.add(arg)
        return names

    @staticmethod
    def _filter_mapping_by_allowed_keys(mapping, allowed_keys):
        mapping = mapping or {}
        if not allowed_keys:
            return {}, list(mapping.keys())
        filtered = {}
        skipped = []
        for key, value in mapping.items():
            if key in allowed_keys:
                filtered[key] = value
            else:
                skipped.append(key)
        return filtered, skipped

    def _workflow_failure_payload(self, error):
        return {
            'success': False,
            'error': error,
            'context': self.context,
            'context_variables': self.context,
            'logs': self.logs,
            'external_requests': self.external_requests,
            'api_calls': self.external_requests,
        }

    def _handle_scenario_run_exception(self, runner, exc, idx, item, items_to_run, results):
        """On iterator steps, record failure and continue; on single run, fail the workflow."""
        self.logs.extend(runner.logs)
        self.external_requests.extend(runner.external_requests)
        if len(items_to_run) == 1:
            self.context.update(runner.context)
            self.log(f"Scenario failed: {exc}")
            return self._workflow_failure_payload(str(exc))
        item_hint = ''
        if item is not None:
            if isinstance(item, dict):
                item_hint = item.get('id', item.get('campaignId', item))
            else:
                item_hint = item
        hint_suffix = f" [item={item_hint}]" if item_hint != '' else ''
        self.log(
            f"Scenario failed (iteration {idx + 1}/{len(items_to_run)}): {exc}{hint_suffix}"
        )
        results.append({'success': False, 'error': str(exc), 'item': item})
        return None

    def run(self):
        self.log(f"Starting workflow: {self.workflow.name}")
        self._resolve_model_args()
        self._resolve_auth_variables()
        steps = self.workflow.steps.filter(is_active=True).order_by('order')

        for step in steps:
            try:
                if step.scenario:
                    from .safe_eval import SafeEvaluator
                    # Resolve iterator: if set, loop over list; else run once
                    items_to_run = None
                    if step.iterator_variable:
                        raw_items = self.context.get(step.iterator_variable)
                        if isinstance(raw_items, (list, tuple)):
                            items_to_run = list(raw_items)
                        else:
                            self.log(f"Warning: iterator_variable '{step.iterator_variable}' is not a list (got {type(raw_items).__name__}), skipping step")
                            items_to_run = []
                    if items_to_run is None:
                        items_to_run = [None]  # single run

                    results = []
                    for idx, item in enumerate(items_to_run):
                        if item is not None:
                            self.log(f"  Iteration {idx + 1}/{len(items_to_run)} (item from {step.iterator_variable})")
                        iter_context = {**self.context, 'item': item} if item is not None else self.context

                        expected_args = self._extract_argument_names(step.scenario.arguments if step.scenario else [])
                        step_mapping, skipped_keys = self._filter_mapping_by_allowed_keys(step.input_mapping or {}, expected_args)
                        if skipped_keys:
                            self.log(
                                f"Warning: Workflow step {step.order} ignored stale scenario input_mapping keys: {', '.join(sorted(skipped_keys))}"
                            )
                        args = {}
                        for k, v in step_mapping.items():
                            if isinstance(v, str) and '{{' in v:
                                hint = f"Workflow '{self.workflow.name}' step {step.order}, scenario '{step.scenario.name}', input_mapping '{k}': {v}"
                                resolved = _resolve_template(v, iter_context, raise_on_missing=True, context_hint=hint)
                                try:
                                    args[k] = json.loads(resolved) if isinstance(resolved, str) and resolved.strip().startswith(('{', '[')) else resolved
                                except json.JSONDecodeError:
                                    args[k] = resolved
                            else:
                                args[k] = v

                        runner = ScenarioRunner(step.scenario_id, {**iter_context, **args})
                        try:
                            result = runner.run()
                            self.logs.extend(runner.logs)
                            self.external_requests.extend(runner.external_requests)
                            results.append(result)
                            if len(items_to_run) == 1:
                                self.context.update(runner.context)
                        except Exception as e:
                            failure = self._handle_scenario_run_exception(
                                runner, e, idx, item, items_to_run, results
                            )
                            if failure is not None:
                                return failure

                    if len(results) > 1 and step.output_variable_name:
                        self.context[step.output_variable_name] = results
                        _log_output_variable(self.log, step.output_variable_name, results)
                    elif len(results) == 1 and step.output_variable_name and results[0]:
                        self.context[step.output_variable_name] = results[0]
                        _log_output_variable(self.log, step.output_variable_name, results[0])
                elif step.business_action:
                    from .models import BusinessActionVariant
                    tracker = _resolve_tracker_for_variant(step, self.context)
                    tracker_id = tracker.id if tracker else None
                    variant = BusinessActionVariant.objects.filter(
                        business_action=step.business_action,
                        tracker_id=tracker_id
                    ).first() if tracker_id else None
                    if not variant:
                        variant = BusinessActionVariant.objects.filter(business_action=step.business_action).first()
                    if variant and variant.scenario:
                        from .safe_eval import SafeEvaluator
                        # Resolve iterator: if set, loop over list; else run once
                        items_to_run = None
                        if step.iterator_variable:
                            raw_items = self.context.get(step.iterator_variable)
                            if isinstance(raw_items, (list, tuple)):
                                items_to_run = list(raw_items)
                            else:
                                self.log(f"Warning: iterator_variable '{step.iterator_variable}' is not a list (got {type(raw_items).__name__}), skipping step")
                                items_to_run = []
                        if items_to_run is None:
                            items_to_run = [None]  # single run: one "virtual" item

                        results = []
                        for idx, item in enumerate(items_to_run):
                            if item is not None:
                                self.log(f"  Iteration {idx + 1}/{len(items_to_run)} (item from {step.iterator_variable})")
                            iter_context = {**self.context, 'item': item} if item is not None else self.context

                            # Step input_mapping: workflow context → action args (can use {{ item.campaignId }} etc.)
                            expected_action_args = self._extract_argument_names(
                                step.business_action.arguments if step.business_action else []
                            )
                            step_mapping, skipped_keys = self._filter_mapping_by_allowed_keys(step.input_mapping or {}, expected_action_args)
                            if skipped_keys:
                                self.log(
                                    f"Warning: Workflow step {step.order} ignored stale business-action input_mapping keys: {', '.join(sorted(skipped_keys))}"
                                )
                            args = {}
                            for k, v in step_mapping.items():
                                if isinstance(v, str) and '{{' in v:
                                    hint = f"Workflow '{self.workflow.name}' step {step.order}, input_mapping '{k}': {v}"
                                    resolved = _resolve_template(v, iter_context, raise_on_missing=True, context_hint=hint)
                                    if isinstance(resolved, (dict, list)):
                                        args[k] = resolved
                                    elif isinstance(resolved, str) and resolved.strip().startswith(('{', '[')):
                                        try:
                                            args[k] = json.loads(resolved)
                                        except json.JSONDecodeError:
                                            args[k] = resolved
                                    else:
                                        args[k] = resolved
                                else:
                                    args[k] = v
                            merged = {**iter_context, **args}
                            # Variant input_mapping: action args → scenario args
                            expected_scenario_args = self._extract_argument_names(
                                variant.scenario.arguments if variant and variant.scenario else []
                            )
                            variant_mapping, skipped_variant_keys = self._filter_mapping_by_allowed_keys(
                                variant.input_mapping or {}, expected_scenario_args
                            )
                            if skipped_variant_keys:
                                self.log(
                                    f"Warning: Workflow step {step.order} ignored stale variant input_mapping keys: {', '.join(sorted(skipped_variant_keys))}"
                                )
                            scenario_args = {}
                            for k, v in variant_mapping.items():
                                if isinstance(v, str) and '{{' in v:
                                    hint = f"Workflow '{self.workflow.name}' step {step.order}, variant input_mapping '{k}': {v}"
                                    resolved = _resolve_template(v, merged, raise_on_missing=True, context_hint=hint)
                                    if isinstance(resolved, (dict, list)):
                                        scenario_args[k] = resolved
                                    elif isinstance(resolved, str) and resolved.strip().startswith(('{', '[')):
                                        try:
                                            scenario_args[k] = json.loads(resolved)
                                        except json.JSONDecodeError:
                                            scenario_args[k] = resolved
                                    else:
                                        scenario_args[k] = resolved
                                else:
                                    scenario_args[k] = v
                            runner = ScenarioRunner(variant.scenario_id, {**merged, **scenario_args})
                            try:
                                result = runner.run()
                                self.logs.extend(runner.logs)
                                self.external_requests.extend(runner.external_requests)
                                results.append(result)
                                if len(items_to_run) == 1:
                                    self.context.update(runner.context)
                            except Exception as e:
                                failure = self._handle_scenario_run_exception(
                                    runner, e, idx, item, items_to_run, results
                                )
                                if failure is not None:
                                    return failure

                        if len(results) > 1:
                            if step.output_variable_name:
                                self.context[step.output_variable_name] = results
                                _log_output_variable(self.log, step.output_variable_name, results)
                        elif len(results) == 1:
                            if variant.output_mapping:
                                hint = f"Workflow '{self.workflow.name}' step {step.order}, variant (Tracker={variant.tracker.name})"
                                mapped = _apply_output_mapping(results[0], variant.output_mapping, context_hint=hint)
                                self.context.update(mapped)
                            elif step.output_variable_name:
                                self.context[step.output_variable_name] = results[0]
                                _log_output_variable(self.log, step.output_variable_name, results[0])
            except Exception as e:
                self.log(f"Step {step.order} failed: {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'context': self.context,
                    'context_variables': self.context,
                    'logs': self.logs,
                    'external_requests': self.external_requests,
                    'api_calls': self.external_requests,
                }

        return {
            'success': True,
            'context': self.context,
            'context_variables': self.context,
            'logs': self.logs,
            'external_requests': self.external_requests,
            'api_calls': self.external_requests,
        }


def execute_single_method(endpoint_id, method_id, variables):
    """Execute a single ServiceMethod (for endpoint testing)."""
    from .models import ServiceEndpoint
    from integrations.models import ApiAuthID
    endpoint = ServiceEndpoint.objects.get(pk=endpoint_id)
    method = ServiceMethod.objects.get(pk=method_id, service_endpoint=endpoint)
    url = endpoint.endpoint
    auth_id = variables.get('auth_id')
    auth_obj = None

    for arg_name in method.arguments:
        if arg_name in variables:
            url = url.replace(f"{{{arg_name}}}", str(variables[arg_name]))
            url = url.replace(f"%{arg_name}%", str(variables[arg_name]))

    typed_method_args = {k: variables.get(k) for k in (method.arguments or []) if k in variables}
    typed_method_args = _apply_payload_value_types(method, typed_method_args, log_func=None)

    if not url.startswith('http'):
        if not auth_id:
            raise Exception(f"Invalid URL '{url}': No scheme supplied. Relative URLs require auth_id.")
        auth_obj = ApiAuthID.objects.get(pk=auth_id)
        base_url = (auth_obj.request_url or '').strip().rstrip('/')
        if not base_url or not base_url.startswith('http'):
            raise Exception(
                f"ApiAuthID '{auth_obj.account_name}' has empty or invalid request_url. "
                f"Set the base URL (e.g. https://api.example.com) in Auth ID configuration."
            )
        url = f"{base_url}/{url.lstrip('/')}"

    payload = typed_method_args.get('payload', variables.get('payload'))
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = None
    body_args = {k: v for k, v in variables.items() if k.startswith('body.')}
    body_args.update({k: v for k, v in typed_method_args.items() if k.startswith('body.')})
    if body_args:
        if payload is None:
            payload = {}
        elif not isinstance(payload, dict):
            payload = {}
        for key, value in body_args.items():
            path = key[5:]
            if path:
                parts = path.split('.')
                d = payload
                for p in parts[:-1]:
                    if p not in d:
                        d[p] = {}
                    d = d[p]
                d[parts[-1]] = value

    headers = {}
    if auth_id:
        from integrations.utils import apply_auth_to_request
        auth_obj = ApiAuthID.objects.get(pk=auth_id)
        url, headers = apply_auth_to_request(auth_obj, url, headers=headers)

    req_kwargs = {'method': endpoint.method, 'url': url, 'headers': headers}
    if payload is not None:
        req_kwargs['json'] = payload

    ApiRateLimiter().acquire(req_kwargs.get('url', ''), auth_obj=auth_obj)
    response = requests.request(**req_kwargs)
    try:
        body = response.json()
    except Exception:
        body = response.text

    external_requests = [{
        'step_name': method.name,
        'url': url,
        'method': endpoint.method,
        'request_payload': payload,
        'request_headers': headers,
        'response_status': response.status_code,
        'response_headers': dict(response.headers),
        'response_body': body,
    }]

    result = {
        'success': response.ok,
        'method': endpoint.method,
        'url': url,
        'status_code': response.status_code,
        'headers': dict(response.headers),
        'body': body,
        'request_payload': payload,
        'request_headers': headers,
        'context_variables': variables,
        'external_requests': external_requests,
        'api_calls': external_requests,
    }
    if method.return_key and isinstance(body, dict):
        parts = method.return_key.split('.')
        val = body
        for p in parts:
            val = val.get(p) if isinstance(val, dict) else None
        result['extracted_value'] = val
    if not response.ok:
        result['error'] = f"HTTP {response.status_code}: {response.text}"
    return result
