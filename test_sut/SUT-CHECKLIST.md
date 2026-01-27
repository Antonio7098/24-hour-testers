# Test SUT Checklist — Sample API

## Tier 1: API Health & Basics

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| API-001 | Verify `/health` endpoint returns 200 OK with status payload | High | Low | ☐ Not Started |
| API-002 | Create a new item via POST `/items` with JSON body | High | Medium | ☐ Not Started |
| API-003 | List items via GET `/items` and confirm created entry | Medium | Low | ✅ Completed |

## Tier 2: Item Processing

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| API-004 | Process an item via POST `/items/<id>/process` | High | High | ✅ Completed |
| API-005 | Verify processed item status becomes `processed` | Medium | Medium | ✅ Completed |

## Tier 3: Error Handling

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| API-006 | Validate 404 response for GET `/items/999` | Low | Low | ✅ Completed |
| API-007 | Exercise reset workflow via POST `/reset` | Low | Medium | ✅ Completed |


