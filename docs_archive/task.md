# Tasks

- [x] **Deep Argument Mapping (JSON Fields)** <!-- id: 100 -->
    - [x] **Plan & Design**
        - [x] Design Proposal <!-- id: 101 -->
        - [x] Create Implementation Plan <!-- id: 103 -->
    - [x] **Backend Implementation**
        - [x] Add `payload_fields` to `ServiceMethod` model <!-- id: 104 -->
        - [x] Update `ServiceMethod.arguments` property to include payload fields <!-- id: 105 -->
        - [x] Update `ScenarioRunner` to construct JSON body from `body.*` arguments <!-- id: 106 -->
    - [x] **Frontend/Admin Implementation**
        - [x] Add UI to edit `payload_fields` in `ServiceMethod` Admin <!-- id: 107 -->
        - [x] Verify `ArgumentMappingWidget` handles dot-notation keys correctly <!-- id: 108 -->
        - [x] Add "Import from JSON" feature to Admin UI
    - [x] **Verification**
        - [x] Create test Scenario with deep mapping <!-- id: 109 -->
        - [x] Verify correct JSON payload construction <!-- id: 110 -->
    - [x] Optional Body Arguments (PATCH Support)
    - [x] Update `ServiceMethod.save` to exclude `payload` if `body.*` exists
    - [x] Update `ScenarioRunner` to handle `body.*` arguments
    - [x] Update `TestEndpointView` to handle `body.*` arguments
    - [x] Test Terminal UX: Allow empty input for optional fields
    - [x] Test Terminal UX: Show Request Payload/Headers <!-- id: 112 -->

- [ ] **Code Cleanup & Testing (On Hold)** <!-- id: 97 -->
    - [ ] Remove `_execute_method` from `utils.py` <!-- id: 98 -->
    - [ ] Add `ScenarioRunnerTests` <!-- id: 99 -->

- [x] **Analyze existing documentation** <!-- id: 0 -->
