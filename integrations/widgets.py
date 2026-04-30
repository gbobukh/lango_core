from django.forms.widgets import Widget
from django import forms
from django.utils.safestring import mark_safe
from django.forms.utils import flatatt
from django.template.loader import render_to_string
import json

class KeyDefinitionsWidget(Widget):
    template_name = 'admin/integrations/widgets/key_definitions.html'

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        return context

class ClickToEditWidget(forms.Widget):
    template_name = 'admin/integrations/widgets/click_to_edit_field.html'

    def __init__(self, widget, *args, **kwargs):
        self.widget = widget
        super().__init__(*args, **kwargs)

    @property
    def media(self):
        return self.widget.media + forms.Media(js=('integrations/js/click_to_edit_field.js',))

    def render(self, name, value, attrs=None, renderer=None):
        # Render the underlying widget
        widget_html = self.widget.render(name, value, attrs, renderer)
        
        # Determine display value
        display_value = value
        if hasattr(self.widget, 'choices'):
            # It's a select widget (or select multiple)
            # Convert choices to dict for easier lookup
            choices_dict = dict(self.widget.choices)
            
            if isinstance(value, (list, tuple)):
                # Handle M2M (list of values)
                labels = []
                for v in value:
                    label = choices_dict.get(v)
                    if label:
                        labels.append(str(label))
                    else:
                        # Fallback if value not in choices (e.g. string vs int mismatch)
                        # Try converting to string
                        label = choices_dict.get(str(v))
                        if label:
                            labels.append(str(label))
                        else:
                            labels.append(str(v))
                display_value = ", ".join(labels)
            else:
                # Handle single value
                display_value = choices_dict.get(value)
                if display_value is None:
                    display_value = choices_dict.get(str(value), value)
        
        display_value = self._format_display_value(display_value)
        is_multiline = isinstance(display_value, str) and '\n' in display_value

        return render_to_string(self.template_name, {
            'display_value': display_value,
            'is_multiline': is_multiline,
            'widget_html': widget_html,
        })

    def _format_display_value(self, value):
        """
        Pretty-print JSON-like values in read mode while keeping scalar values compact.
        """
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, ensure_ascii=False)

        if isinstance(value, str):
            raw = value.strip()
            if raw and raw[0] in '{[':
                try:
                    parsed = json.loads(raw)
                except (ValueError, TypeError):
                    return value
                if isinstance(parsed, (dict, list)):
                    return json.dumps(parsed, indent=2, ensure_ascii=False)
        return value

class CredentialsInputWidget(forms.Widget):
    template_name = 'admin/integrations/widgets/credentials_input.html'

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['value'] = value
        return context
