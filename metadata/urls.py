from django.urls import path
from .views import GlobalVariableListView

urlpatterns = [
    path('api/global-variables/', GlobalVariableListView.as_view(), name='global_variables_list'),
]
