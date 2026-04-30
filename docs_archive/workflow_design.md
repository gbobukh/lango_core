# Workflow Architecture (Explicit Entity)

## Philosophy
**Separation of Concerns**:
- **Scenario**: A low-level "Function" that executes a linear sequence of API calls or transformations. It is an "Atomic Unit of Work".
- **Workflow**: A high-level "Orchestrator" that manages the flow of data between Scenarios. It defines the business process (e.g., "Generate Links" -> "Create Campaign").

## Data Model

### 1. Workflow
Represents a business process definition.
- **name**: `CharField` (e.g. "Publisher Onboarding")
- **arguments**: `JSONField` (Global inputs, e.g. `{"url": "...", "geo": "..."}`)
- **return_variables**: `JSONField` (List of context variables to return as the final result)
- **created_at**, **updated_at**

### 2. WorkflowStep
A step in the workflow that executes a specific Scenario.
- **workflow**: `ForeignKey(Workflow)`
- **order**: `PositiveIntegerField`
- **scenario**: `ForeignKey(Scenario)` (The unit of work to execute)
- **argument_mapping**: `JSONField` (Maps Workflow Context -> Scenario Arguments)
    - Example: `{"url": "{{ url }}", "geo": "US"}`
- **iterator_variable**: `CharField` (Optional. If set, runs the Scenario for each item in this list)
- **output_variable_name**: `CharField` (Where to store the Result in Workflow Context)
- **is_active**: `BooleanField` (For testing/debugging)

## Execution Engine

### WorkflowRunner
A new runner class dedicated to orchestrating Workflows.

**Logic**:
1.  **Init**: Accepts `workflow_id` and `initial_context`.
2.  **Loop**: Iterates through `WorkflowStep` Objects (ordered).
3.  **Step Execution**:
    - Resolves Arguments from Context (using `SafeEvaluator` or simple template logic).
    - **Looping**: If `iterator_variable` is present:
        - Resolves List.
        - For each item:
            - create `ScenarioRunner(step.scenario, item_args)`.
            - `runner.run()`.
            - Collect outputs.
    - **Single Run**:
        - create `ScenarioRunner(step.scenario, args)`.
        - `runner.run()`.
        - Capture output.
4.  **Context Update**: Stores result in `output_variable_name`.
5.  **Termination**: Returns requested `return_variables`.

## Integration Points

### 1. Scenario Interface
To make Scenarios usable by Workflows, we need to know **what they return**.
- **Update `Scenario` Model**: Add `return_variables` (JSON list).
- **Update `ScenarioRunner`**: At the end of `run()`, return a dictionary containing these variables from its context.

### 2. Admin UI
- **Workflow Admin**: Similar to Scenario Admin, but simpler steps (no "Method", "Action Type", etc. - just "Scenario").
- **Test Terminal**: Needs to support "Run Workflow" mode.

## Implementation Plan

1.  **Model Layout**: define `Workflow` and `WorkflowStep`. Update `Scenario` with `return_variables`.
2.  **Migration**: Create database tables.
3.  **Engine**: Implement `WorkflowRunner`.
4.  **UI**: Create Admin interface for Workflows.
5.  **Verification**: Create a test Workflow linking "Link Generator" and a Mock "Create Campaign" scenario.
