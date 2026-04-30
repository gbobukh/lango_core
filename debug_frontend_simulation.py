import os
import django
import json
from django.conf import settings
from django.test import RequestFactory
# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lango_core.settings')
django.setup()

from django.contrib.auth.models import User
from service_builder.api import ModelDiscoveryView, ModelFieldsView

def test_frontend_flow():
    factory = RequestFactory()
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("No superuser found.")
        return

    # 1. Simulate Model Discovery
    print("--- 1. Model Discovery ---")
    request = factory.get('/api/models/')
    request.user = user
    view_discovery = ModelDiscoveryView.as_view()
    response = view_discovery(request)
    
    if response.status_code != 200:
        print(f"Discovery Failed: {response.status_code}")
        return

    data = json.loads(response.content)
    models = data.get('models', [])
    
    partner_model = None
    for m in models:
        print(f"Found Model: {m['full_name']} ({m['verbose_name']})")
        if m['full_name'] == 'integrations.partneraccount':
            partner_model = m
            break
            
    if not partner_model:
        print("CRITICAL: PartnerAccount model not found in discovery response!")
        return
        
    print(f"Target Model: {partner_model}")
    
    # 2. Simulate Field Fetch
    print("\n--- 2. Field Fetch ---")
    app_label = partner_model['app_label']
    model_name = partner_model['model_name']
    
    print(f"Fetching fields for: {app_label}.{model_name}")
    
    request = factory.get(f'/api/models/{app_label}/{model_name}/fields/')
    request.user = user
    view_fields = ModelFieldsView.as_view()
    response = view_fields(request, app_label=app_label, model_name=model_name)
    
    if response.status_code != 200:
        print(f"Field Fetch Failed: {response.status_code}")
        return
        
    data = json.loads(response.content)
    fields = data.get('fields', [])
    
    found = False
    print("\nAvailable Fields:")
    for f in fields:
        print(f"- {f['name']} ({f['verbose_name']})")
        if 'tracker_identifiers' in f['name']:
            found = True
            
    if found:
        print("\nSUCCESS: Tracker Identifiers found!")
    else:
        print("\nFAILURE: Tracker Identifiers NOT found.")

if __name__ == '__main__':
    test_frontend_flow()
