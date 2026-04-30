(function () {
    // Create modal structure on load
    document.addEventListener('DOMContentLoaded', function () {
        if (document.getElementById('context-help-modal')) return;

        const modal = document.createElement('div');
        modal.id = 'context-help-modal';
        modal.style.cssText = `
            display: none;
            position: fixed;
            z-index: 10000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0,0,0,0.4);
        `;

        const content = document.createElement('div');
        content.style.cssText = `
            background-color: #fefefe;
            margin: 10% auto;
            padding: 20px;
            border: 1px solid #888;
            width: 80%;
            max-width: 600px;
            border-radius: 5px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            position: relative;
        `;

        const closeBtn = document.createElement('span');
        closeBtn.innerHTML = '&times;';
        closeBtn.style.cssText = `
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        `;
        closeBtn.onclick = function () {
            modal.style.display = 'none';
        };

        const body = document.createElement('div');
        body.id = 'context-help-body';

        content.appendChild(closeBtn);
        content.appendChild(body);
        modal.appendChild(content);
        document.body.appendChild(modal);

        // Close on click outside
        window.onclick = function (event) {
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        };
    });

    window.openContextHelp = function () {
        const modal = document.getElementById('context-help-modal');
        const body = document.getElementById('context-help-body');

        // Fetch content if empty
        if (!body.innerHTML) {
            // We can't easily fetch the template URL from here without Django context.
            // So we'll hardcode the content for now, or fetch it if we had an API.
            // Actually, let's just embed the content here since it's static and small.
            body.innerHTML = `
                <h2 style="margin-top: 0; color: #333;">Context Extraction Syntax</h2>
                <p>Use Python-like expressions to extract data or validate results.</p>
                
                <h3 style="color: #447e9b;">Helper Functions</h3>
                <ul style="line-height: 1.6;">
                    <li><code>find(list, key, value)</code><br>
                        Finds the first item in a list where <code>item[key] == value</code>.<br>
                        <em>Example:</em> <code>find(domains, 'name', 'example.com')['id']</code>
                    </li>
                    <li><code>sum(list)</code>, <code>min(list)</code>, <code>max(list)</code>: Aggregation.</li>
                    <li><code>len(obj)</code>: Length of list/string.</li>
                    <li><code>int(x)</code>, <code>float(x)</code>, <code>str(x)</code>, <code>bool(x)</code>: Type casting.</li>
                </ul>

                <h3 style="color: #447e9b;">Advanced Features</h3>
                <ul style="line-height: 1.6;">
                    <li><strong>List Comprehensions:</strong> Filter and transform lists.<br>
                        <em>Ex:</em> <code>[x['id'] for x in items if x['active']]</code>
                    </li>
                    <li><strong>Data Structures:</strong> Create lists <code>[]</code> and dicts <code>{}</code>.<br>
                        <em>Ex:</em> <code>{'ids': [1, 2], 'total': sum(values)}</code>
                    </li>
                </ul>

                <h3 style="color: #447e9b;">Variables</h3>
                <ul style="line-height: 1.6;">
                    <li><code>result</code>: The JSON response from the current step.</li>
                    <li><code>context</code>: The global context dictionary.</li>
                </ul>
                
                <h3 style="color: #447e9b;">Operators</h3>
                <p><code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>, <code>==</code>, <code>!=</code>, <code>and</code>, <code>or</code>, <code>in</code></p>
            `;
        }

        modal.style.display = 'block';
    };
})();
