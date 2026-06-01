import json
import os

from django import forms
from django.core.exceptions import ValidationError

from .models import ApiSpec, CompatibilityMatrix, TargetParameter

MAX_API_SPEC_UPLOAD_BYTES = 100 * 1024 * 1024


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
            if self.instance.subject_parameter and 'subject_value' in self.fields:
                vals = self.instance.subject_parameter.values
                self.fields['subject_value'].choices = [(v, v) for v in vals]

            if self.instance.target_parameter and 'allowed_values' in self.fields:
                vals = self.instance.target_parameter.values
                self.fields['allowed_values'].choices = [(v, v) for v in vals]
        elif 'is_locked' in self.fields:
            # New instance (Add View): Default to Unlocked
            self.fields['is_locked'].initial = False

        # Also populate if data is present (validation phase) to prevent "Select valid choice" error
        if self.data:
            subject_param_id = self.data.get('subject_parameter')
            target_param_id = self.data.get('target_parameter')

            if subject_param_id and 'subject_value' in self.fields:
                try:
                    sp = TargetParameter.objects.get(pk=subject_param_id)
                    self.fields['subject_value'].choices = [(v, v) for v in sp.values]
                except (ValueError, TargetParameter.DoesNotExist):
                    pass

            if target_param_id and 'allowed_values' in self.fields:
                try:
                    tp = TargetParameter.objects.get(pk=target_param_id)
                    self.fields['allowed_values'].choices = [(v, v) for v in tp.values]
                except (ValueError, TargetParameter.DoesNotExist):
                    pass


class ApiSpecForm(forms.ModelForm):
    class Meta:
        model = ApiSpec
        fields = '__all__'

    def clean_spec_file(self):
        uploaded = self.cleaned_data.get('spec_file')
        if uploaded is False:
            return uploaded
        if uploaded:
            if uploaded.size > MAX_API_SPEC_UPLOAD_BYTES:
                raise ValidationError(
                    f'File is too large ({uploaded.size} bytes). '
                    f'Maximum allowed size is {MAX_API_SPEC_UPLOAD_BYTES // (1024 * 1024)} MB.'
                )
            return uploaded
        if not self.instance.pk or not self.instance.spec_file:
            raise ValidationError('Upload an API specification file.')
        return self.instance.spec_file

    def save(self, commit=True):
        obj = super().save(commit=False)
        uploaded = self.cleaned_data.get('spec_file')
        if uploaded and getattr(uploaded, 'name', None):
            obj.source_filename = os.path.basename(uploaded.name)
        if commit:
            previous_path = None
            if obj.pk:
                previous = ApiSpec.objects.filter(pk=obj.pk).first()
                if (
                    previous
                    and previous.spec_file
                    and previous.spec_file.name != getattr(obj.spec_file, 'name', None)
                ):
                    previous_path = previous.spec_file.name
            obj.save()
            self.save_m2m()
            if previous_path and obj.spec_file.name != previous_path:
                from django.core.files.storage import default_storage

                if default_storage.exists(previous_path):
                    default_storage.delete(previous_path)
        return obj
