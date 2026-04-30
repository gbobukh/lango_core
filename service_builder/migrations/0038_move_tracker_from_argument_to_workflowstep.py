# Move tracker_from_argument from BusinessAction to WorkflowStep

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0037_businessaction_tracker_from_argument'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='businessaction',
            name='tracker_from_argument',
        ),
        migrations.AddField(
            model_name='workflowstep',
            name='tracker_from_argument',
            field=models.CharField(
                blank=True,
                help_text="Name of the workflow argument (ApiAuthID) from which to derive tracker for variant selection. "
                          "If empty, variant falls back to GENERAL.",
                max_length=255
            ),
        ),
    ]
