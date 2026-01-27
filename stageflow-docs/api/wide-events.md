# Wide Events API Reference

This document provides the API reference for Stageflow's wide events system, which enables pipeline-level and stage-level event emission for comprehensive observability.

## Overview

Wide events provide a high-level view of pipeline execution, emitting summary events that capture the overall state and performance of pipeline runs and individual stage executions.

## WideEventEmitter

```python
from stageflow.observability import WideEventEmitter
```

Core class for emitting wide events during pipeline execution.

### Constructor

```python
WideEventEmitter(event_sink: EventSink | None = None)
```

**Parameters:**
- `event_sink`: Optional event sink for emitting events (uses global sink if None)

### Methods

#### `emit_stage_wide(stage_name: str, result: StageResult, ctx: PipelineContext) -> None`

Emit a stage-wide summary event.

**Parameters:**
- `stage_name`: Name of the stage
- `result`: Stage execution result
- `ctx`: Pipeline execution context

**Example:**
```python
emitter = WideEventEmitter()
emitter.emit_stage_wide("llm_stage", result, ctx)
```

#### `emit_pipeline_wide(results: dict[str, StageResult], ctx: PipelineContext) -> None`

Emit a pipeline-wide summary event.

**Parameters:**
- `results`: Dictionary of stage results
- `ctx`: Pipeline execution context

**Example:**
```python
emitter = WideEventEmitter()
emitter.emit_pipeline_wide(results, ctx)
```

---

## emit_stage_wide()

```python
from stageflow.observability import emit_stage_wide
```

Convenience function to emit a stage-wide event.

### Function Signature

```python
def emit_stage_wide(
    stage_name: str,
    result: StageResult,
    ctx: PipelineContext,
    event_sink: EventSink | None = None
) -> None
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `stage_name` | `str` | Name of the stage |
| `result` | `StageResult` | Stage execution result |
| `ctx` | `PipelineContext` | Pipeline execution context |
| `event_sink` | `EventSink \| None` | Optional event sink |

### Example Usage

```python
from stageflow.observability import emit_stage_wide

# In a stage or interceptor
emit_stage_wide("my_stage", result, ctx)
```

---

## emit_pipeline_wide()

```python
from stageflow.observability import emit_pipeline_wide
```

Convenience function to emit a pipeline-wide event.

### Function Signature

```python
def emit_pipeline_wide(
    results: dict[str, StageResult],
    ctx: PipelineContext,
    event_sink: EventSink | None = None
) -> None
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `results` | `dict[str, StageResult]` | Dictionary of stage results |
| `ctx` | `PipelineContext` | Pipeline execution context |
| `event_sink` | `EventSink \| None` | Optional event sink |

### Example Usage

```python
from stageflow.observability import emit_pipeline_wide

# After pipeline execution
emit_pipeline_wide(results, ctx)
```

---

## Event Schemas

### stage.wide Event

Emitted when a stage completes or fails.

**Event Type:** `stage.wide`

**Schema:**
```json
{
  "stage_name": "string",
  "status": "OK|SKIP|CANCEL|FAIL|RETRY",
  "duration_ms": "number",
  "started_at": "ISO datetime",
  "ended_at": "ISO datetime",
  "error": "string|null",
  "data_keys": ["string"],
  "artifacts_count": "number",
  "events_count": "number",
  "correlation_ids": {
    "pipeline_run_id": "string|null",
    "request_id": "string|null",
    "session_id": "string|null",
    "user_id": "string|null",
    "org_id": "string|null"
  },
  "pipeline_metadata": {
    "service": "string",
    "topology": "string",
    "execution_mode": "string"
  }
}
```

**Example:**
```json
{
  "stage_name": "llm_stage",
  "status": "OK",
  "duration_ms": 1500,
  "started_at": "2023-01-01T10:00:00Z",
  "ended_at": "2023-01-01T10:00:01.5Z",
  "error": null,
  "data_keys": ["response", "tokens_used"],
  "artifacts_count": 1,
  "events_count": 3,
  "correlation_ids": {
    "pipeline_run_id": "550e8400-e29b-41d4-a716-446655440000",
    "request_id": "550e8400-e29b-41d4-a716-446655440001",
    "session_id": "550e8400-e29b-41d4-a716-446655440002",
    "user_id": "550e8400-e29b-41d4-a716-446655440003",
    "org_id": "550e8400-e29b-41d4-a716-446655440004"
  },
  "pipeline_metadata": {
    "service": "chat",
    "topology": "fast_kernel",
    "execution_mode": "practice"
  }
}
```

### pipeline.wide Event

Emitted when a pipeline completes or fails.

**Event Type:** `pipeline.wide`

**Schema:**
```json
{
  "status": "OK|FAIL",
  "duration_ms": "number",
  "started_at": "ISO datetime",
  "ended_at": "ISO datetime",
  "stages_total": "number",
  "stages_completed": "number",
  "stages_failed": "number",
  "stages_skipped": "number",
  "stages_cancelled": "number",
  "error": "string|null",
  "stage_summaries": [
    {
      "stage_name": "string",
      "status": "string",
      "duration_ms": "number",
      "error": "string|null"
    }
  ],
  "correlation_ids": {
    "pipeline_run_id": "string|null",
    "request_id": "string|null",
    "session_id": "string|null",
    "user_id": "string|null",
    "org_id": "string|null"
  },
  "pipeline_metadata": {
    "service": "string",
    "topology": "string",
    "execution_mode": "string"
  }
}
```

**Example:**
```json
{
  "status": "OK",
  "duration_ms": 5000,
  "started_at": "2023-01-01T10:00:00Z",
  "ended_at": "2023-01-01T10:00:05Z",
  "stages_total": 3,
  "stages_completed": 3,
  "stages_failed": 0,
  "stages_skipped": 0,
  "stages_cancelled": 0,
  "error": null,
  "stage_summaries": [
    {
      "stage_name": "input_stage",
      "status": "OK",
      "duration_ms": 100,
      "error": null
    },
    {
      "stage_name": "llm_stage",
      "status": "OK",
      "duration_ms": 1500,
      "error": null
    },
    {
      "stage_name": "output_stage",
      "status": "OK",
      "duration_ms": 200,
      "error": null
    }
  ],
  "correlation_ids": {
    "pipeline_run_id": "550e8400-e29b-41d4-a716-446655440000",
    "request_id": "550e8400-e29b-41d4-a716-446655440001",
    "session_id": "550e8400-e29b-41d4-a716-446655440002",
    "user_id": "550e8400-e29b-41d4-a716-446655440003",
    "org_id": "550e8400-e29b-41d4-a716-446655440004"
  },
  "pipeline_metadata": {
    "service": "chat",
    "topology": "fast_kernel",
    "execution_mode": "practice"
  }
}
```

---

## Integration with Pipeline Execution

### Enabling Wide Events in StageGraph

```python
from stageflow import Pipeline
from stageflow.observability import WideEventEmitter

# Create pipeline with wide events enabled
pipeline = Pipeline().with_stage("stage1", Stage1, StageKind.TRANSFORM)

# Build with wide events
graph = pipeline.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=WideEventEmitter()
)

# Run pipeline - wide events will be emitted automatically
results = await graph.run(ctx)
```

### Custom Wide Event Emitter

```python
from stageflow.observability import WideEventEmitter, EventSink

class CustomWideEventEmitter(WideEventEmitter):
    def emit_stage_wide(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        # Add custom logic before emitting
        if result.status == StageStatus.FAIL:
            self._log_failure(stage_name, result.error)
        
        # Call parent implementation
        super().emit_stage_wide(stage_name, result, ctx)
    
    def _log_failure(self, stage_name: str, error: str | None) -> None:
        print(f"Stage {stage_name} failed: {error}")

# Use custom emitter
emitter = CustomWideEventEmitter()
graph = pipeline.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=emitter
)
```

### Integration with Event Sinks

```python
from stageflow.observability import WideEventEmitter
from stageflow.events import LoggingEventSink

# Create event sink
event_sink = LoggingEventSink()

# Create emitter with custom sink
emitter = WideEventEmitter(event_sink=event_sink)

# Use in pipeline
graph = pipeline.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=emitter
)
```

---

## Usage Examples

### Basic Wide Events Setup

```python
from stageflow import Pipeline, StageKind
from stageflow.observability import WideEventEmitter

# Define stages
class InputStage:
    name = "input"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx):
        return StageOutput.ok(text="processed input")

class LLMStage:
    name = "llm"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx):
        # Access upstream stage output
        input_text = ctx.inputs.get_from("input", "text")
        response = f"LLM response to: {input_text}"
        return StageOutput.ok(response=response)

# Build pipeline with wide events
pipeline = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("llm", LLMStage, StageKind.TRANSFORM, dependencies=("input",))
)

# Enable wide events
emitter = WideEventEmitter()
graph = pipeline.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=emitter
)

# Run - wide events will be emitted to the configured event sink
results = await graph.run(ctx)
```

### Custom Event Processing

```python
from stageflow.observability import WideEventEmitter
from stageflow.events import EventSink
import json

class AnalyticsEventSink(EventSink):
    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        if type in ["stage.wide", "pipeline.wide"]:
            # Send to analytics system
            await self.send_to_analytics(type, data)
    
    async def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        try:
            await self.emit(type=type, data=data)
        except Exception:
            # Log but don't raise
            print(f"Failed to emit {type} event")
    
    async def send_to_analytics(self, event_type: str, data: dict) -> None:
        # Custom analytics integration
        print(f"Analytics: {event_type} - {json.dumps(data, indent=2)}")

# Use with wide events
analytics_sink = AnalyticsEventSink()
emitter = WideEventEmitter(event_sink=analytics_sink)

graph = pipeline.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=emitter
)
```

### Performance Monitoring

```python
from stageflow.observability import WideEventEmitter
import time

class PerformanceMonitoringEmitter(WideEventEmitter):
    def __init__(self, slow_threshold_ms: int = 1000, **kwargs):
        super().__init__(**kwargs)
        self.slow_threshold_ms = slow_threshold_ms
    
    def emit_stage_wide(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        # Check for slow stages
        if result.duration_ms > self.slow_threshold_ms:
            self._alert_slow_stage(stage_name, result.duration_ms)
        
        super().emit_stage_wide(stage_name, result, ctx)
    
    def _alert_slow_stage(self, stage_name: str, duration_ms: int) -> None:
        print(f"ALERT: Stage {stage_name} took {duration_ms}ms (threshold: {self.slow_threshold_ms}ms)")

# Use for performance monitoring
monitor = PerformanceMonitoringEmitter(slow_threshold_ms=2000)
graph = pipeline.build(
    emit_stage_wide_events=True,
    wide_event_emitter=monitor
)
```

### Error Tracking

```python
from stageflow.observability import WideEventEmitter
from collections import defaultdict

class ErrorTrackingEmitter(WideEventEmitter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.error_counts = defaultdict(int)
        self.error_details = []
    
    def emit_stage_wide(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        if result.status == StageStatus.FAIL:
            self.error_counts[stage_name] += 1
            self.error_details.append({
                "stage": stage_name,
                "error": result.error,
                "timestamp": time.time(),
                "run_id": str(ctx.pipeline_run_id)
            })
        
        super().emit_stage_wide(stage_name, result, ctx)
    
    def get_error_summary(self) -> dict:
        return {
            "total_errors": sum(self.error_counts.values()),
            "errors_by_stage": dict(self.error_counts),
            "recent_errors": self.error_details[-10:]  # Last 10 errors
        }

# Use for error tracking
tracker = ErrorTrackingEmitter()
graph = pipeline.build(
    emit_stage_wide_events=True,
    wide_event_emitter=tracker
)

# After execution, check error summary
results = await graph.run(ctx)
error_summary = tracker.get_error_summary()
print(f"Errors: {error_summary}")
```

---

## Best Practices

1. **Enable in production** - Wide events provide valuable observability with minimal overhead
2. **Use appropriate event sinks** - Route events to your monitoring/analytics systems
3. **Monitor event volume** - Wide events are less frequent than detailed events but still consider volume
4. **Correlate with other events** - Use correlation IDs to link wide events with detailed telemetry
5. **Customize for your needs** - Extend WideEventEmitter for domain-specific event processing
6. **Handle failures gracefully** - Ensure event emission doesn't break pipeline execution
7. **Use for alerting** - Set up alerts based on wide event patterns (slow stages, high failure rates)
8. **Archive for analysis** - Store wide events for historical analysis and debugging

---

## Performance Considerations

- **Event Emission Overhead**: Minimal impact, typically <1ms per event
- **Memory Usage**: Events are emitted immediately, no large buffers
- **Network I/O**: Depends on event sink implementation
- **Correlation ID Propagation**: Uses existing context data, no additional computation

---

## Event Sink Integration

Wide events work with any EventSink implementation:

- **LoggingEventSink**: Logs events for debugging
- **NoOpEventSink**: Discards events (useful for testing)
- **Custom Sinks**: Send to monitoring systems, databases, or analytics platforms

Example custom sink:
```python
from datetime import datetime, timezone
from stageflow.events import EventSink

class DatabaseEventSink(EventSink):
    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        await self.db.insert("events", {
            "type": type,
            "data": json.dumps(data),
            "timestamp": datetime.now(timezone.utc)
        })
```
