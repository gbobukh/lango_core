(function () {
    function get$() {
        if (typeof django !== 'undefined' && typeof django.jQuery === 'function') return django.jQuery;
        if (typeof jQuery === 'function') return jQuery;
        if (typeof window !== 'undefined' && typeof window.jQuery === 'function') return window.jQuery;
        return null;
    }

    function init($) {
        if (window.__scenarioStepPolymorphicV11Initialized) return;
        window.__scenarioStepPolymorphicV11Initialized = true;

        /**
         * Django stacked inline for ScenarioStep uses prefix "steps" → wrapper id "steps-group".
         * Each row is div.inline-related (see admin/edit_inline/stacked.html).
         */
        var STEPS_GROUP_SEL = '#steps-group';

        function scenarioStepRows() {
            var $grp = $(STEPS_GROUP_SEL);
            if ($grp.length) {
                return $grp.find('.inline-related');
            }
            return $('.inline-related').filter(function () {
                return $(this).find('select[id$="-step_type"]').length > 0;
            });
        }

        function resolveScenarioStepRow(el) {
            var $row = $(el).closest('.inline-related');
            if (!$row.length) return $();
            if (!$row.find('select[id$="-step_type"]').length) return $();
            var $grp = $(STEPS_GROUP_SEL);
            if ($grp.length && !$row.closest(STEPS_GROUP_SEL).length) return $();
            return $row;
        }

        var ACTION_TEMPLATES = {
            'MERGE': '{\n    "input_a": "context.list_a",\n    "input_b": "context.list_b",\n    "join_key_a": "id",\n    "join_key_b": "other_id",\n    "match_type": "exact",\n    "how": "left"\n}',
            'FILTER': '{\n    "input": "context.list_to_filter",\n    "match": "all",\n    "filters": [\n        {\n            "field": "status",\n            "operator": "==",\n            "value": "active"\n        }\n    ]\n}',
            'TRANSFORM': '{\n    "input": "context.list_to_transform",\n    "rename": {\n        "old_field": "new_field"\n    }\n}',
            'TREE_STATS_BY_PATHS': '{\n    "state_input": "context.campaign_after",\n    "paths_input": "context.diff.changes",\n    "path_field": "path",\n    "branch_spec": {\n        "branch_level_node": "paths",\n        "leaf_collection": "offers",\n        "leaf_id_field": "offerId",\n        "leaf_flags": ["enabled"]\n    },\n    "metrics": {\n        "count_total_leaves": true,\n        "count_enabled_leaves": true\n    }\n}',
            'ENRICH': '{\n    "input": "context.main_list",\n    "source": "context.source_list",\n    "join": {\n        "main_key_field": "source_key_field"\n    },\n    "update_field": "list_field_in_main_to_extend",\n    "operation": "extend",\n    "mapping": {\n        "new_field": "source.source_field",\n        "const_id": -1\n    },\n    "unique_keys": ["id"]\n}',
            'FLATTEN_COLLECTION': '{\n    "input": "item",\n    "list_field": "source",\n    "parent_key": "campaignId",\n    "item_key": "referer"\n}'
        };

        function fieldRow(row, fieldName) {
            var selectors = [
                '.form-row.field-' + fieldName,
                '.field-' + fieldName,
                '[class*="field-' + fieldName + '"]'
            ];
            var found = $();
            for (var i = 0; i < selectors.length; i += 1) {
                found = row.find(selectors[i]).first();
                if (found.length) break;
            }
            if (!found.length) return found;
            var wrapped = found.closest('.form-row, .fieldBox, .field-' + fieldName);
            return wrapped.length ? wrapped.first() : found;
        }

        function toggleFields(row) {
            var stepTypeSelect = row.find('select[id$="-step_type"]');
            if (!stepTypeSelect.length) return;

            var stepType = stepTypeSelect.val();
            var methodRow = fieldRow(row, 'method');
            var argMappingRow = fieldRow(row, 'argument_mapping');
            var actionTypeRow = fieldRow(row, 'action_type');
            var actionConfigRow = fieldRow(row, 'action_config');
            var authVarRow = fieldRow(row, 'auth_context_variable');
            var iteratorVarRow = fieldRow(row, 'iterator_variable');

            if (stepType === 'ACTION') {
                methodRow.hide();
                argMappingRow.hide();
                authVarRow.hide();
                iteratorVarRow.show();
                actionTypeRow.show();
                actionConfigRow.show();
                return;
            }
            if (stepType === 'API_BATCH') {
                methodRow.hide();
                argMappingRow.hide();
                authVarRow.show();
                iteratorVarRow.show();
                actionTypeRow.hide();
                actionConfigRow.show();
                return;
            }

            methodRow.show();
            argMappingRow.show();
            authVarRow.show();
            iteratorVarRow.show();
            actionTypeRow.hide();
            actionConfigRow.hide();
        }

        function populateConfigTemplate(row) {
            var actionTypeSelect = row.find('select[id$="-action_type"]');
            var configTextarea = row.find('textarea[id$="-action_config"]');
            if (!actionTypeSelect.length || !configTextarea.length) return;
            if (configTextarea.closest('.api-batch-config-widget').length) return;

            var actionType = actionTypeSelect.val();
            var currentConfig = (configTextarea.val() || '').trim();
            if (currentConfig === '' || currentConfig === '{}') {
                var template = ACTION_TEMPLATES[actionType];
                if (template) configTextarea.val(template);
            }
        }

        function getContextVariablesForAction(currentRow) {
            var vars = [];
            try {
                var args = JSON.parse($('#id_arguments').val() || '[]');
                if (Array.isArray(args)) {
                    args.forEach(function (arg) {
                        if (typeof arg === 'string') vars.push(arg);
                        else if (arg && arg.name) vars.push(arg.name);
                    });
                }
            } catch (e) { }

            var allRows = scenarioStepRows();
            var curEl = currentRow && currentRow.jquery ? currentRow[0] : currentRow;
            var currentIndex = curEl ? allRows.index(curEl) : -1;
            allRows.each(function (index) {
                if (currentIndex >= 0 && index >= currentIndex) return;
                var outputInput = $(this).find('input[id$="-output_variable_name"]');
                if (outputInput.length && outputInput.val() && !vars.includes(outputInput.val())) {
                    vars.push(outputInput.val());
                }
                var contextInput = $(this).find('textarea[id$="-context_extraction"]');
                if (contextInput.length) {
                    try {
                        var jsonVal = JSON.parse(contextInput.val() || '{}');
                        Object.keys(jsonVal).forEach(function (key) {
                            if (!vars.includes(key)) vars.push(key);
                        });
                    } catch (e) { }
                }
            });
            return vars;
        }

        function addInsertVarHelper(row) {
            var textarea = row.find('textarea[id$="-action_config"]');
            if (!textarea.length) return;
            if (textarea.closest('.api-batch-config-widget').length) return;
            if (textarea.data('has-var-helper')) return;

            var container = $('<div>').css({ 'margin-bottom': '5px', 'display': 'flex', 'align-items': 'center', 'gap': '10px' });
            var select = $('<select>').css({ 'width': 'auto', 'max-width': '200px' });
            select.append($('<option>').val('').text('+ Insert Var'));
            textarea.before(container);
            container.append(select);
            textarea.data('has-var-helper', true);

            select.on('focus', function () {
                var currentVal = select.val();
                select.empty();
                select.append($('<option>').val('').text('+ Insert Var'));
                getContextVariablesForAction(row).forEach(function (v) {
                    select.append($('<option>').val(v).text(v));
                });
                if (window.GLOBAL_VARIABLES && window.GLOBAL_VARIABLES.length > 0) {
                    select.append($('<option>').prop('disabled', true).text('---GLOBAL---'));
                    window.GLOBAL_VARIABLES.forEach(function (v) {
                        select.append($('<option>').val(v).text(v));
                    });
                }
                select.val(currentVal);
            });

            select.on('change', function () {
                var val = $(this).val();
                if (!val) return;
                var domInput = textarea[0];
                var textToInsert = '{{ ' + val + ' }}';
                if (domInput && (domInput.selectionStart || domInput.selectionStart === 0)) {
                    var startPos = domInput.selectionStart;
                    var endPos = domInput.selectionEnd;
                    textarea.val(textarea.val().substring(0, startPos) + textToInsert + textarea.val().substring(endPos));
                    domInput.selectionStart = startPos + textToInsert.length;
                    domInput.selectionEnd = startPos + textToInsert.length;
                } else {
                    textarea.val((textarea.val() || '') + textToInsert);
                }
                $(this).val('');
                textarea.trigger('change').focus();
            });
        }

        function getAuthArguments() {
            var $scenarioArgsInput = $('#id_arguments');
            var authArgs = [];
            try {
                var args = JSON.parse($scenarioArgsInput.val() || '[]');
                if (!Array.isArray(args)) return authArgs;
                args.forEach(function (arg) {
                    if (typeof arg === 'object' && arg && arg.name) {
                        var modelName = (arg.model || '').toLowerCase();
                        if (arg.type === 'model' && (modelName === 'api auth id' || modelName.includes('apiauthid'))) authArgs.push(arg.name);
                        else if (arg.name.toLowerCase().includes('auth')) authArgs.push(arg.name);
                    } else if (typeof arg === 'string' && arg.toLowerCase().includes('auth')) {
                        authArgs.push(arg);
                    }
                });
            } catch (e) { }
            return authArgs;
        }

        function updateAuthSelectOptions(row) {
            var authInput = row.find('input[id$="-auth_context_variable"]');
            var select = row.find('select[id$="-auth_context_variable_select"]');
            if (!select.length) return;
            var currentVal = authInput.val();
            var authArgs = getAuthArguments();
            select.empty();
            select.append($('<option>').val('auth_id').text('Default Only (auth_id)'));
            authArgs.forEach(function (arg) {
                if (arg !== 'auth_id') select.append($('<option>').val(arg).text(arg));
            });
            if (currentVal && currentVal !== 'auth_id' && !authArgs.includes(currentVal)) {
                select.append($('<option>').val(currentVal).text(currentVal + ' (Custom/Old)'));
            }
            select.val(currentVal || 'auth_id');
        }

        function convertAuthInputToSelect(row) {
            var authInput = row.find('input[id$="-auth_context_variable"]');
            if (!authInput.length) return;
            if (authInput.data('converted-to-select')) {
                updateAuthSelectOptions(row);
                return;
            }
            var currentVal = authInput.val();
            var select = $('<select>').attr('id', authInput.attr('id') + '_select').css({ 'width': '300px', 'padding': '5px' });
            authInput.hide();
            authInput.after(select);
            authInput.data('converted-to-select', true);
            select.on('change', function () { authInput.val($(this).val()); });
            if (currentVal) authInput.val(currentVal);
            updateAuthSelectOptions(row);
        }

        function initRow(row) {
            toggleFields(row);
            convertAuthInputToSelect(row);
            addInsertVarHelper(row);
        }

        if (!window.GLOBAL_VARIABLES) {
            window.GLOBAL_VARIABLES = [];
            $.ajax({
                url: '/metadata/api/global-variables/',
                method: 'GET',
                success: function (data) { window.GLOBAL_VARIABLES = data.variables || []; }
            });
        }

        $(document).on('change', 'select[id$="-step_type"]', function () {
            var $row = resolveScenarioStepRow(this);
            if ($row.length) initRow($row);
        });

        $(document).on('change', 'select[id$="-action_type"]', function () {
            var $row = resolveScenarioStepRow(this);
            if ($row.length) populateConfigTemplate($row);
        });

        $(document).on('click', '.click-to-edit-trigger', function () {
            var $row = resolveScenarioStepRow(this);
            if (!$row.length) return;
            setTimeout(function () { initRow($row); }, 0);
        });

        $('#id_arguments').on('change keyup', function () {
            setTimeout(function () {
                scenarioStepRows().each(function () { convertAuthInputToSelect($(this)); });
            }, 300);
        });

        scenarioStepRows().each(function () { initRow($(this)); });
        $(document).on('formset:added', function (_event, row) {
            var $resolved = resolveScenarioStepRow(row);
            initRow($resolved.length ? $resolved : $(row));
        });
    }

    var $ = get$();
    if ($) {
        init($);
        return;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var delayed$ = get$();
        if (delayed$) init(delayed$);
        else console.error('scenario_step_polymorphic_v11: jQuery not available.');
    });
})();
