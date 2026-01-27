# Custom Interceptors

This guide covers building custom interceptors for cross-cutting concerns.

## Interceptor Basics

Interceptors wrap stage execution to add functionality without modifying stages:

```
Request → [Your Interceptor] → [Other Interceptors] → Stage
                                                        ↓
Response ← [Your Interceptor] ← [Other Interceptors] ← Stage
```

## Creating an Interceptor

### Basic Structure

```python
from stageflow import BaseInterceptor, InterceptorResult, ErrorAction
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

class MyInterceptor(BaseInterceptor):
    name = "my_interceptor"
    priority = 30  # Lower = runs first (outer wrapper)

    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        """Called before stage execution."""
        # Return None to continue
        # Return InterceptorResult(stage_ran=False, ...) to short-circuit
        return None

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        """Called after stage completes."""
        pass

    async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction:
        """Called when stage throws."""
        return ErrorAction.FAIL
```

### Priority Guidelines

| Priority Range | Use Case |
|----------------|----------|
| 1-10 | Security (auth, rate limiting) |
| 10-20 | Reliability (circuit breaker, timeout) |
| 20-40 | Observability (tracing, metrics) |
| 40-60 | Logging, auditing |

## Common Patterns

### Rate Limiting

```python
import time
from collections import defaultdict

class RateLimitInterceptor(BaseInterceptor):
    name = "rate_limit"
    priority = 15

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        user_id = str(ctx.user_id) if ctx.user_id else "anonymous"
        now = time.time()

        # Clean old requests
        cutoff = now - self.window_seconds
        self._requests[user_id] = [t for t in self._requests[user_id] if t > cutoff]

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
        pass
```

### Caching

```python
import hashlib
import json

class CachingInterceptor(BaseInterceptor):
    name = "caching"
    priority = 25

    def __init__(self, cache_stages: set[str] | None = None, ttl_seconds: int = 300):
        self.cache_stages = cache_stages or set()
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[StageResult, float]] = {}

    def _cache_key(self, stage_name: str, ctx: PipelineContext) -> str:
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
            cached_result, cached_at = self._cache[cache_key]
            if time.time() - cached_at < self.ttl_seconds:
                return InterceptorResult(
                    stage_ran=False,
                    result=cached_result.data,
                )

        ctx.data[f"_cache_key.{stage_name}"] = cache_key
        return None

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        cache_key = ctx.data.pop(f"_cache_key.{stage_name}", None)
        if cache_key and result.status == "completed":
            self._cache[cache_key] = (result, time.time())
```

### Retry with Backoff

```python
import asyncio
import random

class RetryInterceptor(BaseInterceptor):
    name = "retry"
    priority = 12

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._retry_counts: dict[str, int] = {}

    async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction:
        # Only retry transient errors
        if not self._is_retryable(error):
            return ErrorAction.FAIL

        key = f"{ctx.pipeline_run_id}:{stage_name}"
        self._retry_counts[key] = self._retry_counts.get(key, 0) + 1

        if self._retry_counts[key] > self.max_retries:
            del self._retry_counts[key]
            return ErrorAction.FAIL

        # Exponential backoff with jitter
        delay = self.base_delay * (2 ** (self._retry_counts[key] - 1))
        delay *= (0.5 + random.random())
        await asyncio.sleep(delay)

        return ErrorAction.RETRY

    def _is_retryable(self, error: Exception) -> bool:
        retryable_types = (TimeoutError, ConnectionError)
        return isinstance(error, retryable_types)

    async def before(self, stage_name: str, ctx: PipelineContext) -> None:
        pass

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        # Clear retry count on success
        key = f"{ctx.pipeline_run_id}:{stage_name}"
        self._retry_counts.pop(key, None)
```

### Request Logging

```python
import logging
from datetime import datetime, timezone

logger = logging.getLogger("request_logger")

class RequestLoggingInterceptor(BaseInterceptor):
    name = "request_logging"
    priority = 45

    async def before(self, stage_name: str, ctx: PipelineContext) -> None:
        ctx.data[f"_request_log.{stage_name}.start"] = datetime.now(timezone.utc)
        
        logger.info(
            f"Stage {stage_name} starting",
            extra={
                "stage": stage_name,
                "pipeline_run_id": str(ctx.pipeline_run_id),
                "user_id": str(ctx.user_id) if ctx.user_id else None,
                "topology": ctx.topology,
            },
        )

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        start = ctx.data.pop(f"_request_log.{stage_name}.start", None)
        duration_ms = 0
        if start:
            duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

        logger.info(
            f"Stage {stage_name} completed",
            extra={
                "stage": stage_name,
                "status": result.status,
                "duration_ms": duration_ms,
                "pipeline_run_id": str(ctx.pipeline_run_id),
            },
        )
```

### Streaming Telemetry & Analytics Hooks

Interceptors are a great place to wire telemetry emitters and analytics exporters so every stage shares the same observable pipeline:

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer, BufferedExporter

class StreamingTelemetryInterceptor(BaseInterceptor):
    name = "streaming_telemetry"
    priority = 35

    async def before(self, stage_name: str, ctx: PipelineContext) -> None:
        queue = ChunkQueue(event_emitter=ctx.try_emit_event)
        buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)

        exporter = BufferedExporter(
            sink=self._sink,
            on_overflow=lambda dropped, size: ctx.try_emit_event(
                "analytics.overflow",
                {"stage": stage_name, "dropped": dropped, "buffer_size": size},
            ),
            high_water_mark=0.8,
        )

        ctx.data["_stream_queue"] = queue
        ctx.data["_stream_buffer"] = buffer
        ctx.data["_analytics_exporter"] = exporter
```

This ensures stages emit standardized `stream.*` events (`stream.chunk_dropped`, `stream.producer_blocked`, `stream.buffer_overflow`, etc.) even if the stage itself is unaware of the helper classes.

### Feature Flags

```python
class FeatureFlagInterceptor(BaseInterceptor):
    name = "feature_flags"
    priority = 8

    def __init__(self, feature_service):
        self.feature_service = feature_service

    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        # Check if stage is enabled for this user/org
        feature_key = f"stage.{stage_name}.enabled"
        
        is_enabled = await self.feature_service.is_enabled(
            feature_key,
            user_id=ctx.user_id,
            org_id=ctx.org_id,
        )

        if not is_enabled:
            return InterceptorResult(
                stage_ran=False,
                result={"skipped": True, "reason": "Feature disabled"},
            )

        return None

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        pass
```

### Cost Tracking

```python
class CostTrackingInterceptor(BaseInterceptor):
    name = "cost_tracking"
    priority = 42

    def __init__(self, cost_service):
        self.cost_service = cost_service

    async def before(self, stage_name: str, ctx: PipelineContext) -> None:
        pass

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        # Extract cost-related data from result
        tokens_used = result.data.get("tokens_used", 0)
        model = result.data.get("model")

        if tokens_used and model:
            await self.cost_service.record_usage(
                user_id=ctx.user_id,
                org_id=ctx.org_id,
                stage=stage_name,
                model=model,
                tokens=tokens_used,
                pipeline_run_id=ctx.pipeline_run_id,
            )
```

## Short-Circuiting Execution

Return `InterceptorResult` with `stage_ran=False` to skip the stage:

```python
async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
    # Check condition
    if should_skip:
        return InterceptorResult(
            stage_ran=False,
            result={"cached": True, "data": cached_data},
            error=None,  # Not an error, just skipped
        )
    
    # Continue to stage
    return None
```

## Error Handling

Control error behavior with `ErrorAction`:

```python
async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction:
    if isinstance(error, TransientError):
        return ErrorAction.RETRY  # Retry the stage
    
    if isinstance(error, RecoverableError):
        return ErrorAction.FALLBACK  # Use fallback result
    
    return ErrorAction.FAIL  # Propagate failure
```

## Using Interceptor Context

Access context data safely:

```python
from stageflow import InterceptorContext

async def before(self, stage_name: str, ctx: PipelineContext) -> None:
    i_ctx = InterceptorContext(ctx, _interceptor_name=self.name)
    
    # Read-only access to data
    data = i_ctx.data  # Returns a copy
    
    # Access IDs
    run_id = i_ctx.pipeline_run_id
    user_id = i_ctx.user_id
    
    # Add observation for other interceptors
    i_ctx.add_observation("start_time", time.time())

async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
    i_ctx = InterceptorContext(ctx, _interceptor_name=self.name)
    
    # Retrieve observation
    start_time = i_ctx.get_observation("start_time")
```

## Registering Interceptors

### With Default Interceptors

```python
from stageflow import get_default_interceptors

interceptors = [
    MyInterceptor(),
    *get_default_interceptors(),
]
```

### With StageGraph

```python
from stageflow.pipeline.dag import StageGraph

graph = StageGraph(
    specs=pipeline.build().stage_specs,
    interceptors=interceptors,
)
```

## Testing Interceptors

```python
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_ctx():
    ctx = Mock()
    ctx.pipeline_run_id = uuid4()
    ctx.user_id = uuid4()
    ctx.data = {}
    return ctx

@pytest.mark.asyncio
async def test_rate_limit_allows_requests(mock_ctx):
    interceptor = RateLimitInterceptor(max_requests=10)
    
    # First request should pass
    result = await interceptor.before("test_stage", mock_ctx)
    assert result is None

@pytest.mark.asyncio
async def test_rate_limit_blocks_excess(mock_ctx):
    interceptor = RateLimitInterceptor(max_requests=2)
    
    # First two requests pass
    await interceptor.before("test_stage", mock_ctx)
    await interceptor.before("test_stage", mock_ctx)
    
    # Third request blocked
    result = await interceptor.before("test_stage", mock_ctx)
    assert result is not None
    assert result.stage_ran is False
```

## Best Practices

### 1. Keep Interceptors Focused

One interceptor, one concern:

```python
# Good
class LoggingInterceptor: ...
class MetricsInterceptor: ...
class AuthInterceptor: ...

# Bad
class DoEverythingInterceptor: ...
```

### 2. Handle Errors Gracefully

Don't let interceptor errors crash the pipeline:

```python
async def before(self, stage_name: str, ctx: PipelineContext) -> None:
    try:
        await self.risky_operation()
    except Exception as e:
        logger.warning(f"Interceptor error: {e}")
        # Don't re-raise - let stage continue
```

### 3. Clean Up in after()

Always clean up resources:

```python
async def before(self, stage_name: str, ctx: PipelineContext) -> None:
    ctx.data["_my_temp"] = "value"

async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
    ctx.data.pop("_my_temp", None)  # Clean up
```

### 4. Use Namespaced Keys

Avoid key collisions in context data:

```python
# Good
ctx.data["_my_interceptor.start_time"] = time.time()

# Bad
ctx.data["start_time"] = time.time()  # May conflict
```

## Next Steps

- [Error Handling](errors.md) — Handle failures gracefully
- [Testing Strategies](testing.md) — Test your interceptors
- [Extensions](extensions.md) — Add custom context data
