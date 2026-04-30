import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lango_core.settings')
django.setup()

from service_builder.models import Scenario, ServiceMethod, ServiceEndpoint

scenario_name = "binom - stats_token_X_in_traffic_source_X"

try:
    scenario = Scenario.objects.get(name=scenario_name)
    print(f"Scenario: {scenario.name} (ID: {scenario.id})")
    
    for step in scenario.steps.all().order_by('order'):
        if step.method:
            method = step.method
            endpoint = method.service_endpoint
            print(f"\nStep {step.order}: Method '{method.name}'")
            print(f"Endpoint: '{endpoint.name}' (ID: {endpoint.id})")
            print("Endpoint API Configuration:")
            if endpoint.api_configuration:
                print(json.dumps(endpoint.api_configuration, indent=2))
            else:
                print("  None (Empty)")
                
except Scenario.DoesNotExist:
    print(f"Scenario '{scenario_name}' not found.")
