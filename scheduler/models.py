from django.db import models
from django.conf import settings


class Frequency(models.Model):
    """Describes schedule periodicity for cron (minutes, hours, days, weeks, months)."""

    INTERVAL_UNIT_CHOICES = [
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ]

    name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this schedule (e.g., Every 6 hours)"
    )
    interval_unit = models.CharField(
        max_length=20,
        choices=INTERVAL_UNIT_CHOICES,
        help_text="Unit of the interval"
    )
    interval_value = models.PositiveIntegerField(
        default=1,
        help_text="Number of units between runs (e.g., 6 for every 6 hours)"
    )
    minute = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Minute (0-59). Used for hours/days/weeks/months."
    )
    hour = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Hour (0-23). Used for days/weeks/months."
    )
    day_of_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Day of month (1-31). Used for months."
    )
    day_of_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Day of week (0-6, Sunday=0). Used for weeks."
    )
    month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Month (1-12). Used for monthly schedules."
    )

    class Meta:
        verbose_name = "Frequency"
        verbose_name_plural = "Frequencies"

    def __str__(self):
        return self.name

    def to_cron_expression(self):
        """
        Convert this Frequency to a 5-field cron expression: minute hour day_of_month month day_of_week.
        """
        if self.interval_unit == 'minutes':
            # Every N minutes. If minute is set: start from that minute (e.g. 45 + every 30 = 15,45)
            if self.minute is not None:
                minutes = set()
                m = self.minute % 60
                for _ in range(60):
                    minutes.add(m)
                    m = (m + self.interval_value) % 60
                return f"{','.join(str(x) for x in sorted(minutes))} * * * *"
            return f"*/{self.interval_value} * * * *"
        if self.interval_unit == 'hours':
            # Every N hours at minute M: M */N * * *
            m = self.minute if self.minute is not None else 0
            return f"{m} */{self.interval_value} * * *"
        if self.interval_unit == 'days':
            # Every N days at H:M: M H */N * *
            m = self.minute if self.minute is not None else 0
            h = self.hour if self.hour is not None else 0
            return f"{m} {h} */{self.interval_value} * *"
        if self.interval_unit == 'weeks':
            # Every N weeks on day D at H:M: M H * * D
            m = self.minute if self.minute is not None else 0
            h = self.hour if self.hour is not None else 0
            d = self.day_of_week if self.day_of_week is not None else 0
            return f"{m} {h} * * {d}"
        if self.interval_unit == 'months':
            # Every N months on day D at H:M: M H D */N *
            m = self.minute if self.minute is not None else 0
            h = self.hour if self.hour is not None else 0
            dom = self.day_of_month if self.day_of_month is not None else 1
            return f"{m} {h} {dom} */{self.interval_value} *"
        return "* * * * *"


class ScheduledWorkflow(models.Model):
    """Links a Workflow to a Frequency and default arguments for scheduled execution."""

    workflow = models.ForeignKey(
        'service_builder.Workflow',
        on_delete=models.CASCADE,
        related_name='scheduled_instances',
        help_text="Workflow to run on schedule"
    )
    frequency = models.ForeignKey(
        Frequency,
        on_delete=models.PROTECT,
        related_name='scheduled_workflows',
        help_text="How often to run"
    )
    default_arguments = models.JSONField(
        default=dict,
        blank=True,
        help_text="Default context/arguments for the workflow (e.g. {\"auth_id\": 1})"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to disable this schedule"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Scheduled Workflow"
        verbose_name_plural = "Scheduled Workflows"

    def __str__(self):
        return f"{self.workflow.name} ({self.frequency.name})"

    def get_arguments_summary(self):
        """
        Returns a comma-separated string of all argument values, resolved using
        workflow.arguments schema (model PKs → str(obj), report_dates → DD.MM–DD.MM).
        """
        from django.apps import apps
        from django.core.exceptions import ObjectDoesNotExist
        from datetime import datetime

        args = (self.workflow.arguments or []) if self.workflow_id else []
        defs = self.default_arguments or {}
        parts = []

        for arg in args:
            name = arg.get('name') if isinstance(arg, dict) else arg
            if not name:
                continue
            val = defs.get(name)
            if val is None:
                continue

            arg_type = arg.get('type', 'string') if isinstance(arg, dict) else 'string'

            if arg_type == 'model':
                model_path = arg.get('model')
                if model_path:
                    try:
                        app_label, model_name = model_path.split('.')
                        Model = apps.get_model(app_label, model_name.lower())
                        pk = int(val) if isinstance(val, (int, str)) and str(val).strip().isdigit() else None
                        if pk is not None:
                            obj = Model.objects.get(pk=pk)
                            parts.append(str(obj))
                        else:
                            parts.append(str(val))
                    except (LookupError, ValueError, ObjectDoesNotExist):
                        parts.append(f"pk={val} (удалён)" if val else "—")
                else:
                    parts.append(str(val))

            elif arg_type == 'report_dates' and isinstance(val, dict):
                preset = val.get('preset')
                if preset:
                    from .utils import PRESET_LABELS
                    parts.append(PRESET_LABELS.get(preset, f"{preset} (dynamic)"))
                else:
                    start = val.get('start', '')
                    end = val.get('end', '')
                    if start and end:
                        try:
                            s = datetime.strptime(start, '%Y-%m-%d').strftime('%d.%m')
                            e = datetime.strptime(end, '%Y-%m-%d').strftime('%d.%m')
                            parts.append(f"{s}–{e}")
                        except (ValueError, TypeError):
                            parts.append(f"{start}–{end}")
                    else:
                        parts.append(str(val))

            else:
                parts.append(str(val))

        return ", ".join(parts)
