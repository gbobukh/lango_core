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
