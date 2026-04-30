import os
import django
import sys

# Setup Django environment
sys.path.append('/root/lango_core')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lango_core.settings')
django.setup()

from service_builder.models import ServiceEndpoint

def migrate_endpoints():
    endpoints = ServiceEndpoint.objects.all()
    count = 0
    print(f"Found {endpoints.count()} endpoints to check.")
    
    for ep in endpoints:
        # Only migrate if resource_path is empty
        if not ep.resource_path:
            print(f"Migrating: {ep.name} ({ep.endpoint})")
            ep.resource_path = ep.endpoint
            # Ensure parameters is a list
            if ep.parameters is None:
                 ep.parameters = []
            
            # Save using update_fields to avoid triggering any unrelated logic (though safe currently)
            ep.save(update_fields=['resource_path', 'parameters'])
            count += 1
            
    print(f"Successfully migrated {count} endpoints.")

if __name__ == "__main__":
    migrate_endpoints()
