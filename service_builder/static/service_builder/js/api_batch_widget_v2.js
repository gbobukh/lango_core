(function () {
    function get$() {
        if (typeof django !== "undefined" && typeof django.jQuery === "function") return django.jQuery;
        if (typeof jQuery === "function") return jQuery;
        if (typeof window !== "undefined" && typeof window.jQuery === "function") return window.jQuery;
        return null;
    }

    function parseJsonSafe(raw, fallback) {
        try { return JSON.parse(raw); } catch (_e) { return fallback; }
    }

    function toPrettyJson(value) {
        if (value == null || value === "") return "{}";
        if (typeof value === "string") {
            var parsed = parseJsonSafe(value, null);
            if (parsed !== null && typeof parsed === "object") return JSON.stringify(parsed, null, 2);
            return value;
        }
        try { return JSON.stringify(value, null, 2); } catch (_e) { return "{}"; }
    }

    function makeDefaultBatchConfig() {
        return {
            version: "1.0",
            source: { type: "context_path", value: "diff.0.changes" },
            iterate_as: "op",
            path_graph: {
                root: "item",
                entity_nodes: ["rules", "paths", "offers"],
                entity_alias: { rules: "rule", paths: "path", offers: "offer" },
                field_filters: ["enabled"]
            },
            routing: { by: "op._leaf_entity", methods: [], default: null },
            index_to_id: {},
            execution: { mode: "sequential", continue_on_error: true, max_ops: 500, dry_run: false },
            error_policy: {
                retry: { max_attempts: 2, backoff_ms: 300 },
                on_route_missing: "skip",
                on_mapping_error: "fail_op",
                on_http_error: "fail_op"
            },
            report: {
                output_variable: "batch_report",
                include_requests: true,
                include_responses: true,
                truncate_response_body: 2000
            }
        };
    }

    // ── shared context-variable helpers (mirrors argument_mapping_v14.js) ──────

    function ensureGlobalVariables($) {
        if (window.GLOBAL_VARIABLES) return;
        window.GLOBAL_VARIABLES = [];
        $.ajax({
            url: "/metadata/api/global-variables/",
            method: "GET",
            success: function (data) { window.GLOBAL_VARIABLES = data.variables || []; }
        });
    }

    function getContextVariables() {
        var vars = [];

        // 1. Scenario arguments
        try {
            var args = parseJsonSafe((document.getElementById("id_arguments") || {}).value || "[]", []);
            if (Array.isArray(args)) {
                args.forEach(function (arg) {
                    if (typeof arg === "string") { if (!vars.includes(arg)) vars.push(arg); }
                    else if (arg && arg.name) { if (!vars.includes(arg.name)) vars.push(arg.name); }
                });
            }
        } catch (_e) { }

        // 2. Output variables from all steps
        document.querySelectorAll(".field-output_variable_name input").forEach(function (el) {
            if (el.value && !vars.includes(el.value)) vars.push(el.value);
        });

        // 3. Context extraction keys from all steps
        document.querySelectorAll(".field-context_extraction textarea").forEach(function (el) {
            try {
                var obj = parseJsonSafe(el.value || "{}", {});
                Object.keys(obj).forEach(function (k) {
                    if (k && !vars.includes(k)) vars.push(k);
                });
            } catch (_e) { }
        });

        return vars;
    }

    function getTrackerArgNames() {
        var trackerArgs = [];
        try {
            var args = parseJsonSafe((document.getElementById("id_arguments") || {}).value || "[]", []);
            if (Array.isArray(args)) {
                args.forEach(function (arg) {
                    if (arg && typeof arg === "object" && arg.type === "model" && arg.name) {
                        var model = (arg.model || "").toLowerCase();
                        if (model.includes("metrics.tracker") || model.includes("integrations.tracker")) {
                            trackerArgs.push(arg.name);
                        }
                    }
                });
            }
        } catch (_e) { }
        return trackerArgs;
    }

    // Build and return the "+ Insert Var" <select> element for a mapping row
    function buildInsertVarSelect($) {
        var $select = $('<select>').css({ width: "auto", "max-width": "160px" });
        $select.append($("<option>").val("").text("+ Insert Var"));

        var contextVars = getContextVariables();
        contextVars.forEach(function (v) {
            $select.append($("<option>").val(v).text(v));
        });

        var globals = window.GLOBAL_VARIABLES || [];
        if (globals.length > 0) {
            $select.append($("<option>").prop("disabled", true).text("---GLOBAL---"));
            globals.forEach(function (v) {
                $select.append($("<option>").val(v).text(v));
            });

            var trackerArgNames = getTrackerArgNames();
            if (trackerArgNames.length > 0) {
                $select.append($("<option>").prop("disabled", true).text("---TRACKER KEYS---"));
                trackerArgNames.forEach(function (argName) {
                    globals.forEach(function (gv) {
                        var key = argName + ".keys." + gv;
                        $select.append($("<option>").val(key).text(key));
                    });
                });
            }
        }

        return $select;
    }

    // Wire Insert Var select to its sibling textarea
    function wireInsertVar($, $select, $input) {
        $select.on("focus", function () {
            // Rebuild options on every open so they reflect current state
            var current = $select.val();
            $select.empty();
            $select.append($("<option>").val("").text("+ Insert Var"));

            getContextVariables().forEach(function (v) {
                $select.append($("<option>").val(v).text(v));
            });

            var globals = window.GLOBAL_VARIABLES || [];
            if (globals.length > 0) {
                $select.append($("<option>").prop("disabled", true).text("---GLOBAL---"));
                globals.forEach(function (v) {
                    $select.append($("<option>").val(v).text(v));
                });
                var trackerArgNames = getTrackerArgNames();
                if (trackerArgNames.length > 0) {
                    $select.append($("<option>").prop("disabled", true).text("---TRACKER KEYS---"));
                    trackerArgNames.forEach(function (argName) {
                        globals.forEach(function (gv) {
                            $select.append($("<option>").val(argName + ".keys." + gv).text(argName + ".keys." + gv));
                        });
                    });
                }
            }

            if (current) $select.val(current);
        });

        $select.on("change", function () {
            var val = $(this).val();
            if (!val) return;
            var toInsert = "{{ " + val + " }}";
            var dom = $input[0];
            if (dom.selectionStart !== undefined) {
                var s = dom.selectionStart, e = dom.selectionEnd;
                $input.val($input.val().substring(0, s) + toInsert + $input.val().substring(e));
                dom.selectionStart = dom.selectionEnd = s + toInsert.length;
            } else {
                $input.val(($input.val() || "") + toInsert);
            }
            $(this).val("");
            $input.trigger("change").focus();
        });
    }

    // ── methods cache ──────────────────────────────────────────────────────────

    var methodsCache = null;

    function fetchMethods($, cb) {
        if (Array.isArray(methodsCache)) { cb(methodsCache); return; }

        var accumulated = [];

        function fetchPage(page) {
            $.ajax({
                url: "/admin/autocomplete/",
                method: "GET",
                data: {
                    app_label: "service_builder",
                    model_name: "scenariostep",
                    field_name: "method",
                    term: "",
                    page: page
                },
                success: function (data) {
                    var results = (data && data.results) ? data.results : [];
                    results.forEach(function (r) {
                        accumulated.push({ id: r.id, name: r.text, label: r.text });
                    });
                    if (data && data.pagination && data.pagination.more) {
                        fetchPage(page + 1);
                    } else {
                        methodsCache = accumulated;
                        cb(methodsCache);
                    }
                },
                error: function () { methodsCache = accumulated; cb(accumulated); }
            });
        }

        fetchPage(1);
    }

    // ── widget init ────────────────────────────────────────────────────────────

    function initWidget($, $widget) {
        if ($widget.data("api-batch-widget-init")) return;
        $widget.data("api-batch-widget-init", true);

        var $textarea   = $widget.find("textarea[name]").first();
        var $builder    = $widget.find(".api-batch-builder");
        var $routes     = $widget.find(".routes-container");
        var $toggleJson = $widget.find(".toggle-json-btn");
        var $jsonWrap   = $widget.find(".json-editor-wrap");
        var $jsonEditor = $widget.find(".json-editor");
        var $jsonLabel  = $widget.find(".api-batch-json-label");
        var $row        = $widget.closest(".inline-related");

        var batchConfig = {};
        var methods     = [];

        function currentStepType() {
            return ($row.find("select[id$=\"-step_type\"]").val() || "").trim();
        }

        function isBatchMode() {
            return currentStepType() === "API_BATCH";
        }

        function ensureBatchDefaults() {
            var d = makeDefaultBatchConfig();
            if (!batchConfig.version)    batchConfig.version    = d.version;
            if (!batchConfig.source)     batchConfig.source     = d.source;
            if (!batchConfig.iterate_as) batchConfig.iterate_as = d.iterate_as;
            if (!batchConfig.path_graph) batchConfig.path_graph = d.path_graph;
            if (!batchConfig.routing)    batchConfig.routing    = d.routing;
            if (!Array.isArray(batchConfig.routing.methods)) batchConfig.routing.methods = [];
            if (!batchConfig.index_to_id)  batchConfig.index_to_id  = d.index_to_id;
            if (!batchConfig.execution)    batchConfig.execution    = d.execution;
            if (!batchConfig.error_policy) batchConfig.error_policy = d.error_policy;
            if (!batchConfig.report)       batchConfig.report       = d.report;
        }

        function syncHiddenFromBatch() {
            var pretty = toPrettyJson(batchConfig);
            $textarea.val(pretty).trigger("change");
            $jsonEditor.val(pretty);
        }

        function fetchMethodArgs(methodId, cb) {
            if (!methodId) { cb([]); return; }
            $.ajax({
                url: "/admin/service_builder/scenario/api/method-arguments/" + methodId + "/",
                method: "GET",
                success: function (data) { cb(data.arguments || []); },
                error: function () { cb([]); }
            });
        }

        function saveRoute(index, route, $entity, $methodSel) {
            route.entity     = ($entity.val() || "").trim();
            var mid          = $methodSel.val();
            route.method_id  = mid ? parseInt(mid, 10) : null;
            route.method_ref = route.method_id
                ? ("method://service_builder." + (($methodSel.find("option:selected").text() || "").trim()))
                : null;
            batchConfig.routing.methods[index] = route;
            syncHiddenFromBatch();
        }

        // ── per-route mapping table (same UX as ArgumentMappingWidget) ─────────

        function renderMappingTable($tbody, route, index, methodArgs, $entity, $methodSel) {
            $tbody.empty();

            if (!methodArgs || methodArgs.length === 0) {
                $tbody.append(
                    $('<tr><td colspan="3" class="help" style="padding:6px; color:#888;">No arguments for selected method.</td></tr>')
                );
                // Prune stale keys
                route.argument_mapping = {};
                saveRoute(index, route, $entity, $methodSel);
                return;
            }

            // Prune keys not in current method contract
            var allowed = methodArgs.reduce(function (s, k) { s[k] = true; return s; }, {});
            Object.keys(route.argument_mapping).forEach(function (k) {
                if (!allowed[k]) delete route.argument_mapping[k];
            });

            methodArgs.forEach(function (arg) {
                var $tr = $("<tr>");

                var $tdArg = $('<td style="padding:5px 6px; border-bottom:1px solid #eee; vertical-align:top; width:30%;"></td>').text(arg);

                var $input = $('<textarea rows="1"></textarea>').css({
                    flex: "1",
                    padding: "4px",
                    "min-height": "28px",
                    "font-family": "monospace",
                    "font-size": "12px",
                    resize: "vertical",
                    "overflow-y": "hidden"
                }).val(route.argument_mapping[arg] || "");

                // Auto-resize
                function autoResize() {
                    this.style.height = "auto";
                    this.style.height = this.scrollHeight + "px";
                }
                $input.on("input", autoResize);
                setTimeout(function () { if ($input[0]) autoResize.call($input[0]); }, 0);

                $input.on("change keyup paste", function () {
                    var v = $(this).val();
                    if (v) route.argument_mapping[arg] = v;
                    else   delete route.argument_mapping[arg];
                    saveRoute(index, route, $entity, $methodSel);
                });

                var $insertVar = buildInsertVarSelect($);
                wireInsertVar($, $insertVar, $input);

                var $flex = $('<div>').css({ display: "flex", gap: "8px", "align-items": "flex-start" });
                $flex.append($input, $insertVar);

                var $tdInput = $('<td style="padding:5px 6px; border-bottom:1px solid #eee;"></td>').append($flex);
                $tr.append($tdArg, $tdInput);
                $tbody.append($tr);
            });
        }

        // ── route card ─────────────────────────────────────────────────────────

        function renderRouteCard(route, index) {
            if (!route.argument_mapping) route.argument_mapping = {};

            var $card = $('<div class="route-card">').css({
                border: "1px solid #ddd",
                padding: "10px",
                "margin-bottom": "12px",
                "border-radius": "4px",
                background: "#fafafa"
            });

            // ── header: entity + method + remove ──────────────────────────────

            var $head = $('<div>').css({ display: "flex", gap: "10px", "align-items": "center", "flex-wrap": "wrap", "margin-bottom": "10px" });

            var $entityWrap = $('<div>').css({ display: "flex", "align-items": "center", gap: "6px" });
            $entityWrap.append($('<label style="font-weight:600; white-space:nowrap;">Entity key</label>'));
            var $entity = $('<input type="text" placeholder="e.g. offer">').css({ width: "150px" }).val(route.entity || "");

            var $methodWrap = $('<div>').css({ display: "flex", "align-items": "center", gap: "6px", flex: "1", "min-width": "260px" });
            $methodWrap.append($('<label style="font-weight:600; white-space:nowrap;">Method</label>'));
            var $methodSel = $('<select>').css({ flex: "1", "min-width": "260px" });
            $methodSel.append($("<option>").val("").text("— select method —"));
            var selectedId = route.method_id ? String(route.method_id) : "";
            methods.forEach(function (opt) {
                var idStr = String(opt.id);
                var $opt  = $("<option>").val(idStr).text(opt.label || opt.name || idStr);
                if (idStr === selectedId) $opt.prop("selected", true);
                $methodSel.append($opt);
            });

            var $remove = $('<button type="button" class="button">Remove</button>').css({ "margin-left": "auto" });

            $entityWrap.append($entity);
            $methodWrap.append($methodSel);
            $head.append($entityWrap, $methodWrap, $remove);
            $card.append($head);

            // ── mapping table ─────────────────────────────────────────────────

            var $table = $(
                '<table style="width:100%; border-collapse:collapse;">' +
                '<thead><tr>' +
                '<th style="text-align:left; width:30%; border-bottom:1px solid #ddd; padding:5px 6px;">Method arg</th>' +
                '<th style="text-align:left; border-bottom:1px solid #ddd; padding:5px 6px;">Context variable</th>' +
                '</tr></thead><tbody></tbody></table>'
            );
            var $tbody = $table.find("tbody");
            $card.append($table);

            // ── event handlers ────────────────────────────────────────────────

            $entity.on("change keyup", function () { saveRoute(index, route, $entity, $methodSel); });

            $methodSel.on("change", function () {
                route.argument_mapping = {};
                saveRoute(index, route, $entity, $methodSel);
                fetchMethodArgs($methodSel.val(), function (args) {
                    renderMappingTable($tbody, route, index, args, $entity, $methodSel);
                });
            });

            $remove.on("click", function () {
                batchConfig.routing.methods.splice(index, 1);
                renderRoutes();
                syncHiddenFromBatch();
            });

            // Initial load of args
            fetchMethodArgs($methodSel.val(), function (args) {
                renderMappingTable($tbody, route, index, args, $entity, $methodSel);
            });

            return $card;
        }

        function renderRoutes() {
            ensureBatchDefaults();
            $routes.empty();
            if (!methods.length) {
                $routes.append('<p class="help" style="color:#888;">No methods loaded. Save the scenario first if methods are not appearing.</p>');
                return;
            }
            batchConfig.routing.methods.forEach(function (route, index) {
                $routes.append(renderRouteCard(route, index));
            });
        }

        // ── visibility / mode switching ────────────────────────────────────────

        function activateBatchMode() {
            var raw = parseJsonSafe(($textarea.val() || "{}").trim(), null);
            batchConfig = (raw && typeof raw === "object") ? raw : {};
            ensureBatchDefaults();

            $jsonLabel.hide();
            $toggleJson.show().text("Show JSON");
            $jsonWrap.hide();
            $builder.show();

            fetchMethods($, function (loaded) {
                methods = loaded || [];
                renderRoutes();
                syncHiddenFromBatch();
            });
        }

        function activateJsonMode() {
            $builder.hide();
            $toggleJson.hide();
            $jsonWrap.show();
            $jsonLabel.show();
            $jsonEditor.val(toPrettyJson($textarea.val() || "{}"));
        }

        function updateVisibility() {
            if (isBatchMode()) activateBatchMode();
            else               activateJsonMode();
        }

        // ── events ─────────────────────────────────────────────────────────────

        $jsonEditor.on("change", function () {
            if (isBatchMode()) {
                var parsed = parseJsonSafe($jsonEditor.val(), null);
                if (!parsed || typeof parsed !== "object") return;
                batchConfig = parsed;
                if (!batchConfig.routing) batchConfig.routing = { by: "op._leaf_entity", methods: [] };
                if (!Array.isArray(batchConfig.routing.methods)) batchConfig.routing.methods = [];
                renderRoutes();
                syncHiddenFromBatch();
            } else {
                $textarea.val($jsonEditor.val()).trigger("change");
            }
        });

        $widget.find(".add-route-btn").on("click", function () {
            ensureBatchDefaults();
            batchConfig.routing.methods.push({ entity: "", method_id: null, method_ref: null, argument_mapping: {} });
            renderRoutes();
            syncHiddenFromBatch();
        });

        $toggleJson.on("click", function () {
            var visible = $jsonWrap.is(":visible");
            $jsonWrap.toggle(!visible);
            $toggleJson.text(visible ? "Show JSON" : "Hide JSON");
        });

        $row.on("change", "select[id$=\"-step_type\"]", function () {
            updateVisibility();
        });

        updateVisibility();
    }

    // ── bootstrap ──────────────────────────────────────────────────────────────

    function initAll($) {
        if (window.__apiBatchWidgetV2Initialized) return;
        window.__apiBatchWidgetV2Initialized = true;

        ensureGlobalVariables($);

        function scanAndInit() {
            $(".api-batch-config-widget").each(function () { initWidget($, $(this)); });
        }

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", scanAndInit);
        } else {
            scanAndInit();
        }

        $(document).on("formset:added", function (_event, row) {
            $(row).find(".api-batch-config-widget").each(function () { initWidget($, $(this)); });
        });
    }

    var $ = get$();
    if ($) { initAll($); return; }
    document.addEventListener("DOMContentLoaded", function () {
        var delayed$ = get$();
        if (delayed$) initAll(delayed$);
        else console.error("api_batch_widget_v2: jQuery not available.");
    });
})();
