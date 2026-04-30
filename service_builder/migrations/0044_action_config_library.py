# Generated manually (catalog of action presets; no ScenarioStep schema change).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('service_builder', '0043_scenariostep_error_handlers'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActionConfigLibrary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text="Unique label within this action type (e.g. 'Merge campaigns with stats').", max_length=255)),
                ('description', models.TextField(blank=True, help_text='What this preset does and which context variables it expects.')),
                (
                    'action_type',
                    models.CharField(
                        choices=[
                            ('MERGE', 'Merge List'),
                            ('FILTER', 'Filter List'),
                            ('TRANSFORM', 'Transform Data'),
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
                (
                    'action_config',
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='JSON passed to ActionRunner for this action_type (same shape as ScenarioStep.action_config).',
                    ),
                ),
                ('is_active', models.BooleanField(default=True, help_text='Hide outdated presets without deleting them.')),
                ('sort_order', models.PositiveIntegerField(default=0, help_text='Display order in admin and future pickers.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Action config library entry',
                'verbose_name_plural': 'Action config library',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='actionconfiglibrary',
            constraint=models.UniqueConstraint(fields=('action_type', 'name'), name='uniq_actionconfiglibrary_action_type_name'),
        ),
    ]
