document.addEventListener("DOMContentLoaded", function () {
    console.log("Access Control script loaded.");
    // Find the Access Control fieldset by its custom class
    const accessControl = document.querySelector('.access-control-fieldset');

    if (accessControl) {
        console.log("Access Control fieldset found. Moving...");
        // Find the container where we want to move it.
        // In Django Admin, the main form content is usually in a div with id "content-main" -> form
        // We want to move it to the very end of the form, after all fieldsets and inlines.

        // The form usually contains a div with class 'aligned' or just direct fieldsets/inline-groups.
        // We can append it to the form element itself, but before the submit row if possible, or just at the end of the fieldset container.

        // A safer bet in standard Django admin is to append it to the main fieldset container or after the last inline-group.
        // Let's try appending it to the parent of the fieldset, which effectively moves it to the end of that container.

        accessControl.parentNode.appendChild(accessControl);

        // If there are inline groups (which are usually siblings to fieldsets), this will move it after them 
        // IF they are in the same container. In standard Django, inlines are often separate.

        // Let's be more aggressive: find the submit row and insert before it? 
        // Or just append to the form's main container div (usually <div> containing fieldsets and inlines).

        // Let's try to find the last inline group and insert after it.
        const inlineGroups = document.querySelectorAll('.inline-group');
        if (inlineGroups.length > 0) {
            const lastInline = inlineGroups[inlineGroups.length - 1];
            console.log("Found inline groups. Moving after the last one.");
            lastInline.parentNode.insertBefore(accessControl, lastInline.nextSibling);
        } else {
            // If no inlines, just moving to end of parent is fine (it was already there or close to it).
            console.log("No inline groups found. Appending to parent.");
            accessControl.parentNode.appendChild(accessControl);
        }
    } else {
        // Fieldset not found (e.g. non-superuser or different page). Silent exit.
    }
});
