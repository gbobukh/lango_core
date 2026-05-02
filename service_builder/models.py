from django.db import models
from django.contrib.auth.models import User
from integrations.models import Tracker

# Shared by ScenarioStep.action_type and ActionConfigLibrary.action_type (must match ActionRunner).
SCENARIO_ACTION_TYPE_CHOICES = [
    ('MERGE', 'Merge List'),
    ('FILTER', 'Filter List'),
    ('TRANSFORM', 'Transform Data'),
    ('DIFF_OBJECTS', 'Diff Objects'),
    ('ENRICH', 'Enrich List (Join & Append)'),
    ('HIERARCHICAL_FLATTEN', 'Hierarchical Flatten (Parent→Child)'),
    ('MULTI_HIERARCHICAL_FLATTEN', 'Multi-Hierarchical Flatten (N levels)'),
    ('GROUP_BY', 'Group By (Aggregate)'),
    ('FLATTEN_COLLECTION', 'Flatten Collection (Expand List Field)'),
    ('FIND_OIDH', 'Find OIDH'),
    ('BUILD_OIDH_BLACKLIST', 'Build OIDH Blacklist'),
    ('DICT_TO_LIST', 'Dict to List'),
]


class ValidationStatusMixin(models.Model):
    VALIDATION_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VALID', 'Valid'),
        ('INVALID', 'Invalid'),
        ('TEST', 'Test (Manual Only)'),
    ]

    validation_status = models.CharField(
        max_length=10,
        choices=VALIDATION_STATUS_CHOICES,
        default='PENDING',
        help_text="Status of the entity validation."
    )

    class Meta:
        abstract = True

    def get_critical_fields(self):
        """
        Returns a list of field names that, when changed, should reset validation status to PENDING.
        Must be overridden by subclasses.
        """
        return []

    def update_validation_status(self, success: bool):
        """
        Unified method to update status based on test result.
        Uses update_fields to update the status safely without side effects on other fields.
        """
        new_status = 'VALID' if success else 'INVALID'
        
        # Only update if changed
        if self.validation_status != new_status:
            self.validation_status = new_status
            # We use save(update_fields=...) which invokes the model's save() method 
            # but usually limits the SQL UPDATE to just these fields.
            # Our Mixin's save() logic checks for CRITICAL FIELD changes. 
            # Since we aren't changing critical fields, it won't reset to PENDING.
            self.save(update_fields=['validation_status'])


    def save(self, *args, **kwargs):
        # 1. OPTIMIZATION: If we are only updating validation_status, skip the check
        if 'update_fields' in kwargs and kwargs['update_fields'] and 'validation_status' in kwargs['update_fields']:
             # If validation_status is the ONLY thing being updated, definitely skip
             if len(kwargs['update_fields']) == 1:
                 super().save(*args, **kwargs)
                 return

        if self.pk:
            try:
                # 2. Use defined critical fields if available
                if hasattr(self, 'get_critical_fields'):
                    critical_fields = self.get_critical_fields()
                else:
                    # Fallback introspection
                    all_fields = [f.name for f in self._meta.fields]
                    excluded_fields = ['id', 'name', 'validation_status', 'created_at', 'updated_at', 'visible_to', 'endpoint']
                    critical_fields = [f for f in all_fields if f not in excluded_fields]
                
                if critical_fields:
                    # Fetch old data specifically for these fields
                    old_data = self.__class__.objects.filter(pk=self.pk).values(*critical_fields).first()
                    if old_data:
                        for field in critical_fields:
                            old_val = old_data.get(field)
                            new_val = getattr(self, field)
                            
                            # Type safety for comparison (e.g. None vs '')
                            if old_val != new_val:
                                # Reset to PENDING unless explicitly set to TEST
                                if self.validation_status != 'TEST':
                                    self.validation_status = 'PENDING'
                                break
            except Exception as e:
                # Fallback: if introspection fails, do nothing or log
                print(f"Validation Check Error: {e}")
                pass
        super().save(*args, **kwargs)
class ServiceEndpoint(ValidationStatusMixin, models.Model):
    # VALIDATION_STATUS_CHOICES moved to Mixin
    
    # validation_status inherited from Mixin

    def get_critical_fields(self):
         return ['name', 'method', 'resource_path', 'parameters']

    @property
    def is_locked(self):
        """Locked if used by any Method."""
        return self.validation_status == 'VALID' and self.methods.exists()

    METHOD_CHOICES = [
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('PATCH', 'PATCH'),
        ('DELETE', 'DELETE'),
    ]

    tracker = models.ForeignKey(
        Tracker,
        on_delete=models.CASCADE,
        related_name='service_endpoints',
        help_text="The tracker this endpoint belongs to"
    )
    name = models.CharField(
        max_length=255,
        help_text="Name of the endpoint (e.g., Get Traffic Source)"
    )
    method = models.CharField(
        max_length=10,
        choices=METHOD_CHOICES,
        default='GET',
        help_text="HTTP method for the request"
    )
    resource_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Invariant part of the URL (e.g., /api/v1/traffic)"
    )
    parameters = models.JSONField(
        default=list,
        blank=True,
        help_text="List of query parameters (e.g., ['dateFrom', 'dateTo'])"
    )
    endpoint = models.CharField(
        max_length=500,
        help_text="Full API endpoint path (Auto-generated)"
    )
    api_configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuration for API data formatting (e.g. date formats, modifiers)"
    )
    
    visible_to = models.ManyToManyField(
        User,
        blank=True,
        related_name='visible_service_endpoints',
        help_text="Users who can view this endpoint"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Strict Generation of Endpoint
        if not self.parameters:
            self.endpoint = self.resource_path
        else:
            # Construct query string: param={param}
            query_parts = []
            # Ensure parameters is a list
            params = self.parameters if isinstance(self.parameters, list) else []
            for param in params:
                if not param:
                    continue
                
                # Check for key=val1,val2 syntax
                if '=' in param:
                    key, values_str = param.split('=', 1)
                    values = [v.strip() for v in values_str.split(',')]
                    for val in values:
                         query_parts.append(f"{key}={val}")
                else:
                    # Default variable behavior
                    query_parts.append(f"{param}={{{param}}}")
            
            if query_parts:
                separator = '&' if '?' in self.resource_path else '?'
                self.endpoint = f"{self.resource_path}{separator}{'&'.join(query_parts)}"
            else:
                self.endpoint = self.resource_path
                
        super().save(*args, **kwargs)

    def get_arguments(self):
        import re
        url = self.endpoint
        # Find {var} or %var%
        regex = r'\{([^}]+)\}|%([^%]+)%'
        matches = re.findall(regex, url)
        # Flatten matches and filter empty strings
        args_found = []
        for match in matches:
            # match is a tuple ('var', '') or ('', 'var')
            var = match[0] or match[1]
            if var and var not in args_found:
                args_found.append(var)
        
        # Auto-add 'payload' argument for POST/PUT/PATCH
        if self.method in ['POST', 'PUT', 'PATCH']:
            if 'payload' not in args_found:
                args_found.append('payload')
        
        return args_found

    def __str__(self):
        return f"{self.name} ({self.method} {self.endpoint})"

    class Meta:
        verbose_name = "Endpoint"
        verbose_name_plural = "Endpoints"


class ServiceMethod(ValidationStatusMixin, models.Model):
    name = models.CharField(
        max_length=255,
        help_text="Name of the method (e.g., Get Account Name)"
    )
    # validation_status inherited
    
    def get_critical_fields(self):
        return ['name', 'service_endpoint_id', 'return_key', 'payload_fields']

    @property
    def is_locked(self):
        """Locked if used by any Scenario Step."""
        return self.validation_status == 'VALID' and self.scenario_steps.exists()

    service_endpoint = models.ForeignKey(
        ServiceEndpoint,
        on_delete=models.CASCADE,
        related_name='methods',
        help_text="The endpoint this method uses"
    )
    return_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="JSON key to return (e.g., data.name). Leave empty to return full response."
    )
    arguments = models.JSONField(
        default=list,
        blank=True,
        help_text="List of arguments discovered from the endpoint URL"
    )
    
    payload_fields = models.JSONField(
        default=list,
        blank=True,
        null=True,
        help_text="List of fields to be constructed in the JSON body (e.g. ['body.name', 'body.data.id'])"
    )
    
    visible_to = models.ManyToManyField(
        User,
        blank=True,
        related_name='visible_service_methods',
        help_text="Users who can view this method"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-discover arguments from endpoint URL
        if self.service_endpoint:
            # Get URL arguments
            url_args = self.service_endpoint.get_arguments()
            # Combine with payload fields
            # Ensure unique and preserve order
            combined_args = list(url_args)
            
            payload_fields = self.payload_fields or []
            
            # If we have specific payload fields (body.*), we should NOT include the generic 'payload' argument
            # This prevents confusion in the UI and Test Terminal
            if payload_fields and 'payload' in combined_args:
                combined_args.remove('payload')

            for field in payload_fields:
                if field not in combined_args:
                    combined_args.append(field)
            
            self.arguments = combined_args
            
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Method"
        verbose_name_plural = "Methods"


class Scenario(ValidationStatusMixin, models.Model):
    name = models.CharField(
        max_length=255,
        help_text="Name of the scenario (e.g., Clone Campaign & Offer)"
    )
    arguments = models.JSONField(
        default=list,
        blank=True,
        help_text="List of arguments required by this scenario (e.g., ['source_campaign_id', 'geo'])"
    )
    visible_to = models.ManyToManyField(
        User,
        blank=True,
        related_name='visible_scenarios',
        help_text="Users who can view this scenario"
    )
    # validation_status inherited

    def get_critical_fields(self):
        return ['name', 'arguments']

    @property
    def is_locked(self):
        """Locked if used by a Workflow Step or Business Action Variant."""
        # Note: related_name for WorkflowStep.scenario is default (workflowstep_set)
        # Note: related_name for BusinessActionVariant.scenario is default (businessactionvariant_set)
        return self.validation_status == 'VALID' and (
            self.workflowstep_set.exists() or self.businessactionvariant_set.exists()
        )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def validate(self):
        """
        Validates the scenario and returns (is_valid, errors).
        Updates self.is_valid but does not save the model.
        """
        errors = []
        steps = self.steps.all().order_by('order')
        
        if not steps:
            errors.append("Scenario must have at least one step.")
            
        # Extract argument names
        arg_names = []
        for arg in self.arguments:
            if isinstance(arg, dict):
                arg_names.append(arg.get('name'))
            else:
                arg_names.append(arg)
                
        context_vars = set(arg_names)
        unused_args = set(arg_names)
        
        for step in steps:
            method = step.method
            mapping = step.argument_mapping or {}
            modifications = step.response_modification or {}
            
            # Validate Argument Mapping
            import re
            template_regex = r'\{\{\s*([^}]+?)\s*\}\}'
            
            if method:
                for arg in method.arguments:
                    if arg not in mapping:
                        errors.append(f"Step {step.order} ({method.name}): Argument '{arg}' is not mapped.")
                    else:
                        mapped_value = mapping[arg]
                        # We now support templates, so mapped_value is likely a string.
                        # We only validate variables inside {{ }}.
                        if isinstance(mapped_value, str):
                            matches = re.findall(template_regex, mapped_value)
                            for var_name in matches:
                                var_name = var_name.strip()
                                # Handle dot notation: check only the root variable
                                root_var = var_name.split('.')[0]
                                
                                if root_var not in context_vars:
                                    errors.append(f"Step {step.order} ({method.name}): Variable '{var_name}' in template '{mapped_value}' not found in context.")
                                
                                # Mark as used (we only track root vars for unused check)
                                if root_var in unused_args:
                                    unused_args.remove(root_var)
                        else:
                            # Fallback for legacy or direct JSON values (if any)
                            pass
            else:
                # ACTION Step Validation (Basic)
                pass
            
            # Validate Response Modification
            step_name = method.name if method else f"Action {step.action_type}"
            for json_path, context_var in modifications.items():
                if context_var not in context_vars:
                    errors.append(f"Step {step.order} ({step_name}): Modification variable '{context_var}' not found in context.")
                if context_var in unused_args:
                    unused_args.remove(context_var)
            
            # Add output to context
            if step.output_variable_name:
                context_vars.add(step.output_variable_name)
            
            # Add extracted context variables to context
            extraction = step.context_extraction or {}
            for var_name in extraction.keys():
                context_vars.add(var_name)
        
        # Validation Logic (Soft Check)
        # We no longer block saving or mark as invalid based on static analysis,
        # because optional arguments (especially body.*) are valid to omit.
        
        # We return 'warnings' instead of 'errors' to be semantically correct for the UI.
        warnings = errors 
        return True, warnings, unused_args

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Scenario"
        verbose_name_plural = "Scenarios"


class ActionConfigLibrary(models.Model):
    """
    Reusable presets for Scenario action steps (action_type + action_config).
    ScenarioStep is unchanged until integration; entries are documentation/catalog only for now.
    """
    name = models.CharField(
        max_length=255,
        help_text="Unique label within this action type (e.g. 'Merge campaigns with stats').",
    )
    description = models.TextField(
        blank=True,
        help_text="What this preset does and which context variables it expects.",
    )
    action_type = models.CharField(
        max_length=50,
        choices=SCENARIO_ACTION_TYPE_CHOICES,
        help_text="Must match an ActionRunner action type.",
    )
    action_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON passed to ActionRunner for this action_type (same shape as ScenarioStep.action_config).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Hide outdated presets without deleting them.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['action_type', 'name']
        verbose_name = "Action config library entry"
        verbose_name_plural = "Action config library"
        constraints = [
            models.UniqueConstraint(
                fields=['action_type', 'name'],
                name='uniq_actionconfiglibrary_action_type_name',
            ),
        ]

    def __str__(self):
        return f"{self.action_type}: {self.name}"


class ScenarioStep(models.Model):
    scenario = models.ForeignKey(
        Scenario,
        on_delete=models.CASCADE,
        related_name='steps'
    )
    STEP_TYPE_CHOICES = [
        ('API_CALL', 'API Call'),
        ('ACTION', 'Action'),
        ('API_BATCH', 'API Batch'),
    ]
    step_type = models.CharField(
        max_length=20,
        choices=STEP_TYPE_CHOICES,
        default='API_CALL',
        help_text="Type of step: API Call (single HTTP request), Action (internal processing), or API Batch (multiple API calls by routing)."
    )
    
    action_type = models.CharField(
        max_length=50,
        choices=SCENARIO_ACTION_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Type of action to perform (if Step Type is Action)"
    )
    action_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuration for the action (e.g. Merge keys, inputs). Format: JSON."
    )
    
    iterator_variable = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Variable name of the list to iterate over (e.g. 'campaigns'). If set, this step runs for each item."
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to temporarily disable this step during testing."
    )

    order = models.PositiveIntegerField(
        default=0,
        help_text="Order of execution"
    )
    
    # Method is now optional for Actions
    method = models.ForeignKey(
        ServiceMethod,
        on_delete=models.PROTECT,
        related_name='scenario_steps',
        blank=True,
        null=True,
        help_text="The Service Method to call (Required if Step Type is API Call)"
    )
    argument_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Mapping of method arguments to context variables (e.g., {'id': 'source_campaign_id'})"
    )
    response_modification = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name="Response Injection",
        help_text="Map internal JSON paths to context variables (e.g. {'data.id': 'new_id'}). Injects context values INTO the response."
    )
    context_extraction = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text="Extract data from result into context variables. Format: {'var_name': 'expression'}. Example: {'first_id': 'result[0][\"id\"]'}."
    )
    success_condition = models.TextField(
        blank=True,
        help_text="Python-like expression to validate the result (e.g., result['status'] == 'success'). Available variables: result, context."
    )
    condition_error_message = models.CharField(
        max_length=255,
        blank=True,
        help_text="Message to display if the condition fails."
    )
    output_variable_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the variable to store the result in Context (e.g., 'new_campaign_id')"
    )
    auth_context_variable = models.CharField(
        max_length=255,
        default='auth_id',
        blank=True,
        help_text="Name of the Context Variable that contains the ApiAuthID to use for this step. Defaults to 'auth_id'."
    )
    error_handlers = models.JSONField(
        default=list,
        blank=True,
        help_text="For API Call: list of handlers for non-2xx responses. Each: status_codes, body_match (optional), action (return_body|return_value), value (if return_value). Empty = current behaviour (raise)."
    )

    def save(self, *args, **kwargs):
        # Guard against form/widget edge cases sending explicit null.
        if self.error_handlers is None:
            self.error_handlers = []
        super().save(*args, **kwargs)

    def __str__(self):
        prefix = f"Step {self.order}: "
        if self.step_type == 'ACTION':
            name = self.get_action_type_display() or 'Unknown Action'
        elif self.step_type == 'API_BATCH':
            name = 'API Batch'
        else:
            name = str(self.method) if self.method else 'Unconfigured API Step'
        return f"{prefix}{name}"

    class Meta:
        ordering = ['order']
        verbose_name = "Scenario Step"
        verbose_name_plural = "Scenario Steps"



class Workflow(ValidationStatusMixin, models.Model):
    name = models.CharField(
        max_length=255,
        help_text="Name of the workflow (e.g., Publisher Onboarding)"
    )
    # validation_status inherited

    @property
    def is_locked(self):
        """
        Workflow is the highest-level entity and is rarely used by others.
        It should remain editable even if Valid.
        If we eventually add 'Sub-Workflows', we can check usage there.
        """
        return False

    def get_inputs(self):
        """
        Returns the manually defined arguments for this Workflow.
        """
        return self.arguments

    def get_critical_fields(self):
        return ['name']

    arguments = models.JSONField(
        default=list,
        blank=True,
        help_text="Define arguments required to start this workflow. These will be available in the initial context."
    )

    def get_apiauthid_argument_names(self):
        """Return argument names of type model=integrations.apiauthid for tracker_from_argument dropdown."""
        result = []
        for arg in self.arguments or []:
            if not isinstance(arg, dict):
                continue
            if arg.get('type') != 'model':
                continue
            model = (arg.get('model') or '').lower()
            if 'apiauthid' in model or 'apiauth' in model:
                name = arg.get('name')
                if name:
                    result.append(name)
        return result

    # return_variables = ...

    visible_to = models.ManyToManyField(
        User,
        blank=True,
        related_name='visible_workflows',
        help_text="Users who can view this workflow"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class WorkflowStep(models.Model):
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name='steps'
    )
    order = models.PositiveIntegerField(default=0)
    scenario = models.ForeignKey(
        Scenario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Default Scenario to execute. Required if no routing logic is defined or matches."
    )

    business_action = models.ForeignKey(
        'BusinessAction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Abstract Business Action to perform (resolves to a Scenario based on Tracker)."
    )
    input_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map Workflow Context variables to Action Arguments. format: {'action_arg': '{{ context_var }}'}"
    )
    iterator_variable = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Context variable name (list) to iterate over. The Scenario will run for each item."
    )
    output_variable_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of variable to store the result in Workflow Context."
    )
    tracker_from_argument = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the workflow argument (ApiAuthID) from which to derive tracker for variant selection. "
                  "If empty, variant falls back to GENERAL."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to skip this step."
    )

    class Meta:
        ordering = ['order']
        verbose_name = "Workflow Step"
        verbose_name_plural = "Workflow Steps"

    def __str__(self):
        if self.business_action:
            return f"Step {self.order}: {self.business_action.name}"
        if self.scenario:
            return f"Step {self.order}: {self.scenario.name} (Legacy)"
        return f"Step {self.order}: (No Action)"

class BusinessAction(ValidationStatusMixin, models.Model):
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Name of the Abstract Action (e.g. 'Create Campaign')"
    )
    # validation_status inherited
    
    arguments = models.JSONField(
        default=list,
        blank=True,
        help_text="List of arguments required by this action (e.g., ['campaign_name', 'offer_id'])"
    )

    visible_to = models.ManyToManyField(
        User,
        blank=True,
        related_name='visible_business_actions',
        help_text="Users who can view this action"
    )

    @property
    def is_locked(self):
        """Locked if used by any Workflow."""
        return self.validation_status == 'VALID' and self.workflowstep_set.exists()

    def save(self, *args, **kwargs):
        if not self.arguments:
            self.arguments = []
        super().save(*args, **kwargs)

    def get_critical_fields(self):
        return ['name', 'arguments', 'output_variables']

    output_variables = models.JSONField(
        default=list,
        blank=True,
        help_text="List of output variables provided by this action (e.g., ['campaign_id', 'url'])"
    )

    def __str__(self):
        return self.name

    def get_apiauthid_argument_names(self):
        """Return argument names of type model=integrations.apiauthid (for single-action test)."""
        result = []
        for arg in self.arguments or []:
            if not isinstance(arg, dict):
                continue
            if arg.get('type') != 'model':
                continue
            model = (arg.get('model') or '').lower()
            if 'apiauthid' in model or 'apiauth' in model:
                name = arg.get('name')
                if name:
                    result.append(name)
        return result

class BusinessActionVariant(models.Model):
    business_action = models.ForeignKey(
        BusinessAction,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    scenario = models.ForeignKey(
        Scenario,
        on_delete=models.PROTECT,
        help_text="Scenario that implements this action."
    )
    tracker = models.ForeignKey(
        Tracker,
        on_delete=models.PROTECT,
        help_text="Tracker for which this scenario is applicable."
    )
    
    input_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map Business Action Args to Scenario Args. Key=ScenarioArg (Target), Val={{ActionArg}} (Source)"
    )
    
    output_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map Scenario Results to Business Action Outputs. Key=ActionOutput (Target), Val={{ScenarioReturn}} (Source)"
    )

    class Meta:
        unique_together = ('business_action', 'tracker')

    def __str__(self):
        return f"{self.tracker.name} -> {self.scenario.name}"

# WorkflowStep Update: Add business_action field
# (We cannot easily inject into the existing class def without using replace on the definition block)
# So I will REPLACE the WorkflowStep class definition fully.

