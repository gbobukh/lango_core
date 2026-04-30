console.log("Admin Locking Script v2 (High Contrast) Loaded");

document.addEventListener('DOMContentLoaded', function () {
    function applyLockingStyles() {
        const rows = document.querySelectorAll('#changelist table tbody tr');

        rows.forEach(row => {
            const lockSpan = row.querySelector('.lock-status');

            if (lockSpan && lockSpan.dataset.locked === 'true') {
                row.classList.add('row-locked');

                // Direct JS Injection for maximum priority - Darker Grey
                const bgColor = '#e0e0e0';
                const textColor = '#666666';

                row.style.setProperty('background-color', bgColor, 'important');

                // Gray out all cells
                const cells = row.querySelectorAll('td, th');
                cells.forEach(cell => {
                    cell.style.setProperty('background-color', bgColor, 'important');
                    cell.style.setProperty('color', textColor, 'important');
                    cell.style.setProperty('opacity', '0.7', 'important');
                });

                // Gray out links (but allow clicking)
                const links = row.querySelectorAll('a');
                links.forEach(link => {
                    link.style.setProperty('color', textColor, 'important');
                });
            }
        });
    }

    applyLockingStyles();

    // Observer for HTMX/dynamic updates
    const changeList = document.querySelector('#changelist');
    if (changeList) {
        new MutationObserver(applyLockingStyles).observe(changeList, { childList: true, subtree: true });
    }
});
