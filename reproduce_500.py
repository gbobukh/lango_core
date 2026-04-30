import os
import django
import requests

# Setup Django (for logging, though we won't use models likely)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lango_core.settings')
django.setup()

from service_builder.utils import ScenarioRunner, format_value_with_config
from types import SimpleNamespace

# Mock Classes
class MockMethod:
    name = "Test Method"
    arguments = []
    service_endpoint = SimpleNamespace(endpoint="/campaign/123", method="GET")
    return_key = None

class MockStep:
    method = MockMethod()
    argument_mapping = {}
    auth_context_variable = "source_auth" # Mismatch!

class MockRunner:
    context = {"source_auth_obj": "some_auth"} # Missing "source_auth"
    logs = []
    def log(self, msg):
        print(f"LOG: {msg}")
        self.logs.append(msg)
    
    # Borrowing the logic from utils.py _execute_single_api_call
    # extracting relevant parts to confirm crash
    def execute_api(self, step):
        # ... logic ...
        url = step.method.service_endpoint.endpoint
        auth_var = step.auth_context_variable
        auth_id = self.context.get(auth_var)
        
        # Logic says: if auth_id is None, we log warning but PROCEED
        if not auth_id:
            self.log(f"Warning: Relative URL used but no Auth ID found in context variable '{auth_var}'.")
        
        # ... skip auth injection ...
        
        req_kwargs = {
            'method': 'GET',
            'url': url, # "/campaign/123"
        }
        
        print(f"Attempting request to: {url}")
        # This should CRASH
        response = requests.request(**req_kwargs)
        return response

print("--- RUNNING REPRODUCTION ---")
runner = MockRunner()
try:
    runner.execute_api(MockStep())
except requests.exceptions.MissingSchema:
    print("--- SUCCESS: CAUGHT Expected MissingSchema Error! ---")
    print("This confirms that unhandled requests.request causes a crash.")
except Exception as e:
    print(f"--- FAILED with other error: {e}")
