# Events API Reference

This document provides the API reference for the event system.

## EventSink Protocol

```python
from datetime import datetime, timezone
from stageflow import EventSink
```

Protocol for event persistence/emission.

### Methods

#### `emit(*, type: str, data: dict | None) -> None`

Emit an event asynchronously.

**Parameters:**
- `type`: `str` — Event type string (e.g., "stage.llm.completed")
- `data`: `dict | None` — Event payload data

#### `try_emit(*, type: str, data: dict | None) -> None`

Emit an event without blocking (fire-and-forget).

---

## Built-in Sinks

### NoOpEventSink

```python
from stageflow import NoOpEventSink
```

Discards all events. Useful for testing.

### LoggingEventSink

```python
from stageflow import LoggingEventSink
```

Logs events via Python's logging module.

### BackpressureAwareEventSink

```python
from stageflow import BackpressureAwareEventSink, BackpressureMetrics
```

Event sink with bounded queue and backpressure handling. Prevents memory exhaustion under load by dropping events when the queue is full.

**Key Features:**
- Bounded `asyncio.Queue` prevents unbounded memory growth
- `BackpressureMetrics` track emitted/dropped events
- Graceful shutdown with queue draining
- Configurable queue size and on-drop callbacks

**Example:**
```python
from stageflow import BackpressureAwareEventSink, LoggingEventSink

# Create sink with 1000 event buffer
sink = BackpressureAwareEventSink(
    downstream=LoggingEventSink(),
    max_queue_size=1000,
    on_drop=lambda type, data: print(f"Dropped event: {type}")
)

await sink.start()

# Use the sink
success = sink.try_emit(type="event.type", data={"key": "value"})
if not success:
    print("Event dropped due to backpressure")

# Check metrics
metrics = sink.metrics
print(f"Emitted: {metrics.emitted}, Dropped: {metrics.dropped}")
print(f"Drop rate: {metrics.drop_rate}%")

# Graceful shutdown
await sink.stop(drain=True)
```

---

## Event Management

### set_event_sink

```python
from stageflow import set_event_sink

set_event_sink(LoggingEventSink())
```

Set the global event sink.

### get_event_sink

```python
from stageflow import get_event_sink

sink = get_event_sink()
```

Get the current event sink.

### clear_event_sink

```python
from stageflow import clear_event_sink

clear_event_sink()
```

Reset to default (NoOp) sink.

### emit_event

```python
from stageflow.events import emit_event

await emit_event(type="custom.event", data={"key": "value"})
```

Emit an event through the current sink.

---

## Event Types

### Stage Events

| Event | Description |
|-------|-------------|
| `stage.{name}.started` | Stage began execution |
| `stage.{name}.completed` | Stage finished successfully |
| `stage.{name}.failed` | Stage failed with error |

**Example data:**
```python
{
    "stage": "llm",
    "status": "completed",
    "timestamp": "2024-01-15T10:30:00Z",
    "topology": "chat_fast",
    "execution_mode": "practice",
    "duration_ms": 1250,
    "pipeline_run_id": "...",
    "request_id": "...",
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

### Pipeline Events

| Event | Description |
|-------|-------------|
| `pipeline.started` | Pipeline run began |
| `pipeline.completed` | Pipeline finished |
| `pipeline.failed` | Pipeline failed |
| `pipeline.cancelled` | Pipeline was cancelled |

### Approval Events

| Event | Description |
|-------|-------------|
| `approval.requested` | Approval requested |
| `approval.decided` | Approval granted/denied |

### Subpipeline Events

| Event | Description |
|-------|-------------|
| `pipeline.spawned_child` | Child pipeline spawned from parent stage |
| `pipeline.child_completed` | Child pipeline completed successfully |
| `pipeline.child_failed` | Child pipeline failed with error |
| `pipeline.canceled` | Pipeline was canceled (with cascade depth) |

**Example subpipeline event data:**
```python
# pipeline.spawned_child
{
    "parent_run_id": "...",
    "child_run_id": "...",
    "parent_stage_id": "tool_executor",
    "pipeline_name": "tool_pipeline",
    "correlation_id": "...",
    "timestamp": "2024-01-15T10:30:00Z",
}
```

See [Subpipeline Runs](../advanced/subpipelines.md) for full event schemas.

---

## Custom Event Sink

```python
from stageflow import EventSink

class DatabaseEventSink:
    """Store events in a database."""
    
    def __init__(self, db):
        self.db = db
    
    async def emit(self, *, type: str, data: dict | None) -> None:
        await self.db.insert("events", {
            "type": type,
            "data": data,
            "timestamp": datetime.now(timezone.utc),
        })
    
    def try_emit(self, *, type: str, data: dict | None) -> None:
        import asyncio
        asyncio.create_task(self.emit(type=type, data=data))

# Use custom sink
from stageflow import set_event_sink
set_event_sink(DatabaseEventSink(db=my_db))
```

---

## Emitting Events from Stages

```python
from stageflow import StageContext, StageOutput

class MyStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Emit custom event
        ctx.try_emit_event("custom.processing_started", {
            "step": "validation",
            "input_size": len(ctx.snapshot.input_text or ""),
        })
        
        # Do work...
        
        ctx.try_emit_event("custom.processing_completed", {
            "step": "validation",
            "result": "passed",
        })
        
        return StageOutput.ok(...)
```

---

## Usage Example

```python
import asyncio
from stageflow import (
    set_event_sink,
    get_event_sink,
    clear_event_sink,
    LoggingEventSink,
)
from stageflow.events import emit_event

# Configure logging sink
set_event_sink(LoggingEventSink())

# Emit events
await emit_event(type="app.started", data={"version": "1.0"})

# Custom sink with filtering
class FilteredEventSink:
    def __init__(self, include_types: set[str]):
        self.include_types = include_types
    
    async def emit(self, *, type: str, data: dict | None) -> None:
        if any(type.startswith(t) for t in self.include_types):
            print(f"Event: {type} - {data}")
    
    def try_emit(self, *, type: str, data: dict | None) -> None:
        asyncio.create_task(self.emit(type=type, data=data))

# Only log stage and tool events
set_event_sink(FilteredEventSink(include_types={"stage.", "tool."}))

# Reset to default
clear_event_sink()
```

---

## Streaming Telemetry Events

When using streaming helpers with an `event_emitter`, events are emitted with correlation IDs:

- `stream.chunk_dropped` — Queue dropped a chunk due to overflow/full conditions
- `stream.producer_blocked` — Producer blocked waiting for queue capacity
- `stream.throttle_started`, `stream.throttle_ended` — Backpressure signaling
- `stream.queue_closed` — Queue closed with final stats
- `stream.buffer_overflow`, `stream.buffer_underrun`, `stream.buffer_recovered` — Buffer anomalies

Example wiring from stages:

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer

queue = ChunkQueue(event_emitter=ctx.try_emit_event)
buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)
```

---

## Tool Parsing and Resolution Events

If LLM responses include tool calls, prefer resolving them via `ToolRegistry.parse_and_resolve`. Emit an event for unresolved calls:

```python
resolved, unresolved = registry.parse_and_resolve(tool_calls)
for call in unresolved:
    ctx.try_emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})
```

Execution events (examples):
- `tool.invoked`, `tool.started`, `tool.completed`, `tool.failed`
- `tool.denied` (behavior gating), `tool.undone`, `tool.undo_failed`
