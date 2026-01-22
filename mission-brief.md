# Mission Brief: {SUT_NAME}

## System Under Test (SUT)
**{SUT_NAME}** is a {DESCRIPTION_OF_SYSTEM}. It is critical infrastructure requiring {REQUIREMENTS}.

### Architecture
- **Runtime**: {RUNTIME_STACK}
- **Database**: {DATABASE_INFO}
- **Authentication**: {AUTH_MECHANISM}
- **Documentation**: 
  - [API Spec]({PATH_TO_API_SPEC})
  - [Compliance Rules]({PATH_TO_COMPLIANCE_RULES})

### Key Interfaces
- `GET /health` - System status
- `{METHOD} {ENDPOINT}` - {DESCRIPTION}

### Known Risks & Focus Areas
1.  **{RISK_AREA_1}**: {DESCRIPTION}
2.  **{RISK_AREA_2}**: {DESCRIPTION}
3.  **{RISK_AREA_3}**: {DESCRIPTION}

## Automation Objectives
- **Phase 1 (Research)**: Analyze API docs and compliance rules to identify gap between spec and implementation.
- **Phase 2 (Smoke)**: Verify basic happy-path connectivity and auth.
- **Phase 3 (Security/Fuzzing)**: Attack IDOR, broken access control, and XSS vectors.
- **Phase 4 (Infinite)**: Continuously explore edge cases in transaction logic (e.g. concurrent transfers).

## Access
- **Base URL**: `{BASE_URL}`
- **Test Token**: `{TEST_TOKEN}`
