# Core Types API Reference

This document provides the API reference for stageflow's core types.

## Stage Protocol

```python
from stageflow import Stage
```

The `Stage` protocol defines the interface for all stage implementations.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique identifier within the pipeline |
| `kind` | `StageKind` | Stage categorization |

### Methods

#### `execute(ctx: StageContext) -> StageOutput`

Execute the stage logic.

**Parameters:**
- `ctx`: `StageContext` — Execution context with snapshot and config

**Returns:** `StageOutput` with status, data, artifacts, and events

**Example:**
```python
class MyStage:
    name = "my_stage"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(result="done")
```

---

## StageKind

```python
from stageflow import StageKind
```

Enumeration of stage types.

### Values

| Value | Description |
|-------|-------------|
| `TRANSFORM` | Data transformation (STT, TTS, LLM) |
| `ENRICH` | Context enrichment (Profile, Memory) |
| `ROUTE` | Path selection (Router, Dispatcher) |
| `GUARD` | Validation/filtering (Guardrails, Policy) |
| `WORK` | Side effects (Persist, Assessment) |
| `AGENT` | Interactive logic (Coach, Interviewer) |

**Example:**
```python
from stageflow import StageKind

class MyStage:
    kind = StageKind.TRANSFORM
```

---

## StageStatus

```python
from stageflow import StageStatus
```

Enumeration of stage execution outcomes.

### Values

| Value | Description |
|-------|-------------|
| `OK` | Stage completed successfully |
| `SKIP` | Stage was skipped (conditional) |
| `CANCEL` | Pipeline cancelled (no error) |
| `FAIL` | Stage failed (error) |
| `RETRY` | Stage failed but is retryable |

---

## StageOutput

```python
from stageflow import StageOutput
```

Unified return type for all stage executions.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `status` | `StageStatus` | Execution outcome |
| `data` | `dict[str, Any]` | Output data |
| `artifacts` | `list[StageArtifact]` | Produced artifacts |
| `events` | `list[StageEvent]` | Emitted events |
| `error` | `str \| None` | Error message if failed |

### Provider Response Conventions

Stages calling AI providers should attach standardized payloads to `data` for downstream analytics and UI layers:

- `LLMResponse` for chat/completions (fields: `content`, `model`, `provider`, `input_tokens`, `output_tokens`, `latency_ms`)
- `STTResponse` for speech-to-text (fields: `text`, `confidence`, `duration_ms`, `language`, `words`, `is_final`)
- `TTSResponse` for text-to-speech (fields: `duration_ms`, `sample_rate`, `format`, `characters_processed`)

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

### Class Methods

#### `ok(data=None, **kwargs) -> StageOutput`

Create a successful output.

```python
return StageOutput.ok(result="done", count=42)
# or
return StageOutput.ok(data={"result": "done", "count": 42})
```

#### `skip(reason="", data=None) -> StageOutput`

Create a skipped output.

```python
return StageOutput.skip(reason="No user_id provided")
```

#### `cancel(reason="", data=None) -> StageOutput`

Create a cancelled output to stop pipeline without error.

```python
return StageOutput.cancel(reason="Content blocked", data={"blocked": True})
```

#### `fail(error, data=None) -> StageOutput`

Create a failed output.

```python
return StageOutput.fail(error="Service unavailable")
```

#### `retry(error, data=None) -> StageOutput`

Create a retry-needed output.

```python
return StageOutput.retry(error="Rate limited, try again")
```

---

## StageContext

```python
from stageflow import StageContext, create_stage_context
```

Execution context for stages.

### Constructor

```python
StageContext(snapshot: ContextSnapshot, config: dict | None = None)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `snapshot` | `ContextSnapshot` | Immutable input snapshot |
| `config` | `dict[str, Any]` | Stage configuration |
| `started_at` | `datetime` | When context was created |
| `timer` | `PipelineTimer` | Shared pipeline timer |
| `pipeline_run_id` | `UUID \| None` | Pipeline run identifier |
| `request_id` | `UUID \| None` | Request identifier |
| `execution_mode` | `str \| None` | Current execution mode |
| `event_sink` | `EventSink \| None` | Event sink if available |

### Methods

#### `try_emit_event(type: str, data: dict) -> None`

Emit an event during execution without blocking. This delegates to the
configured event sink if present and safely no-ops otherwise.

```python
ctx.try_emit_event("custom.started", {"step": 1})
```

#### `add_artifact(type: str, payload: dict) -> None`

Add an artifact to the output.

```python
ctx.add_artifact("chart", {"data": [1, 2, 3]})
```

#### `collect_outputs() -> list[StageOutput]`

Collect all outputs emitted during execution.

#### `get_output_data(key: str, default=None) -> Any`

Get a value from any output data.

#### `to_dict() -> dict[str, Any]`

Convert context to dictionary for serialization.

#### `now() -> datetime` (classmethod)

Return current UTC timestamp for consistent stage timing.

### Factory Function

```python
ctx = create_stage_context(snapshot=snapshot, config={"timeout": 30})
```

---

## StageArtifact

```python
from stageflow import StageArtifact
```

An artifact produced by a stage during execution.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `type` | `str` | Artifact type (e.g., "audio", "chart") |
| `payload` | `dict[str, Any]` | Artifact data |
| `timestamp` | `datetime` | When artifact was created |

---

## StageEvent

```python
from stageflow import StageEvent
```

An event emitted by a stage during execution.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `type` | `str` | Event type (e.g., "started", "progress") |
| `data` | `dict[str, Any]` | Event data |
| `timestamp` | `datetime` | When event was emitted |

---

## PipelineTimer

```python
from stageflow import PipelineTimer
```

Shared timer for consistent cross-stage timing.

### Methods

#### `elapsed_ms() -> int`

Get milliseconds elapsed since pipeline start.

```python
timer = ctx.timer
print(f"Elapsed: {timer.elapsed_ms()}ms")
```

---

## Usage Example

```python
from stageflow import (
    Stage,
    StageKind,
    StageStatus,
    StageOutput,
    StageContext,
    StageArtifact,
    StageEvent,
    create_stage_context,
)
from stageflow.context import ContextSnapshot

class ProcessingStage:
    name = "processing"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Access snapshot
        input_text = ctx.snapshot.input_text
        user_id = ctx.snapshot.user_id
        
        # Access upstream outputs
        previous_result = ctx.inputs.get("result")
        
        # Emit event
        ctx.try_emit_event("processing.started", {"input_length": len(input_text or "")})
        
        # Add artifact
        ctx.add_artifact("result", {"processed": True})
        
        # Return output
        return StageOutput.ok(
            result="processed",
            input_length=len(input_text or ""),
        )
```
