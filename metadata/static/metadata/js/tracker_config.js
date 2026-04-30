
document.addEventListener('DOMContentLoaded', function () {
    console.log('[TrackerConfig] JS Loaded');

    function initTrackerConfig(container) {
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

    // Global Lock Handling (for Admin Form)
    const lockCheckbox = document.getElementById('id_is_locked');
    if (lockCheckbox) {
        console.log('[TrackerConfig] Found Lock Checkbox');

        lockCheckbox.addEventListener('change', function (e) {
            const isLocked = e.target.checked;
            console.log('[TrackerConfig] Lock changed:', isLocked);

            // 1. Lock Widget Inputs
            widgets.forEach(widget => {
                const inputs = widget.querySelectorAll('.key-input');
                inputs.forEach(input => {
                    input.disabled = isLocked;
                });
            });

            // 2. Lock Tracker Selection
            const trackerSelect = document.getElementById('id_tracker');
            if (trackerSelect) {
                trackerSelect.disabled = isLocked;
            }
        });

        // Trigger immediately on load to ensure state is correct
        lockCheckbox.dispatchEvent(new Event('change'));
    }
});
