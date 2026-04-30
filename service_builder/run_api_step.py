    def _execute_api_step(self, step):
        method = step.method
        if not method:
             # Should not happen if validated
             raise Exception("Step type is API_CALL but no method is defined.")
             
        self.log(f"Running Step {step.order}: {method.name}")
        
        # Resolve arguments
        mapping = step.argument_mapping or {}
        method_args = {}
        for arg_name in method.arguments:
            if arg_name in mapping:
                raw_value = mapping[arg_name]
                
                # Template parsing logic
                if isinstance(raw_value, str) and ('{{' in raw_value or '{' in raw_value):
                    # It might be a template or a JSON string
                    # We use a simple regex to replace {{ var }} with context values
                    
                    # Check for exact variable match first (to preserve type)
                    # Use [^}]+ to avoid matching multiple variables as one (e.g. "{{ a }} {{ b }}")
                    exact_match = re.fullmatch(r'\{\{\s*([^}]+?)\s*\}\}', raw_value.strip())
                    if exact_match:
                        var_name = exact_match.group(1).strip()
                        val = self._get_context_value(var_name)
                        if val is not self._SENTINEL:
                            method_args[arg_name] = val
                        else:
                            self.log(f"Warning: Variable '{var_name}' not found in context.")
                            method_args[arg_name] = raw_value # Keep original if not found
                    
                    elif '{{' in raw_value:
                        # We need to handle multiple variables in one string (String Interpolation)
                        
                        def replace_match(match):
                            var_name = match.group(1).strip()
                            val = self._get_context_value(var_name)
                            if val is not self._SENTINEL:
                                return str(val)
                            else:
                                self.log(f"Warning: Variable '{var_name}' not found in context.")
                                return "" # Or keep original?
                        
                        # Replace {{ var }}
                        resolved_value = re.sub(r'\{\{\s*(.+?)\s*\}\}', replace_match, raw_value)
                        
                        # Try to parse as JSON if it looks like one
                        if (resolved_value.strip().startswith('{') and resolved_value.strip().endswith('}')) or \
                           (resolved_value.strip().startswith('[') and resolved_value.strip().endswith(']')):
                            try:
                                method_args[arg_name] = json.loads(resolved_value)
                            except json.JSONDecodeError:
                                # Fallback to string
                                method_args[arg_name] = resolved_value
                        else:
                            method_args[arg_name] = resolved_value
                    else:
                         # Should not happen given the if condition, but just in case
                         method_args[arg_name] = raw_value
                        
                elif raw_value in self.context:
                    # Direct mapping (Legacy or simple variable name)
                    method_args[arg_name] = self.context[raw_value]
                else:
                    # Literal string or JSON primitive (number, boolean)
                    try:
                        # Try to parse as JSON to support numbers (6), booleans (true), etc.
                        method_args[arg_name] = json.loads(raw_value)
                    except (json.JSONDecodeError, TypeError):
                        # Fallback to literal string
                        method_args[arg_name] = raw_value
                         
            else:
                # Check if this is 'payload' and we have 'body.*' arguments mapped
                # If so, we can ignore the missing 'payload' argument
                if arg_name == 'payload':
                    has_body_args = any(k.startswith('body.') for k in mapping.keys())
                    if has_body_args:
                        continue
                
                # Optional Body Arguments (PATCH Support)
                # If a 'body.*' argument is not mapped, we simply ignore it (don't send it)
                if arg_name.startswith('body.'):
                    continue

                error = f"Argument '{arg_name}' is not mapped"
                self.log(f"Error: {error}")
                # Replaced return with raise
                raise Exception(error)
        
        # Execute Method
        endpoint = method.service_endpoint
        url = endpoint.endpoint
        
        # Replace URL variables
        for arg, val in method_args.items():
            # If the argument is 'payload', we skip URL replacement
            if arg == 'payload':
                continue
            if f"{{{arg}}}" in url:
                url = url.replace(f"{{{arg}}}", str(val))
            elif f"%{arg}%" in url:
                url = url.replace(f"%{arg}%", str(val))
        
        # Prepend base URL if needed
        if not url.startswith('http'):
            from integrations.models import ApiAuthID
            auth_id = self.context.get('auth_id')
            if not auth_id:
                raise Exception(
                    f"Invalid URL '{url}': No scheme supplied. "
                    f"Relative URLs require auth_id in context."
                )
            auth_obj = ApiAuthID.objects.get(pk=auth_id)
            base_url = (auth_obj.request_url or '').strip().rstrip('/')
            if not base_url or not base_url.startswith('http'):
                raise Exception(
                    f"ApiAuthID '{auth_obj.account_name}' has empty or invalid request_url. "
                    f"Set the base URL (e.g. https://api.example.com) in Auth ID configuration."
                )
            url = f"{base_url}/{url.lstrip('/')}"
            self.log(f"Prepended base URL from Auth ID: {base_url}")

        # Prepare request
        req_kwargs = {
            'method': endpoint.method,
            'url': url,
            # 'headers': ... (Auth headers are handled by integrations/utils logic usually, but here we might need to inject them)
        }
        
        # Handle Payload
        payload_data = None
        
        # 1. Check for legacy 'payload' argument
        if 'payload' in method_args:
            payload_data = method_args['payload']
            # If payload is a string, try to parse it as JSON
            if isinstance(payload_data, str):
                try:
                    payload_data = json.loads(payload_data)
                except json.JSONDecodeError:
                    self.log("Warning: Payload is a string but not valid JSON. Sending as string.")
                    pass
        
        # 2. Check for 'body.*' arguments (Deep Mapping)
        # These take precedence or merge? Let's say they form the base, and 'payload' overwrites if present?
        # Or better: if body.* args exist, we construct the payload from them.
        
        body_args = {k: v for k, v in method_args.items() if k.startswith('body.')}
        if body_args:
            if payload_data is None:
                payload_data = {}
            elif not isinstance(payload_data, dict):
                self.log("Warning: 'payload' argument is not a dict, but 'body.*' arguments are present. 'body.*' will be ignored.")
                body_args = {} # Skip body args if payload is not a dict
            
            for key, value in body_args.items():
                # Remove 'body.' prefix
                path = key[5:]
                if path:
                    self._set_json_value(payload_data, path, value)
        
        if payload_data is not None:
            req_kwargs['json'] = payload_data
        
        # Add Auth Headers
        headers = {}
        auth_id = self.context.get('auth_id')
        if auth_id:
            try:
                from integrations.models import ApiAuthID
                from integrations.utils import apply_auth_to_request
                
                auth_obj = ApiAuthID.objects.get(pk=auth_id)
                
                url, headers = apply_auth_to_request(auth_obj, url, headers=headers, log_func=self.log)
                
                self.log(f"Injected Auth Headers for type: {auth_obj.auth_type.name}")

            except Exception as e:
                self.log(f"Error injecting auth headers: {e}")

        req_kwargs['headers'] = headers
        
        response = requests.request(**req_kwargs)
        
        self.log(f"Response Status: {response.status_code}")
        try:
            result = response.json()
        except:
            result = response.text
        
        if not response.ok:
            self.log(f"Response Body: {response.text[:500]}...") # Log first 500 chars of error
            raise Exception(f"HTTP {response.status_code}: {response.text}")
        
        self.log(f"Method executed successfully. Result: {result}")
        return result
