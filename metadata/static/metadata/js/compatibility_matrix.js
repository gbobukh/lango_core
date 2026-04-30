document.addEventListener('DOMContentLoaded', function () {
    const subjectParamSelect = document.querySelector('#id_subject_parameter');
    const targetParamSelect = document.querySelector('#id_target_parameter');
    const subjectValueSelect = document.querySelector('#id_subject_value');
    const allowedValuesSelect = document.querySelector('#id_allowed_values');

    // Data injected from Django Admin view
    // format: { "param_id": ["val1", "val2"] }
    const paramsData = window.TARGET_PARAMS_DATA || {};

    function updateOptions(selectElement, paramId, currentValues = []) {
        console.log('Updating options for', selectElement, 'with paramId:', paramId);
        // Clear existing options
        selectElement.innerHTML = '';

        if (!paramId || !paramsData[paramId]) {
            console.warn('No data found for paramId:', paramId);
            // Add placeholder if empty
            const placeholder = document.createElement('option');
            placeholder.textContent = '--- Select a parameter first ---';
            selectElement.appendChild(placeholder);
            return;
        }

        const values = paramsData[paramId];
        values.forEach(val => {
            const option = document.createElement('option');
            option.value = val;
            option.textContent = val;
            if (currentValues.includes(val) || currentValues.includes(String(val))) {
                option.selected = true;
            }
            selectElement.appendChild(option);
        });
    }

    if (subjectParamSelect) {
        subjectParamSelect.addEventListener('change', function () {
            updateOptions(subjectValueSelect, this.value);
        });
    }

    if (targetParamSelect) {
        targetParamSelect.addEventListener('change', function () {
            updateOptions(allowedValuesSelect, this.value);
        });
    }

    // Initial load handling
    // We only need to trigger update if the field is empty or changed.

    // --- Locking Logic ---
    const isLockedCheckbox = document.querySelector('#id_is_locked');
    const fieldsToLock = [
        document.querySelector('#id_subject_parameter'),
        document.querySelector('#id_subject_value'),
        document.querySelector('#id_target_parameter'),
        document.querySelector('#id_allowed_values')
    ];

    function toggleLock(locked) {
        fieldsToLock.forEach(field => {
            if (field) {
                if (locked) {
                    field.setAttribute('disabled', 'disabled');
                } else {
                    field.removeAttribute('disabled');
                }
            }
        });
    }

    if (isLockedCheckbox) {
        isLockedCheckbox.addEventListener('change', function () {
            toggleLock(this.checked);
        });

        // Initial sync (though server likely set it correctly)
        toggleLock(isLockedCheckbox.checked);
    }
});
