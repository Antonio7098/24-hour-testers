# FinCore API Specification v1.0.0

## Authentication
All requests must include the header `X-Fin-Token`.
The accepted value for development is `banker-secret`.

## Endpoints

### GET /health
Returns 200 OK if system is operational.

### GET /accounts
Returns list of accounts owned by the authenticated user.
*Note: Currently mocks a single user context for simplicity.*

### GET /accounts/:id/transactions
Returns transaction history for a specific account.
**Parameters:**
- `id`: Account ID (integer)

### POST /transfer
Initiates a fund transfer between accounts.
**Headers:**
- `Idempotency-Key`: (Required) Unique string for request deduplication.
**Body:**
- `from_account`: (int) Source Account ID
- `to_account`: (int) Destination Account ID
- `amount`: (float) Amount to transfer

### GET /admin/debug
Internal debug endpoint. **Should be disabled in production.**
