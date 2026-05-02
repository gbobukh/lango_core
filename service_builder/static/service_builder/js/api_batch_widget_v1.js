(function () {
    function get$() {
        if (typeof django !== "undefined" && typeof django.jQuery === "function") return django.jQuery;
        if (typeof jQuery === "function") return jQuery;
        if (typeof window.jQuery === "function") return window.jQuery;
        return null;
    }

    function parseJsonSafe(raw, fallback) {
        try {
            return JSON.parse(raw);
        } catch (e) {
            return fallback;
        }
    }

    function makeDefaultConfig() {
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
            report: { output_variable: "batch_report", include_requests: true, include_responses: true, truncate_response_body: 2000 }
        };
    }

    function buildMethodSelectOptions($row) {
        var $methodSelect = $row.find('select[id$="-method"]');
        var options = [];
        $methodSelect.find("option").each(function () {
            options.push({ value: $(this).attr("value"), label: $(this).text() });
        });
        return options;
    }

    function initWidget($widget) {
        var $textarea = $widget.find('textarea[name]').first();
        var $builder = $widget.find(".api-batch-builder");
        var $routes = $widget.find(".routes-container");
        var $toggleJson = $widget.find(".toggle-json-btn");
        var $jsonWrap = $widget.find(".json-editor-wrap");
        var $jsonEditor = $widget.find(".json-editor");
        var $row = $widget.closest(".inline-related");
        var methodOptions = buildMethodSelectOptions($row);

        var raw = ($textarea.val() || "{}").trim();
        var config = parseJsonSafe(raw, {});
        if (!config || typeof config !== "object") config = {};

        function ensureBatchConfig() {
            var defaults = makeDefaultConfig();
            if (!config.version) config.version = defaults.version;
            if (!config.source) config.source = defaults.source;
            if (!config.iterate_as) config.iterate_as = defaults.iterate_as;
            if (!config.path_graph) config.path_graph = defaults.path_graph;
            if (!config.routing) config.routing = defaults.routing;
            if (!Array.isArray(config.routing.methods)) config.routing.methods = [];
            if (!config.index_to_id) config.index_to_id = defaults.index_to_id;
            if (!config.execution) config.execution = defaults.execution;
            if (!config.error_policy) config.error_policy = defaults.error_policy;
            if (!config.report) config.report = defaults.report;
        }

        function syncHidden() {
            var pretty = JSON.stringify(config || {}, null, 2);
            $textarea.val(pretty).trigger("change");
            $jsonEditor.val(pretty);
        }

        function fetchMethodArgs(methodId, cb) {
            if (!methodId) return cb([]);
            $.ajax({
                url: "/admin/service_builder/scenario/api/method-arguments/" + methodId + "/",
                method: "GET",
                success: function (data) { cb(data.arguments || []); },
                error: function () { cb([]); }
            });
        }

        function renderRouteCard(route, index) {
            var $card = $('<div class="route-card" style="border:1px solid #eee; padding:8px; margin-bottom:8px; border-radius:4px;"></div>');
            var entityVal = route.entity || "";
            var methodId = route.method_id ? String(route.method_id) : "";
            if (!route.argument_mapping) route.argument_mapping = {};

            var $head = $('<div style="display:flex; gap:8px; align-items:center; margin-bottom:8px;"></div>');
            var $entity = $('<input type="text" placeholder="entity key (e.g. offer)" style="width:170px;" />').val(entityVal);
            var $method = $('<select style="min-width:320px;"></select>');
            methodOptions.forEach(function (opt) {
                var $opt = $("<option></option>").attr("value", opt.value || "").text(opt.label);
                if ((opt.value || "") === methodId) $opt.prop("selected", true);
                $method.append($opt);
            });
            var $remove = $('<button type="button" class="button">Remove</button>');
            $head.append($('<label style="font-weight:600;">Entity</label>')).append($entity);
            $head.append($('<label style="font-weight:600;">Method</label>')).append($method);
            $head.append($remove);
            $card.append($head);

            var $mappingTable = $('<table style="width:100%; border-collapse: collapse;"><thead><tr><th style="text-align:left; width:35%; border-bottom:1px solid #ddd; padding:4px;">Method Arg</th><th style="text-align:left; border-bottom:1px solid #ddd; padding:4px;">Template Mapping</th></tr></thead><tbody></tbody></table>');
            var $tbody = $mappingTable.find("tbody");
            $card.append($mappingTable);

            function saveRoute() {
                route.entity = $entity.val().trim();
                var mid = $method.val();
                route.method_id = mid ? parseInt(mid, 10) : null;
                if (route.method_id) route.method_ref = "method://service_builder." + ($method.find("option:selected").text() || "").trim();
                else route.method_ref = null;
                config.routing.methods[index] = route;
                syncHidden();
            }

            function renderArgs(args) {
                $tbody.empty();
                args.forEach(function (argName) {
                    var $tr = $("<tr></tr>");
                    var $name = $("<td style='padding:4px; border-bottom:1px solid #f1f1f1;'></td>").text(argName);
                    var current = route.argument_mapping[argName] || "";
                    var $input = $("<textarea rows='1' style='width:100%; min-height:30px;'></textarea>").val(current);
                    $input.on("change keyup", function () {
                        var v = $(this).val();
                        if (v) route.argument_mapping[argName] = v;
                        else delete route.argument_mapping[argName];
                        saveRoute();
                    });
                    var $val = $("<td style='padding:4px; border-bottom:1px solid #f1f1f1;'></td>").append($input);
                    $tr.append($name).append($val);
                    $tbody.append($tr);
                });
                Object.keys(route.argument_mapping).forEach(function (k) {
                    if (args.indexOf(k) === -1) delete route.argument_mapping[k];
                });
                saveRoute();
            }

            $entity.on("change keyup", saveRoute);
            $method.on("change", function () {
                route.argument_mapping = {};
                saveRoute();
                fetchMethodArgs($method.val(), renderArgs);
            });
            $remove.on("click", function () {
                config.routing.methods.splice(index, 1);
                renderRoutes();
                syncHidden();
            });

            fetchMethodArgs($method.val(), renderArgs);
            return $card;
        }

        function renderRoutes() {
            ensureBatchConfig();
            $routes.empty();
            config.routing.methods.forEach(function (route, index) {
                $routes.append(renderRouteCard(route, index));
            });
        }

        $widget.find(".add-route-btn").on("click", function () {
            ensureBatchConfig();
            config.routing.methods.push({ entity: "", method_id: null, method_ref: null, argument_mapping: {} });
            renderRoutes();
            syncHidden();
        });

        $toggleJson.on("click", function () {
            var shown = $jsonWrap.is(":visible");
            $jsonWrap.toggle(!shown);
            $toggleJson.text(shown ? "Show JSON" : "Hide JSON");
        });

        $jsonEditor.on("change", function () {
            var parsed = parseJsonSafe($jsonEditor.val(), null);
            if (parsed && typeof parsed === "object") {
                config = parsed;
                if (!config.routing) config.routing = { by: "op._leaf_entity", methods: [] };
                if (!Array.isArray(config.routing.methods)) config.routing.methods = [];
                renderRoutes();
                syncHidden();
            }
        });

        function updateVisibility() {
            var stepType = ($row.find('select[id$="-step_type"]').val() || "").trim();
            var isBatch = stepType === "API_BATCH";
            $builder.toggle(isBatch);
            if (isBatch) {
                ensureBatchConfig();
                renderRoutes();
                syncHidden();
            } else {
                $jsonEditor.val($textarea.val() || "{}");
            }
        }

        $row.on("change", 'select[id$="-step_type"]', updateVisibility);

        updateVisibility();
    }

    function initAll($) {
        $(document).ready(function () {
            $(".api-batch-config-widget").each(function () { initWidget($(this)); });
            $(document).on("formset:added", function (_event, row) {
                $(row).find(".api-batch-config-widget").each(function () { initWidget($(this)); });
            });
        });
    }

    var $ = get$();
    if ($) {
        initAll($);
        return;
    }

    document.addEventListener("DOMContentLoaded", function () {
        var delayed$ = get$();
        if (delayed$) {
            initAll(delayed$);
        } else {
            console.error("api_batch_widget_v1: jQuery not available; widget initialization skipped.");
        }
    });
})();
