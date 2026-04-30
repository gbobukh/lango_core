# Service Builder & Integrations Walkthrough

## Overview
This walkthrough covers the implementation of the **Service Builder** application and its integration with the **Integrations** core to enable automated account name fetching.

## Related Docs
- Runtime and deployment runbook: `docs/runtime_environment.md`
- Project architecture map (modules, links, runtime flows): `docs/project_map.md`
- Action config template catalog: `docs/action_config_library.md`
- Admin click-to-edit and JSON readability UX: `docs/admin_ux_click_to_edit.md`
- Redis-backed API rate limiting: `docs/api_rate_limits.md`

## Features Implemented

### 1. Service Builder
A new app designed to define and test external API endpoints.

#### Endpoints & Methods
- **ServiceEndpoint**: Defines the base API endpoint (URL, Method, Tracker).
- **ServiceMethod**: Defines specific actions on an endpoint (e.g., "Get Account Name").
    - **Auto-Discovery**: Automatically finds variables like `{id}` in the URL.
    - **Return Key**: Specifies which field from the JSON response to extract (supports dot notation like `data.name`).

#### Interactive Tests UI
- **Run Test**: A terminal-like interface to test endpoints and methods.
- **Variable Prompting**: Automatically asks for values for URL variables.
- **Return Value Extraction**: Displays the specific value extracted using the `Return Key`.

### 2. Integrations Core Enhancements

#### Partner Account Auto-Fetch
- **Goal**: Automatically populate the "Account Name" in a Tracker Identifier by querying the API.
- **Workflow**:
    1.  In **Partner Account**, add a **Tracker Identifier**.
    2.  Select an **Identifying Method** (from Service Builder).
    3.  Enter the **Account ID**.
    4.  Click **Save**.
    5.  The system executes the method, extracts the name, and saves it to **Account Name**.

## Usage Guide

### Creating a Service Method
1.  Go to **Service Builder > Service Endpoints**.
2.  Create an Endpoint (e.g., `https://api.example.com/users/{id}`).
3.  Go to **Service Builder > Service Methods**.
4.  Create a Method linked to that Endpoint.
5.  Set **Return Key** (e.g., `user.full_name`).

### Testing
1.  Click **Run Test** on the Method list or change page.
2.  Enter the required variables (e.g., `id`).
3.  View the result in the terminal.

### Linking to Partner Account
1.  Go to **Integrations > Partner Account IDs**.
2.  Edit a Partner Account.
3.  In **Tracker Identifiers**, select the **Identifying Method**.
4.  Enter the **Account ID**.
5.  Save.

### 3. Scenarios
A mechanism to chain multiple methods, passing data between them via a shared context.

#### Features
- **Scenario**: Defines a sequence of steps.
    - **Arguments**: Dynamic list of input variables required by the scenario (e.g., `source_campaign_id`, `geo`).
- **Scenario Steps**:
    - **Method**: The Service Method to execute.
    - **Argument Mapping**: Maps method arguments to context variables (e.g., `id` -> `source_campaign_id`).
    - **Output Variable**: Name of the variable to store the result in (e.g., `new_campaign_id`).
- **Validation**:
    - **Non-Blocking**: Scenarios can be saved even with errors (marked as **Invalid**).
    - **Checks**:
        - At least one step exists.
        - All required method arguments are mapped.
        - Mapped variables exist in the context.
    - **Status**: Displayed in the list view and edit form (Valid/Invalid).

#### Argument Mapping UI
- Implemented a custom `ArgumentMappingWidget` for `ScenarioStep`.
- Created a dynamic JavaScript interface (`argument_mapping_v3.js`) that:
    - Fetches arguments for the selected `ServiceMethod` via a new API endpoint (`/admin/service_builder/scenario/api/method-arguments/<id>/`).
    - Displays a table with dropdowns to map method arguments to available context variables.
    - Context variables include Scenario arguments and outputs from previous steps.
    - Handles `django.jQuery` initialization robustly to avoid conflicts.
- **Fixes applied during implementation:**
    - Fixed static file serving in `urls.py` for DEBUG mode.
    - Resolved `TypeError: $ is not a function` by adding robust jQuery detection and waiting for `DOMContentLoaded`.
    - Fixed API URL 404 by correcting the path in JS to match `ScenarioAdmin`'s URL structure.
    - Renamed JS file to `v3` to resolve persistent browser caching issues.

#### Composite Argument Mapping
- Enhanced the UI to support **Composite Mapping** (combining text and variables).
- Replaced simple dropdowns with **Text Inputs** + **Insert Variable** helper.
- Implemented **Template Syntax** `{{ variable }}` for variable substitution.
- Updated validation logic in `models.py` to parse templates and verify only the variables inside `{{ }}`.
- **Features:**
    - Allows constructing complex strings: `prefix_{{ id }}_suffix`.
    - Allows JSON construction: `{"ids": [{{ id1 }}, {{ id2 }}]}`.
    - Preserves insertion order of variables in the helper dropdown.
    - Updates live when Context Variables are added/removed.
- **Validation Fixes**:
    - Resolved an issue where validation status (`is_valid`) was not persisting correctly due to a race condition during save.
    - Implemented `refresh_from_db()` in `save_formset` to ensure atomic updates.
    - Silenced harmless console warnings from `move_access_control.js`.
    - **Dot Notation Support**: Added support for accessing nested properties in context variables (e.g., `{{ campaign_template.name }}`).
    - **Literal Value Support**: Added support for entering literal values directly (e.g., `6`, `true`, `some_string`). These are automatically parsed as JSON primitives (numbers, booleans) if possible.
    - **Validation Fix**: Updated scenario validation to correctly recognize dot notation variables (e.g., `{{ campaign_template.name }}`) as valid if the root variable (`campaign_template`) exists in the context.
    - **None Value Fix**: Resolved an issue where `None` (null) values in the context were treated as missing variables. They are now correctly passed as `null` to the API.
    - **Safe Navigation**: Implemented safe navigation for nested variables. If a parent object is `None` (e.g., `campaign_template.hideReferrer`), accessing a child property (e.g., `domainUuid`) will now return `None` instead of failing.
    - **### Optional Body Arguments (PATCH Support)
We implemented support for optional body arguments, particularly useful for PATCH requests where you only want to update specific fields.
- **Deep Mapping**: You can now map individual fields like `body.name`, `body.status` instead of a single `payload` JSON.
- **Test Terminal UX**:
    - The terminal now prompts for each field individually.
    - You can skip optional fields by pressing Enter (leaving them empty).
    - A "Submit" button (↵) was added to ensure you can submit empty values easily.
    - **Request Logging**: The terminal now displays the exact **Request Payload** and **Request Headers** sent to the server, providing full visibility into the test execution.
- **Backend Logic**:
    - `ServiceMethod` automatically hides the generic `payload` argument if `body.*` fields are defined.
    - `TestEndpointView` constructs the JSON payload from individual `body.*` arguments and handles type conversion (e.g., "123" -> 123)., streamlining the testing process for complex methods.

### Scenario Validation Fixes
- **Issue**: `Scenario.is_valid` was not persisting correctly due to a race condition in `save_formset`.
- **Fix**: Updated `ScenarioAdmin.save_formset` to explicitly check the database state before validation and only update if changed.
- **Console Warning**: Silenced "Access Control fieldset NOT found" warning in `move_access_control.js`.

### Scenario Testing UI
- **Feature**: Added "Run Test" button to `ScenarioAdmin` list view.
- **UI**: Updated `TestEndpointView` and `test_endpoint.html` to support Scenario execution.
    - Displays Scenario Name.
    - Prompts for Context Variables (Scenario Arguments).
    - Executes Scenario via `ScenarioRunner`.
    - Displays detailed execution logs (Step-by-step, URL, Status, Response Body).
- **Fixes**:
    - **Base URL**: `ScenarioRunner` now correctly prepends the Base URL from the selected Auth ID for relative endpoints.
    - **JSON Parsing**: Fixed JSON serialization of arguments passed to the frontend to prevent JS errors.
    - **Variable Scope**: Fixed `UnboundLocalError` in `ScenarioRunner`.
    - **Logging**: Enhanced logging to include HTTP Status and Response Body for easier debugging.

### Scenario Conditional Logic
- **Feature**: Added `success_condition` and `condition_error_message` fields to `ScenarioStep`.
- **Safe Evaluation**: Implemented `SafeEvaluator` (AST-based) to securely execute Python-like expressions.
    - Supported: Math, Logic, Comparisons, List/Dict access, `len()`, `int()`, `str()`.
    - Blocked: Imports, System calls, Private attributes.
- **Logic**: Steps now validate the condition after execution. If false, the scenario stops with the custom error message (or a default one).
- **UI Feedback**: Added a "Toast" notification system to display success/error messages prominently in the Test Terminal.

### Context Extraction
- **Feature**: Added `context_extraction` field to `ScenarioStep`.
- **Purpose**: Extract specific data from the method result into context variables using Python-like expressions.
- **Format**: JSON `{"var_name": "expression"}`.
- **Example**: `{"first_id": "result[0]['id']"}`.
- **Renaming**: Renamed `Response modification` to `Response Injection` to clarify its purpose (injecting context INTO result).

#### Usage
1.  Go to **Service Builder > Scenarios**.
2.  Create a Scenario, define arguments (e.g., `source_id`).
3.  Add Steps. Use `{{ source_id }}` to map arguments.
4.  (Optional) Add a **Success Condition**: `result.get('status') == 'active'`.
5.  (Optional) Add a **Condition Error Message**: "Campaign is not active!".
6.  Click **Run Test** to verify.
    - Set Output Variable (optional).
    - **Response Modification**: Optionally modify the JSON response (e.g., `{"data.id": "new_id"}`).
4.  Save. Validation runs automatically, updating the **Is Valid** status.

## Technical Details
- **Models**: `ServiceEndpoint`, `ServiceMethod`, `PartnerAccountTrackerIdentifier`, `Scenario`, `ScenarioStep`.
- **Views**: `TestEndpointView` (Custom Admin View).
- **Security**: All views and models are protected by Access Control (User visibility).

### Emergency Diagnostics & Resolution
- **Issue:** User reported "Site not working", "Infinite loading", "Dropped connection", "PrivacyWall hijack".
- **Root Cause Analysis:**
    1.  **404 on Root:** Missing URL handler for `/`. Fixed by adding redirect to `/admin/`.
    2.  **Infinite Loading:** Browser cache holding references to old JS files. Fixed by clearing cache/Incognito.
    3.  **Dropped Connection:** Port conflict (Gunicorn running on 8000 & 8001). Fixed by killing all processes and restarting on 8001.
    4.  **PrivacyWall / QUIC Error / Access Denied:** **ISP Block (Vodafone)**. Confirmed by user screenshot ("Por causas ajenas a Vodafone...") and success via VPN.
- **Final Status:** Server is healthy, SSL is Strict, Application is running. Access requires VPN/DNS change for Vodafone users.

### Debugging & Fixes (Session 2)

### 1. Invalid URL Scheme
- **Issue:** Relative URLs (e.g., `/public/api/...`) caused "No scheme supplied" errors because the base URL was missing.
- **Fix:** Updated `ScenarioRunner` to fetch the `base_url` from the selected `ApiAuthID` and prepend it to the endpoint URL if it doesn't start with `http`.

### 2. Missing Authentication (401 Unauthorized)
- **Issue:** `ScenarioRunner` was not injecting authentication headers, leading to 401 errors.
- **Fix:** Implemented logic in `ScenarioRunner` to:
    - Retrieve `ApiAuthID` from context.
    - Decrypt stored credentials.
    - Inject headers based on `ApiAuthType` (e.g., `Api-Key: <value>` for Binom).

### 3. Payload Type Error (500 Internal Server Error)
- **Issue:** The API expected a JSON object for `payload`, but received a string. This happened because the variable substitution logic converted everything to strings (e.g., `"{'key': 'val'}"`).
- **Fix:** Implemented "Exact Match" logic in `utils.py`. If a field contains *only* a variable (e.g., `{{ campaign_template }}`), the original object type (dict/list) is preserved from the context, bypassing string conversion.
- **Refinement:** Updated regex to `[^}]+` to ensure composite strings (e.g., `{{ geo }} {{ id }}`) are treated as text interpolation, while single variables are treated as objects.

### 4. Frontend Caching
- **Issue:** Browser/Cloudflare caching caused old logs to be displayed.
- **Fix:** Added a timestamp (`?t=...`) to the AJAX request URL in `test_terminal.js` and bumped the script version to `v13`.

### Payload Variable Feature
- **Goal:** Allow users to send dynamic JSON bodies in POST/PUT requests within scenarios.
- **Implementation:**
    - **ServiceEndpoint:** Added `get_arguments()` method that automatically detects URL variables and appends a `payload` argument if the method is POST/PUT/PATCH.
    - **ServiceMethod:** Inherits arguments from its parent Endpoint.
    - **UI:** "Run Test" terminal now prompts for `{payload}` value (JSON string) when testing POST endpoints.
    - **Execution:** `ScenarioRunner` extracts the `payload` variable and sends it as the request body (`json=payload`).

## UI Fixes
- **Argument Mapping Widget**: Fixed an issue where the argument mapping UI would disappear or fail to load when using the "Click-to-Edit" widget.
    - Implemented a robust selector strategy in `argument_mapping_v12.js` that finds the method dropdown by its ID (derived from the widget's name) rather than relying on DOM traversal.
### Deep Argument Mapping (JSON Field Mapping)
- **Goal**: Allow users to map specific fields of a JSON payload (e.g., `body.name`, `body.budget`) instead of constructing the entire JSON payload manually.
- **Implementation:**
    - **ServiceMethod**: Added `payload_fields` (JSON list) to define expected body fields.
    - **Argument Discovery**: `ServiceMethod.save()` now combines URL arguments and `payload_fields` into the `arguments` list.
    - **ScenarioRunner**: Updated to detect arguments starting with `body.` and construct a nested JSON object for the request body.
    - **Precedence**: If `body.*` arguments are present, they are used to construct the payload. If `payload` (legacy) is also present, it is ignored (or used as a base if needed, but current logic favors `body.*`).
- **Verification**:
    - Created `tests_deep_mapping.py` to verify that `ScenarioRunner` correctly assembles nested JSON from flat arguments (e.g., `body.settings.geo` -> `{"settings": {"geo": "..."}}`).
    - Verified that implicit payload construction works even if the legacy `payload` argument is missing.

### 3. JSON Import Feature
To simplify the creation of `payload_fields`, an "Import from JSON" button has been added to the `ServiceMethod` admin interface.

1.  Click "Import from JSON" next to the `Payload fields` input.
2.  Paste a valid JSON example of the request body.
3.  The tool automatically flattens the JSON into the required dot-notation format (e.g., `["body.name", "body.settings.geo"]`).
4.  You can then manually edit the list to remove optional fields or adjust mappings.

This feature ensures that complex nested structures can be mapped quickly and accurately without manual error.

# Workflow Orchestration

## Overview
Workflows are high-level orchestrators that coordinate the execution of multiple Scenarios.
While a **Scenario** represents a linear "Unit of Work" (API calls, data transformation), a **Workflow** represents a "Business Process" that connects these units.

## Core Entities

### 1. Workflow
- **Purpose**: Defines the inputs (`arguments`) and outputs (`return_variables`) of the overall process.
- **Model**: `service_builder.models.Workflow`

### 2. WorkflowStep
- **Purpose**: Executes a specific Scenario within the Workflow.
- **Mapping**: Maps Workflow Context variables to Scenario Arguments using `{{ var }}` syntax.
- **Iteration**: Supports looping over a list (`iterator_variable`), executing the Scenario for each item.

### 3. Scenario Interface
- **Output Contract**: Scenarios now define `return_variables`. Only these variables are extracted from the Scenario Context and returned to the Workflow.

## Execution Flow (`WorkflowRunner`)
1.  **Initialize**: Workflow starts with global arguments.
2.  **Execute Step**:
    - Resolves arguments based on mapping.
    - If `iterator_variable` is set:
        - Loops through the list.
        - Executes Scenario for each item.
        - Collects outputs into a List.
    - Else:
        - Executes Scenario once.
        - Collects output.
3.  **Store Result**: Stores the output in the Workflow Context (e.g., `step_result`).
4.  **Next Step**: Subsequent steps can access `step_result` via mapping.
5.  **Finalize**: Extracts `return_variables` from Workflow Context as the final result.

## Usage
Workflows are managed via the Django Admin.
- **Create Scenarios** first (the building blocks).
- **Create Workflow**: Define inputs.
- **Add Steps**: Link inputs to Scenarios. Use dot notation for nested data access (e.g., `gen_output.calculated.list`).

## Dynamic Routing
WorkflowStep can dynamically choose which Scenario to run based on context.

1.  **Configure Step**: Leave `Scenario` empty (or set as default).
2.  **Set Router Variable**: Ente the variable name to check (e.g., `tracker_type`).
3.  **Define Map**: enter a JSON dictionary mapping values to Scenario IDs.
    - Example: `{"TrafficGold": 12, "Voluum": 15}`
4.  **Execution**:
    - If `tracker_type` == "TrafficGold", Scenario #12 runs.
    - If no match found, the Default Scenario runs.
    - If no Default and no match, the workflow fails.

### Example: "Universal Create & Run"

**Goal**: Create a campaign on *either* TrafficGold *or* Voluum, then generate links.

**Setup**:
1.  **Workflow Inputs**: `['tracker_type', 'campaign_name']`
2.  **Scenarios**:
    - Scenario A (ID=10): "Create on TrafficGold" (Input: `name` -> Output: `camp_id`)
    - Scenario B (ID=20): "Create on Voluum" (Input: `name` -> Output: `camp_id`)
    - Scenario C (ID=30): "Generate Links" (Input: `id`)

**Step 1 (Routing)**:
- **Router Variable**: `tracker_type`
- **Routing Map**: `{"TrafficGold": 10, "Voluum": 20}`
- **Argument Mapping**: `{"name": "{{ campaign_name }}"}`
- **Output Var**: `creation_result`

**Step 2 (Common)**:
- **Scenario**: C (Generate Links)
- **Argument Mapping**: `{"id": "{{ creation_result.camp_id.camp_id }}"}`
- *Note*: Use dot notation (`a.b`) to access nested dictionary values.

**Result**:
- If `tracker_type="TrafficGold"`, Scenario 10 runs. Context gets TG ID. Step 2 uses TG ID.
- If `tracker_type="Voluum"`, Scenario 20 runs. Context gets Voluum ID. Step 2 uses Voluum ID.
