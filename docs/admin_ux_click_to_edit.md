# Admin UX: Click-to-Edit and JSON Readability

## Goal

Provide a consistent admin editing experience:
- existing objects open in read mode,
- each field can be edited independently via pencil icon,
- JSON values are readable in view mode (pretty multiline format).

## Shared Mechanism

Core components:
- `ClickToEditFormMixin`
- `ClickToEditWidget`
- click-to-edit widget template and JS

General behavior:
1. Existing records are wrapped with click-to-edit widgets.
2. Field value is shown in display mode.
3. Clicking pencil reveals only that field input.

## JSON Display Policy

JSON-like values are rendered in pretty format in read mode:
- `dict`/`list` values are serialized with indentation,
- JSON-looking strings are parsed and pretty-printed when valid,
- multiline values render in a `<pre>` style block with scroll.

Result:
- no more one-line unreadable JSON in click-to-edit display mode.

## Lock-Readonly Special Case

`Scenario` lock mode uses Django readonly fields (not form widgets), so normal click-to-edit does not apply there.

For `ScenarioStepInline` in locked scenarios, dedicated pretty readonly renderers are used for JSON fields:
- `action_config`
- `response_modification`
- `error_handlers`
- `context_extraction`

This keeps JSON readable even when the inline is forced to readonly.

## SystemConfig Integration

`SystemConfig` uses a click-to-edit form as well:
- fields open in read mode,
- pencil per field,
- `value` JSON shown in pretty multiline read mode.

## Practical Notes

- Add-view behavior remains normal (click-to-edit targets existing records).
- The same policy is applied globally where forms use `ClickToEditFormMixin`.
- If a model uses hard readonly via `readonly_fields`, pretty rendering may require explicit readonly helper methods.

