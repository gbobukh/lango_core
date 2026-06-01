"""
URL configuration for lango_core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.admin.sites import AdminSite

admin.site.site_header = "Lango Core"
admin.site.site_title = "Lango Core"
admin.site.index_title = "Welcome to Lango Core"

# Monkey patch AdminSite.get_app_list to reorder Service Builder models
# Desired order: Endpoints, Methods, Scenarios, Business Actions, Workflows
# We patch the CLASS to ensure all instances are affected.
original_get_app_list = AdminSite.get_app_list

def get_app_list(self, request, app_label=None):
    app_list = original_get_app_list(self, request, app_label)
    
    # Define custom order for Service Builder
    desired_order = [
        'ServiceEndpoint',
        'ServiceMethod',
        'Scenario',
        'BusinessAction',
        'Workflow'
    ]
    
    for app in app_list:
        if app['app_label'] == 'service_builder':
            # Create a dict for fast lookup and sort
            models = app['models']
            models.sort(key=lambda x: desired_order.index(x['object_name']) if x['object_name'] in desired_order else 99)
            
    return app_list

# Bind the method to the AdminSite class
AdminSite.get_app_list = get_app_list

from django.conf import settings
from django.conf.urls.static import static

from django.views.generic import RedirectView
from service_builder.api import ModelChoicesAPIView

urlpatterns = [
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    path('admin/service_builder/api/model-choices/<str:app_label>/<str:model_name>/',
         ModelChoicesAPIView.as_view(), name='service_builder_model_choices_api'),
    path('admin/', admin.site.urls),
    path('integrations/', include('integrations.urls')),
    path('metadata/', include('metadata.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
