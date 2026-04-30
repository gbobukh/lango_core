from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0018_systemconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiauthtype',
            name='static_inject_in',
            field=models.CharField(
                blank=True,
                choices=[('HEADER', 'Header'), ('QUERY_PARAM', 'Query Parameter')],
                default='HEADER',
                help_text='For static credentials (key_definitions): where to inject keys into the main request.',
                max_length=20,
            ),
        ),
    ]

