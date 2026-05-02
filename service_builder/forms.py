from django import forms
from integrations.forms import ClickToEditFormMixin
from integrations.widgets import ClickToEditWidget
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from .models import ActionConfigLibrary, ServiceEndpoint, ServiceMethod, Scenario, ScenarioStep

class TestStatusFormMixin(forms.Form):
    mark_as_test = forms.BooleanField(
        required=False, 
        label="Mark as Ready for Testing (Manual)",
        help_text="Check this to manually set status to TEST, enabling use in Test Runners (even if validation fails)."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['mark_as_test'].initial = (self.instance.validation_status == 'TEST')

    def clean(self):
        cleaned_data = super().clean()
        mark_test = cleaned_data.get('mark_as_test')
        
        # Logic:
        # 1. If Checked -> Force TEST
        # 2. If Unchecked AND was TEST -> Revert to PENDING (Manual Switch Off)
        # 3. If Unchecked AND was VALID/PENDING -> Do nothing (let model logic handle critical fields)
        
        if mark_test:
            self.instance.validation_status = 'TEST'
        elif self.instance.validation_status == 'TEST':
            self.instance.validation_status = 'PENDING'
            
        return cleaned_data

class ServiceEndpointForm(ClickToEditFormMixin, TestStatusFormMixin, forms.ModelForm):
    class Meta:
        model = ServiceEndpoint
        fields = '__all__'

    def clean_api_configuration(self):
        data = self.cleaned_data.get('api_configuration')
        if data is None:
            return {}
        return data

from .widgets import ArgumentMappingWidget, PayloadFieldsWidget

class ServiceMethodForm(ClickToEditFormMixin, TestStatusFormMixin, forms.ModelForm):
    class Meta:
        model = ServiceMethod
        fields = '__all__'
        widgets = {
            'arguments': forms.Textarea(attrs={'readonly': 'readonly', 'rows': 3}),
            'payload_fields': PayloadFieldsWidget(attrs={'rows': 3, 'placeholder': '["body.name", "body.budget"]'}),
        }

from .widgets import ArgumentMappingWidget, TypedArgumentWidget

class ScenarioForm(ClickToEditFormMixin, TestStatusFormMixin, forms.ModelForm):
    class Meta:
        model = Scenario
        fields = '__all__'
        widgets = {
            'arguments': TypedArgumentWidget(),
            'return_variables': TypedArgumentWidget(),
        }

class ScenarioStepForm(ClickToEditFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.utils.html import format_html

        from integrations.widgets import ClickToEditWidget as _CTE
        # Base widget for action_config is chosen in ScenarioStepInline.formfield_for_dbfield
        # so locked scenarios (field swapped for *_pretty) never touch this field.
        if 'action_config' in self.fields and self.instance and self.instance.pk:
            inner = self.fields['action_config'].widget
            self.fields['action_config'].widget = _CTE(inner)

        help_link = format_html(
            ' <a href="#" onclick="window.openContextHelp(); return false;" style="color: #447e9b; font-weight: bold;">[Syntax Help]</a>'
        )
        
        if 'context_extraction' in self.fields:
            self.fields['context_extraction'].help_text += help_link
            
        if 'success_condition' in self.fields:
            self.fields['success_condition'].help_text += help_link

    def clean(self):
        cleaned_data = super().clean()
        from .scenario_step_contracts import validate_scenario_step_cleaned

        validate_scenario_step_cleaned(cleaned_data)
        return cleaned_data

    def clean_error_handlers(self):
        value = self.cleaned_data.get('error_handlers')
        if value in (None, ''):
            return []
        return value

    class Meta:
        model = ScenarioStep
        fields = '__all__'
        # Widgets for ScenarioStep are set in ScenarioStepInline.formfield_for_dbfield only when
        # each field participates in the form (unlocked scenarios and non-swapped columns).

from .models import BusinessAction


class BusinessActionForm(ClickToEditFormMixin, TestStatusFormMixin, forms.ModelForm):
    class Meta:
        model = BusinessAction
        fields = '__all__'


from .widgets import PrettyJSONWidget


class ActionConfigLibraryForm(ClickToEditFormMixin, forms.ModelForm):
    """
    Reuse click-to-edit UX for library entries:
    existing records open in read mode; each field is editable via pencil icon.
    """
    def apply_click_to_edit(self):
        if not hasattr(self, 'instance') or not self.instance.pk:
            return

        wrap_widgets = (
            forms.TextInput,
            forms.NumberInput,
            forms.EmailInput,
            forms.Textarea,
            forms.Select,
            forms.SelectMultiple,
            forms.CheckboxInput,
            RelatedFieldWidgetWrapper,
        )

        for field in self.fields.values():
            if isinstance(field.widget, ClickToEditWidget):
                continue
            if isinstance(field.widget, wrap_widgets):
                field.widget = ClickToEditWidget(field.widget)

    class Meta:
        model = ActionConfigLibrary
        fields = '__all__'
        widgets = {
            'action_config': PrettyJSONWidget(attrs={'rows': 10, 'style': 'font-family: monospace; width: 100%;'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }
