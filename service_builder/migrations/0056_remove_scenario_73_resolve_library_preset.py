# Remove mistaken scenario-specific Action Config Library entry (templates only).

from django.db import migrations

SCENARIO_73_PRESET_NAME = (
    'RESOLVE_HIERARCHICAL_DISABLES - After DIFF + TREE_STATS (scenario 73)'
)


def remove_scenario_preset(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.filter(
        action_type='RESOLVE_HIERARCHICAL_DISABLES',
        name=SCENARIO_73_PRESET_NAME,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0055_add_resolve_hierarchical_disables_action_type'),
    ]

    operations = [
        migrations.RunPython(remove_scenario_preset, migrations.RunPython.noop),
    ]
