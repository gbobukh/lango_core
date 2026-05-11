from django.contrib import admin
from django.urls import path
from django.utils.html import format_html
from .models import ApiAuthType, Tracker, ApiAuthID, PartnerAccount, PartnerAccountType, PartnerAccountTrackerIdentifier, SystemConfig
from .forms import ApiAuthTypeForm, TrackerForm, ApiAuthIDForm, PartnerAccountForm, PartnerAccountTypeForm, PartnerAccountTrackerIdentifierForm, SystemConfigForm
from .views import TestApiAuthView
from .admin_access import AccessControlAdminMixin

@admin.register(ApiAuthType)
class ApiAuthTypeAdmin(admin.ModelAdmin):
    form = ApiAuthTypeForm
    list_display = ('name', 'get_key_definitions_str', 'created_at')
    search_fields = ('name',)
    list_filter = ('created_at',)
    filter_horizontal = ('visible_to',)  # Makes selecting users easier with a dual-pane widget
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': ('name', 'key_definitions', 'static_inject_in')
            }),
            ('Active Authentication (Optional)', {
                'fields': ('login_url', 'login_payload', 'token_path', 'inject_in', 'inject_key'),
                'description': 'Configure automatic token fetching. If set, this logic will run before any request using this auth type.',
                'classes': ('collapse',),
            }),
        ]
        if request.user.is_superuser:
            fieldsets.append(('Access Control', {
                'fields': ('visible_to',),
                'description': 'Select users who can view and use this authentication type.',
                'classes': ('collapse', 'access-control-fieldset'),
            }))
        return fieldsets

    class Media:
        js = ('integrations/js/move_access_control.js',)

    def get_key_definitions_str(self, obj):
        """Helper to display keys as a comma-separated string in the list view"""
        if not obj.key_definitions:
            return "-"
        return ", ".join(obj.key_definitions)
    get_key_definitions_str.short_description = "Required Keys"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visible_to=request.user).distinct()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:  # Only on creation
            obj.visible_to.add(request.user)


@admin.register(Tracker)
class TrackerAdmin(admin.ModelAdmin):
    form = TrackerForm
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    list_filter = ('created_at',)
    list_filter = ('created_at',)
    filter_horizontal = ('visible_to',)

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': ('name', 'api_configuration')
            }),
        ]
        if request.user.is_superuser:
            fieldsets.append(('Access Control', {
                'fields': ('visible_to',),
                'description': 'Select users who can view and use this tracker.',
                'classes': ('collapse', 'access-control-fieldset'),
            }))
        return fieldsets

    class Media:
        js = ('integrations/js/move_access_control.js',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visible_to=request.user).distinct()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:  # Only on creation
            obj.visible_to.add(request.user)


@admin.register(ApiAuthID)
class ApiAuthIDAdmin(admin.ModelAdmin):
    form = ApiAuthIDForm
    list_display = ('account_name', 'tracker', 'auth_type', 'request_url', 'created_at', 'run_test_link')
    search_fields = ('account_name', 'tracker__name', 'request_url')
    list_filter = ('tracker', 'auth_type', 'created_at')
    filter_horizontal = ('visible_to',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('test-auth/<int:auth_id>/', self.admin_site.admin_view(TestApiAuthView.as_view()), name='integrations_apiauthid_test_auth'),
        ]
        return custom_urls + urls

    def run_test_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:integrations_apiauthid_test_auth', args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank">Test Auth</a>', url)
    run_test_link.short_description = "Test"

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': ('account_name', 'tracker', 'request_url', 'auth_type', 'credentials_encrypted')
            }),
        ]
        if request.user.is_superuser:
            fieldsets.append(('Access Control', {
                'fields': ('visible_to',),
                'description': 'Select users who can view and use this authentication ID.',
                'classes': ('collapse', 'access-control-fieldset'),
            }))
        return fieldsets

    class Media:
        js = ('integrations/js/move_access_control.js',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visible_to=request.user).distinct()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:  # Only on creation
            obj.visible_to.add(request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "auth_type":
            if not request.user.is_superuser:
                kwargs["queryset"] = ApiAuthType.objects.filter(visible_to=request.user)
        if db_field.name == "tracker":
            if not request.user.is_superuser:
                kwargs["queryset"] = Tracker.objects.filter(visible_to=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PartnerAccountTrackerIdentifierInline(admin.TabularInline):
    model = PartnerAccountTrackerIdentifier
    form = PartnerAccountTrackerIdentifierForm
    extra = 1
    fields = ('api_auth_id', 'identifying_method', 'account_id_in_tracker', 'account_name_in_tracker')
    readonly_fields = ('account_name_in_tracker',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "api_auth_id":
            if not request.user.is_superuser:
                kwargs["queryset"] = ApiAuthID.objects.filter(visible_to=request.user)
        if db_field.name == "identifying_method":
            # Avoid circular import at module level if possible, or just import here
            from service_builder.models import ServiceMethod
            if not request.user.is_superuser:
                kwargs["queryset"] = ServiceMethod.objects.filter(visible_to=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PartnerAccount)
class PartnerAccountAdmin(admin.ModelAdmin):
    form = PartnerAccountForm
    list_display = ('name', 'account_type', 'domain', 'created_at')
    search_fields = ('name', 'account_type__name', 'domain')
    list_filter = ('account_type', 'created_at')
    filter_horizontal = ('visible_to',)
    inlines = [PartnerAccountTrackerIdentifierInline]

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': ('name', 'account_type', 'domain')
            }),
        ]
        if request.user.is_superuser:
            fieldsets.append(('Access Control', {
                'fields': ('visible_to',),
                'description': 'Select users who can view and use this partner account.',
                'classes': ('collapse', 'access-control-fieldset'),
            }))
        return fieldsets

    class Media:
        js = ('integrations/js/move_access_control.js',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visible_to=request.user).distinct()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:  # Only on creation
            obj.visible_to.add(request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "account_type":
            if not request.user.is_superuser:
                kwargs["queryset"] = PartnerAccountType.objects.filter(visible_to=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PartnerAccountType)
class PartnerAccountTypeAdmin(admin.ModelAdmin):
    form = PartnerAccountTypeForm
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    list_filter = ('created_at',)
    filter_horizontal = ('visible_to',)

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': ('name',)
            }),
        ]
        if request.user.is_superuser:
            fieldsets.append(('Access Control', {
                'fields': ('visible_to',),
                'description': 'Select users who can view and use this partner account type.',
                'classes': ('collapse', 'access-control-fieldset'),
            }))
        return fieldsets

    class Media:
        js = ('integrations/js/move_access_control.js',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visible_to=request.user).distinct()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:  # Only on creation
            obj.visible_to.add(request.user)

@admin.register(SystemConfig)
class SystemConfigAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    form = SystemConfigForm
    list_display = ('key', 'description', 'updated_at')
    search_fields = ('key', 'description')

