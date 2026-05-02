"""
Views for Run Tests page and related API endpoints.
"""
import json
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import ServiceEndpoint, ServiceMethod, Scenario, Workflow, BusinessAction
from integrations.models import ApiAuthID


def _sanitize_for_json(data):
    """Convert data to JSON-serializable form."""
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sanitize_for_json(v) for v in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    else:
        return str(data)


@method_decorator(staff_member_required, name='dispatch')
class TestEndpointView(LoginRequiredMixin, View):
    template_name = 'admin/service_builder/test_endpoint.html'

    def get(self, request):
        method_id = request.GET.get('method_id')
        scenario_id = request.GET.get('scenario_id')
        workflow_id = request.GET.get('workflow_id')
        action_id = request.GET.get('action_id')

        auth_choices = []
        for a in ApiAuthID.objects.all().select_related('auth_type'):
            auth_choices.append({'id': a.pk, 'label': a.account_name or str(a.pk)})

        scenario_arguments_json = '[]'
        method_arguments_json = '[]'
        method_endpoint_url = ''
        method_http_method = 'GET'
        entity_name = 'Select a scenario, workflow or action'
        if method_id:
            try:
                m = ServiceMethod.objects.select_related('service_endpoint').get(pk=method_id)
                entity_name = f"{m.name} ({m.service_endpoint.method} {m.service_endpoint.endpoint})"
                method_arguments_json = json.dumps(m.arguments if m.arguments else [])
                method_endpoint_url = m.service_endpoint.endpoint or ''
                method_http_method = m.service_endpoint.method or 'GET'
            except ServiceMethod.DoesNotExist:
                pass
        elif scenario_id:
            try:
                s = Scenario.objects.get(pk=scenario_id)
                entity_name = s.name
                scenario_arguments_json = json.dumps(s.arguments if s.arguments else [])
            except Scenario.DoesNotExist:
                pass
        elif workflow_id:
            try:
                w = Workflow.objects.get(pk=workflow_id)
                entity_name = w.name
                scenario_arguments_json = json.dumps(w.arguments if w.arguments else [])
            except Workflow.DoesNotExist:
                pass
        elif action_id:
            try:
                a = BusinessAction.objects.get(pk=action_id)
                entity_name = a.name
                scenario_arguments_json = json.dumps(a.arguments if a.arguments else [])
            except BusinessAction.DoesNotExist:
                pass

        context = {
            'auth_choices': auth_choices,
            'scenario_id': scenario_id or '',
            'workflow_id': workflow_id or '',
            'action_id': action_id or '',
            'method_id': method_id or '',
            'scenario_arguments_json': scenario_arguments_json,
            'method_arguments_json': method_arguments_json,
            'method_endpoint_url': method_endpoint_url,
            'method_http_method': method_http_method,
            'entity_name': entity_name,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        method_id = data.get('method_id')
        scenario_id = data.get('scenario_id')
        workflow_id = data.get('workflow_id')
        action_id = data.get('action_id')
        auth_id = data.get('auth_id')
        variables = data.get('variables') or {}

        if auth_id:
            variables['auth_id'] = auth_id

        runner = None
        try:
            from .utils import WorkflowRunner, ScenarioRunner

            if workflow_id:
                runner = WorkflowRunner(int(workflow_id), variables)
                result = runner.run()
            elif scenario_id:
                runner = ScenarioRunner(int(scenario_id), variables)
                result = runner.run()
            elif action_id:
                from .models import BusinessActionVariant
                from .utils import (
                    _apply_output_mapping,
                    _resolve_template,
                    _resolve_tracker_from_arg_name,
                    WorkflowRunner,
                )
                action = BusinessAction.objects.get(pk=action_id)
                api_auth_names = action.get_apiauthid_argument_names()
                arg_name = api_auth_names[0] if api_auth_names else ''
                tracker = _resolve_tracker_from_arg_name(arg_name, variables)
                tracker_id = tracker.id if tracker else None
                variant = BusinessActionVariant.objects.filter(
                    business_action=action,
                    tracker_id=tracker_id
                ).first() if tracker_id else None
                if not variant:
                    variant = BusinessActionVariant.objects.filter(business_action=action).first()
                if variant and variant.scenario:
                    expected_scenario_args = WorkflowRunner._extract_argument_names(
                        variant.scenario.arguments if variant.scenario else []
                    )
                    variant_mapping, _ = WorkflowRunner._filter_mapping_by_allowed_keys(
                        variant.input_mapping or {},
                        expected_scenario_args,
                    )

                    scenario_args = {}
                    for key, template in variant_mapping.items():
                        if isinstance(template, str) and '{{' in template:
                            hint = (
                                f"BusinessAction '{action.name}', variant input_mapping "
                                f"'{key}': {template}"
                            )
                            resolved = _resolve_template(
                                template,
                                variables,
                                raise_on_missing=True,
                                context_hint=hint,
                            )
                            if isinstance(resolved, (dict, list)):
                                scenario_args[key] = resolved
                            elif isinstance(resolved, str) and resolved.strip().startswith(('{', '[')):
                                try:
                                    scenario_args[key] = json.loads(resolved)
                                except json.JSONDecodeError:
                                    scenario_args[key] = resolved
                            else:
                                scenario_args[key] = resolved
                        else:
                            scenario_args[key] = template

                    runner = ScenarioRunner(variant.scenario_id, {**variables, **scenario_args})
                    result = runner.run()
                    if variant.output_mapping:
                        hint = f"BusinessAction '{action.name}', variant output_mapping"
                        mapped_outputs = _apply_output_mapping(result, variant.output_mapping, context_hint=hint)
                        if isinstance(result, dict):
                            result['outputs'] = mapped_outputs
                            ctx = result.get('context')
                            if isinstance(ctx, dict):
                                ctx.update(mapped_outputs)
                            cvars = result.get('context_variables')
                            if isinstance(cvars, dict):
                                cvars.update(mapped_outputs)
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'No scenario variant found for this action',
                        'logs': [],
                        'context_variables': {},
                        'external_requests': []
                    })
            elif method_id:
                from .utils import execute_single_method
                method = ServiceMethod.objects.get(pk=method_id)
                endpoint_id = method.service_endpoint_id
                result = execute_single_method(int(endpoint_id), int(method_id), variables)
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'No method, scenario, workflow or action specified',
                    'logs': [],
                    'context_variables': {},
                    'external_requests': []
                })

            out = {
                'success': result.get('success', True),
                'error': result.get('error'),
                'logs': result.get('logs', []),
                'context': result.get('context', {}),
                'context_variables': result.get('context_variables', result.get('context', {})),
                'external_requests': result.get('external_requests', result.get('api_calls', [])),
                'api_calls': result.get('external_requests', result.get('api_calls', [])),
                'outputs': result.get('outputs'),
            }
            out.update({k: v for k, v in result.items() if k not in out})
            return JsonResponse(_sanitize_for_json(out))

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            context_vars = {}
            ext_requests = []
            logs_list = [f'Error: {str(e)}', tb]
            if runner is not None:
                context_vars = getattr(runner, 'context', {})
                ext_requests = getattr(runner, 'external_requests', [])
                logs_list = list(getattr(runner, 'logs', [])) + logs_list
            return JsonResponse(_sanitize_for_json({
                'success': False,
                'error': str(e),
                'traceback': tb,
                'logs': logs_list,
                'context_variables': context_vars,
                'external_requests': ext_requests
            }))
        except BaseException as e:
            import traceback
            tb = traceback.format_exc()
            context_vars = {}
            ext_requests = []
            logs_list = [f'Error: {type(e).__name__}: {e}', tb]
            if runner is not None:
                context_vars = getattr(runner, 'context', {})
                ext_requests = getattr(runner, 'external_requests', [])
                logs_list = list(getattr(runner, 'logs', [])) + logs_list
            return JsonResponse(_sanitize_for_json({
                'success': False,
                'error': f'{type(e).__name__}: {e}',
                'traceback': tb,
                'logs': logs_list,
                'context_variables': context_vars,
                'external_requests': ext_requests
            }))


@method_decorator(staff_member_required, name='dispatch')
class GetMethodArgumentsView(LoginRequiredMixin, View):
    def get(self, request, method_id):
        try:
            method = ServiceMethod.objects.get(pk=method_id)
            return JsonResponse({'arguments': method.arguments or []})
        except ServiceMethod.DoesNotExist:
            return JsonResponse({'arguments': []})


@method_decorator(staff_member_required, name='dispatch')
class GetMethodsListView(LoginRequiredMixin, View):
    def get(self, request):
        qs = ServiceMethod.objects.select_related('service_endpoint').filter(validation_status__in=['VALID', 'TEST'])
        if not request.user.is_superuser:
            qs = qs.filter(visible_to=request.user).distinct()

        methods = []
        for method in qs.order_by('name'):
            endpoint = method.service_endpoint
            endpoint_label = ""
            if endpoint is not None:
                endpoint_label = f"{endpoint.method} {endpoint.endpoint}"
            methods.append({
                'id': method.pk,
                'name': method.name,
                'label': f"{method.name} ({endpoint_label})" if endpoint_label else method.name,
            })
        return JsonResponse({'methods': methods})


@method_decorator(staff_member_required, name='dispatch')
class GetScenarioArgumentsView(LoginRequiredMixin, View):
    def get(self, request, scenario_id):
        try:
            scenario = Scenario.objects.get(pk=scenario_id)
            return JsonResponse({'arguments': scenario.arguments or []})
        except Scenario.DoesNotExist:
            return JsonResponse({'arguments': []})


@method_decorator(staff_member_required, name='dispatch')
class GetScenarioDetailsView(LoginRequiredMixin, View):
    def get(self, request, scenario_id):
        try:
            scenario = Scenario.objects.get(pk=scenario_id)
            last_step = scenario.steps.filter(is_active=True).order_by('order').last()
            return_vars = [last_step.output_variable_name] if (last_step and last_step.output_variable_name) else []
            return JsonResponse({
                'arguments': scenario.arguments or [],
                'return_variables': return_vars
            })
        except Scenario.DoesNotExist:
            return JsonResponse({'arguments': [], 'return_variables': []})


@method_decorator(staff_member_required, name='dispatch')
class ResolveActionVariantView(LoginRequiredMixin, View):
    def get(self, request):
        from .models import BusinessActionVariant
        action_id = request.GET.get('action_id')
        tracker_id = request.GET.get('tracker_id')
        if not action_id:
            return JsonResponse({'error': 'action_id required'}, status=400)
        variant = BusinessActionVariant.objects.filter(
            business_action_id=action_id,
            tracker_id=tracker_id or None
        ).first()
        if not variant:
            variant = BusinessActionVariant.objects.filter(business_action_id=action_id).first()
        if variant:
            return JsonResponse({
                'scenario_id': variant.scenario_id,
                'arguments': variant.scenario.arguments if variant.scenario else []
            })
        return JsonResponse({'scenario_id': None, 'arguments': []})


@method_decorator(staff_member_required, name='dispatch')
class GetBusinessActionArgumentsView(LoginRequiredMixin, View):
    def get(self, request, action_id):
        try:
            action = BusinessAction.objects.get(pk=action_id)
            return JsonResponse({'arguments': action.arguments or []})
        except BusinessAction.DoesNotExist:
            return JsonResponse({'arguments': []})
