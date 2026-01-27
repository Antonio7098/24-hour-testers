# Authentication

Stageflow provides built-in support for authentication and multi-tenant isolation. This guide covers how to secure your pipelines.

## Overview

The auth system provides:

- **AuthContext** — Authenticated user identity from JWT validation
- **OrgContext** — Organization/tenant information with features
- **AuthInterceptor** — JWT validation middleware
- **OrgEnforcementInterceptor** — Tenant isolation enforcement
- **TenantContext** — Tenant-scoped operations with validation
- **TenantIsolationValidator** — Track and validate tenant isolation
- **TenantAwareLogger** — Automatic tenant context in logs

## AuthContext

The `AuthContext` represents an authenticated user:

```python
from stageflow.auth import AuthContext
from uuid import uuid4

auth = AuthContext(
    user_id=uuid4(),
    session_id=uuid4(),
    email="user@example.com",
    org_id=uuid4(),
    roles=("user", "editor"),
)

# Check roles
if auth.has_role("admin"):
    # Admin access
    ...

if auth.is_admin():
    # Has 'admin' or 'org_admin' role
    ...

# Always authenticated
assert auth.is_authenticated
```

## OrgContext

The `OrgContext` represents organization/tenant information:

```python
from stageflow.auth import OrgContext
from uuid import uuid4

org = OrgContext(
    org_id=uuid4(),
    tenant_id=uuid4(),  # May differ in multi-tenant setups
    plan_tier="pro",    # "starter", "pro", or "enterprise"
    features=("advanced_analytics", "custom_models"),
)

# Check features
if org.has_feature("advanced_analytics"):
    # Feature enabled
    ...

# Check plan tier
if org.plan_tier == "enterprise":
    # Enterprise features
    ...
```

## Auth Interceptors

### AuthInterceptor

Validates JWT tokens and creates `AuthContext`:

```python
from stageflow.auth import AuthInterceptor, JwtValidator

class MyJwtValidator:
    """Custom JWT validator."""
    
    async def validate(self, token: str) -> AuthContext:
        # Validate token with your auth provider
        # (Clerk, Auth0, WorkOS, etc.)
        claims = await verify_jwt(token)
        
        return AuthContext(
            user_id=UUID(claims["sub"]),
            session_id=UUID(claims["session_id"]),
            email=claims.get("email"),
            org_id=UUID(claims["org_id"]) if claims.get("org_id") else None,
            roles=tuple(claims.get("roles", [])),
        )

# Create interceptor with validator
auth_interceptor = AuthInterceptor(validator=MyJwtValidator())
```

### OrgEnforcementInterceptor

Ensures tenant isolation:

```python
from stageflow.auth import OrgEnforcementInterceptor

org_interceptor = OrgEnforcementInterceptor()
# Verifies ctx.org_id matches AuthContext.org_id
# Raises CrossTenantAccessError on mismatch
```

### Using Auth Interceptors

```python
from stageflow import get_default_interceptors

# Include auth interceptors
interceptors = get_default_interceptors(include_auth=True)
# [AuthInterceptor, OrgEnforcementInterceptor, TimeoutInterceptor, ...]

# Or manually add them
from stageflow.auth import AuthInterceptor, OrgEnforcementInterceptor

interceptors = [
    AuthInterceptor(validator=my_validator),
    OrgEnforcementInterceptor(),
    *get_default_interceptors(),
]
```

## JWT Validation

### JwtValidator Protocol

Implement the `JwtValidator` protocol:

```python
from stageflow.auth import JwtValidator, AuthContext

class JwtValidator(Protocol):
    async def validate(self, token: str) -> AuthContext:
        """Validate a JWT and return AuthContext."""
        ...
```

### Mock Validator for Testing

```python
from stageflow.auth import MockJwtValidator

# For testing - always returns a valid AuthContext
mock_validator = MockJwtValidator(
    user_id=uuid4(),
    org_id=uuid4(),
    roles=("user",),
)

auth_interceptor = AuthInterceptor(validator=mock_validator)
```

### Example: Clerk Integration

```python
import httpx
from stageflow.auth import JwtValidator, AuthContext

class ClerkJwtValidator:
    def __init__(self, clerk_secret_key: str):
        self.secret_key = clerk_secret_key
    
    async def validate(self, token: str) -> AuthContext:
        # Verify JWT signature and claims
        claims = await self._verify_token(token)
        
        return AuthContext(
            user_id=UUID(claims["sub"]),
            session_id=UUID(claims["sid"]),
            email=claims.get("email"),
            org_id=UUID(claims["org_id"]) if claims.get("org_id") else None,
            roles=tuple(claims.get("roles", [])),
        )
    
    async def _verify_token(self, token: str) -> dict:
        # Use Clerk's SDK or verify manually
        ...
```

## Auth Errors

### Error Types

```python
from stageflow.auth import (
    AuthenticationError,      # Base auth error
    InvalidTokenError,        # Token is invalid
    TokenExpiredError,        # Token has expired
    MissingClaimsError,       # Required claims missing
    CrossTenantAccessError,   # Accessing another tenant's data
)

try:
    await auth_interceptor.before(stage_name, ctx)
except InvalidTokenError as e:
    # Handle invalid token
    ...
except TokenExpiredError as e:
    # Handle expired token
    ...
except CrossTenantAccessError as e:
    # Handle cross-tenant access attempt
    ...
```

### Handling Auth Failures

```python
from stageflow import BaseInterceptor, InterceptorResult

class AuthErrorHandlerInterceptor(BaseInterceptor):
    name = "auth_error_handler"
    priority = 0  # Run before auth interceptor
    
    async def on_error(self, stage_name, error, ctx):
        if isinstance(error, AuthenticationError):
            # Log the attempt
            logger.warning(
                "Authentication failed",
                extra={
                    "error_type": type(error).__name__,
                    "stage": stage_name,
                    "request_id": str(ctx.request_id),
                },
            )
        return ErrorAction.FAIL
```

## Auth Events

The auth system emits events for auditing:

```python
from stageflow.auth import (
    AuthLoginEvent,
    AuthFailureEvent,
    TenantAccessDeniedEvent,
)

# Events are emitted through the event sink
# auth.login - Successful authentication
# auth.failure - Failed authentication attempt
# tenant.access_denied - Cross-tenant access blocked
```

## Accessing Auth in Stages

### From Context Data

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Auth context is injected via StageInputs ports
    auth_context = getattr(ctx.inputs.ports, "auth", None) if ctx.inputs.ports else None
    
    if auth_context:
        user_id = auth_context.user_id
        is_admin = auth_context.is_admin()
        roles = auth_context.roles
```

### From Snapshot

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Identity from snapshot
    user_id = ctx.snapshot.user_id
    org_id = ctx.snapshot.org_id
    session_id = ctx.snapshot.session_id
```

## Multi-Tenant Patterns

### Row-Level Security

Use org_id for data filtering:

```python
class DataStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        org_id = ctx.snapshot.org_id
        
        # Always filter by org_id
        data = await self.db.query(
            "SELECT * FROM items WHERE org_id = $1",
            org_id,
        )
        
        return StageOutput.ok(items=data)
```

### Application-Level Filtering

```python
class SecureDataStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        org_id = ctx.snapshot.org_id
        
        # Verify ownership before returning
        items = await self.db.get_items(item_ids)
        
        # Filter to only items belonging to this org
        owned_items = [i for i in items if i.org_id == org_id]
        
        return StageOutput.ok(items=owned_items)
```

### Cross-Tenant Prevention

```python
from stageflow.auth import CrossTenantAccessError

class ItemStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        item_id = ctx.snapshot.input_text
        org_id = ctx.snapshot.org_id
        
        item = await self.db.get_item(item_id)
        
        # Verify ownership
        if item.org_id != org_id:
            raise CrossTenantAccessError(
                f"Item {item_id} belongs to another organization"
            )
        
        return StageOutput.ok(item=item)
```

## Role-Based Access Control

### Checking Roles in Stages

```python
class AdminStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        auth = getattr(ctx.inputs.ports, "auth", None) if ctx.inputs.ports else None
        
        if not auth or not auth.is_admin():
            return StageOutput.cancel(
                reason="Admin access required",
                data={"error": "unauthorized"},
            )
        
        # Admin-only logic
        ...
```

### Role-Based Tool Gating

```python
from stageflow.tools import ToolDefinition

admin_tool = ToolDefinition(
    name="admin_action",
    action_type="ADMIN_ACTION",
    handler=admin_handler,
    allowed_behaviors=("admin",),  # Only in admin mode
)
```

## Best Practices

### 1. Always Validate Tokens

Never trust client-provided identity:

```python
# Bad: Trusting client-provided user_id
user_id = request.headers.get("X-User-Id")

# Good: Extract from validated JWT
auth = await validator.validate(token)
user_id = auth.user_id
```

### 2. Enforce Tenant Isolation

Always filter data by org_id:

```python
# Bad: No tenant filtering
items = await db.query("SELECT * FROM items")

# Good: Filter by org_id
items = await db.query(
    "SELECT * FROM items WHERE org_id = $1",
    ctx.snapshot.org_id,
)
```

### 3. Log Auth Events

Track authentication for security auditing:

```python
logger.info(
    "User authenticated",
    extra={
        "user_id": str(auth.user_id),
        "org_id": str(auth.org_id),
        "roles": auth.roles,
        "request_id": str(ctx.request_id),
    },
)
```

### 4. Use Least Privilege

Only grant necessary roles:

```python
# Check specific role, not just "is authenticated"
if auth.has_role("document_editor"):
    # Can edit documents
    ...
elif auth.has_role("document_viewer"):
    # Can only view
    ...
```

## Multi-Tenant Isolation

### TenantContext

For tenant-scoped operations with validation:

```python
from stageflow.auth import TenantContext, TenantIsolationError
from uuid import uuid4

tenant_ctx = TenantContext(org_id=uuid4())

# Validate access to resources
try:
    tenant_ctx.validate_access(resource.org_id, operation="read_document")
except TenantIsolationError as e:
    print(f"Access denied: {e}")

# Get tenant-aware logger
logger = tenant_ctx.get_logger("my_service")
logger.info("Processing request")  # Includes org_id automatically
```

### TenantIsolationValidator

Track and validate tenant isolation across execution:

```python
from stageflow.auth import TenantIsolationValidator

validator = TenantIsolationValidator(expected_org_id=org_id, strict=False)

# Record all resource accesses
validator.record_access(resource.org_id, resource_type="document")
validator.record_access(other_org_id, resource_type="document")  # Violation

# Check for violations
violations = validator.get_violations()
if violations:
    print(f"Cross-tenant violations: {len(violations)}")

# Verify isolation
if not validator.is_isolated():
    raise SecurityError("Tenant isolation violated")
```

### Tenant Context Variables

Manage tenant context across async boundaries:

```python
from stageflow.auth import (
    set_current_tenant,
    get_current_tenant,
    require_tenant,
    clear_current_tenant
)

# Set current tenant
set_current_tenant(org_id)

# Require tenant (raises if not set)
tenant_id = require_tenant()

# Clear when done
clear_current_tenant()
```

### 5. Handle Auth Failures Gracefully

Return appropriate errors to clients:

```python
try:
    results = await graph.run(ctx)
except AuthenticationError as e:
    return {"error": "authentication_required", "message": str(e)}
except CrossTenantAccessError as e:
    return {"error": "access_denied", "message": "Resource not found"}
except TenantIsolationError as e:
    return {"error": "access_denied", "message": "Tenant isolation violation"}
```

## Next Steps

- [Interceptors](interceptors.md) — Learn more about middleware
- [Error Handling](../advanced/errors.md) — Handle auth errors
- [Testing](../advanced/testing.md) — Test auth flows
- [Observability](observability.md) — Multi-tenant tracing and logging
