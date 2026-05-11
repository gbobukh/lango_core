class AccessControlAdminMixin:
    filter_horizontal = ('visible_to',)

    class Media:
        js = ('integrations/js/move_access_control.js',)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            fieldsets = list(fieldsets)
            fieldsets.append(
                (
                    'Access Control',
                    {
                        'fields': ('visible_to',),
                        'classes': ('collapse', 'access-control-fieldset'),
                    },
                )
            )
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
