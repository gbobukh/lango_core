from django import forms
import json

class ArgumentMappingWidget(forms.Widget):
    template_name = 'admin/service_builder/widgets/argument_mapping.html'

    def __init__(self, attrs=None):
        super().__init__(attrs)

    def format_value(self, value):
        if value is None:
            return '{}'
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['value'] = self.format_value(value)
        return context

class PrettyJSONWidget(forms.Textarea):
    def format_value(self, value):
        if value is None:
            return '{}'
        # If it's a string, try to parse it first so we can re-dump it pretty
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return value
        
        return json.dumps(value, indent=4)

from django.utils.safestring import mark_safe

class PayloadFieldsWidget(forms.Textarea):
    class Media:
        js = ('service_builder/js/payload_importer_v3.js',)

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        # Add initialization script
        # We use the ID from attrs to initialize the importer
        field_id = attrs.get('id', f'id_{name}')
        script = f"""
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                if (window.PayloadImporter) {{
                    window.PayloadImporter.init('{field_id}');
                }}
            }});
        </script>
        """
        return mark_safe(html + script)

class TypedArgumentWidget(forms.Widget):
    template_name = 'admin/service_builder/widgets/typed_arguments.html'

    class Media:
        css = {
            'all': ('service_builder/css/typed_arguments.css',)
        }
        js = ('service_builder/js/typed_arguments_v7.js',)

    def __init__(self, attrs=None):
        super().__init__(attrs)

    def format_value(self, value):
        if value is None:
            return '[]'
        if isinstance(value, str):
            # If it's a string, it might be a JSON string or a legacy comma-separated list?
            # Scenario.arguments is a JSONField, so value should be a list or dict.
            # But in the form it might come as string if re-rendering.
            return value
        return json.dumps(value)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['value'] = self.format_value(value)
        return context


class ApiBatchConfigWidget(forms.Widget):
    template_name = 'admin/service_builder/widgets/api_batch_config.html'

    class Media:
        js = ('service_builder/js/api_batch_widget_v2.js',)

    def format_value(self, value):
        if value is None:
            return '{}'
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['value'] = self.format_value(value)
        return context
