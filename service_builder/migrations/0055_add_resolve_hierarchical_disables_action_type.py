# Generated manually: RESOLVE_HIERARCHICAL_DISABLES action type + library preset.

from django.db import migrations, models


PRESET_NAME_GENERIC = 'RESOLVE_HIERARCHICAL_DISABLES - Escalate disable ops from tree stats'
PRESET_NAME_SCENARIO_73 = (
    'RESOLVE_HIERARCHICAL_DISABLES - After DIFF + TREE_STATS (scenario 73)'
)

DEFAULT_ACTION_CONFIG = {
    'tree': {
        'stats_path': 'branch_stats',
        'stats_branch_key_template': 'customRotation.rules[{r}].paths[{p}]',
        'stats_rule_key_template': 'customRotation.rules[{r}]',
        'offers_enabled_field': 'offers_enabled',
        'paths_enabled_field': 'paths_enabled',
    },
    'input': {
        'changes_path': 'proposed_changes',
        'path_field': 'path',
    },
    'policy': {
        'min_active_children': 1,
        'escalation': 'parent',
        'multi_change_policy': 'simulate_counters',
    },
    'output': {
        'resolved_operations_path': 'safe_disable_ops',
        'report_path': 'guard_report',
    },
}

_ACTION_TYPE_CHOICES = [
    ('MERGE', 'Merge List'),
    ('FILTER', 'Filter List'),
    ('TRANSFORM', 'Transform Data'),
    ('DIFF_OBJECTS', 'Diff Objects'),
    ('TREE_STATS_BY_PATHS', 'Tree Stats by Paths'),
    ('RESOLVE_HIERARCHICAL_DISABLES', 'Resolve Hierarchical Disables'),
    ('ENRICH', 'Enrich List (Join & Append)'),
    ('HIERARCHICAL_FLATTEN', 'Hierarchical Flatten (Parent→Child)'),
    ('MULTI_HIERARCHICAL_FLATTEN', 'Multi-Hierarchical Flatten (N levels)'),
    ('GROUP_BY', 'Group By (Aggregate)'),
    ('FLATTEN_COLLECTION', 'Flatten Collection (Expand List Field)'),
    ('FIND_OIDH', 'Find OIDH'),
    ('BUILD_OIDH_BLACKLIST', 'Build OIDH Blacklist'),
    ('DICT_TO_LIST', 'Dict to List'),
]

SCENARIO_73_ACTION_CONFIG = {
    **DEFAULT_ACTION_CONFIG,
    'tree': {
        **DEFAULT_ACTION_CONFIG['tree'],
        'stats_path': 'tree_stats_changed_campaign_json',
    },
    'input': {
        **DEFAULT_ACTION_CONFIG['input'],
        'changes_path': 'diff_changes',
    },
}


def add_preset(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.update_or_create(
        action_type='RESOLVE_HIERARCHICAL_DISABLES',
        name=PRESET_NAME_GENERIC,
        defaults={
            'description': (
                'Resolve offer-level disable changes using TREE_STATS_BY_PATHS branch stats. '
                'Escalates to path or rule scope when disabling the last active child would '
                'violate min_active_children. Writes safe_disable_ops and guard_report to context. '
                'Generic context keys: branch_stats, proposed_changes.'
            ),
            'action_config': DEFAULT_ACTION_CONFIG,
            'is_active': True,
        },
    )
    ActionConfigLibrary.objects.update_or_create(
        action_type='RESOLVE_HIERARCHICAL_DISABLES',
        name=PRESET_NAME_SCENARIO_73,
        defaults={
            'description': (
                'Same as the generic RESOLVE_HIERARCHICAL_DISABLES preset, with context keys '
                'matching the TEST scenario 73 pipeline: tree_stats_changed_campaign_json and '
                'diff_changes (after DIFF_OBJECTS + TREE_STATS_BY_PATHS).'
            ),
            'action_config': SCENARIO_73_ACTION_CONFIG,
            'is_active': True,
        },
    )


def remove_preset(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.filter(
        action_type='RESOLVE_HIERARCHICAL_DISABLES',
        name__in=[PRESET_NAME_GENERIC, PRESET_NAME_SCENARIO_73],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0054_actionconfiglibrary_visible_to'),
    ]

    operations = [
        migrations.AlterField(
            model_name='actionconfiglibrary',
            name='action_type',
            field=models.CharField(
                choices=_ACTION_TYPE_CHOICES,
                help_text='Must match an ActionRunner action type.',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='scenariostep',
            name='action_type',
            field=models.CharField(
                blank=True,
                choices=_ACTION_TYPE_CHOICES,
                help_text='Type of action to perform (if Step Type is Action)',
                max_length=50,
                null=True,
            ),
        ),
        migrations.RunPython(add_preset, remove_preset),
    ]
