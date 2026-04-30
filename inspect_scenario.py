import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lango_core.settings')
django.setup()

from service_builder.models import Workflow, Scenario, BusinessAction

# 1. Find the Child Scenario
# User mentioned Workflow ID 3 in URL from screenshot
try:
    workflow = Workflow.objects.get(pk=3)
    print(f"Workflow: {workflow.name} (ID: 3)")
    
    # User said Step 3 calls the scenario
    step_3 = workflow.steps.filter(order=3).first()
    if not step_3:
        print("Step 3 not found in Workflow 3. Listing all steps:")
        for s in workflow.steps.all():
            print(f" - Step {s.order}: {s.business_action.name if s.business_action else 'No Action'}")
    else:
        print(f"Step 3 Action: {step_3.business_action.name}")
        # Find Scenario from Action
        # Assuming direct Resolvable? Or Variant?
        # Let's check variants
        variants = step_3.business_action.variants.all()
        target_scenario = None
        for v in variants:
            print(f" - Variant ID: {v.id} (Tracker: {v.tracker.name if v.tracker else 'General'}) -> Scenario: {v.scenario.name} (ID: {v.scenario.id})")
            target_scenario = v.scenario # Just pick the last one for now or check logic
            
        if target_scenario:
            print(f"\n--- Inspecting Scenario: {target_scenario.name} ---")
            for step in target_scenario.steps.all().order_by('order'):
                print(f"Step {step.order} ({step.step_type}):")
                print(f"  Method: {step.method.name if step.method else 'None'}")
                print(f"  Auth Context Var: '{step.auth_context_variable}'")
                print(f"  Iterator Var: {step.iterator_variable}")
                print(f"  Args Mapping: {step.argument_mapping}")
                if step.method:
                   print(f"  Endpoint: {step.method.service_endpoint.endpoint} [{step.method.service_endpoint.method}]")

except Exception as e:
    print(f"Error: {e}")
