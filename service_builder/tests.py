import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from integrations.models import Tracker
from service_builder.models import BusinessAction, BusinessActionVariant, Scenario
from service_builder.utils import ActionRunner
from service_builder.views import TestEndpointView


class _FakeScenarioRunner:
    last_context = None

    def __init__(self, scenario_id, initial_context):
        self.scenario_id = scenario_id
        self.context = dict(initial_context)
        self.logs = ['fake-run']
        self.external_requests = []
        _FakeScenarioRunner.last_context = dict(initial_context)

    def run(self):
        return {
            'success': True,
            'context': {'foo': 'bar'},
            'context_variables': {'foo': 'bar'},
            'logs': self.logs,
            'external_requests': self.external_requests,
        }


class BusinessActionRunTestMappingTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='x',
            is_staff=True,
            is_superuser=True,
        )
        self.tracker = Tracker.objects.create(name='test-tracker')
        self.scenario = Scenario.objects.create(
            name='Action Target Scenario',
            arguments=['my_tg_auth_obj', 'message'],
        )
        self.action = BusinessAction.objects.create(
            name='send alert',
            arguments=['auth_obj', 'message'],
            output_variables=['sent_status'],
        )
        BusinessActionVariant.objects.create(
            business_action=self.action,
            scenario=self.scenario,
            tracker=self.tracker,
            input_mapping={
                'my_tg_auth_obj': '{{ auth_obj }}',
                'message': '{{ message }}',
            },
            output_mapping={
                'sent_status': '{{ foo }}',
            },
        )

    @patch('service_builder.utils.ScenarioRunner', _FakeScenarioRunner)
    def test_action_run_applies_variant_mappings(self):
        payload = {
            'action_id': self.action.pk,
            'variables': {
                'auth_obj': 8,
                'message': 'hello',
            },
        }
        request = self.factory.post(
            '/admin/service_builder/businessaction/execute-test/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        request.user = self.user

        response = TestEndpointView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.content.decode())
        self.assertTrue(body.get('success'))
        self.assertEqual(_FakeScenarioRunner.last_context.get('my_tg_auth_obj'), 8)
        self.assertEqual(_FakeScenarioRunner.last_context.get('message'), 'hello')
        self.assertEqual(body.get('outputs', {}).get('sent_status'), 'bar')


class DiffObjectsActionTests(TestCase):
    def test_diff_objects_reports_replace_add_remove(self):
        runner = ActionRunner(
            context={
                'a': {'x': 1, 'y': {'z': True}, 'arr': [1, 2]},
                'b': {'x': 2, 'y': {'z': True}, 'arr': [1, 2, 3], 'new_key': 'ok'},
            }
        )
        step = SimpleNamespace(action_type='DIFF_OBJECTS', action_config={'input_a': 'a', 'input_b': 'b'})

        result = runner.run(step)

        self.assertFalse(result['equal'])
        self.assertFalse(result['truncated'])
        self.assertEqual(result['summary']['replacements_count'], 1)
        self.assertEqual(result['summary']['additions_count'], 2)
        self.assertEqual(result['summary']['removals_count'], 0)
        self.assertEqual(
            result['changes_count'],
            result['summary']['replacements_count']
            + result['summary']['additions_count']
            + result['summary']['removals_count'],
        )

    def test_diff_objects_respects_max_changes_and_sets_truncated(self):
        runner = ActionRunner(
            context={
                'a': {'a': 1, 'b': 2, 'c': 3},
                'b': {'a': 10, 'b': 20, 'c': 30},
            }
        )
        step = SimpleNamespace(
            action_type='DIFF_OBJECTS',
            action_config={'input_a': 'a', 'input_b': 'b', 'max_changes': 2},
        )

        result = runner.run(step)

        self.assertTrue(result['truncated'])
        self.assertEqual(result['max_changes'], 2)
        self.assertEqual(result['changes_count'], 2)


class TransformUpdateNestedByPredicateTests(TestCase):
    def test_update_nested_by_predicate_disables_offer_in_rules_paths(self):
        campaign = {
            'customRotation': {
                'rules': [
                    {
                        'id': 1,
                        'paths': [
                            {
                                'id': 10,
                                'offers': [
                                    {'offerId': 50, 'enabled': True},
                                    {'offerId': 60, 'enabled': True},
                                ],
                            }
                        ],
                    }
                ]
            }
        }
        runner = ActionRunner(context={'campaign': campaign, 'offer_id': 50})
        step = SimpleNamespace(
            action_type='TRANSFORM',
            action_config={
                'operation': 'update_nested_by_predicate',
                'input': 'campaign',
                'scope_path': 'customRotation.rules',
                'target_collections': ['paths[].offers[]'],
                'predicate': {'field': 'offerId', 'op': '==', 'value_from': 'offer_id'},
                'patch': {'enabled': False},
                'match_mode': 'all',
            },
        )

        result = runner.run(step)

        offer_50 = result['customRotation']['rules'][0]['paths'][0]['offers'][0]
        offer_60 = result['customRotation']['rules'][0]['paths'][0]['offers'][1]
        self.assertFalse(offer_50['enabled'])
        self.assertTrue(offer_60['enabled'])
        # Ensure original context object is not mutated in place
        self.assertTrue(campaign['customRotation']['rules'][0]['paths'][0]['offers'][0]['enabled'])


class TreeStatsByPathsActionTests(TestCase):
    def test_tree_stats_by_paths_counts_only_affected_branches(self):
        campaign = {
            'customRotation': {
                'rules': [
                    {
                        'id': 1,
                        'paths': [
                            {
                                'offers': [
                                    {'offerId': 50, 'enabled': True},
                                    {'offerId': 60, 'enabled': False},
                                ]
                            },
                            {
                                'offers': [
                                    {'offerId': 70, 'enabled': True},
                                ]
                            },
                        ],
                    },
                    {
                        'id': 2,
                        'paths': [
                            {
                                'offers': [
                                    {'offerId': 91, 'enabled': False},
                                ]
                            }
                        ],
                    },
                ]
            }
        }
        diff = {
            'changes': [
                {'path': 'customRotation.rules[0].paths[0].offers[1].enabled'},
                {'path': 'customRotation.rules[0].paths[0].offers[0].enabled'},
                {'path': 'customRotation.rules[1].paths[0].offers[0].enabled'},
            ]
        }
        runner = ActionRunner(context={'campaign_after': campaign, 'diff': diff})
        step = SimpleNamespace(
            action_type='TREE_STATS_BY_PATHS',
            action_config={
                'state_input': 'campaign_after',
                'paths_input': 'diff.changes',
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
            },
        )

        result = runner.run(step)

        self.assertEqual(result['summary']['requested_paths'], 3)
        self.assertEqual(result['summary']['resolved_branches'], 2)
        self.assertEqual(result['summary']['unresolved_paths'], 0)
        self.assertEqual(len(result['by_branch']), 2)

        b0 = result['by_branch']['customRotation.rules[0].paths[0]']
        b1 = result['by_branch']['customRotation.rules[1].paths[0]']

        self.assertEqual(b0['offers_total'], 2)
        self.assertEqual(b0['offers_enabled'], 1)
        self.assertEqual(b0['offers_ids'], [50, 60])

        self.assertEqual(b1['offers_total'], 1)
        self.assertEqual(b1['offers_enabled'], 0)
        self.assertEqual(b1['offers_ids'], [91])

    def test_tree_stats_by_paths_reports_unresolved_paths(self):
        campaign = {
            'customRotation': {
                'rules': [
                    {'paths': [{'offers': [{'offerId': 50, 'enabled': True}]}]},
                ]
            }
        }
        diff = {
            'changes': [
                {'path': 'customRotation.rules[99].paths[0].offers[0].enabled'},
                {'path': 'customRotation.rules[0].unknown[0].enabled'},
            ]
        }
        runner = ActionRunner(context={'campaign_after': campaign, 'diff': diff})
        step = SimpleNamespace(
            action_type='TREE_STATS_BY_PATHS',
            action_config={
                'state_input': 'campaign_after',
                'paths_input': 'diff',
                'path_field': 'path',
                'branch_spec': {
                    'branch_level_node': 'paths',
                    'leaf_collection': 'offers',
                    'leaf_flags': ['enabled'],
                },
                'metrics': {'count_total_leaves': True, 'count_enabled_leaves': True},
            },
        )

        result = runner.run(step)

        self.assertEqual(result['summary']['requested_paths'], 2)
        self.assertEqual(result['summary']['resolved_branches'], 0)
        self.assertEqual(result['summary']['unresolved_paths'], 2)
        reasons = {row['reason'] for row in result['unresolved']}
        self.assertIn('branch_not_found', reasons)
        self.assertIn('branch_level_node_not_found', reasons)

    def test_tree_stats_by_paths_leaf_block_only(self):
        """Without node_metrics action emits the leaf collection block (e.g. offers_*)."""
        campaign = {
            'customRotation': {
                'rules': [
                    {
                        'enabled': False,
                        'paths': [
                            {
                                'enabled': True,
                                'offers': [
                                    {'offerId': 50, 'enabled': True},
                                    {'offerId': 49, 'enabled': False},
                                ],
                            },
                            {
                                'enabled': False,
                                'offers': [
                                    {'offerId': 48, 'enabled': True},
                                    {'offerId': 47, 'enabled': True},
                                ],
                            },
                        ],
                    }
                ]
            }
        }
        diff = {
            'changes': [
                {'path': 'customRotation.rules[0].paths[0].offers[0].enabled'},
                {'path': 'customRotation.rules[0].paths[1].offers[1].enabled'},
            ]
        }
        runner = ActionRunner(context={'campaign_after': campaign, 'diff': diff})
        step = SimpleNamespace(
            action_type='TREE_STATS_BY_PATHS',
            action_config={
                'state_input': 'campaign_after',
                'paths_input': 'diff.changes',
                'path_field': 'path',
                'branch_spec': {
                    'branch_level_node': 'paths',
                    'leaf_collection': 'offers',
                    'leaf_id_field': 'offerId',
                    'leaf_flags': ['enabled'],
                },
                'metrics': {'count_total_leaves': True, 'count_enabled_leaves': True},
            },
        )

        result = runner.run(step)

        self.assertEqual(result['summary']['requested_paths'], 2)
        self.assertEqual(result['summary']['resolved_branches'], 2)
        self.assertEqual(result['summary']['unresolved_paths'], 0)
        self.assertIn('by_branch', result)
        self.assertNotIn('branches', result)

        bp0 = 'customRotation.rules[0].paths[0]'
        bp1 = 'customRotation.rules[0].paths[1]'
        p0 = result['by_branch'][bp0]
        p1 = result['by_branch'][bp1]

        self.assertEqual(set(p0.keys()), {'offers_path', 'offers_total', 'offers_enabled', 'offers_ids'})
        self.assertEqual(p0['offers_path'], f'{bp0}.offers')
        self.assertEqual(p0['offers_total'], 2)
        self.assertEqual(p0['offers_enabled'], 1)
        self.assertEqual(p0['offers_ids'], [50, 49])

        self.assertEqual(p1['offers_path'], f'{bp1}.offers')
        self.assertEqual(p1['offers_total'], 2)
        self.assertEqual(p1['offers_enabled'], 2)
        self.assertEqual(p1['offers_ids'], [48, 47])

    def test_tree_stats_by_paths_node_metrics_unified_levels(self):
        campaign = {
            'customRotation': {
                'rules': [
                    {
                        'enabled': True,
                        'paths': [
                            {
                                'enabled': True,
                                'offers': [
                                    {'offerId': 50, 'enabled': True},
                                    {'offerId': 49, 'enabled': False},
                                ],
                            },
                            {
                                'enabled': False,
                                'offers': [
                                    {'offerId': 48, 'enabled': True},
                                ],
                            },
                        ],
                    }
                ]
            }
        }
        diff = {
            'changes': [
                {'path': 'customRotation.rules[0].paths[0].offers[0].enabled'},
                {'path': 'customRotation.rules[0].paths[1].offers[0].enabled'},
            ]
        }
        runner = ActionRunner(context={'campaign_after': campaign, 'diff': diff})
        step = SimpleNamespace(
            action_type='TREE_STATS_BY_PATHS',
            action_config={
                'state_input': 'campaign_after',
                'paths_input': 'diff.changes',
                'path_field': 'path',
                'branch_spec': {
                    'branch_level_node': 'paths',
                    'leaf_collection': 'offers',
                    'leaf_id_field': 'offerId',
                    'leaf_flags': ['enabled'],
                },
                'metrics': {'count_total_leaves': True, 'count_enabled_leaves': True},
                'node_metrics': [
                    {
                        'name': 'rules',
                        'segment': 'rules',
                        'path_style': 'upto_named_token',
                        'item_flags': ['enabled'],
                    },
                    {
                        'name': 'paths',
                        'segment': 'paths',
                        'path_style': 'parent_plus_named_token',
                        'item_flags': ['enabled'],
                    },
                ],
            },
        )

        result = runner.run(step)
        self.assertEqual(result['summary']['resolved_branches'], 2)

        bp0 = 'customRotation.rules[0].paths[0]'
        bp1 = 'customRotation.rules[0].paths[1]'
        p0 = result['by_branch'][bp0]
        p1 = result['by_branch'][bp1]

        expected_keys = {
            'rules_path',
            'rules_total',
            'rules_enabled',
            'rules_ids',
            'paths_path',
            'paths_total',
            'paths_enabled',
            'paths_ids',
            'offers_path',
            'offers_total',
            'offers_enabled',
            'offers_ids',
        }
        self.assertEqual(set(p0.keys()), expected_keys)
        self.assertEqual(set(p1.keys()), expected_keys)

        # One rule in customRotation.rules; that rule is enabled.
        self.assertEqual(p0['rules_path'], 'customRotation.rules')
        self.assertEqual(p0['rules_total'], 1)
        self.assertEqual(p0['rules_enabled'], 1)
        self.assertEqual(p0['rules_ids'], [0])

        # Under that rule: two paths, one enabled.
        self.assertEqual(p0['paths_path'], 'customRotation.rules[0].paths')
        self.assertEqual(p0['paths_total'], 2)
        self.assertEqual(p0['paths_enabled'], 1)
        self.assertEqual(p0['paths_ids'], [0, 1])

        self.assertEqual(p0['offers_path'], f'{bp0}.offers')
        self.assertEqual(p0['offers_total'], 2)
        self.assertEqual(p0['offers_enabled'], 1)
        self.assertEqual(p0['offers_ids'], [50, 49])

        self.assertEqual(p1['rules_path'], 'customRotation.rules')
        self.assertEqual(p1['paths_path'], 'customRotation.rules[0].paths')
        self.assertEqual(p1['paths_total'], 2)
        self.assertEqual(p1['paths_enabled'], 1)
        self.assertEqual(p1['offers_path'], f'{bp1}.offers')
        self.assertEqual(p1['offers_total'], 1)
        self.assertEqual(p1['offers_enabled'], 1)
        self.assertEqual(p1['offers_ids'], [48])


class ScenarioStepContractValidationTests(TestCase):
    """Contracts for ScenarioStep polymorphism (scenario_step_contracts)."""

    def test_api_call_ok(self):
        from service_builder.scenario_step_contracts import validate_scenario_step_cleaned

        validate_scenario_step_cleaned(
            {
                'step_type': 'API_CALL',
                'method': SimpleNamespace(pk=1),
                'action_type': None,
                'action_config': {},
            }
        )

    def test_api_call_requires_method(self):
        from django.core.exceptions import ValidationError

        from service_builder.scenario_step_contracts import validate_scenario_step_cleaned

        with self.assertRaises(ValidationError) as ctx:
            validate_scenario_step_cleaned(
                {
                    'step_type': 'API_CALL',
                    'method': None,
                    'action_type': None,
                    'action_config': {},
                }
            )
        self.assertIn('method', ctx.exception.error_dict)

    def test_api_call_clears_action_type_and_action_config(self):
        """Для API_CALL поля action не используются — контракт сбрасывает их в cleaned_data."""
        from service_builder.scenario_step_contracts import validate_scenario_step_cleaned

        data = {
            'step_type': 'API_CALL',
            'method': SimpleNamespace(pk=1),
            'action_type': 'FILTER',
            'action_config': {'routing': {'methods': [{'entity': 'x'}]}},
        }
        validate_scenario_step_cleaned(data)
        self.assertIsNone(data['action_type'])
        self.assertEqual(data['action_config'], {})

    def test_action_ok_and_rejects_method(self):
        from django.core.exceptions import ValidationError

        from service_builder.scenario_step_contracts import validate_scenario_step_cleaned

        validate_scenario_step_cleaned(
            {
                'step_type': 'ACTION',
                'method': None,
                'action_type': 'MERGE',
                'action_config': {'input_a': 'a', 'input_b': 'b'},
            }
        )

        with self.assertRaises(ValidationError) as ctx:
            validate_scenario_step_cleaned(
                {
                    'step_type': 'ACTION',
                    'method': SimpleNamespace(pk=1),
                    'action_type': 'MERGE',
                    'action_config': {},
                }
            )
        self.assertIn('method', ctx.exception.error_dict)

        with self.assertRaises(ValidationError) as ctx:
            validate_scenario_step_cleaned(
                {
                    'step_type': 'ACTION',
                    'method': None,
                    'action_type': None,
                    'action_config': {},
                }
            )
        self.assertIn('action_type', ctx.exception.error_dict)

    def test_api_batch_requires_source_routes_and_method_ref(self):
        from django.core.exceptions import ValidationError

        from service_builder.scenario_step_contracts import validate_scenario_step_cleaned

        validate_scenario_step_cleaned(
            {
                'step_type': 'API_BATCH',
                'method': None,
                'action_type': None,
                'action_config': {
                    'source': {'value': 'context.ops'},
                    'routing': {
                        'methods': [
                            {'entity': 'rule', 'method_id': 42, 'argument_mapping': {}},
                        ]
                    },
                },
            }
        )

        with self.assertRaises(ValidationError) as ctx:
            validate_scenario_step_cleaned(
                {
                    'step_type': 'API_BATCH',
                    'method': None,
                    'action_type': None,
                    'action_config': {'source': {'value': 'x'}, 'routing': {'methods': []}},
                }
            )
        self.assertIn('action_config', ctx.exception.error_dict)

        with self.assertRaises(ValidationError) as ctx:
            validate_scenario_step_cleaned(
                {
                    'step_type': 'API_BATCH',
                    'method': None,
                    'action_type': None,
                    'action_config': {
                        'routing': {
                            'methods': [{'entity': 'rule', 'argument_mapping': {}}],
                        },
                    },
                }
            )
        self.assertIn('action_config', ctx.exception.error_dict)

    def test_unknown_step_type(self):
        from django.core.exceptions import ValidationError

        from service_builder.scenario_step_contracts import validate_scenario_step_cleaned

        with self.assertRaises(ValidationError) as ctx:
            validate_scenario_step_cleaned({'step_type': 'WEIRD'})
        self.assertIn('step_type', ctx.exception.error_dict)
