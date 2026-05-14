from django import forms
from django.contrib import admin
from django.contrib import messages
from django.db import models
from django.db import transaction
import json
from .models import (
    ActionConfigLibrary,
    BusinessAction,
    BusinessActionVariant,
    Scenario,
    ScenarioStep,
    ServiceEndpoint,
    ServiceMethod,
    Workflow,
    WorkflowStep,
)
from .forms import ActionConfigLibraryForm, ServiceEndpointForm, ServiceMethodForm, BusinessActionForm



from .widgets import ApiBatchConfigWidget, ArgumentMappingWidget, PrettyJSONWidget
from integrations.models import Tracker
from integrations.admin_access import AccessControlAdminMixin, VisibleToAdminMixin, VisibleToInlineMixin
from integrations.access_control import filter_queryset_for_user
from integrations.widgets import KeyDefinitionsWidget

from django.urls import path
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils.text import capfirst
from django.contrib.admin import helpers as admin_helpers
from django.contrib.admin.utils import NestedObjects, flatten_fieldsets
from .views import TestEndpointView, GetMethodArgumentsView, GetMethodsListView, GetScenarioArgumentsView, GetScenarioDetailsView, ResolveActionVariantView, GetBusinessActionArgumentsView
from .api import ModelChoicesView

@admin.action(description='Duplicate selected objects')
@admin.action(description='Duplicate selected objects')
def duplicate_object(modeladmin, request, queryset):
    for obj in queryset:
        # Pre-fetch related objects before clearing PK
        related_items = []
        
        # Handle Scenarios and Workflows (both have 'steps' relative name)
        if hasattr(obj, 'steps'):
            related_items = list(obj.steps.all())
        # Handle BusinessActions
        elif hasattr(obj, 'variants'):
            related_items = list(obj.variants.all())
            
        # Duplicate Parent
        obj.pk = None
        obj.name = f"{obj.name} (Copy)"
        obj.validation_status = 'PENDING'
        
        # Handle Unique Code for BusinessAction
        if hasattr(obj, 'code'):
            import uuid
            # Append short random string to avoid collision if repeated copies
            suffix = str(uuid.uuid4())[:8]
            obj.code = f"{obj.code}_copy_{suffix}"
            
        obj.save()
        
        # Duplicate Children
        for item in related_items:
            item.pk = None
            # Re-link to new parent
            if hasattr(item, 'scenario_id') and hasattr(obj, 'steps') and obj._meta.model_name == 'scenario':
                item.scenario = obj
            elif hasattr(item, 'workflow_id') and hasattr(obj, 'steps') and obj._meta.model_name == 'workflow':
                item.workflow = obj
            elif hasattr(item, 'business_action_id'):
                item.business_action = obj
            item.save()

@admin.action(description='Set Valid for selected tree')
def mark_valid(modeladmin, request, queryset):
    visited = set()
    changed_by_model = {}
    skipped_already_valid = 0

    def mark_object_valid(obj):
        nonlocal skipped_already_valid
        if not obj or not getattr(obj, 'pk', None):
            return
        key = (obj._meta.label, obj.pk)
        if key in visited:
            return
        visited.add(key)

        if hasattr(obj, 'validation_status'):
            if obj.validation_status != 'VALID':
                obj.validation_status = 'VALID'
                obj.save(update_fields=['validation_status'])
                model_name = obj._meta.verbose_name.title()
                changed_by_model[model_name] = changed_by_model.get(model_name, 0) + 1
            else:
                skipped_already_valid += 1

        # Downstream propagation by object type.
        if isinstance(obj, Workflow):
            for step in obj.steps.select_related('business_action', 'scenario').all():
                if step.business_action_id:
                    mark_object_valid(step.business_action)
                if step.scenario_id:
                    mark_object_valid(step.scenario)
        elif isinstance(obj, BusinessAction):
            for variant in obj.variants.select_related('scenario').all():
                if variant.scenario_id:
                    mark_object_valid(variant.scenario)
        elif isinstance(obj, Scenario):
            for step in obj.steps.select_related('method').all():
                if step.method_id:
                    mark_object_valid(step.method)
        elif isinstance(obj, ServiceMethod):
            if obj.service_endpoint_id:
                mark_object_valid(obj.service_endpoint)

    with transaction.atomic():
        for root_obj in queryset:
            mark_object_valid(root_obj)

    total_changed = sum(changed_by_model.values())
    if total_changed:
        details = ', '.join(f"{name}: {count}" for name, count in sorted(changed_by_model.items()))
        extra = f" Skipped already VALID: {skipped_already_valid}." if skipped_already_valid else ""
        modeladmin.message_user(
            request,
            f"Marked as VALID with propagation. Updated {total_changed} object(s) ({details}).{extra}",
            level=messages.SUCCESS,
        )
    else:
        modeladmin.message_user(
            request,
            "No status changes were required (all reachable objects are already VALID).",
            level=messages.INFO,
        )

class LifecycleAdminMixin:
    actions = [duplicate_object, mark_valid]

    def get_lock_status(self, obj):
        is_locked = False
        if hasattr(obj, 'is_locked'):
            is_locked = obj.is_locked
        
        if is_locked:
            icon = '🔒'
            title = 'Locked'
            locked_attr = 'true'
        else:
            icon = '✏️'
            title = 'Edit'
            locked_attr = 'false'
            
        return format_html(
            '<span class="lock-status" data-locked="{}" title="{}">{}</span>',
            locked_attr, title, icon
        )
    get_lock_status.short_description = "LOCK"

    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',)
        }
        js = ('service_builder/js/admin_locking_v2.js',)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Always lock validation_status from manual edit in form (use actions)
        if 'validation_status' not in readonly:
            readonly.append('validation_status')
            
        if obj and hasattr(obj, 'is_locked') and obj.is_locked:
            # Lock all fields if entity is in use
            for field in [f.name for f in self.model._meta.fields]:
                if field not in readonly:
                    readonly.append(field)
            # Also lock m2m?
            # self.filter_horizontal...
        return readonly

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Filter dropdowns to only show Valid OR Test entities
        # Note: We must exclude the object itself if needed, but for FK it's fine.
        # We need to check if the related model has validation_status field.
        related_model = db_field.remote_field.model
        if hasattr(related_model, 'validation_status'):
             # Allow both VALID and TEST statuses
             kwargs["queryset"] = related_model.objects.filter(validation_status__in=['VALID', 'TEST'])
             
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class LifecycleInlineMixin:
    def has_add_permission(self, request, obj=None):
        if obj and hasattr(obj, 'is_locked') and obj.is_locked:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and hasattr(obj, 'is_locked') and obj.is_locked:
            return False
        return super().has_delete_permission(request, obj)
    
    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)
        if obj and hasattr(obj, 'is_locked') and obj.is_locked:
            # Make all fields read-only
            # We must be careful with get_fields because it might return dynamic fields?
            # Standard way is to get all fields from model or self.fields.
            # Using self.model._meta.fields is safer for model inlines.
            all_fields = [f.name for f in self.model._meta.fields]
            # Also need to handle fields declared in readonly_fields that are NOT in model?
            return list(set(list(readonly) + all_fields))
        return readonly


@admin.register(ServiceEndpoint)
class ServiceEndpointAdmin(LifecycleAdminMixin, VisibleToAdminMixin, admin.ModelAdmin):
    form = ServiceEndpointForm
    list_display = ('name', 'tracker', 'method', 'endpoint', 'validation_status', 'created_at', 'get_lock_status')
    search_fields = ('name', 'endpoint', 'tracker__name')
    list_filter = ('validation_status', 'tracker', 'method', 'created_at')
    filter_horizontal = ('visible_to',)
    readonly_fields = ('endpoint',)

    # Use the KeyDefinitionsWidget for parameters
    formfield_overrides = {
        models.JSONField: {'widget': KeyDefinitionsWidget},
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Override widget for api_configuration back to standard Textarea/JSON
        if db_field.name == 'api_configuration':
             # from django.contrib.postgres.forms import JSONField
             from django.forms import Textarea
             kwargs['widget'] = Textarea(attrs={'rows': 5, 'cols': 80, 'style': 'font-family:monospace;'})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_lock_status(self, obj):
        is_locked = False
        if hasattr(obj, 'is_locked'):
            is_locked = obj.is_locked
        
        if is_locked:
            icon = '🔒'
            title = 'Locked'
            locked_attr = 'true'
        else:
            icon = '✏️'
            title = 'Edit'
            locked_attr = 'false'
            
        return format_html(
            '<span class="lock-status" data-locked="{}" title="{}">{}</span>',
            locked_attr, title, icon
        )
    get_lock_status.short_description = "LOCK"


    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
             path('run-tests/', self.admin_site.admin_view(TestEndpointView.as_view()), name='service_builder_run_tests'),
             path('execute-test/', self.admin_site.admin_view(TestEndpointView.as_view()), name='service_builder_action_execute_test'),
             path('api/models/<str:app_label>/<str:model_name>/choices/', self.admin_site.admin_view(ModelChoicesView.as_view()), name='service_builder_model_choices'),
        ]
        return custom_urls + urls

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': ('tracker', 'name', 'method', 'api_configuration')
            }),
            ('URL Configuration', {
                'fields': ('resource_path', 'parameters', 'endpoint'),
                'description': "Enter the Base Path and Parameters. The 'Endpoint' field will be auto-generated."
            }),
            ('Current Validation', {
                 'fields': ('validation_status', 'mark_as_test')
            })
        ]
        if request.user.is_superuser:
            fieldsets.append(('Access Control', {
                'fields': ('visible_to',),
                'description': 'Select users who can view and use this endpoint.',
                'classes': ('collapse', 'access-control-fieldset'),
            }))
        return fieldsets

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visible_to=request.user).distinct()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            obj.visible_to.add(request.user)

    class Media:
        js = ('integrations/js/move_access_control.js',)

@admin.register(ServiceMethod)
class ServiceMethodAdmin(LifecycleAdminMixin, VisibleToAdminMixin, admin.ModelAdmin):
    form = ServiceMethodForm
    list_display = ('name', 'service_endpoint', 'return_key', 'validation_status', 'created_at', 'run_test_link', 'get_lock_status')
    search_fields = ('name', 'service_endpoint__name')
    autocomplete_fields = ('service_endpoint',)

    def get_lock_status(self, obj):
        is_locked = False
        if hasattr(obj, 'is_locked'):
            is_locked = obj.is_locked
        
        if is_locked:
            icon = '🔒'
            title = 'Locked'
            locked_attr = 'true'
        else:
            icon = '✏️'
            title = 'Edit'
            locked_attr = 'false'
            
        return format_html(
            '<span class="lock-status" data-locked="{}" title="{}">{}</span>',
            locked_attr, title, icon
        )
    get_lock_status.short_description = "LOCK"

    list_filter = ('validation_status', 'service_endpoint__tracker', 'created_at')
    filter_horizontal = ('visible_to',)
    readonly_fields = ('arguments',)

    def run_test_link(self, obj):
        url = reverse('admin:service_builder_run_tests')
        return format_html('<a class="button" href="{}?method_id={}">Run Test</a>', url, obj.pk)
    run_test_link.short_description = "Actions"
    run_test_link.allow_tags = True

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': (
                    'service_endpoint',
                    'name',
                    'return_key',
                    'payload_fields',
                    'payload_value_types',
                    'arguments',
                    'validation_status',
                    'mark_as_test',
                )
            }),
        ]
        if request.user.is_superuser:
            fieldsets.append(('Access Control', {
                'fields': ('visible_to',),
                'description': 'Select users who can view and use this method.',
                'classes': ('collapse', 'access-control-fieldset'),
            }))
        return fieldsets

    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',)
        }
        js = (
            'service_builder/js/admin_locking_v2.js',
            'integrations/js/move_access_control.js',
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visible_to=request.user).distinct()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:  # Only on creation
            obj.visible_to.add(request.user)

    def get_deleted_objects(self, objs, request):
        """Add parent entity name to protected objects (e.g. Scenario for ScenarioStep)."""
        deleted, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)

        if not protected:
            return deleted, model_count, perms_needed, protected

        try:
            obj = objs[0]
        except IndexError:
            return deleted, model_count, perms_needed, protected

        from django.db import router
        using = router.db_for_write(obj._meta.model)
        collector = NestedObjects(using=using, origin=objs)
        collector.collect(objs)

        result = []
        for p in collector.protected:
            base = f"{capfirst(p._meta.verbose_name)}: {p}"
            parent_info = ""
            if hasattr(p, 'scenario') and p.scenario_id:
                parent_info = f" (in Scenario: {p.scenario})"
            elif hasattr(p, 'workflow') and p.workflow_id:
                parent_info = f" (in Workflow: {p.workflow})"
            elif hasattr(p, 'business_action') and p.business_action_id:
                parent_info = f" (in Business Action: {p.business_action})"
            result.append(base + parent_info)

        return deleted, model_count, perms_needed, result


from .models import Scenario, ScenarioStep
from .forms import ScenarioForm, ScenarioStepForm, effective_scenario_step_for_form

from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
import json

class ScenarioStepFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        # Get parent Scenario arguments from POST data
        # Note: self.data is the QueryDict. The parent field is 'arguments'.
        # We need to handle the case where 'arguments' might be missing or invalid JSON.
        arguments_json = self.data.get('arguments', '[]')
        try:
            scenario_args = json.loads(arguments_json)
            if not isinstance(scenario_args, list):
                scenario_args = []
        except json.JSONDecodeError:
            scenario_args = []
            
        # Extract argument names for validation
        arg_names = []
        for arg in scenario_args:
            if isinstance(arg, dict):
                arg_names.append(arg.get('name'))
            else:
                arg_names.append(arg)
                
        context_vars = set(arg_names)
        unused_args = set(arg_names)
        
        # Iterate over forms (steps)
        # self.forms contains all forms, including empty ones and those marked for deletion.
        # We need to sort them by order if possible, but they might not be sorted in the formset list.
        # However, for context validation, order matters!
        # The forms in self.forms are usually in the order they appear on the page.
        # If the user reordered them via drag-and-drop (if supported) or changed 'order' field...
        # We should rely on the 'order' field in cleaned_data.
        
        valid_forms = []
        for form in self.forms:
            if not form.is_valid():
                continue
            if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                valid_forms.append(form)
                
        # Sort by 'order' field
        valid_forms.sort(key=lambda f: f.cleaned_data.get('order', 0))
        
        # Re-iterate for correct validation order
        # We need to rebuild context step by step to validate correctly.
        # The previous loop was doing it, but I added output_var too early for the current step's modification check?
        # Actually, modification uses context vars to inject INTO response.
        # So yes, the var must exist.
        
        # Let's rewrite the loop slightly to be cleaner.
        context_vars = set(arg_names)
        unused_args = set(arg_names)
        
        # Validation has been moved to save_formset to allow saving invalid scenarios (with a warning).
        # We only do implicit mapping here.
        
        for i, form in enumerate(valid_forms):
            method = form.cleaned_data.get('method')
            mapping = form.cleaned_data.get('argument_mapping') or {}
            
            if not method:
                continue



            # Auto-mapping (Implicit)
            mapping_updated = False
            for arg in method.arguments:
                if arg not in mapping:
                    if arg in context_vars:
                        mapping[arg] = f"{{{{ {arg} }}}}"
                        mapping_updated = True
            
            if mapping_updated:
                form.cleaned_data['argument_mapping'] = mapping
                form.instance.argument_mapping = mapping
            
            # Update context for implicit mapping of subsequent steps
            # (We need to simulate context build-up even without validation to support implicit mapping correctly)
            output_var = form.cleaned_data.get('output_variable_name')
            if output_var:
                context_vars.add(output_var)

class ScenarioStepInline(LifecycleInlineMixin, VisibleToInlineMixin, admin.StackedInline):
    model = ScenarioStep
    form = ScenarioStepForm
    formset = ScenarioStepFormSet
    extra = 0
    template = 'admin/edit_inline/scenario_step_stacked.html'
    autocomplete_fields = ('method',)
    # Group fields: Top row (Order, Method, Output), Bottom row (Mappings)
    fieldsets = (
        (None, {
            'fields': (
                ('is_active', 'order', 'step_type'),
                'method', 
                ('iterator_variable', 'auth_context_variable'),
                'action_type',
                'argument_mapping', 
                'action_config',
                ('output_variable_name', 'response_modification'),
                'error_handlers',
                'context_extraction',
                ('success_condition', 'condition_error_message'),
            )
        }),
    )
    
    class Media:
        js = (
            'service_builder/js/argument_mapping_v14.js',
            'service_builder/js/context_help.js',
            'service_builder/js/scenario_step_polymorphic_v11.js',
        )

    LOCKED_JSON_FIELDS = {
        'action_config': 'action_config_pretty',
        'response_modification': 'response_modification_pretty',
        'error_handlers': 'error_handlers_pretty',
        'context_extraction': 'context_extraction_pretty',
    }

    def _replace_locked_json_fields(self, fields):
        if isinstance(fields, (tuple, list)):
            replaced = [self._replace_locked_json_fields(f) for f in fields]
            return tuple(replaced) if isinstance(fields, tuple) else replaced
        if isinstance(fields, str) and fields in self.LOCKED_JSON_FIELDS:
            return self.LOCKED_JSON_FIELDS[fields]
        return fields

    def _pretty_json_for_field(self, obj, field_name):
        value = getattr(obj, field_name, None)
        if value in (None, ''):
            return "-"

        if isinstance(value, str):
            raw = value.strip()
            if raw and raw[0] in '{[':
                try:
                    value = json.loads(raw)
                except (ValueError, TypeError):
                    pass

        if isinstance(value, (dict, list)):
            text = json.dumps(value, indent=2, ensure_ascii=False)
        else:
            text = str(value)

        return format_html(
            '<pre style="white-space: pre-wrap; max-height: 260px; overflow: auto; margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \'Liberation Mono\', \'Courier New\', monospace;">{}</pre>',
            text,
        )

    def action_config_pretty(self, obj):
        return self._pretty_json_for_field(obj, 'action_config')
    action_config_pretty.short_description = "Action config"

    def response_modification_pretty(self, obj):
        return self._pretty_json_for_field(obj, 'response_modification')
    response_modification_pretty.short_description = "Response injection"

    def error_handlers_pretty(self, obj):
        return self._pretty_json_for_field(obj, 'error_handlers')
    error_handlers_pretty.short_description = "Error handlers"

    def context_extraction_pretty(self, obj):
        return self._pretty_json_for_field(obj, 'context_extraction')
    context_extraction_pretty.short_description = "Context extraction"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and hasattr(obj, 'is_locked') and obj.is_locked:
            for original, pretty in self.LOCKED_JSON_FIELDS.items():
                # Keep original model fields readonly to avoid form/save regressions.
                # We only swap display fields in fieldsets (to *_pretty) for readability.
                if pretty not in readonly:
                    readonly.append(pretty)
        return readonly

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not (obj and hasattr(obj, 'is_locked') and obj.is_locked):
            return fieldsets

        rebuilt = []
        for title, opts in fieldsets:
            copied = dict(opts)
            copied['fields'] = self._replace_locked_json_fields(copied.get('fields', ()))
            rebuilt.append((title, copied))
        return rebuilt

    # Scenario step widgets: only fields present on the form (see LOCKED_JSON_FIELDS swap) get customized.
    ACTION_CONFIG_WIDGET_ATTRS = {'rows': 10, 'style': 'font-family: monospace; width: 100%;'}
    ERROR_HANDLERS_WIDGET_ATTRS = {
        'rows': 8,
        'style': 'font-family: monospace; width: 100%;',
        'placeholder': '[{"status_codes": [404], "body_match": {"error.code": "NotFoundError"}, "action": "skip"}]',
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        name = db_field.name
        if name == 'argument_mapping':
            kwargs['widget'] = ArgumentMappingWidget()
        elif name == 'action_config':
            kwargs['widget'] = ApiBatchConfigWidget(attrs=dict(self.ACTION_CONFIG_WIDGET_ATTRS))
        elif name == 'error_handlers':
            kwargs['widget'] = PrettyJSONWidget(attrs=dict(self.ERROR_HANDLERS_WIDGET_ATTRS))
        elif name == 'response_modification':
            kwargs['widget'] = forms.Textarea(
                attrs={'rows': 3, 'placeholder': '{"json_path": "context_var"}'}
            )
        elif name == 'context_extraction':
            kwargs['widget'] = forms.Textarea(
                attrs={'rows': 3, 'placeholder': '{"var_name": "expression"}'}
            )
        elif name == 'success_condition':
            kwargs['widget'] = forms.Textarea(
                attrs={'rows': 2, 'placeholder': "result['status'] == 'success'"}
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "method":
            qs = ServiceMethod.objects.filter(validation_status__in=['VALID', 'TEST'])
            kwargs["queryset"] = filter_queryset_for_user(request.user, qs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


def _scenario_step_fieldsets_for_step_type(fieldsets, step_type):
    """Drop field rows not allowed for ``step_type`` (locked *_pretty mapped to logical field)."""
    from .scenario_step_contracts import SCENARIO_STEP_FORM_FIELDS_BY_TYPE

    allowed = SCENARIO_STEP_FORM_FIELDS_BY_TYPE.get(step_type)
    if allowed is None:
        allowed = SCENARIO_STEP_FORM_FIELDS_BY_TYPE['API_CALL']
    pretty_inv = {v: k for k, v in ScenarioStepInline.LOCKED_JSON_FIELDS.items()}

    def logical_allowed(name):
        logical = pretty_inv.get(name, name)
        return logical in allowed

    def filter_slot(slot):
        if isinstance(slot, (list, tuple)):
            kept = tuple(f for f in slot if logical_allowed(f))
            if not kept:
                return None
            if len(kept) == 1:
                return kept[0]
            return kept
        if logical_allowed(slot):
            return slot
        return None

    rebuilt = []
    for title, opts in fieldsets:
        raw_fields = opts.get('fields', ())
        next_fields = []
        for slot in raw_fields:
            filtered = filter_slot(slot)
            if filtered is not None:
                next_fields.append(filtered)
        if next_fields:
            new_opts = dict(opts)
            new_opts['fields'] = tuple(next_fields)
            rebuilt.append((title, new_opts))
    return rebuilt


class ScenarioStepInlineAdminFormSet(admin_helpers.InlineAdminFormSet):
    """Per-row fieldsets filtered by ScenarioStep.step_type while hidden fields preserve POST data."""

    def __iter__(self):
        if self.has_change_permission:
            readonly_for_editing = self.readonly_fields
        else:
            readonly_for_editing = tuple(self.readonly_fields) + tuple(
                flatten_fieldsets(self.fieldsets)
            )

        queryset = list(self.formset.get_queryset())
        for form, original in zip(self.formset.initial_forms, queryset):
            view_on_site_url = self.opts.get_view_on_site_url(original)
            st = effective_scenario_step_for_form(form)
            row_fieldsets = _scenario_step_fieldsets_for_step_type(self.fieldsets, st)
            yield admin_helpers.InlineAdminForm(
                self.formset,
                form,
                row_fieldsets,
                self.prepopulated_fields,
                original,
                readonly_for_editing,
                model_admin=self.opts,
                view_on_site_url=view_on_site_url,
            )

        for form in self.formset.extra_forms:
            st = effective_scenario_step_for_form(form)
            row_fieldsets = _scenario_step_fieldsets_for_step_type(self.fieldsets, st)
            yield admin_helpers.InlineAdminForm(
                self.formset,
                form,
                row_fieldsets,
                self.prepopulated_fields,
                None,
                self.readonly_fields,
                model_admin=self.opts,
                view_on_site_url=None,
            )

        if self.has_add_permission:
            empty = self.formset.empty_form
            st = effective_scenario_step_for_form(empty)
            row_fieldsets = _scenario_step_fieldsets_for_step_type(self.fieldsets, st)
            yield admin_helpers.InlineAdminForm(
                self.formset,
                empty,
                row_fieldsets,
                self.prepopulated_fields,
                None,
                self.readonly_fields,
                model_admin=self.opts,
                view_on_site_url=None,
            )


def _can_manage_action_config_library_access(request, model_admin, obj):
    """Show Access Control fieldset for anyone who may add or change a library entry (not superuser-only)."""
    if request.user.is_superuser:
        return True
    if obj is None:
        return model_admin.has_add_permission(request)
    return model_admin.has_change_permission(request, obj)


@admin.register(ActionConfigLibrary)
class ActionConfigLibraryAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    form = ActionConfigLibraryForm
    list_display = ('name', 'action_type', 'is_active', 'updated_at')
    list_filter = ('action_type', 'is_active')
    search_fields = ('name', 'description')
    ordering = ('action_type', 'name')
    filter_horizontal = ('visible_to',)

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (
                None,
                {
                    'fields': (
                        'name',
                        'description',
                        'action_type',
                        'action_config',
                        'is_active',
                    ),
                },
            ),
        ]
        if _can_manage_action_config_library_access(request, self, obj):
            fieldsets.append(
                (
                    'Access Control',
                    {
                        'fields': ('visible_to',),
                        'description': 'Users who can view and use this action config library entry in admin.',
                        'classes': ('collapse', 'access-control-fieldset'),
                    },
                )
            )
        return fieldsets

    class Media:
        js = ('integrations/js/move_access_control.js',)


@admin.register(Scenario)
class ScenarioAdmin(LifecycleAdminMixin, VisibleToAdminMixin, admin.ModelAdmin):
    LOCKED_CONTENT_FIELDS = ('name', 'arguments')
    def get_urls(self):
        urls = super().get_urls()
        from .api import ModelDiscoveryView, ModelFieldsView, ModelChoicesView
        custom_urls = [
            path('api/method-arguments/<int:method_id>/', self.admin_site.admin_view(GetMethodArgumentsView.as_view()), name='service_builder_get_method_arguments'),
            path('api/methods/', self.admin_site.admin_view(GetMethodsListView.as_view()), name='service_builder_get_methods'),
            path('api/models/', self.admin_site.admin_view(ModelDiscoveryView.as_view()), name='service_builder_get_models'),
            path('api/models/<str:app_label>/<str:model_name>/fields/', self.admin_site.admin_view(ModelFieldsView.as_view()), name='service_builder_get_model_fields'),
            path('api/models/<str:app_label>/<str:model_name>/choices/', self.admin_site.admin_view(ModelChoicesView.as_view()), name='service_builder_get_model_choices'),
        ]
        return custom_urls + urls

    form = ScenarioForm
    list_display = ('name', 'validation_status', 'created_at', 'run_test_link', 'get_lock_status')
    search_fields = ('name',)

    def get_lock_status(self, obj):
        is_locked = False
        if hasattr(obj, 'is_locked'):
            is_locked = obj.is_locked
        
        if is_locked:
            icon = '🔒'
            title = 'Locked'
            locked_attr = 'true'
        else:
            icon = '✏️'
            title = 'Edit'
            locked_attr = 'false'
            
        return format_html(
            '<span class="lock-status" data-locked="{}" title="{}">{}</span>',
            locked_attr, title, icon
        )
    get_lock_status.short_description = "LOCK"

    list_filter = ('validation_status', 'created_at',)
    filter_horizontal = ('visible_to',)
    readonly_fields = ('validation_status',)
    inlines = [ScenarioStepInline]

    def run_test_link(self, obj):
        url = reverse('admin:service_builder_run_tests')
        return format_html('<a class="button" href="{}?scenario_id={}">Run Test</a>', url, obj.pk)
    run_test_link.short_description = "Actions"
    run_test_link.allow_tags = True

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': ('name', 'arguments', 'validation_status', 'mark_as_test')
            }),
        ]
        if request.user.is_superuser:
            fieldsets.append(('Access Control', {
                'fields': ('visible_to',),
                'description': 'Select users who can view and use this scenario.',
                'classes': ('collapse', 'access-control-fieldset'),
            }))
        return fieldsets

    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',)
        }
        js = (
            'service_builder/js/admin_locking_v2.js',
            'integrations/js/move_access_control.js',
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visible_to=request.user).distinct()

    def save_model(self, request, obj, form, change):
        if change and obj.is_locked:
            original = Scenario.objects.get(pk=obj.pk)
            for field_name in self.LOCKED_CONTENT_FIELDS:
                setattr(obj, field_name, getattr(original, field_name))
        super().save_model(request, obj, form, change)
        if not change:  # Only on creation
            obj.visible_to.add(request.user)
            
    def save_formset(self, request, form, formset, change):
        if change and form.instance.is_locked:
            formset.new_objects = []
            formset.changed_objects = []
            formset.deleted_objects = []
            return

        # Handle deletions manually because we use commit=False
        instances = formset.save(commit=False)
        
        for obj in formset.deleted_objects:
            obj.delete()
            
        for instance in instances:
            instance.save()
        formset.save_m2m()
        

        # Validation Logic (Non-blocking)
        scenario = form.instance
        # Ensure we have the latest status from save_model to avoid race conditions
        scenario.refresh_from_db()
        
        # Reset status to PENDING on any edit (unless Manual Test)
        if scenario.validation_status not in ('PENDING', 'TEST'):
            scenario.validation_status = 'PENDING'
            scenario.save(update_fields=['validation_status'])
        
        is_valid, warnings, unused_args = scenario.validate()
        # ... (lines 537-545 omitted in target context, but safe to assume typical flow)
        if warnings:
            self.message_user(request, f"Scenario saved. Warnings: {'; '.join(warnings)}", level='WARNING')
        elif unused_args:
            self.message_user(request, f"Scenario saved. Warning: Unused scenario arguments: {', '.join(unused_args)}", level='WARNING')
        else:
             pass

    def get_inline_formsets(self, request, formsets, inline_instances, obj=None):
        can_edit_parent = (
            self.has_change_permission(request, obj)
            if obj
            else self.has_add_permission(request)
        )
        inline_admin_formsets = []
        for inline, formset in zip(inline_instances, formsets):
            fieldsets = list(inline.get_fieldsets(request, obj))
            readonly = list(inline.get_readonly_fields(request, obj))
            if can_edit_parent:
                has_add_permission = inline.has_add_permission(request, obj)
                has_change_permission = inline.has_change_permission(request, obj)
                has_delete_permission = inline.has_delete_permission(request, obj)
            else:
                has_add_permission = has_change_permission = has_delete_permission = False
                formset.extra = formset.max_num = 0
            has_view_permission = inline.has_view_permission(request, obj)
            prepopulated = dict(inline.get_prepopulated_fields(request, obj))
            helper_cls = (
                ScenarioStepInlineAdminFormSet
                if isinstance(inline, ScenarioStepInline)
                else admin_helpers.InlineAdminFormSet
            )
            inline_admin_formsets.append(
                helper_cls(
                    inline,
                    formset,
                    fieldsets,
                    prepopulated,
                    readonly,
                    model_admin=self,
                    has_add_permission=has_add_permission,
                    has_change_permission=has_change_permission,
                    has_delete_permission=has_delete_permission,
                    has_view_permission=has_view_permission,
                )
            )
        return inline_admin_formsets

from .models import Workflow, WorkflowStep, BusinessAction, BusinessActionVariant
from .forms import ScenarioStepForm 

class WorkflowStepInline(LifecycleInlineMixin, VisibleToInlineMixin, admin.StackedInline):
    model = WorkflowStep
    extra = 0
    autocomplete_fields = ('business_action',)
    readonly_fields = ('get_step_inputs', 'get_step_outputs')
    fieldsets = (
        (None, {
            'fields': (
                ('is_active', 'order', 'business_action'),
                'tracker_from_argument',
                ('get_step_inputs', 'get_step_outputs'),
                'input_mapping',
            )
        }),
    )
    
    def get_step_inputs(self, obj):
        if obj.business_action and obj.business_action.arguments:
             args = [a.get('name', str(a)) + (f" ({a.get('type')})" if isinstance(a, dict) and a.get('type') else "") if isinstance(a, dict) else str(a) for a in obj.business_action.arguments]
             return f"{', '.join(args)}"
        return "-"
    get_step_inputs.short_description = "Required Inputs (Contract)"

    def get_step_outputs(self, obj):
        if obj.business_action and obj.business_action.output_variables:
             outputs = [o.get('name', str(o)) if isinstance(o, dict) else str(o) for o in obj.business_action.output_variables]
             return f"{', '.join(outputs)}"
        return "-"
    get_step_outputs.short_description = "Outputs (Contract)"
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'input_mapping':
            from .widgets import ArgumentMappingWidget
            kwargs['widget'] = ArgumentMappingWidget
        if db_field.name == 'tracker_from_argument':
            api_auth_names = []
            object_id = request.resolver_match.kwargs.get('object_id') if request.resolver_match else None
            if object_id:
                try:
                    workflow = Workflow.objects.get(pk=object_id)
                    api_auth_names = workflow.get_apiauthid_argument_names()
                except (Workflow.DoesNotExist, ValueError):
                    pass
            choices = [('', 'GENERAL')]
            if api_auth_names:
                choices.extend([(name, name) for name in api_auth_names])
            else:
                choices[0] = ('', 'GENERAL (no ApiAuthID argument — add one for tracker-specific variants)')
            kwargs['widget'] = forms.Select(choices=choices)
            kwargs['required'] = False
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "business_action":
            kwargs["queryset"] = BusinessAction.objects.filter(validation_status__in=['VALID', 'TEST'])
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    class Media:
        js = (
            'service_builder/js/argument_mapping_workflow_v9.js',
            'service_builder/js/context_help.js',
        )

from integrations.widgets import KeyDefinitionsWidget

@admin.register(Workflow)
class WorkflowAdmin(LifecycleAdminMixin, AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'validation_status', 'created_at', 'updated_at', 'run_test_link', 'get_lock_status')
    search_fields = ('name',)

    list_filter = ('validation_status',)
    inlines = [WorkflowStepInline]
    # Remove get_workflow_inputs from readonly (auto-discovery removed)
    readonly_fields = ('validation_status', 'get_workflow_outputs') 
    
    # Use TypedArgumentWidget for arguments (Rich UI)
    from .widgets import TypedArgumentWidget
    formfield_overrides = {
        models.JSONField: {'widget': TypedArgumentWidget},
    }

    fieldsets = (
        (None, {
            'fields': ('name', 'arguments', 'validation_status')
        }),
        ('Workflow Interface', {
            'fields': ('get_workflow_outputs',),
            'description': "Outputs are automatically derived from the Last active steps."
        }),
    )

    # get_workflow_inputs removed (replaced by manual arguments)

    def get_workflow_outputs(self, obj):
        last_step = obj.steps.filter(is_active=True).order_by('order').last()
        outputs = []
        if last_step:
            if last_step.output_variable_name:
                outputs.append(f"Context Variable: {last_step.output_variable_name}")
            if last_step.business_action and last_step.business_action.output_variables:
                action_outs = [o.get('name', str(o)) if isinstance(o, dict) else str(o) for o in last_step.business_action.output_variables]
                outputs.append(f"Action Outputs: {', '.join(action_outs)}")
        
        if outputs:
            return format_html_join(
                mark_safe('<br>'),
                '{}',
                ((o,) for o in outputs)
            )
        return "-"
    get_workflow_outputs.short_description = "Workflow Outputs (from Last Step)"

    def get_lock_status(self, obj):
        is_locked = False
        if hasattr(obj, 'is_locked'):
            is_locked = obj.is_locked
        
        if is_locked:
            icon = '🔒'
            title = 'Locked'
            locked_attr = 'true'
        else:
            icon = '✏️'
            title = 'Edit'
            locked_attr = 'false'
            
        return format_html(
            '<span class="lock-status" data-locked="{}" title="{}">{}</span>',
            locked_attr, title, icon
        )
    get_lock_status.short_description = "LOCK"
    
    def run_test_link(self, obj):
        url = reverse('admin:service_builder_run_tests')
        return format_html('<a class="button" href="{}?workflow_id={}">Run Test</a>', url, obj.pk)
    run_test_link.short_description = "Test"
    run_test_link.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path('api/scenario-arguments/<int:scenario_id>/', self.admin_site.admin_view(GetScenarioArgumentsView.as_view()), name='service_builder_get_scenario_arguments'),
            path('api/scenario-details/<int:scenario_id>/', self.admin_site.admin_view(GetScenarioDetailsView.as_view()), name='service_builder_get_scenario_details'),
            path('api/business-action-arguments/<int:action_id>/', self.admin_site.admin_view(GetBusinessActionArgumentsView.as_view()), name='service_builder_get_business_action_arguments'),
        ]
        return custom_urls + urls

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            instance.save()
        formset.save_m2m()
        
        # Reset Workflow Status to PENDING
        workflow = form.instance
        if workflow.pk and workflow.validation_status not in ('PENDING', 'TEST'):
             workflow.validation_status = 'PENDING'
             workflow.save(update_fields=['validation_status'])
    


    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',)
        }
        js = (
            'service_builder/js/admin_locking_v2.js',
            'integrations/js/move_access_control.js',
        )


class BusinessActionVariantInline(LifecycleInlineMixin, VisibleToInlineMixin, admin.StackedInline):
    model = BusinessActionVariant
    extra = 0
    fk_name = 'business_action'
    autocomplete_fields = ('tracker', 'scenario')
    
    # We use StackedInline for better space for mapping widgets
    fieldsets = (
        (None, {
            'fields': (
                ('tracker', 'scenario'),
                'input_mapping',
                'output_mapping'
            )
        }),
    )

    from .widgets import ArgumentMappingWidget
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in ['input_mapping', 'output_mapping']:
            kwargs['widget'] = ArgumentMappingWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "scenario":
            kwargs["queryset"] = db_field.remote_field.model.objects.filter(validation_status__in=['VALID', 'TEST'])
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',)
        }
        js = (
            'service_builder/js/variant_mapping_v7.js',
            'service_builder/js/admin_locking_v2.js', 
            'service_builder/js/business_action_inline.js'
        )

@admin.register(BusinessAction)
class BusinessActionAdmin(LifecycleAdminMixin, AccessControlAdminMixin, admin.ModelAdmin):
    form = BusinessActionForm
    list_display = ('name', 'validation_status', 'get_lock_status', 'run_test_link')
    search_fields = ('name',)
    list_display_links = ('name',)
    
    # Use TypedArgumentWidget for arguments (Rich UI)
    from .widgets import TypedArgumentWidget
    formfield_overrides = {
        models.JSONField: {'widget': TypedArgumentWidget},
    }
    
    fieldsets = (
        (None, {
            'fields': ('name', 'arguments', 'output_variables')
        }),
        ('Current Validation', {
             'fields': ('validation_status', 'mark_as_test')
        }),
    )
    readonly_fields = ('validation_status',)

    def run_test_link(self, obj):
        url = f"execute-test/?action_id={obj.pk}"
        return format_html('<a class="button" href="{}" target="_blank">Run Test</a>', url)
    run_test_link.short_description = "Test"

    def get_lock_status(self, obj):
        is_locked = False
        if hasattr(obj, 'is_locked'):
            is_locked = obj.is_locked
        
        if is_locked:
            icon = '🔒'
            title = 'Locked'
            locked_attr = 'true'
        else:
            icon = '✏️'
            title = 'Edit'
            locked_attr = 'false'
            
        return format_html(
            '<span class="lock-status" data-locked="{}" title="{}">{}</span>',
            locked_attr, title, icon
        )
    get_lock_status.short_description = "LOCK"

    list_filter = ('validation_status',)
    inlines = [BusinessActionVariantInline]
    
    class Media:
        css = {
            'all': ('service_builder/css/admin_locking_v2.css',)
        }
        js = (
            'service_builder/js/admin_locking_v2.js',
            'integrations/js/move_access_control.js',
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('api/scenario-details/<int:scenario_id>/', self.admin_site.admin_view(GetScenarioDetailsView.as_view()), name='service_builder_get_scenario_details_ba'),
            path('api/action-variant/', self.admin_site.admin_view(ResolveActionVariantView.as_view()), name='service_builder_resolve_action_variant'),
            path('execute-test/', self.admin_site.admin_view(TestEndpointView.as_view()), name='service_builder_action_execute_test'),
        ]
        return custom_urls + urls

