# Rename FIND lookup library preset and config keys to domain-neutral names.

from django.db import migrations

OLD_PRESET_NAME = 'FIND - Lookup IDs in campaign tree'
NEW_PRESET_NAME = 'FIND - Lookup IDs in hierarchical tree'

LOOKUP_ACTION_CONFIG = {
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
}


def refresh_lookup_preset(apps, schema_editor):
    ActionConfigLibrary = apps.get_model('service_builder', 'ActionConfigLibrary')
    ActionConfigLibrary.objects.filter(
        action_type='FIND',
        name=OLD_PRESET_NAME,
    ).delete()
    ActionConfigLibrary.objects.update_or_create(
        action_type='FIND',
        name=NEW_PRESET_NAME,
        defaults={
            'description': (
                'Resolve API ids for rows that reference hierarchical paths (rules/paths/offers segments). '
                'Expects path segments like rules[i].paths[j].offers[k]; optional stats.by_branch fills gaps.'
            ),
            'action_config': LOOKUP_ACTION_CONFIG,
            'is_active': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0057_rename_find_oidh_to_find_presets_lookup'),
    ]

    operations = [
        migrations.RunPython(refresh_lookup_preset, migrations.RunPython.noop),
    ]
