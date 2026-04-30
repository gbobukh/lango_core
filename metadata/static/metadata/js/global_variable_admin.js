document.addEventListener('DOMContentLoaded', function () {
    // Select the name input field
    const nameInput = document.getElementById('id_name');

    if (nameInput) {
        // Function to uppercase value
        // Using 'input' event for immediate feedback
        nameInput.addEventListener('input', function (e) {
            // Store cursor position
            const start = this.selectionStart;
            const end = this.selectionEnd;

            // Transform to uppercase
            this.value = this.value.toUpperCase();

            // Restore cursor position (otherwise it jumps to end)
            this.setSelectionRange(start, end);
        });

        // Also ensure on blur just in case
        nameInput.addEventListener('blur', function () {
            this.value = this.value.toUpperCase();
        });
    }
});
