# Generated manually for tracker_from_argument

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0036_alter_scenariostep_action_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessaction',
            name='tracker_from_argument',
            field=models.CharField(
                blank=True,
                help_text="Name of the argument (ApiAuthID) from which to derive tracker for variant selection. "
                          "If empty or no ApiAuthID arg, variant falls back to GENERAL.",
                max_length=255
            ),
        ),
    ]
