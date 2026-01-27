# Core Concepts

This guide explains the fundamental concepts behind stageflow. Understanding these will help you design better pipelines.

## The Big Picture

Stageflow is a **DAG-based execution framework**. You define stages (nodes) and their dependencies (edges), and the framework handles:

- Running stages in the correct order
- Parallelizing independent stages
- Passing data between stages
- Handling errors and cancellation
- Providing observability (logging, streaming telemetry, metrics, tracing)

```
┌─────────────────────────────────────────────────────────────┐
│                        Pipeline                             │
│                                                             │
│   [input_guard] ──┐                                         │
│                   │                                         │
│   [profile] ──────┼──> [llm] ──> [output_guard]             │
│                   │                                         │
│   [memory] ───────┘                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Stages

A **Stage** is the fundamental unit of work. Every stage:

1. Has a **name** (unique identifier)
2. Has a **kind** (categorization)
3. Implements an **execute** method

```python
from stageflow import StageContext, StageKind, StageOutput

class MyStage:
    name = "my_stage"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Do work here
        return StageOutput.ok(result="done")
```

### Stage Kinds

Stages are categorized by their purpose:

| Kind | Purpose | Examples |
|------|---------|----------|
| `TRANSFORM` | Change data form | STT, TTS, LLM, text processing |
| `ENRICH` | Add context | Profile lookup, memory retrieval |
| `ROUTE` | Select execution path | Router, dispatcher |
| `GUARD` | Validate/filter | Input validation, output filtering |
| `WORK` | Side effects | Persistence, assessment, notifications |
| `AGENT` | Interactive logic | Chat agents, coaches |

### Stage Output

Every stage returns a `StageOutput`:

```python
# Success with data
return StageOutput.ok(key="value", another="data")

# Skip this stage (conditional execution)
return StageOutput.skip(reason="condition not met")

# Cancel the entire pipeline (graceful stop)
return StageOutput.cancel(reason="user requested stop")

# Failure
return StageOutput.fail(error="Something went wrong")
```

### Provider Responses

Stageflow standardizes provider metadata via frozen dataclasses located in `stageflow.helpers`:

```python
from stageflow.helpers import LLMResponse, STTResponse, TTSResponse

llm = LLMResponse(
    content="Hello!",
    model="gpt-4",
    provider="openai",
    input_tokens=123,
    output_tokens=456,
)

return StageOutput.ok(
    message=llm.content,
    llm=llm.to_dict(),          # friendly for downstream stages
    llm_attrs=llm.to_otel_attributes(),  # telemetry-ready
)
```

Use `STTResponse` and `TTSResponse` to capture speech metadata (confidence, duration, sample rate, byte count, etc.) so downstream stages can reason about latency, accuracy, and audio quality without parsing unstructured payloads.

## Pipelines

A **Pipeline** is a collection of stages with their dependencies. Use the fluent builder API:

```python
from stageflow import Pipeline, StageKind

pipeline = (
    Pipeline()
    .with_stage("stage_a", StageA, StageKind.TRANSFORM)
    .with_stage("stage_b", StageB, StageKind.TRANSFORM)
    .with_stage(
        "stage_c",
        StageC,
        StageKind.TRANSFORM,
        dependencies=("stage_a", "stage_b"),  # Waits for both
    )
)
```

### Dependency Rules

- Stages with **no dependencies** run immediately (in parallel if multiple)
- Stages run as soon as **all dependencies complete**
- The framework detects cycles and deadlocks

### Building the Graph

Call `build()` to create an executable `StageGraph`:

```python
graph = pipeline.build()
results = await graph.run(ctx)
```

## Context

Context carries data through the pipeline. There are two main context types:

### ContextSnapshot

An **immutable**, composition-based view of the world passed to stages. It groups related data into bundles for clarity:

- **RunIdentity**: `pipeline_run_id`, `request_id`, `session_id`, `user_id`, `org_id`, `interaction_id`
- **Conversation**: `messages`, `input_text`, `routing_decision`
- **Enrichments**: `profile`, `memory`, `documents`, `web_results`
- **Extensions**: Application-specific typed bundle

```python
from uuid import uuid4
from stageflow.context import ContextSnapshot, RunIdentity

snapshot = ContextSnapshot(
    run_id=RunIdentity(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
    ),
    topology="chat_fast",
    execution_mode="practice",
    input_text="Hello!",
)
```

### StageContext

The **per-stage execution wrapper** that stages receive. Provides:

- Access to the immutable snapshot
- Filtered upstream outputs via `StageInputs`
- Shared timer and event sink
- Convenience properties for run identity fields

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Snapshot data is immutable
    user_input = ctx.snapshot.input_text
    user_id = ctx.snapshot.user_id

    # Access upstream outputs
    transcript = ctx.inputs.get("transcript")
    route = ctx.inputs.get_from("router", "route", default="general")

    ctx.try_emit_event("my_stage.started", {"route": route})
    return StageOutput.ok(...)
```

## Data Flow

Data flows through the pipeline via stage outputs:

1. **Snapshot** provides initial input (immutable)
2. **Stage outputs** are collected as `StageOutput.data`
3. **Downstream stages** access upstream outputs via `StageInputs`

```python
class StageA:
    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(computed_value=42)

class StageB:
    async def execute(self, ctx: StageContext) -> StageOutput:
        value = ctx.inputs.get_from("stage_a", "computed_value")
        return StageOutput.ok(doubled=value * 2)
```

## Interceptors

**Interceptors** are middleware that wrap stage execution. They handle cross-cutting concerns:

- **Idempotency** — Short-circuit duplicate WORK stages using cached `StageResult`s keyed by request metadata
- **Logging** — Structured logging of stage events
- **Streaming Telemetry** — Emit queue/backpressure events from `ChunkQueue` or `StreamingBuffer`
- **Metrics** — Duration, success/failure tracking
- **Tracing** — OpenTelemetry span creation
- **Timeouts** — Per-stage execution limits
- **Circuit Breakers** — Prevent cascading failures
- **Authentication** — JWT validation and org enforcement

```python
from stageflow import get_default_interceptors

# Default interceptors are applied automatically
interceptors = get_default_interceptors()
# [IdempotencyInterceptor, TimeoutInterceptor, CircuitBreakerInterceptor,
#  TracingInterceptor, MetricsInterceptor, ChildTrackerMetricsInterceptor, LoggingInterceptor]
```

## Events

Stageflow emits structured events for observability:

- `stage.{name}.started` — Stage began execution
- `stage.{name}.completed` — Stage finished successfully
- `stage.{name}.failed` — Stage failed with error
- `stream.*` — Streaming helpers emit telemetry (chunk drops, throttle start/end, buffer underruns)

Events flow through an `EventSink`:

```python
from stageflow import set_event_sink, LoggingEventSink

# Use logging sink (default)
set_event_sink(LoggingEventSink())

# Or implement your own
class MyEventSink:
    async def emit(self, *, type: str, data: dict) -> None:
        await save_to_database(type, data)
    
    def try_emit(self, *, type: str, data: dict) -> None:
        asyncio.create_task(self.emit(type=type, data=data))
```

## Key Principles

### 1. Containers vs. Payloads

Stages are **containers** that handle orchestration (timeouts, retries, telemetry). Business logic lives in **payloads** (the actual work being done).

### 2. Immutable Data Flow

The `ContextSnapshot` is frozen. Stages cannot modify shared state—they read inputs and produce outputs.

### 3. Parallel by Default

Independent stages run concurrently. You don't need to manage threads or async coordination.

### 4. Observability First

Every stage execution is logged, timed, and traceable. Events are emitted for monitoring and debugging, and helpers provide ready-to-use telemetry:

- `ChunkQueue(event_emitter=...)` triggers streaming events for drops/throttling.
- `StreamingBuffer(event_emitter=...)` notifies underruns and overflows.
- `BufferedExporter(on_overflow=...)` alerts when analytics buffers near capacity.
- `ToolRegistry.parse_and_resolve()` standardizes LLM tool-call observability.

### 5. Fail Fast, Recover Gracefully

Errors are caught, logged, and can trigger retries or fallbacks via interceptors.

## Next Steps

- [Building Stages](../guides/stages.md) — Deep dive into stage implementation
- [Composing Pipelines](../guides/pipelines.md) — Advanced pipeline patterns
- [Context & Data Flow](../guides/context.md) — Detailed context usage
- [Observability](../guides/observability.md) — Streaming telemetry, analytics exporters, and overflow callbacks
