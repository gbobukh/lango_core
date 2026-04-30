(function ($) {
    $(document).ready(function () {

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

            if (stepType === 'ACTION') {
                methodRow.hide();
                argMappingRow.hide();
                authVarRow.hide();

                actionTypeRow.show();
                actionConfigRow.show();
            } else {
                // Default or API_CALL
                methodRow.show();
                argMappingRow.show();
                authVarRow.show();

                actionTypeRow.hide();
                actionConfigRow.hide();
            }
        }

        var ACTION_TEMPLATES = {
            'MERGE': '{\n    "input_a": "context.list_a",\n    "input_b": "context.list_b",\n    "join_key_a": "id",\n    "join_key_b": "other_id",\n    "match_type": "exact",\n    "how": "left"\n}',
            'FILTER': '{\n    "input": "context.list_to_filter",\n    "match": "all",\n    "filters": [\n        {\n            "field": "status",\n            "operator": "==",\n            "value": "active"\n        }\n    ]\n}'
        };

        function populateConfigTemplate(row) {
            var actionTypeSelect = row.find('select[id$="-action_type"]');
            var configTextarea = row.find('textarea[id$="-action_config"]');

            if (!actionTypeSelect.length || !configTextarea.length) return;

            var actionType = actionTypeSelect.val();
            var currentConfig = configTextarea.val().trim();

            // Only populate if empty or generic default
            if (currentConfig === '' || currentConfig === '{}') {
                var template = ACTION_TEMPLATES[actionType];
                if (template) {
                    configTextarea.val(template);
                }
            }
        }

        // Handle changes for Step Type (Visibility)
        $(document).on('change', 'select[id$="-step_type"]', function () {
            var row = $(this).closest('.dynamic-steps');
            toggleFields(row);
        });

        // Handle changes for Action Type (Template)
        $(document).on('change', 'select[id$="-action_type"]', function () {
            var row = $(this).closest('.dynamic-steps');
            populateConfigTemplate(row);
        });

        // Initialize existing rows
        $('.dynamic-steps').each(function () {
            toggleFields($(this));
        });

        // Handle new rows (Django dynamic inlines)
        $(document).on('formset:added', function (event, row) {
            toggleFields($(row));
        });

    });
})(django.jQuery);
