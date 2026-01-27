# Testing Strategies

This guide covers testing patterns for stageflow pipelines, stages, and interceptors.

## Runtime Safety and Hardening

Stageflow provides optional hardening interceptors and helpers for development and production safety:

### UUID Collision and Clock Skew Detection

```python
from stageflow.helpers.uuid_utils import UuidCollisionMonitor, generate_uuid7

# Enable in PipelineRunner
runner = PipelineRunner(
    enable_uuid_monitor=True,
    uuid_monitor_ttl_seconds=300,
)

# Use UUIDv7 for time-ordered IDs
uid = generate_uuid7()  # Falls back to uuid4 if uuid6 unavailable
```

### Memory Tracking

```python
from stageflow.helpers.memory_tracker import MemoryTracker, track_memory

# Enable in PipelineRunner
runner = PipelineRunner(enable_memory_tracker=True)

# Decorator for functions
@track_memory(label="my_stage")
async def expensive_work():
    ...
```

### Deep Immutability Validation

```python
# Enable in PipelineRunner (slow, dev/testing only)
runner = PipelineRunner(enable_immutability_check=True)
```

### Context Size Monitoring

```python
# Enable in PipelineRunner
runner = PipelineRunner(
    enable_context_size_monitor=True,
    # Optionally customize thresholds via ContextSizeInterceptor
)
```

### Compression Utilities

```python
from stageflow.compression import compress, apply_delta

base = {"a": 1, "b": 2}
current = {"a": 1, "b": 3, "c": 4}
delta, metrics = compress(base, current)

rebuilt = apply_delta(base, delta)
assert rebuilt == current
```

## Schema Registry & Typed Outputs

Typed payloads plus schema diffing prevent accidental breaking changes. Stage
authors should:

1. Define a Pydantic model for the stage output payload.
2. Wrap the model with `stageflow.contracts.TypedStageOutput`.
3. Register the contract with the shared registry (typically at module import).
4. Run the `stageflow contracts ...` CLI commands in CI to diff versions.

```python
from pydantic import BaseModel
from stageflow.contracts import TypedStageOutput


class SummarizePayload(BaseModel):
    text: str
    confidence: float


summarize_output = TypedStageOutput(
    SummarizePayload,
    version_factory=TypedStageOutput.timestamp_version,
)


async def execute(self, ctx: StageContext) -> StageOutput:
    payload = await build_payload()
    return summarize_output.ok(payload)
```

Register the schema once so CLI tooling can diff versions:

```python
summarize_output.register_contract(
    stage="summarize",
    version="summary/v2",
    description="Response returned to orchestrator entry point",
)
```

### CLI Workflows

```bash
# Discover contracts in a module and list versions
python -m stageflow.cli contracts list app/pipelines/summarize.py

# Diff two versions and fail CI on breaking changes
python -m stageflow.cli contracts diff \
  --module app/pipelines/summarize.py \
  --stage summarize --from summary/v1 --to summary/v2

# Generate upgrade plan/runbook text for reviewers
python -m stageflow.cli contracts plan-upgrade \
  --module app/pipelines/summarize.py \
  --stage summarize --from summary/v1 --to summary/v2
```

`diff` emits JSON/TTY compatibility reports. `plan-upgrade` augments the diff
with remediation steps pulled from `ContractSuggestion` entries, producing
copy-pastable PR comments.

### Lint Integration

`stageflow cli lint` now enriches `DependencyIssue` errors with structured
contract codes, documentation links, and suggestion text. Enable `--json` to
surface doc URLs in CI dashboards. Add a pre-commit hook that runs:

```bash
python -m stageflow.cli lint pipelines/my_pipeline.py --strict
```

Warnings (isolated stages, orphaned deps) can be escalated via `--strict` to
enforce DAG hygiene before contract registration.

## Testing Pyramid

```
        E2E Tests (10-20)
       /                \
      /  Integration     \
     /   Tests (50-100)   \
    /                      \
   /    Unit Tests          \
  /     (200-500)            \
 /____________________________\
```

- **Unit tests**: Fast, isolated, no external dependencies
- **Integration tests**: Test stage interactions, mock external services
- **E2E tests**: Full user journeys, real services

## Unit Testing Stages

### Basic Stage Test

```python
import pytest
from uuid import uuid4
from stageflow import StageContext, StageOutput, StageStatus, PipelineTimer
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.stages import StageInputs

from my_app.stages import UppercaseStage


@pytest.fixture
def snapshot():
    return ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        ),
        topology="test",
        execution_mode="test",
        input_text="hello world",
    )


@pytest.fixture
def ctx(snapshot):
    return StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="test_stage",
        timer=PipelineTimer(),
    )


@pytest.mark.asyncio
async def test_uppercase_stage(ctx):
    stage = UppercaseStage()
    
    output = await stage.execute(ctx)
    
    assert output.status == StageStatus.OK
    assert output.data["text"] == "HELLO WORLD"
```

### Testing with Dependencies

```python
from unittest.mock import AsyncMock, Mock

@pytest.fixture
def mock_profile_service():
    service = Mock()
    service.get_profile = AsyncMock(return_value=Profile(
        user_id=uuid4(),
        display_name="Alice",
        preferences={"tone": "friendly"},
        goals=["Learn Python"],
    ))
    return service


@pytest.mark.asyncio
async def test_profile_enrich_stage(ctx, mock_profile_service):
    stage = ProfileEnrichStage(profile_service=mock_profile_service)
    
    output = await stage.execute(ctx)
    
    assert output.status == StageStatus.OK
    assert output.data["profile"]["display_name"] == "Alice"
    mock_profile_service.get_profile.assert_called_once_with(ctx.snapshot.user_id)
```

### Testing Skip Conditions

```python
@pytest.mark.asyncio
async def test_profile_enrich_skips_without_user_id():
    snapshot = ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=None,  # No user_id
            org_id=None,
            interaction_id=uuid4(),
        ),
        topology="test",
        execution_mode="test",
    )
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="test_stage",
        timer=PipelineTimer(),
    )
    stage = ProfileEnrichStage()
    
    output = await stage.execute(ctx)
    
    assert output.status == StageStatus.SKIP
    assert "No user_id" in output.data.get("reason", "")
```

### Testing Error Handling

```python
@pytest.mark.asyncio
async def test_llm_stage_handles_api_error(ctx, mock_llm_client):
    mock_llm_client.chat.side_effect = Exception("API Error")
    stage = LLMStage(llm_client=mock_llm_client)
    
    output = await stage.execute(ctx)
    
    assert output.status == StageStatus.FAIL
    assert "API Error" in output.error
```

## Integration Testing Pipelines

### Testing Pipeline Execution

```python
import pytest
from stageflow import Pipeline, StageKind, StageContext
from stageflow.context import ContextSnapshot


@pytest.fixture
def test_pipeline():
    return (
        Pipeline()
        .with_stage("input", MockInputStage, StageKind.TRANSFORM)
        .with_stage("process", MockProcessStage, StageKind.TRANSFORM, dependencies=("input",))
        .with_stage("output", MockOutputStage, StageKind.TRANSFORM, dependencies=("process",))
    )


@pytest.mark.asyncio
async def test_pipeline_execution(test_pipeline, snapshot):
    graph = test_pipeline.build()
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )
    
    results = await graph.run(ctx)
    
    assert "input" in results
    assert "process" in results
    assert "output" in results
    assert all(r.status == StageStatus.OK for r in results.values())
```

### Testing Data Flow

```python
@pytest.mark.asyncio
async def test_data_flows_between_stages(snapshot):
    pipeline = (
        Pipeline()
        .with_stage("producer", ProducerStage, StageKind.TRANSFORM)
        .with_stage("consumer", ConsumerStage, StageKind.TRANSFORM, dependencies=("producer",))
    )
    
    graph = pipeline.build()
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )
    
    results = await graph.run(ctx)
    
    # Verify producer output
    assert results["producer"].data["value"] == 42
    
    # Verify consumer received producer's output
    assert results["consumer"].data["received_value"] == 42
```

### Testing Parallel Execution

```python
import time

@pytest.mark.asyncio
async def test_parallel_stages_run_concurrently(snapshot):
    # Stages that each take 0.1s
    pipeline = (
        Pipeline()
        .with_stage("parallel_a", SlowStage(delay=0.1), StageKind.ENRICH)
        .with_stage("parallel_b", SlowStage(delay=0.1), StageKind.ENRICH)
        .with_stage("aggregate", AggregateStage, StageKind.TRANSFORM, 
                   dependencies=("parallel_a", "parallel_b"))
    )
    
    graph = pipeline.build()
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )
    
    start = time.time()
    results = await graph.run(ctx)
    elapsed = time.time() - start
    
    # Should take ~0.1s (parallel), not ~0.2s (sequential)
    assert elapsed < 0.15
```

### Testing Cancellation

```python
from stageflow.pipeline.dag import UnifiedPipelineCancelled

@pytest.mark.asyncio
async def test_pipeline_cancellation(snapshot):
    pipeline = (
        Pipeline()
        .with_stage("guard", CancellingGuardStage, StageKind.GUARD)
        .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("guard",))
    )
    
    graph = pipeline.build()
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )
    
    with pytest.raises(UnifiedPipelineCancelled) as exc_info:
        await graph.run(ctx)
    
    assert exc_info.value.stage == "guard"
    assert "guard" in exc_info.value.results
    assert "process" not in exc_info.value.results
```

## Testing Interceptors

### Basic Interceptor Test

```python
from stageflow import BaseInterceptor, InterceptorResult
from stageflow.stages.context import PipelineContext

@pytest.fixture
def mock_pipeline_ctx():
    ctx = Mock(spec=PipelineContext)
    ctx.pipeline_run_id = uuid4()
    ctx.user_id = uuid4()
    ctx.data = {}
    return ctx


@pytest.mark.asyncio
async def test_rate_limit_allows_requests(mock_pipeline_ctx):
    interceptor = RateLimitInterceptor(max_requests=10)
    
    result = await interceptor.before("test_stage", mock_pipeline_ctx)
    
    assert result is None  # None means continue


@pytest.mark.asyncio
async def test_rate_limit_blocks_excess(mock_pipeline_ctx):
    interceptor = RateLimitInterceptor(max_requests=2)
    
    # First two pass
    await interceptor.before("test_stage", mock_pipeline_ctx)
    await interceptor.before("test_stage", mock_pipeline_ctx)
    
    # Third blocked
    result = await interceptor.before("test_stage", mock_pipeline_ctx)
    
    assert result is not None
    assert result.stage_ran is False
```

### Testing Error Handling

```python
from stageflow import ErrorAction

@pytest.mark.asyncio
async def test_retry_interceptor_retries_transient_errors(mock_pipeline_ctx):
    interceptor = RetryInterceptor(max_retries=3)
    
    action = await interceptor.on_error(
        "test_stage",
        TimeoutError("Connection timed out"),
        mock_pipeline_ctx,
    )
    
    assert action == ErrorAction.RETRY


@pytest.mark.asyncio
async def test_retry_interceptor_fails_permanent_errors(mock_pipeline_ctx):
    interceptor = RetryInterceptor(max_retries=3)
    
    action = await interceptor.on_error(
        "test_stage",
        ValueError("Invalid input"),
        mock_pipeline_ctx,
    )
    
    assert action == ErrorAction.FAIL
```

## Testing Tools

### Basic Tool Test

```python
from stageflow.tools import ToolInput, ToolOutput

@pytest.fixture
def tool_input():
    return ToolInput(
        action_id=uuid4(),
        tool_name="greet",
        payload={"name": "Alice"},
    )


@pytest.mark.asyncio
async def test_greet_tool(tool_input):
    tool = GreetTool()
    
    output = await tool.execute(tool_input, ctx={})
    
    assert output.success
    assert output.data["message"] == "Hello, Alice!"
```

### Testing Tool Registry

```python
from stageflow.tools import get_tool_registry

@pytest.fixture
def registry():
    reg = get_tool_registry()
    reg.register(GreetTool())
    reg.register(CalculatorTool())
    yield reg
    # Cleanup if needed


def test_registry_finds_tool(registry):
    tool = registry.get("greet")
    assert tool is not None
    assert tool.name == "greet"


def test_registry_finds_by_action_type(registry):
    tool = registry.get_by_action_type("GREET")
    assert tool is not None
```

## Contract Tests

### Stage Contract

```python
@pytest.mark.asyncio
async def test_stage_returns_stage_output(ctx):
    """All stages must return StageOutput."""
    stage = MyStage()
    
    output = await stage.execute(ctx)
    
    assert isinstance(output, StageOutput)
    assert output.status in StageStatus


@pytest.mark.asyncio
async def test_stage_has_required_attributes():
    """All stages must have name and kind."""
    stage = MyStage()
    
    assert hasattr(stage, "name")
    assert hasattr(stage, "kind")
    assert isinstance(stage.name, str)
    assert isinstance(stage.kind, StageKind)
```

### Pipeline Contract

```python
def test_pipeline_has_no_cycles():
    """Pipeline must be a valid DAG."""
    pipeline = create_my_pipeline()
    
    # build() validates the DAG
    graph = pipeline.build()
    
    assert len(graph.stage_specs) > 0


def test_pipeline_dependencies_exist():
    """All dependencies must reference existing stages."""
    pipeline = create_my_pipeline()
    stage_names = set(pipeline.stages.keys())
    
    for spec in pipeline.stages.values():
        for dep in spec.dependencies:
            assert dep in stage_names, f"Missing dependency: {dep}"
```

## Testing Utilities

Stageflow provides built-in testing utilities in `stageflow.testing`:

### create_test_snapshot

Create a `ContextSnapshot` with sensible defaults:

```python
from stageflow.testing import create_test_snapshot

# Minimal - all UUIDs auto-generated
snapshot = create_test_snapshot()

# With specific values
snapshot = create_test_snapshot(
    input_text="Hello, world!",
    user_id=uuid4(),
    execution_mode="practice",
)
```

### create_test_stage_context

Create a `StageContext` for testing stages:

```python
from stageflow.testing import create_test_stage_context
from stageflow import StageOutput

# Simple context
ctx = create_test_stage_context(input_text="Test input")

# With prior stage outputs
ctx = create_test_stage_context(
    prior_outputs={
        "stage_a": StageOutput.ok(value=42),
        "router": StageOutput.ok(route="general"),
    },
)

# Access inputs via the new type-safe property
value = ctx.inputs.get("value")  # Returns 42
route = ctx.inputs.get_from("router", "route")  # Returns "general"
```

### create_test_pipeline_context

Create a `PipelineContext` for testing interceptors:

```python
from stageflow.testing import create_test_pipeline_context

ctx = create_test_pipeline_context(
    user_id=uuid4(),
    data={"key": "value"},
    topology="chat_fast",
)
```

### Snapshot Validation

Validate snapshots to catch issues early:

```python
from stageflow.testing import (
    validate_snapshot,
    validate_snapshot_strict,
    snapshot_from_dict_strict,
)

# Check validity with detailed errors
result = validate_snapshot(snapshot, require_user_id=True)
if not result:
    for error in result.errors:
        print(f"{error.field}: {error.message}")

# Raise on invalid (for tests)
snapshot = validate_snapshot_strict(snapshot, require_user_id=True)

# Create from dict with validation
snapshot = snapshot_from_dict_strict(
    json_data,
    require_pipeline_run_id=True,
)
```

---

## Fixtures and Helpers

### Using Testing Utilities in Fixtures

```python
# conftest.py
import pytest
from uuid import uuid4
from stageflow.testing import (
    create_test_snapshot,
    create_test_stage_context,
    create_test_pipeline_context,
)


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()


@pytest.fixture
def snapshot(user_id, session_id):
    return create_test_snapshot(
        user_id=user_id,
        session_id=session_id,
    )


@pytest.fixture
def ctx(snapshot):
    return create_test_stage_context(snapshot=snapshot)


@pytest.fixture
def ctx_with_input():
    def _create(input_text: str, **kwargs):
        return create_test_stage_context(
            input_text=input_text,
            **kwargs,
        )
    return _create


@pytest.fixture
def pipeline_ctx(user_id, session_id):
    return create_test_pipeline_context(
        user_id=user_id,
        session_id=session_id,
    )
```

### Legacy Fixtures (Manual Creation)

```python
# conftest.py
import pytest
from uuid import uuid4
from stageflow import StageContext
from stageflow.context import ContextSnapshot


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()


@pytest.fixture
def base_snapshot(user_id, session_id):
    return ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=session_id,
            user_id=user_id,
            org_id=uuid4(),
            interaction_id=uuid4(),
        ),
        topology="test",
        execution_mode="test",
    )


@pytest.fixture
def ctx(base_snapshot):
    return StageContext(
        snapshot=base_snapshot,
        inputs=StageInputs(snapshot=base_snapshot),
        stage_name="test_stage",
        timer=PipelineTimer(),
    )


@pytest.fixture
def ctx_with_input(base_snapshot):
    def _create(input_text: str):
        snapshot = ContextSnapshot(
            run_id=base_snapshot.run_id,
            topology=base_snapshot.topology,
            execution_mode=base_snapshot.execution_mode,
            input_text=input_text,
        )
        return StageContext(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="test_stage",
            timer=PipelineTimer(),
        )
    return _create
```

### Mock Services

```python
# test_helpers.py
from unittest.mock import AsyncMock, Mock

def create_mock_llm_client(response: str = "Mock response"):
    client = Mock()
    client.chat = AsyncMock(return_value=response)
    return client


def create_mock_profile_service(display_name: str = "Test User"):
    service = Mock()
    service.get_profile = AsyncMock(return_value=Profile(
        user_id=uuid4(),
        display_name=display_name,
        preferences={},
        goals=[],
    ))
    return service
```

## Best Practices

### 1. Test Behavior, Not Implementation

```python
# Good: Tests behavior
@pytest.mark.asyncio
async def test_uppercase_transforms_text(ctx):
    stage = UppercaseStage()
    output = await stage.execute(ctx)
    assert output.data["text"] == ctx.snapshot.input_text.upper()

# Bad: Tests implementation details
@pytest.mark.asyncio
async def test_uppercase_calls_upper_method(ctx):
    with patch.object(str, "upper") as mock_upper:
        stage = UppercaseStage()
        await stage.execute(ctx)
        mock_upper.assert_called()
```

### 2. Use Descriptive Test Names

```python
# Good
def test_profile_enrich_skips_when_user_id_missing(): ...
def test_llm_stage_retries_on_timeout(): ...
def test_guard_cancels_pipeline_on_blocked_content(): ...

# Bad
def test_stage(): ...
def test_error(): ...
def test_1(): ...
```

### 3. Keep Tests Fast

```python
# Good: Mock slow operations
@pytest.mark.asyncio
async def test_llm_stage(mock_llm_client):
    mock_llm_client.chat = AsyncMock(return_value="response")
    stage = LLMStage(llm_client=mock_llm_client)
    # Fast test

# Bad: Real API calls
@pytest.mark.asyncio
async def test_llm_stage():
    stage = LLMStage(llm_client=RealLLMClient())
    # Slow, flaky, costs money
```

### 4. Test Edge Cases

```python
@pytest.mark.asyncio
async def test_handles_empty_input(ctx_with_input):
    ctx = ctx_with_input("")
    stage = ProcessStage()
    output = await stage.execute(ctx)
    assert output.status == StageStatus.OK


@pytest.mark.asyncio
async def test_handles_very_long_input(ctx_with_input):
    ctx = ctx_with_input("x" * 100000)
    stage = ProcessStage()
    output = await stage.execute(ctx)
    # Verify handling
```

### 5. Isolate Tests

```python
# Good: Each test is independent
@pytest.fixture
def fresh_registry():
    from stageflow.tools import ToolRegistry
    return ToolRegistry()

# Bad: Tests share state
registry = get_tool_registry()  # Global state
```

### 6. Test Streaming Telemetry

Validate that `ChunkQueue` and `StreamingBuffer` emit events under backpressure and underrun conditions.

```python
import asyncio
import pytest
from stageflow.helpers import ChunkQueue, StreamingBuffer


@pytest.mark.asyncio
async def test_chunk_queue_emits_drop_and_throttle_events():
    events = []

    def emitter(event_type: str, attrs: dict | None = None):
        events.append((event_type, attrs or {}))

    queue = ChunkQueue(maxsize=1, event_emitter=emitter)
    await queue.put("a")
    # This put causes backpressure or drop
    await queue.put("b", block=False) if hasattr(queue, "put") else None
    await queue.close()

    assert any(e[0] == "stream.chunk_dropped" for e in events) or any(e[0] == "stream.producer_blocked" for e in events)
    assert any(e[0] == "stream.queue_closed" for e in events)


@pytest.mark.asyncio
async def test_streaming_buffer_overflow_and_recovery_events():
    events = []

    def emitter(event_type: str, attrs: dict | None = None):
        events.append((event_type, attrs or {}))

    buf = StreamingBuffer(capacity_ms=50, event_emitter=emitter)
    # Simulate overflow/underrun by alternating writes and reads
    buf.write(b"x" * 4096, duration_ms=100)  # overflow likely
    chunk = buf.read(duration_ms=100)        # underrun or recovery

    assert any(e[0] in {"stream.buffer_overflow", "stream.buffer_underrun", "stream.buffer_recovered"} for e in events)
```

### 7. Test Analytics Overflow Callbacks

Ensure `BufferedExporter` invokes the overflow callback on pressure and drops.

```python
from stageflow.helpers import BufferedExporter, AnalyticsEvent


def test_buffered_exporter_overflow_callback(monkeypatch):
    calls: list[tuple[int, int]] = []

    def on_overflow(dropped: int, size: int) -> None:
        calls.append((dropped, size))

    exporter = BufferedExporter(
        sink=None,  # use no-op/monkeypatched sink
        on_overflow=on_overflow,
        high_water_mark=0.01,
    )

    # Flood the buffer
    for i in range(1000):
        exporter.submit(AnalyticsEvent(type="t", data={"i": i}))

    # Either high-water warnings (-1) or real drops (>0) should be observed
    assert any(dropped == -1 or dropped > 0 for dropped, _ in calls)
```

### 8. Test Tool Parsing Helper

`ToolRegistry.parse_and_resolve` should parse OpenAI/Anthropic tool call shapes and resolve to registered tools.

```python
import pytest
from stageflow.tools import ToolRegistry, BaseTool, ToolInput, ToolOutput


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo args"
    action_type = "ECHO"

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        return ToolOutput(success=True, data=input.action.payload)


def test_parse_and_resolve_openai():
    reg = ToolRegistry()
    reg.register(EchoTool())

    tool_calls = [{
        "id": "call_1",
        "function": {"name": "echo", "arguments": "{\"msg\": \"hi\"}"},
    }]

    resolved, unresolved = reg.parse_and_resolve(tool_calls)
    assert len(resolved) == 1 and len(unresolved) == 0
    assert resolved[0].name == "echo"
    assert resolved[0].arguments["msg"] == "hi"
```

## Next Steps

- [Extensions](extensions.md) — Add custom context data
- [Error Handling](errors.md) — Test error scenarios
- [Observability](../guides/observability.md) — Test event emission
