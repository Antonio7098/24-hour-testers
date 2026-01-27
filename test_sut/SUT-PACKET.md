# Test SUT Mission Brief — Sample API

## System Under Test
A lightweight Flask API defined in `test_sut/sample_api.py`. It exposes health, CRUD, and processing endpoints for checklist validation.

## Mission
1. Validate core endpoints (`/health`, `/items`, `/items/<id>`, `/reset`).
2. Ensure item processing sets status to `processed`.
3. Confirm error responses behave as expected (404/500 cases).
4. Capture structured findings with reproducible steps and logs.

## Environment
- Base URL: `http://127.0.0.1:5000`
- Default item payload: `{ "name": "sample" }`
- Processing sleep: ~0.5s; 10% random failure from `/items/<id>/process`.
- Reset endpoint clears in-memory state between tests.

## Constraints
- Use Stageflow processor (Python) via CLI.
- Prioritize observability and fail-fast reporting.
- Retry limit: 2 attempts per checklist item.

## Success Criteria
- All Tier 1–3 checklist items completed (or marked failed with evidence).
- Logs show agent prompts, retries, and outcomes.
- Final reports and tier synthesis executed without crashes.
