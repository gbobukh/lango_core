import os
import django
import json
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lango_core.settings')
django.setup()

from service_builder.models import Workflow, Scenario
from service_builder.utils import WorkflowRunner

def run_debug():
    workflow_id = 3
    print(f"DEBUG: Running Workflow {workflow_id}...")
    
    # Fetch valid input
    from integrations.models import PartnerAccount
    pa = PartnerAccount.objects.filter(name__icontains='Traffichunt').first()
    if not pa:
        pa = PartnerAccount.objects.first()
        print(f"DEBUG: Traffichunt not found, using first available: {pa}")
    else:
        print(f"DEBUG: Found Input Object: {pa} (ID: {pa.pk})")
        
    variables = {
        'trafficSource_obj': pa.pk if pa else 1, # Pass PK as likely expected by Runner/TypedArgs
    }
    
    try:
        runner = WorkflowRunner(workflow_id, variables)
        result = runner.run()
        print("DEBUG: Execution Finished.")
        
        # Simulate View Serialization
        def _sanitize_for_json(data):
            if isinstance(data, dict):
                return {k: _sanitize_for_json(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [_sanitize_for_json(v) for v in data]
            elif isinstance(data, (str, int, float, bool, type(None))):
                return data
            else:
                return str(data)
                
        sanitized = _sanitize_for_json(result)
        print("DEBUG: Serialization Successful.")
        print(json.dumps(sanitized, indent=2))
        
    except Exception:
        print("DEBUG: CRASHED!")
        traceback.print_exc()
        
    except Exception:
        print("DEBUG: CRASHED!")
        traceback.print_exc()

if __name__ == '__main__':
    run_debug()
