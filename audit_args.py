import os
import django
from django.apps import apps
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lango_core.settings")
django.setup()

from service_builder.models import Scenario, Workflow, BusinessAction

def check_uniqueness(model_path, lookup_field):
    if not model_path:
        return "?"
    if not lookup_field:
        return "N/A (Object)"
    
    try:
        app_label, model_name = model_path.split('.')
        Model = apps.get_model(app_label, model_name)
        
        try:
            field = Model._meta.get_field(lookup_field)
            if field.unique or field.primary_key:
                return "YES"
            else:
                return "NO"
        except:
             # Look for Property
             if hasattr(Model, lookup_field):
                 # Properties are not DB fields
                 return "False (Property)"
             return "Error: Field Not Found"
    except Exception as e:
        return f"Error: {e}"

def audit():
    rows = []
    # Header
    rows.append(["Entity Name", "Type", "Argument", "Model", "Lookup Field", "Is Unique?"])
    
    # 1. Scenarios
    for s in Scenario.objects.all():
        args = s.arguments or []
        for arg in args:
            if isinstance(arg, dict) and arg.get('type') == 'model':
                lookup = arg.get('lookup')
                unique_status = check_uniqueness(arg.get('model'), lookup)
                rows.append([s.name, "Scenario", arg.get('name'), arg.get('model'), lookup or "(Object)", unique_status])

    # 2. Business Actions
    for ba in BusinessAction.objects.all():
        args = ba.arguments or []
        for arg in args:
            if isinstance(arg, dict) and arg.get('type') == 'model':
                lookup = arg.get('lookup')
                unique_status = check_uniqueness(arg.get('model'), lookup)
                rows.append([ba.name, "BizAction", arg.get('name'), arg.get('model'), lookup or "(Object)", unique_status])

    # 3. Workflows
    for w in Workflow.objects.all():
        args = w.arguments or []
        for arg in args:
            if isinstance(arg, dict) and arg.get('type') == 'model':
                lookup = arg.get('lookup')
                unique_status = check_uniqueness(arg.get('model'), lookup)
                rows.append([w.name, "Workflow", arg.get('name'), arg.get('model'), lookup or "(Object)", unique_status])

    # Print Table
    col_widths = [30, 15, 25, 30, 20, 15]
    
    # Header
    header = ""
    for i, col in enumerate(rows[0]):
        header += str(col).ljust(col_widths[i]) + " | "
    print(header)
    print("-" * len(header))
    
    # Rows
    for row in rows[1:]:
        line = ""
        for i, col in enumerate(row):
            line += str(col)[:col_widths[i]-1].ljust(col_widths[i]) + " | "
        print(line)

if __name__ == "__main__":
    audit()
