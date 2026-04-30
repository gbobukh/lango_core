# Proposal: Deep Argument Mapping (JSON Field Mapping)

## Problem
When chaining steps (e.g., `Get Campaign` -> `Create Campaign`), the output of the first step often contains the right data but in a different structure than what the second step expects.
- **Source**: `{"data": {"attributes": {"name": "My Campaign", "budget": 100}}}`
- **Target**: `{"name": "My Campaign", "daily_budget": 100}`

Currently, we can only map the entire `payload` to a single variable, which requires the variable to already be in the exact target format (or requires complex Python expressions to transform it).

## Proposed Solution: "Deep Argument Mapping"

Instead of treating the Body Payload as a single "black box" argument, we allow defining **specific fields** within the payload as individual arguments. This leverages the existing, user-friendly "Argument Mapping" UI.

### 1. Define Payload Fields in ServiceMethod
We extend `ServiceMethod` to allow defining a "Payload Schema" or simply a list of "Body Arguments".

**Example Definition:**
- `body.name` (Target field: `name`)
- `body.daily_budget` (Target field: `daily_budget`)
- `body.settings.geo` (Target field: `settings.geo`)

### 2. Unified Mapping UI
These fields appear in the Scenario Step's "Argument Mapping" list, mixed with (or grouped alongside) URL parameters.

| Method Argument | Map to Context Variable |
| :--- | :--- |
| `id` (URL) | `{{ source_campaign_id }}` |
| `body.name` | `{{ source_campaign.data.attributes.name }}` |
| `body.daily_budget` | `{{ source_campaign.data.attributes.budget }}` |

### 3. Automatic Construction
The `ScenarioRunner` collects all arguments starting with `body.` (or a configured prefix) and constructs the nested JSON object automatically.

- Input:
    - `body.name` = "My Campaign"
    - `body.daily_budget` = 100
- Generated Payload:
    ```json
    {
      "name": "My Campaign",
      "daily_budget": 100
    }
    ```

## Advantages
1.  **Consistent UI**: Uses the same "dropdown/template" interface users already know.
2.  **Granular Control**: Users can map specific fields from different sources (e.g., `name` from Campaign A, `budget` from a Global Constant).
3.  **No Code**: No need to write complex JSON transformation scripts or Python dictionaries in the "Context Extraction" step.

## Handling Arrays (Future)
Mapping lists (e.g., "Create 5 Ads from these 5 Source Ads") is more complex.
- **Initial approach**: Support "List of Values" if the target field expects an array (e.g., `body.tags` -> `{{ source_tags_list }}`).
- **Advanced**: "For Each" loop support in Scenarios (separate feature).

## Implementation Steps
1.  **Model**: Add `payload_fields` (JSON/List) to `ServiceMethod`.
2.  **Admin**: UI to add/edit payload fields (simple "Add Field" list).
3.  **API**: Update `GetMethodArgumentsView` to include these fields.
4.  **Runner**: Update `ScenarioRunner` to construct the JSON body from these arguments.
