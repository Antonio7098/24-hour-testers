# Interceptors

Interceptors run around stage execution and receive the **PipelineContext**, which gives them access to run identity, topology, shared data, and cancellation state.

Interceptors are middleware that wrap stage execution to provide cross-cutting concerns like logging, metrics, timeouts, and authentication. This guide covers how to use and create interceptors.

## What Are Interceptors?

Interceptors wrap stage execution in a layered manner:

```
Request → [Timeout] → [CircuitBreaker] → [Tracing] → [Metrics] → [Logging] → Stage
                                                                              ↓
Response ← [Timeout] ← [CircuitBreaker] ← [Tracing] ← [Metrics] ← [Logging] ← Stage
```

Each interceptor can:
- Run code **before** the stage executes
- Run code **after** the stage completes
- Handle **errors** during execution
- **Short-circuit** execution (skip the stage entirely)

## Built-in Interceptors

Stageflow provides several interceptors out of the box:

### TimeoutInterceptor

Enforces per-stage execution timeouts:

```python
from stageflow import TimeoutInterceptor

# Default timeout is 30 seconds
timeout = TimeoutInterceptor()

# Pipelines can override by setting ctx.data["_timeout_ms"] before execution
pipeline_ctx.data["_timeout_ms"] = 60000  # 60 seconds for this run
```

### CircuitBreakerInterceptor

Prevents cascading failures by tracking stage failures:

```python
from stageflow import CircuitBreakerInterceptor

circuit_breaker = CircuitBreakerInterceptor()
# After 5 failures, circuit opens for 30 seconds
# Half-open state allows test requests through
```

### TracingInterceptor

Creates OpenTelemetry-compatible spans:

```python
from stageflow import TracingInterceptor

tracing = TracingInterceptor()
# Adds span context to ctx.data for downstream tracing
```

Add provider metadata as span attributes by using the standardized helpers:

```python
from stageflow.helpers import LLMResponse

span.set_attributes(LLMResponse(...).to_otel_attributes())
```

### ChildTrackerMetricsInterceptor

Logs `ChildRunTracker` metrics for subpipeline orchestration:

```python
from stageflow import ChildTrackerMetricsInterceptor

tracker_metrics = ChildTrackerMetricsInterceptor()
# Logs registration counts, lookup operations, tree traversals, etc.
```

### MetricsInterceptor

Records stage execution metrics:

```python
from stageflow import MetricsInterceptor

metrics = MetricsInterceptor()
# Logs duration, status, and pipeline_run_id
```

Pair with queue/buffer telemetry emitters so metrics can correlate high latency with backpressure events.

### LoggingInterceptor

Provides structured JSON logging:

```python
from stageflow import LoggingInterceptor

logging_interceptor = LoggingInterceptor()
# Logs stage start/complete with structured data
```

## Default Interceptors

Get the default set of interceptors:

```python
from stageflow import get_default_interceptors

interceptors = get_default_interceptors()
# Returns: [IdempotencyInterceptor, TimeoutInterceptor, CircuitBreakerInterceptor,
#           TracingInterceptor, MetricsInterceptor, ChildTrackerMetricsInterceptor, LoggingInterceptor]

# Include auth interceptors
interceptors = get_default_interceptors(include_auth=True)
# Adds: [OrganizationInterceptor, RegionInterceptor, RateLimitInterceptor, PolicyGatewayInterceptor]

# Share a store across stages / pipelines
shared_store = MyPersistentIdempotencyStore()
interceptors = get_default_interceptors(idempotency_store=shared_store)
```

### Ordering Guarantees (Verified)

Interceptors are sorted by `priority` every time `run_with_interceptors()` executes a stage, so lower values always wrap higher ones regardless of construction order. When auth interceptors are enabled, the stack is:

- `AuthInterceptor` (priority `1`) when explicitly supplied
- `OrganizationInterceptor` (`30`), `RegionInterceptor` (`35`), `RateLimitInterceptor` (`37`), `PolicyGatewayInterceptor` (`39`)
- Reliability/observability defaults (`Timeout` `5`, `CircuitBreaker` `10`, `Tracing` `20`, `Metrics` `40`, `ChildTrackerMetrics` `45`, `Logging` `50`)

This matches the runtime behavior enforced in `run_with_interceptors()` and the unit tests that assert sorting semantics, so authentication always runs before timeouts or circuit breakers even if the input list is shuffled.@stageflow/pipeline/interceptors.py#356-538 @tests/framework/test_interceptors.py#567-604

## Interceptor Priority

Interceptors run in **priority order** (lower = runs first, outer wrapper):

| Interceptor | Priority | Position |
|-------------|----------|----------|
| AuthInterceptor | 1 | Outermost |
| OrgEnforcementInterceptor | 2 | |
| TimeoutInterceptor | 5 | |
| CircuitBreakerInterceptor | 10 | |
| TracingInterceptor | 20 | |
| MetricsInterceptor | 40 | |
| ChildTrackerMetricsInterceptor | 45 | |
| LoggingInterceptor | 50 | Innermost |

Lower priority interceptors wrap higher priority ones, so they see the full execution including any modifications by inner interceptors.

## Auth Interceptors

### AuthInterceptor

Validates JWT tokens and creates `AuthContext`:

```python
from stageflow.auth import AuthInterceptor, JwtValidator

# With custom validator
validator = MyJwtValidator()  # Implements JwtValidator protocol
auth = AuthInterceptor(validator=validator)

# The interceptor:
# 1. Extracts JWT from context
# 2. Validates the token
# 3. Creates AuthContext with user_id, org_id, roles
# 4. Stores in ctx.data["_auth_context"]
```

### OrgEnforcementInterceptor

Ensures tenant isolation:

```python
from stageflow.auth import OrgEnforcementInterceptor

org_enforcement = OrgEnforcementInterceptor()
# Verifies ctx.org_id matches AuthContext.org_id
# Raises CrossTenantAccessError on mismatch
```

## Creating Custom Interceptors

### Basic Structure

Extend `BaseInterceptor`:

```python
from stageflow import BaseInterceptor, InterceptorResult, ErrorAction
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

class MyInterceptor(BaseInterceptor):
    name = "my_interceptor"
    priority = 30  # Between tracing (20) and metrics (40)

    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        """Called before stage execution."""
        # Return None to continue
        # Return InterceptorResult(stage_ran=False, ...) to short-circuit
        print(f"Before {stage_name}")
        return None

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        """Called after stage completes (success or failure)."""
        print(f"After {stage_name}: {result.status}")

    async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction:
        """Called when stage throws an exception."""
        print(f"Error in {stage_name}: {error}")
        return ErrorAction.FAIL  # or RETRY, FALLBACK
```

### Short-Circuiting Execution

Skip stage execution by returning an `InterceptorResult`:

```python
async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
    # Here `ctx` is a PipelineContext, and `ctx.data` is the shared mutable dictionary for this pipeline run.
    # Check some condition
    if ctx.data.get("skip_all_stages"):
        return InterceptorResult(
            stage_ran=False,
            result={"skipped": True},
            error="Skipped by interceptor",
        )
    return None
```

### Error Handling

Control error behavior with `ErrorAction`:

```python
async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction:
    if isinstance(error, TransientError):
        return ErrorAction.RETRY  # Retry the stage
    elif isinstance(error, RecoverableError):
        return ErrorAction.FALLBACK  # Use fallback result
    else:
        return ErrorAction.FAIL  # Propagate failure
```

### Adding Observations

Interceptors can add data for other interceptors:

```python
from stageflow import InterceptorContext

async def before(self, stage_name: str, ctx: PipelineContext) -> None:
    # Create interceptor context
    i_ctx = InterceptorContext(ctx, _interceptor_name=self.name)
    
    # Add observation
    i_ctx.add_observation("start_time", time.time())

async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
    i_ctx = InterceptorContext(ctx, _interceptor_name=self.name)
    
    # Retrieve observation
    start_time = i_ctx.get_observation("start_time")
    duration = time.time() - start_time
```

## Example: Rate Limiting Interceptor

```python
import time
from collections import defaultdict
from stageflow import BaseInterceptor, InterceptorResult

class RateLimitInterceptor(BaseInterceptor):
    """Limit stage executions per user."""
    
    name = "rate_limit"
    priority = 15  # After circuit breaker, before tracing
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
    
    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        user_id = str(ctx.user_id) if ctx.user_id else "anonymous"
        now = time.time()
        
        # Clean old requests
        cutoff = now - self.window_seconds
        self._requests[user_id] = [
            t for t in self._requests[user_id] if t > cutoff
        ]
        
        # Check limit
        if len(self._requests[user_id]) >= self.max_requests:
            return InterceptorResult(
                stage_ran=False,
                error=f"Rate limit exceeded for user {user_id}",
            )
        
        # Record request
        self._requests[user_id].append(now)
        return None
    
    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        pass  # Nothing to do after
```

## Example: Caching Interceptor

```python
import hashlib
import json
from stageflow import BaseInterceptor, InterceptorResult
from stageflow.stages.result import StageResult
from dataclasses import dataclass

@dataclass
class CachingInterceptor(BaseInterceptor):
    """Cache stage results based on input."""
    
    name = "caching"
    priority = 25  # After tracing
    cache_stages: set[str] | None = None
    _cache: dict[str, StageResult] = None

    def __post_init__(self):
        self.cache_stages = self.cache_stages or set()
        self._cache = {}

    
    def __init__(self, cache_stages: set[str] | None = None):
        self.cache_stages = cache_stages or set()
        self._cache: dict[str, StageResult] = {}
    
    def _cache_key(self, stage_name: str, ctx: PipelineContext) -> str:
        """Generate cache key from stage name and relevant context."""
        key_data = {
            "stage": stage_name,
            "input_text": ctx.data.get("input_text"),
            "user_id": str(ctx.user_id) if ctx.user_id else None,
        }
        return hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    
    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        if stage_name not in self.cache_stages:
            return None
        
        cache_key = self._cache_key(stage_name, ctx)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return InterceptorResult(
                stage_ran=False,
                result=cached.data,
            )
        
        # Store key for after()
        ctx.data[f"_cache_key.{stage_name}"] = cache_key
        return None
    
    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        cache_key = ctx.data.pop(f"_cache_key.{stage_name}", None)
        if cache_key and result.status == "completed":
            self._cache[cache_key] = result
```

## Analytics Overflow Interceptor Pattern

Intercept analytics buffers to trigger overflow callbacks centrally:

```python
from stageflow.helpers import BufferedExporter

class AnalyticsInterceptor(BaseInterceptor):
    name = "analytics_overflow"
    priority = 60

    def __init__(self):
        self._exporter = BufferedExporter(
            ConsoleExporter(),
            on_overflow=self._handle_overflow,
            high_water_mark=0.75,
        )

    def _handle_overflow(self, dropped_count: int, buffer_size: int) -> None:
        logging.warning(
            "Analytics buffer pressure",
            extra={"dropped": dropped_count, "size": buffer_size},
        )
```

Attach this interceptor after `MetricsInterceptor` so telemetry flows in order.

## Tool Registry Parsing from Interceptors

Interceptors can parse tool calls before stages to enforce policies:

```python
class ToolPolicyInterceptor(BaseInterceptor):
    name = "tool_policy"
    priority = 18  # Before tracing

    async def before(self, stage_name: str, ctx: PipelineContext):
        tool_calls = ctx.data.get("pending_tool_calls", [])
        registry = ctx.data.get("tool_registry")
        if not tool_calls or not registry:
            return None

        resolved, unresolved = registry.parse_and_resolve(tool_calls)
        for call in unresolved:
            ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})
            raise PermissionError("Unregistered tool requested")

        ctx.data["resolved_tool_calls"] = resolved
```

This keeps tool parsing centralized and auditable.

## Using Custom Interceptors

### With StageGraph

Pass interceptors when creating the graph:

```python
from stageflow.pipeline.dag import StageGraph

custom_interceptors = [
    RateLimitInterceptor(max_requests=50),
    CachingInterceptor(cache_stages={"expensive_stage"}),
    *get_default_interceptors(),
]

graph = StageGraph(specs=pipeline.stage_specs, interceptors=custom_interceptors)
```

### Ordering Matters

Interceptors are sorted by priority. Ensure your custom interceptor has the right priority:

```python
class MyInterceptor(BaseInterceptor):
    name = "my_interceptor"
    priority = 35  # Runs after tracing (20), before metrics (40)
```

## Interceptor Context

The `InterceptorContext` provides a read-only view of the pipeline context:

```python
from stageflow import InterceptorContext

i_ctx = InterceptorContext(ctx, _interceptor_name="my_interceptor")

# Read-only access to context data
data = i_ctx.data  # Returns a copy

# Access IDs
run_id = i_ctx.pipeline_run_id
request_id = i_ctx.request_id
user_id = i_ctx.user_id
org_id = i_ctx.org_id

# Access configuration
topology = i_ctx.topology
execution_mode = i_ctx.execution_mode
```

## Best Practices

### 1. Keep Interceptors Focused

Each interceptor should handle one concern:

```python
# Good: Single responsibility
class LoggingInterceptor: ...
class MetricsInterceptor: ...
class AuthInterceptor: ...

# Bad: Multiple concerns
class DoEverythingInterceptor:
    async def before(self, ...):
        self.log_start()
        self.record_metric()
        self.check_auth()
        self.apply_rate_limit()
```

### 2. Handle Errors Gracefully

Interceptor errors shouldn't crash the pipeline:

```python
async def before(self, stage_name: str, ctx: PipelineContext) -> None:
    try:
        # Risky operation
        await self.external_service.notify(stage_name)
    except Exception as e:
        # Log but don't fail
        logger.warning(f"Interceptor error: {e}")
```

### 3. Use Appropriate Priority

Choose priority based on when your interceptor needs to run:

- **1-10**: Security (auth, rate limiting)
- **10-20**: Reliability (circuit breaker, timeout)
- **20-40**: Observability (tracing, metrics)
- **40-60**: Logging, auditing

### 4. Clean Up in after()

Always clean up resources in `after()`:

```python
async def before(self, stage_name: str, ctx: PipelineContext) -> None:
    ctx.data["_my_temp_data"] = "value"

async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
    ctx.data.pop("_my_temp_data", None)  # Clean up
```

## Next Steps

- [Tools & Agents](tools.md) — Build agent capabilities
- [Observability](observability.md) — Monitor your pipelines
- [Custom Interceptors](../advanced/custom-interceptors.md) — Advanced patterns
