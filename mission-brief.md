# Mission Brief: FinCore Banking API

## System Under Test (SUT)
**FinCore** is a mock banking backend designed to process transactions and manage user accounts. It is critical infrastructure requiring high reliability, security, and strict compliance with financial regulations.

### Architecture
- **Runtime**: Node.js / Express
- **Database**: In-memory (mocked for this environment)
- **Authentication**: Header-based `X-Fin-Token`
- **Documentation**: 
  - [API Spec](sut-server/docs/api-spec.md)
  - [Compliance Rules](sut-server/docs/compliance-rules.md)

### Key Interfaces
- `GET /health` - System status
- `GET /accounts` - List authenticated user's accounts
- `GET /accounts/:id/transactions` - Transaction history
- `POST /transfer` - Fund transfers (requires Idempotency-Key)
- `GET /admin/debug` - Internal diagnostics

### Known Risks & Focus Areas
1.  **Authorization (IDOR)**: Ensure users cannot access accounts they do not own.
2.  **Transaction Integrity**: Double-spending, negative transfers, and idempotency key enforcement.
3.  **Data Leakage**: Admin endpoints or error messages leaking PII or internal state.
4.  **Input Validation**: Injection attacks (XSS, SQLi-style) in fields like 'description'.

## Automation Objectives
- **Phase 1 (Research)**: Analyze API docs and compliance rules to identify gap between spec and implementation.
- **Phase 2 (Smoke)**: Verify basic happy-path connectivity and auth.
- **Phase 3 (Security/Fuzzing)**: Attack IDOR, broken access control, and XSS vectors.
- **Phase 4 (Infinite)**: Continuously explore edge cases in transaction logic (e.g. concurrent transfers).

## Access
- **Base URL**: `http://localhost:3000`
- **Test Token**: `banker-secret`
