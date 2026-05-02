from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0047_alter_actionconfiglibrary_action_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scenariostep',
            name='step_type',
            field=models.CharField(
                choices=[('API_CALL', 'API Call'), ('ACTION', 'Action'), ('API_BATCH', 'API Batch')],
                default='API_CALL',
                help_text='Type of step: API Call (single HTTP request), Action (internal processing), or API Batch (multiple API calls by routing).',
                max_length=20,
            ),
        ),
    ]
