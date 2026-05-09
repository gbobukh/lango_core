# Generated manually: add TREE_STATS_BY_PATHS_V2 action type.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0051_add_tree_stats_by_paths_library_entry'),
    ]

    operations = [
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
                    ('TREE_STATS_BY_PATHS_V2', 'Tree Stats by Paths v2'),
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
                    ('TREE_STATS_BY_PATHS_V2', 'Tree Stats by Paths v2'),
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
