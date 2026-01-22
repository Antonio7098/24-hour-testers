# FinCore Compliance & Security Standards

## 1. Data Protection
- **PCI-DSS**: No full credit card numbers shall be stored or returned in API responses.
- **PII**: User addresses and phone numbers must be masked in non-admin responses.

## 2. Transaction Integrity
- **Idempotency**: All state-changing operations (POST/PUT/DELETE) MUST enforce idempotency keys to prevent duplicate processing during network retries.
- **Atomicity**: Transfers must be atomic. Money cannot be deducted from source without being added to destination.

## 3. Access Control
- **IDOR**: Users must strictly only access their own data. Cross-account access is a critical failure.
- **Admin Access**: Admin endpoints must require a separate, higher-privilege token or be unreachable from the public internet.

## 4. Error Handling
- Errors must return JSON.
- Errors must NOT leak stack traces or internal database query structures.
