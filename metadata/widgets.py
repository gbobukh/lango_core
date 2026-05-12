import json
from django import forms
from django.utils.safestring import mark_safe
from .models import TargetParameter

class PublisherConfigWidget(forms.Widget):
    template_name = 'metadata/widgets/publisher_config.html' # standard django approach, but we'll inline for now or use format_html

    class Media:
        css = {
            'all': ('metadata/css/publisher_config.css',) # Optional, maybe inline styles
        }
        js = ('metadata/js/publisher_config.js',)

    def _is_disabled(self, attrs):
        return bool((attrs or {}).get('disabled'))

    def render(self, name, value, attrs=None, renderer=None):
        # deserializing value
        if isinstance(value, str):
            try:
                config = json.loads(value)
            except json.JSONDecodeError:
                config = {}
        elif isinstance(value, dict):
            config = value
        else:
            config = {}
        config = config or {}

        all_params = TargetParameter.objects.all().order_by('name')
        widget_disabled = self._is_disabled(attrs)
        widget_classes = 'publisher-config-widget'
        if widget_disabled:
            widget_classes += ' config-widget-locked'

        # Build HTML
        html = [f'<div class="{widget_classes}" id="widget_{name}">']
        if not widget_disabled:
            html.append(f'<input type="hidden" name="{name}" value="{json.dumps(config) if config else "{}"}">')
        
        # Inline minimal styles
        html.append("""
        <style>
            .publisher-config-table { width: 100%; max_width: 600px; border-collapse: collapse; }
            .publisher-config-table th, .publisher-config-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            .publisher-config-table th { background-color: #f4f4f4; }
            .config-widget-locked input[disabled] { background-color: #f4f4f4; color: #666; cursor: not-allowed; }
        </style>
        """)

        html.append('<table class="publisher-config-table"><thead><tr>')
        html.append('<th>Target Parameter</th><th>Exists</th><th>TTZ Encoded</th>')
        html.append('</tr></thead><tbody>')

        for param in all_params:
            param_name = param.name
            
            # Current state
            state = config.get(param_name, {'exists': False, 'ttz_encoded': False})
            exists = state.get('exists', False)
            ttz_encoded = state.get('ttz_encoded', False)

            # Attrs
            exists_checked = 'checked' if exists else ''
            ttz_checked = 'checked' if ttz_encoded else ''
            
            # TTZ disabled if not exists OR if widget is effectively disabled
            ttz_disabled = 'disabled' if (not exists or widget_disabled) else ''
            exists_disabled = 'disabled' if widget_disabled else ''

            html.append(f'<tr data-param-name="{param_name}">')
            html.append(f'<td><strong>{param_name}</strong></td>')
            
            # Exists Checkbox
            html.append(f'<td><input type="checkbox" class="exists-cb" {exists_checked} {exists_disabled}></td>')
            
            # TTZ Checkbox
            html.append(f'<td><input type="checkbox" class="ttz-cb" {ttz_checked} {ttz_disabled}></td>')
            
            html.append('</tr>')

        html.append('</tbody></table></div>')
        
        return mark_safe(''.join(html))

class KeyDefinitionsWidget(forms.Widget):
    template_name = 'admin/integrations/widgets/key_definitions.html'

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        return context

from .models import GlobalVariable

class TrackerConfigWidget(forms.Widget):
    template_name = 'metadata/widgets/tracker_config.html' # Virtual, inline template

    class Media:
        js = ('metadata/js/tracker_config.js',)

    def _is_disabled(self, attrs):
        return bool((attrs or {}).get('disabled'))

    def render(self, name, value, attrs=None, renderer=None):
        # Deserializing value
        if isinstance(value, str):
            try:
                config = json.loads(value)
            except json.JSONDecodeError:
                config = {}
        elif isinstance(value, dict):
            config = value
        else:
            config = {}
        config = config or {}

        # Fetch all known Global Variables
        all_vars = GlobalVariable.objects.all().order_by('name')
        widget_disabled = self._is_disabled(attrs)
        widget_classes = 'tracker-config-widget'
        if widget_disabled:
            widget_classes += ' config-widget-locked'

        # Build HTML
        html = [f'<div class="{widget_classes}" id="widget_{name}">']
        if not widget_disabled:
            html.append(f'<input type="hidden" name="{name}" value=\'{json.dumps(config) if config else "{}"}\'>')
        
        # Inline minimal styles (consistent with PublisherConfig)
        html.append("""
        <style>
            .tracker-config-table { width: 100%; max_width: 800px; border-collapse: collapse; margin-top: 10px; }
            .tracker-config-table th, .tracker-config-table td { border: 1px solid #ddd; padding: 10px; text-align: left; }
            .tracker-config-table th { background-color: #f4f4f4; text-transform: uppercase; font-size: 11px; font-weight: bold; color: #666; }
            .tracker-config-table input[type="text"] { width: 100%; box-sizing: border-box; padding: 5px; border: 1px solid #ccc; border-radius: 4px; }
            .tracker-config-table input[type="text"]:focus { border-color: #417690; outline: none; }
            .config-widget-locked .mapping-value { color: #333; }
            .config-widget-locked input[disabled] { background-color: #f4f4f4; color: #666; cursor: not-allowed; }
        </style>
        """)

        html.append('<table class="tracker-config-table"><thead><tr>')
        html.append('<th style="width: 40%">Global Variable</th><th style="width: 60%">Key in Tracker Response</th>')
        html.append('</tr></thead><tbody>')

        if not all_vars:
             html.append('<tr><td colspan="2" style="color: grey; text-align: center; padding: 20px;">No Global Variables defined yet. Add them in the "Global Variables" section.</td></tr>')

        for var in all_vars:
            var_name = var.name
            var_desc = var.description or ""
            
            # Current state (Key for this variable)
            current_key = config.get(var_name, "")

            html.append(f'<tr data-var-name="{var_name}">')
            
            # Variable Name + Description tooltip
            html.append(f'<td><strong>{var_name}</strong>')
            if var_desc:
                html.append(f'<br><small style="color: #666;">{var_desc}</small>')
            html.append('</td>')
            
            if widget_disabled:
                display_key = current_key or '—'
                html.append(f'<td class="mapping-value">{display_key}</td>')
            else:
                html.append(
                    f'<td><input type="text" class="key-input" value="{current_key}" '
                    f'placeholder="e.g. click_id"></td>'
                )
            
            html.append('</tr>')

        html.append('</tbody></table></div>')
        
        return mark_safe(''.join(html))
