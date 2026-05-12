def model_has_visible_to(model):
    return hasattr(model, 'visible_to') and hasattr(model.visible_to, 'field')


def filter_queryset_for_user(user, queryset):
    if user.is_superuser:
        return queryset
    if not model_has_visible_to(queryset.model):
        return queryset
    return queryset.filter(visible_to=user).distinct()


def user_can_access_obj(user, obj):
    if user.is_superuser:
        return True
    if obj is None:
        return False
    if not model_has_visible_to(obj.__class__):
        return True
    return obj.visible_to.filter(pk=user.pk).exists()
