# Pipeline API Reference

This document provides the API reference for pipeline building and execution.

## Pipeline

```python
from stageflow import Pipeline
```

Builder for composing stages into a pipeline DAG.

### Constructor

```python
Pipeline(stages: dict[str, UnifiedStageSpec] = None)
```

### Methods

#### `with_stage(name, runner, kind, dependencies=None, conditional=False) -> Pipeline`

Add a stage to the pipeline (fluent builder).

**Parameters:**
- `name`: `str` — Unique stage name within the pipeline
- `runner`: `type[Stage] | Stage` — Stage class or instance
- `kind`: `StageKind` — Stage categorization
- `dependencies`: `tuple[str, ...] | None` — Names of stages that must complete first
- `conditional`: `bool` — If True, stage may be skipped based on context

**Returns:** New `Pipeline` instance (immutable)

```python
pipeline = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("input",))
)
```

#### `compose(other: Pipeline) -> Pipeline`

Merge stages from another pipeline.

**Parameters:**
- `other`: `Pipeline` — Pipeline to merge

**Returns:** New `Pipeline` with merged stages

```python
base = Pipeline().with_stage("a", StageA, StageKind.TRANSFORM)
extension = Pipeline().with_stage("b", StageB, StageKind.TRANSFORM)
merged = base.compose(extension)
```

#### `build(*, emit_stage_wide_events=False, emit_pipeline_wide_event=False, wide_event_emitter=None) -> StageGraph`

Generate executable DAG for the orchestrator.

**Parameters:**
- `emit_stage_wide_events`: `bool` — When `True`, the resulting `StageGraph` emits `stage.wide` events after each stage completes/fails.
- `emit_pipeline_wide_event`: `bool` — When `True`, emits a single `pipeline.wide` event after the run.
- `wide_event_emitter`: `WideEventEmitter | None` — Optional shared emitter instance (auto-created when omitted but a custom emitter lets you integrate with your own sinks).

**Returns:** `StageGraph` ready for execution

**Raises:** `ValueError` if pipeline is empty or dependencies are invalid

```python
from stageflow.observability import WideEventEmitter

graph = pipeline.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=WideEventEmitter(),
)
results = await graph.run(ctx)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `stages` | `dict[str, UnifiedStageSpec]` | Mapping of stage name to spec |

---

## UnifiedStageSpec

```python
from stageflow import UnifiedStageSpec
```

Specification for a stage in the pipeline DAG.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Stage name |
| `runner` | `type[Stage] \| Stage` | Stage class or instance |
| `kind` | `StageKind` | Stage categorization |
| `dependencies` | `tuple[str, ...]` | Stage dependencies |
| `conditional` | `bool` | Whether stage can be skipped |

---

## StageGraph

```python
from stageflow import StageGraph
```

Dependency-driven DAG executor with parallel execution.

### Constructor

```python
StageGraph(
    specs: Iterable[StageSpec],
    interceptors: list[BaseInterceptor] | None = None,
    *,
    wide_event_emitter: WideEventEmitter | None = None,
    emit_stage_wide_events: bool = False,
    emit_pipeline_wide_event: bool = False,
)
```

### Methods

#### `run(ctx: StageContext) -> dict[str, StageOutput]`

Execute the DAG with the given context.

**Parameters:**
- `ctx`: `StageContext` — Execution context

**Returns:** Dict mapping stage name to `StageOutput`

**Raises:**
- `RuntimeError` — If deadlock detected
- `StageExecutionError` — If a stage fails

```python
results = await graph.run(ctx)
print(results["my_stage"].data)
```

### Provider Response & Telemetry Propagation

Encourage stages within the pipeline to emit standardized provider metadata and streaming telemetry so downstream consumers can rely on consistent fields.

- Wrap LLM/STT/TTS outputs with `LLMResponse` / `STTResponse` / `TTSResponse` and include the serialized dict in each stage's `StageOutput`.
- Wire `ChunkQueue` / `StreamingBuffer` event emitters to `ctx.try_emit_event` so pipeline-level WideEventEmitter streams capture `stream.*` events alongside `stage.wide`.

```python
queue = ChunkQueue(event_emitter=ctx.try_emit_event)
buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)
```

### Tool Call Resolution Pattern

When tool-executing stages are part of the graph, resolve LLM-provided tool calls before execution:

```python
tool_calls = llm_response.tool_calls or []
resolved, unresolved = registry.parse_and_resolve(tool_calls)

for call in unresolved:
    ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})

for call in resolved:
    tool_input = ToolInput(action=call.arguments)
    await call.tool.execute(tool_input, ctx={"call_id": call.call_id})
```

#### Wide events

If you construct `StageGraph` manually, you can opt into wide events:

```python
from stageflow.observability import WideEventEmitter

graph = StageGraph(
    specs=[...],
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=WideEventEmitter(),
)
```

Each stage completion/failure produces a `stage.wide` payload (duration, artifacts, correlation IDs) and the entire run produces a single `pipeline.wide` summary.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `stage_specs` | `list[StageSpec]` | List of stage specifications |

---

## StageSpec

```python
from stageflow import StageSpec
```

Low-level specification for a stage (used by StageGraph).

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Stage name |
| `runner` | `StageRunner` | Callable that runs the stage |
| `dependencies` | `tuple[str, ...]` | Stage dependencies |
| `conditional` | `bool` | Whether stage can be skipped |

---

## PipelineRegistry

```python
from stageflow import PipelineRegistry, pipeline_registry
```

Registry for pipeline instances with lazy registration.

### Methods

#### `register(name: str, pipeline: Pipeline) -> None`

Register a pipeline instance.

```python
pipeline_registry.register("chat", create_chat_pipeline())
```

#### `get(name: str) -> Pipeline`

Get a pipeline by name.

**Raises:** `KeyError` if not found

```python
pipeline = pipeline_registry.get("chat")
```

#### `list() -> list[str]`

List all registered pipeline names.

```python
names = pipeline_registry.list()  # ["chat", "voice", ...]
```

#### `__contains__(name: str) -> bool`

Check if pipeline name is registered.

```python
if "chat" in pipeline_registry:
    pipeline = pipeline_registry.get("chat")
```

### Global Instance

```python
from stageflow import pipeline_registry

# Use the global registry
pipeline_registry.register("my_pipeline", my_pipeline)
pipeline = pipeline_registry.get("my_pipeline")
```

---

## PipelineBuilder

```python
from stageflow.pipeline import PipelineBuilder
```

Code-defined pipeline with typed composition and full DAG validation.

### Constructor

```python
PipelineBuilder(name: str = "pipeline", stages: dict[str, PipelineSpec] = None)
```

### Methods

#### `with_stage(name, runner, dependencies=None, inputs=None, outputs=None, conditional=False, args=None) -> PipelineBuilder`

Add a stage to the pipeline (fluent builder, immutable).

**Parameters:**
- `name`: `str` — Unique stage name
- `runner`: `type[StageRunner] | StageRunner` — Stage class or instance
- `dependencies`: `tuple[str, ...] | None` — Stage dependencies
- `inputs`: `tuple[str, ...] | None` — Keys this stage reads from context
- `outputs`: `tuple[str, ...] | None` — Keys this stage writes to context
- `conditional`: `bool` — Whether stage can be skipped
- `args`: `dict[str, Any] | None` — Arguments passed to stage constructor

```python
builder = (
    PipelineBuilder(name="my_pipeline")
    .with_stage("input", InputStage)
    .with_stage("process", ProcessStage, dependencies=("input",))
)
```

#### `compose(other: PipelineBuilder) -> PipelineBuilder`

Merge stages from another pipeline builder.

#### `build() -> StageGraph`

Generate executable DAG. Validates the pipeline and raises on errors.

**Raises:**
- `CycleDetectedError` — If pipeline contains a cycle
- `PipelineValidationError` — If dependencies reference non-existent stages
- `ValueError` — If pipeline is empty

#### `stage_names() -> list[str]`

Get stage names in topological order.

---

## Exceptions

### PipelineValidationError

```python
from stageflow import PipelineValidationError
```

Raised when pipeline validation fails.

**Attributes:**
- `stages`: `list[str]` — Stages involved in the error

```python
try:
    pipeline.build()
except PipelineValidationError as e:
    print(f"Validation failed: {e}")
    print(f"Involved stages: {e.stages}")
```

### CycleDetectedError

```python
from stageflow import CycleDetectedError
```

Raised when a cycle is detected in the pipeline DAG. Subclass of `PipelineValidationError`.

**Attributes:**
- `cycle_path`: `list[str]` — Stages forming the cycle (e.g., `['A', 'B', 'C', 'A']`)
- `stages`: `list[str]` — All stages involved in cycles

```python
try:
    pipeline = (
        PipelineBuilder()
        .with_stage("a", StageA, dependencies=("c",))
        .with_stage("b", StageB, dependencies=("a",))
        .with_stage("c", StageC, dependencies=("b",))  # Cycle: a -> b -> c -> a
    )
except CycleDetectedError as e:
    print(f"Cycle detected: {' -> '.join(e.cycle_path)}")
    # Output: "Cycle detected: a -> b -> c -> a"
```

### StageExecutionError

```python
from stageflow import StageExecutionError
```

Raised when a stage inside a StageGraph fails.

**Attributes:**
- `stage`: `str` — Name of the failed stage
- `original`: `Exception` — Original exception
- `recoverable`: `bool` — Whether error is recoverable

### UnifiedPipelineCancelled

```python
from stageflow.pipeline.dag import UnifiedPipelineCancelled
```

Raised when pipeline is cancelled by a stage (not an error).

**Attributes:**
- `stage`: `str` — Stage that cancelled
- `reason`: `str` — Cancellation reason
- `results`: `dict[str, StageOutput]` — Partial results

```python
try:
    results = await graph.run(ctx)
except UnifiedPipelineCancelled as e:
    print(f"Cancelled by {e.stage}: {e.reason}")
    partial = e.results
```

---

## Structured Cancellation

### UnifiedStageGraph with Cleanup

```python
from stageflow.pipeline.dag import UnifiedStageGraph
from stageflow.pipeline.cancellation import CleanupRegistry

# Create graph with cleanup support
graph = UnifiedStageGraph(specs, cleanup_timeout=10.0)

# Register cleanup callbacks
graph.register_cleanup(cleanup_database, name="db_cleanup")
graph.register_cleanup(close_connections, name="conn_cleanup")

# Run with automatic cleanup
try:
    results = await graph.run(ctx)
finally:
    # Cleanup runs automatically on success, error, or cancellation
    pass
```

### CleanupRegistry

```python
from stageflow.pipeline.cancellation import CleanupRegistry

registry = CleanupRegistry()

# Register cleanup callbacks (LIFO order)
registry.register(cleanup_connections, name="connections")
registry.register(cleanup_files, name="files")

# Run all cleanups
completed, failed = await registry.run_all(timeout=5.0)

# Check results
print(f"Completed: {completed}")
print(f"Failed: {failed}")
```

### CancellationToken

```python
from stageflow.pipeline.cancellation import CancellationToken

token = CancellationToken()

# Check for cancellation
if token.is_cancelled:
    print("Operation cancelled:", token.reason)

# Register cancellation callback
token.on_cancel(lambda: print("Cancelled!"))

# Request cancellation
token.cancel("User requested stop")
```

### StructuredTaskGroup

```python
from stageflow.pipeline.cancellation import StructuredTaskGroup

async def run_with_cleanup():
    async with StructuredTaskGroup() as tg:
        # Register cleanup
        tg.cleanup_registry.register(cleanup_resources)
        
        # Create tasks
        tg.create_task(task1())
        tg.create_task(task2())
        tg.create_task(task3())
        
        # If any task fails, all others are cancelled
        # and cleanup runs automatically
```

---

## Usage Example

```python
from stageflow import (
    Pipeline,
    PipelineRegistry,
    StageKind,
    StageContext,
    StageOutput,
    StageExecutionError,
    pipeline_registry,
)
from stageflow.context import ContextSnapshot
from stageflow.pipeline.dag import UnifiedPipelineCancelled
from stageflow.pipeline.cancellation import CleanupRegistry

# Define stages
class InputStage:
    name = "input"
    kind = StageKind.TRANSFORM
    async def execute(self, ctx): return StageOutput.ok(text="hello")

class ProcessStage:
    name = "process"
    kind = StageKind.TRANSFORM
    async def execute(self, ctx):
        text = ctx.inputs.get("text", "")
        return StageOutput.ok(result=text.upper())

# Build pipeline
pipeline = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("input",))
)

# Register
pipeline_registry.register("example", pipeline)

# Execute
async def run():
    graph = pipeline.build()
    snapshot = ContextSnapshot(...)
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )
    
    try:
        results = await graph.run(ctx)
        print(results["process"].data["result"])  # "HELLO"
    except StageExecutionError as e:
        print(f"Stage {e.stage} failed: {e.original}")
    except UnifiedPipelineCancelled as e:
        print(f"Cancelled: {e.reason}")
```
