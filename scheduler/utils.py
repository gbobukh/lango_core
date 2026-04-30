"""
Utilities for scheduler, including dynamic date preset resolution.
"""
from datetime import date, timedelta

# Preset values stored in default_arguments for report_dates
REPORT_DATES_PRESETS = frozenset({
    'today', 'yesterday', 'last-3-days', 'last-7-days', 'last-30-days', 'last-90-days',
})

PRESET_LABELS = {
    'today': 'Today (dynamic)',
    'yesterday': 'Yesterday (dynamic)',
    'last-3-days': 'Last 3 days (dynamic)',
    'last-7-days': 'Last 7 days (dynamic)',
    'last-30-days': 'Last 30 days (dynamic)',
    'last-90-days': 'Last 90 days (dynamic)',
}


def resolve_report_dates_preset(preset_value, reference_date=None):
    """
    Convert a preset key to {start, end} dates based on reference_date (default: today).
    Returns None if preset_value is not a known preset.
    """
    if preset_value not in REPORT_DATES_PRESETS:
        return None
    ref = reference_date or date.today()
    if preset_value == 'today':
        return {'start': ref.isoformat(), 'end': ref.isoformat()}
    if preset_value == 'yesterday':
        d = ref - timedelta(days=1)
        return {'start': d.isoformat(), 'end': d.isoformat()}
    if preset_value == 'last-3-days':
        start = ref - timedelta(days=3)
        return {'start': start.isoformat(), 'end': ref.isoformat()}
    if preset_value == 'last-7-days':
        start = ref - timedelta(days=7)
        return {'start': start.isoformat(), 'end': ref.isoformat()}
    if preset_value == 'last-30-days':
        start = ref - timedelta(days=30)
        return {'start': start.isoformat(), 'end': ref.isoformat()}
    if preset_value == 'last-90-days':
        start = ref - timedelta(days=90)
        return {'start': start.isoformat(), 'end': ref.isoformat()}
    return None


def resolve_default_arguments(default_arguments, workflow_arguments):
    """
    Resolve report_dates presets in default_arguments to actual {start, end} dates.
    Uses workflow.arguments to identify which keys are report_dates.
    Returns a new dict with presets resolved; other values unchanged.
    """
    if not default_arguments:
        return {}
    result = dict(default_arguments)
    args = workflow_arguments or []

    for arg in args:
        if not isinstance(arg, dict):
            continue
        name = arg.get('name')
        arg_type = arg.get('type', 'string')
        if not name or name not in result:
            continue

        val = result.get(name)

        if arg_type == 'report_dates':
            if not isinstance(val, dict):
                continue
            preset = val.get('preset')
            if preset:
                resolved = resolve_report_dates_preset(preset)
                if resolved:
                    result[name] = resolved
            continue

        if arg_type == 'integer' and isinstance(val, str):
            text = val.strip()
            if text:
                try:
                    result[name] = int(text)
                except ValueError:
                    pass
            continue

        if arg_type in ('float', 'number') and isinstance(val, str):
            text = val.strip()
            if text:
                try:
                    result[name] = float(text)
                except ValueError:
                    pass
            continue

        if arg_type == 'boolean' and isinstance(val, str):
            normalized = val.strip().lower()
            if normalized in ('true', '1', 'yes', 'on'):
                result[name] = True
            elif normalized in ('false', '0', 'no', 'off'):
                result[name] = False
            continue

        if arg_type == 'json' and isinstance(val, str):
            text = val.strip()
            if text:
                try:
                    import json
                    result[name] = json.loads(text)
                except (ValueError, TypeError):
                    pass
    return result
