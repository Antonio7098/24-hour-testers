# Observability API Reference

This document provides the API reference for observability protocols and utilities.

## PipelineRunLogger Protocol

```python
from stageflow.observability import PipelineRunLogger
```

Protocol for logging pipeline runs.

### Methods

#### `log_run_started(...) -> None`

Log pipeline run start.

**Parameters:**
- `pipeline_run_id`: `UUID` — Run identifier
- `pipeline_name`: `str` — Pipeline name
- `topology`: `str | None` — Topology name
- `execution_mode`: `str | None` — Execution mode
- `user_id`: `UUID | None` — User identifier
- `**kwargs` — Additional metadata

#### `log_run_completed(...) -> None`

Log pipeline run completion.

**Parameters:**
- `pipeline_run_id`: `UUID` — Run identifier
- `pipeline_name`: `str` — Pipeline name
- `duration_ms`: `int` — Total duration
- `status`: `str` — Final status
- `stage_results`: `dict` — Stage results
- `**kwargs` — Additional metadata

#### `log_run_failed(...) -> None`

Log pipeline run failure.

**Parameters:**
- `pipeline_run_id`: `UUID` — Run identifier
- `pipeline_name`: `str` — Pipeline name
- `error`: `str` — Error message
- `stage`: `str | None` — Failed stage name
- `**kwargs` — Additional metadata

---

## ProviderCallLogger Protocol

```python
from stageflow.observability import ProviderCallLogger
```

Protocol for logging external provider API calls.

### Methods

#### `log_call_start(...) -> UUID`

Log provider call start.

**Parameters:**
- `operation`: `str` — Operation type (e.g., "chat", "stt")
- `provider`: `str` — Provider name (e.g., "openai", "groq")
- `model_id`: `str | None` — Model identifier
- `**context` — Additional context

**Returns:** Call ID for correlation

#### `log_call_end(call_id, ...) -> None`

Log provider call completion.

**Parameters:**
- `call_id`: `UUID` — Call identifier from `log_call_start`
- `success`: `bool` — Whether call succeeded
- `latency_ms`: `int` — Call duration
- `error`: `str | None` — Error message if failed
- `**metrics` — Additional metrics (tokens, etc.)

---

## CircuitBreaker Protocol

```python
from stageflow.observability import CircuitBreaker, CircuitBreakerOpenError
```

Protocol for circuit breaker pattern.

### Methods

#### `is_open(*, operation: str, provider: str) -> bool`

Check if circuit is open.

#### `record_success(*, operation: str, provider: str) -> None`

Record successful call.

#### `record_failure(*, operation: str, provider: str, reason: str) -> None`

Record failed call.

### CircuitBreakerOpenError

Raised when circuit breaker is open.

**Attributes:**
- `operation`: `str` — Operation type
- `provider`: `str` — Provider name

---

## Utility Functions

### summarize_pipeline_error

```python
from stageflow.observability import summarize_pipeline_error

summary = summarize_pipeline_error(exception)
# {
#     "code": "TIMEOUT",
#     "type": "TimeoutError",
#     "message": "Stage timed out...",
#     "retryable": True,
# }
```

Summarize a pipeline error for logging.

### error_summary_to_string

```python
from stageflow.observability import error_summary_to_string

error_str = error_summary_to_string(summary)
# "TIMEOUT: Stage timed out..."
```

Convert error summary to string.

### error_summary_to_stages_patch

```python
from stageflow.observability import error_summary_to_stages_patch

patch = error_summary_to_stages_patch(summary)
# {"failure": {"error": {...}}}
```

Convert error summary to stages patch format.

### get_circuit_breaker

```python
from stageflow.observability import get_circuit_breaker

breaker = get_circuit_breaker()
```

Get the configured circuit breaker (returns NoOp by default).

---

## No-Op Implementations

### NoOpPipelineRunLogger

```python
from stageflow.observability import NoOpPipelineRunLogger

logger = NoOpPipelineRunLogger()
```

No-op logger for testing.

### NoOpProviderCallLogger

```python
from stageflow.observability import NoOpProviderCallLogger

logger = NoOpProviderCallLogger()
```

No-op provider call logger.

---

## Usage Example

```python
from uuid import uuid4
from stageflow.observability import (
    PipelineRunLogger,
    ProviderCallLogger,
    CircuitBreaker,
    CircuitBreakerOpenError,
    summarize_pipeline_error,
    get_circuit_breaker,
)

# Custom pipeline run logger
class MyPipelineRunLogger:
    def __init__(self, db):
        self.db = db
    
    async def log_run_started(self, *, pipeline_run_id, pipeline_name, **kwargs):
        await self.db.insert("runs", {
            "id": pipeline_run_id,
            "name": pipeline_name,
            "status": "running",
            **kwargs,
        })
    
    async def log_run_completed(self, *, pipeline_run_id, duration_ms, status, **kwargs):
        await self.db.update("runs", pipeline_run_id, {
            "status": status,
            "duration_ms": duration_ms,
        })
    
    async def log_run_failed(self, *, pipeline_run_id, error, stage, **kwargs):
        await self.db.update("runs", pipeline_run_id, {
            "status": "failed",
            "error": error,
            "failed_stage": stage,
        })

# Custom provider call logger
class MyProviderCallLogger:
    async def log_call_start(self, *, operation, provider, model_id, **context):
        call_id = uuid4()
        print(f"Starting {operation} on {provider}/{model_id}")
        return call_id
    
    async def log_call_end(self, call_id, *, success, latency_ms, error=None, **metrics):
        status = "success" if success else f"failed: {error}"
        print(f"Call {call_id} {status} in {latency_ms}ms")

# Using circuit breaker
breaker = get_circuit_breaker()

async def call_provider():
    if await breaker.is_open(operation="chat", provider="openai"):
        raise CircuitBreakerOpenError("chat", "openai")
    
    try:
        result = await openai_client.chat(...)
        await breaker.record_success(operation="chat", provider="openai")
        return result
    except Exception as e:
        await breaker.record_failure(operation="chat", provider="openai", reason=str(e))
        raise

# Error summarization
try:
    results = await graph.run(ctx)
except Exception as e:
    summary = summarize_pipeline_error(e)
    print(f"Pipeline failed: {summary['code']} - {summary['message']}")
    if summary['retryable']:
        print("This error is retryable")
```

---

## Analytics Exporters

### BufferedExporter

Batch analytics events and provide backpressure/overflow signaling.

```python
from stageflow.helpers import BufferedExporter, ConsoleExporter

def on_overflow(dropped_count: int, buffer_size: int) -> None:
    # dropped_count == -1 indicates a high-water warning
    logger.warning("analytics_overflow", extra={"dropped": dropped_count, "buffer": buffer_size})

exporter = BufferedExporter(
    ConsoleExporter(),
    on_overflow=on_overflow,
    high_water_mark=0.8,
)

# Optional runtime stats
stats = exporter.stats  # {"queued": int, "dropped": int, "flushes": int, ...}
```

Parameters:
- `on_overflow`: `(int dropped_count, int buffer_size) -> None` callback invoked on drop or high-water warning
- `high_water_mark`: `float` between 0 and 1 indicating warning threshold

---

## Distributed Tracing

### StageflowTracer

```python
from stageflow.observability import StageflowTracer, OTEL_AVAILABLE
```

Tracer wrapper that works with or without OpenTelemetry. Provides a consistent API for creating spans and propagating trace context.

**Constructor:**
```python
StageflowTracer(name: str = "stageflow")
```

**Key Methods:**

#### `start_span(name: str, *, kind=None, attributes=None) -> ContextManager`

Start a new span for tracing.

**Parameters:**
- `name`: Span name
- `kind`: Span kind (server, client, etc.)
- `attributes`: Initial span attributes

**Example:**
```python
tracer = StageflowTracer("my_service")

with tracer.start_span("process_request") as span:
    span.set_attribute("user_id", str(user_id))
    result = await process()
    span.set_attribute("result_size", len(result))
```

#### `inject_context(carrier: dict[str, str]) -> None`

Inject current trace context into a carrier (e.g., HTTP headers).

#### `extract_context(carrier: dict[str, str]) -> TraceContext`

Extract trace context from a carrier.

---

### TraceContext

```python
from stageflow.observability import TraceContext
```

Container for trace context that can be propagated across async boundaries.

**Constructor:**
```python
TraceContext(
    trace_id: str | None = None,
    span_id: str | None = None,
    correlation_id: UUID | None = None,
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    org_id: UUID | None = None,
    baggage: dict[str, str] = {}
)
```

**Key Methods:**

#### `capture() -> TraceContext`

Capture the current trace context from contextvars.

#### `activate() -> ContextManager`

Activate this trace context in the current context.

**Example:**
```python
# Capture context
ctx = TraceContext.capture()

# Pass to another task/service
async def worker(trace_ctx: TraceContext):
    with trace_ctx.activate():
        # All operations here have the same trace context
        await do_work()
```

#### `to_headers() -> dict[str, str]`

Convert to HTTP headers for propagation.

#### `from_headers(headers: dict[str, str]) -> TraceContext`

Create TraceContext from HTTP headers.

---

### Correlation ID Management

```python
from stageflow.observability import (
    set_correlation_id,
    get_correlation_id,
    ensure_correlation_id,
    clear_correlation_id,
    get_trace_context_dict
)
```

Functions for managing correlation IDs across async boundaries.

**Example:**
```python
from uuid import uuid4

# Set correlation ID
set_correlation_id(uuid4())

# Get current correlation ID
current = get_correlation_id()

# Ensure correlation ID exists (creates if not set)
cid = ensure_correlation_id()

# Get all trace context as dict
context = get_trace_context_dict()
# {
#     "trace_id": "...",
#     "span_id": "...",
#     "correlation_id": "...",
# }

# Clear correlation ID
clear_correlation_id()
```

---

### OpenTelemetry Integration

The tracing module integrates with OpenTelemetry when available:

```python
# Check if OpenTelemetry is available
from stageflow.observability import OTEL_AVAILABLE

if OTEL_AVAILABLE:
    # Full tracing with OpenTelemetry
    tracer = StageflowTracer("my_service")
    with tracer.start_span("operation") as span:
        # Span is recorded in OpenTelemetry backend
        pass
else:
    # No-op tracing - still maintains correlation IDs
    tracer = StageflowTracer("my_service")
    with tracer.start_span("operation") as span:
        # Span is no-op but correlation IDs still work
        pass
```

---

## Streaming Telemetry Events

Streaming primitives emit events to your configured sink when provided an `event_emitter`.

Emitted event types include:
- `stream.chunk_dropped` — Queue dropped a chunk (overflow/full)
- `stream.producer_blocked` — Producer blocked waiting for capacity
- `stream.throttle_started`, `stream.throttle_ended` — Backpressure window
- `stream.queue_closed` — Queue closed with final stats
- `stream.buffer_overflow` — Buffer dropped audio/data during overflow
- `stream.buffer_underrun`, `stream.buffer_recovered` — Underrun and subsequent recovery

Usage:

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer

queue = ChunkQueue(event_emitter=ctx.try_emit_event)
buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)
```
