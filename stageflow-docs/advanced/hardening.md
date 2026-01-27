# Runtime Safety and Hardening

This guide covers advanced safety and observability features for production-grade pipelines.

## UUID Telemetry

### Collision Detection

```python
from stageflow.helpers.uuid_utils import UuidCollisionMonitor

monitor = UuidCollisionMonitor(
    ttl_seconds=300,
    category="pipeline",
    check_skew=True,
)

# Observe IDs during execution
monitor.observe(pipeline_run_id)
monitor.observe(correlation_id)
```

### UUIDv7 and Clock Skew

```python
from stageflow.helpers.uuid_utils import generate_uuid7

# Generate time-ordered UUIDv7 (falls back to UUIDv7 if uuid6 unavailable)
uid = generate_uuid7()
```

## Memory Growth Tracking

### PipelineRunner Integration

```python
from stageflow.helpers.run_utils import PipelineRunner

runner = PipelineRunner(
    enable_memory_tracker=True,
    memory_tracker_auto_start=True,
)
```

### Decorator for Functions

```python
from stageflow.helpers.memory_tracker import track_memory

@track_memory(label="heavy_stage")
async def heavy_computation():
    ...
```

## Deep Immutability Validation

> **Performance Warning:** This interceptor serializes the entire context before and after each stage. Use only during development or testing.

```python
from stageflow.helpers.run_utils import PipelineRunner

runner = PipelineRunner(
    enable_immutability_check=True,
)
```

## Context Size Monitoring

```python
from stageflow.helpers.run_utils import PipelineRunner

runner = PipelineRunner(
    enable_context_size_monitor=True,
    # Custom thresholds via ContextSizeInterceptor if needed
)
```

## Compression Utilities

### Delta Compression

```python
from stageflow.compression import compress, apply_delta

base = {"a": 1, "b": 2}
current = {"a": 1, "b": 3, "c": 4}
delta, metrics = compress(base, current)

rebuilt = apply_delta(base, delta)
assert rebuilt == current
```

### Metrics

```python
print(metrics.delta_bytes)
print(metrics.original_bytes)
print(metrics.compression_ratio)
```

## Hardening Interceptors

### ImmutabilityInterceptor

Detects if a stage mutates the input ContextSnapshot.

```python
from stageflow.pipeline.interceptors_hardening import ImmutabilityInterceptor

interceptor = ImmutabilityInterceptor(crash_on_violation=True)
```

### ContextSizeInterceptor

Monitors context payload size and growth.

```python
from stageflow.pipeline.interceptors_hardening import ContextSizeInterceptor

interceptor = ContextSizeInterceptor(
    max_size_bytes=1024 * 1024,  # 1MB warning
    warn_on_growth_bytes=100 * 1024,  # 100KB growth warning
)
```

## ToolExecutor Integration

```python
from stageflow.tools.executor import ToolExecutor
from stageflow.helpers.uuid_utils import UuidCollisionMonitor
from stageflow.helpers.memory_tracker import MemoryTracker

executor = ToolExecutor(
    uuid_monitor=UuidCollisionMonitor(category="tool"),
    memory_tracker=MemoryTracker(),
)
```

## Production Checklist

- Enable UUID monitoring in production to surface collision anomalies.
- Enable memory tracking to detect leaks during long-running sessions.
- Use context size monitoring to catch runaway payload growth.
- Enable immutability validation only during development/testing.
- Use compression utilities for large context snapshots when persisting or transmitting.
