from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("service_builder", "0048_alter_scenariostep_step_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicemethod",
            name="payload_value_types",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Optional payload argument typing metadata. Format: "
                    '{"body.campaignIds": {"type": "array", "items_type": "integer", '
                    '"nullable": false, "hint": "Array of campaign IDs", "example": [45]}}'
                ),
            ),
        ),
    ]
