# Testing API Reference

This document provides the API reference for Stageflow's testing utilities, which help you write effective tests for stages, pipelines, and contexts.

## Overview

The testing module provides utilities to create test contexts, mock stages, and set up comprehensive test scenarios for your Stageflow applications.

## create_test_snapshot()

```python
from stageflow.testing import create_test_snapshot
```

Create a ContextSnapshot for testing with sensible defaults.

### Function Signature

```python
def create_test_snapshot(
    *,
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    topology: str | None = "test",
    execution_mode: str | None = "test",
    input_text: str | None = None,
    messages: list[Message] | None = None,
    extensions: Any | None = None,
    **kwargs: Any,
) -> ContextSnapshot
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `pipeline_run_id` | `UUID \| None` | Pipeline run ID (default: new UUID) |
| `request_id` | `UUID \| None` | Request ID (default: new UUID) |
| `session_id` | `UUID \| None` | Session ID (default: new UUID) |
| `user_id` | `UUID \| None` | User ID (default: new UUID) |
| `org_id` | `UUID \| None` | Organization ID (default: None) |
| `interaction_id` | `UUID \| None` | Interaction ID (default: new UUID) |
| `topology` | `str \| None` | Pipeline topology name (default: "test") |
| `execution_mode` | `str \| None` | Execution mode (default: "test") |
| `input_text` | `str \| None` | Input text for the pipeline |
| `messages` | `list[Message] \| None` | Message history |
| `extensions` | `Any \| None` | Extension data (dict or ExtensionBundle) |
| `**kwargs` | `Any` | Additional ContextSnapshot fields |

### Returns

`ContextSnapshot` configured for testing.

### Example Usage

```python
from uuid import uuid4
from stageflow.testing import create_test_snapshot
from stageflow.context import Message

# Basic test snapshot
snapshot = create_test_snapshot(
    input_text="Hello, world!",
    user_id=uuid4(),
)

# With conversation history
messages = [
    Message(role="user", content="What's Python?"),
    Message(role="assistant", content="Python is a programming language..."),
]

snapshot = create_test_snapshot(
    input_text="Can you give me an example?",
    messages=messages,
    topology="chat",
    execution_mode="practice"
)

# With extensions
extensions = {
    "user_preferences": {"language": "en", "theme": "dark"},
    "feature_flags": {"advanced_mode": True}
}

snapshot = create_test_snapshot(
    input_text="Test input",
    extensions=extensions,
    org_id=uuid4()
)
```

---

## create_test_context()

```python
from stageflow.testing import create_test_context
```

Create a StageContext for testing with all necessary components.

### Function Signature

```python
def create_test_context(
    snapshot: ContextSnapshot | None = None,
    config: dict[str, Any] | None = None,
    inputs: StageInputs | None = None,
    ports: CorePorts | LLMPorts | AudioPorts | None = None,
    **kwargs: Any,
) -> StageContext
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `snapshot` | `ContextSnapshot \| None` | Context snapshot (creates default if None) |
| `config` | `dict[str, Any] \| None` | Stage configuration |
| `inputs` | `StageInputs \| None` | Stage inputs (creates from snapshot if None) |
| `ports` | `CorePorts \| LLMPorts \| AudioPorts \| None` | Stage ports |
| `**kwargs` | `Any` | Additional StageContext parameters |

### Returns

`StageContext` configured for testing.

### Example Usage

```python
from stageflow.testing import create_test_context, create_test_snapshot
from stageflow.stages.ports import create_core_ports

# Create with default snapshot
ctx = create_test_context(
    config={"timeout": 30},
    input_text="Test input"
)

# Create with custom snapshot and ports
snapshot = create_test_snapshot(input_text="Hello")
ports = create_core_ports(
    user_message="Hello",
    system_prompt="You are a helpful assistant"
)

ctx = create_test_context(
    snapshot=snapshot,
    ports=ports,
    config={"model": "gpt-4"}
)
```

---

## create_test_pipeline_context()

```python
from stageflow.testing import create_test_pipeline_context
```

Create a PipelineContext for testing pipeline execution.

### Function Signature

```python
def create_test_pipeline_context(
    snapshot: ContextSnapshot | None = None,
    service: str = "test",
    event_sink: EventSink | None = None,
    **kwargs: Any,
) -> PipelineContext
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `snapshot` | `ContextSnapshot \| None` | Context snapshot (creates default if None) |
| `service` | `str` | Service name (default: "test") |
| `event_sink` | `EventSink \| None` | Event sink (uses NoOpEventSink if None) |
| `**kwargs` | `Any` | Additional PipelineContext parameters |

### Returns

`PipelineContext` configured for testing.

### Example Usage

```python
from stageflow.testing import create_test_pipeline_context
from stageflow.events import LoggingEventSink

# Basic pipeline context
ctx = create_test_pipeline_context(
    service="chat",
    input_text="Hello"
)

# With custom event sink
event_sink = LoggingEventSink()
ctx = create_test_pipeline_context(
    service="voice",
    event_sink=event_sink,
    topology="voice_pipeline"
)
```

---

## MockStage

```python
from stageflow.testing import MockStage
```

Mock stage implementation for testing.

### Constructor

```python
MockStage(
    name: str,
    kind: StageKind,
    output: StageOutput | None = None,
    execute_delay: float = 0.0,
    should_fail: bool = False,
    failure_error: str | None = None
)
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Stage name |
| `kind` | `StageKind` | Stage kind |
| `output` | `StageOutput \| None` | Output to return (creates default if None) |
| `execute_delay` | `float` | Delay in seconds before returning (for async testing) |
| `should_fail` | `bool` | Whether to raise an exception |
| `failure_error` | `str \| None` | Error message when failing |

### Example Usage

```python
from stageflow.testing import MockStage
from stageflow.core import StageKind, StageOutput

# Successful mock stage
mock_stage = MockStage(
    name="test_stage",
    kind=StageKind.TRANSFORM,
    output=StageOutput.ok(result="mock_result")
)

# Failing mock stage
failing_stage = MockStage(
    name="failing_stage",
    kind=StageKind.TRANSFORM,
    should_fail=True,
    failure_error="Simulated failure"
)

# Delayed stage (for timeout testing)
delayed_stage = MockStage(
    name="slow_stage",
    kind=StageKind.TRANSFORM,
    execute_delay=2.0
)
```

---

## TestPipelineBuilder

```python
from stageflow.testing import TestPipelineBuilder
```

Utility for building test pipelines with mock stages.

### Constructor

```python
TestPipelineBuilder()
```

### Methods

#### `with_mock_stage(name: str, kind: StageKind, output: StageOutput | None = None) -> TestPipelineBuilder`

Add a mock stage to the pipeline.

**Parameters:**
- `name`: Stage name
- `kind`: Stage kind
- `output`: Stage output (creates default if None)

**Returns:** Self for chaining

#### `with_delay(name: str, delay_seconds: float) -> TestPipelineBuilder`

Add a delay before a stage executes.

**Parameters:**
- `name`: Stage name to delay
- `delay_seconds`: Delay duration

**Returns:** Self for chaining

#### `build() -> Pipeline`

Build the test pipeline.

**Returns:** Configured Pipeline instance

### Example Usage

```python
from stageflow.testing import TestPipelineBuilder
from stageflow.core import StageKind, StageOutput

# Build simple test pipeline
pipeline = (
    TestPipelineBuilder()
    .with_mock_stage("input", StageKind.TRANSFORM, StageOutput.ok(text="processed"))
    .with_mock_stage("process", StageKind.TRANSFORM, StageOutput.ok(result="final"))
    .build()
)

# Build with delays
pipeline = (
    TestPipelineBuilder()
    .with_mock_stage("slow_stage", StageKind.TRANSFORM)
    .with_delay("slow_stage", 1.0)  # 1 second delay
    .build()
)
```

---

## TestFixtures

```python
from stageflow.testing import TestFixtures
```

Common test fixtures and utilities.

### Methods

#### `static_snapshot() -> ContextSnapshot`

Get a static snapshot with fixed UUIDs for reproducible tests.

#### `static_context() -> StageContext`

Get a static context with fixed values.

#### `empty_snapshot() -> ContextSnapshot`

Get an empty snapshot with minimal data.

#### `chat_snapshot(input_text: str) -> ContextSnapshot`

Get a snapshot configured for chat testing.

**Parameters:**
- `input_text`: Chat input text

**Returns:** Chat-configured ContextSnapshot

#### `voice_snapshot(audio_data: bytes) -> ContextSnapshot`

Get a snapshot configured for voice testing.

**Parameters:**
- `audio_data`: Audio data bytes

**Returns:** Voice-configured ContextSnapshot

### Example Usage

```python
from stageflow.testing import TestFixtures

# Use static fixtures for reproducible tests
snapshot = TestFixtures.static_snapshot()
ctx = TestFixtures.static_context()

# Domain-specific fixtures
chat_ctx = TestFixtures.chat_context("Hello, how are you?")
voice_ctx = TestFixtures.voice_context(audio_bytes)
```

---

## Assertion Helpers

```python
from stageflow.testing import assert_stage_output, assert_pipeline_success
```

Utility functions for common test assertions.

### assert_stage_output()

```python
def assert_stage_output(
    output: StageOutput,
    status: StageStatus | None = None,
    contains_data: dict[str, Any] | None = None,
    error_message: str | None = None
) -> None
```

Assert properties about a StageOutput.

**Parameters:**
- `output`: Stage output to check
- `status`: Expected status (optional)
- `contains_data`: Data that should be present (optional)
- `error_message`: Expected error message (optional)

**Raises:** `AssertionError` if assertions fail

### assert_pipeline_success()

```python
def assert_pipeline_success(
    results: dict[str, StageOutput],
    expected_stages: list[str] | None = None
) -> None
```

Assert that a pipeline executed successfully.

**Parameters:**
- `results`: Pipeline execution results
- `expected_stages`: List of expected stage names (optional)

**Raises:** `AssertionError` if pipeline failed

### Example Usage

```python
from stageflow.testing import assert_stage_output, assert_pipeline_success
from stageflow.core import StageStatus

# Test stage output
output = await stage.execute(ctx)
assert_stage_output(
    output,
    status=StageStatus.OK,
    contains_data={"result": "expected_value"}
)

# Test pipeline results
results = await pipeline.run(ctx)
assert_pipeline_success(results, expected_stages=["stage1", "stage2"])
```

---

## Async Test Utilities

```python
from stageflow.testing import run_stage_test, run_pipeline_test
```

Utilities for running async tests.

### run_stage_test()

```python
async def run_stage_test(
    stage: Stage,
    input_text: str | None = None,
    config: dict[str, Any] | None = None,
    timeout: float | None = None
) -> StageOutput
```

Run a stage with test context and handle common test scenarios.

**Parameters:**
- `stage`: Stage to test
- `input_text`: Input text for context
- `config`: Stage configuration
- `timeout`: Execution timeout

**Returns:** Stage execution result

### run_pipeline_test()

```python
async def run_pipeline_test(
    pipeline: Pipeline,
    input_text: str | None = None,
    interceptors: list[BaseInterceptor] | None = None,
    timeout: float | None = None
) -> dict[str, StageOutput]
```

Run a pipeline with test context.

**Parameters:**
- `pipeline`: Pipeline to test
- `input_text`: Input text for context
- `interceptors`: Pipeline interceptors
- `timeout`: Execution timeout

**Returns:** Pipeline execution results

### Example Usage

```python
from stageflow.testing import run_stage_test, run_pipeline_test

# Test a single stage
output = await run_stage_test(
    my_stage,
    input_text="Test input",
    config={"model": "gpt-4"},
    timeout=5.0
)

# Test a pipeline
results = await run_pipeline_test(
    my_pipeline,
    input_text="Hello, world!",
    timeout=10.0
)
```

---

## Usage Examples

### Complete Stage Test

```python
import pytest
from uuid import uuid4
from stageflow.testing import (
    create_test_context,
    create_test_snapshot,
    assert_stage_output,
    run_stage_test
)
from stageflow.core import StageKind, StageStatus, StageOutput

class TestMyStage:
    def test_basic_execution(self):
        """Test basic stage execution."""
        stage = MyStage()
        
        output = await run_stage_test(
            stage,
            input_text="Hello, world!",
            config={"timeout": 30}
        )
        
        assert_stage_output(
            output,
            status=StageStatus.OK,
            contains_data={"result": "processed"}
        )

    def test_with_custom_context(self):
        """Test with custom test context."""
        snapshot = create_test_snapshot(
            input_text="Custom input",
            user_id=uuid4(),
            extensions={"feature_flags": {"advanced": True}}
        )
        
        ctx = create_test_context(
            snapshot=snapshot,
            config={"model": "gpt-4"}
        )
        
        stage = MyStage()
        output = await stage.execute(ctx)
        
        assert output.status == StageStatus.OK
        assert "result" in output.data

    @pytest.mark.asyncio
    async def test_async_behavior(self):
        """Test async stage behavior."""
        stage = AsyncStage()
        
        output = await run_stage_test(
            stage,
            input_text="Async test",
            timeout=5.0
        )
        
        assert output.status == StageStatus.OK
```

### Pipeline Integration Test

```python
import pytest
from stageflow.testing import (
    TestPipelineBuilder,
    create_test_context,
    assert_pipeline_success,
    run_pipeline_test
)
from stageflow.core import StageKind, StageOutput

class TestChatPipeline:
    def test_pipeline_success(self):
        """Test complete pipeline execution."""
        pipeline = (
            TestPipelineBuilder()
            .with_mock_stage("input", StageKind.TRANSFORM, StageOutput.ok(text="processed"))
            .with_mock_stage("llm", StageKind.TRANSFORM, StageOutput.ok(response="Hello!"))
            .with_mock_stage("output", StageKind.TRANSFORM, StageOutput.ok(final="formatted"))
            .build()
        )
        
        results = await run_pipeline_test(
            pipeline,
            input_text="Hello, world!"
        )
        
        assert_pipeline_success(results)
        assert len(results) == 3
        assert results["llm"].data["response"] == "Hello!"

    def test_pipeline_with_dependencies(self):
        """Test pipeline with stage dependencies."""
        pipeline = (
            TestPipelineBuilder()
            .with_mock_stage("stage1", StageKind.TRANSFORM, StageOutput.ok(value="A"))
            .with_mock_stage("stage2", StageKind.TRANSFORM, StageOutput.ok(value="B"))
            .build()
        )
        
        # Add dependencies manually for testing
        pipeline.stages["stage2"].dependencies = ("stage1",)
        
        results = await run_pipeline_test(pipeline, input_text="test")
        
        assert_pipeline_success(results)
        # stage1 should complete before stage2 starts
        assert results["stage1"].data["value"] == "A"
        assert results["stage2"].data["value"] == "B"
```

### Error Handling Test

```python
import pytest
from stageflow.testing import MockStage, run_stage_test
from stageflow.core import StageStatus

class TestErrorHandling:
    def test_stage_failure(self):
        """Test stage failure handling."""
        failing_stage = MockStage(
            name="failing_stage",
            kind=StageKind.TRANSFORM,
            should_fail=True,
            failure_error="Simulated error"
        )
        
        with pytest.raises(Exception, match="Simulated error"):
            await run_stage_test(failing_stage, input_text="test")

    def test_timeout_handling(self):
        """Test timeout handling."""
        slow_stage = MockStage(
            name="slow_stage",
            kind=StageKind.TRANSFORM,
            execute_delay=5.0  # 5 second delay
        )
        
        with pytest.raises(TimeoutError):
            await run_stage_test(slow_stage, input_text="test", timeout=1.0)
```

### Context Testing

```python
from stageflow.testing import create_test_snapshot, create_test_context
from stageflow.context import Message

class TestContextHandling:
    def test_conversation_context(self):
        """Test with conversation history."""
        messages = [
            Message(role="user", content="What's Python?"),
            Message(role="assistant", content="Python is a programming language..."),
        ]
        
        snapshot = create_test_snapshot(
            input_text="Can you give me an example?",
            messages=messages
        )
        
        ctx = create_test_context(snapshot=snapshot)
        
        # Test conversation access
        assert ctx.snapshot.conversation is not None
        assert ctx.snapshot.conversation.message_count == 2
        assert ctx.snapshot.conversation.last_user_message.content == "Can you give me an example?"

    def test_extension_context(self):
        """Test with extensions."""
        extensions = {
            "user_preferences": {"language": "en", "theme": "dark"},
            "feature_flags": {"beta_features": True}
        }
        
        snapshot = create_test_snapshot(
            input_text="Test",
            extensions=extensions
        )
        
        ctx = create_test_context(snapshot=snapshot)
        
        # Test extension access
        assert ctx.snapshot.extensions["user_preferences"]["language"] == "en"
        assert ctx.snapshot.extensions["feature_flags"]["beta_features"] is True
```

---

## Best Practices

1. **Use factory functions** - `create_test_snapshot()` and `create_test_context()` provide consistent test setup
2. **Mock external dependencies** - Use `MockStage` to isolate units under test
3. **Test both success and failure** - Use `should_fail=True` to test error handling
4. **Use static fixtures for reproducibility** - `TestFixtures.static_*` methods provide consistent test data
5. **Assert specific outcomes** - Use assertion helpers for clear test expectations
6. **Test async behavior** - Use timeout parameters to test async edge cases
7. **Keep tests isolated** - Each test should create its own context and not share state
8. **Use descriptive test names** - Clear test names help with test documentation and debugging
