from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import GlobalVariable

class GlobalVariableListView(LoginRequiredMixin, View):
    def get(self, request):
        variables = list(GlobalVariable.objects.values_list('name', flat=True))
        return JsonResponse({'variables': variables})
