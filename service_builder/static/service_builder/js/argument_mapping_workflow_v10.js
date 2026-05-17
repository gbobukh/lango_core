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

            const $row = $widget.closest('.inline-related');
            const $actionSelect = $row.find('.field-business_action select');
            const $workflowArgsInput = $('.typed-arguments-widget input[type="hidden"]');
            const $iteratorInput = $row.find('input[id$="-iterator_variable"]');

            let currentMapping = {};
            try {
                currentMapping = JSON.parse($textarea.val() || '{}');
            } catch (e) {
                currentMapping = {};
            }

            function getContextVariables() {
                let vars = [];

                function getTextByLabel($stepRow, labelText) {
                    let text = '';
                    $stepRow.find('label').each(function () {
                        if ($(this).text().indexOf(labelText) !== -1) {
                            text = $(this).siblings('.readonly').text();
                            return false;
                        }
                    });
                    return text;
                }

                const $rows = $('.inline-related');
                const $currentRow = $widget.closest('.inline-related');
                const currentIndex = $rows.index($currentRow);

                let workflowArgs = window.WORKFLOW_ARGUMENTS || [];
                if (!workflowArgs || workflowArgs.length === 0) {
                    try {
                        const workflowArgsStr = $workflowArgsInput.val();
                        if (workflowArgsStr) {
                            workflowArgs = JSON.parse(workflowArgsStr);
                        }
                    } catch (e) {
                        console.error('Error parsing workflow arguments for context:', e);
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

                $rows.each(function (index) {
                    if (index < currentIndex) {
                        const text = getTextByLabel($(this), 'Outputs (Contract)');
                        if (text && text !== '-') {
                            text.split(',').forEach(part => {
                                let v = part.trim().replace(/\s*\(.*?\)$/, '');
                                if (v && !vars.includes(v)) vars.push(v);
                            });
                        }
                    }
                });

                const iteratorVar = ($iteratorInput.val() || '').trim();
                if (iteratorVar) {
                    if (!vars.includes('item')) {
                        vars.push('item');
                    }
                }

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
                    }
                    $table.hide();
                    $help.text('Selected Business Action has no arguments.');
                    $help.show();
                    return;
                }

                if (!isManualMode) {
                    const allowedKeys = new Set((actionArgs || []).map(getArgName).filter(Boolean));
                    const pruned = {};
                    Object.entries(currentMapping || {}).forEach(([key, value]) => {
                        if (allowedKeys.has(key)) {
                            pruned[key] = value;
                        }
                    });
                    currentMapping = pruned;
                    updateHiddenInput();
                }

                $table.show();
                if (!isManualMode) $help.hide();

                actionArgs.forEach(arg => {
                    const $tr = $('<tr>');
                    const $tdArg = $('<td>');

                    let argName = arg;
                    let argType = '';
                    if (typeof arg === 'object' && arg !== null) {
                        argName = arg.name;
                        if (arg.type) argType = ` <span style="color:#888; font-size:0.9em;">(${arg.type})</span>`;
                    }

                    if (isManualMode) {
                        const $keyInput = $('<input type="text" placeholder="Arg Name">').val(argName).css({ width: '100%' });
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
                        $tdArg.html(argName + argType);
                    }

                    const $tdInput = $('<td>');
                    const placeholderText = `Implicit: {{ ${argName} }}`;
                    const $flexContainer = $('<div>').css({ display: 'flex', gap: '10px', alignItems: 'center' });
                    const $input = $('<input type="text">').attr('placeholder', placeholderText).css({ flex: '1', padding: '5px' });

                    if (currentMapping[argName]) {
                        $input.val(currentMapping[argName]);
                    }

                    const $select = $('<select>').css({ width: 'auto', maxWidth: '150px' });
                    $select.append($('<option>').val('').text('+ Insert Var'));
                    contextVars.forEach(v => $select.append($('<option>').val(v).text(v)));

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
                            if (domInput.selectionStart || domInput.selectionStart === '0') {
                                const startPos = domInput.selectionStart;
                                const endPos = domInput.selectionEnd;
                                $input.val(
                                    currentVal.substring(0, startPos) + '{{ ' + val + ' }}' + currentVal.substring(endPos)
                                );
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
                        currentMapping['new_arg_' + Math.floor(Math.random() * 1000)] = '';
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

            $iteratorInput.on('change keyup', function () {
                fetchActionArguments($actionSelect.val());
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

        $(document).on('formset:added', function (event, row) {
            if (!row) return;
            const $row = $(row);
            if ($row.find('.argument-mapping-widget').length > 0) {
                $row.find('.argument-mapping-widget').each(function () {
                    initArgumentMappingWidget($(this));
                });
            }
        });
    });
});
