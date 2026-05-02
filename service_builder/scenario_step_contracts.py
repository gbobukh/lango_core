"""
Explicit contracts for ScenarioStep polymorphism by step_type.

Validation rules live here as the single source of truth for admin/form saves.
Runtime behaviour remains in ScenarioRunner, ActionRunner, ApiBatchRunner.

API_CALL does not use action_type / action_config: validate_scenario_step_cleaned clears them
in-place so saves do not retain stale values.

See docs/engineering_principles.md (polymorphic contracts).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from .models import SCENARIO_ACTION_TYPE_CHOICES

ACTION_TYPE_CODES = frozenset(code for code, _label in SCENARIO_ACTION_TYPE_CHOICES)

# Admin form visibility (stacked inline must match validation & Runtime contracts).
_SCENARIO_STEP_FIELDS_COMMON = frozenset(
    {
        'is_active',
        'order',
        'step_type',
        'iterator_variable',
        'output_variable_name',
        'response_modification',
        'error_handlers',
        'context_extraction',
        'success_condition',
        'condition_error_message',
    }
)
SCENARIO_STEP_FORM_FIELDS_BY_TYPE: dict[str, frozenset[str]] = {
    'API_CALL': _SCENARIO_STEP_FIELDS_COMMON
    | frozenset({'method', 'argument_mapping', 'auth_context_variable'}),
    'ACTION': _SCENARIO_STEP_FIELDS_COMMON
    | frozenset({'action_type', 'action_config'}),
    'API_BATCH': _SCENARIO_STEP_FIELDS_COMMON
    | frozenset({'action_config', 'auth_context_variable'}),
}


def validate_scenario_step_cleaned(cleaned_data: dict) -> None:
    """
    Validate inline ScenarioStep form cleaned_data.
    Mutates cleaned_data where fields are irrelevant for the chosen step_type.
    Raises django.core.exceptions.ValidationError with field keys matching form fields.
    """
    step_type = cleaned_data.get('step_type') or 'API_CALL'

    if step_type == 'API_CALL':
        # Поля action не участвуют в API Call — сбрасываем, чтобы не хранить мусор в БД.
        cleaned_data['action_type'] = None
        cleaned_data['action_config'] = {}
        _validate_api_call(cleaned_data)
    elif step_type == 'ACTION':
        _validate_action(cleaned_data)
    elif step_type == 'API_BATCH':
        _validate_api_batch(cleaned_data)
    else:
        raise ValidationError(
            {'step_type': ValidationError('Неизвестный тип шага.', code='invalid_choice')}
        )


def _falsy_action_type(value) -> bool:
    return value in (None, '',)


def _ensure_action_config_dict(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    raise ValidationError(
        {'action_config': ValidationError('Должен быть JSON-объект.', code='invalid')}
    )


def _validate_api_call(cleaned_data: dict) -> None:
    method = cleaned_data.get('method')

    if not method:
        raise ValidationError(
            {
                'method': [
                    ValidationError(
                        'Для шага типа API Call нужно выбрать Service Method.', code='required'
                    )
                ],
            }
        )


def _validate_action(cleaned_data: dict) -> None:
    method = cleaned_data.get('method')
    action_type = cleaned_data.get('action_type')
    action_config_raw = cleaned_data.get('action_config')

    errs: dict[str, list] = {}
    if method:
        errs.setdefault('method', []).append(
            ValidationError(
                'Для шага типа Action поле Service Method не используется.', code='invalid'
            )
        )

    if _falsy_action_type(action_type):
        errs.setdefault('action_type', []).append(
            ValidationError('Для шага типа Action укажите Action Type.', code='required')
        )
    elif action_type not in ACTION_TYPE_CODES:
        errs.setdefault('action_type', []).append(
            ValidationError('Недопустимый Action Type.', code='invalid_choice')
        )

    try:
        _ensure_action_config_dict(action_config_raw)
    except ValidationError as exc:
        errs.setdefault('action_config', []).extend(exc.error_dict.get('action_config', []))

    if errs:
        raise ValidationError(errs)


def _validate_api_batch(cleaned_data: dict) -> None:
    method = cleaned_data.get('method')
    action_type = cleaned_data.get('action_type')
    action_config_raw = cleaned_data.get('action_config')

    errs: dict[str, list] = {}
    if method:
        errs.setdefault('method', []).append(
            ValidationError(
                'Для шага типа API Batch поле Service Method не используется.', code='invalid'
            )
        )

    if not _falsy_action_type(action_type):
        errs.setdefault('action_type', []).append(
            ValidationError(
                'Для API Batch поле Action Type не используется — очистите его.', code='invalid'
            )
        )

    try:
        cfg = _ensure_action_config_dict(action_config_raw)
    except ValidationError as exc:
        errs.setdefault('action_config', []).extend(exc.error_dict.get('action_config', []))
        if errs:
            raise ValidationError(errs)
        return

    routing = cfg.get('routing')
    if not isinstance(routing, dict):
        errs.setdefault('action_config', []).append(
            ValidationError('API Batch: поле routing должно быть объектом.', code='invalid')
        )
    else:
        methods = routing.get('methods')
        if not isinstance(methods, list) or len(methods) == 0:
            errs.setdefault('action_config', []).append(
                ValidationError(
                    'API Batch: routing.methods должен быть непустым списком маршрутов.',
                    code='invalid',
                )
            )
        else:
            for idx, route in enumerate(methods):
                if not isinstance(route, dict):
                    errs.setdefault('action_config', []).append(
                        ValidationError(
                            f'API Batch: маршрут #{idx + 1} должен быть объектом.',
                            code='invalid',
                        )
                    )
                    continue
                entity = route.get('entity')
                if not entity or not isinstance(entity, str):
                    errs.setdefault('action_config', []).append(
                        ValidationError(
                            f'API Batch: у маршрута #{idx + 1} задайте непустое поле entity.',
                            code='invalid',
                        )
                    )
                method_id = route.get('method_id')
                method_ref = route.get('method_ref')
                has_id = method_id is not None and method_id != ''
                has_ref = isinstance(method_ref, str) and method_ref.startswith('method://')
                if not has_id and not has_ref:
                    errs.setdefault('action_config', []).append(
                        ValidationError(
                            f'API Batch: маршрут #{idx + 1} — укажите method_id или method_ref (method://...).',
                            code='invalid',
                        )
                    )

    source_cfg = cfg.get('source')
    if not isinstance(source_cfg, dict):
        errs.setdefault('action_config', []).append(
            ValidationError('API Batch: поле source должно быть объектом.', code='invalid')
        )
    else:
        source_path = source_cfg.get('value')
        if source_path is None or source_path == '':
            errs.setdefault('action_config', []).append(
                ValidationError(
                    'API Batch: задайте source.value (путь к списку операций в контексте).',
                    code='invalid',
                )
            )
        elif not isinstance(source_path, str):
            errs.setdefault('action_config', []).append(
                ValidationError('API Batch: source.value должно быть строкой.', code='invalid')
            )

    if errs:
        raise ValidationError(errs)
