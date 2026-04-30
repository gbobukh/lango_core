from django.db import models
from django.contrib.auth.models import User

class ApiAuthType(models.Model):
    """
    Defines a type of authentication for external APIs (e.g., 'Basic Auth', 'Bearer Token').
    Stores the structure of keys required, but not the values themselves.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the authentication type (e.g., 'OAuth2', 'API Key')")
    
    INJECT_IN_CHOICES = [
        ('HEADER', 'Header'),
        ('QUERY_PARAM', 'Query Parameter'),
        ('PATH_TEMPLATE', 'Path Template'),
    ]

    # Stores a list of key names required. e.g., ["client_id", "client_secret"]
    key_definitions = models.JSONField(
        default=list, 
        blank=True, 
        help_text="List of key names required for this auth type (e.g., ['api_key'] or ['username', 'password'])"
    )
    static_inject_in = models.CharField(
        max_length=20,
        choices=INJECT_IN_CHOICES,
        default='HEADER',
        blank=True,
        help_text=(
            "For static credentials (key_definitions): where to inject keys into the main request. "
            "PATH_TEMPLATE replaces %key_name% placeholders in request URL."
        )
    )
    
    # Visibility permission
    visible_to = models.ManyToManyField(
        User, 
        related_name='visible_auth_types', 
        blank=True,
        help_text="Users who can view and use this authentication type."
    )
    
    # Active Auth (Auto-Login) Configuration
    login_url = models.CharField(
        max_length=500, 
        blank=True, 
        help_text="URL to Login/Get Token (e.g. https://api.site.com/login). Supports {base_url}."
    )
    login_payload = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="JSON Body for Login. Use {{ username }} and {{ password }} as placeholders."
    )
    token_path = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="JSON Path to extract token from response (e.g. data.token or access_token)"
    )
    
    inject_in = models.CharField(
        max_length=20, 
        choices=INJECT_IN_CHOICES, 
        default='HEADER',
        blank=True,
        help_text=(
            "Where to inject the token in the main request. "
            "PATH_TEMPLATE replaces %inject_key% in URL."
        )
    )
    inject_key = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="Key name for injection (e.g. 'Authorization' or 'api_key')"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-discover keys from login_url and login_payload
        if self.login_url or self.login_payload:
            import re
            discovered_keys = set()
            regex = r'\{\{\s*([^}]+?)\s*\}\}'
            
            # Check URL
            if self.login_url:
                matches = re.findall(regex, self.login_url)
                discovered_keys.update(m.strip() for m in matches)
                
            # Check Payload
            if self.login_payload:
                def extract_keys(obj):
                    if isinstance(obj, str):
                        matches = re.findall(regex, obj)
                        return set(m.strip() for m in matches)
                    elif isinstance(obj, dict):
                        keys = set()
                        for v in obj.values():
                            keys.update(extract_keys(v))
                        return keys
                    elif isinstance(obj, list):
                        keys = set()
                        for v in obj:
                            keys.update(extract_keys(v))
                        return keys
                    return set()

                discovered_keys.update(extract_keys(self.login_payload))
            
            # Remove system variables if any (e.g. base_url)
            discovered_keys.discard('base_url')
            
            # Update key_definitions
            # We strictly set it to discovered keys if we are in Active Auth mode
            if discovered_keys:
                self.key_definitions = sorted(list(discovered_keys))
                
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "API Auth Type"
        verbose_name_plural = "API Auth Types"


class Tracker(models.Model):
    """
    Represents a tracking entity (e.g., an external system or campaign).
    Currently stores only the name.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the tracker")
    
    api_configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tracker-specific API configuration (e.g. output_formats)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    visible_to = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='accessible_trackers'
    )

    def __str__(self):
        return self.name

    @property
    def keys(self):
        """
        Shortcut to access the associated TrackerConfig mapping.
        Usage in template: {{ tracker.keys.STD_VAR }}
        """
        if hasattr(self, 'tracker_config'):
            return self.tracker_config.mapping
        return {}

    class Meta:
        verbose_name = "Tracker"
        verbose_name_plural = "Trackers"


class ApiAuthID(models.Model):
    """
    Stores credentials for a specific API connection (Auth ID).
    Credentials are encrypted at rest.
    """
    account_name = models.CharField(
        max_length=255, 
        unique=True,
        help_text="Account to which you connect with the API"
    )
    tracker = models.ForeignKey(
        Tracker, 
        on_delete=models.CASCADE,
        related_name='auth_ids'
    )
    request_url = models.URLField(
        help_text=(
            "The base URL for requests. Supports %credential_key% placeholders, "
            "for example: https://api.telegram.org/bot%token%."
        )
    )
    auth_type = models.ForeignKey(
        ApiAuthType, 
        on_delete=models.PROTECT,
        related_name='auth_ids'
    )
    credentials_encrypted = models.TextField(blank=True)
    
    visible_to = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='accessible_auth_ids'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_credentials(self, credentials_dict):
        from .utils import encrypt_data
        self.credentials_encrypted = encrypt_data(credentials_dict)

    def get_credentials(self):
        from .utils import decrypt_data
        if not self.credentials_encrypted:
            return {}
        return decrypt_data(self.credentials_encrypted)

    def __str__(self):
        return f"{self.account_name} ({self.auth_type.name})"

    class Meta:
        verbose_name = "API Auth ID"
        verbose_name_plural = "API Auth IDs"


class PartnerAccount(models.Model):
    """
    Represents a partner account (e.g., an advertiser or publisher account).
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the partner account")
    
    account_type = models.ForeignKey(
        'PartnerAccountType',
        on_delete=models.PROTECT,
        related_name='partner_accounts',
        help_text="Type of the partner account",
        null=True
    )
    domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional domain associated with this account (e.g., for publishers)"
    )

    visible_to = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='accessible_partner_accounts'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Partner Account ID"
        verbose_name_plural = "Partner Account IDs"


class PartnerAccountType(models.Model):
    """
    Defines a type of partner account (e.g., 'Advertiser', 'Publisher').
    Currently stores only the name.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the partner account type")
    
    visible_to = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='accessible_partner_account_types'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Partner Account Type"
        verbose_name_plural = "Partner Account Types"


class PartnerAccountTrackerIdentifier(models.Model):
    """
    Links a PartnerAccount to a Tracker, storing the specific ID and name used in that tracker.
    """
    partner_account = models.ForeignKey(
        PartnerAccount,
        on_delete=models.CASCADE,
        related_name='tracker_identifiers'
    )
    api_auth_id = models.ForeignKey(
        ApiAuthID,
        on_delete=models.PROTECT,
        related_name='partner_identifiers',
        help_text="The specific API connection (Tracker + Credentials) where this partner exists.",
        null=True
    )
    identifying_method = models.ForeignKey(
        'service_builder.ServiceMethod',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Method used to fetch the account name automatically"
    )
    account_id_in_tracker = models.CharField(
        max_length=255,
        help_text="ID of this account in the specific tracker"
    )
    account_name_in_tracker = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of this account in the specific tracker (fetched from API)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-fetch account name if method is selected
        if self.identifying_method and self.api_auth_id and self.account_id_in_tracker:
            try:
                import requests
                from .utils import decrypt_data
                
                method = self.identifying_method
                endpoint = method.service_endpoint
                auth = self.api_auth_id
                
                # Prepare URL
                url = endpoint.endpoint
                # Replace {id} or %id% with account_id_in_tracker
                url = url.replace("{id}", self.account_id_in_tracker)
                url = url.replace("%id%", self.account_id_in_tracker)
                
                # Base URL handling
                if not url.startswith('http'):
                    base_url = auth.request_url.rstrip('/')
                    url = f"{base_url}/{url.lstrip('/')}"
                
                # Headers
                headers = {}
                if auth.credentials_encrypted:
                    creds = decrypt_data(auth.credentials_encrypted)
                    if isinstance(creds, dict):
                        for k, v in creds.items():
                            headers[k] = v
                            
                # Execute
                response = requests.request(endpoint.method.upper(), url, headers=headers)
                
                if response.ok and method.return_key:
                    try:
                        json_data = response.json()
                        keys = method.return_key.split('.')
                        value = json_data
                        for key in keys:
                            if isinstance(value, dict):
                                value = value.get(key)
                            elif isinstance(value, list) and key.isdigit():
                                value = value[int(key)]
                            else:
                                value = None
                                break
                        
                        if value:
                            self.account_name_in_tracker = str(value)
                    except Exception as e:
                        print(f"Error parsing response: {e}")
                        
            except Exception as e:
                print(f"Error fetching account name: {e}")
                
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.partner_account.name} in {self.api_auth_id}"

    class Meta:
        verbose_name = "Tracker Identifier"
        verbose_name_plural = "Tracker Identifiers"
        unique_together = ('partner_account', 'api_auth_id')


class SystemConfig(models.Model):
    """
    Stores global system configuration as Key-Value pairs.
    Example: Key='date_input_formats', Value=['%d-%m-%Y', '%Y-%m-%d']
    """
    key = models.CharField(max_length=255, unique=True, help_text="Configuration key (e.g. 'date_input_formats')")
    value = models.JSONField(default=dict, help_text="Configuration value (JSON)")
    description = models.TextField(blank=True, help_text="Description of what this setting controls")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key

    class Meta:
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configurations"

