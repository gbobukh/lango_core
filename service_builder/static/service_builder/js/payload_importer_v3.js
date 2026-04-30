(function () {
    'use strict';

    window.PayloadImporter = {
        init: function (fieldId) {
            const textarea = document.getElementById(fieldId);
            if (!textarea) {
                console.error('PayloadImporter: Textarea not found', fieldId);
                return;
            }

            // Create Import Button
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'button';
            btn.style.marginTop = '5px';
            btn.textContent = 'Import from JSON';

            // Insert after textarea
            textarea.parentNode.insertBefore(btn, textarea.nextSibling);

            btn.addEventListener('click', function () {
                const jsonStr = prompt("Paste your JSON example here:");
                if (jsonStr) {
                    try {
                        const data = JSON.parse(jsonStr);
                        const flattened = PayloadImporter.flatten(data);
                        // Filter duplicates
                        const unique = [...new Set(flattened)];
                        textarea.value = JSON.stringify(unique, null, 4);
                    } catch (e) {
                        alert("Invalid JSON: " + e.message);
                    }
                }
            });
        },

        flatten: function (data, prefix = 'body') {
            let keys = [];

            if (data === null || typeof data !== 'object') {
                return keys;
            }

            for (let key in data) {
                if (data.hasOwnProperty(key)) {
                    const value = data[key];
                    const currentPath = prefix ? `${prefix}.${key}` : key;

                    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
                        // Recurse for nested objects
                        keys = keys.concat(PayloadImporter.flatten(value, currentPath));
                    } else if (Array.isArray(value)) {
                        keys.push(currentPath);
                        // Heuristic: If array contains objects, suggest mapping fields of the first object
                        if (value.length > 0 && typeof value[0] === 'object') {
                            keys = keys.concat(PayloadImporter.flatten(value[0], `${currentPath}.0`));
                        }
                    } else {
                        // Primitive value
                        keys.push(currentPath);
                    }
                }
            }
            return keys;
        }
    };
})();
