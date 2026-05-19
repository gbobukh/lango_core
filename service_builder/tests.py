import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from integrations.models import Tracker
from service_builder.models import (
    BusinessAction,
    BusinessActionVariant,
    Scenario,
    Workflow,
    WorkflowStep,
)
from service_builder.utils import ActionRunner, WorkflowRunner
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


class FilterActionTests(TestCase):
    def test_filter_flat_field_unchanged_behavior(self):
        items = [
            {'status': 'Active', 'clicks': 10},
            {'status': 'Paused', 'clicks': 5},
            {'status': 'Active', 'clicks': 2},
        ]
        runner = ActionRunner(context={'items': items})
        step = SimpleNamespace(
            action_type='FILTER',
            action_config={
                'input': 'items',
                'match': 'all',
                'filters': [
                    {'field': 'status', 'operator': '==', 'value': 'Active'},
                    {'field': 'clicks', 'operator': '>', 'value': 9},
                ],
            },
        )

        result = runner.run(step)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['status'], 'Active')
        self.assertEqual(result[0]['clicks'], 10)

    def test_filter_dotted_path_nested_field(self):
        verify_results = [
            {
                'success': True,
                'context': {'offer_enabled_in_campaign': True, 'id': '10'},
            },
            {
                'success': True,
                'context': {'offer_enabled_in_campaign': False, 'id': '11'},
            },
            {'success': False, 'error': 'boom', 'item': {'id': '12'}},
        ]
        runner = ActionRunner(context={'verify_results': verify_results})
        step = SimpleNamespace(
            action_type='FILTER',
            action_config={
                'input': 'verify_results',
                'match': 'all',
                'filters': [
                    {'field': 'success', 'operator': '!=', 'value': False},
                    {
                        'field': 'context.offer_enabled_in_campaign',
                        'operator': '==',
                        'value': True,
                    },
                ],
            },
        )

        result = runner.run(step)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['context']['id'], '10')

    def test_filter_dotted_path_missing_does_not_match(self):
        items = [{'context': {'id': '1'}}]
        runner = ActionRunner(context={'items': items})
        step = SimpleNamespace(
            action_type='FILTER',
            action_config={
                'input': 'items',
                'match': 'all',
                'filters': [
                    {
                        'field': 'context.offer_enabled_in_campaign',
                        'operator': '==',
                        'value': True,
                    },
                ],
            },
        )

        result = runner.run(step)

        self.assertEqual(result, [])


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


class TransformCountNestedByPredicateTests(TestCase):
    def test_count_enabled_offer_in_rotation(self):
        campaign = {
            'customRotation': {
                'defaultPaths': [
                    {
                        'offers': [
                            {'offerId': 77, 'enabled': True},
                            {'offerId': 99, 'enabled': False},
                        ]
                    }
                ],
                'rules': [
                    {
                        'paths': [
                            {
                                'offers': [
                                    {'offerId': 77, 'enabled': False},
                                    {'offerId': 50, 'enabled': True},
                                ]
                            }
                        ]
                    }
                ],
            }
        }
        runner = ActionRunner(context={'campaign_json': [campaign], 'offer_id': 77})
        step = SimpleNamespace(
            action_type='TRANSFORM',
            action_config={
                'operation': 'count_nested_by_predicate',
                'input': 'context.campaign_json',
                'scope_path': '',
                'target_collections': [
                    'customRotation.defaultPaths[].offers[]',
                    'customRotation.rules[].paths[].offers[]',
                ],
                'match_mode': 'all',
                'predicate': {
                    'conditions': [
                        {'field': 'offerId', 'op': '==', 'value_from': 'offer_id'},
                        {'field': 'enabled', 'op': '==', 'value': True},
                    ],
                },
            },
        )

        result = runner.run(step)

        self.assertEqual(result['matched_count'], 1)


class TransformCountFlagInScenarioResultsTests(TestCase):
    def test_count_flag_in_scenario_results(self):
        verify_results = [
            {
                'success': True,
                'context': {'offer_enabled_in_campaign': True, 'id': '10'},
            },
            {
                'success': True,
                'context': {'offer_enabled_in_campaign': False, 'id': '11'},
            },
            {'success': False, 'error': 'boom', 'item': {'id': '12'}},
        ]
        runner = ActionRunner(context={'verify_results': verify_results})
        step = SimpleNamespace(
            action_type='TRANSFORM',
            action_config={
                'operation': 'count_flag_in_scenario_results',
                'input': 'verify_results',
                'context_flag': 'offer_enabled_in_campaign',
                'id_context_field': 'id',
            },
        )

        result = runner.run(step)

        self.assertEqual(result['still_active_count'], 1)
        self.assertEqual(result['still_active_campaign_ids'], ['10'])
        self.assertTrue(result['offer_still_active_anywhere'])


class Auto2VerifyAssertExpressionTests(TestCase):
    """SafeEvaluator expressions used in auto-2 verify/assert bootstrap scenarios."""

    def test_verify_calculate_from_wrapped_count_result(self):
        from service_builder.safe_eval import SafeEvaluator

        evaluator = SafeEvaluator(
            context={'offer_count_result': [{'matched_count': 0}]},
        )
        self.assertFalse(evaluator.evaluate('offer_count_result[0]["matched_count"] > 0'))
        self.assertEqual(evaluator.evaluate('offer_count_result[0]["matched_count"]'), 0)

        evaluator.context['offer_count_result'] = [{'matched_count': 2}]
        self.assertTrue(evaluator.evaluate('offer_count_result[0]["matched_count"] > 0'))

    def test_assert_success_condition_still_active_zero(self):
        from service_builder.safe_eval import SafeEvaluator

        evaluator = SafeEvaluator(context={'result': {'still_active_count': 0}})
        self.assertTrue(evaluator.evaluate('result["still_active_count"] == 0'))

        evaluator.context['result'] = {'still_active_count': 1}
        self.assertFalse(evaluator.evaluate('result["still_active_count"] == 0'))


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


class ResolveHierarchicalDisablesTests(TestCase):
    """Integration tests for RESOLVE_HIERARCHICAL_DISABLES (conversation fixtures)."""

    BRANCH_STATS = {
        'summary': {
            'requested_paths': 7,
            'resolved_branches': 7,
            'unresolved_paths': 0,
        },
        'by_branch': {
            'customRotation.rules[0].paths[0]': {
                'offers_enabled': 3,
                'paths_enabled': 3,
            },
            'customRotation.rules[0].paths[1]': {
                'offers_enabled': 1,
                'paths_enabled': 3,
            },
            'customRotation.rules[1].paths[0]': {
                'offers_enabled': 3,
                'paths_enabled': 1,
            },
            'customRotation.rules[2].paths[0]': {
                'offers_enabled': 3,
                'paths_enabled': 1,
            },
            'customRotation.rules[3].paths[0]': {
                'offers_enabled': 3,
                'paths_enabled': 1,
            },
            'customRotation.rules[4].paths[0]': {
                'offers_enabled': 3,
                'paths_enabled': 1,
            },
            'customRotation.rules[5].paths[0]': {
                'offers_enabled': 3,
                'paths_enabled': 1,
            },
        },
        'unresolved': [],
    }

    PROPOSED_CHANGES = {
        'equal': False,
        'truncated': False,
        'max_changes': 1000,
        'changes_count': 7,
        'summary': {
            'replacements_count': 7,
            'additions_count': 0,
            'removals_count': 0,
        },
        'changes': [
            {
                'op': 'replace',
                'path': 'customRotation.rules[0].paths[0].offers[0].enabled',
                'before': True,
                'after': False,
            },
            {
                'op': 'replace',
                'path': 'customRotation.rules[0].paths[1].offers[0].enabled',
                'before': True,
                'after': False,
            },
            {
                'op': 'replace',
                'path': 'customRotation.rules[1].paths[0].offers[0].enabled',
                'before': True,
                'after': False,
            },
            {
                'op': 'replace',
                'path': 'customRotation.rules[2].paths[0].offers[0].enabled',
                'before': True,
                'after': False,
            },
            {
                'op': 'replace',
                'path': 'customRotation.rules[3].paths[0].offers[0].enabled',
                'before': True,
                'after': False,
            },
            {
                'op': 'replace',
                'path': 'customRotation.rules[4].paths[0].offers[0].enabled',
                'before': True,
                'after': False,
            },
            {
                'op': 'replace',
                'path': 'customRotation.rules[5].paths[0].offers[0].enabled',
                'before': True,
                'after': False,
            },
        ],
    }

    DEFAULT_CONFIG = {
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

    def _run(self, context=None, config=None):
        context = {
            'branch_stats': self.BRANCH_STATS,
            'proposed_changes': self.PROPOSED_CHANGES,
            **(context or {}),
        }
        runner = ActionRunner(context=context)
        step = SimpleNamespace(
            action_type='RESOLVE_HIERARCHICAL_DISABLES',
            action_config=config or self.DEFAULT_CONFIG,
        )
        return runner.run(step), context

    def test_resolves_seven_changes_with_one_path_escalation(self):
        report, context = self._run()

        self.assertEqual(report['summary']['input_changes'], 7)
        self.assertEqual(report['summary']['resolved_operations'], 7)
        self.assertEqual(report['summary']['offer_level'], 6)
        self.assertEqual(report['summary']['path_level'], 1)
        self.assertEqual(report['summary']['rule_level'], 0)
        self.assertEqual(report['summary']['rejected'], 0)
        self.assertEqual(report['summary']['multi_change_policy'], 'simulate_counters')

        ops = context['safe_disable_ops']
        self.assertEqual(len(ops), 7)

        path_ops = [op for op in ops if op['scope'] == 'path']
        self.assertEqual(len(path_ops), 1)
        self.assertEqual(path_ops[0]['path'], 'customRotation.rules[0].paths[1]')
        self.assertEqual(path_ops[0]['op'], 'disable_path')
        self.assertEqual(
            path_ops[0]['escalated_from'],
            'customRotation.rules[0].paths[1].offers[0].enabled',
        )

        offer_ops = [op for op in ops if op['scope'] == 'offer']
        self.assertEqual(len(offer_ops), 6)

        escalated = [
            d for d in report['details'] if d.get('escalation') == 'offer_to_path'
        ]
        self.assertEqual(len(escalated), 1)
        self.assertIn('Only one active offer', escalated[0]['note'])

    def test_rule_escalation_when_only_one_active_path(self):
        stats = {
            'by_branch': {
                'customRotation.rules[2].paths[0]': {
                    'offers_enabled': 1,
                    'paths_enabled': 1,
                },
            },
        }
        changes = {
            'changes': [
                {
                    'op': 'replace',
                    'path': 'customRotation.rules[2].paths[0].offers[0].enabled',
                    'after': False,
                },
            ],
        }
        report, context = self._run(
            context={'branch_stats': stats, 'proposed_changes': changes}
        )

        self.assertEqual(report['summary']['rule_level'], 1)
        op = context['safe_disable_ops'][0]
        self.assertEqual(op['scope'], 'rule')
        self.assertEqual(op['path'], 'customRotation.rules[2]')
        self.assertEqual(op['op'], 'pause_rule')
        self.assertEqual(report['details'][0]['escalation'], 'path_to_rule')


class FindLookupInTreeTests(TestCase):
    """FIND action: lookup_in_tree (hierarchical paths) + oidh_match (legacy FIND_OIDH behavior)."""

    def _sample_tree_source(self):
        return {
            'id': 990,
            'customRotation': {
                'rules': [
                    {
                        'id': 501,
                        'paths': [
                            {
                                'id': 701,
                                'offers': [
                                    {'offerId': 901},
                                    {'offerId': 902},
                                ],
                            }
                        ],
                    }
                ]
            },
        }

    def test_lookup_in_tree_enriches_items_offer_row(self):
        tree_source = self._sample_tree_source()
        items_to_enrich = [
            {'op': 'replace', 'path': 'rules[0].paths[0].offers[1]', 'scope': 'offer'},
        ]
        runner = ActionRunner(
            context={'items_to_enrich': items_to_enrich, 'tree_source': tree_source}
        )
        step = SimpleNamespace(
            action_type='FIND',
            action_config={
                'operation': 'lookup_in_tree',
                'input': 'items_to_enrich',
                'source': 'tree_source',
                'path_field': 'path',
                'scope_field': 'scope',
                'tree': {
                    'rules_path': 'customRotation.rules',
                    'paths_segment': 'paths',
                    'offers_segment': 'offers',
                },
            },
        )

        out = runner.run(step)

        self.assertEqual(len(out), 1)
        row = out[0]
        self.assertEqual(row['root_id'], 990)
        self.assertEqual(row['rule_id'], 501)
        self.assertEqual(row['path_id'], 701)
        self.assertEqual(row['offer_id'], 902)
        self.assertEqual(row['op'], 'replace')

    def test_lookup_in_tree_legacy_campaign_output_keys(self):
        """output.campaign_id and tree.campaign_id_field remain supported."""
        tree_source = self._sample_tree_source()
        items = [{'path': 'rules[0].paths[0].offers[0]', 'scope': 'offer'}]
        runner = ActionRunner(context={'items': items, 'tree_source': tree_source})
        step = SimpleNamespace(
            action_type='FIND',
            action_config={
                'operation': 'lookup_in_tree',
                'input': 'items',
                'source': 'tree_source',
                'tree': {
                    'rules_path': 'customRotation.rules',
                    'paths_segment': 'paths',
                    'offers_segment': 'offers',
                    'campaign_id_field': 'id',
                },
                'output': {
                    'campaign_id': 'campaign_id',
                    'rule_id': 'rule_id',
                    'path_id': 'path_id',
                    'offer_id': 'offer_id',
                },
            },
        )
        row = runner.run(step)[0]
        self.assertEqual(row['campaign_id'], 990)
        self.assertEqual(row['offer_id'], 901)

    def test_lookup_in_tree_scope_path_omits_offer_id_output(self):
        tree_source = self._sample_tree_source()
        items_to_enrich = [
            {'op': 'disable_path', 'path': 'rules[0].paths[0]', 'scope': 'path'},
        ]
        runner = ActionRunner(
            context={'items_to_enrich': items_to_enrich, 'tree_source': tree_source}
        )
        step = SimpleNamespace(
            action_type='FIND',
            action_config={
                'operation': 'lookup_in_tree',
                'input': 'items_to_enrich',
                'source': 'tree_source',
            },
        )

        row = runner.run(step)[0]
        self.assertEqual(row['rule_id'], 501)
        self.assertEqual(row['path_id'], 701)
        self.assertNotIn('offer_id', row)

    def test_oidh_match_default_operation_on_find_action(self):
        rules_list = [
            {'id': 10, 'name': 'Wide', 'criteria': [{'values': ['ios', 'us']}]},
            {'id': 20, 'name': 'Narrow', 'criteria': [{'values': ['ios']}]},
        ]
        input_list = [{'device': 'ios', 'geo': 'us', 'qty': 1}]
        runner = ActionRunner(context={'hits': input_list, 'rules': rules_list})
        step = SimpleNamespace(
            action_type='FIND',
            action_config={
                'input': 'hits',
                'rules': 'rules',
            },
        )

        out = runner.run(step)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['matched_rule_id'], 10)

    def test_oidh_match_explicit_operation_oidh_match(self):
        rules_list = [{'id': 7, 'name': 'Only', 'criteria': [{'values': ['t-mobile']}]}]
        input_list = [{'carrier': 't-mobile', 'n': 0}]
        runner = ActionRunner(context={'rows': input_list, 'rl': rules_list})
        step = SimpleNamespace(
            action_type='FIND',
            action_config={
                'operation': 'oidh_match',
                'input': 'rows',
                'rules': 'rl',
            },
        )
        self.assertEqual(runner.run(step)[0]['matched_rule_id'], 7)

    def test_legacy_find_oidh_action_type_dispatches_oidh_match(self):
        rules_list = [{'id': 3, 'name': 'R', 'criteria': [{'values': ['a']}]}]
        runner = ActionRunner(context={'rows': [{'k': 'a'}], 'rl': rules_list})
        step = SimpleNamespace(
            action_type='FIND_OIDH',
            action_config={
                'input': 'rows',
                'rules': 'rl',
            },
        )
        self.assertEqual(runner.run(step)[0]['matched_rule_id'], 3)

    def test_find_rejects_unknown_operation(self):
        runner = ActionRunner(context={})
        step = SimpleNamespace(
            action_type='FIND',
            action_config={
                'operation': 'bogus_op',
                'input': 'x',
                'source': 'y',
            },
        )
        with self.assertRaises(ValueError) as ctx:
            runner.run(step)
        self.assertIn('unsupported operation', str(ctx.exception).lower())


class _IteratorScenarioRunnerFactory:
    """Mock ScenarioRunner that fails on selected iteration indices (0-based)."""

    def __init__(self, fail_at_indices):
        self.fail_at_indices = set(fail_at_indices)
        self.call_count = 0
        self.instances = []

    def __call__(self, scenario_id, initial_context):
        factory = self

        class _Runner:
            def __init__(self, sid, ctx):
                self.logs = []
                self.external_requests = []
                self.context = dict(ctx)
                self._index = factory.call_count
                factory.call_count += 1
                factory.instances.append(self)

            def run(self):
                if self._index in factory.fail_at_indices:
                    raise ValueError(f'boom-{self._index}')
                return {
                    'success': True,
                    'context': {'iteration': self._index},
                    'context_variables': {'iteration': self._index},
                    'logs': self.logs,
                    'external_requests': self.external_requests,
                }

        return _Runner(scenario_id, initial_context)


class WorkflowRunnerIteratorFailureTests(TestCase):
    def setUp(self):
        self.tracker = Tracker.objects.create(name='wf-iter-tracker')
        self.scenario = Scenario.objects.create(
            name='wf-iter-scenario',
            arguments=['id'],
        )

    @patch('service_builder.utils.ScenarioRunner')
    def test_direct_scenario_iterator_continues_after_failure(self, mock_runner_cls):
        factory = _IteratorScenarioRunnerFactory(fail_at_indices={0})
        mock_runner_cls.side_effect = factory

        workflow = Workflow.objects.create(name='wf-direct-iter', arguments=[])
        WorkflowStep.objects.create(
            workflow=workflow,
            order=0,
            scenario=self.scenario,
            iterator_variable='items',
            output_variable_name='step_results',
            is_active=True,
        )

        result = WorkflowRunner(
            workflow.pk,
            {'items': [{'id': '1'}, {'id': '2'}]},
        ).run()

        self.assertTrue(result['success'])
        self.assertEqual(factory.call_count, 2)
        step_results = result['context']['step_results']
        self.assertEqual(len(step_results), 2)
        self.assertFalse(step_results[0]['success'])
        self.assertEqual(step_results[0]['error'], 'boom-0')
        self.assertTrue(step_results[1]['success'])

    @patch('service_builder.utils.ScenarioRunner')
    def test_direct_scenario_single_run_fails_workflow(self, mock_runner_cls):
        factory = _IteratorScenarioRunnerFactory(fail_at_indices={0})
        mock_runner_cls.side_effect = factory

        workflow = Workflow.objects.create(name='wf-direct-single', arguments=[])
        WorkflowStep.objects.create(
            workflow=workflow,
            order=0,
            scenario=self.scenario,
            iterator_variable=None,
            output_variable_name='step_results',
            is_active=True,
        )

        result = WorkflowRunner(workflow.pk, {}).run()

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'boom-0')
        self.assertEqual(factory.call_count, 1)

    @patch('service_builder.utils.ScenarioRunner')
    def test_business_action_iterator_continues_after_failure(self, mock_runner_cls):
        factory = _IteratorScenarioRunnerFactory(fail_at_indices={0})
        mock_runner_cls.side_effect = factory

        action = BusinessAction.objects.create(
            name='wf-iter-action',
            arguments=['id'],
        )
        BusinessActionVariant.objects.create(
            business_action=action,
            scenario=self.scenario,
            tracker=self.tracker,
            input_mapping={'id': '{{ id }}'},
        )
        workflow = Workflow.objects.create(name='wf-ba-iter', arguments=[])
        WorkflowStep.objects.create(
            workflow=workflow,
            order=0,
            business_action=action,
            input_mapping={'id': '{{ item.id }}'},
            iterator_variable='items',
            output_variable_name='pause_results',
            tracker_from_argument='',
            is_active=True,
        )

        result = WorkflowRunner(
            workflow.pk,
            {'items': [{'id': 'c1'}, {'id': 'c2'}]},
        ).run()

        self.assertTrue(result['success'])
        self.assertEqual(factory.call_count, 2)
        pause_results = result['context']['pause_results']
        self.assertEqual(len(pause_results), 2)
        self.assertFalse(pause_results[0]['success'])
        self.assertTrue(pause_results[1]['success'])
