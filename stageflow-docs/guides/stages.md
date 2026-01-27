# Building Stages

Stages are the fundamental building blocks of stageflow pipelines. This guide covers everything you need to know about creating effective stages.

## The Stage Protocol

Every stage must implement the `Stage` protocol:

```python
from stageflow import StageContext, StageKind, StageOutput

class MyStage:
    name: str = "my_stage"      # Unique identifier
    kind: StageKind = StageKind.TRANSFORM  # Categorization
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute the stage logic."""
        ...
```

## Stage Kinds

Choose the appropriate kind based on what your stage does:

### TRANSFORM

Stages that change data form or generate new data.

```python
from stageflow.helpers import LLMResponse

class TextToUpperStage:
    name = "text_to_upper"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.snapshot.input_text or ""
        llm = LLMResponse(
            content=text.upper(),
            model="demo-mini",
            provider="mock",
            input_tokens=len(text),
            output_tokens=len(text),
        )
        return StageOutput.ok(text=llm.content, llm=llm.to_dict())
```

**Use for**: STT, TTS, LLM calls, text processing, data transformation.

### ENRICH

Stages that add contextual information without transforming the core data.

```python
class ProfileEnrichStage:
    name = "profile_enrich"
    kind = StageKind.ENRICH

    def __init__(self, profile_service):
        self.profile_service = profile_service

    async def execute(self, ctx: StageContext) -> StageOutput:
        user_id = ctx.snapshot.user_id
        if not user_id:
            return StageOutput.skip(reason="No user_id provided")
        
        profile = await self.profile_service.get_profile(user_id)
        return StageOutput.ok(
            profile={
                "display_name": profile.display_name,
                "preferences": profile.preferences,
            }
        )
```

**Use for**: Profile lookup, memory retrieval, document fetching, external data enrichment.

### ROUTE

Stages that make routing decisions about which path to take.

```python
class RouterStage:
    name = "router"
    kind = StageKind.ROUTE

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        
        # Simple keyword-based routing
        if "help" in input_text.lower():
            route = "support"
        elif "buy" in input_text.lower():
            route = "sales"
        else:
            route = "general"
        
        return StageOutput.ok(
            route=route,
            confidence=0.9,
        )
```

**Use for**: Intent classification, dispatcher logic, path selection.

### GUARD

Stages that validate input or output, potentially blocking execution.

```python
class InputGuardStage:
    name = "input_guard"
    kind = StageKind.GUARD

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        
        # Check for blocked content
        blocked_words = ["spam", "abuse"]
        for word in blocked_words:
            if word in input_text.lower():
                return StageOutput.cancel(
                    reason=f"Blocked content detected: {word}",
                    data={"blocked": True},
                )
        
        return StageOutput.ok(validated=True)
```

**Use for**: Input validation, output filtering, policy enforcement, safety checks.

### WORK

Stages that perform side effects without producing user-facing output.

```python
class PersistStage:
    name = "persist"
    kind = StageKind.WORK

    def __init__(self, db):
        self.db = db

    async def execute(self, ctx: StageContext) -> StageOutput:
        response = ctx.inputs.get("response")
        
        if response:
            await self.db.save_interaction(
                session_id=ctx.snapshot.session_id,
                response=response,
            )
        
        return StageOutput.ok(persisted=True)
```

**Use for**: Database writes, analytics, notifications, background processing.

### AGENT

Stages that implement interactive agent logic, often with tool execution.

```python
from stageflow.tools import ToolInput


class ChatAgentStage:
    name = "chat_agent"
    kind = StageKind.AGENT

    def __init__(self, llm_client, tool_registry):
        self.llm_client = llm_client
        self.tool_registry = tool_registry

    async def execute(self, ctx: StageContext) -> StageOutput:
        messages = list(ctx.snapshot.messages)
        if ctx.snapshot.input_text:
            messages.append({"role": "user", "content": ctx.snapshot.input_text})
        
        # Call LLM
        response = await self.llm_client.chat(messages)
        
        # Parse + resolve tool calls (LLM-native format)
        resolved, unresolved = self.tool_registry.parse_and_resolve(response.tool_calls)

        tool_results = []
        for call in resolved:
            tool_input = ToolInput(action=call.arguments)
            result = await call.tool.execute(tool_input, ctx={"call_id": call.call_id})
            tool_results.append(result)
        
        return StageOutput.ok(
            response=response.content,
            tool_results=tool_results,
        )
```

**Use for**: Conversational agents, coaches, interactive assistants.

## Reading Input Data

### From the Snapshot

The `ContextSnapshot` contains immutable input data:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # User input
    input_text = ctx.snapshot.input_text
    
    # Identity
    user_id = ctx.snapshot.user_id
    session_id = ctx.snapshot.session_id
    org_id = ctx.snapshot.org_id
    
    # Configuration
    topology = ctx.snapshot.topology
    execution_mode = ctx.snapshot.execution_mode
    
    # Message history
    messages = ctx.snapshot.messages
    
    # Enrichments (if populated by earlier stages)
    profile = ctx.snapshot.profile
    memory = ctx.snapshot.memory
    documents = ctx.snapshot.documents
```

### From Upstream Stages (StageInputs)

Access outputs from dependency stages via `StageInputs`:

```python
from stageflow.stages.inputs import StageInputs

async def execute(self, ctx: StageContext) -> StageOutput:
    # Get specific key from any upstream stage (searches all)
    processed_text = ctx.inputs.get("text")
    
    # Get from a specific stage (preferred - explicit dependency)
    router_decision = ctx.inputs.get_from("router", "route", default="general")
    
    # Check if a stage has output
    if ctx.inputs.has_output("validator"):
        validator_output = ctx.inputs.get_output("validator")
    
    # Access injected services through ports
    if ctx.inputs.ports and ctx.inputs.ports.llm_provider:
        response = await ctx.inputs.ports.llm_provider.chat(...)
        # Wrap raw provider payloads with standardized responses
        from stageflow.helpers import LLMResponse
        llm = LLMResponse(
            content=response.content,
            model=response.model,
            provider=response.provider,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
        return StageOutput.ok(message=llm.content, llm=llm.to_dict())
```

#### Key Validation and Error Handling

`StageInputs` methods validate that keys are provided and are non-empty strings. This prevents silent data-loss bugs from accidental `None` or incorrect key usage.

```python
# These will raise TypeError/ValueError with clear messages:
ctx.inputs.get(None)                    # TypeError: StageInputs key must be provided
ctx.inputs.get_from("stage", None)       # TypeError: StageInputs key must be a string  
ctx.inputs.require_from("stage", "")     # ValueError: StageInputs key cannot be empty

# Correct usage:
text = ctx.inputs.get("text")           # Returns None if not found
route = ctx.inputs.get_from("router", "route", default="general")
required = ctx.inputs.require_from("auth", "token")  # Raises KeyError if missing
```

**Error Types:**
- `TypeError` - Key is `None` or not a string
- `ValueError` - Key is an empty string
- `KeyError` - Required key is missing (from `require_from`)
- `UndeclaredDependencyError` - Stage not in declared dependencies (when strict=True)

### Injected Services (Modular Ports)

Stages can access injected services through modular ports:

```python
from stageflow.stages.ports import CorePorts, LLMPorts, AudioPorts

async def execute(self, ctx: StageContext) -> StageOutput:
    # Access specific port types
    ports = ctx.inputs.ports or CorePorts()
    llm_ports: LLMPorts | None = getattr(ctx.inputs.ports, "llm", None) if ctx.inputs.ports else None
    audio_ports: AudioPorts | None = getattr(ctx.inputs.ports, "audio", None) if ctx.inputs.ports else None
    
    # Database access (CorePorts)
    if ports.db:
        await ports.db.save_interaction(...)
    
    # LLM operations (LLMPorts)
    if llm_ports and llm_ports.llm_provider:
        response = await llm_ports.llm_provider.chat(messages)
    
    # Token streaming (LLMPorts)
    if llm_ports and llm_ports.send_token:
        await llm_ports.send_token("Hello")
    
    # Audio streaming (AudioPorts)
    if audio_ports and audio_ports.send_audio_chunk:
        await audio_ports.send_audio_chunk(audio_bytes, "wav", 0, False)
    
    # Status updates (CorePorts)
    if ports.send_status:
        await ports.send_status(ctx.stage_name, "completed", {"data": result})
```

### Creating Ports

When creating stages, inject the specific ports needed:

```python
from stageflow.stages.ports import (
    create_core_ports,
    create_llm_ports,
    create_audio_ports,
    create_stage_inputs,
)

# Create modular ports
inputs = create_stage_inputs(
    snapshot=snapshot,
    prior_outputs=prev_outputs,
    ports=CorePorts(
        db=db_session,
        send_status=status_callback,
    ),
)

# For LLM stage
inputs = create_stage_inputs(
    snapshot=snapshot,
    prior_outputs=prev_outputs,
    ports=LLMPorts(
        llm_provider=my_llm,
        send_token=token_callback,
    ),
)

# For audio stage
inputs = create_stage_inputs(
    snapshot=snapshot,
    prior_outputs=prev_outputs,
    ports=AudioPorts(
        tts_provider=my_tts,
        stt_provider=my_stt,
    ),
)
```


### Supplying Stage Configuration

Stages typically receive configuration through their constructor or via injected ports rather than through the context. For example:

```python
class SummarizeStage:
    def __init__(self, *, default_model: str = "gpt-4o-mini"):
        self.default_model = default_model

    async def execute(self, ctx: StageContext) -> StageOutput:
        model = self.default_model
        elapsed = ctx.timer.elapsed_ms()
        ...
```

## Producing Output

### Success Output

Return data that downstream stages can consume:

```python
from stageflow.helpers import TTSResponse

audio = await synthesize_audio(...)
tts = TTSResponse(
    audio=audio,
    duration_ms=1250,
    sample_rate=24000,
    provider="mock_tts",
    model="demo-voice",
)

return StageOutput.ok(
    text="processed result",
    metadata={"source": "transform"},
    tts=tts.to_dict(),
    count=42,
)
```

### Typed Outputs & Schema Versions

For structured payloads, wrap `StageOutput.ok(...)` with
`stageflow.contracts.TypedStageOutput`. This helper validates data using a
Pydantic model and tags outputs with schema versions for downstream safety.

```python
from pydantic import BaseModel, Field
from stageflow.contracts import TypedStageOutput


class SummaryPayload(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1)


summary_output = TypedStageOutput(
    SummaryPayload,
    default_version="summary/v1",  # optional fallback
)


class SummarizeStage:
    name = "summarize"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        payload = SummaryPayload(
            text="processed result",
            confidence=0.94,
        )
        return summary_output.ok(payload)
```

Typed helpers support async factories and timestamped versions:

```python
typed = TypedStageOutput(
    SummaryPayload,
    version_factory=TypedStageOutput.timestamp_version,
)

output = await typed.ok_async(build_payload)
```

Register contracts with the shared registry to enable compatibility diffing
and CLI linting:

```python
typed.register_contract(
    stage="summarize",
    description="Summaries returned to orchestrator",
)

report = registry.diff("summarize", from_version="summary/v1", to_version="summary/v2")
if not report.is_compatible:
    raise RuntimeError(report.summary())
```

See [Schema Registry & Typed Outputs](../advanced/testing.md#schema-registry--typed-outputs)
for CLI commands and compatibility guardrails.

### Skip Output

Skip the stage without error (useful for conditional stages):

```python
if not ctx.snapshot.user_id:
    return StageOutput.skip(reason="No user_id provided")
```

### Cancel Output

Stop the entire pipeline gracefully:

```python
if is_blocked:
    return StageOutput.cancel(
        reason="Content policy violation",
        data={"blocked": True, "policy": "safety"},
    )
```

### Fail Output

Indicate an error occurred:

```python
try:
    result = await external_service.call()
except ServiceError as e:
    return StageOutput.fail(
        error=f"Service call failed: {e}",
        data={"error_type": type(e).__name__},
    )
```

## Stage Initialization

### Stateless Stages

Simple stages can be defined as classes:

```python
class EchoStage:
    name = "echo"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(echo=ctx.snapshot.input_text)
```

### Stages with Dependencies

Inject dependencies via `__init__`:

```python
class LLMStage:
    name = "llm"
    kind = StageKind.TRANSFORM

    def __init__(self, llm_client, model: str = "gpt-4"):
        self.llm_client = llm_client
        self.model = model

    async def execute(self, ctx: StageContext) -> StageOutput:
        response = await self.llm_client.chat(
            messages=[...],
            model=self.model,
        )
        return StageOutput.ok(response=response)
```

### Using Instances vs Classes

You can register either a class or an instance:

```python
# Register a class (instantiated per execution)
pipeline.with_stage("echo", EchoStage, StageKind.TRANSFORM)

# Register an instance (reused across executions)
llm_stage = LLMStage(llm_client=my_client, model="gpt-4")
pipeline.with_stage("llm", llm_stage, StageKind.TRANSFORM)
```

## Emitting Events

Stages can emit events for observability:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Emit a custom event
    ctx.emit_event("custom.processing_started", {"step": 1})
    
    # Do work...
    
    ctx.emit_event("custom.processing_completed", {"step": 1, "duration_ms": 100})

    # Emit streaming telemetry by wiring ChunkQueue/StreamingBuffer emitters
    from stageflow.helpers import ChunkQueue
    queue = ChunkQueue(event_emitter=ctx.emit_event)
    await queue.put("sample")
    await queue.close()
    
    return StageOutput.ok(...)
```

## Adding Artifacts

Stages can produce artifacts (UI payloads, files, etc.):

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Add an artifact
    ctx.add_artifact(
        type="chart",
        payload={
            "chart_type": "bar",
            "data": [1, 2, 3, 4, 5],
            "title": "Results",
        },
    )
    
    return StageOutput.ok(chart_generated=True)
```

## Best Practices

### 1. Keep Stages Focused

Each stage should do one thing well. If a stage is doing too much, split it.

```python
# Bad: One stage doing everything
class DoEverythingStage:
    async def execute(self, ctx):
        # Validate, enrich, transform, persist...
        pass

# Good: Separate concerns
class ValidateStage: ...
class EnrichStage: ...
class TransformStage: ...
class PersistStage: ...
```

### 2. Handle Missing Data Gracefully

Always check for missing data and handle appropriately:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    user_id = ctx.snapshot.user_id
    if not user_id:
        return StageOutput.skip(reason="No user_id")
    
    # Continue with valid data...
```

### 3. Use Appropriate Output Types

- `ok()` — Stage completed successfully with data
- `skip()` — Stage was skipped (not an error)
- `cancel()` — Stop the pipeline (not an error)
- `fail()` — Stage failed (is an error)

### 4. Log Meaningful Information

Use structured logging for debugging:

```python
import logging

logger = logging.getLogger(__name__)

async def execute(self, ctx: StageContext) -> StageOutput:
    logger.info(
        "Processing request",
        extra={
            "user_id": str(ctx.snapshot.user_id),
            "input_length": len(ctx.snapshot.input_text or ""),
            "telemetry": ctx.inputs.get("llm", {}).get("latency_ms"),
        },
    )
```

### 5. Make Stages Testable

Design stages to be easily testable:

```python
# Stage with injected dependency
class MyStage:
    def __init__(self, service):
        self.service = service

# Easy to test with mock
def test_my_stage():
    mock_service = Mock()
    stage = MyStage(service=mock_service)
    # Test...
```

## Next Steps

- [Composing Pipelines](pipelines.md) — Combine stages into complex workflows
- [Context & Data Flow](context.md) — Deep dive into data passing
- [Examples](../examples/simple.md) — See complete working examples
- [Observability](observability.md) — Capture streaming telemetry and analytics overflow callbacks
