/*
 * Auto-fill Tracker in BusinessActionVariant Inline when Scenario is selected.
 */
(function ($) {
    'use strict';

    $(document).ready(function () {

        // Function to update Tracker field
        function updateTracker($row) {
            const $scenarioSelect = $row.find('.field-scenario select');
            const $trackerSelect = $row.find('.field-tracker select');

            const scenarioId = $scenarioSelect.val();

            if (!scenarioId) {
                // Clear tracker if no scenario
                //$trackerSelect.val(''); // Optional: maybe keep previous? No, clear is safer.
                return;
            }

            // Call API
            $.ajax({
                url: '/admin/service_builder/businessaction/api/scenario-details/' + scenarioId + '/',
                method: 'GET',
                success: function (data) {
                    if (data.tracker_id) {
                        $trackerSelect.val(data.tracker_id);
                        // Trigger change event just in case (e.g. for Select2 if used)
                        $trackerSelect.trigger('change');
                    } else {
                        console.log("No tracker found for scenario " + scenarioId);
                    }
                },
                error: function (xhr, status, error) {
                    console.error("Error fetching scenario details:", error);
                }
            });
        }

        // Event Delegation for existing and dynamically added rows
        $(document).on('change', '.field-scenario select', function () {
            const $row = $(this).closest('.form-row'); // TabularInline rows are .form-row
            updateTracker($row);
        });

    });
})(django.jQuery);
