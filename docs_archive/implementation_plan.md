# Deep Argument Mapping (JSON Field Mapping)

## Goal Description
Allow users to map specific fields of a JSON payload in Scenario Steps, enabling the construction of complex nested JSON objects from various context variables without writing code.

## User Review Required
> [!NOTE]
> This feature expands the `ServiceMethod` model to include `payload_fields`.

## Proposed Changes

### Service Builder

#### [MODIFY] [models.py](file:///root/lango_core/service_builder/models.py)
- Update `ServiceMethod` model:
    - Add `payload_fields` (JSONField, default list).
    - Update `save()` method or `arguments` property to merge `payload_fields` into the returned arguments list.

#### [MODIFY] [admin.py](file:///root/lango_core/service_builder/admin.py)
- Update `ServiceMethodAdmin`:
    - Add a field/widget to edit `payload_fields`.
    - *Initial implementation*: A simple JSONField widget (or List widget if available) where users can enter dot-notation strings (e.g., `body.name`, `body.data.id`).

#### [MODIFY] [utils.py](file:///root/lango_core/service_builder/utils.py)
- Update `ScenarioRunner.run`:
    - In the argument resolution loop, identify arguments starting with `body.` (or the configured prefix).
    - Construct a `payload_data` dictionary using `_set_json_value` logic.
    - If `payload_data` is not empty, send it as `json=payload_data`.
    - *Conflict Handling*: If both `payload` (legacy) and `body.*` arguments are present, `body.*` takes precedence or merges?
        - *Decision*: `body.*` constructs the payload. If `payload` is also mapped, it might overwrite or be ignored. Let's assume they are mutually exclusive in usage, but if both exist, `body.*` merges INTO `payload`?
        - *Simpler*: If `body.*` args exist, they form the payload.

#### [MODIFY] [views.py](file:///root/lango_core/service_builder/views.py)
- Update `GetMethodArgumentsView` (if necessary):
    - Ensure it returns the merged list of arguments (URL + Payload).
    - *Note*: If `ServiceMethod.arguments` is updated to include them, this might be automatic.

## Verification Plan

### Manual Verification
1.  **Configure Method**:
    - Create a method `Create Campaign`.
    - Add payload fields: `body.name`, `body.budget`.
2.  **Configure Scenario**:
    - Create a step using this method.
    - Verify "Argument Mapping" shows `body.name` and `body.budget`.
    - Map `body.name` -> `{{ source_name }}`.
    - Map `body.budget` -> `100`.
3.  **Run Test**:
    - Execute the scenario.
    - Verify the log shows a POST request with body `{"name": "...", "budget": 100}`.
