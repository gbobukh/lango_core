document.addEventListener('DOMContentLoaded', function () {
    let $ = null;
    if (typeof django !== 'undefined' && django.jQuery) {
        $ = django.jQuery;
    } else if (typeof jQuery !== 'undefined') {
        $ = jQuery;
    } else if (typeof window.jQuery !== 'undefined') {
        $ = window.jQuery;
    }

    if (typeof $ !== 'function') {
        console.error('ArgumentMappingWorkflow: Valid jQuery not found! Aborting.');
        return;
    }

    $(document).ready(function () {
        function initArgumentMappingWidget($widget) {
            const $textarea = $widget.find('textarea');

            const $container = $widget.find('.mapping-table tbody');
            const $table = $widget.find('.mapping-table');
            const $help = $widget.find('.help');

            // Fetch Global Variables if not already fetched
            if (!window.GLOBAL_VARIABLES) {
                window.GLOBAL_VARIABLES = [];
                $.ajax({
                    url: '/metadata/api/global-variables/',
                    method: 'GET',
                    success: function (data) {
                        window.GLOBAL_VARIABLES = data.variables || [];
                        console.log('Global Variables Loaded (Workflow):', window.GLOBAL_VARIABLES.length);
                        // Force re-render of active widgets if needed
                        // Since renderTable is called on change/init, and this is typically fast, 
                        // we might just need to rely on next interaction or trigger a re-render.
                        // But for now, let's keep it simple.
                    }
                });
            }

            const $row = $widget.closest('.inline-related');
            // 'business_action' is the new source of truth
            const $actionSelect = $row.find('.field-business_action select');

            // Robust selector: Target the hidden input inside our custom widget container
            // This avoids ID ambiguities or name collisions
            const $workflowArgsInput = $('.typed-arguments-widget input[type="hidden"]');

            let currentMapping = {};
            try {
                currentMapping = JSON.parse($textarea.val() || '{}');
            } catch (e) {
                currentMapping = {};
            }

            // --- CHANGED HELPER FUNCTIONS ---
            function getContextVariables() {
                let vars = [];

                // Helper to scrape by Label
                function getTextByLabel($row, labelText) {
                    let text = '';
                    $row.find('label').each(function () {
                        if ($(this).text().indexOf(labelText) !== -1) {
                            text = $(this).siblings('.readonly').text();
                            return false; // break
                        }
                    });
                    return text;
                }

                const $rows = $('.inline-related');
                const $currentRow = $widget.closest('.inline-related');
                const currentIndex = $rows.index($currentRow);

                // 1. Workflow Inputs (Manual Arguments from Parent Form)
                // Prefer Global Variable exposed by TypedArgumentWidget
                let workflowArgs = window.WORKFLOW_ARGUMENTS || [];

                // Fallback to DOM scraping if Global is missing (rare race condition or legacy)
                if (!workflowArgs || workflowArgs.length === 0) {
                    try {
                        const $workflowArgsInput = $('.typed-arguments-widget input[type="hidden"]');
                        const workflowArgsStr = $workflowArgsInput.val();
                        if (workflowArgsStr) {
                            workflowArgs = JSON.parse(workflowArgsStr);
                        }
                    } catch (e) {
                        console.error("Error parsing workflow arguments for context:", e);
                    }
                }

                if (Array.isArray(workflowArgs)) {
                    workflowArgs.forEach(arg => {
                        let argName = typeof arg === 'string' ? arg : arg.name;
                        if (argName && !vars.includes(argName)) {
                            vars.push(argName);
                        }
                    });
                }

                // Legacy Fallback: If arguments empty, check first step? 
                // No, we want to enforce the new "Explicit Arguments" model.
                // If the user wants logic from Step 1, they should add it to Arguments.

                // 2. Previous Steps Outputs (From Step 0 to currentIndex - 1)
                $rows.each(function (index) {
                    // Only include outputs from PREVIOUS steps
                    // (For Step 1 (Index 0), this loop won't run/add anything as index is never < 0)
                    // (For Step 2 (Index 1), it includes outputs from Index 0)
                    if (index < currentIndex) {
                        const text = getTextByLabel($(this), "Outputs (Contract)");

                        if (text && text !== '-') {
                            text.split(',').forEach(part => {
                                let v = part.trim();
                                // Remove type if present
                                v = v.replace(/\s*\(.*?\)$/, '');
                                if (v && !vars.includes(v)) vars.push(v);
                            });
                        }
                    }
                });

                return vars;
            }

            function updateHiddenInput() {
                $textarea.val(JSON.stringify(currentMapping));
            }

            function getArgName(arg) {
                if (typeof arg === 'object' && arg !== null) return arg.name;
                return arg;
            }

            function renderTable(actionArgs, isManualMode) {
                $container.empty();
                const contextVars = getContextVariables();

                if (isManualMode) {
                    $table.show();
                    $help.text('Dynamic Routing enabled. Manually add arguments below.');
                    $help.show();
                    actionArgs = Object.keys(currentMapping);
                    if (actionArgs.length === 0) actionArgs = [''];
                } else if (!actionArgs || actionArgs.length === 0) {
                    const staleCount = Object.keys(currentMapping).length;
                    if (staleCount > 0) {
                        currentMapping = {};
                        updateHiddenInput();
                        console.info(`ArgumentMappingWorkflow: cleared ${staleCount} stale key(s) because action has no arguments.`);
                    }
                    $table.hide();
                    $help.text('Selected Business Action has no arguments.');
                    $help.show();
                    return;
                }

                // Non-manual mode: keep only keys that are present in current action contract.
                if (!isManualMode) {
                    const allowedKeys = new Set((actionArgs || []).map(getArgName).filter(Boolean));
                    const pruned = {};
                    let staleCount = 0;
                    Object.entries(currentMapping || {}).forEach(([key, value]) => {
                        if (allowedKeys.has(key)) {
                            pruned[key] = value;
                        } else {
                            staleCount += 1;
                        }
                    });
                    if (staleCount > 0) {
                        currentMapping = pruned;
                        updateHiddenInput();
                        console.info(`ArgumentMappingWorkflow: pruned ${staleCount} stale key(s) from mapping.`);
                    }
                }

                $table.show();
                if (!isManualMode) $help.hide();

                actionArgs.forEach(arg => {
                    const $tr = $('<tr>');
                    const $tdArg = $('<td>');

                    let argName = arg;
                    let argType = "";
                    if (typeof arg === 'object' && arg !== null) {
                        argName = arg.name;
                        if (arg.type) argType = ` <span style="color:#888; font-size:0.9em;">(${arg.type})</span>`;
                    }

                    if (isManualMode) {
                        const $keyInput = $('<input type="text" placeholder="Arg Name">').val(argName).css({ 'width': '100%' });
                        $keyInput.on('change', function () {
                            const newKey = $(this).val();
                            if (newKey && newKey !== argName) {
                                currentMapping[newKey] = currentMapping[argName];
                                delete currentMapping[argName];
                                updateHiddenInput();
                            }
                        });
                        $tdArg.append($keyInput);
                    } else {
                        $tdArg.html(argName + argType); // Use html() to render type span
                    }

                    const $tdInput = $('<td>');
                    // Add placeholder for implicit mapping
                    // Logic: If field is empty, it implies {{ argName }}.
                    const placeholderText = `Impilcit: {{ ${argName} }}`;

                    const $flexContainer = $('<div>').css({ 'display': 'flex', 'gap': '10px', 'align-items': 'center' });
                    const $input = $('<input type="text" placeholder="' + placeholderText + '">').css({ 'flex': '1', 'padding': '5px' });

                    if (currentMapping[argName]) {
                        $input.val(currentMapping[argName]);
                    }

                    const $select = $('<select>').css({ 'width': 'auto', 'max-width': '150px' });
                    $select.append($('<option>').val('').text('+ Insert Var'));

                    // Local Variables (Context)
                    contextVars.forEach(v => $select.append($('<option>').val(v).text(v)));

                    // Global Variables
                    if (window.GLOBAL_VARIABLES && window.GLOBAL_VARIABLES.length > 0) {
                        $select.append($('<option>').prop('disabled', true).text('---GLOBAL---'));
                        window.GLOBAL_VARIABLES.forEach(v => {
                            $select.append($('<option>').val(v).text(v));
                        });
                    }

                    $select.on('change', function () {
                        const val = $(this).val();
                        if (val) {
                            const currentVal = $input.val();
                            const domInput = $input[0];
                            if (domInput.selectionStart || domInput.selectionStart == '0') {
                                const startPos = domInput.selectionStart;
                                const endPos = domInput.selectionEnd;
                                $input.val(currentVal.substring(0, startPos) + '{{ ' + val + ' }}' + currentVal.substring(endPos));
                            } else {
                                $input.val(currentVal + '{{ ' + val + ' }}');
                            }
                            $(this).val('');
                            $input.trigger('change');
                        }
                    });

                    $input.on('change keyup paste', function () {
                        const val = $(this).val();
                        let key = isManualMode ? $tdArg.find('input').val() : argName;
                        if (!key) return;
                        if (val) currentMapping[key] = val;
                        else delete currentMapping[key];
                        updateHiddenInput();
                    });

                    $flexContainer.append($input, $select);
                    $tdInput.append($flexContainer);
                    $tr.append($tdArg, $tdInput);
                    $container.append($tr);
                });

                if (isManualMode) {
                    const $addBtn = $('<button type="button" style="margin-top:5px;">+ Add Argument</button>');
                    $addBtn.on('click', function () {
                        currentMapping["new_arg_" + Math.floor(Math.random() * 1000)] = "";
                        renderTable(null, true);
                    });
                    $widget.find('.mapping-table').after($addBtn);
                }
            }

            function fetchActionArguments(actionId) {
                if (!actionId) {
                    renderTable(null, true);
                    return;
                }
                $widget.find('button').remove();

                $.ajax({
                    url: '/admin/service_builder/workflow/api/business-action-arguments/' + actionId + '/',
                    method: 'GET',
                    success: function (data) {
                        renderTable(data.arguments, false);
                    },
                    error: function () {
                        $help.text('Error fetching arguments.');
                    }
                });
            }

            fetchActionArguments($actionSelect.val());

            $actionSelect.on('change', function () {
                fetchActionArguments($(this).val());
            });

            let timeout;
            $workflowArgsInput.on('change keyup', function () {
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    fetchActionArguments($actionSelect.val());
                }, 500);
            });
        }

        $('.argument-mapping-widget').each(function () {
            initArgumentMappingWidget($(this));
        });

        $(document).on('formset:added', function (event, row, formsetName) {
            // Ensure row is defined and wrap in jQuery
            if (!row) {
                console.warn('ArgumentMappingWorkflow: formset:added triggered with no row');
                return;
            }
            const $row = $(row);

            if ($row.find('.argument-mapping-widget').length > 0) {
                $row.find('.argument-mapping-widget').each(function () {
                    initArgumentMappingWidget($(this));
                });
            }
        });
    });
});
