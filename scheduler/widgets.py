from django import forms
import json


class ScheduledWorkflowArgumentMappingWidget(forms.Widget):
    template_name = 'admin/scheduler/widgets/argument_mapping.html'

    class Media:
        css = {'all': ('scheduler/css/argument_mapping.css',)}
        js = ('scheduler/js/argument_mapping.js',)

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
