from django.db import migrations, models


LEGACY_PRESET_NAME = 'TREE_STATS_BY_PATHS - Branch Leaf Stats from Diff Paths'
MERGED_PRESET_NAME = 'TREE_STATS_BY_PATHS - Branch Node Stats from Diff Paths'


def forwards_merge_tree_stats_versions(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ScenarioStep = apps.get_model('service_builder', 'ScenarioStep')

    # Repoint any existing V2 records to the unified action type.
    ActionConfigLibrary.objects.filter(action_type='TREE_STATS_BY_PATHS_V2').update(
        action_type='TREE_STATS_BY_PATHS'
    )
    ScenarioStep.objects.filter(action_type='TREE_STATS_BY_PATHS_V2').update(
        action_type='TREE_STATS_BY_PATHS'
    )

    # Remove legacy v1 preset from the library.
    ActionConfigLibrary.objects.filter(
        action_type='TREE_STATS_BY_PATHS',
        name=LEGACY_PRESET_NAME,
    ).delete()

    # Ensure a single active unified preset exists in the library.
    ActionConfigLibrary.objects.update_or_create(
        action_type='TREE_STATS_BY_PATHS',
        name=MERGED_PRESET_NAME,
        defaults={
            'description': (
                'Compute stats for affected branches resolved from diff paths. '
                'Produces by_branch blocks with offers_* and optional node-level metrics.'
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
                'node_metrics': [
                    {
                        'name': 'paths',
                        'segment': 'paths',
                        'path_style': 'parent_plus_named_token',
                        'item_flags': ['enabled'],
                        'item_id_field': 'id',
                    }
                ],
                'output_variable': 'tree_stats_changed_campaign_json',
            },
            'is_active': True,
        },
    )

    # Clean up any duplicate legacy V2-named presets after remap.
    ActionConfigLibrary.objects.filter(name__icontains='TREE_STATS_BY_PATHS_V2').delete()


def backwards_merge_tree_stats_versions(apps, schema_editor):
    # Irreversible by design: this migration intentionally consolidates action types.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0052_add_tree_stats_by_paths_v2_action_type'),
    ]

    operations = [
        migrations.RunPython(forwards_merge_tree_stats_versions, backwards_merge_tree_stats_versions),
        migrations.AlterField(
            model_name='actionconfiglibrary',
            name='action_type',
            field=models.CharField(
                choices=[
                    ('MERGE', 'Merge List'),
                    ('FILTER', 'Filter List'),
                    ('TRANSFORM', 'Transform Data'),
                    ('DIFF_OBJECTS', 'Diff Objects'),
                    ('TREE_STATS_BY_PATHS', 'Tree Stats by Paths'),
                    ('ENRICH', 'Enrich List (Join & Append)'),
                    ('HIERARCHICAL_FLATTEN', 'Hierarchical Flatten (Parent→Child)'),
                    ('MULTI_HIERARCHICAL_FLATTEN', 'Multi-Hierarchical Flatten (N levels)'),
                    ('GROUP_BY', 'Group By (Aggregate)'),
                    ('FLATTEN_COLLECTION', 'Flatten Collection (Expand List Field)'),
                    ('FIND_OIDH', 'Find OIDH'),
                    ('BUILD_OIDH_BLACKLIST', 'Build OIDH Blacklist'),
                    ('DICT_TO_LIST', 'Dict to List'),
                ],
                help_text='Must match an ActionRunner action type.',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='scenariostep',
            name='action_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('MERGE', 'Merge List'),
                    ('FILTER', 'Filter List'),
                    ('TRANSFORM', 'Transform Data'),
                    ('DIFF_OBJECTS', 'Diff Objects'),
                    ('TREE_STATS_BY_PATHS', 'Tree Stats by Paths'),
                    ('ENRICH', 'Enrich List (Join & Append)'),
                    ('HIERARCHICAL_FLATTEN', 'Hierarchical Flatten (Parent→Child)'),
                    ('MULTI_HIERARCHICAL_FLATTEN', 'Multi-Hierarchical Flatten (N levels)'),
                    ('GROUP_BY', 'Group By (Aggregate)'),
                    ('FLATTEN_COLLECTION', 'Flatten Collection (Expand List Field)'),
                    ('FIND_OIDH', 'Find OIDH'),
                    ('BUILD_OIDH_BLACKLIST', 'Build OIDH Blacklist'),
                    ('DICT_TO_LIST', 'Dict to List'),
                ],
                help_text='Type of action to perform (if Step Type is Action)',
                max_length=50,
                null=True,
            ),
        ),
    ]
