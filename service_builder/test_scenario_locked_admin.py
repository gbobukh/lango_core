from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from integrations.models import Tracker
from service_builder.models import (
    BusinessAction,
    BusinessActionVariant,
    Scenario,
    ScenarioStep,
    ServiceEndpoint,
    ServiceMethod,
)

User = get_user_model()


class ScenarioAdminLockTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password',
        )
        self.client = Client()
        self.client.force_login(self.superuser)

        self.tracker = Tracker.objects.create(name='Test Tracker')
        self.endpoint = ServiceEndpoint.objects.create(
            tracker=self.tracker,
            name='Get item',
            method='GET',
            resource_path='/api/item',
            parameters=[],
            validation_status='VALID',
        )
        self.service_method = ServiceMethod.objects.create(
            name='Get item method',
            service_endpoint=self.endpoint,
            return_key='data',
            payload_fields=[],
            validation_status='VALID',
        )
        self.arguments = ['source_id']
        self.scenario = Scenario.objects.create(
            name='Locked scenario',
            arguments=self.arguments,
            validation_status='VALID',
        )
        self.step = ScenarioStep.objects.create(
            scenario=self.scenario,
            order=1,
            step_type='API_CALL',
            method=self.service_method,
        )
        self.action = BusinessAction.objects.create(
            name='Use scenario',
            arguments=['source_id'],
        )
        BusinessActionVariant.objects.create(
            business_action=self.action,
            scenario=self.scenario,
            tracker=self.tracker,
        )
        self.scenario.visible_to.add(self.superuser)

        self.demo_admin = User.objects.create_user(
            username='demo_admin',
            email='demo@example.com',
            password='password',
        )

    def test_locked_save_updates_visible_to_without_clearing_scenario_or_steps(self):
        url = reverse('admin:service_builder_scenario_change', args=[self.scenario.pk])
        response = self.client.post(
            url,
            {
                'visible_to': [str(self.demo_admin.pk)],
                'steps-TOTAL_FORMS': '1',
                'steps-INITIAL_FORMS': '1',
                'steps-MIN_NUM_FORMS': '0',
                'steps-MAX_NUM_FORMS': '1000',
                'steps-0-id': str(self.step.pk),
            },
        )
        self.assertEqual(response.status_code, 302)

        self.scenario.refresh_from_db()
        self.step.refresh_from_db()
        self.assertEqual(self.scenario.name, 'Locked scenario')
        self.assertEqual(self.scenario.arguments, self.arguments)
        self.assertEqual(self.scenario.validation_status, 'VALID')
        self.assertEqual(self.step.method_id, self.service_method.pk)
        self.assertEqual(
            set(self.scenario.visible_to.values_list('pk', flat=True)),
            {self.demo_admin.pk},
        )
