import base64
import hashlib
import json
import itertools
import requests
import re
from urllib.parse import quote_plus, parse_qsl, urlencode, urlsplit, urlunsplit
from cryptography.fernet import Fernet
from django.conf import settings

PATH_TEMPLATE_PATTERN = re.compile(r'%([A-Za-z_][A-Za-z0-9_]*)%')
SENSITIVE_URL_KEYS = {'password', 'token', 'secret', 'api_key', 'access_token', 'refresh_token', 'auth', 'session'}

def _get_cipher():
    """
    Returns a Fernet cipher instance using a key derived from settings.SECRET_KEY.
    """
    # Ensure the key is 32 url-safe base64-encoded bytes
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    key_b64 = base64.urlsafe_b64encode(key)
    return Fernet(key_b64)

def encrypt_data(data):
    """
    Encrypts a dictionary or string.
    Returns the encrypted string.
    """
    if isinstance(data, (dict, list)):
        data = json.dumps(data)
    
    if not isinstance(data, str):
        data = str(data)
        
    cipher = _get_cipher()
    return cipher.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data):
    """
    Decrypts the data.
    Returns the original string (or JSON object if it was JSON).
    """
    if not encrypted_data:
        return None
        
    cipher = _get_cipher()
    decrypted_bytes = cipher.decrypt(encrypted_data.encode())
    decrypted_str = decrypted_bytes.decode()
    
    try:
        return json.loads(decrypted_str)
    except json.JSONDecodeError:
        return decrypted_str


def _render_path_templates(text, context):
    """
    Replace %key% placeholders in text from context dict.
    Returns: (rendered_text, used_keys, missing_keys)
    """
    if not isinstance(text, str):
        return text, set(), set()
    if not isinstance(context, dict):
        context = {}

    used_keys = set()
    missing_keys = set()

    def _replace(match):
        key = match.group(1)
        if key in context and context.get(key) is not None:
            used_keys.add(key)
            return str(context.get(key))
        missing_keys.add(key)
        return match.group(0)

    rendered = PATH_TEMPLATE_PATTERN.sub(_replace, text)
    return rendered, used_keys, missing_keys


def _mask_url_sensitive(url, sensitive_values=None):
    """Mask sensitive values in URL for safe logging/debug output."""
    if not isinstance(url, str):
        return url

    try:
        parsed = urlsplit(url)
        masked_query = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if any(marker in key.lower() for marker in SENSITIVE_URL_KEYS):
                masked_query.append((key, '***MASKED***'))
            else:
                masked_query.append((key, value))
        url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(masked_query, doseq=True), parsed.fragment))
    except Exception:
        pass

    for val in (sensitive_values or []):
        if val is None:
            continue
        sval = str(val)
        if sval:
            url = url.replace(sval, '***MASKED***')
    return url

def perform_auto_login(auth_id_obj):
    """
    Checks if the Auth ID's type has Active Auth configured.
    If so, executes the login request and returns the token.
    Returns: (token_value, inject_in, inject_key) or (None, None, None)
    """
    auth_type = auth_id_obj.auth_type
    if not auth_type.login_url:
        return None, None, None

    # Get credentials
    creds = auth_id_obj.get_credentials()
    if not isinstance(creds, dict):
        return None, None, None

    # Prepare Body
    payload = auth_type.login_payload
    # Simple recursive template replacement for dictionary values
    def replace_values(obj, context):
        if isinstance(obj, dict):
            return {k: replace_values(v, context) for k, v in obj.items()}
        elif isinstance(obj, str):
            # Replace {{ var }} with context[var]
            for key, val in context.items():
                obj = obj.replace(f"{{{{ {key} }}}}", str(val))
                obj = obj.replace(f"{{{{{key}}}}}", str(val))
            return obj
        return obj
        
    json_body = replace_values(payload, creds)

    # Prepare URL
    url = auth_type.login_url
    rendered_request_url, _, _ = _render_path_templates(auth_id_obj.request_url or '', creds)
    base_url = rendered_request_url.rstrip('/')
    url = url.replace("{base_url}", base_url)
    
    # Execute Request
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Content-Type': 'application/json'
        }
        response = requests.post(url, json=json_body, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract Token
        token_path = auth_type.token_path
        if token_path:
            keys = token_path.split('.')
            value = data
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                elif isinstance(value, list) and key.isdigit():
                    value = value[int(key)]
                else:
                    return None, None, None
            
            return value, auth_type.inject_in, auth_type.inject_key
            
    except Exception as e:
        print(f"Auto-login failed: {e}")
        return None, None, None

    return None, None, None


def _append_query_param(url, key, value):
    """Append a query parameter to URL with safe encoding."""
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}{quote_plus(str(key))}={quote_plus(str(value))}"


def apply_auth_to_request(auth_id_obj, url, headers=None, log_func=None):
    """
    Apply authentication from ApiAuthID to request url/headers.

    Active Authentication:
    - If login_url is configured and token is obtained, inject by auth_type.inject_in/inject_key.
    - PATH_TEMPLATE replaces %inject_key% directly in URL.

    Static Authentication:
    - For key_definitions credentials, inject by auth_type.static_inject_in.
    - PATH_TEMPLATE replaces %key_name% placeholders in URL.
    - To avoid mixing active/static semantics, static injection is applied only when login_url is empty.

    Returns: (url, headers)
    """
    if headers is None:
        headers = {}

    def _log(msg):
        if callable(log_func):
            try:
                log_func(msg)
            except Exception:
                pass

    auth_type = auth_id_obj.auth_type
    credentials = auth_id_obj.get_credentials() or {}
    static_inject_in = getattr(auth_type, 'static_inject_in', 'HEADER') or 'HEADER'
    used_path_keys = set()

    if (
        not getattr(auth_type, 'login_url', '')
        and static_inject_in == 'PATH_TEMPLATE'
        and isinstance(credentials, dict)
    ):
        url, used_path_keys, missing_path_keys = _render_path_templates(url, credentials)
        if used_path_keys:
            masked_url = _mask_url_sensitive(url, [credentials.get(k) for k in used_path_keys])
            _log(f"Static Auth: rendered PATH_TEMPLATE for keys {sorted(used_path_keys)} -> {masked_url}")
        if missing_path_keys:
            _log(f"Static Auth: PATH_TEMPLATE placeholders missing in credentials: {sorted(missing_path_keys)}")

    # Active Authentication (token flow)
    token, inject_in, inject_key = perform_auto_login(auth_id_obj)
    if token and inject_key:
        if inject_in == 'HEADER':
            headers[inject_key] = token
        elif inject_in == 'QUERY_PARAM':
            url = _append_query_param(url, inject_key, token)
        elif inject_in == 'PATH_TEMPLATE':
            placeholder = f"%{inject_key}%"
            if placeholder in url:
                url = url.replace(placeholder, str(token))
            else:
                _log(f"Active Auth: PATH_TEMPLATE placeholder {placeholder} not found in URL")
        _log(f"Active Auth: injected token via {inject_in} ({inject_key})")

    # Static Authentication (credentials/key_definitions)
    if not getattr(auth_type, 'login_url', '') and isinstance(credentials, dict):
        if static_inject_in == 'PATH_TEMPLATE':
            return url, headers
        for key_name in (auth_type.key_definitions or []):
            if key_name not in credentials:
                continue
            if key_name in used_path_keys:
                continue
            raw_val = credentials.get(key_name)
            if static_inject_in == 'QUERY_PARAM':
                url = _append_query_param(url, key_name, raw_val)
            else:
                headers[key_name] = raw_val

    return url, headers


def _mask_sensitive(obj, keys_to_mask=None):
    """Mask sensitive values for display. keys_to_mask: set of key names (e.g. password, token)."""
    if keys_to_mask is None:
        keys_to_mask = {'password', 'token', 'secret', 'api_key', 'access_token', 'refresh_token'}
    if isinstance(obj, dict):
        return {k: '***MASKED***' if any(m in k.lower() for m in keys_to_mask) else _mask_sensitive(v, keys_to_mask) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask_sensitive(v, keys_to_mask) for v in obj]
    return obj


def test_api_auth(auth_id_obj):
    """
    Test API Auth ID configuration. Returns a dict with test results.
    Used by the admin "Test Auth" functionality.
    Captures raw request/response for debugging.
    """
    result = {
        'success': False,
        'auth_name': str(auth_id_obj),
        'auth_type': auth_id_obj.auth_type.name,
        'checks': [],
        'error': None,
        'token_info': None,
        'request_details': None,
        'response_details': None,
        'auth_type_config': None,
        'token_extraction': None,
        'injection_preview': None,
        'mode': 'active' if auth_id_obj.auth_type.login_url else 'static',
    }

    auth_type = auth_id_obj.auth_type
    creds_for_mask = auth_id_obj.get_credentials()
    if not isinstance(creds_for_mask, dict):
        creds_for_mask = {}
    rendered_base_url, _, _ = _render_path_templates(auth_id_obj.request_url or '', creds_for_mask)
    masked_base_url = _mask_url_sensitive(rendered_base_url, creds_for_mask.values())

    # Check request_url
    if not auth_id_obj.request_url or not str(auth_id_obj.request_url).strip().startswith('http'):
        result['checks'].append({'name': 'request_url', 'ok': False, 'message': 'request_url is empty or invalid'})
    else:
        result['checks'].append({'name': 'request_url', 'ok': True, 'message': f'Base URL: {masked_base_url[:80]}...'})

    if auth_type.login_url:
        # Auth Type config (Active Authentication)
        result['auth_type_config'] = {
            'login_url': auth_type.login_url,
            'token_path': auth_type.token_path or '(not set)',
            'inject_in': auth_type.inject_in or 'HEADER',
            'inject_key': auth_type.inject_key or '(not set)',
        }

        # Active Auth mode - do login manually to capture raw request/response
        creds = auth_id_obj.get_credentials()
        if not isinstance(creds, dict):
            result['checks'].append({'name': 'credentials', 'ok': False, 'message': 'Credentials not found or invalid'})
            result['error'] = 'Credentials not configured'
            return result

        result['checks'].append({'name': 'credentials', 'ok': True, 'message': f'Keys present: {list(creds.keys())}'})

        url = auth_type.login_url
        base_url = rendered_base_url.rstrip('/')
        url = url.replace("{base_url}", base_url)

        def replace_values(obj, context):
            if isinstance(obj, dict):
                return {k: replace_values(v, context) for k, v in obj.items()}
            elif isinstance(obj, str):
                for key, val in context.items():
                    obj = obj.replace(f"{{{{ {key} }}}}", str(val))
                    obj = obj.replace(f"{{{{{key}}}}}", str(val))
                return obj
            return obj

        payload = auth_type.login_payload
        json_body = replace_values(payload, creds) if isinstance(payload, (dict, list)) else payload

        req_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json'
        }

        body_for_display = _mask_sensitive(json_body) if isinstance(json_body, (dict, list)) else json_body
        result['request_details'] = {
            'method': 'POST',
            'url': _mask_url_sensitive(url, creds.values()),
            'headers': dict(req_headers),
            'body': body_for_display,
            'body_str': json.dumps(body_for_display, indent=2, ensure_ascii=False) if isinstance(body_for_display, (dict, list)) else str(body_for_display or ''),
        }

        try:
            response = requests.post(url, json=json_body, headers=req_headers, timeout=10)
            try:
                resp_body = response.json()
            except Exception:
                resp_body = response.text[:5000] if response.text else '(empty)'

            body_str = json.dumps(resp_body, indent=2, ensure_ascii=False) if isinstance(resp_body, (dict, list)) else str(resp_body or '')
            result['response_details'] = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'body': resp_body,
                'body_str': body_str,
            }

            response.raise_for_status()
            data = response.json()

            token_path = auth_type.token_path
            if token_path:
                keys = token_path.split('.')
                value = data
                path_steps = []
                for key in keys:
                    prev_type = type(value).__name__
                    if isinstance(value, dict):
                        value = value.get(key)
                        path_steps.append({'step': key, 'in': prev_type, 'found': value is not None})
                    elif isinstance(value, list) and key.isdigit():
                        value = value[int(key)]
                        path_steps.append({'step': key, 'in': prev_type, 'found': True})
                    else:
                        result['token_extraction'] = {
                            'path': token_path,
                            'steps': path_steps,
                            'extracted_value': None,
                            'error': f"key '{key}' not found in {prev_type}",
                        }
                        result['error'] = f"token_path '{token_path}': key '{key}' not found"
                        result['checks'].append({'name': 'login', 'ok': False, 'message': result['error']})
                        return result

                if value and auth_type.inject_key:
                    token_preview = str(value)[:12] + '...' if len(str(value)) > 12 else str(value)[:4] + '***'
                    result['success'] = True
                    result['token_info'] = {
                        'inject_in': auth_type.inject_in or 'HEADER',
                        'inject_key': auth_type.inject_key,
                        'token_preview': token_preview,
                    }
                    result['token_extraction'] = {
                        'path': token_path,
                        'steps': path_steps,
                        'extracted_value': token_preview,
                    }
                    inject_in = auth_type.inject_in or 'HEADER'
                    inject_key = auth_type.inject_key
                    if inject_in == 'HEADER':
                        result['injection_preview'] = f"{inject_key}: {str(value)[:25]}..." if len(str(value)) > 25 else f"{inject_key}: {value}"
                    else:
                        result['injection_preview'] = f"?{inject_key}={str(value)[:25]}..." if len(str(value)) > 25 else f"?{inject_key}={value}"
                    result['checks'].append({
                        'name': 'login',
                        'ok': True,
                        'message': f'Token received, will inject into {inject_in} as "{inject_key}"',
                    })
                else:
                    result['token_extraction'] = {
                        'path': token_path,
                        'steps': path_steps,
                        'extracted_value': None,
                        'error': 'Value empty or inject_key not set',
                    }
                    result['error'] = 'Token path resolved but value empty or inject_key not set'
                    result['checks'].append({'name': 'login', 'ok': False, 'message': result['error']})
            else:
                result['error'] = 'token_path not configured'
                result['checks'].append({'name': 'login', 'ok': False, 'message': result['error']})

        except requests.RequestException as e:
            result['error'] = str(e)
            result['checks'].append({'name': 'login', 'ok': False, 'message': str(e)})
            if result['response_details'] is None and hasattr(e, 'response') and e.response is not None:
                resp = e.response
                body_str = (resp.text[:5000] if resp.text else '(empty)') if hasattr(resp, 'text') else str(e)
                result['response_details'] = {
                    'status_code': getattr(resp, 'status_code', None),
                    'headers': dict(resp.headers) if hasattr(resp, 'headers') else {},
                    'body': body_str,
                    'body_str': body_str,
                }
    else:
        # Static credentials (API key, Bearer Token)
        creds = auth_id_obj.get_credentials()
        if not isinstance(creds, dict) or not creds:
            result['checks'].append({'name': 'credentials', 'ok': False, 'message': 'Credentials not configured'})
            result['error'] = 'No credentials stored'
            return result

        if auth_type.name == 'API key':
            missing = [k for k in (auth_type.key_definitions or []) if k not in creds or not creds.get(k)]
            if missing:
                result['error'] = f'Missing keys: {missing}'
                result['checks'].append({'name': 'credentials', 'ok': False, 'message': result['error']})
            else:
                result['success'] = True
                result['checks'].append({
                    'name': 'credentials',
                    'ok': True,
                    'message': f'API key configured for: {list(auth_type.key_definitions or [])}',
                })
        elif auth_type.name == 'Bearer Token':
            token = creds.get('token') or creds.get('access_token')
            if not token:
                result['error'] = 'No token in credentials (expected "token" or "access_token")'
                result['checks'].append({'name': 'credentials', 'ok': False, 'message': result['error']})
            else:
                result['success'] = True
                result['checks'].append({
                    'name': 'credentials',
                    'ok': True,
                    'message': 'Bearer token configured',
                })
        else:
            result['success'] = True
            result['checks'].append({
                'name': 'credentials',
                'ok': True,
                'message': f'Credentials stored for type "{auth_type.name}"',
            })

        preview_url, preview_headers = apply_auth_to_request(auth_id_obj, rendered_base_url, headers={})
        result['injection_preview'] = {
            'url': _mask_url_sensitive(preview_url, creds.values()),
            'headers': _mask_sensitive(preview_headers),
        }

    return result


import uuid

def _get_uuid_in_url_v2(url):
    """
    Extracts UUID from URL using regex.
    Logic ported from user script.
    """
    if not url:
        return ""
    match = re.search(r'key=([a-f0-9]+)', url)
    if match:
        full_key = match.group(1)
        return full_key[:10]
    return "UNKNOWN"



def generate_pub_links(my_campaign_url, base_campaign_name, config):
    """
    Generates publisher links dynamically based on extracted config.
    Args:
        my_campaign_url (str): The base campaign URL.
        base_campaign_name (str): The prefix for generated campaign names.
        config (dict): The configuration dictionary (extracted from PublisherConfig).
    """
    from metadata.models import TargetParameter
    
    # 1. Identify active parameters from config
    # config structure: {"ParamName": {"exists": bool, "ttz_encoded": bool}}
    active_params = [] # List of tuples (param_name, values_list)
    
    if not config:
        return []
    # config structure: {"ParamName": {"exists": bool, "ttz_encoded": bool}}
    active_params = [] # List of tuples (param_name, values_list)
    
    if not config:
        return []

    # Sort keys to ensure consistent order of combinations
    # (e.g. always Device then OS, if named that way)
    # Ideally should rely on some explicit ordering, but alphabetical is stable for now.
    sorted_param_names = sorted(config.keys())
    
    for param_name in sorted_param_names:
        settings = config.get(param_name, {})
        # Check if parameter is marked as TTZ Encoded (and implies Exists)
        if settings.get('exists') and settings.get('ttz_encoded'):
            try:
                # Fetch defined values from TargetParameter model
                tp = TargetParameter.objects.get(name=param_name)
                # Ensure values is a list
                values = tp.values if isinstance(tp.values, list) else []
                if values:
                    active_params.append((param_name, values))
            except TargetParameter.DoesNotExist:
                # Config references a parameter that was deleted? Skip.
                continue
    
    # If no parameters are encoded, maybe return a single 'default' segment?
    # Or return empty? Original logic implied specific segments.
    # If list is empty, product is empty.
    if not active_params:
        # Fallback or specific logic if needed. For now, empty list.
        return []

    results = []
    short_id = _get_uuid_in_url_v2(my_campaign_url)

    # 2. Build Cartesian Product
    param_names = [p[0] for p in active_params]
    value_lists = [p[1] for p in active_params]
    
    # itertools.product(*[[a,b], [1,2]]) -> (a,1), (a,2), (b,1), (b,2)
    combinations = itertools.product(*value_lists)
    
    # Fetch Compatibility Rules for active parameters
    # Optimization: Fetch all rules involving active parameters to avoid N+1 queries
    from metadata.models import CompatibilityMatrix
    # We care about rules where subject AND target are in our active list
    rules = CompatibilityMatrix.objects.filter(
        subject_parameter__name__in=param_names,
        target_parameter__name__in=param_names
    ).select_related('subject_parameter', 'target_parameter')

    # Build a lookup for fast checking
    # { (SubjectParam, SubjectVal): { TargetParam: [AllowedValues] } }
    # e.g. { ("OS", "iOS"): { "Device Type": ["Mobile", "Tablet"] } }
    rule_map = {}
    for r in rules:
        key = (r.subject_parameter.name, r.subject_value)
        if key not in rule_map:
            rule_map[key] = {}
        # Assuming one rule per target param per subject value (or merge them)
        rule_map[key][r.target_parameter.name] = r.allowed_values

    final_results = []

    for combo in combinations:
        # combo is a tuple of values corresponding to param_names
        # Create a dict for easy lookup: { "OS": "iOS", "Device Type": "Desktop" }
        combo_dict = dict(zip(param_names, combo))
        
        is_valid = True
        
        # Check Compatibility
        for subject_param, subject_val in combo_dict.items():
            # Check if this value triggers any rules
            if (subject_param, subject_val) in rule_map:
                constraints = rule_map[(subject_param, subject_val)]
                
                # Check each constraint
                for target_param, allowed_values in constraints.items():
                    # If the target parameter is present in this combination
                    if target_param in combo_dict:
                        actual_val = combo_dict[target_param]
                        if actual_val not in allowed_values:
                            # Rule Violation!
                            is_valid = False
                            break
            if not is_valid:
                break
        
        if not is_valid:
            continue

        # 3. Construct Segment Name
        # Join values with space. Filter out empty/None values.
        segment_name_parts = [str(v) for v in combo if v]
        segment_name = " ".join(segment_name_parts)
        
        # Generate random ID
        segment_id = str(uuid.uuid4()).split('-')[0]
        
        # Construct Campaign Name
        # e.g. "My Base Campaign Mobile Android 1a2b3c"
        # Uses base_campaign_name passed in arguments
        pub_campaign_name = f"{base_campaign_name} {segment_name} {segment_id}"
        
        # 4. Construct URL
        pub_campaign_url = my_campaign_url.replace('MYCSDID', short_id)
        pub_campaign_url = pub_campaign_url.replace('MYSGMID', segment_id)
        
        # 5. Build Result Dictionary
        item = {
            'name': pub_campaign_name,
            'url': pub_campaign_url,
            'segment_id': segment_id
        }
        
        # Add dynamic keys for each parameter
        for i, val in enumerate(combo):
            # Key: param name in lower_snake_case (e.g. "Device Type" -> "device_type")
            raw_key = param_names[i]
            safe_key = raw_key.lower().replace(' ', '_')
            item[safe_key] = val
            
        final_results.append(item)
        
    return final_results

def get_partner_tracker_identifiers(partner_account, auth_context=None):
    """
    Helper function to find a Tracker Identifier for a PartnerAccount
    matching a specific Auth Context.
    
    Args:
        partner_account (PartnerAccount): The partner object.
        auth_context: Can be ApiAuthID object, Tracker object, or just an ID/String name.
        
    Returns:
        PartnerAccountTrackerIdentifier or None
    """
    if not partner_account:
        return None

    # Resolve Tracker from auth_context
    target_tracker = None
    target_auth = None
    
    from .models import ApiAuthID, Tracker, PartnerAccountTrackerIdentifier
    
    # Debug print
    # print(f"Finding identifier for {partner_account.name} context: {auth_context} ({type(auth_context)})")

    if isinstance(auth_context, ApiAuthID):
        target_auth = auth_context
        target_tracker = auth_context.tracker
    elif isinstance(auth_context, Tracker):
        target_tracker = auth_context
    elif hasattr(auth_context, 'tracker'): 
        # Handle objects that might have a tracker attribute (like some proxies)
        target_tracker = auth_context.tracker
    
    identifiers = partner_account.tracker_identifiers.all()
    
    # 1. Try Exact Auth ID Match (Most specific)
    if target_auth:
        for ident in identifiers:
            if ident.api_auth_id_id == target_auth.id:
                return ident
                
    # 2. Try Tracker Match (Less specific)
    if target_tracker:
        for ident in identifiers:
            # Check if identifier's auth is linked to the same tracker
            if ident.api_auth_id and ident.api_auth_id.tracker_id == target_tracker.id:
                return ident
                
    # 3. Fallback: If auth_context is None, return first? 
    # Or strict None? Let's return first if exists, to be helpful in simple cases.
    if auth_context is None and identifiers.exists():
        return identifiers.first()
        
    return None


def get_partner_name_by_account_name_in_tracker(account_name_in_tracker, auth_context=None):
    """
    Find PartnerAccount.name by the account name used in the tracker.

    Args:
        account_name_in_tracker: str — value that matches
            PartnerAccountTrackerIdentifier.account_name_in_tracker (e.g. affiliate_network from offers).
        auth_context: ApiAuthID, Tracker, or int (ApiAuthID pk). If given, only identifiers
            for this auth/tracker are considered.

    Returns:
        str or None — PartnerAccount.name if found, else None.
    """
    if not account_name_in_tracker or not str(account_name_in_tracker).strip():
        return None

    from .models import PartnerAccountTrackerIdentifier, ApiAuthID, Tracker

    qs = PartnerAccountTrackerIdentifier.objects.filter(
        account_name_in_tracker=str(account_name_in_tracker).strip()
    ).select_related('partner_account')

    if auth_context is not None:
        if isinstance(auth_context, int):
            auth_context = ApiAuthID.objects.filter(pk=auth_context).first()
        if isinstance(auth_context, ApiAuthID):
            qs = qs.filter(api_auth_id=auth_context)
        elif isinstance(auth_context, Tracker):
            qs = qs.filter(api_auth_id__tracker=auth_context)
        elif hasattr(auth_context, 'tracker'):
            qs = qs.filter(api_auth_id__tracker=auth_context.tracker)

    ident = qs.first()
    return ident.partner_account.name if ident else None


def extract_domain(url):
    """
    Extract domain (host without port) from a URL string.
    Safe for use in scenario expressions (e.g. Transform calculate).

    Args:
        url: str — full URL (e.g. https://sub.example.com:8080/path?q=1).

    Returns:
        str or None — e.g. "sub.example.com", or None if url is empty/invalid.
    """
    if not url or not str(url).strip():
        return None
    from urllib.parse import urlparse
    parsed = urlparse(str(url).strip())
    netloc = parsed.netloc or (parsed.path.split('/')[0] if parsed.path else '')
    return netloc.split(':')[0] or None
