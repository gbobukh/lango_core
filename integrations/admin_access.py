from .access_control import filter_queryset_for_user, model_has_visible_to


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


class VisibleToAdminMixin:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        related_model = db_field.remote_field.model
        if model_has_visible_to(related_model) and not request.user.is_superuser:
            base_qs = kwargs.get('queryset', related_model.objects.all())
            kwargs['queryset'] = filter_queryset_for_user(request.user, base_qs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_search_results(self, request, queryset, search_term):
        queryset = filter_queryset_for_user(request.user, queryset)
        return super().get_search_results(request, queryset, search_term)


class VisibleToInlineMixin:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        related_model = db_field.remote_field.model
        if model_has_visible_to(related_model) and not request.user.is_superuser:
            base_qs = kwargs.get('queryset', related_model.objects.all())
            kwargs['queryset'] = filter_queryset_for_user(request.user, base_qs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class AccessControlAdminMixin(VisibleToAdminMixin):
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
        return filter_queryset_for_user(request.user, super().get_queryset(request))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            obj.visible_to.add(request.user)
