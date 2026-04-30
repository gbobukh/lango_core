(function () {
    window.TypedArgumentsWidget = {
        init: function (containerId) {
            const container = document.getElementById(containerId);
            if (!container) return;

            const input = container.querySelector('input[type="hidden"]');
            const contentArea = container.querySelector('.typed-arguments-container');

            let argumentsList = [];
            try {
                const rawValue = input.value;
                if (rawValue) {
                    const parsed = JSON.parse(rawValue);
                    // Handle legacy list of strings
                    if (Array.isArray(parsed)) {
                        argumentsList = parsed.map(item => {
                            if (typeof item === 'string') {
                                return { name: item, type: 'string' };
                            }
                            return item;
                        });
                    }
                }
            } catch (e) {
                console.error('Error parsing arguments:', e);
                argumentsList = [];
            }

            // State
            const state = {
                arguments: argumentsList,
                models: [] // Cache for models
            };

            // Initialize global state immediately
            window.WORKFLOW_ARGUMENTS = state.arguments;

            // Auto-init removed as per request to remove strict tracker contract
            // const isBusinessAction = document.body.classList.contains('model-businessaction');
            // if (isBusinessAction && state.arguments.length === 0) { ... }

            // Fetch Models
            fetch('/admin/service_builder/scenario/api/models/')
                .then(response => response.json())
                .then(data => {
                    state.models = data.models || [];
                    render();
                })
                .catch(err => {
                    console.error('Failed to fetch models:', err);
                    contentArea.innerHTML = '<p class="error">Failed to load models. Please refresh.</p>';
                });

            function updateInput() {
                input.value = JSON.stringify(state.arguments);
                // Expose globally for argument_mapping_workflow.js to read reliably
                window.WORKFLOW_ARGUMENTS = state.arguments;

                const event = new Event('change', { bubbles: true });
                input.dispatchEvent(event);
                // Also trigger jQuery event for listeners (like argument_mapping_workflow.js)
                if (window.jQuery) {
                    window.jQuery(input).trigger('change');
                } else if (window.django && window.django.jQuery) {
                    window.django.jQuery(input).trigger('change');
                }
            }

            function render() {
                contentArea.innerHTML = '';

                const table = document.createElement('table');
                table.className = 'typed-arguments-table';

                // Header
                const thead = document.createElement('thead');
                thead.innerHTML = `
                    <tr>
                        <th style="width: 30%">Name</th>
                        <th style="width: 20%">Type</th>
                        <th style="width: 25%">Model</th>
                        <th style="width: 20%">Lookup Field</th>
                        <th style="width: 5%"></th>
                    </tr>
                `;
                table.appendChild(thead);

                // Body
                const tbody = document.createElement('tbody');

                state.arguments.forEach((arg, index) => {
                    const tr = document.createElement('tr');
                    // Unlock 'tracker' even if stored as locked (Migration/Revert logic)
                    let isLocked = !!arg.locked;
                    if (arg.name === 'tracker') {
                        isLocked = false;
                        arg.locked = false; // Update internal state too so it saves as unlocked
                        arg.system = false;
                    }

                    // Name
                    const tdName = document.createElement('td');
                    const nameContainer = document.createElement('div');
                    nameContainer.style.display = 'flex';
                    nameContainer.style.alignItems = 'center';

                    const inputName = document.createElement('input');
                    inputName.type = 'text';
                    inputName.value = arg.name || '';
                    inputName.placeholder = 'e.g. partner_id';
                    inputName.disabled = isLocked;
                    if (isLocked) inputName.style.backgroundColor = '#f9f9f9';

                    inputName.onchange = (e) => {
                        let val = e.target.value;
                        if (arg.type === 'model' && val && !val.endsWith('_obj')) {
                            val += '_obj';
                            inputName.value = val;
                        }
                        arg.name = val;
                        updateInput();
                    };
                    nameContainer.appendChild(inputName);

                    // Visual suffix hint for Models
                    if (arg.type === 'model') {
                        const suffixSpan = document.createElement('span');
                        suffixSpan.textContent = '_obj';
                        suffixSpan.style.color = '#888';
                        suffixSpan.style.marginLeft = '4px';
                        suffixSpan.style.fontSize = '0.9em';
                        suffixSpan.title = 'Model objects must have _obj suffix';
                        nameContainer.appendChild(suffixSpan);
                    }

                    tdName.appendChild(nameContainer);
                    tr.appendChild(tdName);

                    // Type
                    const tdType = document.createElement('td');
                    const selectType = document.createElement('select');
                    selectType.disabled = isLocked;

                    ['string', 'integer', 'boolean', 'model', 'report_dates'].forEach(type => {
                        const option = document.createElement('option');
                        option.value = type;
                        option.textContent = type.charAt(0).toUpperCase() + type.slice(1).replace('_', ' ');
                        if (arg.type === type) option.selected = true;
                        selectType.appendChild(option);
                    });
                    selectType.onchange = (e) => {
                        arg.type = e.target.value;
                        if (arg.type !== 'model') {
                            delete arg.model;
                            delete arg.lookup;
                        } else {
                            // Auto-append _obj if switching to model
                            if (arg.name && !arg.name.endsWith('_obj')) {
                                arg.name += '_obj';
                            }
                        }
                        updateInput();
                        render();
                    };
                    tdType.appendChild(selectType);
                    tr.appendChild(tdType);

                    // Model
                    const tdModel = document.createElement('td');
                    if (arg.type === 'model') {
                        const selectModel = document.createElement('select');
                        selectModel.disabled = isLocked;
                        selectModel.innerHTML = '<option value="">Select Model...</option>';
                        state.models.forEach(model => {
                            const option = document.createElement('option');
                            option.value = model.full_name; // e.g. integrations.partneraccount
                            option.textContent = model.verbose_name;
                            // Relaxed matching for DB legacy (PascalCase) vs API (lowercase)
                            if (arg.model && arg.model.toLowerCase() === model.full_name.toLowerCase()) {
                                option.selected = true;
                            }
                            selectModel.appendChild(option);
                        });
                        selectModel.onchange = (e) => {
                            arg.model = e.target.value;
                            arg.lookup = ''; // Reset lookup when model changes
                            updateInput();
                            render(); // Re-render to update lookup fields
                        };
                        tdModel.appendChild(selectModel);
                    } else {
                        tdModel.textContent = '-';
                        tdModel.style.color = '#ccc';
                    }
                    tr.appendChild(tdModel);

                    // Lookup Field (Visible only if type === 'model' && model selected)
                    const tdLookup = document.createElement('td');
                    if (arg.type === 'model' && arg.model) {
                        const selectLookup = document.createElement('select');
                        selectLookup.innerHTML = '<option value="">Loading...</option>';
                        selectLookup.disabled = true;

                        // Parse app_label and model_name
                        const [appLabel, modelName] = arg.model.split('.');

                        // Fetch fields
                        // TODO: Cache fields to avoid repeated requests (but ensure freshness on reload)
                        const timestamp = new Date().getTime();
                        fetch(`/admin/service_builder/scenario/api/models/${appLabel}/${modelName}/fields/?_t=${timestamp}`)
                            .then(res => res.json())
                            .then(data => {
                                selectLookup.innerHTML = '<option value="">Select Field...</option>';
                                (data.fields || []).forEach(field => {
                                    const option = document.createElement('option');
                                    option.value = field.name;

                                    // Visual Indicator
                                    let label = field.name;
                                    if (field.is_unique) {
                                        label += ' (Unique ✓)';
                                        option.style.fontWeight = 'bold';
                                        option.style.color = 'green';
                                    } else {
                                        label += ' (⚠ Not Unique)';
                                        option.style.color = '#d9534f'; // Red warning
                                    }
                                    option.textContent = label;

                                    // Handle 'pk' alias for 'id'
                                    const currentLookup = (arg.lookup === 'pk') ? 'id' : arg.lookup;

                                    if (currentLookup === field.name) option.selected = true;
                                    selectLookup.appendChild(option);
                                });
                                // Only enable if not locked
                                selectLookup.disabled = isLocked;
                            });

                        selectLookup.onchange = (e) => {
                            arg.lookup = e.target.value;
                            updateInput();
                        };
                        tdLookup.appendChild(selectLookup);
                    } else {
                        tdLookup.textContent = '-';
                        tdLookup.style.color = '#ccc';
                    }
                    tr.appendChild(tdLookup);

                    // Remove
                    const tdRemove = document.createElement('td');
                    if (!isLocked) {
                        tdRemove.className = 'btn-remove';
                        tdRemove.textContent = '×';
                        tdRemove.onclick = () => {
                            state.arguments.splice(index, 1);
                            updateInput();
                            render();
                        };
                    } else {
                        const spanLock = document.createElement('span');
                        spanLock.textContent = '🔒';
                        spanLock.title = 'System Argument';
                        tdRemove.appendChild(spanLock);
                    }
                    tr.appendChild(tdRemove);

                    tbody.appendChild(tr);
                });

                table.appendChild(tbody);
                contentArea.appendChild(table);

                // Add Button
                const btnAdd = document.createElement('button');
                btnAdd.type = 'button';
                btnAdd.className = 'btn-add';
                btnAdd.textContent = '+ Add Argument';
                btnAdd.onclick = () => {
                    state.arguments.push({ name: '', type: 'string' });
                    updateInput();
                    render();
                };
                contentArea.appendChild(btnAdd);
            }
        }
    };
})();
