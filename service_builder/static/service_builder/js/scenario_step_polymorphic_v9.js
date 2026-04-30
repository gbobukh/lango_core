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
                iteratorVarRow.show(); // Show iterator for Action (e.g. FLATTEN_COLLECTION over black_list)

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
            'ENRICH': '{\n    "input": "context.main_list",\n    "source": "context.source_list",\n    "join": {\n        "main_key_field": "source_key_field"\n    },\n    "update_field": "list_field_in_main_to_extend",\n    "operation": "extend",\n    "mapping": {\n        "new_field": "source.source_field",\n        "const_id": -1\n    },\n    "unique_keys": ["id"]\n}',
            'FLATTEN_COLLECTION': '{\n    "input": "item",\n    "list_field": "source",\n    "parent_key": "campaignId",\n    "item_key": "referer"\n}'
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


        // --- PART 1.5: Variable Insertion Logic (Action Config) ---

        function getContextVariablesForAction(currentRow) {
            var vars = [];
            // 1. Scenario Arguments
            try {
                var args = JSON.parse($('#id_arguments').val() || '[]');
                if (Array.isArray(args)) {
                    args.forEach(function (arg) {
                        if (typeof arg === 'string') vars.push(arg);
                        else if (arg && arg.name) vars.push(arg.name);
                    });
                }
            } catch (e) { }

            // 2. Previous Steps Outputs
            var allRows = $('.dynamic-steps');
            var currentIndex = allRows.index(currentRow);

            allRows.each(function (index) {
                if (index < currentIndex) {
                    var outputInput = $(this).find('input[id$="-output_variable_name"]');
                    if (outputInput.length && outputInput.val()) {
                        var val = outputInput.val();
                        if (!vars.includes(val)) vars.push(val);
                    }
                    // Also Context Extraction? 
                    var contextInput = $(this).find('textarea[id$="-context_extraction"]');
                    if (contextInput.length) {
                        try {
                            var jsonVal = JSON.parse(contextInput.val() || '{}');
                            Object.keys(jsonVal).forEach(function (key) {
                                if (!vars.includes(key)) vars.push(key);
                            });
                        } catch (e) { }
                    }
                }
            });
            return vars;
        }

        function addInsertVarHelper(row) {
            var textarea = row.find('textarea[id$="-action_config"]');
            if (!textarea.length) return;

            // Check if already added
            if (textarea.data('has-var-helper')) return;

            // Create container
            var container = $('<div>').css({
                'margin-bottom': '5px',
                'display': 'flex',
                'align-items': 'center',
                'gap': '10px'
            });

            var select = $('<select>').css({
                'width': 'auto',
                'max-width': '200px'
            });
            select.append($('<option>').val('').text('+ Insert Var'));

            // Append to DOM (Insert before textarea)
            textarea.before(container);
            container.append(select);
            textarea.data('has-var-helper', true);

            // Load Variables on click or focus? 
            // To keep it fresh, let's load on focus of the select
            select.on('focus', function () {
                var currentVal = select.val();
                select.empty();
                select.append($('<option>').val('').text('+ Insert Var'));

                // Local Vars
                var localVars = getContextVariablesForAction(row);
                localVars.forEach(function (v) {
                    select.append($('<option>').val(v).text(v));
                });

                // Global Vars
                if (window.GLOBAL_VARIABLES && window.GLOBAL_VARIABLES.length > 0) {
                    select.append($('<option>').prop('disabled', true).text('---GLOBAL---'));
                    window.GLOBAL_VARIABLES.forEach(function (v) {
                        select.append($('<option>').val(v).text(v));
                    });

                    // Smart Tracker Keys Detection (Action Config)
                    var trackerArgs = [];
                    // 1. Scan Scenario Arguments
                    try {
                        var args = JSON.parse($('#id_arguments').val() || '[]');
                        if (Array.isArray(args)) {
                            args.forEach(function (arg) {
                                if (arg && typeof arg === 'object' && arg.type === 'model' && arg.name) {
                                    var model = (arg.model || '').toLowerCase();
                                    if (model.includes('metrics.tracker') || model.includes('integrations.tracker')) {
                                        trackerArgs.push(arg.name);
                                    }
                                }
                            });
                        }
                    } catch (e) { }

                    // 2. Add Options
                    if (trackerArgs.length > 0) {
                        select.append($('<option>').prop('disabled', true).text('---TRACKER KEYS---'));
                        trackerArgs.forEach(function (argName) {
                            window.GLOBAL_VARIABLES.forEach(function (gv) {
                                var key = argName + '.keys.' + gv;
                                select.append($('<option>').val(key).text(key));
                            });
                        });
                    }
                }

                select.val(currentVal);
            });

            // Handle Insert
            select.on('change', function () {
                var val = $(this).val();
                if (val) {
                    var domInput = textarea[0];
                    var textToInsert = '{{ ' + val + ' }}';

                    if (domInput.selectionStart || domInput.selectionStart == '0') {
                        var startPos = domInput.selectionStart;
                        var endPos = domInput.selectionEnd;
                        textarea.val(textarea.val().substring(0, startPos) +
                            textToInsert +
                            textarea.val().substring(endPos));
                        // update cursor?
                        domInput.selectionStart = startPos + textToInsert.length;
                        domInput.selectionEnd = startPos + textToInsert.length;
                    } else {
                        textarea.val(textarea.val() + textToInsert);
                    }
                    $(this).val('');
                    // Trigger change?
                    textarea.trigger('change');
                    textarea.focus();
                }
            });
        }

        // Fetch Globals once
        if (!window.GLOBAL_VARIABLES) {
            window.GLOBAL_VARIABLES = [];
            $.ajax({
                url: '/metadata/api/global-variables/',
                method: 'GET',
                success: function (data) {
                    window.GLOBAL_VARIABLES = data.variables || [];
                }
            });
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
                            var modelName = (arg.model || '').toLowerCase();
                            // Robust check for ApiAuthID (legacy 'api auth id' or 'integrations.apiauthid')
                            // Also checking for 'auth' in the name as a fallback for flexibility
                            if (arg.type === 'model' && (modelName === 'api auth id' || modelName.includes('apiauthid'))) {
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
            addInsertVarHelper(row);
        });

        $(document).on('formset:added', function (event, row) {
            var $row = $(row);
            toggleFields($row);
            convertAuthInputToSelect($row);
            addInsertVarHelper($row);
        });

    });
})(django.jQuery);
