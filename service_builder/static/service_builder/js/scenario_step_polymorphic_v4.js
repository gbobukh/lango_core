(function ($) {
    $(document).ready(function () {

        function toggleFields(row) {
            var stepTypeSelect = row.find('select[id$="-step_type"]');
            if (!stepTypeSelect.length) return;

            var stepType = stepTypeSelect.val();

            // Now that fields are ungrouped in admin.py, each lives in a .form-row.field-<name>
            // We can simply toggle the whole row.

            var methodRow = row.find('.form-row.field-method');
            var argMappingRow = row.find('.form-row.field-argument_mapping');

            var actionTypeRow = row.find('.form-row.field-action_type');
            var actionConfigRow = row.find('.form-row.field-action_config');

            if (stepType === 'ACTION') {
                methodRow.hide();
                argMappingRow.hide();

                actionTypeRow.show();
                actionConfigRow.show();
            } else {
                methodRow.show();
                argMappingRow.show();

                actionTypeRow.hide();
                actionConfigRow.hide();
            }
        }

        // Initialize existing rows
        $('.dynamic-steps').each(function () {
            toggleFields($(this));
        });

        var ACTION_TEMPLATES = {
            'MERGE': '{\n    "input_a": "context.list_a",\n    "input_b": "context.list_b",\n    "join_key": "id",\n    "how": "left"\n}'
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

        // Handle new rows (Django dynamic inlines)
        $(document).on('formset:added', function (event, row) {
            toggleFields($(row));
        });

    });
})(django.jQuery);
