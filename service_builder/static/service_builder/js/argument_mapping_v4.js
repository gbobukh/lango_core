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
            const $methodSelect = $row.find('.field-method select');


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
                        vars = vars.concat(args);
                    }
                } catch (e) { }

                // 2. Outputs from previous steps (simple heuristic: look for inputs named *-output_variable_name)
                // We only care about steps BEFORE this one.
                // But for simplicity, we'll just grab all output vars for now.
                // A better approach would be to parse the formset order.
                $('.field-output_variable_name input').each(function () {
                    const val = $(this).val();
                    if (val && !vars.includes(val)) {
                        vars.push(val);
                    }
                });

                return vars;
            }

            function updateHiddenInput() {
                $textarea.val(JSON.stringify(currentMapping));
            }

            function renderTable(methodArgs) {
                $container.empty();
                const contextVars = getContextVariables();

                if (!methodArgs || methodArgs.length === 0) {
                    $table.hide();
                    $help.text('Selected method has no arguments.');
                    $help.show();
                    return;
                }

                $table.show();
                $help.hide();

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

                    // 1. Text Input for the template
                    const $input = $('<input type="text">').css({
                        'flex': '1',
                        'padding': '5px'
                    });

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

                    contextVars.forEach(v => {
                        $select.append($('<option>').val(v).text(v));
                    });

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

            // Initial load
            fetchMethodArguments($methodSelect.val());

            // Listen for Method change
            $methodSelect.on('change', function () {
                // Clear mapping when method changes? Maybe keep overlapping args?
                // For now, let's keep overlapping.
                fetchMethodArguments($(this).val());
            });

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
