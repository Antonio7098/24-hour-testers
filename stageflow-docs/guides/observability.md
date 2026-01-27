# Observability

Stageflow is built with observability as a first-class concern. This guide covers how to monitor, debug, and trace your pipelines.

## Philosophy

> "If it's not logged, traced, and replayable, it didn't happen."

Every stage execution, tool invocation, and pipeline run produces structured events that can be:
- **Logged** for debugging
- **Traced** for distributed tracing
- **Stored** for replay and analysis
- **Streamed** to monitoring systems

## Event System

### EventSink Protocol

All events flow through an `EventSink`:

```python
from stageflow import EventSink

class EventSink(Protocol):
    async def emit(self, *, type: str, data: dict) -> None:
        """Emit an event asynchronously."""
        ...
    
    def try_emit(self, *, type: str, data: dict) -> None:
        """Emit an event without blocking (fire-and-forget)."""
        ...
```

### Built-in Sinks

```python
from stageflow import (
    NoOpEventSink,           # Discards all events
    LoggingEventSink,        # Logs events via Python logging
    BackpressureAwareEventSink, # Bounded queue with backpressure
    set_event_sink,
    get_event_sink,
)

# Use logging sink (default)
set_event_sink(LoggingEventSink())

# Use backpressure-aware sink for production
sink = BackpressureAwareEventSink(
    downstream=LoggingEventSink(),
    max_queue_size=1000,
    on_drop=lambda type, data: print(f"Dropped: {type}")
)
await sink.start()
set_event_sink(sink)

# Get current sink
sink = get_event_sink()
```

### Backpressure-Aware Event Sink

For production workloads, use `BackpressureAwareEventSink` to prevent memory exhaustion:

```python
from stageflow import BackpressureAwareEventSink, LoggingEventSink

# Create sink with 1000 event buffer
sink = BackpressureAwareEventSink(
    downstream=LoggingEventSink(),
    max_queue_size=1000,
    on_drop=lambda type, data: print(f"Event dropped: {type}")
)

await sink.start()

# Monitor metrics
metrics = sink.metrics
print(f"Emitted: {metrics.emitted}")
print(f"Dropped: {metrics.dropped}")
print(f"Drop rate: {metrics.drop_rate}%")

# Graceful shutdown
await sink.stop(drain=True)
```

### 4. Monitor Event Sinks

Use production-grade sinks (Kafka, Pub/Sub, OTLP) for critical telemetry. Default sinks (`NoOpEventSink`, `LoggingEventSink`) are fire-and-forget; combine them with streaming telemetry events and buffered exporters to avoid silent drops.
```

### Custom Event Sink

```python
from datetime import datetime, timezone

class DatabaseEventSink:
    """Store events in a database."""
    
    def __init__(self, db):
        self.db = db
    
    async def emit(self, *, type: str, data: dict) -> None:
        await self.db.insert("pipeline_events", {
            "type": type,
            "data": data,
            "timestamp": datetime.now(timezone.utc),
        })
    
    def try_emit(self, *, type: str, data: dict) -> None:
        # Fire-and-forget
        asyncio.create_task(self.emit(type=type, data=data))

# Register
set_event_sink(DatabaseEventSink(db=my_database))
```

## Event Types

### Stage Events

| Event | Description |
|-------|-------------|
| `stage.{name}.started` | Stage began execution |
| `stage.{name}.completed` | Stage finished successfully |
| `stage.{name}.failed` | Stage failed with error |

Example event data:
```python
{
    "type": "stage.llm.completed",
    "data": {
        "stage": "llm",
        "status": "completed",
        "timestamp": "2024-01-15T10:30:00Z",
        "topology": "chat_fast",
        "execution_mode": "practice",
        "duration_ms": 1250,
        "pipeline_run_id": "...",
        "request_id": "...",
        "user_id": "...",
    }
}
```

### Tool Events

| Event | Description |
|-------|-------------|
| `tool.invoked` | Tool execution requested |
| `tool.started` | Tool execution began |
| `tool.completed` | Tool executed successfully |
| `tool.failed` | Tool execution failed |
| `tool.denied` | Tool denied (behavior gating) |
| `tool.undone` | Tool action was undone |
| `tool.undo_failed` | Undo operation failed |

### Streaming Events

Streaming helpers emit their own telemetry via `ChunkQueue` and `StreamingBuffer`:

| Event | Description |
|-------|-------------|
| `stream.chunk_dropped` | Queue dropped a chunk (overflow, full queue) |
| `stream.producer_blocked` | Producer blocked waiting for capacity |
| `stream.throttle_started` / `stream.throttle_ended` | Backpressure window |
| `stream.buffer_overflow` | Buffer dropped audio during overflow |
| `stream.buffer_underrun` / `stream.buffer_recovered` | Underrun + recovery |
| `stream.queue_closed` | Queue closed with final stats |

Attach emitters when creating queues/buffers:

```python
queue = ChunkQueue(event_emitter=ctx.emit_event)
buffer = StreamingBuffer(event_emitter=ctx.emit_event)
```

#### Pipeline Events

| Event | Description |
|-------|-------------|
| `pipeline.started` | Pipeline run began |
| `pipeline.completed` | Pipeline finished successfully |
| `pipeline.failed` | Pipeline failed |
| `pipeline.cancelled` | Pipeline was cancelled |

### Custom Events

Emit custom events from stages:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Emit custom event
    ctx.emit_event("custom.processing_started", {
        "step": "validation",
        "input_size": len(ctx.snapshot.input_text or ""),
    })
    
    # Do work...
    
    ctx.emit_event("custom.processing_completed", {
        "step": "validation",
        "result": "passed",
    })
    
    return StageOutput.ok(...)
```

### Wide Events (opt-in)

Use wide events when you want a single, denormalized record per stage or per pipeline run.

```python
from stageflow.observability import WideEventEmitter
from stageflow.pipeline.dag import StageGraph, StageSpec

emitter = WideEventEmitter()

graph = StageGraph(
    specs=[StageSpec(name="llm", runner=LLMStage)],
    wide_event_emitter=emitter,
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
)
```

If you build graphs via `PipelineBuilder`, pass the flags through `build()`:

```python
graph = builder.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=WideEventEmitter(),
)
```

Each stage completion/failure will emit `stage.wide` payloads with correlation IDs and summarized stage data, and the pipeline run will emit a single `pipeline.wide` summary once execution finishes. You can also call the helpers directly inside `PipelineRunLogger` implementations:

```python
from stageflow.observability import emit_pipeline_wide_event

class MyPipelineRunLogger(PipelineRunLogger):
    async def log_run_completed(..., stage_results, **_):
        emit_pipeline_wide_event(
            ctx=ctx,
            stage_results=stage_results,
            extra={"customer_id": str(ctx.user_id)},
        )
```

## Distributed Tracing

### Correlation ID Propagation

Stageflow automatically propagates correlation IDs across async boundaries:

```python
from stageflow.observability import (
    set_correlation_id,
    get_correlation_id,
    ensure_correlation_id,
    TraceContext
)

# Set correlation ID at request start
set_correlation_id(uuid4())

# Correlation ID survives across async boundaries
async def process_request():
    cid = get_correlation_id()  # Available here
    
    # Pass to child tasks
    ctx = TraceContext.capture()
    await asyncio.create_task(worker(ctx))

async def worker(trace_ctx: TraceContext):
    with trace_ctx.activate():
        cid = get_correlation_id()  # Same correlation ID
        # Do work...
```

### OpenTelemetry Integration

When OpenTelemetry is available, Stageflow provides full distributed tracing:

```python
from stageflow.observability import StageflowTracer, OTEL_AVAILABLE

if OTEL_AVAILABLE:
    tracer = StageflowTracer("my_service")
    
    with tracer.start_span("process_request") as span:
        span.set_attribute("user_id", str(user_id))
        
        with tracer.start_span("database_query") as db_span:
            db_span.set_attribute("table", "users")
            results = await db.query()
        
        span.set_attribute("result_count", len(results))
```

### Trace Context Propagation

Propagate trace context across service boundaries:

```python
from stageflow.observability import TraceContext

# Capture current context
ctx = TraceContext.capture()

# Convert to HTTP headers for outbound request
headers = ctx.to_headers()
# headers = {
#     "traceparent": "00-abc123-def456-01",
#     "x-correlation-id": "550e8400-e29b-41d4-a716-446655440000",
# }

# Extract context from inbound request
received_ctx = TraceContext.from_headers(headers)

# Activate context for processing
with received_ctx.activate():
    # All operations here have the same trace context
    await process_request()
```

### Multi-Tenant Tracing

Include tenant information in traces for multi-tenant applications:

```python
from stageflow.observability import StageflowTracer
from stageflow.auth import TenantContext

tenant_ctx = TenantContext(org_id=org_id)
tracer = StageflowTracer("tenant_service")

with tracer.start_span("tenant_operation") as span:
    span.set_attribute("org_id", str(tenant_ctx.org_id))
    span.set_attribute("tenant", tenant_ctx.metadata.get("tenant_name"))
    
    # Tenant-aware logging
    logger = tenant_ctx.get_logger("tenant_service")
    logger.info("Processing tenant request")
```

## Logging

### Structured Logging

Stageflow uses Python's logging module with structured data:

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

# Stageflow loggers
logger = logging.getLogger("stageflow")
logger = logging.getLogger("pipeline_dag")
logger = logging.getLogger("stage_interceptor")
logger = logging.getLogger("stage_metrics")
```

### Log Output

Stage execution produces logs like:

```
2024-01-15 10:30:00 - stage_interceptor - INFO - Stage starting: llm
2024-01-15 10:30:01 - stage_interceptor - INFO - Stage completed: llm - completed
2024-01-15 10:30:01 - stage_metrics - INFO - Stage metrics: llm
```

### JSON Logging

For production, use JSON logging:

```python
import json
import logging

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        return json.dumps(log_data)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.getLogger().addHandler(handler)
```

## Metrics

### ChildTrackerMetricsInterceptor

The built-in `ChildTrackerMetricsInterceptor` records subpipeline orchestration metrics:

```python
from stageflow import ChildTrackerMetricsInterceptor

# Automatically included in default interceptors
# Logs metrics for ChildRunTracker operations
```

**Metrics tracked**:
- Registration/unregistration counts
- Lookup operations (get_children, get_parent)
- Tree traversal operations
- Cleanup operations
- Maximum concurrent children seen
- Maximum nesting depth seen
- Active parent/child relationships

**Output format**:
```json
{
  "component": "ChildRunTracker",
  "pipeline_run_id": "...",
  "is_child_run": true,
  "registration_count": 15,
  "unregistration_count": 12,
  "lookup_count": 45,
  "tree_traversal_count": 8,
  "cleanup_count": 12,
  "max_concurrent_children": 5,
  "max_depth_seen": 3,
  "active_parents": 3,
  "active_children": 3,
  "total_relationships": 3
}
```

### Direct access to metrics
```python
from stageflow.pipeline.subpipeline import get_child_tracker

tracker = get_child_tracker()
metrics = await tracker.get_metrics()

# Reset counters if needed
await tracker.reset_metrics()
```

### MetricsInterceptor

The built-in `MetricsInterceptor` records:
- Stage duration
- Success/failure status
- Pipeline run correlation

```python
from stageflow import MetricsInterceptor

metrics = MetricsInterceptor()
# Automatically included in default interceptors
```

### Custom Metrics

Integrate with your metrics system:

```python
from stageflow import BaseInterceptor
from your_metrics import counter, histogram

class PrometheusMetricsInterceptor(BaseInterceptor):
    name = "prometheus_metrics"
    priority = 40
    
    async def before(self, stage_name: str, ctx) -> None:
        counter("stage_started_total", labels={"stage": stage_name}).inc()
    
    async def after(self, stage_name: str, result, ctx) -> None:
        duration_ms = (result.ended_at - result.started_at).total_seconds() * 1000
        
        histogram("stage_duration_seconds", labels={"stage": stage_name}).observe(duration_ms / 1000)
        counter("stage_completed_total", labels={
            "stage": stage_name,
            "status": result.status,
        }).inc()
```

## Tracing

### TracingInterceptor

The built-in `TracingInterceptor` creates span context:

```python
from stageflow import TracingInterceptor

tracing = TracingInterceptor()
# Stores span context in ctx.data for downstream use
```

### OpenTelemetry Integration

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from stageflow import BaseInterceptor

tracer = trace.get_tracer(__name__)

class OpenTelemetryInterceptor(BaseInterceptor):
    name = "opentelemetry"
    priority = 20
    
    async def before(self, stage_name: str, ctx) -> None:
        span = tracer.start_span(
            f"stage.{stage_name}",
            kind=SpanKind.INTERNAL,
            attributes={
                "stage.name": stage_name,
                "pipeline.run_id": str(ctx.pipeline_run_id),
                "pipeline.topology": ctx.topology,
            },
        )
        ctx.data[f"_otel_span.{stage_name}"] = span
    
    async def after(self, stage_name: str, result, ctx) -> None:
        span = ctx.data.pop(f"_otel_span.{stage_name}", None)
        if span:
            span.set_attribute("stage.status", result.status)
            span.set_attribute("stage.duration_ms", 
                (result.ended_at - result.started_at).total_seconds() * 1000)
            span.end()
```

## Pipeline Run Logging

### PipelineRunLogger Protocol

```python
from stageflow.observability import PipelineRunLogger

class PipelineRunLogger(Protocol):
    async def log_run_started(
        self,
        *,
        pipeline_run_id: UUID,
        pipeline_name: str,
        topology: str | None,
        execution_mode: str | None,
        user_id: UUID | None,
        **kwargs,
    ) -> None: ...

    async def log_run_completed(
        self,
        *,
        pipeline_run_id: UUID,
        pipeline_name: str,
        duration_ms: int,
        status: str,
        stage_results: dict,
        **kwargs,
    ) -> None: ...

    async def log_run_failed(
        self,
        *,
        pipeline_run_id: UUID,
        pipeline_name: str,
        error: str,
        stage: str | None,
        **kwargs,
    ) -> None: ...
```

### Implementation Example

```python
from datetime import datetime, timezone

class DatabasePipelineRunLogger:
    def __init__(self, db):
        self.db = db
    
    async def log_run_started(self, *, pipeline_run_id, pipeline_name, **kwargs):
        await self.db.insert("pipeline_runs", {
            "id": pipeline_run_id,
            "pipeline_name": pipeline_name,
            "status": "running",
            "started_at": datetime.now(timezone.utc),
            **kwargs,
        })
    
    async def log_run_completed(self, *, pipeline_run_id, duration_ms, status, **kwargs):
        await self.db.update("pipeline_runs", pipeline_run_id, {
            "status": status,
            "duration_ms": duration_ms,
            "completed_at": datetime.now(timezone.utc),
        })
    
    async def log_run_failed(self, *, pipeline_run_id, error, stage, **kwargs):
        await self.db.update("pipeline_runs", pipeline_run_id, {
            "status": "failed",
            "error": error,
            "failed_stage": stage,
            "failed_at": datetime.now(timezone.utc),
        })
```

## Provider Call Logging

Track external API calls (LLM, STT, TTS):

```python
from stageflow.observability import ProviderCallLogger

class ProviderCallLogger(Protocol):
    async def log_call_start(
        self,
        *,
        operation: str,
        provider: str,
        model_id: str | None,
        **context,
    ) -> UUID: ...

    async def log_call_end(
        self,
        call_id: UUID,
        *,
        success: bool,
        latency_ms: int,
        error: str | None = None,
        **metrics,
    ) -> None: ...
```

### Usage in Stages

```python
from stageflow.observability import provider_call_logger

class LLMStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Log call start
        call_id = await provider_call_logger.log_call_start(
            operation="chat",
            provider="openai",
            model_id="gpt-4",
            pipeline_run_id=ctx.pipeline_run_id,
        )
        
        start = time.time()
        try:
            response = await self.llm_client.chat(...)
            
            # Log success
            await provider_call_logger.log_call_end(
                call_id,
                success=True,
                latency_ms=int((time.time() - start) * 1000),
                tokens_used=response.usage.total_tokens,
            )
            
            return StageOutput.ok(response=response.content)
        except Exception as e:
            # Log failure
            await provider_call_logger.log_call_end(
                call_id,
                success=False,
                latency_ms=int((time.time() - start) * 1000),
                error=str(e),
            )
            raise
```

## Circuit Breaker

Prevent cascading failures:

```python
from stageflow.observability import CircuitBreaker, CircuitBreakerOpenError

class CircuitBreaker(Protocol):
    async def is_open(self, *, operation: str, provider: str) -> bool: ...
    async def record_success(self, *, operation: str, provider: str) -> None: ...
    async def record_failure(self, *, operation: str, provider: str, reason: str) -> None: ...

# Usage
breaker = get_circuit_breaker()

if await breaker.is_open(operation="chat", provider="openai"):
    raise CircuitBreakerOpenError("chat", "openai")

try:
    result = await call_provider()
    await breaker.record_success(operation="chat", provider="openai")
except Exception as e:
    await breaker.record_failure(operation="chat", provider="openai", reason=str(e))
    raise
```

## Error Summarization

Summarize errors for logging:

```python
from stageflow.observability import (
    summarize_pipeline_error,
    error_summary_to_string,
)

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
    
    error_str = error_summary_to_string(summary)
    # "TIMEOUT: Stage timed out after 30000ms"
```

## Correlation IDs

Track requests across services:

```python
from stageflow import CorrelationIds

ids = CorrelationIds(
    run_id=uuid4(),
    request_id=uuid4(),
    trace_id="abc123",
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),
    extra={"interaction_id": str(interaction_id)},
)

# Convert to dict for logging
log_data = ids.to_dict()
# {
#     "pipeline_run_id": "...",
#     "request_id": "...",
#     "trace_id": "abc123",
#     "session_id": "...",
#     "user_id": "...",
#     "org_id": "...",
#     "interaction_id": "...",
# }
```

## Debugging Tips

### 1. Enable Debug Logging

```python
import logging
logging.getLogger("stageflow").setLevel(logging.DEBUG)
logging.getLogger("pipeline_dag").setLevel(logging.DEBUG)
```

### 2. Use the Logging Event Sink

```python
from stageflow import set_event_sink, LoggingEventSink

set_event_sink(LoggingEventSink())
# All events will be logged
```

### 3. Inspect Stage Results

```python
results = await graph.run(ctx)

for name, output in results.items():
    print(f"Stage: {name}")
    print(f"  Status: {output.status}")
    print(f"  Data: {output.data}")
    if output.error:
        print(f"  Error: {output.error}")
```

### 4. Check Interceptor Observations

```python
# After execution, check context data for interceptor info
print(ctx.data.get("_interceptor.metrics"))
print(ctx.data.get("_interceptor.tracing"))
```

## Best Practices

### 1. Always Include Correlation IDs

```python
ctx.emit_event("custom.event", {
    "pipeline_run_id": str(ctx.pipeline_run_id),
    "request_id": str(ctx.request_id),
    "user_id": str(ctx.snapshot.user_id),
    # ... your data
})
```

### 2. Log at Appropriate Levels

- **DEBUG**: Detailed diagnostic information
- **INFO**: General operational events
- **WARNING**: Unexpected but handled situations
- **ERROR**: Failures that need attention

### 3. Structure Your Logs

Use structured logging with consistent fields:

```python
logger.info(
    "Stage completed",
    extra={
        "stage": stage_name,
        "status": "completed",
        "duration_ms": duration,
        "pipeline_run_id": str(ctx.pipeline_run_id),
    },
)
```

### 4. Monitor Key Metrics

Track these metrics for pipeline health:
- Stage duration (p50, p95, p99)
- Success/failure rates
- Error types and frequencies
- Provider call latencies

## Next Steps

- [Authentication](authentication.md) — Secure your pipelines
- [Error Handling](../advanced/errors.md) — Handle failures gracefully
- [Testing](../advanced/testing.md) — Test your observability setup
