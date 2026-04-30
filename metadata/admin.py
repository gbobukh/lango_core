from django.contrib import admin
from django.db import models
from .models import (
    TargetParameter,
    PublisherConfig,
    CompatibilityMatrix,
    TrafficType,
    SegmentAttributeType,
    SegmentAttribute,
)
# from integrations.widgets import KeyDefinitionsWidget 
from .widgets import PublisherConfigWidget, KeyDefinitionsWidget

@admin.register(TargetParameter)
class TargetParameterAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    # Use KeyDefinitionsWidget for the 'values' JSONField
    formfield_overrides = {
        models.JSONField: {'widget': KeyDefinitionsWidget},
    }

@admin.register(PublisherConfig)
class PublisherConfigAdmin(admin.ModelAdmin):
    list_display = ('partner_account', 'updated_at')
    list_filter = ('partner_account__account_type',)
    search_fields = ('partner_account__name',)
    readonly_fields = ('created_at', 'updated_at')
    
    # Use our new widget for the 'config' JSONField
    formfield_overrides = {
        models.JSONField: {'widget': PublisherConfigWidget},
    }

    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',) # Reuse existing styles
        }
        js = ('integrations/js/move_access_control.js',) # Optional helpers

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.is_locked:
            # If locked, disable the config widget
            if 'config' in form.base_fields:
                form.base_fields['config'].widget.attrs['disabled'] = True
        return form

from .forms import CompatibilityMatrixForm
import json

@admin.register(TrafficType)
class TrafficTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(SegmentAttributeType)
class SegmentAttributeTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(SegmentAttribute)
class SegmentAttributeAdmin(admin.ModelAdmin):
    list_display = ('name', 'attribute_type', 'created_at')
    list_filter = ('attribute_type',)
    search_fields = ('name',)


@admin.register(CompatibilityMatrix)
class CompatibilityMatrixAdmin(admin.ModelAdmin):
    form = CompatibilityMatrixForm
    list_display = ('subject_parameter', 'subject_value', 'target_parameter', 'allowed_values_preview')
    list_filter = ('subject_parameter', 'target_parameter')
    search_fields = ('subject_value',)
    
    # Force use of our template override
    change_form_template = 'admin/metadata/compatibilitymatrix/change_form.html'
    add_form_template = 'admin/metadata/compatibilitymatrix/change_form.html'
    
    fieldsets = (
        (None, {
            'fields': ('is_locked', 'subject_parameter', 'subject_value', 'target_parameter', 'allowed_values')
        }),
    )

    def allowed_values_preview(self, obj):
        return ", ".join(obj.allowed_values)
    allowed_values_preview.short_description = "Allowed Values"

    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',)
        }
        js = (
            'integrations/js/move_access_control.js',
            'metadata/js/compatibility_matrix.js',
        )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.is_locked:
            # Disable all fields if locked
            for field_name in ['subject_parameter', 'subject_value', 'target_parameter', 'allowed_values']:
                if field_name in form.base_fields:
                    form.base_fields[field_name].widget.attrs['disabled'] = True
                    # For ChoiceFields (our dynamic widgets), we also need to make them effectively readonly for data passing
                    form.base_fields[field_name].required = False
        elif obj is None:
             # Add view: Default to Unlocked
             form.base_fields['is_locked'].initial = False
             
        return form

    def get_target_params_json(self):
        """Returns JSON mapping of TargetParameter ID -> Values list"""
        data = {}
        for param in TargetParameter.objects.all():
            data[param.id] = param.values
        return json.dumps(data)
    
    def get_changeform_initial_data(self, request):
        """Default new rules to Unlocked so they can be edited immediately"""
        return {'is_locked': False}

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['target_params_json'] = self.get_target_params_json()
        return super().add_view(request, form_url, extra_context=extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['target_params_json'] = self.get_target_params_json()
        return super().change_view(request, object_id, form_url, extra_context=extra_context)





from .models import GlobalVariable, TrackerConfig
from .widgets import TrackerConfigWidget

@admin.register(GlobalVariable)
class GlobalVariableAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
    # inlines = [] # Removed

    class Media:
        js = ('metadata/js/global_variable_admin.js',)

@admin.register(TrackerConfig)
class TrackerConfigAdmin(admin.ModelAdmin):
    list_display = ('tracker', 'updated_at')
    search_fields = ('tracker__name',)
    # list_filter = ('is_locked',) # Removed as per request
    
    formfield_overrides = {
        models.JSONField: {'widget': TrackerConfigWidget},
    }

    class Media:
        # Reuse locking css/js or create new. 
        # reusing admin_locking_v2.css if it exists or we can just rely on the widget's JS listening to the checkbox.
        pass

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.is_locked:
            # If locked, disable the config widget
            if 'mapping' in form.base_fields:
                form.base_fields['mapping'].widget.attrs['disabled'] = True
        return form

