# Generated manually: add ActionConfigLibrary preset for TREE_STATS_BY_PATHS.

from django.db import migrations


PRESET_NAME = 'TREE_STATS_BY_PATHS - Branch Leaf Stats from Diff Paths'


def add_tree_stats_preset(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.update_or_create(
        action_type='TREE_STATS_BY_PATHS',
        name=PRESET_NAME,
        defaults={
            'description': (
                'Compute branch-level leaf stats only for branches affected by changed paths. '
                'Use after DIFF_OBJECTS to prepare decision input for downstream steps.'
            ),
            'action_config': {
                'state_input': 'context.campaign_after',
                'paths_input': 'context.diff.changes',
                'path_field': 'path',
                'branch_spec': {
                    'branch_level_node': 'paths',
                    'leaf_collection': 'offers',
                    'leaf_id_field': 'offerId',
                    'leaf_flags': ['enabled'],
                },
                'metrics': {
                    'count_total_leaves': True,
                    'count_enabled_leaves': True,
                },
                'output_variable': 'branch_stats',
            },
            'is_active': True,
        },
    )


def remove_tree_stats_preset(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.filter(
        action_type='TREE_STATS_BY_PATHS',
        name=PRESET_NAME,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0050_add_tree_stats_by_paths_action_type'),
    ]

    operations = [
        migrations.RunPython(add_tree_stats_preset, remove_tree_stats_preset),
    ]

