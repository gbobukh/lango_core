document.addEventListener('DOMContentLoaded', function () {
    console.log('[PublisherConfig] JS Loaded');

    function initPublisherConfig(container) {
        if (container.classList.contains('config-widget-locked')) {
            return;
        }
        console.log('[PublisherConfig] Init widget:', container);
        const table = container.querySelector('.publisher-config-table');
        const hiddenInput = container.querySelector('input[type="hidden"]');

        if (!table || !hiddenInput) {
            console.error('[PublisherConfig] Table or Input not found in', container);
            return;
        }

        function updateState() {
            const config = {};
            const rows = table.querySelectorAll('tbody tr');

            rows.forEach(row => {
                const paramName = row.getAttribute('data-param-name');
                const existsProps = row.querySelector('.exists-cb');
                const ttzProps = row.querySelector('.ttz-cb');

                if (!existsProps || !ttzProps) return;

                if (existsProps.checked) {
                    config[paramName] = {
                        'exists': true,
                        'ttz_encoded': ttzProps.checked
                    };
                } else {
                    config[paramName] = {
                        'exists': false,
                        'ttz_encoded': false
                    };
                }
            });

            const jsonVal = JSON.stringify(config);
            hiddenInput.value = jsonVal;
            console.log('[PublisherConfig] State Updated:', jsonVal);
        }

        // Use Event Delegation
        table.addEventListener('change', function (e) {
            const target = e.target;

            if (target.classList.contains('exists-cb')) {
                console.log('[PublisherConfig] Exists changed for', target);
                // Handle Enable/Disable
                const row = target.closest('tr');
                const ttzCb = row.querySelector('.ttz-cb');

                if (target.checked) {
                    ttzCb.disabled = false;
                } else {
                    ttzCb.checked = false;
                    ttzCb.disabled = true;
                }
                updateState();
            } else if (target.classList.contains('ttz-cb')) {
                console.log('[PublisherConfig] TTZ changed for', target);
                updateState();
            }
        });
    }

    // Initialize
    const widgets = document.querySelectorAll('.publisher-config-widget');
    console.log('[PublisherConfig] Found widgets:', widgets.length);
    widgets.forEach(initPublisherConfig);
});
