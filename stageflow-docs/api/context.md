# Context API Reference

This document provides the API reference for Stageflow's context system, updated for the RunIdentity/ContextSnapshot/StageContext migration.

## Related Modules

- [StageInputs API](inputs.md) - Immutable access to prior stage outputs with validation
- [Context Sub-modules](context-submodules.md) - Detailed reference for context components

## RunIdentity

```python
from stageflow.context import RunIdentity
```

Frozen bundle grouping all run-level identifiers.

### Constructor

```python
RunIdentity(
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `pipeline_run_id` | `UUID \| None` | Pipeline run identifier |
| `request_id` | `UUID \| None` | Request identifier |
| `session_id` | `UUID \| None` | Session identifier |
| `user_id` | `UUID \| None` | User identifier |
| `org_id` | `UUID \| None` | Organization identifier |
| `interaction_id` | `UUID \| None` | Interaction identifier |

---

## ContextSnapshot

```python
from stageflow.context import ContextSnapshot
```

Immutable, composition-based snapshot passed to stages. Uses bundles for identity, conversation, and enrichments with sensible defaults for easy instantiation.

### Constructor

```python
ContextSnapshot(
    run_id: RunIdentity = RunIdentity(),
    conversation: Conversation | None = None,
    enrichments: Enrichments | None = None,
    extensions: ExtensionBundle | None = None,
    input_text: str | None = None,
    input_audio_duration_ms: int | None = None,
    topology: str | None = None,
    execution_mode: str | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `run_id` | `RunIdentity` | Grouped run identity bundle |
| `conversation` | `Conversation \| None` | Messages + routing data |
| `enrichments` | `Enrichments \| None` | Profile, memory, documents, web results |
| `extensions` | `ExtensionBundle \| None` | Typed application-specific data |
| `input_text` | `str \| None` | Latest user utterance |
| `input_audio_duration_ms` | `int \| None` | Speech input duration |
| `topology` | `str \| None` | Pipeline topology |
| `execution_mode` | `str \| None` | Execution mode (practice, doc_edit, etc.) |
| `metadata` | `dict[str, Any]` | Custom metadata (default `{}`) |
| `created_at` | `datetime` | Snapshot creation timestamp |

### Convenience Properties

Backwards-compatible accessors surface legacy flat fields:

| Property | Type | Description |
|----------|------|-------------|
| `pipeline_run_id` | `UUID \| None` | `run_id.pipeline_run_id` |
| `request_id` | `UUID \| None` | `run_id.request_id` |
| `session_id` | `UUID \| None` | `run_id.session_id` |
| `user_id` | `UUID \| None` | `run_id.user_id` |
| `org_id` | `UUID \| None` | `run_id.org_id` |
| `interaction_id` | `UUID \| None` | `run_id.interaction_id` |
| `messages` | `tuple[Message, ...] \| list[Message]` | From `conversation.messages` |
| `profile` | `ProfileEnrichment \| None` | From `enrichments.profile` |
| `memory` | `MemoryEnrichment \| None` | From `enrichments.memory` |
| `documents` | `tuple[DocumentEnrichment, ...] \| list[...]` | From `enrichments.documents` |

### Methods

#### `to_dict() -> dict[str, Any>`

JSON-serializable representation including nested bundles.

#### `from_dict(data: dict) -> ContextSnapshot`

Deserialize a snapshot (supports test fixtures and replay pipelines).

---

## Conversation

```python
from stageflow.context import Conversation
```

Frozen message bundle storing chat history and routing decisions.

| Attribute | Type | Description |
|-----------|------|-------------|
| `messages` | `tuple[Message, ...]` | Ordered history |
| `routing_decision` | `RoutingDecision \| None` | Output from router stages |
| `input_text` | `str \| None` | Latest raw input |
| `input_audio_duration_ms` | `int \| None` | Optional speech duration |
| `metadata` | `dict[str, Any]` | Additional context |

---

## Enrichments

```python
from stageflow.context import Enrichments
```

Structured data added by enrichment stages.

| Attribute | Type | Description |
|-----------|------|-------------|
| `profile` | `ProfileEnrichment \| None` | User profile bundle |
| `memory` | `MemoryEnrichment \| None` | Long-term memory |
| `documents` | `tuple[DocumentEnrichment, ...]` | Retrieved documents |
| `web_results` | `tuple[dict, ...]` | Web search snippets |

---

## Message

```python
from stageflow.context import Message
```

Single chat message entity (role, content, metadata). See previous example for instantiation.

---

## StageContext

```python
from stageflow.core import StageContext
```

Frozen dataclass describing per-stage execution state. Stages receive a StageContext and must return a StageOutput—no direct mutation of pipeline state.

### Constructor

```python
StageContext(
    snapshot: ContextSnapshot,
    inputs: StageInputs,
    stage_name: str,
    timer: PipelineTimer,
    event_sink: EventSink | None = None,
)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `snapshot` | `ContextSnapshot` | Immutable input state |
| `inputs` | `StageInputs` | Outputs from declared dependencies + ports |
| `stage_name` | `str` | Current stage identifier |
| `timer` | `PipelineTimer` | Shared pipeline timer |
| `event_sink` | `EventSink \| None` | Optional fire-and-forget sink |

### Convenience Properties

Expose frequently-used snapshot fields directly (`pipeline_run_id`, `request_id`, `execution_mode`, etc.) for easy access.

### Methods

| Method | Description |
|--------|-------------|
| `to_dict()` | Merge snapshot data with stage metadata for tooling |
| `try_emit_event(type, data)` | Non-blocking event emission with correlation IDs |

### Usage

```python
class MyStage(Stage):
    async def execute(self, ctx: StageContext) -> StageOutput:
        transcript = ctx.inputs.get("transcript")
        route = ctx.inputs.get_from("router", "route", default="general")

        if ctx.inputs.ports and ctx.inputs.ports.send_status:
            await ctx.inputs.ports.send_status(ctx.stage_name, "started", None)

        ctx.try_emit_event("my_stage.processed", {"route": route})
        return StageOutput.ok(result="processed")
```

---

## StageInputs

```python
from stageflow.stages.inputs import StageInputs, create_stage_inputs
```

Immutable view of upstream outputs plus injected ports. Enforces explicit dependency contracts (strict mode raises for undeclared dependencies).

### Constructor (dataclass)

```python
StageInputs(
    snapshot: ContextSnapshot,
    prior_outputs: dict[str, StageOutput] = {},
    ports: CorePorts | LLMPorts | AudioPorts | None = None,
    declared_deps: frozenset[str] = frozenset(),
    stage_name: str | None = None,
    strict: bool = True,
)
```

### Key Methods

| Method | Description |
|--------|-------------|
| `get(key, default=None)` | Search all prior outputs for key (non-validating) |
| `get_from(stage_name, key, default=None)` | Preferred explicit access—validates dependency |
| `has_output(stage_name)` | Returns `True` if dependency has produced output |
| `get_output(stage_name)` | Returns the full `StageOutput` |
| `require_from(stage_name, key)` | Like `get_from` but raises `KeyError` if missing |

### Factory Helper

```python
inputs = create_stage_inputs(
    snapshot=snapshot,
    prior_outputs={"router": router_output},
    declared_deps=["router"],
    stage_name="planner",
    strict=True,
)
```

---

## OutputBag

```python
from stageflow.context.output_bag import OutputBag, OutputEntry, OutputConflictError
```

Append-only, thread-safe storage for stage outputs with attempt tracking—replaces the legacy `ContextBag`.

### Methods

| Method | Description |
|--------|-------------|
| `async write(stage_name, output, allow_overwrite=False)` | Add output; optionally permit retries |
| `write_sync(...)` | Sync variant for single-threaded tests |
| `get(stage_name)` | Return `OutputEntry` (output + attempt metadata) |
| `get_output(stage_name)` | Return just the `StageOutput` |
| `has(stage_name)` | Whether stage already wrote output |
| `outputs()` | Snapshot of all outputs (used to seed `StageInputs`) |
| `get_attempt_count(stage_name)` | Attempt counter |
| `get_retry_stages()` | Names of stages with attempt > 1 |

### OutputEntry

```python
@dataclass(frozen=True, slots=True)
class OutputEntry:
    output: StageOutput
    attempt: int
    timestamp: datetime
    stage_name: str
```

---

## PipelineContext

```python
from stageflow.stages.context import PipelineContext
```

Mutable coordinator used by the pipeline engine. Owns OutputBag, timers, and event sinks; produces immutable StageContext instances via `derive_for_stage`.

### Attributes (selected)

| Attribute | Type | Description |
|-----------|------|-------------|
| `pipeline_run_id`, `request_id`, ... | `UUID \| None` | Run-level identifiers |
| `topology` | `str \| None` | Pipeline name |
| `execution_mode` | `str \| None` | Execution hint |
| `configuration` | `dict[str, Any]` | Static DAG wiring/config |
| `event_sink` | `EventSink` | Observability events |
| `artifacts` | `list[StageArtifact]` | Produced UI artifacts |
| `canceled` | `bool` | Cancellation flag |
| `parent_run_id`, `parent_stage_id`, `correlation_id` | Correlation IDs for subpipelines |

> `data` remains for legacy compatibility but should be considered deprecated in favor of OutputBag + StageInputs.

### Key Methods

| Method | Description |
|--------|-------------|
| `derive_for_stage(stage_name, snapshot, output_bag, *, declared_deps=None, ports=None, strict=True)` | Build immutable StageContext, wiring StageInputs from OutputBag |
| `fork(child_run_id, parent_stage_id, correlation_id, *, topology=None, execution_mode=None)` | Spawn child PipelineContext for subpipelines |
| `record_stage_event(stage, status, payload=None)` | Emit observability events |
| `try_emit_event(type, data)` | ExecutionContext compatibility |
| `mark_canceled()` / `is_canceled` | Cancellation helpers |

---

## Usage Example

```python
from uuid import uuid4
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.context.output_bag import OutputBag
from stageflow.stages.context import PipelineContext

run_id = RunIdentity(pipeline_run_id=uuid4())
snapshot = ContextSnapshot(run_id=run_id, input_text="hello")
output_bag = OutputBag()
pipeline_ctx = PipelineContext(
    pipeline_run_id=run_id.pipeline_run_id,
    request_id=run_id.request_id,
    session_id=None,
    user_id=None,
    org_id=None,
    interaction_id=None,
    topology="chat_fast",
)

# After upstream stages write outputs into the bag:
# await output_bag.write("uppercase", StageOutput.ok(text="HELLO"))

stage_ctx = pipeline_ctx.derive_for_stage(
    stage_name="exclaim",
    snapshot=snapshot,
    output_bag=output_bag,
    declared_deps=["uppercase"],
)

result = await some_stage.execute(stage_ctx)
await output_bag.write("exclaim", result)
```

---

## Provider Response Conventions

Stages that call AI providers should attach standardized response payloads to `StageOutput.data` using frozen dataclasses from `stageflow.helpers`:

- `LLMResponse` — chat/completions fields like `content`, `model`, `provider`, `input_tokens`, `output_tokens`
- `STTResponse` — speech-to-text fields like `text`, `confidence`, `duration_ms`, `language`, `words`, `is_final`
- `TTSResponse` — text-to-speech metadata like `duration_ms`, `sample_rate`, `format`, `characters_processed`

Attach via `to_dict()` for downstream consumption and analytics:

```python
from stageflow.helpers import LLMResponse

llm = LLMResponse(
    content=response_text,
    model="gpt-4o-mini",
    provider="openai",
    input_tokens=prompt_tokens,
    output_tokens=completion_tokens,
)
return StageOutput.ok(message=llm.content, llm=llm.to_dict())
```

---

## Streaming Telemetry Emitters

When using streaming primitives in stages, wire telemetry event emitters so events carry correlation IDs from `StageContext` through the configured sinks.

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer

queue = ChunkQueue(event_emitter=ctx.try_emit_event)
buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)
```

Emits events including:
- `stream.chunk_dropped`, `stream.producer_blocked`, `stream.throttle_started`, `stream.throttle_ended`, `stream.queue_closed`
- `stream.buffer_overflow`, `stream.buffer_underrun`, `stream.buffer_recovered`

