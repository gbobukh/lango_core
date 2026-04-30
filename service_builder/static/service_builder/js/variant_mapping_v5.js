/*
 variant_mapping_v1.js
 Handles dynamic argument mapping for Business Action Variants.
*/
document.addEventListener('DOMContentLoaded', function () {
    let $ = null;
    if (typeof django !== 'undefined' && django.jQuery) {
        $ = django.jQuery;
    } else if (typeof jQuery !== 'undefined') {
        $ = jQuery;
    }

    if (!$ || typeof $ !== 'function') {
        console.error('VariantMapping: Valid jQuery not found.');
        return;
    }

    $(document).ready(function () {

        function getBusinessActionConfig(fieldId) {
            // Field ID is typically #id_arguments or #id_output_variables
            // These widgets (TypedArgumentWidget) store value as JSON string in a hidden or text input,
            // or we might need to look at the DOM structure if it's complex.
            // But TypedArgumentWidget usually updates the underlying input on save.
            // Wait, TypedArgumentWidget might be complex.
            // Let's assume it updates the main textarea/input referencing the field name.

            const $input = $('#' + fieldId);
            let val = $input.val();

            // If it's the TypedWidget, there might be a hidden input.
            // Let's rely on the input with correct ID.
            try {
                const parsed = JSON.parse(val || '[]');
                // If list of dicts (TypedArgument), map to names.
                // e.g. [{"name": "foo", "type": "String"}] -> ["foo"]
                if (Array.isArray(parsed)) {
                    return parsed.map(item => {
                        if (typeof item === 'object' && item.name) return item.name;
                        return item;
                    });
                }
                return [];
            } catch (e) {
                return [];
            }
        }

        function initVariantRow($row) {
            const $scenarioSelect = $row.find('select[name$="-scenario"]');

            // Widgets
            const $inputMappingWidget = $row.find('.field-input_mapping .argument-mapping-widget').first();
            const $outputMappingWidget = $row.find('.field-output_mapping .argument-mapping-widget').first();

            if ($inputMappingWidget.length === 0 || $outputMappingWidget.length === 0) return;

            // --- Widget Controller Wrappers ---
            // We reuse the logic from argument_mapping_workflow.js but adapted manually since we don't have a shared library yet.
            // Ideally we should refactor to a View/Controller class.

            function renderWidget($widget, rows, contextVars, label) {
                const $textarea = $widget.find('textarea');
                const $container = $widget.find('.mapping-table tbody');
                const $table = $widget.find('.mapping-table');
                const $help = $widget.find('.help');

                // Update specific help text
                // Update specific help text and headers
                const $headerArg = $table.find('th').eq(0);
                const $headerVal = $table.find('th').eq(1);

                if (label === 'Input Mapping') {
                    $help.text('Select a Scenario to map Business Action Arguments to Scenario Arguments.');
                    $headerArg.text('Scenario Argument');
                    $headerVal.text('Action Argument (Value)');
                } else if (label === 'Output Mapping') {
                    $help.text('Select a Scenario to map Scenario Results to Business Action Outputs.');
                    $headerArg.text('Action Output');
                    $headerVal.text('Scenario Result (Value)');
                }

                let currentMapping = {};
                try { currentMapping = JSON.parse($textarea.val() || '{}'); } catch (e) { }

                $container.empty();

                if (!rows || rows.length === 0) {
                    $table.hide();
                    $help.show();
                    return;
                }
                $table.show();
                $help.hide();

                rows.forEach(arg => {
                    const argName = (typeof arg === 'object' && arg !== null) ? arg.name : arg;
                    const $tr = $('<tr>');
                    const $tdArg = $('<td>').text(argName);
                    const $tdInput = $('<td>');

                    const $flex = $('<div>').css({ display: 'flex', gap: '10px', alignItems: 'flex-start' });
                    // Use textarea for better visibility of long values
                    const $input = $('<textarea rows="1" style="flex:1; min-height: 30px; resize: vertical; overflow-y: hidden;">');

                    // Auto-resize logic
                    function autoResize() {
                        this.style.height = 'auto';
                        this.style.height = (this.scrollHeight) + 'px';
                    }
                    $input.on('input', autoResize);

                    if (currentMapping[argName]) {
                        $input.val(currentMapping[argName]);
                        // Trigger resize after value is set (need small delay or attachment to DOM)
                        setTimeout(() => autoResize.call($input[0]), 0);
                    }

                    const $select = $('<select style="width:auto;max-width:150px">');
                    $select.append($('<option>').val('').text('+ Var'));
                    contextVars.forEach(v => {
                        const vName = (typeof v === 'object' && v !== null) ? v.name : v;
                        $select.append($('<option>').val(vName).text(vName));
                    });

                    $select.on('change', function () {
                        const val = $(this).val();
                        if (val) {
                            $input.val($input.val() + '{{ ' + val + ' }}');
                            $input.trigger('change');
                            $(this).val('');
                        }
                    });

                    $input.on('change keyup paste', function () {
                        const val = $(this).val();
                        if (val) currentMapping[argName] = val;
                        else delete currentMapping[argName];
                        $textarea.val(JSON.stringify(currentMapping));
                    });

                    $flex.append($input, $select);
                    $tdInput.append($flex);
                    $tr.append($tdArg, $tdInput);
                    $container.append($tr);
                });
            }


            function updateMappings(scenarioId) {
                // 1. Get Parent Contexts
                const actionArgs = getBusinessActionConfig('id_arguments');
                const actionOutputs = getBusinessActionConfig('id_output_variables');

                if (!scenarioId) {
                    // Reset or Clear
                    renderWidget($inputMappingWidget, [], actionArgs, 'Input Mapping');
                    renderWidget($outputMappingWidget, actionOutputs, [], 'Output Mapping'); // No scenario context
                    return;
                }

                // 2. Fetch Scenario Details
                const url = '/admin/service_builder/businessaction/api/scenario-details/' + scenarioId + '/?t=' + new Date().getTime();

                $.ajax({
                    url: url,
                    method: 'GET',
                    success: function (data) {
                        const scenarioArgs = data.arguments || [];
                        const scenarioReturns = data.return_variables || [];


                        // INPUT MAPPING:
                        // Rows: Scenario Args (Target)
                        // Context: Action Args (Source)
                        renderWidget($inputMappingWidget, scenarioArgs, actionArgs, 'Input Mapping');

                        // OUTPUT MAPPING:
                        // Rows: Action Outputs (Target)
                        // Context: Scenario Returns (Source)
                        renderWidget($outputMappingWidget, actionOutputs, scenarioReturns, 'Output Mapping');
                    },
                    error: function (xhr, status, error) {
                        console.error('VariantMapping Error:', error);
                    }
                });
            }


            // Init
            updateMappings($scenarioSelect.val());

            // Listeners
            $scenarioSelect.on('change', function () {
                updateMappings($(this).val());
            });

            // Listen to parent fields changes? 
            // Might be heavy. But user inputs args/outputs in the same form.
            $('#id_arguments, #id_output_variables').on('change', function () {
                setTimeout(() => updateMappings($scenarioSelect.val()), 500);
            });
        }

        $('.inline-related').each(function () {
            initVariantRow($(this));
        });

        $(document).on('formset:added', function (event, $row) {
            initVariantRow($row);
        });
    });
});
