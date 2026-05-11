def _fieldsets_without_field(fieldsets, field_name):
    """Drop a field from admin fieldsets, including nested row tuples."""
    cleaned = []

    for title, options in fieldsets:
        opts = dict(options)
        fields = opts.get('fields')
        if fields is not None:
            stripped = []
            for item in fields:
                if isinstance(item, (list, tuple)):
                    row = tuple(name for name in item if name != field_name)
                    if row:
                        stripped.append(row)
                elif item != field_name:
                    stripped.append(item)
            if not stripped:
                continue
            opts['fields'] = stripped
        cleaned.append((title, opts))

    return cleaned


class AccessControlAdminMixin:
    filter_horizontal = ('visible_to',)

    class Media:
        js = ('integrations/js/move_access_control.js',)

    def get_fieldsets(self, request, obj=None):
        fieldsets = _fieldsets_without_field(
            super().get_fieldsets(request, obj),
            'visible_to',
        )
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
