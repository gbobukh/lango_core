from django.contrib import admin
from django.urls import path

from integrations.admin_access import AccessControlAdminMixin
from .models import Frequency, ScheduledWorkflow
from .views import CrontabView, GetWorkflowArgumentsView, RunScheduledWorkflowView
from .widgets import ScheduledWorkflowArgumentMappingWidget


@admin.register(Frequency)
class FrequencyAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'interval_unit', 'interval_value', 'minute', 'hour', 'day_of_month', 'day_of_week', 'month')
    list_filter = ('interval_unit',)
    search_fields = ('name',)


@admin.register(ScheduledWorkflow)
class ScheduledWorkflowAdmin(AccessControlAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'workflow', 'frequency', 'get_arguments_summary', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('workflow__name',)
    change_list_template = 'admin/scheduler/scheduledworkflow/change_list.html'

    def get_arguments_summary(self, obj):
        return obj.get_arguments_summary()

    get_arguments_summary.short_description = 'Arguments'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('workflow')

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'default_arguments':
            kwargs['widget'] = ScheduledWorkflowArgumentMappingWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('crontab/',
                 self.admin_site.admin_view(CrontabView.as_view()),
                 name='scheduler_scheduledworkflow_crontab'),
            path('run/<int:sw_id>/',
                 self.admin_site.admin_view(RunScheduledWorkflowView.as_view()),
                 name='scheduler_scheduledworkflow_run'),
            path('api/workflow-arguments/<int:workflow_id>/',
                 self.admin_site.admin_view(GetWorkflowArgumentsView.as_view()),
                 name='scheduler_workflow_arguments'),
        ]
        return custom + urls
