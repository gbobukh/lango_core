from django.http import JsonResponse
from django.views import View
from django.apps import apps
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.db import models
from django.db.models import Q

class ModelDiscoveryView(PermissionRequiredMixin, View):
    permission_required = 'service_builder.view_scenario'  # Basic permission

    def get(self, request):
        """
        Returns a list of allowed models for Typed Arguments.
        Currently restricts to 'integrations' app and 'auth.User' for safety.
        """
        allowed_apps = ['integrations', 'metadata']
        allowed_models = []

        # Add specific models from other apps if needed
        # allowed_models.append({
        #     'app_label': 'auth',
        #     'model_name': 'user',
        #     'verbose_name': 'User'
        # })

        for app_label in allowed_apps:
            app_config = apps.get_app_config(app_label)
            for model in app_config.get_models():
                allowed_models.append({
                    'app_label': app_label,
                    'model_name': model._meta.model_name,
                    'verbose_name': model._meta.verbose_name.title(),
                    'full_name': f"{app_label}.{model._meta.model_name}"
                })
        
        # Sort by verbose name
        allowed_models.sort(key=lambda x: x['verbose_name'])
        
        return JsonResponse({'models': allowed_models})

class ModelFieldsView(PermissionRequiredMixin, View):
    permission_required = 'service_builder.view_scenario'

    def get(self, request, app_label, model_name):
        """
        Returns a list of fields for the specified model that can be used for lookup.
        Filters for CharField, IntegerField, UUIDField, etc. (unique identifiers).
        """
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            return JsonResponse({'error': 'Model not found'}, status=404)

        fields = []
        for field in model._meta.get_fields():
            # We only want fields that can be used to identify the object (Lookup fields)
            # Typically these are unique or indexed fields, but for flexibility we allow most scalar fields.
            # We exclude relations for now as lookup keys (too complex for V1).
            
            if isinstance(field, (models.CharField, models.IntegerField, models.UUIDField, models.AutoField, models.SlugField, models.JSONField)):
                fields.append({
                    'name': field.name,
                    'verbose_name': field.verbose_name.title() if hasattr(field, 'verbose_name') else field.name,
                    'type': field.get_internal_type(),
                    'is_unique': getattr(field, 'unique', False) or getattr(field, 'primary_key', False)
                })
        
        if hasattr(model, 'publisher_name'):
             fields.append({
                 'name': 'partner_account__name',
                 'verbose_name': 'Publisher Name',
                 'type': 'string',
                 'is_unique': True  # Known to be unique (PartnerAccount.name)
             })
        
        # Sort by name, but put 'id' and 'name' first if they exist
        fields.sort(key=lambda x: x['name'])
        
        # Prioritize common lookup fields
        priority = ['id', 'name', 'uuid', 'slug']
        sorted_fields = []
        seen = set()
        
        for p in priority:
            for f in fields:
                if f['name'] == p:
                    sorted_fields.append(f)
                    seen.add(f['name'])
        
        for f in fields:
            if f['name'] not in seen:
                sorted_fields.append(f)
                
        # ---------------------------------------------------
        # REVERTED: Related fields logic removed.
        # Use Helper Functions (get_partner_tracker_identifiers) instead.
        # ---------------------------------------------------

        return JsonResponse({'fields': sorted_fields})


class ModelChoicesView(PermissionRequiredMixin, View):
    permission_required = 'service_builder.view_scenario'

    def get(self, request, app_label, model_name):
        """
        Returns choices for model instances: [{ value: pk, label: str }, ...].
        Used for model-type argument dropdowns on Run Tests page.
        """
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            return JsonResponse({'error': 'Model not found'}, status=404)

        qs = model.objects.all().order_by('id')
        # Filter by visible_to for models that have it (e.g. PartnerAccount)
        if hasattr(model, 'visible_to') and hasattr(model.visible_to, 'field') and not request.user.is_superuser:
            try:
                qs = qs.filter(Q(visible_to=request.user) | Q(visible_to__isnull=True)).distinct()
            except Exception:
                qs = qs.filter(visible_to=request.user).distinct()

        choices = []
        for obj in qs:
            choices.append({'value': str(obj.pk), 'label': str(obj)})
        return JsonResponse({'choices': choices})


@method_decorator(staff_member_required, name='dispatch')
class ModelChoicesAPIView(View):
    """Standalone API for model choices — requires staff only (no view_scenario)."""
    def get(self, request, app_label, model_name):
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            return JsonResponse({'error': 'Model not found'}, status=404)

        qs = model.objects.all().order_by('id')
        if hasattr(model, 'visible_to') and hasattr(model.visible_to, 'field') and not request.user.is_superuser:
            try:
                qs = qs.filter(Q(visible_to=request.user) | Q(visible_to__isnull=True)).distinct()
            except Exception:
                qs = qs.filter(visible_to=request.user).distinct()

        choices = [{'value': str(obj.pk), 'label': str(obj)} for obj in qs]
        return JsonResponse({'choices': choices})
