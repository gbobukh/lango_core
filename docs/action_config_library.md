# Action Config Library

## Purpose

`ActionConfigLibrary` is a catalog of reusable Action config templates for Scenario steps.

Key idea:
- It is currently used as a **detached template catalog**.
- Runtime execution still reads `ScenarioStep.action_config` directly.
- No live linkage from `ScenarioStep` to library entry is required.

This keeps runtime behavior stable while improving authoring speed and consistency.

## Model Contract

`ActionConfigLibrary` stores:
- `name`
- `description`
- `action_type`
- `action_config` (JSON)
- `is_active`
- `created_at`, `updated_at`

Uniqueness:
- Unique pair: `(action_type, name)`

Ordering:
- Default ordering is `action_type`, then `name`.

## Current Usage Pattern

1. Open Library and pick a template.
2. Copy/adapt `action_config` into Scenario Step.
3. Save Scenario Step as an independent runtime config.

This is intentional:
- no hidden runtime coupling,
- no cascading behavior changes if a library template is edited later.

## Template Coverage

Library contains templates for all current `ACTION` types:
- `MERGE`
- `FILTER`
- `TRANSFORM`
- `ENRICH`
- `HIERARCHICAL_FLATTEN`
- `MULTI_HIERARCHICAL_FLATTEN`
- `GROUP_BY`
- `FLATTEN_COLLECTION`
- `FIND_OIDH`
- `BUILD_OIDH_BLACKLIST`
- `DICT_TO_LIST`
- `DIFF_OBJECTS`

Also included:
- custom-function-oriented `TRANSFORM` templates (from `SafeEvaluator` custom functions), such as:
  - generate publisher links,
  - partner tracker identifier resolution,
  - partner name resolution,
  - domain extraction,
  - list lookup helper.

## Naming Convention

Current naming style:
- `ACTION_TYPE - Short Title`

Examples:
- `MERGE - Join Two Lists by Rules`
- `TRANSFORM - Resolve Partner Tracker Identifier`
- `GROUP_BY - Aggregate by Keys`

Descriptions follow a consistent action-oriented style:
- `Use this template to ...`

