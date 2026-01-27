# Protocols API Reference

This document provides the API reference for stageflow protocol definitions.

## Overview

Stageflow uses protocols (interfaces) to define extension points that allow the framework to be extended without modifying core code. Following the Dependency Inversion Principle, high-level modules depend on these abstractions, not on concrete implementations.

## ExecutionContext

```python
from stageflow.protocols import ExecutionContext
```

Common interface for all execution contexts. Both `PipelineContext` and `StageContext` implement this protocol, enabling tools and other components to work with either context type.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `pipeline_run_id` | `UUID \| None` | Pipeline run identifier for correlation |
| `request_id` | `UUID \| None` | Request identifier for tracing |
| `execution_mode` | `str \| None` | Current execution mode (e.g., 'practice', 'roleplay') |

### Methods

#### `to_dict() -> dict[str, Any]`

Convert context to dictionary for serialization.

#### `try_emit_event(type: str, data: dict[str, Any]) -> None`

Emit an event without blocking (fire-and-forget). This method should not raise exceptions.

### Example

```python
from stageflow.protocols import ExecutionContext

def process(ctx: ExecutionContext) -> None:
    """Works with both PipelineContext and StageContext."""
    print(f"Run: {ctx.pipeline_run_id}")
    print(f"Mode: {ctx.execution_mode}")
    ctx.try_emit_event("custom.event", {"key": "value"})
```

### Streaming Telemetry Helpers

Because both `PipelineContext` and `StageContext` implement `ExecutionContext`, you can wire streaming helpers and analytics exporters the same way regardless of where you are in the pipeline:

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer, BufferedExporter

def build_streaming_helpers(ctx: ExecutionContext):
    queue = ChunkQueue(event_emitter=ctx.try_emit_event)
    buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)

    exporter = BufferedExporter(
        sink=my_sink,
        on_overflow=lambda dropped, size: ctx.try_emit_event(
            "analytics.overflow",
            {"dropped": dropped, "buffer_size": size},
        ),
        high_water_mark=0.8,
    )
    return queue, buffer, exporter
```

Emitted telemetry events include `stream.chunk_dropped`, `stream.producer_blocked`, `stream.throttle_started`, `stream.throttle_ended`, `stream.queue_closed`, `stream.buffer_overflow`, `stream.buffer_underrun`, and `stream.buffer_recovered`.

---

## EventSink

```python
from stageflow.protocols import EventSink
# or
from stageflow import EventSink
```

Protocol for event persistence/emission. Implementations handle where events go—database, message queue, logging system, or discarded (NoOp).

### Methods

#### `emit(*, type: str, data: dict | None) -> None`

Emit an event asynchronously.

#### `try_emit(*, type: str, data: dict | None) -> None`

Emit an event without blocking (fire-and-forget). Should not raise exceptions.

### Example

```python
class DatabaseEventSink:
    def __init__(self, db):
        self.db = db
    
    async def emit(self, *, type: str, data: dict | None) -> None:
        await self.db.insert("events", {"type": type, "data": data})
    
    def try_emit(self, *, type: str, data: dict | None) -> None:
        import asyncio
        asyncio.create_task(self.emit(type=type, data=data))
```

---

## RunStore

```python
from stageflow.protocols import RunStore
# or
from stageflow import RunStore
```

Protocol for pipeline run persistence. Implementations handle how pipeline runs are stored and retrieved.

### Methods

#### `create_run(run_id, *, service, topology=None, execution_mode=None, status="created", **metadata) -> Any`

Create a new pipeline run record.

**Parameters:**
- `run_id`: `UUID` — Unique identifier for the run
- `service`: `str` — Service name (e.g., "voice", "chat")
- `topology`: `str | None` — Pipeline topology name
- `execution_mode`: `str | None` — Execution mode
- `status`: `str` — Initial status (default: "created")
- `**metadata` — Additional metadata

#### `update_status(run_id, status, *, error=None, duration_ms=None, **data) -> None`

Update a pipeline run's status.

**Parameters:**
- `run_id`: `UUID` — Run identifier
- `status`: `str` — New status
- `error`: `str | None` — Error message if failed
- `duration_ms`: `int | None` — Total duration in milliseconds

#### `get_run(run_id) -> Any | None`

Retrieve a pipeline run by ID.

### Example

```python
class PostgresRunStore:
    def __init__(self, db):
        self.db = db
    
    async def create_run(self, run_id, *, service, topology=None, **metadata):
        return await self.db.insert("pipeline_runs", {
            "id": run_id,
            "service": service,
            "topology": topology,
            **metadata,
        })
    
    async def update_status(self, run_id, status, *, error=None, duration_ms=None, **data):
        await self.db.update("pipeline_runs", run_id, {
            "status": status,
            "error": error,
            "duration_ms": duration_ms,
            **data,
        })
    
    async def get_run(self, run_id):
        return await self.db.get("pipeline_runs", run_id)
```

---

## ConfigProvider

```python
from stageflow.protocols import ConfigProvider
# or
from stageflow import ConfigProvider
```

Protocol for configuration access. Implementations provide configuration values from environment, files, databases, or other sources.

### Methods

#### `get(key: str, default=None) -> Any`

Get a configuration value.

### Example

```python
import os

class EnvConfigProvider:
    def get(self, key: str, default=None):
        return os.environ.get(key, default)

class DictConfigProvider:
    def __init__(self, config: dict):
        self._config = config
    
    def get(self, key: str, default=None):
        return self._config.get(key, default)
```

---

## CorrelationIds

```python
from stageflow.protocols import CorrelationIds
# or
from stageflow import CorrelationIds
```

Frozen dataclass for distributed tracing correlation IDs. These IDs are propagated through the pipeline to correlate logs, traces, and events across services.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `run_id` | `UUID \| None` | Pipeline run identifier |
| `request_id` | `UUID \| None` | HTTP/WS request identifier |
| `trace_id` | `str \| None` | Distributed tracing ID (e.g., OpenTelemetry) |
| `session_id` | `UUID \| None` | User session identifier |
| `user_id` | `UUID \| None` | User identifier |
| `org_id` | `UUID \| None` | Organization/tenant identifier |
| `extra` | `dict[str, Any]` | Extension point for app-specific IDs |

### Methods

#### `to_dict() -> dict[str, Any]`

Convert to dictionary for logging/serialization.

### Example

```python
from uuid import uuid4
from stageflow import CorrelationIds

ids = CorrelationIds(
    run_id=uuid4(),
    request_id=uuid4(),
    trace_id="abc123def456",
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),
    extra={"interaction_id": str(uuid4())},
)

# Use in logging
logger.info("Processing request", extra=ids.to_dict())
```

---

## Usage Example

```python
from uuid import uuid4
from stageflow import (
    EventSink,
    RunStore,
    ConfigProvider,
    CorrelationIds,
)
from stageflow.protocols import ExecutionContext

# Custom implementations
class MyEventSink:
    async def emit(self, *, type: str, data: dict | None) -> None:
        print(f"Event: {type} - {data}")
    
    def try_emit(self, *, type: str, data: dict | None) -> None:
        import asyncio
        asyncio.create_task(self.emit(type=type, data=data))

class MyRunStore:
    def __init__(self):
        self._runs = {}
    
    async def create_run(self, run_id, *, service, **metadata):
        self._runs[run_id] = {"service": service, "status": "created", **metadata}
        return self._runs[run_id]
    
    async def update_status(self, run_id, status, **data):
        if run_id in self._runs:
            self._runs[run_id]["status"] = status
            self._runs[run_id].update(data)
    
    async def get_run(self, run_id):
        return self._runs.get(run_id)

class MyConfigProvider:
    def __init__(self, config: dict):
        self._config = config
    
    def get(self, key: str, default=None):
        return self._config.get(key, default)

# Using correlation IDs
ids = CorrelationIds(
    run_id=uuid4(),
    request_id=uuid4(),
    user_id=uuid4(),
)

# Function that accepts any ExecutionContext
def log_context(ctx: ExecutionContext) -> None:
    ctx.try_emit_event("debug.context_logged", ctx.to_dict())
```
