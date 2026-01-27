# Subpipeline Runs

This guide covers nested pipeline execution for complex workflows.

## Overview

Subpipelines allow a stage to spawn a child pipeline run. This is useful for:

- **Tool execution** that requires its own pipeline topology
- **Delegation** to specialized agents
- **Complex operations** that need isolation

## How It Works

```
Parent Pipeline
┌─────────────────────────────────────────────────────────────┐
│  [stage_a] → [stage_b] → [tool_executor] → [stage_c]        │
│                               │                             │
│                               ▼                             │
│                    ┌─────────────────────┐                  │
│                    │  Child Pipeline     │                  │
│                    │  [parse] → [exec]   │                  │
│                    └─────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

## Forking Context

Use `PipelineContext.fork()` to create a child context:

```python
from uuid import uuid4
from stageflow.stages.context import PipelineContext

# Parent context
parent_ctx = PipelineContext(
    pipeline_run_id=uuid4(),
    request_id=uuid4(),
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),
    interaction_id=uuid4(),
    topology="parent_pipeline",
    execution_mode="default",
)

# Fork for child pipeline
child_ctx = parent_ctx.fork(
    child_run_id=uuid4(),
    parent_stage_id="tool_executor",
    correlation_id=uuid4(),
    topology="child_pipeline",  # Optional: different topology
    execution_mode="tool_mode",  # Optional: different mode
)
```

## Child Context Properties

The child context:

- Has its own `pipeline_run_id`
- References parent via `parent_run_id` and `parent_stage_id`
- Gets a **read-only snapshot** of parent data
- Inherits auth context (`user_id`, `org_id`, `session_id`)
- Has its own fresh `data` dict and `artifacts` list

```python
# Check if context is a child run
if child_ctx.is_child_run:
    print(f"Parent run: {child_ctx.parent_run_id}")
    print(f"Parent stage: {child_ctx.parent_stage_id}")
    print(f"Correlation: {child_ctx.correlation_id}")

# Access parent data (read-only)
parent_value = child_ctx.get_parent_data("some_key", default=None)
```

## Implementing Subpipeline Execution

### Stage That Spawns Subpipeline

```python
from uuid import uuid4
from stageflow import StageContext, StageKind, StageOutput, Pipeline

class ToolDispatcher(Stage):
    """Stage that executes tools via subpipelines."""
    
    name = "tool_dispatcher"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        tool_calls = ctx.inputs.get("tool_calls", [])
        
        results = []
        for call in tool_calls:
            # Create child pipeline for each tool call
            child_ctx = ctx.pipeline_ctx.fork_child(
                child_run_id=uuid4(),
                correlation_id=uuid4(),
                topology=f"tool_{call.type}",
                execution_mode="tool_execution",
            )
            
            # Execute child pipeline
            result = await self._run_child_pipeline(
                parent_ctx=ctx,
                child_run_id=child_run_id,
                correlation_id=correlation_id,
                pipeline=tool_pipeline,
                tool_call=tool_call,
            )
            results.append(result)
        
        return StageOutput.ok(tool_results=results)

    async def _run_child_pipeline(
        self,
        parent_ctx,
        child_run_id,
        correlation_id,
        pipeline,
        tool_call,
    ):
        # Build child graph
        graph = pipeline.build()
        
        # Create child context (simplified - actual implementation uses PipelineContext)
        child_snapshot = ContextSnapshot(
            pipeline_run_id=child_run_id,
            request_id=parent_ctx.snapshot.request_id,
            session_id=parent_ctx.snapshot.session_id,
            user_id=parent_ctx.snapshot.user_id,
            org_id=parent_ctx.snapshot.org_id,
            interaction_id=parent_ctx.snapshot.interaction_id,
            topology=f"tool_{tool_call.type}",
            execution_mode="tool_execution",
            input_text=str(tool_call.payload),
        )
        
        child_ctx = StageContext(snapshot=child_snapshot)
        
        # Run child pipeline
        try:
            results = await graph.run(child_ctx)
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

### What the `runner` Callable Must Do

`SubpipelineSpawner.spawn()` expects you to pass a coroutine function with the
signature `async def runner(child_ctx: PipelineContext) -> dict[str, Any]`.
This runner is responsible for:

1. Building or reusing the child pipeline graph.
2. Converting the provided `PipelineContext` into a `StageContext`.
3. Running the graph and returning a plain `dict` payload (the framework wraps
   it into `SubpipelineResult.data`).

`ToolExecutor.spawn_subpipeline()` wires this runner up automatically, so most
teams never have to construct it. If you implement your own orchestration layer,
use the same contract so the spawner can emit events, enforce depth limits, and
handle cancellations.

### Telemetry & Tool Resolution in Subpipelines

Subpipeline stages often orchestrate multiple tools. Standardize telemetry by resolving LLM-provided tool calls before spawning a child run and wiring streaming emitters through the child context:

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer

resolved, unresolved = self.registry.parse_and_resolve(tool_calls)
for call in unresolved:
    ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})

for call in resolved:
    child_ctx = ctx.pipeline_ctx.fork_child(
        child_run_id=uuid4(),
        correlation_id=call.call_id,
        topology=f"tool_{call.name}",
        execution_mode="tool_execution",
    )

    queue = ChunkQueue(event_emitter=child_ctx.try_emit_event)
    buffer = StreamingBuffer(event_emitter=child_ctx.try_emit_event)
    # Queue/buffer now emit `stream.*` events scoped to the child pipeline
```

Child pipelines should also propagate `LLMResponse` / `STTResponse` / `TTSResponse` payloads back to the parent via `StageOutput` so the parent can aggregate provider metrics.

## Correlation and Tracing

### Correlation IDs

Child runs maintain correlation with parent:

```python
# In events and logs
event_data = {
    "pipeline_run_id": str(child_ctx.pipeline_run_id),
    "parent_run_id": str(child_ctx.parent_run_id),
    "parent_stage_id": child_ctx.parent_stage_id,
    "correlation_id": str(child_ctx.correlation_id),
}
```

### Event Correlation

Events from child pipelines include parent references:

```python
# Child pipeline event
{
    "type": "stage.parse.completed",
    "data": {
        "pipeline_run_id": "child-uuid",
        "parent_run_id": "parent-uuid",
        "parent_stage_id": "tool_executor",
        "correlation_id": "action-uuid",
        ...
    }
}
```

## Observability and Metrics

### ChildRunTracker Metrics

The `ChildRunTracker` provides comprehensive metrics for subpipeline orchestration:

```python
from stageflow.pipeline.subpipeline import get_child_tracker

# Get current metrics
tracker = get_child_tracker()
metrics = await tracker.get_metrics()

print(f"Active children: {metrics['active_children']}")
print(f"Max depth seen: {metrics['max_depth_seen']}")
print(f"Total registrations: {metrics['registration_count']}")
```

### Automatic Metrics Logging

The `ChildTrackerMetricsInterceptor` automatically logs metrics for child pipeline runs:

```python
# Included in default interceptors
from stageflow import get_default_interceptors

interceptors = get_default_interceptors()
# Contains ChildTrackerMetricsInterceptor at priority 45
```

**Metrics logged**:
- Registration/unregistration counts
- Lookup operations (get_children, get_parent)
- Tree traversal operations
- Maximum concurrent children
- Maximum nesting depth
- Active relationships

### Streaming Telemetry Propagation

When a child pipeline processes audio or streaming chunks, pass the parent's event sink into the child so all `stream.*` events stay correlated:

```python
def _build_child_streaming_helpers(child_ctx):
    queue = ChunkQueue(event_emitter=child_ctx.try_emit_event)
    buffer = StreamingBuffer(event_emitter=child_ctx.try_emit_event)
    return queue, buffer
```

Combined with `BufferedExporter` (configured with `on_overflow`), this allows you to detect when subpipeline analytics fall behind and emit events such as `stream.chunk_dropped`, `stream.buffer_overflow`, and `analytics.overflow`.

### Performance Monitoring

Monitor subpipeline performance with the metrics:

```json
{
  "component": "ChildRunTracker",
  "pipeline_run_id": "123e4567-e89b-12d3-a456-426614174000",
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

Use these metrics to:
- Detect excessive subpipeline nesting
- Monitor cleanup efficiency
- Track lookup performance
- Identify memory usage patterns

## Error Handling

### Child Failures

Child failures bubble up to the parent:

```python
async def _run_child_pipeline(self, ...):
    try:
        results = await graph.run(child_ctx)
        return {"success": True, "results": results}
    except StageExecutionError as e:
        # Log with correlation
        logger.error(
            f"Child pipeline failed",
            extra={
                "parent_run_id": str(parent_ctx.pipeline_run_id),
                "child_run_id": str(child_run_id),
                "failed_stage": e.stage,
                "error": str(e.original),
            },
        )
        return {"success": False, "error": str(e), "stage": e.stage}
    except UnifiedPipelineCancelled as e:
        return {"success": False, "cancelled": True, "reason": e.reason}
```

### Cancellation Propagation

Parent cancellation should cascade to children:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Check for cancellation before spawning children
    if ctx.pipeline_ctx.canceled:
        return StageOutput.cancel(reason="Parent cancelled")
    
    # Track child tasks for cancellation
    child_tasks = []
    
    for tool_call in tool_calls:
        task = asyncio.create_task(self._run_child(tool_call))
        child_tasks.append(task)
    
    # Wait with cancellation support
    try:
        results = await asyncio.gather(*child_tasks)
    except asyncio.CancelledError:
        # Cancel all children
        for task in child_tasks:
            task.cancel()
        await asyncio.gather(*child_tasks, return_exceptions=True)
        raise
```

## Data Isolation

### Read-Only Parent Data

Children get a frozen snapshot of parent data:

```python
from stageflow.utils.frozen import FrozenDict

# In fork()
child_ctx = PipelineContext(
    ...
    _parent_data=FrozenDict(parent_ctx.data),  # Read-only copy
)

# In child stage
parent_value = ctx.get_parent_data("key")  # Safe read
# ctx.data is fresh dict for child's own outputs
```

### Output Isolation

Child outputs don't pollute parent context:

```python
# Child writes to its own data dict
child_ctx.data["child_result"] = "value"

# Parent data is unchanged
assert "child_result" not in parent_ctx.data

# Results returned explicitly
return {"child_output": child_ctx.data}
```

## Use Cases

### Tool Execution

```python
def create_tool_pipeline(tool_type: str) -> Pipeline:
    """Create pipeline for specific tool type."""
    if tool_type == "EDIT_DOCUMENT":
        return (
            Pipeline()
            .with_stage("parse", ParseEditStage, StageKind.TRANSFORM)
            .with_stage("validate", ValidateEditStage, StageKind.GUARD, dependencies=("parse",))
            .with_stage("execute", ExecuteEditStage, StageKind.WORK, dependencies=("validate",))
        )
    elif tool_type == "SEARCH":
        return (
            Pipeline()
            .with_stage("parse", ParseSearchStage, StageKind.TRANSFORM)
            .with_stage("search", SearchStage, StageKind.WORK, dependencies=("parse",))
            .with_stage("rank", RankResultsStage, StageKind.TRANSFORM, dependencies=("search",))
        )
    else:
        raise ValueError(f"Unknown tool type: {tool_type}")
```

### Agent Delegation

```python
class DelegatingAgentStage:
    """Agent that delegates to specialized sub-agents."""
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        intent = self._classify_intent(ctx.snapshot.input_text)
        
        if intent == "document_edit":
            # Delegate to document agent via subpipeline
            result = await self._delegate_to_agent(
                ctx,
                agent_pipeline="document_agent",
                context_enrichment={"document_id": self._extract_doc_id(ctx)},
            )
        elif intent == "code_review":
            result = await self._delegate_to_agent(
                ctx,
                agent_pipeline="code_review_agent",
            )
        else:
            # Handle directly
            result = await self._handle_directly(ctx)
        
        return StageOutput.ok(response=result)
```

## ToolExecutor.spawn_subpipeline API *(updated in 0.5.1)*

The simplest way to spawn a subpipeline from a tool is via `ToolExecutor.spawn_subpipeline()`:

```python
from stageflow.tools.executor import ToolExecutor

executor = ToolExecutor()

# Spawn a child pipeline
result = await executor.spawn_subpipeline(
    "validation_pipeline",  # Pipeline name from registry
    ctx,                    # Parent PipelineContext
    action.id,              # Correlation ID (typically action UUID)
    topology_override="fast_kernel",        # Optional
    execution_mode_override="strict",       # Optional
)

if result.success:
    validated_data = result.data
    print(f"Child {result.child_run_id} completed in {result.duration_ms}ms")
else:
    logger.error(f"Validation failed: {result.error}")
```

### Features

- **Pipeline lookup** from the global `PipelineRegistry`
- **Automatic graph building** and execution
- **Full observability** via `SubpipelineSpawner` events
- **Depth limit enforcement** (raises `MaxDepthExceededError`)
- **Cancellation propagation** via `ChildRunTracker`
- **Structured logging** with correlation IDs

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `pipeline_name` | `str` | Name of the registered pipeline to run |
| `ctx` | `PipelineContext` | Parent context (will be forked for child) |
| `correlation_id` | `UUID` | Action ID that triggered spawn (for tracing) |
| `topology_override` | `str \| None` | Optional different topology for child |
| `execution_mode_override` | `str \| None` | Optional different execution mode |

### Returns

`SubpipelineResult` with:
- `success`: Whether child completed successfully
- `child_run_id`: The child pipeline run UUID
- `data`: Output data from child stages
- `error`: Error message if failed
- `duration_ms`: Execution time

### Exceptions

- `KeyError`: Pipeline name not found in registry
- `MaxDepthExceededError`: Nesting depth limit exceeded

### Converting StageContext to PipelineContext

Stages are executed with immutable `StageContext` instances derived from the
mutable `PipelineContext` by the orchestrator. When a stage needs to call APIs
that expect the richer pipeline-level context (for example,
`ToolExecutor.spawn_subpipeline()`), use the helper:

```python
from stageflow.core import StageContext

async def execute(self, ctx: StageContext) -> StageOutput:
    pipeline_ctx = ctx.as_pipeline_context(
        topology_override="subpipeline_general",
        data={"invoked_by": ctx.stage_name},
    )

    result = await self.executor.spawn_subpipeline(
        pipeline_name="general_chat",
        ctx=pipeline_ctx,
        correlation_id=uuid4(),
    )

    return StageOutput.ok(child=result.data)
```

`StageContext.as_pipeline_context()` copies the identifiers (run, request,
session, etc.), topology, execution mode, and event sink from the snapshot so
that stages can safely bridge back to the orchestration context without having
to manually re-create the dataclass.

### Dependency Injection

For testing, inject custom spawner and registry:

```python
from stageflow.pipeline import PipelineRegistry, SubpipelineSpawner

# Create with custom dependencies
executor = ToolExecutor(
    spawner=mock_spawner,
    registry=mock_registry,
)
```

---

## SubpipelineSpawner API

```python
from stageflow.pipeline.subpipeline import (
    SubpipelineSpawner,
    get_subpipeline_spawner,
    set_subpipeline_spawner,
)
```

The `SubpipelineSpawner` handles spawning and managing child pipeline runs with proper correlation and cancellation support.

### Constructor

```python
spawner = SubpipelineSpawner(
    child_tracker=None,  # Optional custom tracker
    emit_events=True,    # Emit subpipeline events
    max_depth=5,         # Maximum nesting depth (default: 5)
)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `max_depth` | `int` | Maximum allowed subpipeline nesting depth |

### Methods

#### `spawn(pipeline_name, ctx, correlation_id, parent_stage_id, runner, *, topology=None, execution_mode=None) -> SubpipelineResult`

Spawn a child pipeline run.

```python
result = await spawner.spawn(
    pipeline_name="tool_execution",
    ctx=parent_ctx,
    correlation_id=action_id,
    parent_stage_id="tool_executor",
    runner=my_pipeline_runner,
    topology="tool_fast",
)
```

#### `cancel_with_children(run_id, reason="user_requested", contexts=None) -> list[UUID]`

Cancel a run and all its children (depth-first cascading).

```python
canceled_ids = await spawner.cancel_with_children(
    run_id=parent_run_id,
    reason="timeout",
    contexts=active_contexts,  # Optional: mark contexts as canceled
)
```

#### `is_canceled(run_id) -> bool`

Check if a run has been canceled.

### Depth Limiting

The spawner enforces a maximum nesting depth to prevent runaway recursion:

```python
from stageflow.pipeline.subpipeline import (
    SubpipelineSpawner,
    MaxDepthExceededError,
    DEFAULT_MAX_SUBPIPELINE_DEPTH,  # 5
)

# Custom depth limit
spawner = SubpipelineSpawner(max_depth=3)

try:
    result = await spawner.spawn(...)
except MaxDepthExceededError as e:
    print(f"Depth {e.current_depth} exceeds max {e.max_depth}")
    print(f"Parent run: {e.parent_run_id}")
```

### Global Instance

```python
# Get the global spawner
spawner = get_subpipeline_spawner()

# Set a custom spawner
set_subpipeline_spawner(my_spawner)
```

---

## ChildRunTracker API

```python
from stageflow.pipeline.subpipeline import (
    ChildRunTracker,
    get_child_tracker,
    set_child_tracker,
)
```

Thread-safe tracking of parent-child relationships for cancellation propagation.

### Methods

#### `register_child(parent_id, child_id) -> None`

Register a child run under a parent.

#### `unregister_child(parent_id, child_id) -> None`

Unregister a child run from its parent.

#### `get_children(parent_id) -> set[UUID]`

Get all child run IDs for a parent.

#### `get_parent(child_id) -> UUID | None`

Get the parent run ID for a child.

#### `get_all_descendants(run_id) -> set[UUID]`

Get all descendant run IDs (children, grandchildren, etc.).

#### `get_root_run(run_id) -> UUID`

Get the root run ID by traversing up the parent chain.

#### `cleanup_run(run_id) -> None`

Clean up tracking data for a completed run.

---

## SubpipelineResult

```python
from stageflow.pipeline.subpipeline import SubpipelineResult
```

Result from executing a subpipeline.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `success` | `bool` | Whether the child pipeline completed successfully |
| `child_run_id` | `UUID` | The child pipeline run ID |
| `data` | `dict \| None` | Output data from the child pipeline |
| `error` | `str \| None` | Error message if failed |
| `duration_ms` | `float` | Execution time in milliseconds |

```python
result = await spawner.spawn(...)
if result.success:
    print(f"Child {result.child_run_id} completed in {result.duration_ms}ms")
    print(f"Data: {result.data}")
else:
    print(f"Child failed: {result.error}")
```

---

## Subpipeline Events

```python
from stageflow.pipeline.subpipeline import (
    PipelineSpawnedChildEvent,
    PipelineChildCompletedEvent,
    PipelineChildFailedEvent,
    PipelineCanceledEvent,
)
```

### Event Types

| Event Type | Description |
|------------|-------------|
| `pipeline.spawned_child` | Emitted when a child pipeline is spawned |
| `pipeline.child_completed` | Emitted when a child pipeline completes successfully |
| `pipeline.child_failed` | Emitted when a child pipeline fails |
| `pipeline.canceled` | Emitted when a pipeline is canceled |

### PipelineSpawnedChildEvent

```python
{
    "parent_run_id": "uuid-string",
    "child_run_id": "uuid-string",
    "parent_stage_id": "tool_executor",
    "pipeline_name": "tool_pipeline",
    "correlation_id": "action-uuid",
    "timestamp": "2024-01-15T10:30:00Z",
}
```

### PipelineChildCompletedEvent

```python
{
    "parent_run_id": "uuid-string",
    "child_run_id": "uuid-string",
    "pipeline_name": "tool_pipeline",
    "duration_ms": 150.5,
    "timestamp": "2024-01-15T10:30:00Z",
}
```

### PipelineChildFailedEvent

```python
{
    "parent_run_id": "uuid-string",
    "child_run_id": "uuid-string",
    "pipeline_name": "tool_pipeline",
    "error_message": "Stage validation failed",
    "duration_ms": 50.2,
    "timestamp": "2024-01-15T10:30:00Z",
}
```

### PipelineCanceledEvent

```python
{
    "pipeline_run_id": "uuid-string",
    "parent_run_id": "uuid-string",  # null if root
    "reason": "user_requested",
    "cascade_depth": 0,  # 0 for root, 1 for child, etc.
    "timestamp": "2024-01-15T10:30:00Z",
}
```

---

## Best Practices

### 1. Limit Nesting Depth

Avoid deeply nested subpipelines:

```python
# Good: Single level of nesting
Parent → Child

# Avoid: Deep nesting
Parent → Child → Grandchild → Great-grandchild
```

### 2. Keep Children Focused

Each child pipeline should have a specific purpose:

```python
# Good: Focused child pipeline
edit_pipeline = Pipeline()
    .with_stage("parse", ParseStage, ...)
    .with_stage("execute", ExecuteStage, ...)

# Avoid: Kitchen-sink child pipeline
everything_pipeline = Pipeline()
    .with_stage("parse", ...)
    .with_stage("validate", ...)
    .with_stage("enrich", ...)
    .with_stage("execute", ...)
    .with_stage("notify", ...)
    .with_stage("audit", ...)
```

### 3. Propagate Correlation IDs

Always include correlation IDs in events and logs:

```python
logger.info(
    "Child pipeline started",
    extra={
        "parent_run_id": str(parent_run_id),
        "child_run_id": str(child_run_id),
        "correlation_id": str(correlation_id),
    },
)
```

### 4. Handle Timeouts

Set appropriate timeouts for child pipelines:

```python
async def _run_child_pipeline(self, ...):
    try:
        results = await asyncio.wait_for(
            graph.run(child_ctx),
            timeout=30.0,  # 30 second timeout
        )
        return {"success": True, "results": results}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Child pipeline timed out"}
```

## Next Steps

- [Custom Interceptors](custom-interceptors.md) — Build middleware for subpipelines
- [Error Handling](errors.md) — Handle subpipeline failures
- [Testing](testing.md) — Test subpipeline execution
