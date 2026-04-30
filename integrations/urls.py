from django.urls import path
from . import views

urlpatterns = [
    path('api/auth-type-keys/<int:type_id>/', views.get_auth_type_keys, name='get_auth_type_keys'),
]
