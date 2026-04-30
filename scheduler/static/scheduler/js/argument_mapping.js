/**
 * ScheduledWorkflow Argument Mapping Widget
 * Fetches workflow arguments when workflow is selected and renders typed inputs.
 */
(function () {
    const MODEL_CHOICES_API = '/admin/service_builder/api/model-choices/';

    async function fetchModelChoices(modelKey) {
        const cache = window._schedulerModelChoices || {};
        if (cache[modelKey]) return cache[modelKey];
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
        try {
            const res = await fetch(`${MODEL_CHOICES_API}${appLabel}/${normModel}/`, { credentials: 'same-origin' });
            if (!res.ok) return null;
            const data = await res.json();
            if (data.choices && Array.isArray(data.choices)) {
                window._schedulerModelChoices = window._schedulerModelChoices || {};
                window._schedulerModelChoices[modelKey] = data.choices;
                return data.choices;
            }
        } catch (e) {
            console.warn('Failed to fetch model choices for', modelKey, e);
        }
        return null;
    }

    function init() {
        const widget = document.querySelector('.scheduler-argument-mapping-widget');
        if (!widget) return;

        const hiddenInput = widget.querySelector('input[type="hidden"]');
        const container = widget.querySelector('.scheduler-argument-mapping-container');
        const apiBase = widget.dataset.apiBase || '/admin/scheduler/scheduledworkflow/api/workflow-arguments/';

        let currentValues = {};
        try {
            const raw = hiddenInput.value;
            if (raw && raw !== '{}') currentValues = JSON.parse(raw);
        } catch (e) {}

        function parseTypedValue(raw, argType) {
            if (raw == null) return raw;
            const val = String(raw).trim();
            if (val === '') return '';

            if (argType === 'integer') {
                const n = Number(val);
                return Number.isInteger(n) ? n : raw;
            }
            if (argType === 'float' || argType === 'number') {
                const n = Number(val);
                return Number.isFinite(n) ? n : raw;
            }
            if (argType === 'boolean') {
                const normalized = val.toLowerCase();
                if (normalized === 'true' || normalized === '1') return true;
                if (normalized === 'false' || normalized === '0') return false;
                return raw;
            }
            if (argType === 'json') {
                try {
                    return JSON.parse(val);
                } catch (e) {
                    return raw;
                }
            }

            if (val.startsWith('{') || val.startsWith('[')) {
                try { return JSON.parse(val); } catch (e) {}
            }
            return raw;
        }

        function collectValues() {
            const result = {};
            widget.querySelectorAll('.scheduler-arg-row').forEach(row => {
                const name = row.dataset.argName;
                if (!name) return;

                if (row.dataset.argType === 'report_dates') {
                    const preset = row.querySelector('.scheduler-arg-preset');
                    const start = row.querySelector('.scheduler-date-start');
                    const end = row.querySelector('.scheduler-date-end');
                    if (preset && preset.value && preset.value !== 'custom') {
                        result[name] = { preset: preset.value };
                    } else if (start && end && start.value && end.value) {
                        result[name] = { start: start.value, end: end.value };
                    }
                } else {
                    const inp = row.querySelector('select, input[type="text"]');
                    if (inp && inp.value !== '') {
                        const argType = row.dataset.argType || 'string';
                        result[name] = parseTypedValue(inp.value, argType);
                    }
                }
            });
            hiddenInput.value = JSON.stringify(result);
            hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function renderArgRow(arg, choices, existingVal) {
            const name = typeof arg === 'string' ? arg : (arg.name || '');
            const argType = (typeof arg === 'object' && arg) ? (arg.type || 'string') : 'string';

            const row = document.createElement('div');
            row.className = 'scheduler-arg-row';
            row.dataset.argName = name;
            row.dataset.argType = argType;

            const label = document.createElement('label');
            label.className = 'scheduler-arg-label';
            label.textContent = name + (argType !== 'string' ? ` (${argType})` : '');

            const inputCell = document.createElement('div');
            inputCell.className = 'scheduler-arg-input-cell';

            if (argType === 'report_dates') {
                row.dataset.argType = 'report_dates';
                const preset = document.createElement('select');
                preset.className = 'scheduler-arg-preset';
                preset.innerHTML = '<option value="">-- Preset --</option>' +
                    '<option value="today">Today</option><option value="yesterday">Yesterday</option>' +
                    '<option value="last-3-days">Last 3 Days</option><option value="last-7-days">Last 7 Days</option>' +
                    '<option value="last-30-days">Last 30 Days</option><option value="last-90-days">Last 90 Days</option>' +
                    '<option value="custom">Custom</option>';

                const startInput = document.createElement('input');
                startInput.type = 'date';
                startInput.className = 'scheduler-date-start scheduler-arg-input';

                const endInput = document.createElement('input');
                endInput.type = 'date';
                endInput.className = 'scheduler-date-end scheduler-arg-input';

                const formatDate = (d) => {
                    const y = d.getFullYear(), m = String(d.getMonth() + 1).padStart(2, '0'), day = String(d.getDate()).padStart(2, '0');
                    return `${y}-${m}-${day}`;
                };

                preset.onchange = function () {
                    const val = preset.value;
                    const today = new Date();
                    let start = new Date(), end = new Date();
                    if (val === 'yesterday') start.setDate(today.getDate() - 1), end.setDate(today.getDate() - 1);
                    else if (val === 'last-3-days') start.setDate(today.getDate() - 3);
                    else if (val === 'last-7-days') start.setDate(today.getDate() - 7);
                    else if (val === 'last-30-days') start.setDate(today.getDate() - 30);
                    else if (val === 'last-90-days') start.setDate(today.getDate() - 90);
                    if (val && val !== 'custom') {
                        startInput.value = formatDate(start);
                        endInput.value = formatDate(end);
                        collectValues();
                    } else if (val === 'custom') {
                        collectValues();
                    }
                };

                startInput.onchange = endInput.onchange = collectValues;

                if (existingVal && typeof existingVal === 'object') {
                    if (existingVal.preset) {
                        preset.value = existingVal.preset;
                        const today = new Date();
                        let start = new Date(), end = new Date();
                        if (existingVal.preset === 'yesterday') start.setDate(today.getDate() - 1), end.setDate(today.getDate() - 1);
                        else if (existingVal.preset === 'last-3-days') start.setDate(today.getDate() - 3);
                        else if (existingVal.preset === 'last-7-days') start.setDate(today.getDate() - 7);
                        else if (existingVal.preset === 'last-30-days') start.setDate(today.getDate() - 30);
                        else if (existingVal.preset === 'last-90-days') start.setDate(today.getDate() - 90);
                        startInput.value = formatDate(start);
                        endInput.value = formatDate(end);
                    } else if (existingVal.start && existingVal.end) {
                        preset.value = 'custom';
                        startInput.value = existingVal.start;
                        endInput.value = existingVal.end;
                    }
                }

                inputCell.appendChild(preset);
                inputCell.appendChild(startInput);
                inputCell.appendChild(document.createTextNode(' — '));
                inputCell.appendChild(endInput);
            } else if (choices && choices.length > 0) {
                const select = document.createElement('select');
                select.className = 'scheduler-arg-input';
                select.innerHTML = '<option value="">-- Select --</option>';
                choices.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = typeof c.value === 'object' && c.value !== null ? JSON.stringify(c.value) : c.value;
                    opt.textContent = c.label;
                    select.appendChild(opt);
                });
                if (existingVal != null) select.value = String(existingVal);
                select.onchange = collectValues;
                inputCell.appendChild(select);
            } else {
                const textInput = document.createElement('input');
                textInput.type = 'text';
                textInput.className = 'scheduler-arg-input';
                textInput.value = existingVal != null ? String(existingVal) : (arg.default != null ? String(arg.default) : '');
                textInput.onchange = textInput.oninput = collectValues;
                inputCell.appendChild(textInput);
            }

            row.appendChild(label);
            row.appendChild(inputCell);
            return row;
        }

        async function loadArguments(workflowId) {
            if (!workflowId) {
                container.innerHTML = '<p class="scheduler-argument-mapping-placeholder">Выберите workflow, чтобы настроить аргументы.</p>';
                hiddenInput.value = '{}';
                return;
            }

            container.innerHTML = '<p class="scheduler-arg-loading">Загрузка аргументов...</p>';

            let args = [];
            try {
                const res = await fetch(apiBase + workflowId + '/', { credentials: 'same-origin' });
                const data = await res.json();
                args = data.arguments || [];
            } catch (e) {
                container.innerHTML = '<p class="scheduler-arg-error">Ошибка загрузки аргументов.</p>';
                return;
            }

            if (args.length === 0) {
                container.innerHTML = '<p class="scheduler-argument-mapping-placeholder">У этого workflow нет аргументов.</p>';
                hiddenInput.value = '{}';
                return;
            }

            container.innerHTML = '';

            for (const arg of args) {
                const argName = typeof arg === 'string' ? arg : (arg.name || '');
                const argType = (typeof arg === 'object' && arg) ? (arg.type || 'string') : 'string';
                const argModel = (typeof arg === 'object' && arg) ? arg.model : null;
                const existingVal = currentValues[argName];

                let choices = null;
                let resolvedType = argType;

                if (argType === 'model' && argModel) {
                    choices = await fetchModelChoices(argModel);
                } else if (argName.toLowerCase().includes('auth') || argName.toLowerCase().includes('account') || argModel === 'integrations.ApiAuthID') {
                    choices = await fetchModelChoices('integrations.ApiAuthID');
                }

                const argDef = typeof arg === 'object' && arg ? arg : { name: argName, type: 'string' };
                const row = renderArgRow(argDef, choices, existingVal);
                container.appendChild(row);
            }

            collectValues();
        }

        const workflowSelect = document.getElementById('id_workflow');
        if (workflowSelect) {
            workflowSelect.addEventListener('change', function () {
                loadArguments(this.value);
            });
            if (workflowSelect.value) {
                loadArguments(workflowSelect.value);
            }
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();
