from django.contrib import admin
from django.db import models
from integrations.admin_access import AccessControlAdminMixin
from integrations.access_control import filter_queryset_for_user
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
class TargetParameterAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    # Use KeyDefinitionsWidget for the 'values' JSONField
    formfield_overrides = {
        models.JSONField: {'widget': KeyDefinitionsWidget},
    }

@admin.register(PublisherConfig)
class PublisherConfigAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('partner_account', 'updated_at')
    list_filter = ('partner_account__account_type',)
    search_fields = ('partner_account__name',)
    readonly_fields = ('created_at', 'updated_at')
    LOCKED_CONTENT_FIELDS = ('partner_account', 'config')
    LOCKED_DISPLAY_FIELDS = {
        'config': 'config_display',
    }
    LOCKED_JSON_FIELD = 'config'

    # Use our new widget for the 'config' JSONField
    formfield_overrides = {
        models.JSONField: {'widget': PublisherConfigWidget},
    }

    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',) # Reuse existing styles
        }
        js = (
            'integrations/js/move_access_control.js',
            'metadata/js/publisher_config.js',
        )

    def _content_fields_locked(self, request, obj):
        if obj is None:
            return False
        if request.method == 'POST':
            if not request.POST.get('is_locked'):
                if request.POST.get(self.LOCKED_JSON_FIELD) is None:
                    return True
            return bool(request.POST.get('is_locked'))
        return obj.is_locked

    def _replace_locked_display_fields(self, fields):
        if isinstance(fields, (tuple, list)):
            replaced = [self._replace_locked_display_fields(field) for field in fields]
            return tuple(replaced) if isinstance(fields, tuple) else replaced
        if isinstance(fields, str) and fields in self.LOCKED_DISPLAY_FIELDS:
            return self.LOCKED_DISPLAY_FIELDS[fields]
        return fields

    def config_display(self, obj):
        if obj is None:
            return '-'
        widget = PublisherConfigWidget()
        return widget.render('config_display', obj.config, attrs={'disabled': True})

    config_display.short_description = PublisherConfig._meta.get_field('config').verbose_name

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and self._content_fields_locked(request, obj):
            if 'partner_account' not in readonly:
                readonly.append('partner_account')
            display_field = self.LOCKED_DISPLAY_FIELDS['config']
            if display_field not in readonly:
                readonly.append(display_field)
        return readonly

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if obj and self._content_fields_locked(request, obj):
            for field_name in self.LOCKED_DISPLAY_FIELDS:
                if field_name not in exclude:
                    exclude.append(field_name)
        return exclude

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not (obj and self._content_fields_locked(request, obj)):
            return fieldsets

        rebuilt = []
        for title, options in fieldsets:
            copied = dict(options)
            copied['fields'] = self._replace_locked_display_fields(copied.get('fields', ()))
            rebuilt.append((title, copied))
        return rebuilt

    def save_model(self, request, obj, form, change):
        if change:
            original = PublisherConfig.objects.get(pk=obj.pk)
            if self._content_fields_locked(request, obj):
                for field_name in self.LOCKED_CONTENT_FIELDS:
                    setattr(obj, field_name, getattr(original, field_name))
                if request.method == 'POST' and not request.POST.get('is_locked'):
                    obj.is_locked = False
            elif not request.POST.get('is_locked'):
                for field_name in self.LOCKED_CONTENT_FIELDS:
                    setattr(obj, field_name, getattr(original, field_name))
                obj.is_locked = False
        super().save_model(request, obj, form, change)
        if change and not request.POST.get('is_locked') and request.POST.get('config') is not None:
            PublisherConfig.objects.filter(pk=obj.pk).update(is_locked=True)
            obj.is_locked = True

from .forms import CompatibilityMatrixForm
import json

@admin.register(TrafficType)
class TrafficTypeAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(SegmentAttributeType)
class SegmentAttributeTypeAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(SegmentAttribute)
class SegmentAttributeAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'attribute_type', 'created_at')
    list_filter = ('attribute_type',)
    search_fields = ('name',)


@admin.register(CompatibilityMatrix)
class CompatibilityMatrixAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    form = CompatibilityMatrixForm
    list_display = ('subject_parameter', 'subject_value', 'target_parameter', 'allowed_values_preview')
    list_filter = ('subject_parameter', 'target_parameter')
    search_fields = ('subject_value',)
    RULE_FIELDS = (
        'subject_parameter',
        'subject_value',
        'target_parameter',
        'allowed_values',
    )
    
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

    def _rule_fields_locked(self, request, obj):
        if obj is None:
            return False
        if request.method == 'POST':
            return bool(request.POST.get('is_locked'))
        return obj.is_locked

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and self._rule_fields_locked(request, obj):
            for field_name in self.RULE_FIELDS:
                if field_name not in readonly:
                    readonly.append(field_name)
        return readonly

    def save_model(self, request, obj, form, change):
        if change and self._rule_fields_locked(request, obj):
            original = CompatibilityMatrix.objects.get(pk=obj.pk)
            for field_name in self.RULE_FIELDS:
                setattr(obj, field_name, getattr(original, field_name))
        super().save_model(request, obj, form, change)

    def get_target_params_json(self, request):
        """Returns JSON mapping of TargetParameter ID -> Values list"""
        data = {}
        for param in filter_queryset_for_user(request.user, TargetParameter.objects.all()):
            data[param.id] = param.values
        return json.dumps(data)
    
    def get_changeform_initial_data(self, request):
        """Default new rules to Unlocked so they can be edited immediately"""
        return {'is_locked': False}

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['target_params_json'] = self.get_target_params_json(request)
        return super().add_view(request, form_url, extra_context=extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['target_params_json'] = self.get_target_params_json(request)
        return super().change_view(request, object_id, form_url, extra_context=extra_context)





from .models import GlobalVariable, TrackerConfig
from .widgets import TrackerConfigWidget

@admin.register(GlobalVariable)
class GlobalVariableAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
    # inlines = [] # Removed

    class Media:
        js = ('metadata/js/global_variable_admin.js',)

@admin.register(TrackerConfig)
class TrackerConfigAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('tracker', 'updated_at')
    search_fields = ('tracker__name',)
    LOCKED_CONTENT_FIELDS = ('tracker', 'mapping')
    LOCKED_DISPLAY_FIELDS = {
        'mapping': 'mapping_display',
    }
    LOCKED_JSON_FIELD = 'mapping'

    formfield_overrides = {
        models.JSONField: {'widget': TrackerConfigWidget},
    }

    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',)
        }
        js = ('metadata/js/tracker_config.js',)

    def _content_fields_locked(self, request, obj):
        if obj is None:
            return False
        if request.method == 'POST':
            if not request.POST.get('is_locked'):
                if request.POST.get(self.LOCKED_JSON_FIELD) is None:
                    return True
            return bool(request.POST.get('is_locked'))
        return obj.is_locked

    def _replace_locked_display_fields(self, fields):
        if isinstance(fields, (tuple, list)):
            replaced = [self._replace_locked_display_fields(field) for field in fields]
            return tuple(replaced) if isinstance(fields, tuple) else replaced
        if isinstance(fields, str) and fields in self.LOCKED_DISPLAY_FIELDS:
            return self.LOCKED_DISPLAY_FIELDS[fields]
        return fields

    def mapping_display(self, obj):
        if obj is None:
            return '-'
        widget = TrackerConfigWidget()
        return widget.render('mapping_display', obj.mapping, attrs={'disabled': True})

    mapping_display.short_description = TrackerConfig._meta.get_field('mapping').verbose_name

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and self._content_fields_locked(request, obj):
            if 'tracker' not in readonly:
                readonly.append('tracker')
            display_field = self.LOCKED_DISPLAY_FIELDS['mapping']
            if display_field not in readonly:
                readonly.append(display_field)
        return readonly

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if obj and self._content_fields_locked(request, obj):
            for field_name in self.LOCKED_DISPLAY_FIELDS:
                if field_name not in exclude:
                    exclude.append(field_name)
        return exclude

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not (obj and self._content_fields_locked(request, obj)):
            return fieldsets

        rebuilt = []
        for title, options in fieldsets:
            copied = dict(options)
            copied['fields'] = self._replace_locked_display_fields(copied.get('fields', ()))
            rebuilt.append((title, copied))
        return rebuilt

    def save_model(self, request, obj, form, change):
        if change:
            original = TrackerConfig.objects.get(pk=obj.pk)
            if self._content_fields_locked(request, obj):
                for field_name in self.LOCKED_CONTENT_FIELDS:
                    setattr(obj, field_name, getattr(original, field_name))
                if request.method == 'POST' and not request.POST.get('is_locked'):
                    obj.is_locked = False
            elif not request.POST.get('is_locked'):
                for field_name in self.LOCKED_CONTENT_FIELDS:
                    setattr(obj, field_name, getattr(original, field_name))
                obj.is_locked = False
        super().save_model(request, obj, form, change)
        if change and not request.POST.get('is_locked') and request.POST.get('mapping') is not None:
            TrackerConfig.objects.filter(pk=obj.pk).update(is_locked=True)
            obj.is_locked = True

