# Context & Data Flow

Understanding how data flows through stageflow pipelines is essential for building effective applications. This guide covers the context system in depth.

## Context Overview

Stageflow uses a layered context system:

1. **PipelineContext** — Execution context for a pipeline run, shared across stages and used by the engine and interceptors
2. **ContextSnapshot** — Immutable input data derived from RunIdentity + bundles (conversation, enrichments)
3. **StageContext** — Per-stage execution wrapper with immutable snapshot and typed `StageInputs`
4. **StageInputs** — Filtered view of upstream stage outputs + injected ports plus tooling helpers
5. **OutputBag** — Thread-safe, append-only output storage with attempt tracking

```
┌─────────────────────────────────────────────────────────────┐
│                      PipelineContext                        │
│  (run identity, topology, output bag, timer, event sink)    │
└─────────────────────────────────────────────────────────────┘
                            │ derive_for_stage()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ContextSnapshot (immutable)              │
│  run_id · conversation · enrichments · extensions           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      StageContext                           │
│  snapshot · StageInputs · timer · event sink                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      StageInputs                            │
│  prior_outputs + ports with strict dependency validation    │
└─────────────────────────────────────────────────────────────┘
                            │ writes
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                       OutputBag                             │
│  append-only StageOutput entries with attempt tracking      │
└─────────────────────────────────────────────────────────────┘
```

## PipelineContext

`PipelineContext` is the execution context for a single pipeline run.

It is:

- Shared across all stages in the run
- Owned/managed by the engine and interceptors (you rarely construct it by hand)
- The place where:
  - run identity (pipeline_run_id, request_id, session_id, user_id, org_id, interaction_id)
  - topology and execution_mode
  - shared `data` dict
  - artifacts and observability metadata
  - event sink and streaming telemetry emitters
  - subpipeline correlation (parent_run_id, parent_stage_id, correlation_id)
  
  live for the lifetime of the run.

A simplified view of the important fields:

```python
from stageflow.stages.context import PipelineContext

ctx = PipelineContext(
    pipeline_run_id=...,   # run identity
    request_id=...,
    session_id=...,
    user_id=...,
    org_id=...,
    interaction_id=...,
    topology="chat_fast",
    execution_mode="practice",
    configuration={},
    service="pipeline",
    data={},               # shared mutable data across stages
    artifacts=[],          # produced StageArtifact objects
    event_sink=logging_sink,
    streaming_emitters={
        "chunk_queue": lambda event, attrs: event_sink.try_emit(type=event, data=attrs),
        "buffer": lambda event, attrs: event_sink.try_emit(type=event, data=attrs),
    },
)
```

### How it relates to other context types

- The **engine** uses `PipelineContext` as the authoritative state for a run.
- A **`ContextSnapshot`** is an immutable view derived from that state and passed into stages via `StageContext`.
- A **`StageContext`** wraps a `ContextSnapshot` plus per-stage config and output buffer.
- **Interceptors** receive the `PipelineContext` directly and can:
  - Read IDs, topology, execution_mode, and shared `data`
  - Attach transient flags into `ctx.data` (e.g. rate limiting, caching hints)
- Tools and agents often see a **dict view** of `PipelineContext` created via `PipelineContext.to_dict()`.

## ContextSnapshot

The `ContextSnapshot` is an **immutable**, **serializable** view of the world. It contains everything a stage needs to do its work.

### Creating a Snapshot

```python
from uuid import uuid4
from datetime import datetime, timezone
from stageflow.context import (
    ContextSnapshot,
    Message,
    RoutingDecision,
    ProfileEnrichment,
    MemoryEnrichment,
)

snapshot = ContextSnapshot(
    # Run Identity
    pipeline_run_id=uuid4(),
    request_id=uuid4(),
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),
    interaction_id=uuid4(),
    
    # Configuration
    topology="chat_fast",
    execution_mode="practice",
    
    # Input
    input_text="Hello, how are you?",
    messages=[
        Message(role="user", content="Hi there", timestamp=datetime.now(timezone.utc)),
        Message(role="assistant", content="Hello!", timestamp=datetime.now(timezone.utc)),
    ],
    
    # Enrichments (optional, can be populated by stages)
    profile=ProfileEnrichment(
        user_id=uuid4(),
        display_name="Alice",
        preferences={"tone": "friendly"},
        goals=["learn Python"],
    ),
    memory=MemoryEnrichment(
        recent_topics=["programming", "AI"],
        key_facts=["prefers examples"],
    ),
    
    # Extensions (application-specific)
    extensions={"skills": {"active_skill_ids": ["python"]}},
    
    # Metadata
    metadata={"source": "web_chat"},
)
```

### Snapshot Fields

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_run_id` | `UUID` | Unique identifier for this pipeline run |
| `request_id` | `UUID` | HTTP/WebSocket request identifier |
| `session_id` | `UUID` | User session identifier |
| `user_id` | `UUID` | User identifier |
| `org_id` | `UUID` | Organization/tenant identifier |
| `interaction_id` | `UUID` | Specific interaction identifier |
| `topology` | `str` | Pipeline topology name |
| `execution_mode` | `str` | Execution mode (practice, roleplay, etc.) |
| `input_text` | `str` | Raw user input |
| `messages` | `list[Message]` | Conversation history |
| `profile` | `ProfileEnrichment` | User profile data |
| `memory` | `MemoryEnrichment` | Conversation memory |
| `documents` | `list[DocumentEnrichment]` | Document context |
| `extensions` | `dict` | Application-specific data |
| `metadata` | `dict` | Additional metadata |

### Serialization

Snapshots can be serialized for testing, logging, or replay:

```python
# To dict
data = snapshot.to_dict()

# From dict
restored = ContextSnapshot.from_dict(data)
```

## StageContext

The `StageContext` wraps a snapshot and provides stage execution utilities.

### Accessing the Snapshot

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # All snapshot fields are accessible
    user_id = ctx.snapshot.user_id
    input_text = ctx.snapshot.input_text
    messages = ctx.snapshot.messages
    execution_mode = ctx.snapshot.execution_mode
```

### Accessing Configuration

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Configuration is typically provided via constructor args or injected ports
    timeout = 30
    model = "default"
    
    # Shared timer for consistent timing
    elapsed = ctx.timer.elapsed_ms()
```

### Accessing Upstream Outputs via StageInputs

Stages receive upstream outputs through `StageInputs`, an immutable view of prior stage outputs:

```python
from stageflow.stages.inputs import StageInputs

async def execute(self, ctx: StageContext) -> StageOutput:
    inputs: StageInputs = ctx.inputs
    
    # Get any key from upstream outputs (searches all prior stages)
    processed_text = inputs.get("text")
    
    # Get from a specific stage (preferred - explicit dependency)
    route = inputs.get_from("router", "route", default="general")
    
    # Check if a stage has produced output
    if inputs.has_output("validator"):
        validation = inputs.get_output("validator")
    
    # Access injected services through ports
    if inputs.ports and inputs.ports.db:
        await inputs.ports.db.save(...)

    # Wrap provider payloads for downstream telemetry
    if inputs.ports and getattr(inputs.ports, "llm_provider", None):
        raw = await inputs.ports.llm_provider.chat(messages)
        from stageflow.helpers import LLMResponse

        llm = LLMResponse(
            content=raw.content,
            provider=raw.provider,
            model=raw.model,
            input_tokens=raw.usage.prompt_tokens,
            output_tokens=raw.usage.completion_tokens,
        )
        return StageOutput.ok(message=llm.content, llm=llm.to_dict())
```

**Key `StageInputs` methods:**
- `get(key, default=None)` — Search all prior outputs for a key
- `get_from(stage_name, key, default=None)` — Get from specific stage (preferred)
- `has_output(stage_name)` — Check if stage produced output
- `get_output(stage_name)` — Get complete `StageOutput` object

### Emitting Events

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Emit custom events
    ctx.emit_event("custom.started", {"step": 1})
    
    # Do work...
    
    ctx.emit_event("custom.completed", {"step": 1, "result": "success"})
    
    return StageOutput.ok(...)
```

### Adding Artifacts

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Add UI artifacts
    ctx.add_artifact(
        type="chart",
        payload={"data": [1, 2, 3], "title": "Results"},
    )
    
    return StageOutput.ok(artifact_added=True)
```

## Data Flow Between Stages

### How Outputs Flow

1. Stage A returns `StageOutput.ok(key="value")`
2. The framework collects the output
3. Stage B (depends on A) receives outputs via `inputs`

```python
# Stage A
class StageA:
    async def execute(self, ctx: StageContext) -> StageOutput:
        from stageflow.helpers import STTResponse

        stt = STTResponse(text="hello world", confidence=0.98, duration_ms=1500)
        return StageOutput.ok(
            computed_value=42,
            metadata={"source": "stage_a"},
            stt=stt.to_dict(),
        )

# Stage B (depends on A)
class StageB:
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Access A's output
        value = ctx.inputs.get_from("stage_a", "computed_value")

        return StageOutput.ok(doubled=value * 2)
```

### Multiple Dependencies

When a stage depends on multiple upstream stages:

```python
# Stage C depends on both A and B
class StageC:
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get from specific stages
        a_value = ctx.inputs.get_from("stage_a", "computed_value")
        b_value = ctx.inputs.get_from("stage_b", "doubled")

        return StageOutput.ok(combined=a_value + b_value)
```

### Handling Missing Data

Always handle cases where upstream data might be missing:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # With default value
    value = ctx.inputs.get("optional_key", default="fallback")
    
    # Check before use
    if ctx.inputs.has_output("required_stage"):
        data = ctx.inputs.get_from("required_stage", "required_key")
    else:
        return StageOutput.skip(reason="Missing required_key")
```

## OutputBag

The `OutputBag` is the append-only store for stage outputs. It tracks write attempts for retry visibility and replaces the legacy ContextBag.

### Writing Outputs

```python
from stageflow.context.output_bag import OutputBag

bag = OutputBag()
await bag.write("stage_a", StageOutput.ok(result=42))
await bag.write("stage_a", StageOutput.ok(result=84), allow_overwrite=True)  # retries
```

### Reading Outputs

```python
if bag.has("stage_a"):
    entry = bag.get("stage_a")
    print(entry.output.data, entry.attempt)

prior_outputs = bag.outputs()  # pass directly into StageInputs
```

## Enrichments

Enrichments are structured data added to the context by ENRICH stages.

### ProfileEnrichment

User profile information:

```python
from stageflow.context import ProfileEnrichment

profile = ProfileEnrichment(
    user_id=uuid4(),
    display_name="Alice",
    preferences={"tone": "friendly", "language": "en"},
    goals=["learn Python", "build APIs"],
)
```

### MemoryEnrichment

Conversation memory:

```python
from stageflow.context import MemoryEnrichment

memory = MemoryEnrichment(
    recent_topics=["Python", "async programming"],
    key_facts=["prefers examples", "works at TechCorp"],
    interaction_history_summary="Discussed Python basics last session",
)
```

### DocumentEnrichment

Document context:

```python
from stageflow.context import DocumentEnrichment

document = DocumentEnrichment(
    document_id="doc_123",
    document_type="sales_script",
    blocks=[
        {"id": "blk_1", "type": "heading", "content": "Introduction"},
        {"id": "blk_2", "type": "paragraph", "content": "Welcome..."},
    ],
    metadata={"version": 3, "last_edited": "2024-01-15"},
)

## Tool Registry Helper Access

Stages that parse LLM tool calls can keep the context flow clean by resolving calls before mutating outputs:

```python
resolved, unresolved = ctx.inputs.tool_registry.parse_and_resolve(tool_calls)
for call in unresolved:
    ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})
```

This keeps telemetry, context propagation, and tool execution metadata co-located with the stage data flow.

## Extensions

Extensions allow applications to add custom data to the context without modifying core types.

### Using Extensions

```python
# Add extension data to snapshot
snapshot = ContextSnapshot(
    ...,
    extensions={
        "skills": {
            "active_skill_ids": ["python", "javascript"],
            "current_level": "intermediate",
        },
        "custom_app_data": {
            "feature_flags": ["new_ui", "beta_features"],
        },
    },
)

# Access in stage
async def execute(self, ctx: StageContext) -> StageOutput:
    skills = ctx.snapshot.extensions.get("skills", {})
    active_skills = skills.get("active_skill_ids", [])
```

### Typed Extensions

For type safety, use the extension registry:

```python
from dataclasses import dataclass, field
from stageflow.extensions import ExtensionRegistry, ExtensionHelper

@dataclass
class SkillsExtension:
    active_skill_ids: list[str] = field(default_factory=list)
    current_level: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SkillsExtension":
        return cls(
            active_skill_ids=data.get("active_skill_ids", []),
            current_level=data.get("current_level"),
        )

# Register
ExtensionRegistry.register("skills", SkillsExtension)

# Use with type safety
skills = ExtensionHelper.get(
    ctx.snapshot.extensions,
    "skills",
    SkillsExtension,
)
if skills:
    print(skills.active_skill_ids)  # IDE knows this is list[str]
```

## Message History

The `messages` field contains conversation history:

```python
from datetime import datetime, timezone
from stageflow.context import Message

messages = [
    Message(
        role="system",
        content="You are a helpful assistant.",
        timestamp=datetime.now(timezone.utc),
        metadata={"source": "config"},
    ),
    Message(
        role="user",
        content="Hello!",
        timestamp=datetime.now(timezone.utc),
    ),
    Message(
        role="assistant",
        content="Hi there! How can I help?",
        timestamp=datetime.now(timezone.utc),
        metadata={"model": "gpt-4"},
    ),
]
```

### Accessing Messages in Stages

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    messages = ctx.snapshot.messages
    
    # Get last N messages
    recent = messages[-5:]
    
    # Filter by role
    user_messages = [m for m in messages if m.role == "user"]
    
    # Convert for LLM
    llm_messages = [
        {"role": m.role, "content": m.content}
        for m in messages
    ]
```

## Routing Decisions

The `routing_decision` field captures routing stage output:

```python
from stageflow.context import RoutingDecision

decision = RoutingDecision(
    agent_id="support_agent",
    pipeline_name="support_pipeline",
    topology="support_fast",
    reason="User asked for help with billing",
)
```

## Best Practices

### 1. Keep Snapshots Immutable

Never try to modify a snapshot. Create new data in stage outputs:

```python
# Bad: Trying to modify snapshot
ctx.snapshot.input_text = "modified"  # This will fail!

# Good: Return new data in output
return StageOutput.ok(processed_text="modified")
```

### 2. Use Descriptive Output Keys

Choose clear, descriptive keys for stage outputs:

```python
# Good
return StageOutput.ok(
    user_profile=profile,
    profile_fetch_duration_ms=elapsed,
)

# Bad
return StageOutput.ok(
    p=profile,
    d=elapsed,
)
```

### 3. Handle Missing Data Gracefully

Always provide defaults or skip when data is missing:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    user_id = ctx.snapshot.user_id
    if not user_id:
        return StageOutput.skip(reason="No user_id provided")
    
    # Continue with valid data...
```

### 4. Document Expected Inputs/Outputs

Make it clear what your stage expects and produces:

```python
class MyStage:
    """Process user input.
    
    Inputs:
        - snapshot.input_text: Raw user input
        - upstream.validated: Boolean from guard stage
    
    Outputs:
        - processed_text: Transformed text
        - word_count: Number of words
    """
```

## Next Steps

- [Interceptors](interceptors.md) — Add middleware for cross-cutting concerns
- [Tools & Agents](tools.md) — Build agent capabilities
- [Examples](../examples/parallel.md) — See data flow in action
