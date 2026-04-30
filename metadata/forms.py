from django import forms
from .models import CompatibilityMatrix, TargetParameter
import json

class CompatibilityMatrixForm(forms.ModelForm):
    subject_value = forms.ChoiceField(
        choices=[], 
        required=False, 
        widget=forms.Select(attrs={'class': 'dynamic-subject-value', 'style': 'min-width: 250px !important;'})
    )
    allowed_values = forms.MultipleChoiceField(
        choices=[], 
        required=False, 
        widget=forms.SelectMultiple(attrs={'class': 'dynamic-allowed-values', 'style': 'min-width: 350px !important; min-height: 150px !important;'})
    )

    class Meta:
        model = CompatibilityMatrix
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate initial choices if instance exists
        if self.instance and self.instance.pk:
            if self.instance.subject_parameter:
                vals = self.instance.subject_parameter.values
                self.fields['subject_value'].choices = [(v, v) for v in vals]
            
            if self.instance.target_parameter:
                vals = self.instance.target_parameter.values
                self.fields['allowed_values'].choices = [(v, v) for v in vals]
        else:
             # New instance (Add View): Default to Unlocked
             self.fields['is_locked'].initial = False
        
        # Also populate if data is present (validation phase) to prevent "Select valid choice" error
        if self.data:
            subject_param_id = self.data.get('subject_parameter')
            target_param_id = self.data.get('target_parameter')
            
            if subject_param_id:
                try:
                    sp = TargetParameter.objects.get(pk=subject_param_id)
                    self.fields['subject_value'].choices = [(v, v) for v in sp.values]
                except (ValueError, TargetParameter.DoesNotExist):
                    pass

            if target_param_id:
                try:
                    tp = TargetParameter.objects.get(pk=target_param_id)
                    self.fields['allowed_values'].choices = [(v, v) for v in tp.values]
                except (ValueError, TargetParameter.DoesNotExist):
                    pass
