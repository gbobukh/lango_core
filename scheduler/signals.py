"""
Signals to auto-sync crontab when ScheduledWorkflow or Frequency changes.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .crontab import sync_crontab
from .models import Frequency, ScheduledWorkflow


@receiver(post_save, sender=ScheduledWorkflow)
@receiver(post_delete, sender=ScheduledWorkflow)
def sync_crontab_on_scheduled_workflow_change(sender, **kwargs):
    sync_crontab()


@receiver(post_save, sender=Frequency)
def sync_crontab_on_frequency_change(sender, **kwargs):
    """Frequency change affects cron expression; sync to update crontab."""
    sync_crontab()
