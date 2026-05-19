"""
Idempotently create auto-2.* entities for pausing an offer across all active Binom campaigns.

Workflow: auto-2.PauseOfferInAllActiveCampaigns
  - Inputs: auth_obj (ApiAuthID), offer_id (int)
  - Step 1: fetch active campaign ids via auto-2.GetActiveCampaignIds
  - Step 2: iterate auto-2.PauseOfferInCampaign (wraps scenario #78 binom - pause offer in campaign)
  - Step 3: iterate auto-2.VerifyOfferEnabledInActiveCampaign (fresh GET per campaign, read-only)
  - Step 4: auto-2.AssertNoOfferStillActiveInActiveCampaigns (FILTER + TRANSFORM on verify_results)
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from integrations.models import Tracker
from service_builder.models import (
    BusinessAction,
    BusinessActionVariant,
    Scenario,
    ScenarioStep,
    ServiceEndpoint,
    ServiceMethod,
    Workflow,
    WorkflowStep,
)

PAUSE_SCENARIO_ID = 78
BINOM_TRACKER_NAME = 'Binom'

AUTH_OBJ_ARG = {
    'name': 'auth_obj',
    'type': 'model',
    'model': 'integrations.apiauthid',
    'lookup': 'account_name',
}
OFFER_ID_ARG = {'name': 'offer_id', 'type': 'integer'}
CAMPAIGN_ID_ARG = {'name': 'id', 'type': 'string'}

ENDPOINT_NAME = 'auto-2.binom-campaign-list-filtered'
METHOD_NAME = 'auto-2.binom-get-campaign-list-filtered'
CAMPAIGN_BY_ID_ENDPOINT_NAME = 'auto-2.binom-campaign-by-id'
CAMPAIGN_BY_ID_METHOD_NAME = 'auto-2.binom-get-campaign-by-id'

LIST_SCENARIO_NAME = 'auto-2.binom-get-active-campaign-ids'
VERIFY_SCENARIO_NAME = 'auto-2.binom-verify-offer-enabled-in-campaign'
ASSERT_SCENARIO_NAME = 'auto-2.binom-assert-no-offer-still-active'

LIST_BA_NAME = 'auto-2.GetActiveCampaignIds'
PAUSE_BA_NAME = 'auto-2.PauseOfferInCampaign'
VERIFY_BA_NAME = 'auto-2.VerifyOfferEnabledInActiveCampaign'
ASSERT_BA_NAME = 'auto-2.AssertNoOfferStillActiveInActiveCampaigns'
WORKFLOW_NAME = 'auto-2.PauseOfferInAllActiveCampaigns'

COUNT_ENABLED_OFFER_CONFIG = {
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
}


class Command(BaseCommand):
    help = 'Create auto-2 pause-offer-in-all-active-campaigns workflow stack (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print planned objects without writing to the database.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        tracker = Tracker.objects.get(name=BINOM_TRACKER_NAME)
        pause_scenario = Scenario.objects.get(pk=PAUSE_SCENARIO_ID)
        if pause_scenario.name != 'binom - pause offer in campaign':
            self.stdout.write(
                self.style.WARNING(
                    f'Scenario {PAUSE_SCENARIO_ID} name is "{pause_scenario.name}", expected pause offer scenario.'
                )
            )

        staff_users = list(get_user_model().objects.filter(is_superuser=True)[:5])

        if dry_run:
            self.stdout.write(self.style.NOTICE('DRY RUN — no database writes'))
            self._print_plan(tracker, pause_scenario)
            return

        endpoint = self._ensure_endpoint(tracker)
        method = self._ensure_method(endpoint)
        campaign_endpoint = self._ensure_campaign_by_id_endpoint(tracker)
        campaign_method = self._ensure_campaign_by_id_method(campaign_endpoint)
        list_scenario = self._ensure_list_scenario(method)
        self._validate_scenario(list_scenario)
        verify_scenario = self._ensure_verify_scenario(campaign_method)
        self._validate_scenario(verify_scenario)
        assert_scenario = self._ensure_assert_scenario()
        self._validate_scenario(assert_scenario)
        list_ba = self._ensure_list_business_action(list_scenario, tracker)
        pause_ba = self._ensure_pause_business_action(pause_scenario, tracker)
        verify_ba = self._ensure_verify_business_action(verify_scenario, tracker)
        assert_ba = self._ensure_assert_business_action(assert_scenario, tracker)
        workflow = self._ensure_workflow(list_ba, pause_ba, verify_ba, assert_ba)

        for user in staff_users:
            for obj in (
                endpoint,
                method,
                campaign_endpoint,
                campaign_method,
                list_scenario,
                verify_scenario,
                assert_scenario,
                list_ba,
                pause_ba,
                verify_ba,
                assert_ba,
                workflow,
            ):
                if hasattr(obj, 'visible_to'):
                    obj.visible_to.add(user)

        self.stdout.write(self.style.SUCCESS('auto-2 stack ready'))
        self.stdout.write(f'  Endpoint id={endpoint.pk} {endpoint.name}')
        self.stdout.write(f'  Method id={method.pk} {method.name}')
        self.stdout.write(f'  Campaign-by-id endpoint id={campaign_endpoint.pk} {campaign_endpoint.name}')
        self.stdout.write(f'  Campaign-by-id method id={campaign_method.pk} {campaign_method.name}')
        self.stdout.write(f'  List scenario id={list_scenario.pk} {list_scenario.name}')
        self.stdout.write(f'  Verify scenario id={verify_scenario.pk} {verify_scenario.name}')
        self.stdout.write(f'  Assert scenario id={assert_scenario.pk} {assert_scenario.name}')
        self.stdout.write(f'  List BA id={list_ba.pk} {list_ba.name}')
        self.stdout.write(f'  Pause BA id={pause_ba.pk} {pause_ba.name} -> scenario {PAUSE_SCENARIO_ID}')
        self.stdout.write(f'  Verify BA id={verify_ba.pk} {verify_ba.name}')
        self.stdout.write(f'  Assert BA id={assert_ba.pk} {assert_ba.name}')
        self.stdout.write(f'  Workflow id={workflow.pk} {workflow.name}')

    def _print_plan(self, tracker, pause_scenario):
        self.stdout.write(f'Tracker: {tracker.name} (id={tracker.pk})')
        self.stdout.write(f'Pause scenario: {pause_scenario.pk} {pause_scenario.name}')
        self.stdout.write(
            f'Would create/update: {ENDPOINT_NAME}, {METHOD_NAME}, '
            f'{CAMPAIGN_BY_ID_ENDPOINT_NAME}, {CAMPAIGN_BY_ID_METHOD_NAME},'
        )
        self.stdout.write(
            f'  {LIST_SCENARIO_NAME}, {VERIFY_SCENARIO_NAME}, {ASSERT_SCENARIO_NAME},'
        )
        self.stdout.write(
            f'  {LIST_BA_NAME}, {PAUSE_BA_NAME}, {VERIFY_BA_NAME}, {ASSERT_BA_NAME}, {WORKFLOW_NAME}'
        )

    def _ensure_endpoint(self, tracker):
        endpoint, created = ServiceEndpoint.objects.update_or_create(
            tracker=tracker,
            name=ENDPOINT_NAME,
            defaults={
                'method': 'GET',
                'resource_path': '/public/api/v1/campaign/list/filtered',
                'parameters': [],
                'api_configuration': {},
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created endpoint {endpoint.name}')
        return endpoint

    def _ensure_campaign_by_id_endpoint(self, tracker):
        endpoint, created = ServiceEndpoint.objects.update_or_create(
            tracker=tracker,
            name=CAMPAIGN_BY_ID_ENDPOINT_NAME,
            defaults={
                'method': 'GET',
                'resource_path': '/public/api/v1/campaign/{id}',
                'parameters': [],
                'api_configuration': {},
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created endpoint {endpoint.name}')
        return endpoint

    def _ensure_method(self, endpoint):
        method, created = ServiceMethod.objects.update_or_create(
            service_endpoint=endpoint,
            name=METHOD_NAME,
            defaults={
                'return_key': '',
                'payload_fields': [],
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created method {method.name}')
        return method

    def _ensure_campaign_by_id_method(self, endpoint):
        method, created = ServiceMethod.objects.update_or_create(
            service_endpoint=endpoint,
            name=CAMPAIGN_BY_ID_METHOD_NAME,
            defaults={
                'return_key': '',
                'payload_fields': [],
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created method {method.name}')
        method.save()
        return method

    def _ensure_list_scenario(self, method):
        scenario, created = Scenario.objects.update_or_create(
            name=LIST_SCENARIO_NAME,
            defaults={
                'arguments': [AUTH_OBJ_ARG],
                'validation_status': 'PENDING',
            },
        )
        if created:
            self.stdout.write(f'Created scenario {scenario.name}')

        ScenarioStep.objects.filter(scenario=scenario).delete()

        ScenarioStep.objects.create(
            scenario=scenario,
            order=0,
            step_type='API_CALL',
            method=method,
            argument_mapping={},
            auth_context_variable='auth_obj',
            output_variable_name='campaign_list_raw',
            is_active=True,
        )
        ScenarioStep.objects.create(
            scenario=scenario,
            order=1,
            step_type='ACTION',
            action_type='TRANSFORM',
            action_config={
                'input': 'context.campaign_list_raw',
                'select': ['id'],
            },
            auth_context_variable='auth_obj',
            output_variable_name='active_campaign_ids',
            is_active=True,
        )
        return scenario

    def _ensure_verify_scenario(self, method):
        scenario, created = Scenario.objects.update_or_create(
            name=VERIFY_SCENARIO_NAME,
            defaults={
                'arguments': [AUTH_OBJ_ARG, CAMPAIGN_ID_ARG, OFFER_ID_ARG],
                'validation_status': 'PENDING',
            },
        )
        if created:
            self.stdout.write(f'Created scenario {scenario.name}')

        ScenarioStep.objects.filter(scenario=scenario).delete()

        ScenarioStep.objects.create(
            scenario=scenario,
            order=0,
            step_type='API_CALL',
            method=method,
            argument_mapping={'id': '{{ id }}'},
            auth_context_variable='auth_obj',
            output_variable_name='campaign_json',
            is_active=True,
        )
        ScenarioStep.objects.create(
            scenario=scenario,
            order=1,
            step_type='ACTION',
            action_type='TRANSFORM',
            action_config=COUNT_ENABLED_OFFER_CONFIG,
            auth_context_variable='auth_obj',
            output_variable_name='offer_count_result',
            is_active=True,
        )
        ScenarioStep.objects.create(
            scenario=scenario,
            order=2,
            step_type='ACTION',
            action_type='TRANSFORM',
            action_config={
                'calculate': {
                    # offer_count_result is a list (ScenarioRunner wraps step output).
                    'offer_enabled_in_campaign': 'offer_count_result[0]["matched_count"] > 0',
                    'enabled_offer_count': 'offer_count_result[0]["matched_count"]',
                },
            },
            auth_context_variable='auth_obj',
            is_active=True,
        )
        return scenario

    def _ensure_assert_scenario(self):
        scenario, created = Scenario.objects.update_or_create(
            name=ASSERT_SCENARIO_NAME,
            defaults={
                'arguments': [],
                'validation_status': 'PENDING',
            },
        )
        if created:
            self.stdout.write(f'Created scenario {scenario.name}')

        ScenarioStep.objects.filter(scenario=scenario).delete()

        ScenarioStep.objects.create(
            scenario=scenario,
            order=0,
            step_type='ACTION',
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
            output_variable_name='still_enabled_entries',
            is_active=True,
        )
        ScenarioStep.objects.create(
            scenario=scenario,
            order=1,
            step_type='ACTION',
            action_type='TRANSFORM',
            action_config={
                'calculate': {
                    'matched_count': 'len(still_enabled_entries)',
                },
            },
            output_variable_name='verify_summary',
            success_condition='result["matched_count"] == 0',
            condition_error_message='Offer is still enabled in at least one active campaign.',
            is_active=True,
        )
        return scenario

    def _validate_scenario(self, scenario):
        _is_valid, warnings, _unused = scenario.validate()
        scenario.validation_status = 'VALID'
        scenario.save(update_fields=['validation_status'])
        if warnings:
            self.stdout.write(
                self.style.WARNING(f'Scenario {scenario.name} validation notes: {warnings}')
            )

    def _ensure_list_business_action(self, list_scenario, tracker):
        ba, created = BusinessAction.objects.update_or_create(
            name=LIST_BA_NAME,
            defaults={
                'arguments': [AUTH_OBJ_ARG],
                'output_variables': [{'name': 'active_campaigns'}],
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created business action {ba.name}')

        BusinessActionVariant.objects.update_or_create(
            business_action=ba,
            tracker=tracker,
            defaults={
                'scenario': list_scenario,
                'input_mapping': {
                    'auth_obj': '{{ auth_obj }}',
                },
                'output_mapping': {
                    'active_campaigns': '{{ active_campaign_ids }}',
                },
            },
        )
        return ba

    def _ensure_pause_business_action(self, pause_scenario, tracker):
        ba, created = BusinessAction.objects.update_or_create(
            name=PAUSE_BA_NAME,
            defaults={
                'arguments': [AUTH_OBJ_ARG, CAMPAIGN_ID_ARG, OFFER_ID_ARG],
                'output_variables': [],
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created business action {ba.name}')

        BusinessActionVariant.objects.update_or_create(
            business_action=ba,
            tracker=tracker,
            defaults={
                'scenario': pause_scenario,
                'input_mapping': {
                    'auth_obj': '{{ auth_obj }}',
                    'id': '{{ id }}',
                    'offer_id': '{{ offer_id }}',
                },
                'output_mapping': {},
            },
        )
        return ba

    def _ensure_verify_business_action(self, verify_scenario, tracker):
        ba, created = BusinessAction.objects.update_or_create(
            name=VERIFY_BA_NAME,
            defaults={
                'arguments': [AUTH_OBJ_ARG, CAMPAIGN_ID_ARG, OFFER_ID_ARG],
                'output_variables': [],
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created business action {ba.name}')

        BusinessActionVariant.objects.update_or_create(
            business_action=ba,
            tracker=tracker,
            defaults={
                'scenario': verify_scenario,
                'input_mapping': {
                    'auth_obj': '{{ auth_obj }}',
                    'id': '{{ id }}',
                    'offer_id': '{{ offer_id }}',
                },
                'output_mapping': {},
            },
        )
        return ba

    def _ensure_assert_business_action(self, assert_scenario, tracker):
        ba, created = BusinessAction.objects.update_or_create(
            name=ASSERT_BA_NAME,
            defaults={
                'arguments': [],
                'output_variables': [{'name': 'verify_summary'}],
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created business action {ba.name}')

        BusinessActionVariant.objects.update_or_create(
            business_action=ba,
            tracker=tracker,
            defaults={
                'scenario': assert_scenario,
                'input_mapping': {},
                'output_mapping': {
                    'verify_summary': '{{ verify_summary }}',
                },
            },
        )
        return ba

    def _ensure_workflow(self, list_ba, pause_ba, verify_ba, assert_ba):
        workflow, created = Workflow.objects.update_or_create(
            name=WORKFLOW_NAME,
            defaults={
                'arguments': [AUTH_OBJ_ARG, OFFER_ID_ARG],
                'validation_status': 'VALID',
            },
        )
        if created:
            self.stdout.write(f'Created workflow {workflow.name}')

        WorkflowStep.objects.filter(workflow=workflow).delete()

        WorkflowStep.objects.create(
            workflow=workflow,
            order=0,
            business_action=list_ba,
            input_mapping={'auth_obj': '{{ auth_obj }}'},
            iterator_variable=None,
            output_variable_name='',
            tracker_from_argument='auth_obj',
            is_active=True,
        )
        WorkflowStep.objects.create(
            workflow=workflow,
            order=1,
            business_action=pause_ba,
            input_mapping={
                'auth_obj': '{{ auth_obj }}',
                'id': '{{ item.id }}',
                'offer_id': '{{ offer_id }}',
            },
            iterator_variable='active_campaigns',
            output_variable_name='pause_results',
            tracker_from_argument='auth_obj',
            is_active=True,
        )
        WorkflowStep.objects.create(
            workflow=workflow,
            order=2,
            business_action=verify_ba,
            input_mapping={
                'auth_obj': '{{ auth_obj }}',
                'id': '{{ item.id }}',
                'offer_id': '{{ offer_id }}',
            },
            iterator_variable='active_campaigns',
            output_variable_name='verify_results',
            tracker_from_argument='auth_obj',
            is_active=True,
        )
        WorkflowStep.objects.create(
            workflow=workflow,
            order=3,
            business_action=assert_ba,
            input_mapping={},
            iterator_variable=None,
            output_variable_name='verify_summary',
            tracker_from_argument='auth_obj',
            is_active=True,
        )
        return workflow
