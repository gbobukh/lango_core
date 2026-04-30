from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views import View
from .models import ApiAuthType, ApiAuthID
from .utils import test_api_auth


@user_passes_test(lambda u: u.is_staff)
def get_auth_type_keys(request, type_id):
    """
    Returns the key definitions for a specific ApiAuthType.
    Used by the Admin UI to dynamically render input fields.
    """
    try:
        auth_type = ApiAuthType.objects.get(pk=type_id)
        return JsonResponse({
            'keys': auth_type.key_definitions
        })
    except ApiAuthType.DoesNotExist:
        return JsonResponse({'error': 'Auth Type not found'}, status=404)


@method_decorator(staff_member_required, name='dispatch')
class TestApiAuthView(View):
    """Test API Auth ID - runs login/credentials check and shows result."""

    def get(self, request, auth_id):
        auth_obj = get_object_or_404(ApiAuthID, pk=auth_id)
        result = test_api_auth(auth_obj)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('json'):
            return JsonResponse(result)
        return render(request, 'admin/integrations/test_auth.html', {'result': result})

    def post(self, request, auth_id):
        auth_obj = get_object_or_404(ApiAuthID, pk=auth_id)
        result = test_api_auth(auth_obj)
        return JsonResponse(result)
