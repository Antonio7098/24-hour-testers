# Error Handling

This guide covers error taxonomy, handling strategies, and recovery patterns in stageflow.

## Error Categories

### Transient Errors

Temporary failures that may succeed on retry.

**Examples:**
- Provider timeouts
- Rate limits
- Network glitches
- Temporary service unavailability

**Handling:** Retry with exponential backoff

```python
from stageflow import StageOutput

async def execute(self, ctx: StageContext) -> StageOutput:
    try:
        result = await self.provider.call()
        return StageOutput.ok(result=result)
    except TimeoutError:
        return StageOutput.retry(error="Provider timeout, will retry")
```

### Permanent Errors

Failures that won't succeed on retry.

**Examples:**
- Invalid API key
- Malformed request
- Resource not found
- Permission denied

**Handling:** Fail fast with clear error message

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    if not ctx.snapshot.user_id:
        return StageOutput.fail(error="user_id is required")
    
    try:
        result = await self.service.get_user(ctx.snapshot.user_id)
    except NotFoundError:
        return StageOutput.fail(error=f"User {ctx.snapshot.user_id} not found")
```

### Logic Errors

Bugs or invalid state in the application.

**Examples:**
- Missing inputs
- Invalid state transitions
- Duplicate output keys
- Type mismatches

**Handling:** Fix the code, add validation

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Validate required inputs
    if not ctx.inputs.has_output("required_stage"):
        return StageOutput.fail(error="Missing required input: required_key")
    
    value = ctx.inputs.get_from("required_stage", "required_key")
    if not isinstance(value, str):
        return StageOutput.fail(error=f"Expected string, got {type(value).__name__}")
```

### Systemic Errors

Infrastructure-level failures.

**Examples:**
- Database outage
- Circuit breaker open
- Memory exhaustion
- Disk full

**Handling:** DLQ, alert ops, fail run

```python
from stageflow.observability import CircuitBreakerOpenError

async def execute(self, ctx: StageContext) -> StageOutput:
    try:
        result = await self.db.query(...)
    except CircuitBreakerOpenError:
        return StageOutput.fail(
            error="Database circuit breaker open",
            data={"systemic": True, "dlq": True},
        )
```

### Policy Errors

Security or compliance violations.

**Examples:**
- Content policy violation
- Cross-tenant access
- Unauthorized action
- Rate limit exceeded

**Handling:** Fail with explanation, no retry

```python
from stageflow.auth import CrossTenantAccessError

async def execute(self, ctx: StageContext) -> StageOutput:
    item = await self.db.get_item(item_id)
    
    if item.org_id != ctx.snapshot.org_id:
        return StageOutput.fail(
            error="Access denied: resource belongs to another organization",
            data={"policy_violation": True},
        )
```

## Stage Output Patterns

### Success

```python
return StageOutput.ok(
    result="processed",
    metadata={"duration_ms": 150},
)
```

### Provider Metadata

Always attach standardized provider response payloads so downstream analytics can categorize failures:

```python
from stageflow.helpers import LLMResponse

try:
    response = await self.llm_client.chat(messages)
except TimeoutError:
    return StageOutput.retry(error="LLM timeout", data={"component": "llm"})

llm = LLMResponse(
    content=response,
    model="gpt-4",
    provider="openai",
    input_tokens=prompt_tokens,
    output_tokens=completion_tokens,
)
return StageOutput.ok(response=llm.content, llm=llm.to_dict())
```

### Skip (Not an Error)

```python
if not ctx.snapshot.user_id:
    return StageOutput.skip(reason="No user_id provided")
```

### Cancel (Stop Pipeline)

```python
if is_blocked:
    return StageOutput.cancel(
        reason="Content blocked by policy",
        data={"blocked": True},
    )
```

### Fail (Error)

```python
return StageOutput.fail(
    error="Service unavailable",
    data={"error_code": "SERVICE_UNAVAILABLE"},
)
```

### Retry (Retryable Error)

```python
return StageOutput.retry(
    error="Rate limited, please retry",
    data={"retry_after_ms": 1000},
)
```

## Interceptor Error Handling

### ErrorAction Options

```python
from stageflow import ErrorAction

async def on_error(self, stage_name: str, error: Exception, ctx) -> ErrorAction:
    if isinstance(error, TransientError):
        return ErrorAction.RETRY      # Retry the stage
    elif isinstance(error, RecoverableError):
        return ErrorAction.FALLBACK   # Use fallback result
    else:
        return ErrorAction.FAIL       # Propagate failure
```

### Retry Interceptor

```python
class RetryInterceptor(BaseInterceptor):
    name = "retry"
    priority = 12

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._counts = {}

    async def on_error(self, stage_name: str, error: Exception, ctx) -> ErrorAction:
        if not self._is_retryable(error):
            return ErrorAction.FAIL

        key = f"{ctx.pipeline_run_id}:{stage_name}"
        self._counts[key] = self._counts.get(key, 0) + 1

        if self._counts[key] > self.max_retries:
            return ErrorAction.FAIL

        return ErrorAction.RETRY

    def _is_retryable(self, error: Exception) -> bool:
        return isinstance(error, (TimeoutError, ConnectionError))
```

## Pipeline-Level Errors

### StageExecutionError

Raised when a stage fails:

```python
from stageflow import StageExecutionError

try:
    results = await graph.run(ctx)
except StageExecutionError as e:
    print(f"Stage '{e.stage}' failed: {e.original}")
    print(f"Recoverable: {e.recoverable}")
```

### UnifiedPipelineCancelled

Raised when a stage cancels the pipeline (not an error):

```python
from stageflow.pipeline.dag import UnifiedPipelineCancelled

try:
    results = await graph.run(ctx)
except UnifiedPipelineCancelled as e:
    print(f"Cancelled by '{e.stage}': {e.reason}")
    partial_results = e.results  # Results from completed stages
```

## Error Summarization

### Summarize Errors

```python
from stageflow.observability import summarize_pipeline_error

try:
    results = await graph.run(ctx)
except Exception as e:
    summary = summarize_pipeline_error(e)
    # {
    #     "code": "TIMEOUT",
    #     "type": "TimeoutError",
    #     "message": "Stage timed out after 30000ms",
    #     "retryable": True,
    # }
```

### Error Codes

| Code | Category | Retryable |
|------|----------|-----------|
| `TIMEOUT` | Transient | Yes |
| `CIRCUIT_OPEN` | Systemic | Yes |
| `RATE_LIMITED` | Transient | Yes |
| `INVALID_INPUT` | Permanent | No |
| `NOT_FOUND` | Permanent | No |
| `UNAUTHORIZED` | Policy | No |
| `UNKNOWN` | Unknown | No |

## Graceful Degradation

### Fallback Responses

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    try:
        response = await self.llm_client.chat(messages)
        return StageOutput.ok(response=response)
    except Exception as e:
        # Fallback to canned response
        return StageOutput.ok(
            response="I'm having trouble right now. Please try again.",
            fallback=True,
            original_error=str(e),
        )
```

### Partial Results

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    results = []
    errors = []
    
    for item in items:
        try:
            result = await self.process(item)
            results.append(result)
        except Exception as e:
            errors.append({"item": item, "error": str(e)})
    
    # Return partial success
    return StageOutput.ok(
        results=results,
        errors=errors,
        partial=len(errors) > 0,
    )
```

### Circuit Breaker Pattern

```python
from stageflow.observability import get_circuit_breaker, CircuitBreakerOpenError

async def execute(self, ctx: StageContext) -> StageOutput:
    breaker = get_circuit_breaker()
    
    if await breaker.is_open(operation="llm", provider="openai"):
        # Use fallback provider
        return await self._call_fallback_provider(ctx)
    
    try:
        result = await self.openai_client.chat(...)
        await breaker.record_success(operation="llm", provider="openai")
        return StageOutput.ok(result=result)
    except Exception as e:
        await breaker.record_failure(operation="llm", provider="openai", reason=str(e))
        raise
```

## Logging Errors

### Structured Error Logging

```python
import logging

logger = logging.getLogger(__name__)

async def execute(self, ctx: StageContext) -> StageOutput:
    try:
        result = await self.service.call()
        return StageOutput.ok(result=result)
    except Exception as e:
        logger.error(
            "Stage execution failed",
            extra={
                "stage": self.name,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "pipeline_run_id": str(ctx.snapshot.pipeline_run_id),
                "user_id": str(ctx.snapshot.user_id),
            },
            exc_info=True,
        )
        return StageOutput.fail(error=str(e))
```

### Error Events

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    try:
        result = await self.service.call()
        return StageOutput.ok(result=result)
    except Exception as e:
        # Emit error event
        ctx.emit_event("stage.error", {
            "stage": self.name,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "retryable": isinstance(e, TransientError),
        })
        raise
```

## Best Practices

### 1. Fail Fast for Invalid Input

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Validate early
    if not ctx.snapshot.input_text:
        return StageOutput.fail(error="input_text is required")
    
    if len(ctx.snapshot.input_text) > 10000:
        return StageOutput.fail(error="input_text exceeds maximum length")
    
    # Continue with valid input...
```

### 2. Provide Actionable Error Messages

```python
# Good
return StageOutput.fail(
    error="Document not found. Verify the document_id exists and you have access.",
    data={"document_id": doc_id, "suggestion": "Check document permissions"},
)

# Bad
return StageOutput.fail(error="Error")
```

### 3. Include Context in Errors

```python
return StageOutput.fail(
    error=f"LLM call failed: {e}",
    data={
        "model": self.model,
        "input_tokens": len(messages),
        "error_type": type(e).__name__,
    },
)
```

### 4. Don't Swallow Errors Silently

```python
# Bad
try:
    result = await risky_operation()
except Exception:
    pass  # Silent failure

# Good
try:
    result = await risky_operation()
except Exception as e:
    logger.warning(f"Operation failed: {e}")
    return StageOutput.fail(error=str(e))
```

### 5. Use Appropriate Error Types

```python
# Use skip for expected conditions
if not ctx.snapshot.user_id:
    return StageOutput.skip(reason="Anonymous user")

# Use cancel for policy blocks
if is_blocked:
    return StageOutput.cancel(reason="Content blocked")

# Use fail for actual errors
if service_error:
    return StageOutput.fail(error="Service unavailable")
```

## Next Steps

- [Testing Strategies](testing.md) — Test error handling
- [Observability](../guides/observability.md) — Monitor errors
- [Custom Interceptors](custom-interceptors.md) — Build error handling middleware
