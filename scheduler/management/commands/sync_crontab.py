"""
Management command to sync ScheduledWorkflow entries to system crontab.
"""
from django.core.management.base import BaseCommand

from scheduler.crontab import sync_crontab


class Command(BaseCommand):
    help = "Sync active ScheduledWorkflow entries to system crontab."

    def handle(self, *args, **options):
        success, message = sync_crontab()
        if success:
            self.stdout.write(self.style.SUCCESS(message))
        else:
            self.stderr.write(self.style.ERROR(message))
