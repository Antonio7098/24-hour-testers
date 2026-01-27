# Governance & Security Patterns Guide

This guide covers authentication, multi-tenant isolation, guardrails, and audit logging patterns in Stageflow.

## Overview

Production pipelines need:
- **Authentication**: Validating user identity
- **Multi-tenancy**: Isolating data between organizations
- **Guardrails**: Content filtering and policy enforcement
- **Audit logging**: Recording actions for compliance

Stageflow provides built-in support and helper utilities for all of these, plus observability hooks (provider responses, streaming telemetry, analytics overflow callbacks) so policy violations can be audited in real time.

## Authentication

### Auth Context

The `AuthContext` carries validated user identity through the pipeline:

```python
from stageflow.auth import AuthContext, AuthInterceptor

# Create auth context from validated JWT
auth = AuthContext(
    user_id="user-123",
    roles=["admin", "editor"],
    permissions=["read", "write"],
    token_claims=jwt_claims,
)

# Add to pipeline context
snapshot = ContextSnapshot(
    user_id=uuid4(),
    extensions={"auth": auth.to_dict()},
)
```

### Auth Interceptor

Add authentication enforcement to all stages:

```python
from stageflow.auth import AuthInterceptor

# Create interceptor
auth_interceptor = AuthInterceptor(
    required_roles=["user"],  # At least one required
    allow_anonymous=False,
)

# Add to pipeline
graph = UnifiedStageGraph(
    specs=specs,
    interceptors=[auth_interceptor, *get_default_interceptors()],
)
```

### Testing with Mock Auth

```python
from stageflow.helpers import MockAuthProvider

# Create mock provider
auth = MockAuthProvider(accept_any=True)

# Or with specific tokens
token, claims = auth.create_token(
    sub="user-123",
    roles=["admin"],
    org_id="org-456",
)

# Validate
claims = await auth.validate(token)
```

## Multi-Tenant Isolation

### Organization Context

Use `OrgContext` to enforce tenant isolation:

```python
from stageflow.auth import OrgContext, OrgEnforcementInterceptor

# Create org context
org = OrgContext(
    org_id="org-123",
    tenant_id="tenant-456",
    environment="production",
)

# Add to snapshot
snapshot = ContextSnapshot(
    org_id=uuid4(),
    extensions={"org": org.to_dict()},
)
```

### Org Enforcement Interceptor

Ensures stages only access data from their organization:

```python
from stageflow.auth import OrgEnforcementInterceptor

# Create interceptor
org_interceptor = OrgEnforcementInterceptor(
    require_org_id=True,
    validate_data_access=True,
)

# All stages will have org context validated
```

### Multi-Tenant Stage Pattern

```python
class TenantAwareStage:
    name = "tenant_data"
    kind = StageKind.ENRICH

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get org context
        org_id = ctx.snapshot.org_id
        if not org_id:
            return StageOutput.fail(error="Organization context required")

        # Query only tenant's data
        data = await self.db.query(
            "SELECT * FROM records WHERE org_id = ?",
            [str(org_id)]
        )

        return StageOutput.ok(records=data)
```

### Tenant Isolation Testing

```python
def test_tenant_isolation():
    """Ensure tenant A can't access tenant B's data."""
    org_a = uuid4()
    org_b = uuid4()

    # Create context for org A
    ctx_a = create_test_stage_context(org_id=org_a)

    # Stage should only return org A's data
    result = await stage.execute(ctx_a)

    for record in result.data["records"]:
        assert record["org_id"] == str(org_a)
```

## Guardrails

### Using Built-in Guardrails

Stageflow provides ready-to-use guardrail utilities:

```python
from stageflow.helpers import (
    GuardrailStage,
    PIIDetector,
    ContentFilter,
    InjectionDetector,
    GuardrailConfig,
)

# Create guardrail stage with multiple checks
guardrail = GuardrailStage(
    checks=[
        PIIDetector(redact=True),
        ContentFilter(block_profanity=True),
        InjectionDetector(),
    ],
    config=GuardrailConfig(
        fail_on_violation=True,
        transform_content=True,
    ),
)

# Add to pipeline before LLM
pipeline = (
    Pipeline()
    .with_stage("guard_input", guardrail, StageKind.GUARD)
    .with_stage("llm", LLMStage, StageKind.TRANSFORM,
                dependencies=("guard_input",))
    .with_stage(
        "tool_policy",
        ToolPolicyStage(registry=tool_registry),
        StageKind.GUARD,
        dependencies=("llm",),
    )
)
```

### PII Detection and Redaction

```python
from stageflow.helpers import PIIDetector

# Detect and redact PII
detector = PIIDetector(
    redact=True,
    redaction_char="*",
    detect_types={"email", "phone", "ssn"},
)

result = detector.check("Contact me at john@example.com or 555-123-4567")

print(result.passed)  # False
print(result.transformed_content)  # "Contact me at ******************** or ************"
print(result.violations)  # List of PolicyViolation objects
```

### Content Filtering

```python
from stageflow.helpers import ContentFilter

# Filter inappropriate content
filter = ContentFilter(
    block_profanity=True,
    blocked_patterns=[
        r"competitor\s+product",
        r"confidential|secret",
    ],
)

result = filter.check("Let me tell you about our competitor product...")
```

### Injection Detection

```python
from stageflow.helpers import InjectionDetector

detector = InjectionDetector(
    additional_patterns=[
        r"<custom_injection_pattern>",
    ],
)

result = detector.check("Ignore previous instructions and...")
print(result.passed)  # False
print(result.violations[0].type)  # ViolationType.INJECTION_ATTEMPT
```

### Custom Guardrails

Implement the `GuardrailCheck` protocol:

```python
from stageflow.helpers.guardrails import GuardrailCheck, GuardrailResult, PolicyViolation, ViolationType

class CustomPolicyCheck:
    """Custom guardrail for domain-specific policies."""

    def check(self, content: str, context: dict | None = None) -> GuardrailResult:
        violations = []

        # Check your custom policy
        if "forbidden_topic" in content.lower():
            violations.append(PolicyViolation(
                type=ViolationType.BLOCKED_TOPIC,
                message="Forbidden topic detected",
                severity=1.0,
            ))

        return GuardrailResult(
            passed=len(violations) == 0,
            violations=violations,
        )

# Use with GuardrailStage
guardrail = GuardrailStage(checks=[
    PIIDetector(),
    CustomPolicyCheck(),
])
```

## Audit Logging

### Event-Based Audit Trail

Use event sinks to capture audit events:

```python
from stageflow.helpers import AnalyticsSink, JSONFileExporter, BufferedExporter

# Create audit exporter with overflow callback
exporter = BufferedExporter(
    JSONFileExporter("audit_log.jsonl"),
    on_overflow=lambda dropped, size: logger.warning(
        "Audit buffer pressure", extra={"dropped": dropped, "buffer": size}
    ),
    high_water_mark=0.8,
)

# Create sink that captures relevant events
audit_sink = AnalyticsSink(
    exporter,
    include_patterns=["auth.", "guardrail.", "tool."],
)

# Use as event sink
ctx = StageContext(
    snapshot=snapshot,
    config={"event_sink": audit_sink},
)
```

### Audit Stage Pattern

Create a dedicated audit stage:

```python
class AuditStage:
    """Captures audit events for compliance."""

    name = "audit"
    kind = StageKind.WORK

    def __init__(self, audit_store: AuditStore):
        self._store = audit_store

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Collect audit data from context
        audit_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pipeline_run_id": str(ctx.snapshot.pipeline_run_id),
            "user_id": str(ctx.snapshot.user_id),
            "org_id": str(ctx.snapshot.org_id) if ctx.snapshot.org_id else None,
            "action": ctx.snapshot.topology,
            "input_text": ctx.snapshot.input_text[:100] if ctx.snapshot.input_text else None,
        }

        # Add guardrail results if available
        if ctx.inputs and ctx.inputs.has_output("guard_input"):
            guard_output = ctx.inputs.get_output("guard_input")
            audit_record["guardrail_passed"] = guard_output.data.get("guardrail_passed")
            audit_record["violations"] = guard_output.data.get("violations", [])

        # Store audit record
        await self._store.write(audit_record)

        return StageOutput.ok(audit_id=audit_record["pipeline_run_id"])
```

### Compliance-Ready Pipeline

```python
pipeline = (
    Pipeline()
    # 1. Validate auth first
    .with_stage("auth", AuthValidationStage, StageKind.GUARD)

    # 2. Run guardrails on input
    .with_stage("guard_input", InputGuardrailStage, StageKind.GUARD,
                dependencies=("auth",))

    # 3. Main processing
    .with_stage("process", ProcessStage, StageKind.TRANSFORM,
                dependencies=("guard_input",))

    # 4. Run guardrails on output
    .with_stage("guard_output", OutputGuardrailStage, StageKind.GUARD,
                dependencies=("process",))

    # 5. Audit everything
    .with_stage("audit", AuditStage, StageKind.WORK,
                dependencies=("guard_input", "guard_output", "process"))
)
```

## Complete Example

Here's a complete multi-tenant pipeline with full governance:

```python
from stageflow import Pipeline, StageKind
from stageflow.auth import AuthInterceptor, OrgEnforcementInterceptor
from stageflow.helpers import (
    GuardrailStage, PIIDetector, ContentFilter, InjectionDetector,
    MemoryFetchStage, MemoryWriteStage, InMemoryStore,
    AnalyticsSink, JSONFileExporter, BufferedExporter, ChunkQueue, StreamingBuffer,
)

# Create stores
memory_store = InMemoryStore()
audit_exporter = JSONFileExporter("audit.jsonl")

# Create guardrails
input_guardrail = GuardrailStage(
    checks=[PIIDetector(redact=True), InjectionDetector()],
    config=GuardrailConfig(fail_on_violation=True),
)

output_guardrail = GuardrailStage(
    checks=[PIIDetector(redact=True), ContentFilter()],
    config=GuardrailConfig(fail_on_violation=False),  # Log but don't fail
)

# Build pipeline
pipeline = (
    Pipeline()
    .with_stage("fetch_memory", MemoryFetchStage(memory_store), StageKind.ENRICH)
    .with_stage("guard_input", input_guardrail, StageKind.GUARD)
    .with_stage("llm", LLMStage, StageKind.TRANSFORM,
                dependencies=("fetch_memory", "guard_input"))
    .with_stage("guard_output", output_guardrail, StageKind.GUARD,
                dependencies=("llm",))
    .with_stage("write_memory", MemoryWriteStage(memory_store), StageKind.WORK,
                dependencies=("llm",))
    .with_stage("tool_policy", ToolPolicyStage(tool_registry), StageKind.GUARD,
                dependencies=("llm",))
)

# Build with auth interceptors
graph = pipeline.build()

# Run with full context
snapshot = ContextSnapshot(
    pipeline_run_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),  # Multi-tenant
    input_text="User input here",
    extensions={
        "auth": {"user_id": "user-123", "roles": ["user"]},
        "org": {"org_id": "org-456", "environment": "production"},
    },
)

# Attach streaming telemetry hooks for auditability
queue = ChunkQueue(event_emitter=audit_sink.emit)
buffer = StreamingBuffer(event_emitter=audit_sink.emit)
```

## Best Practices

### 1. Defense in Depth

Apply multiple layers of protection:

```python
# Layer 1: Auth interceptor (request level)
# Layer 2: Input guardrails (before processing)
# Layer 3: Output guardrails (after processing)
# Layer 4: Audit logging (all actions)
```

### 2. Fail Secure

Default to denying access:

```python
# Good: Explicit allow
if user_has_permission(ctx, "admin"):
    perform_admin_action()
else:
    return StageOutput.fail(error="Permission denied")

# Bad: Implicit allow
if not user_is_blocked(ctx):
    perform_admin_action()  # Dangerous
```

### 3. Audit Critical Actions

Log all sensitive operations:

```python
# Always audit
await audit_log.write({
    "action": "data_access",
    "user_id": str(ctx.snapshot.user_id),
    "org_id": str(ctx.snapshot.org_id),
    "resource": resource_id,
    "timestamp": datetime.now(UTC).isoformat(),
})
```

### 4. Test Security Boundaries

```python
@pytest.mark.security
async def test_org_isolation():
    """User from org A cannot access org B data."""
    ctx = create_test_stage_context(org_id=org_a_id)
    result = await stage.execute(ctx)

    # Should not contain org B data
    for item in result.data.get("items", []):
        assert item["org_id"] != str(org_b_id)
```

## Next Steps

- [Authentication Guide](authentication.md) - Deep dive into auth
- [Tools Guide](tools.md) - Tool execution with approval flows
- [Observability Guide](observability.md) - Monitoring and metrics
