# Rename FIND_OIDH -> FIND on ScenarioStep / ActionConfigLibrary; add FIND library presets.

from django.db import migrations, models


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
    ('FIND', 'Find'),
    ('BUILD_OIDH_BLACKLIST', 'Build OIDH Blacklist'),
    ('DICT_TO_LIST', 'Dict to List'),
]

PRESET_OIDH_NAME = 'FIND - Match OIDH rule'
PRESET_LOOKUP_NAME = 'FIND - Lookup IDs in hierarchical tree'


def migrate_action_type_forward(apps, schema_editor):
    ScenarioStep = apps.get_model('service_builder', 'ScenarioStep')
    ScenarioStep.objects.filter(action_type='FIND_OIDH').update(action_type='FIND')
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.filter(action_type='FIND_OIDH').update(action_type='FIND')


def migrate_action_type_backward(apps, schema_editor):
    """Best-effort: treat all FIND rows as legacy FIND_OIDH before restoring old choices."""
    ScenarioStep = apps.get_model('service_builder', 'ScenarioStep')
    ScenarioStep.objects.filter(action_type='FIND').update(action_type='FIND_OIDH')
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.filter(action_type='FIND').update(action_type='FIND_OIDH')


def add_find_presets(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.update_or_create(
        action_type='FIND',
        name=PRESET_OIDH_NAME,
        defaults={
            'description': (
                'OIDH overlap match: picks the rule with strongest criteria overlap per input row. '
                'Use input + rules lists; optional iterator filters by campaign id.'
            ),
            'action_config': {
                'operation': 'oidh_match',
                'input': 'context.oidh_candidates',
                'rules': 'context.oidh_rules',
                'output_rule_id_key': 'matched_rule_id',
                'output_rule_name_key': 'matched_rule_name',
                'input_campaign_id_field': 'cmp_id',
                'iterator_campaign_id_field': 'id',
            },
            'is_active': True,
        },
    )
    ActionConfigLibrary.objects.update_or_create(
        action_type='FIND',
        name=PRESET_LOOKUP_NAME,
        defaults={
            'description': (
                'Resolve API ids for rows that reference hierarchical paths (rules/paths/offers segments). '
                'Expects path segments like rules[i].paths[j].offers[k]; optional stats.by_branch fills gaps.'
            ),
            'action_config': {
                'operation': 'lookup_in_tree',
                'input': 'context.items_to_enrich',
                'source': 'context.tree_source',
                'path_field': 'path',
                'scope_field': 'scope',
                'tree': {
                    'rules_path': 'customRotation.rules',
                    'paths_segment': 'paths',
                    'offers_segment': 'offers',
                    'root_id_field': 'id',
                    'rule_id_field': 'id',
                    'path_id_field': 'id',
                    'offer_id_field': 'offerId',
                },
                'output': {
                    'root_id': 'root_id',
                    'rule_id': 'rule_id',
                    'path_id': 'path_id',
                    'offer_id': 'offer_id',
                },
                'stats': {
                    'stats_path': 'context.branch_stats',
                    'stats_branch_key_template': 'customRotation.rules[{r}].paths[{p}]',
                    'stats_rule_key_template': 'customRotation.rules[{r}]',
                    'paths_ids_field': 'paths_ids',
                    'offers_ids_field': 'offers_ids',
                    'rules_ids_field': 'rules_ids',
                },
            },
            'is_active': True,
        },
    )


def remove_find_presets(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.filter(
        action_type='FIND',
        name__in=(PRESET_OIDH_NAME, PRESET_LOOKUP_NAME),
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0056_remove_scenario_73_resolve_library_preset'),
    ]

    operations = [
        migrations.RunPython(migrate_action_type_forward, migrate_action_type_backward),
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
        migrations.RunPython(add_find_presets, remove_find_presets),
    ]
