from django import forms
from django.forms.widgets import Widget, TextInput, NumberInput, EmailInput
from .models import ApiAuthType, Tracker, ApiAuthID, PartnerAccount, PartnerAccountType, PartnerAccountTrackerIdentifier, SystemConfig
from .widgets import ClickToEditWidget, KeyDefinitionsWidget, CredentialsInputWidget

from django.contrib.admin.widgets import RelatedFieldWidgetWrapper

class ClickToEditFormMixin:
    """
    Mixin to automatically wrap suitable fields with ClickToEditWidget.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_click_to_edit()

    def apply_click_to_edit(self):
        with open('/root/lango_core/debug_log.txt', 'a') as f:
            # Only apply if editing an existing instance
            if not hasattr(self, 'instance') or not self.instance.pk:
                f.write(f"ClickToEdit: Skipping {self.__class__.__name__} (No instance or PK)\n")
                return

            f.write(f"ClickToEdit: Applying to {self.__class__.__name__}\n")
            for name, field in self.fields.items():
                # Skip fields that already have custom complex widgets or shouldn't be wrapped
                # Also skip 'visible_to' as requested (Access Control has its own collapse logic)
                if name == 'visible_to' or isinstance(field.widget, (KeyDefinitionsWidget, CredentialsInputWidget, forms.CheckboxSelectMultiple)):
                    f.write(f"  Skipping field {name} (Widget: {field.widget.__class__.__name__})\n")
                    continue
                    
                # Wrap standard input widgets, textareas, and Select widgets (including Admin wrappers and M2M)
                if isinstance(field.widget, (TextInput, NumberInput, EmailInput, forms.Textarea, forms.Select, forms.SelectMultiple, RelatedFieldWidgetWrapper)):
                    f.write(f"  Wrapping field {name} (Widget: {field.widget.__class__.__name__})\n")
                    field.widget = ClickToEditWidget(field.widget)
                else:
                    f.write(f"  Ignored field {name} (Widget: {field.widget.__class__.__name__})\n")

class ApiAuthTypeForm(ClickToEditFormMixin, forms.ModelForm):
    class Meta:
        model = ApiAuthType
        fields = '__all__'
        widgets = {
            'key_definitions': KeyDefinitionsWidget(),
        }

class TrackerForm(ClickToEditFormMixin, forms.ModelForm):
    class Meta:
        model = Tracker
        fields = '__all__'


class ApiAuthIDForm(ClickToEditFormMixin, forms.ModelForm):
    # Explicitly declare the field since it's editable=False in model
    credentials_encrypted = forms.CharField(
        widget=CredentialsInputWidget, 
        required=False,
        label="Credentials"
    )

    class Meta:
        model = ApiAuthID
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.credentials_encrypted:
            # Decrypt for display in the widget
            from .utils import decrypt_data
            try:
                decrypted = decrypt_data(self.instance.credentials_encrypted)
                # Widget expects a JSON string of the dict
                import json
                if isinstance(decrypted, dict):
                    self.initial['credentials_encrypted'] = json.dumps(decrypted)
                else:
                    self.initial['credentials_encrypted'] = decrypted
            except Exception as e:
                print(f"Error decrypting credentials: {e}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        # The widget returns a JSON string of the credentials
        creds_json = self.cleaned_data.get('credentials_encrypted')
        if creds_json:
            # Encrypt it before saving
            from .utils import encrypt_data
            # We need to pass the dict, not the string, to set_credentials if we want to be consistent?
            # Actually encrypt_data handles both.
            # But wait, set_credentials calls encrypt_data.
            # So we can just set the raw encrypted string? No, set_credentials expects data to encrypt.
            # So we pass the JSON string (which represents the dict) to encrypt_data.
            instance.credentials_encrypted = encrypt_data(creds_json)
        
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class PartnerAccountForm(ClickToEditFormMixin, forms.ModelForm):
    class Meta:
        model = PartnerAccount
        fields = '__all__'


class PartnerAccountTypeForm(ClickToEditFormMixin, forms.ModelForm):
    class Meta:
        model = PartnerAccountType
        fields = '__all__'

class PartnerAccountTrackerIdentifierForm(ClickToEditFormMixin, forms.ModelForm):
    class Meta:
        model = PartnerAccountTrackerIdentifier
        fields = '__all__'


class SystemConfigForm(ClickToEditFormMixin, forms.ModelForm):
    class Meta:
        model = SystemConfig
        fields = '__all__'
        widgets = {
            'value': forms.Textarea(attrs={'rows': 10, 'style': 'font-family: monospace; width: 100%;'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }
