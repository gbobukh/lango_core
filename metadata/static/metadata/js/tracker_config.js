
document.addEventListener('DOMContentLoaded', function () {
    console.log('[TrackerConfig] JS Loaded');

    function initTrackerConfig(container) {
        if (container.classList.contains('config-widget-locked')) {
            return;
        }
        console.log('[TrackerConfig] Init widget:', container);
        const table = container.querySelector('.tracker-config-table');
        const hiddenInput = container.querySelector('input[type="hidden"]');

        if (!table || !hiddenInput) {
            console.error('[TrackerConfig] Table or Input not found in', container);
            return;
        }

        function updateState() {
            const config = {};
            const rows = table.querySelectorAll('tbody tr');

            rows.forEach(row => {
                const varName = row.getAttribute('data-var-name');
                const keyInput = row.querySelector('.key-input');

                if (!keyInput) return;

                const value = keyInput.value.trim();

                // Only save if not empty? Or save empty string to explicitely clear?
                // Let's save empty string essentially, or we can omit it.
                // PublisherConfig saves everything. Let's save everything for consistency.
                if (value) {
                    config[varName] = value;
                }
            });

            const jsonVal = JSON.stringify(config);
            hiddenInput.value = jsonVal;
            console.log('[TrackerConfig] State Updated:', jsonVal);
        }

        // Use Event Delegation or direct binding
        // Since we have inputs, 'input' event is best.
        table.addEventListener('input', function (e) {
            if (e.target.classList.contains('key-input')) {
                updateState();
            }
        });
    }

    // Initialize
    const widgets = document.querySelectorAll('.tracker-config-widget');
    console.log('[TrackerConfig] Found widgets:', widgets.length);
    widgets.forEach(initTrackerConfig);
});
