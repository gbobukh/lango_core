document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener('click', function (e) {
        // Check if clicked element is a pencil icon or inside one
        const trigger = e.target.closest('.click-to-edit-trigger');
        if (trigger) {
            const container = trigger.closest('.click-to-edit-container');
            if (container) {
                const displayEl = container.querySelector('.click-to-edit-display');
                const inputEl = container.querySelector('.click-to-edit-input');

                if (displayEl && inputEl) {
                    displayEl.style.display = 'none';
                    trigger.style.display = 'none';

                    // Show input
                    inputEl.style.visibility = 'visible';
                    inputEl.style.position = 'static';
                    inputEl.style.opacity = '1';
                    inputEl.style.zIndex = 'auto';
                    inputEl.style.display = 'block'; // Ensure it's block just in case

                    // Focus the first input/select inside
                    const field = inputEl.querySelector('input, select, textarea');
                    if (field) {
                        field.focus();
                    }
                }
            }
        }
    });
});
