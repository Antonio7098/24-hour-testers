# Interceptors API Reference

This document provides the API reference for interceptor middleware.

## BaseInterceptor

```python
from stageflow import BaseInterceptor
```

Base class for stage interceptors.

### Class Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Interceptor name |
| `priority` | `int` | Execution order (lower = runs first) |

### Methods

#### `before(stage_name: str, ctx: PipelineContext) -> InterceptorResult | None`

Called before stage execution.

**Returns:** `None` to continue, or `InterceptorResult` to short-circuit

```python
async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
    if should_skip:
        return InterceptorResult(stage_ran=False, error="Skipped")
    return None
```

#### `after(stage_name: str, result: StageResult, ctx: PipelineContext) -> None`

Called after stage completes (success or failure).

```python
async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
    print(f"Stage {stage_name} completed with status {result.status}")
```

#### `on_error(stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction`

Called when stage throws an exception.

**Returns:** `ErrorAction` indicating how to handle the error

```python
async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction:
    if isinstance(error, TransientError):
        return ErrorAction.RETRY
    return ErrorAction.FAIL
```

---

## InterceptorResult

```python
from stageflow import InterceptorResult
```

Result from an interceptor's `before()` hook.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `stage_ran` | `bool` | Whether stage should run (default: True) |
| `result` | `Any` | Result to use if stage skipped |
| `error` | `str \| None` | Error message if skipped |

```python
# Short-circuit stage execution
return InterceptorResult(
    stage_ran=False,
    result={"cached": True},
    error="Using cached result",
)
```

---

## ErrorAction

```python
from stageflow import ErrorAction
```

Action to take when a stage errors.

### Values

| Value | Description |
|-------|-------------|
| `RETRY` | Retry stage with backoff |
| `FALLBACK` | Use fallback result |
| `FAIL` | Propagate failure to pipeline |

---

## InterceptorContext

```python
from stageflow import InterceptorContext
```

Read-only view of PipelineContext for interceptors.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Interceptor name |
| `data` | `dict` | Read-only copy of context data |
| `pipeline_run_id` | `UUID` | Pipeline run ID |
| `request_id` | `UUID` | Request ID |
| `session_id` | `UUID` | Session ID |
| `user_id` | `UUID` | User ID |
| `org_id` | `UUID` | Organization ID |
| `topology` | `str` | Pipeline topology |
| `execution_mode` | `str` | Execution mode |

### Methods

#### `add_observation(key: str, value: Any) -> None`

Add observation for other interceptors.

#### `get_observation(key: str) -> Any`

Get observation from previous interceptor.

---

## Built-in Interceptors

### TimeoutInterceptor

```python
from stageflow import TimeoutInterceptor
```

Enforces per-stage execution timeouts.

**Priority:** 5 (runs first)
**Default timeout:** 30 seconds

```python
# Override timeout via context
ctx.data["_timeout_ms"] = 60000  # 60 seconds
```

### CircuitBreakerInterceptor

```python
from stageflow import CircuitBreakerInterceptor
```

Prevents cascading failures.

**Priority:** 10
**Threshold:** 5 failures
**Reset timeout:** 30 seconds

### TracingInterceptor

```python
from stageflow import TracingInterceptor
```

Creates OpenTelemetry-compatible span context.

**Priority:** 20

### ChildTrackerMetricsInterceptor

```python
from stageflow import ChildTrackerMetricsInterceptor
```

Logs `ChildRunTracker` metrics for subpipeline orchestration observability.

**Priority:** 45

### MetricsInterceptor

```python
from stageflow import MetricsInterceptor
```

Records stage execution metrics.

**Priority:** 40

### LoggingInterceptor

```python
from stageflow import LoggingInterceptor
```

Provides structured JSON logging.

**Priority:** 50

---

## Telemetry & Provider Metadata

Interceptors often bridge observability gaps across all stages. Recommended patterns:

- Emit streaming telemetry events from shared helpers by wiring `ChunkQueue` / `StreamingBuffer` emitters to `ctx.try_emit_event` inside interceptors that manage audio chunks or realtime data.
- Ensure downstream analytics see standardized provider payloads (`LLMResponse`, `STTResponse`, `TTSResponse`) by validating that stage outputs include `llm`/`stt`/`tts` dictionaries (and enriching them if needed).
- For analytics exporters, configure `BufferedExporter` with an `on_overflow` callback to log or throttle when gauges exceed the high-water mark.

```python
from stageflow.helpers import ChunkQueue, BufferedExporter

queue = ChunkQueue(event_emitter=ctx.try_emit_event)

exporter = BufferedExporter(
    sink=my_sink,
    on_overflow=lambda dropped, size: ctx.try_emit_event(
        "analytics.overflow",
        {"dropped": dropped, "buffer_size": size},
    ),
    high_water_mark=0.75,
)
```

---

## Functions

### get_default_interceptors

```python
from stageflow import get_default_interceptors

interceptors = get_default_interceptors(include_auth=False)
```

Get the default set of interceptors.

**Parameters:**
- `include_auth`: `bool` — Include auth interceptors (default: False)

**Returns:** List of interceptors sorted by priority

### run_with_interceptors

```python
from stageflow import run_with_interceptors

result = await run_with_interceptors(
    stage_name="my_stage",
    stage_run=my_stage_callable,
    ctx=pipeline_context,
    interceptors=interceptors,
)
```

Execute a stage with interceptor wrapping.

---

## Auth Interceptors

### AuthInterceptor

```python
from stageflow.auth import AuthInterceptor
```

Validates JWT tokens and creates AuthContext.

**Priority:** 1

```python
from stageflow.auth import AuthInterceptor, MockJwtValidator

auth = AuthInterceptor(validator=MockJwtValidator())
```

### OrgEnforcementInterceptor

```python
from stageflow.auth import OrgEnforcementInterceptor
```

Ensures tenant isolation.

**Priority:** 2

---

## Creating Custom Interceptors

```python
from stageflow import BaseInterceptor, InterceptorResult, ErrorAction
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

class MyInterceptor(BaseInterceptor):
    name = "my_interceptor"
    priority = 30

    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        # Pre-execution logic
        ctx.data["_my_start_time"] = time.time()
        return None

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        # Post-execution logic
        start = ctx.data.pop("_my_start_time", None)
        if start:
            duration = time.time() - start
            print(f"Stage {stage_name} took {duration:.2f}s")

    async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction:
        # Error handling
        if isinstance(error, TimeoutError):
            return ErrorAction.RETRY
        return ErrorAction.FAIL
```

---

## Usage Example

```python
from stageflow import (
    BaseInterceptor,
    InterceptorResult,
    ErrorAction,
    get_default_interceptors,
    Pipeline,
    StageKind,
)

# Custom rate limiting interceptor
class RateLimitInterceptor(BaseInterceptor):
    name = "rate_limit"
    priority = 15
    
    def __init__(self, max_per_minute: int = 60):
        self.max_per_minute = max_per_minute
        self._counts = {}
    
    async def before(self, stage_name: str, ctx) -> InterceptorResult | None:
        user_id = str(ctx.user_id)
        count = self._counts.get(user_id, 0)
        
        if count >= self.max_per_minute:
            return InterceptorResult(
                stage_ran=False,
                error="Rate limit exceeded",
            )
        
        self._counts[user_id] = count + 1
        return None
    
    async def after(self, stage_name: str, result, ctx) -> None:
        pass

# Use custom interceptors
interceptors = [
    RateLimitInterceptor(max_per_minute=100),
    *get_default_interceptors(),
]

# Build pipeline with custom interceptors
from stageflow.pipeline.dag import StageGraph

pipeline = Pipeline().with_stage("my_stage", MyStage, StageKind.TRANSFORM)
graph = StageGraph(specs=pipeline.build().stage_specs, interceptors=interceptors)
```
