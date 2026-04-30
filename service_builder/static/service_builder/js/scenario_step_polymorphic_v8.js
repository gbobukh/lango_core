(function ($) {
    $(document).ready(function () {

        // --- PART 1: Hiding Fields logic (original) ---
        function toggleFields(row) {
            var stepTypeSelect = row.find('select[id$="-step_type"]');
            if (!stepTypeSelect.length) return;

            var stepType = stepTypeSelect.val();

            // Row selectors
            var methodRow = row.find('.form-row.field-method');
            var argMappingRow = row.find('.form-row.field-argument_mapping');

            var actionTypeRow = row.find('.form-row.field-action_type');
            var actionConfigRow = row.find('.form-row.field-action_config');

            var authVarRow = row.find('.form-row.field-auth_context_variable');

            // New: Iterator Variable Row
            var iteratorVarRow = row.find('.form-row.field-iterator_variable');

            if (stepType === 'ACTION') {
                methodRow.hide();
                argMappingRow.hide();
                authVarRow.hide();
                iteratorVarRow.hide(); // Hide iterator in Action mode (for now)

                actionTypeRow.show();
                actionConfigRow.show();
            } else {
                // Default or API_CALL
                methodRow.show();
                argMappingRow.show();
                authVarRow.show();
                iteratorVarRow.show(); // Show iterator in API mode

                actionTypeRow.hide();
                actionConfigRow.hide();
            }
        }

        var ACTION_TEMPLATES = {
            'MERGE': '{\n    "input_a": "context.list_a",\n    "input_b": "context.list_b",\n    "join_key_a": "id",\n    "join_key_b": "other_id",\n    "match_type": "exact",\n    "how": "left"\n}',
            'FILTER': '{\n    "input": "context.list_to_filter",\n    "match": "all",\n    "filters": [\n        {\n            "field": "status",\n            "operator": "==",\n            "value": "active"\n        }\n    ]\n}',
            'TRANSFORM': '{\n    "input": "context.list_to_transform",\n    "rename": {\n        "old_field": "new_field"\n    }\n}',
            'ENRICH': '{\n    "input": "context.main_list",\n    "source": "context.source_list",\n    "join": {\n        "main_key_field": "source_key_field"\n    },\n    "update_field": "list_field_in_main_to_extend",\n    "operation": "extend",\n    "mapping": {\n        "new_field": "source.source_field",\n        "const_id": -1\n    },\n    "unique_keys": ["id"]\n}'
        };

        function populateConfigTemplate(row) {
            var actionTypeSelect = row.find('select[id$="-action_type"]');
            var configTextarea = row.find('textarea[id$="-action_config"]');

            if (!actionTypeSelect.length || !configTextarea.length) return;

            var actionType = actionTypeSelect.val();
            var currentConfig = configTextarea.val().trim();

            if (currentConfig === '' || currentConfig === '{}') {
                var template = ACTION_TEMPLATES[actionType];
                if (template) {
                    configTextarea.val(template);
                }
            }
        }

        // --- PART 2: dynamic Auth Dropdown logic (New) ---

        function getAuthArguments() {
            var $scenarioArgsInput = $('#id_arguments');
            var authArgs = [];
            try {
                var args = JSON.parse($scenarioArgsInput.val() || '[]');
                if (Array.isArray(args)) {
                    args.forEach(function (arg) {
                        // We look for Type=Model and Model='Api Auth Id' (or 'integrations.ApiAuthID')
                        // Or simple heuristic: string containing 'auth'
                        if (typeof arg === 'object' && arg.name) {
                            if (arg.type === 'Model' && (arg.model === 'Api Auth Id' || arg.model === 'integrations.ApiAuthID')) {
                                authArgs.push(arg.name);
                            } else if (arg.name.toLowerCase().includes('auth')) {
                                // Fallback heuristic
                                authArgs.push(arg.name);
                            }
                        } else if (typeof arg === 'string') {
                            if (arg.toLowerCase().includes('auth')) {
                                authArgs.push(arg);
                            }
                        }
                    });
                }
            } catch (e) {
                console.error("Error parsing arguments for Auth Dropdown:", e);
            }
            return authArgs;
        }

        function convertAuthInputToSelect(row) {
            var authInput = row.find('input[id$="-auth_context_variable"]');
            if (!authInput.length) return;

            // Check if already converted
            if (authInput.data('converted-to-select')) {
                updateAuthSelectOptions(row);
                return;
            }

            var currentVal = authInput.val();

            // Create Select
            var select = $('<select>').attr('id', authInput.attr('id') + '_select').css({
                'width': '300px',
                'padding': '5px'
            });

            // Replace mechanics: Hide input, insert select
            authInput.hide();
            authInput.after(select);
            authInput.data('converted-to-select', true);

            // Bind change
            select.on('change', function () {
                authInput.val($(this).val());
            });

            updateAuthSelectOptions(row);
        }

        function updateAuthSelectOptions(row) {
            var authInput = row.find('input[id$="-auth_context_variable"]');
            var select = row.find('select[id$="-auth_context_variable_select"]');

            if (!select.length) return;

            var currentVal = authInput.val();
            var authArgs = getAuthArguments();

            select.empty();

            // Default Option
            select.append($('<option>').val('auth_id').text('Default Only (auth_id)'));

            // Argument Options
            authArgs.forEach(function (arg) {
                if (arg !== 'auth_id') {
                    select.append($('<option>').val(arg).text(arg));
                }
            });

            // Custom Value Option (if current value is not in list)
            if (currentVal && currentVal !== 'auth_id' && !authArgs.includes(currentVal)) {
                select.append($('<option>').val(currentVal).text(currentVal + ' (Custom/Old)'));
            }

            select.val(currentVal || 'auth_id');
        }


        // Global Update function
        function updateAllAuthDropdowns() {
            $('.dynamic-steps').each(function () {
                convertAuthInputToSelect($(this));
            });
        }


        // Event Listeners
        $(document).on('change', 'select[id$="-step_type"]', function () {
            var row = $(this).closest('.dynamic-steps');
            toggleFields(row);
        });

        $(document).on('change', 'select[id$="-action_type"]', function () {
            var row = $(this).closest('.dynamic-steps');
            populateConfigTemplate(row);
        });

        // Listen for Arguments change
        $('#id_arguments').on('change keyup', function () {
            // Debounce?
            setTimeout(updateAllAuthDropdowns, 500);
        });


        // Initialization
        $('.dynamic-steps').each(function () {
            var row = $(this);
            toggleFields(row);
            convertAuthInputToSelect(row);
        });

        $(document).on('formset:added', function (event, row) {
            var $row = $(row);
            toggleFields($row);
            convertAuthInputToSelect($row);
        });

    });
})(django.jQuery);
