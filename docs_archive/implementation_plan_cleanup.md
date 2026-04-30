# Code Cleanup and Testing

## Goal Description
Remove unused legacy code (`_execute_method`) from `utils.py` and implement comprehensive unit tests for `ScenarioRunner` to ensure stability and prevent regressions.

## User Review Required
> [!NOTE]
> `_execute_method` in `utils.py` is identified as dead code and will be removed.

## Proposed Changes

### Service Builder

#### [MODIFY] [utils.py](file:///root/lango_core/service_builder/utils.py)
- Remove `_execute_method` method from `ScenarioRunner` class.

#### [MODIFY] [tests.py](file:///root/lango_core/service_builder/tests.py)
- Add `ScenarioRunnerTests` class inheriting from `TestCase`.
- Add tests for:
    - Variable substitution (simple, composite, missing variables).
    - JSON parsing of arguments.
    - Base URL prepending logic.
    - Auth header injection (mocked).
    - Response modification logic.
    - Context extraction logic.
    - Success condition logic.

## Verification Plan

### Automated Tests
- Run `python manage.py test service_builder` to execute the new tests.
