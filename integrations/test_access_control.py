import json

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from integrations.access_control import filter_queryset_for_user, user_can_access_obj
from integrations.models import PartnerAccount, PartnerAccountType, Tracker
from service_builder.admin import ServiceEndpointAdmin
from service_builder.api import ModelChoicesAPIView
from service_builder.models import Scenario, ServiceEndpoint
from service_builder.views import GetScenarioArgumentsView

User = get_user_model()


class VisibleToHelperTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password', is_staff=True)
        self.user_b = User.objects.create_user(username='user_b', password='password', is_staff=True)
        self.tracker = Tracker.objects.create(name='Private Tracker')
        self.tracker.visible_to.add(self.user_b)

    def test_filter_queryset_for_user_excludes_other_users_objects(self):
        qs = filter_queryset_for_user(self.user_a, Tracker.objects.all())
        self.assertEqual(list(qs), [])

    def test_user_can_access_obj_respects_visible_to(self):
        self.assertFalse(user_can_access_obj(self.user_a, self.tracker))
        self.assertTrue(user_can_access_obj(self.user_b, self.tracker))


class ServiceEndpointAdminForeignKeyTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password', is_staff=True)
        self.user_b = User.objects.create_user(username='user_b', password='password', is_staff=True)
        self.tracker_a = Tracker.objects.create(name='Tracker A')
        self.tracker_a.visible_to.add(self.user_a)
        self.tracker_b = Tracker.objects.create(name='Tracker B')
        self.tracker_b.visible_to.add(self.user_b)
        self.request = RequestFactory().get('/admin/')
        self.request.user = self.user_a
        self.endpoint_admin = ServiceEndpointAdmin(ServiceEndpoint, admin.site)

    def test_tracker_dropdown_is_scoped_to_visible_to(self):
        field = ServiceEndpoint._meta.get_field('tracker')
        formfield = self.endpoint_admin.formfield_for_foreignkey(field, self.request)
        tracker_ids = set(formfield.queryset.values_list('pk', flat=True))
        self.assertEqual(tracker_ids, {self.tracker_a.pk})


class ModelChoicesApiTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password', is_staff=True)
        self.user_b = User.objects.create_user(username='user_b', password='password', is_staff=True)
        self.account_type = PartnerAccountType.objects.create(name='Publisher')
        self.account_type.visible_to.add(self.user_a, self.user_b)
        self.account_a = PartnerAccount.objects.create(
            name='Account A',
            account_type=self.account_type,
        )
        self.account_a.visible_to.add(self.user_a)
        self.account_b = PartnerAccount.objects.create(
            name='Account B',
            account_type=self.account_type,
        )
        self.account_b.visible_to.add(self.user_b)

    def test_model_choices_api_filters_partner_accounts(self):
        request = RequestFactory().get(
            '/admin/service_builder/api/model-choices/integrations/partneraccount/'
        )
        request.user = self.user_a
        response = ModelChoicesAPIView.as_view()(
            request,
            app_label='integrations',
            model_name='partneraccount',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        values = {choice['value'] for choice in payload['choices']}
        self.assertEqual(values, {str(self.account_a.pk)})


class ScenarioArgumentsApiTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password', is_staff=True)
        self.user_b = User.objects.create_user(username='user_b', password='password', is_staff=True)
        self.scenario = Scenario.objects.create(name='Private Scenario')
        self.scenario.visible_to.add(self.user_b)

    def test_scenario_arguments_api_hides_inaccessible_scenario(self):
        request = RequestFactory().get(
            f'/admin/service_builder/scenario/api/scenario-arguments/{self.scenario.pk}/'
        )
        request.user = self.user_a
        response = GetScenarioArgumentsView.as_view()(request, scenario_id=self.scenario.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {'arguments': []})
