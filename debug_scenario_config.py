import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lango_core.settings")
django.setup()

from service_builder.models import Scenario

try:
    scenario = Scenario.objects.get(name="test")
    print(f"Scenario: {scenario.name} (ID: {scenario.id})")
    for step in scenario.steps.all().order_by('order'):
        print(f"Step {step.order} Type: {step.step_type}")
        if step.step_type == 'ACTION':
            print(f"Action Type: {step.action_type}")
            print(f"Action Config (Raw): {step.action_config}")
            print(f"Action Config Type: {type(step.action_config)}")
            if isinstance(step.action_config, dict):
                 calc = step.action_config.get('calculate')
                 print(f"Calculate Field: {calc}")
                 print(f"Calculate Type: {type(calc)}")
except Scenario.DoesNotExist:
    print("Scenario 'test' not found.")
