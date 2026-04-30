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
        console.error('ArgumentMapping: Valid jQuery not found! Aborting.');
        return;
    }

    $(document).ready(function () {
        // Function to initialize a single widget
        function initArgumentMappingWidget($widget) {
            const $textarea = $widget.find('textarea');
            const $container = $widget.find('.mapping-table tbody');
            const $table = $widget.find('.mapping-table');
            const $help = $widget.find('.help');

            // Find the parent row to locate the Method dropdown
            const $row = $widget.closest('.inline-related');

            // Helper to find the method select element robustly using Input Name
            function findMethodSelect() {
                const textareaName = $textarea.attr('name'); // e.g. steps-0-argument_mapping
                if (!textareaName) return $();

                // Extract index
                const match = textareaName.match(/steps-(\d+)-argument_mapping/);
                if (!match) return $();
                const index = match[1];

                // Construct ID for method field
                const methodId = 'id_steps-' + index + '-method';

                // Try by ID first (fastest and most reliable)
                let $select = $('#' + methodId);

                // If not found, try traversing from the row
                if ($select.length === 0) {
                    // Look for any select with name ending in -method inside this row
                    $select = $row.find('select[name$="-method"]');
                }

                // List all selects in row (for console debug only if needed)
                // const allSelects = $row.find('select');

                // If not found, we can't do much.
                if ($select.length === 0) {
                    // Fallback or error handling
                }

                return $select;
            }

            const $methodSelect = findMethodSelect();

            if ($methodSelect.length === 0) {
                // If it's the template row (containing __prefix__), ignore it silently
                if ($textarea.attr('name') && $textarea.attr('name').indexOf('__prefix__') !== -1) {
                    return;
                }

                console.error('ArgumentMapping: Method select not found for widget', $widget);
                $help.text('Error: Method field not found.');
                $help.show();
                return;
            }


            // Fetch Global Variables if not already fetched
            if (!window.GLOBAL_VARIABLES) {
                window.GLOBAL_VARIABLES = [];
                $.ajax({
                    url: '/metadata/api/global-variables/',
                    method: 'GET',
                    success: function (data) {
                        window.GLOBAL_VARIABLES = data.variables || [];
                        // Trigger re-render of dropdowns if already rendered? 
                        // For simplicity, we assume this loads fast enough or the next interaction will pick it up.
                        // Or we can trigger a refresh.
                        $('.argument-mapping-widget select').each(function () {
                            // This is tricky without rebuilding the whole table. 
                            // But since we build the table dynamically on method change/init, 
                            // and methods often load async too, it might be fine.
                            // Let's just rely on the next render.
                        });
                        console.log('Global Variables Loaded:', window.GLOBAL_VARIABLES.length);

                        // Force refresh of any active widget just in case
                        $('.argument-mapping-widget').each(function () {
                            const $w = $(this);
                            // If table is visible, maybe refresh?
                            // But wait, initArgumentMappingWidget is called per widget.
                            // Best place is to call this once per page load, not per widget.
                        });
                    }
                });
            }

            // Find the Scenario Arguments input (global for the page)
            // It's usually id_arguments
            const $scenarioArgsInput = $('#id_arguments');

            // State
            let currentMapping = {};
            try {
                currentMapping = JSON.parse($textarea.val() || '{}');
            } catch (e) {
                currentMapping = {};
            }

            function getContextVariables() {
                let vars = [];
                // 1. Scenario Arguments
                try {
                    const args = JSON.parse($scenarioArgsInput.val() || '[]');
                    if (Array.isArray(args)) {
                        args.forEach(arg => {
                            if (typeof arg === 'string') {
                                vars.push(arg);
                            } else if (arg && typeof arg === 'object' && arg.name) {
                                vars.push(arg.name);
                            }
                        });
                    }
                } catch (e) { }

                // 2. Outputs from previous steps (simple heuristic: look for inputs named *-output_variable_name)
                // We only care about steps BEFORE this one.
                // But for simplicity, we'll just grab all output vars for now.
                // A better approach would be to parse the formset order.
                // 2. Outputs from previous steps
                $('.field-output_variable_name input').each(function () {
                    const val = $(this).val();
                    if (val && !vars.includes(val)) {
                        vars.push(val);
                    }
                });

                // 3. Context Extraction from previous steps
                $('.field-context_extraction textarea').each(function () {
                    try {
                        const jsonVal = JSON.parse($(this).val() || '{}');
                        Object.keys(jsonVal).forEach(key => {
                            if (key && !vars.includes(key)) {
                                vars.push(key);
                            }
                        });
                    } catch (e) { }
                });

                return vars;
            }

            function updateHiddenInput() {
                const val = JSON.stringify(currentMapping);
                $textarea.val(val);
            }

            function renderTable(methodArgs) {
                $container.empty();
                const contextVars = getContextVariables();

                if (!methodArgs || methodArgs.length === 0) {
                    const staleCount = Object.keys(currentMapping).length;
                    if (staleCount > 0) {
                        currentMapping = {};
                        updateHiddenInput();
                        console.info(`ArgumentMapping: cleared ${staleCount} stale key(s) because method has no arguments.`);
                    }
                    $table.hide();
                    $help.text('Selected method has no arguments.');
                    $help.show();
                    return;
                }

                // Keep only keys present in the current method contract.
                const allowedKeys = new Set((methodArgs || []).filter(Boolean));
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
                    console.info(`ArgumentMapping: pruned ${staleCount} stale key(s) from mapping.`);
                }

                $table.show();
                $help.hide();
                $widget.find('.refresh-args').hide();

                methodArgs.forEach(arg => {
                    const $tr = $('<tr>');
                    const $tdArg = $('<td>').text(arg);
                    const $tdInput = $('<td>');

                    // Container for flex layout
                    const $flexContainer = $('<div>').css({
                        'display': 'flex',
                        'gap': '10px',
                        'align-items': 'center'
                    });

                    // 1. Text Input for the template (Textarea)
                    const $input = $('<textarea rows="1">').css({
                        'flex': '1',
                        'padding': '5px',
                        'min-height': '30px',
                        'resize': 'vertical',
                        'overflow-y': 'hidden'
                    });

                    // Auto-resize logic
                    function autoResize() {
                        this.style.height = 'auto';
                        this.style.height = (this.scrollHeight) + 'px';
                    }
                    $input.on('input', autoResize);

                    const currentVal = currentMapping[arg];
                    if (currentVal) {
                        $input.val(currentVal);
                        setTimeout(() => autoResize.call($input[0]), 0);
                    }

                    // Set current value
                    if (currentMapping[arg]) {
                        $input.val(currentMapping[arg]);
                    }

                    // 2. Helper Dropdown to insert variables
                    const $select = $('<select>').css({
                        'width': 'auto',
                        'max-width': '150px'
                    });
                    $select.append($('<option>').val('').text('+ Insert Var'));

                    // Local Variables (Context)
                    contextVars.forEach(v => {
                        $select.append($('<option>').val(v).text(v));
                    });

                    // Global Variables
                    if (window.GLOBAL_VARIABLES && window.GLOBAL_VARIABLES.length > 0) {
                        $select.append($('<option>').prop('disabled', true).text('---GLOBAL---'));
                        window.GLOBAL_VARIABLES.forEach(v => {
                            $select.append($('<option>').val(v).text(v));
                        });

                        // Smart Tracker Keys Detection
                        // 1. Identify Tracker Arguments
                        const trackerArgs = [];
                        try {
                            const args = JSON.parse($scenarioArgsInput.val() || '[]');
                            if (Array.isArray(args)) {
                                args.forEach(arg => {
                                    if (arg && typeof arg === 'object' && arg.type === 'model' && arg.name) {
                                        // Check model path (loose check)
                                        const model = (arg.model || '').toLowerCase();
                                        if (model.includes('metrics.tracker') || model.includes('integrations.tracker')) {
                                            trackerArgs.push(arg.name);
                                        }
                                    }
                                });
                            }
                        } catch (e) { }

                        // 2. Add Options
                        if (trackerArgs.length > 0) {
                            $select.append($('<option>').prop('disabled', true).text('---TRACKER KEYS---'));
                            trackerArgs.forEach(argName => {
                                window.GLOBAL_VARIABLES.forEach(gv => {
                                    const key = `${argName}.keys.${gv}`;
                                    $select.append($('<option>').val(key).text(key));
                                });
                            });
                        }
                    }

                    // Handle Variable Insertion
                    $select.on('change', function () {
                        const val = $(this).val();
                        if (val) {
                            const currentVal = $input.val();
                            // Insert at cursor position or append? Append is safer for simple implementation.
                            // Let's try to insert at cursor if possible, otherwise append.
                            const domInput = $input[0];
                            if (domInput.selectionStart || domInput.selectionStart == '0') {
                                const startPos = domInput.selectionStart;
                                const endPos = domInput.selectionEnd;
                                $input.val(currentVal.substring(0, startPos) +
                                    '{{ ' + val + ' }}' +
                                    currentVal.substring(endPos, currentVal.length));
                            } else {
                                $input.val(currentVal + '{{ ' + val + ' }}');
                            }

                            // Reset select
                            $(this).val('');
                            // Trigger change to update mapping
                            $input.trigger('change');
                        }
                    });

                    // Handle Input Change
                    $input.on('change keyup paste', function () {
                        const val = $(this).val();
                        if (val) {
                            currentMapping[arg] = val;
                        } else {
                            delete currentMapping[arg];
                        }
                        updateHiddenInput();
                    });

                    $flexContainer.append($input, $select);
                    $tdInput.append($flexContainer);
                    $tr.append($tdArg, $tdInput);
                    $container.append($tr);
                });
            }

            function fetchMethodArguments(methodId) {
                if (!methodId) {
                    $table.hide();
                    $help.text('Select a Method to see arguments.');
                    $help.show();
                    return;
                }

                $.ajax({
                    url: '/admin/service_builder/scenario/api/method-arguments/' + methodId + '/',
                    method: 'GET',
                    success: function (data) {
                        renderTable(data.arguments);
                    },
                    error: function () {
                        $help.text('Error fetching arguments.');
                    }
                });
            }



            // Listen for Method change
            $methodSelect.on('change', function () {
                console.log('Method changed:', $(this).val());
                fetchMethodArguments($(this).val());
            });

            // Initial load
            const initialVal = $methodSelect.val();
            console.log('Initial Method Value:', initialVal);

            // Initial load with polling
            function checkInitialValue(attempts = 0) {
                const val = $methodSelect.val();
                if (val) {
                    fetchMethodArguments(val);
                } else if (attempts < 5) {
                    // Try again in 200ms
                    setTimeout(() => checkInitialValue(attempts + 1), 200);
                } else {
                    // Final attempt: check display value as fallback hint (optional)
                    const displayValue = $row.find('.field-method .click-to-edit-display').text().trim();
                    if (displayValue && displayValue !== '-') {
                        // If we have a display value but no select value, something is weird.
                        // Try to find the option by text?
                        $methodSelect.find('option').each(function () {
                            if ($(this).text().trim() === displayValue) {
                                $methodSelect.val($(this).val()).trigger('change');
                            }
                        });
                    } else {
                        $help.text('Select a Method to see arguments.');
                        $help.show();
                    }
                }
            }

            checkInitialValue();

            // Listen for Context changes (Scenario Args)
            // We use a timeout to avoid excessive re-renders
            let timeout;
            $scenarioArgsInput.on('change keyup', function () {
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    // Re-render current table to update dropdowns
                    fetchMethodArguments($methodSelect.val());
                }, 500);
            });
        }

        // Initialize for existing rows
        $('.argument-mapping-widget').each(function () {
            initArgumentMappingWidget($(this));
        });

        // Initialize for new rows added via "Add another"
        $(document).on('formset:added', function (event, $row, formsetName) {
            if (formsetName === 'steps') {
                $row.find('.argument-mapping-widget').each(function () {
                    initArgumentMappingWidget($(this));
                });
            }
        });
    });
});

