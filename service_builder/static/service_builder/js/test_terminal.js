document.addEventListener('DOMContentLoaded', function () {
    console.log('Test Terminal JS loaded (v50)');
    const btnRun = document.getElementById('btn-run');
    const terminal = document.getElementById('terminal');
    const authSelect = document.getElementById('auth-select');

    // Visual Verification
    log('Terminal JS v48 loaded.', 'info');

    /** Fetch model choices for type=model arguments (e.g. PartnerAccount). Caches in window.apiModelChoices. */
    async function fetchModelChoices(modelKey) {
        const apiChoices = window.apiModelChoices || {};
        if (apiChoices[modelKey]) return apiChoices[modelKey];
        let appLabel, modelName;
        const parts = (modelKey || '').split('.');
        if (parts.length === 2) {
            [appLabel, modelName] = parts;
        } else if (parts.length === 1 && parts[0]) {
            appLabel = 'integrations';
            modelName = parts[0];
        } else {
            return null;
        }
        const normModel = modelName.toLowerCase();
        const url = `/admin/service_builder/api/model-choices/${appLabel}/${normModel}/`;
        try {
            const res = await fetch(url, { credentials: 'same-origin' });
            if (!res.ok) {
                console.warn('Model choices API returned', res.status, res.statusText);
                return null;
            }
            const data = await res.json();
            if (data.choices && Array.isArray(data.choices)) {
                if (!window.apiModelChoices) window.apiModelChoices = {};
                window.apiModelChoices[modelKey] = data.choices;
                return data.choices;
            }
            if (data.error) console.warn('Model choices API error:', data.error);
        } catch (e) {
            console.warn('Failed to fetch model choices for', modelKey, url, e);
        }
        return null;
    }

    // --- Auth Visibility Logic ---
    function checkVisibility() {
        if (!authSelect) return;

        const scenarioIdEl = document.getElementById('scenario-id');
        const workflowIdEl = document.getElementById('workflow-id');
        const actionIdEl = document.getElementById('action-id');

        const authRow = authSelect.closest('.form-row');
        if (!authRow) return;

        const hasScenario = scenarioIdEl && scenarioIdEl.value && scenarioIdEl.value.trim();
        const hasWorkflow = workflowIdEl && workflowIdEl.value && workflowIdEl.value.trim();
        const hasAction = actionIdEl && actionIdEl.value && actionIdEl.value.trim();

        if (hasScenario || hasWorkflow || hasAction) {
            authRow.style.display = 'none';
            console.log('Hiding Auth ID row (Scenario/Workflow/Action mode)');
        } else {
            authRow.style.display = 'flex';
            console.log('Showing Auth ID row (Method mode)');
        }
    }

    checkVisibility();

    function showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span>${message}</span>
            <span class="toast-close" onclick="this.parentElement.remove()">×</span>
        `;

        container.appendChild(toast);
        void toast.offsetWidth;
        toast.classList.add('show');

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    function log(message, type = 'normal') {
        const line = document.createElement('div');
        line.className = 'terminal-line';
        if (type === 'success') line.classList.add('status-success');
        if (type === 'error') line.classList.add('status-error');
        if (type === 'info') line.classList.add('status-info');
        line.textContent = '> ' + message;
        terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
    }

    /** Updates the External requests tab content. */
    function updateExternalRequestsTab(content) {
        var container = document.getElementById('external-requests-content');
        if (!container) container = document.querySelector('#external-requests-tab .tab-content-inner');
        if (container) {
            container.innerHTML = content;
        } else {
            console.warn('External requests tab container not found');
        }
    }

    const MAX_CORE_VAR_LINES = 100;

    function truncateToLines(str, maxLines) {
        if (typeof str !== 'string') return str;
        const lines = str.split('\n');
        if (lines.length <= maxLines) return str;
        return lines.slice(0, maxLines).join('\n') + '\n... (truncated)';
    }

    /** Renders Core variables tab with context_variables. */
    function updateCoreVariablesTab(contextVars) {
        var container = document.getElementById('core-variables-content');
        if (!container) container = document.querySelector('#core-variables-tab .tab-content-inner');
        if (!container) return;

        if (!contextVars || Object.keys(contextVars).length === 0) {
            container.innerHTML = '<p class="empty-state">No context variables yet. Run a test to see values.</p>';
            return;
        }

        let html = '<table class="context-vars-table"><thead><tr><th>Variable</th><th>Value</th></tr></thead><tbody>';
        for (const [name, value] of Object.entries(contextVars)) {
            let displayVal = value;
            if (typeof value === 'object' && value !== null) {
                try {
                    displayVal = JSON.stringify(value, null, 2);
                } catch (e) {
                    displayVal = String(value);
                }
            } else if (value === undefined || value === null) {
                displayVal = '<em>null</em>';
            }
            displayVal = truncateToLines(String(displayVal), MAX_CORE_VAR_LINES);
            html += `<tr><td><code>${escapeHtml(String(name))}</code></td><td><pre>${escapeHtml(displayVal)}</pre></td></tr>`;
        }
        html += '</tbody></table>';
        container.innerHTML = html;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function castByType(value, argType) {
        if (value == null) return value;

        // report_dates is already prepared as an object in prompt()
        if (argType === 'report_dates') return value;

        if (typeof value === 'object') return value;

        const raw = String(value).trim();
        if (raw === '') return value;

        if (argType === 'integer') {
            const n = Number(raw);
            return Number.isInteger(n) ? n : value;
        }

        if (argType === 'float' || argType === 'number') {
            const n = Number(raw);
            return Number.isFinite(n) ? n : value;
        }

        if (argType === 'boolean') {
            const normalized = raw.toLowerCase();
            if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
            if (['false', '0', 'no', 'off'].includes(normalized)) return false;
            return value;
        }

        if (argType === 'json') {
            try {
                return JSON.parse(raw);
            } catch (e) {
                return value;
            }
        }

        return value;
    }

    /** Renders External requests tab with api_calls / external_requests. */
    function renderExternalRequests(requests) {
        if (!requests || requests.length === 0) {
            return '<p class="empty-state">No external requests. Run a test with API call steps.</p>';
        }

        function formatHeaders(headers) {
            if (!headers || typeof headers !== 'object') return 'No headers';
            const entries = Object.entries(headers);
            if (entries.length === 0) return 'No headers';
            return entries.map(([k, v]) => `${k}: ${v}`).join('\n');
        }

        let html = '';
        requests.forEach((req, idx) => {
            const stepName = req.step_name || req.step || 'Request ' + (idx + 1);
            const url = req.url || req.request_url || 'N/A';
            const method = req.method || req.request_method || 'GET';
            let status = req.response_status ?? req.status_code ?? 'N/A';
            if (status === 'pending') status = 'pending (request aborted)';
            let payloadStr = 'No request body';
            if (req.request_payload != null || req.request_body != null) {
                const p = req.request_payload || req.request_body;
                payloadStr = typeof p === 'object' ? JSON.stringify(p, null, 2) : String(p);
            }
            let bodyStr = 'No response';
            if (req.response_body != null || req.body != null) {
                const b = req.response_body != null ? req.response_body : req.body;
                bodyStr = typeof b === 'object' ? JSON.stringify(b, null, 2) : String(b);
                if (bodyStr.length > 2000) bodyStr = bodyStr.substring(0, 2000) + '\n... (truncated)';
            }
            const reqHeadersStr = formatHeaders(req.request_headers);
            const respHeadersStr = formatHeaders(req.response_headers);
            html += `
                <div class="external-request-block">
                    <h4>${escapeHtml(stepName)}</h4>
                    <p><strong>URL:</strong> <code>${escapeHtml(String(url))}</code></p>
                    <p><strong>Method:</strong> ${escapeHtml(String(method))}</p>
                    <p><strong>Request headers:</strong></p>
                    <pre>${escapeHtml(reqHeadersStr)}</pre>
                    <p><strong>Request body:</strong></p>
                    <pre>${escapeHtml(payloadStr)}</pre>
                    <p><strong>Response status:</strong> ${escapeHtml(String(status))}</p>
                    <p><strong>Response headers:</strong></p>
                    <pre>${escapeHtml(respHeadersStr)}</pre>
                    <p><strong>Response body:</strong></p>
                    <pre>${escapeHtml(bodyStr)}</pre>
                </div>
            `;
        });
        return html;
    }

    function prompt(variableName, type = 'string', choices = null, defaultValue = '') {
        return new Promise((resolve) => {
            const line = document.createElement('div');
            line.className = 'terminal-line terminal-input-line';

            const promptSpan = document.createElement('span');
            promptSpan.className = 'terminal-prompt';
            promptSpan.textContent = `> Enter value for {${variableName}} (${type}): `;
            line.appendChild(promptSpan);

            let input;

            if (type === 'report_dates') {
                const container = document.createElement('div');
                container.style.display = 'inline-flex';
                container.style.gap = '10px';
                container.style.alignItems = 'center';

                const presets = document.createElement('select');
                presets.className = 'terminal-input';
                presets.style.width = '120px';
                [
                    { val: '', label: '-- Preset --' },
                    { val: 'today', label: 'Today' },
                    { val: 'yesterday', label: 'Yesterday' },
                    { val: 'last-3-days', label: 'Last 3 Days' },
                    { val: 'last-7-days', label: 'Last 7 Days' },
                    { val: 'last-30-days', label: 'Last 30 Days' },
                    { val: 'last-90-days', label: 'Last 90 Days' },
                    { val: 'custom', label: 'Custom' }
                ].forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.val;
                    opt.textContent = p.label;
                    presets.appendChild(opt);
                });

                const startInput = document.createElement('input');
                startInput.type = 'date';
                startInput.className = 'terminal-input';
                startInput.style.width = '130px';

                const endInput = document.createElement('input');
                endInput.type = 'date';
                endInput.className = 'terminal-input';
                endInput.style.width = '130px';

                const formatDate = (date) => {
                    const y = date.getFullYear();
                    const m = String(date.getMonth() + 1).padStart(2, '0');
                    const d = String(date.getDate()).padStart(2, '0');
                    return `${y}-${m}-${d}`;
                };

                presets.onchange = (e) => {
                    const val = e.target.value;
                    const today = new Date();
                    let start = new Date();
                    let end = new Date();
                    if (val === 'today') { } else if (val === 'yesterday') {
                        start.setDate(today.getDate() - 1);
                        end.setDate(today.getDate() - 1);
                    } else if (val === 'last-3-days') start.setDate(today.getDate() - 3);
                    else if (val === 'last-7-days') start.setDate(today.getDate() - 7);
                    else if (val === 'last-30-days') start.setDate(today.getDate() - 30);
                    else if (val === 'last-90-days') start.setDate(today.getDate() - 90);
                    else if (val !== 'custom') return;
                    if (val !== 'custom') {
                        startInput.value = formatDate(start);
                        endInput.value = formatDate(end);
                    }
                };

                container.appendChild(presets);
                container.appendChild(startInput);
                container.appendChild(document.createTextNode(' - '));
                container.appendChild(endInput);
                line.appendChild(container);

                input = {
                    focus: () => presets.focus(),
                    get value() { return { start: startInput.value, end: endInput.value }; },
                    set disabled(val) { presets.disabled = val; startInput.disabled = val; endInput.disabled = val; }
                };
            } else if (choices && choices.length > 0) {
                input = document.createElement('select');
                input.className = 'terminal-input';
                const defaultOpt = document.createElement('option');
                defaultOpt.value = "";
                defaultOpt.text = "-- Select --";
                input.appendChild(defaultOpt);
                choices.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = typeof c.value === 'object' && c.value !== null ? JSON.stringify(c.value) : c.value;
                    opt.text = c.label;
                    input.appendChild(opt);
                });
                line.appendChild(input);
            } else {
                input = document.createElement('input');
                input.className = 'terminal-input';
                input.type = 'text';
                input.value = defaultValue || '';
                line.appendChild(input);
            }

            const submitBtn = document.createElement('button');
            submitBtn.className = 'terminal-submit-btn';
            submitBtn.textContent = '↵';
            submitBtn.style.marginLeft = '10px';
            submitBtn.style.cursor = 'pointer';
            line.appendChild(submitBtn);
            terminal.appendChild(line);
            terminal.scrollTop = terminal.scrollHeight;
            input.focus && input.focus();

            function resolveValue() {
                let value = input.value;
                if (type === 'report_dates') {
                    if (!value.start || !value.end) {
                        alert('Please select both start and end dates.');
                        return;
                    }
                } else if (typeof value === 'string') {
                    value = value.trim();
                    if (value.startsWith('{') || value.startsWith('[')) {
                        try { value = JSON.parse(value); } catch (e) { }
                    }
                }
                console.log('Resolving with value:', value);
                if (input.disabled !== undefined) input.disabled = true;
                submitBtn.remove();
                resolve(value);
            }

            submitBtn.addEventListener('click', resolveValue);
            if (input.tagName === 'INPUT' || input.tagName === 'SELECT') {
                input.onkeydown = function (e) {
                    if (e.key === 'Enter' || e.keyCode === 13) { e.preventDefault(); resolveValue(); }
                };
            }
        });
    }

    async function doRun() {
        const scenarioIdInput = document.getElementById('scenario-id');
        const scenarioId = scenarioIdInput ? scenarioIdInput.value : null;
        const authId = authSelect ? authSelect.value : null;
        const methodIdInput = document.getElementById('method-id');
        const methodId = methodIdInput ? methodIdInput.value : null;
        const workflowIdInput = document.getElementById('workflow-id');
        const actionIdInput = document.getElementById('action-id');

        if (!methodId && !scenarioId && (!workflowIdInput || !workflowIdInput.value) && (!actionIdInput || !actionIdInput.value)) {
            log('Validation Failed:', 'error');
            if (!methodId) log('- No Method ID found', 'info');
            if (!scenarioId) log('- No Scenario selected', 'info');
            if (!workflowIdInput || !workflowIdInput.value) log('- No Workflow ID found', 'info');
            if (!actionIdInput || !actionIdInput.value) log('- No Action ID found', 'info');
            log('Please use a Run Test link from Method, Scenario, Workflow or Action admin.', 'error');
            return;
        }

        terminal.innerHTML = '';
        const variables = {};

        const authChoices = [];
        if (authSelect) {
            for (let i = 0; i < authSelect.options.length; i++) {
                const opt = authSelect.options[i];
                if (opt.value) authChoices.push({ value: opt.value, label: opt.text });
            }
        }

        if (scenarioId || (workflowIdInput && workflowIdInput.value) || (actionIdInput && actionIdInput.value)) {
            let entityName = "Scenario";
            if (workflowIdInput && workflowIdInput.value) entityName = "Workflow";
            if (actionIdInput && actionIdInput.value) entityName = "Action";
            const labelEl = document.querySelector('.form-row span strong');
            const name = labelEl ? labelEl.textContent : entityName;
            log(`Preparing to run ${entityName}: ${name}...`, 'info');

            const argsInput = document.getElementById('scenario-arguments');
            const args = JSON.parse(argsInput ? argsInput.value || '[]' : '[]');

            if (args.length > 0) {
                log(`Found ${args.length} context variable(s).`, 'info');
                for (const arg of args) {
                    let argName, argType = 'string', choices = null;
                    if (typeof arg === 'object' && arg !== null) {
                        argName = arg.name;
                        argType = arg.type || 'string';
                        const apiChoices = window.apiModelChoices || {};
                        if (arg.type === 'model' && arg.model && apiChoices[arg.model]) {
                            choices = apiChoices[arg.model];
                        } else if (arg._choices) {
                            choices = arg._choices;
                        } else if ((arg.type === 'model' && (arg.model === 'integrations.ApiAuthID' || arg.model === 'Api Auth Id')) ||
                            (argName && (argName.toLowerCase().includes('auth') || argName.toLowerCase().includes('account')))) {
                            choices = authChoices;
                            argType = 'auth_id';
                        } else if (arg.type === 'model' && arg.model) {
                            console.log('Fetching model choices for', arg.model);
                            choices = await fetchModelChoices(arg.model);
                            if (choices) console.log('Model choices loaded:', choices.length);
                            else console.warn('No model choices for', arg.model);
                        }
                    } else if (typeof arg === 'string') {
                        argName = arg;
                        if (arg.includes('auth') || arg.includes('account')) {
                            choices = authChoices;
                            argType = 'auth_id';
                        }
                    }
                    const value = await prompt(argName, argType, choices, arg && arg.default);
                    const typedValue = castByType(value, argType);
                    variables[argName] = typedValue;
                    log(`Value for {${argName}} set to: ${typedValue}`, 'success');
                }
            } else {
                log('No context variables defined for this scenario.', 'info');
            }
        } else {
            const methodEndpointUrl = document.getElementById('method-endpoint-url');
            const methodHttpMethod = document.getElementById('method-http-method');
            const methodArgsInput = document.getElementById('method-arguments');
            const urlTemplate = methodEndpointUrl ? methodEndpointUrl.value : '';
            const method = methodHttpMethod ? methodHttpMethod.value : 'GET';
            const argumentsJson = methodArgsInput ? methodArgsInput.value : '[]';
            log(`Analyzing endpoint: ${method} ${urlTemplate}...`, 'info');
            let varNames = [];
            try {
                if (argumentsJson) varNames = JSON.parse(argumentsJson);
            } catch (e) {
                log('Error parsing arguments configuration.', 'error');
            }
            if (varNames.length > 0) {
                const hasBodyArgs = varNames.some(name => name.startsWith('body.'));
                for (const varName of varNames) {
                    if (varName === 'payload' && hasBodyArgs) continue;
                    const value = await prompt(varName);
                    if (value === '' && varName.startsWith('body.')) {
                        log(`Skipping {${varName}}`, 'info');
                        continue;
                    }
                    variables[varName] = value;
                    log(`Value for {${varName}} set to: ${value}`, 'success');
                }
            } else {
                log('No variables found.', 'info');
            }
        }

        log('Sending request...', 'info');

        const requestPayload = {
            method_id: methodId,
            scenario_id: scenarioId,
            workflow_id: document.getElementById('workflow-id') ? document.getElementById('workflow-id').value : null,
            action_id: document.getElementById('action-id') ? document.getElementById('action-id').value : null,
            auth_id: authId,
            variables: variables
        };

        try {
            const url = window.location.href + (window.location.href.includes('?') ? '&' : '?') + 't=' + new Date().getTime();
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 600000);  // 10 min for long workflows
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken
                },
                body: JSON.stringify(requestPayload),
                credentials: 'same-origin',
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            let result;
            const textResult = await response.text();

            try {
                result = JSON.parse(textResult);
            } catch (e) {
                console.error('JSON Parse Error:', e);
                let errorMsg = 'Server returned non-JSON response (check console for full body).';
                if (textResult && (textResult.includes('Log in') || textResult.includes('login') || textResult.includes('id_username') || textResult.includes('id_password'))) {
                    errorMsg = 'Session expired. Please refresh the page and log in again.';
                } else if (textResult && textResult.match(/<h1 class="exc-title">(.+?)<\/h1>/)) {
                    errorMsg = 'Server Error: ' + textResult.match(/<h1 class="exc-title">(.+?)<\/h1>/)[1];
                } else if (textResult && textResult.includes('<h1>Server Error (500)</h1>')) {
                    errorMsg = 'Server Error (500)';
                } else if (textResult && textResult.length > 0) {
                    errorMsg = 'Invalid JSON response: ' + textResult.substring(0, 150) + (textResult.length > 150 ? '...' : '');
                }
                log(errorMsg, 'error');
                updateExternalRequestsTab('<p class="error">Server error. See log above.</p>');
                throw new Error(errorMsg);
            }

            // --- Update Core variables tab (context_variables) ---
            const contextVars = result.context_variables != null ? result.context_variables : (result.context || {});
            updateCoreVariablesTab(contextVars);

            // --- Update External requests tab (external_requests or api_calls) ---
            const extRequests = result.external_requests || result.api_calls || [];
            updateExternalRequestsTab(renderExternalRequests(extRequests));

            if (response.ok) {
                if (result.logs) {
                    log('Scenario Execution Logs:', 'info');
                    result.logs.forEach(msg => {
                        if (msg.startsWith('Error:')) log(msg, 'error');
                        else if (msg.startsWith('Warning:')) log(msg, 'info');
                        else log(msg, 'success');
                    });
                    if (result.success) {
                        log('Scenario completed successfully.', 'success');
                        showToast('Scenario completed successfully.', 'success');
                        if (result.outputs) {
                            log('Action/Workflow Outputs:', 'success');
                            log(JSON.stringify(result.outputs, null, 2));
                        }
                    } else {
                        log('Scenario failed.', 'error');
                        showToast(`Scenario Failed: ${result.error}`, 'error');
                    }
                } else {
                    log(`Request sent to: ${result.method} ${result.url}`, 'info');
                    if (result.request_payload) log('Request Payload:', 'info') && log(JSON.stringify(result.request_payload, null, 2));
                    if (result.request_headers) log('Request Headers:', 'info') && log(JSON.stringify(result.request_headers, null, 2));
                    log(`Status Code: ${result.status_code}`, result.status_code >= 200 && result.status_code < 300 ? 'success' : 'error');
                    if (result.extracted_value !== undefined) {
                        log('Result (Extracted):', 'success');
                        log(JSON.stringify(result.extracted_value, null, 2), 'success');
                    } else {
                        log('Response Headers:', 'info');
                        log(JSON.stringify(result.headers, null, 2));
                        log('Response Body:', 'info');
                        try { log(JSON.stringify(JSON.parse(result.body), null, 2)); } catch (e) { log(result.body); }
                    }
                }
            } else {
                log(`Error: ${result.error}`, 'error');
            }
            if (!result.success && result.traceback) {
                log('Traceback:', 'error');
                result.traceback.split('\n').forEach(line => log(line, 'error'));
            }

        } catch (error) {
            log(`Network Error: ${error.message}`, 'error');
        }
    }

    btnRun.addEventListener('click', () => doRun());
});
