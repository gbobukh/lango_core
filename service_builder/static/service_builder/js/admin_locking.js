console.log("Admin Locking Script Loaded (Opacity Strategy)");

document.addEventListener('DOMContentLoaded', function () {
    function applyLockingStyles() {
        const rows = document.querySelectorAll('#changelist table tbody tr');
        console.log(`Checking ${rows.length} rows for locking...`);

        rows.forEach(row => {
            // Find the lock icon span
            const lockSpan = row.querySelector('.lock-status');

            if (lockSpan && lockSpan.dataset.locked === 'true') {
                // Add class for CSS targeting
                row.classList.add('row-locked');

                // FORCE inline styles for opacity as a fail-safe against CSS loading issues
                // Opacity is very strong and usually cascades well to children visually (unlike color)
                row.style.setProperty('opacity', '0.5', 'important');
                row.style.setProperty('filter', 'grayscale(80%)', 'important');
                row.style.setProperty('background-color', '#f9f9f9', 'important');
            }
        });
    }

    // Run initially
    applyLockingStyles();

    // Re-run if HTMX or other dynamic content loaders change the table (if applicable)
    // For standard Django admin, DOMContentLoaded is usually enough, but just in case:
    const observer = new MutationObserver(function (mutations) {
        applyLockingStyles();
    });

    const changeList = document.querySelector('#changelist');
    if (changeList) {
        observer.observe(changeList, { childList: true, subtree: true });
    }
});
