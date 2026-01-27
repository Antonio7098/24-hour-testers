# Tools & Approval Workflows Guide

This guide covers implementing tool execution, human-in-the-loop (HITL) approvals, and agent workflows in Stageflow.

## Overview

Agent pipelines often need to:
- **Execute tools**: Call external APIs, databases, or services
- **Require approval**: Get human confirmation for sensitive actions
- **Handle failures**: Retry, rollback, or escalate on errors
- **Track execution**: Log tool calls for audit and debugging

Stageflow provides:
- `ToolRegistry` for tool discovery and management
- `ToolExecutor` and `AdvancedToolExecutor` for execution
- `ApprovalService` for HITL workflows
- `UndoStore` for rollback support

## Tool Registry

### Defining Tools

```python
from stageflow.tools import ToolRegistry, ToolDefinition, ToolInput

# Create registry
registry = ToolRegistry()

# Define a tool
@registry.register
def calculator(expression: str) -> dict:
    """Evaluate a mathematical expression."""
    result = eval(expression)  # In production, use safe_eval
    return {"result": result}

# Or define with ToolDefinition
registry.register_tool(
    ToolDefinition(
        name="weather",
        description="Get current weather for a location",
        parameters={
            "location": {"type": "string", "description": "City name"},
            "units": {"type": "string", "enum": ["celsius", "fahrenheit"]},
        },
        required=["location"],
        handler=get_weather_handler,
    )
)
```

### Tool Input Validation

```python
from stageflow.tools import ToolInput

# Create validated input
tool_input = ToolInput(
    name="weather",
    arguments={"location": "San Francisco", "units": "celsius"},
)

# Validate against schema
if registry.validate_input(tool_input):
    result = await registry.execute(tool_input)
```

## Tool Executor

### Basic Execution

```python
from stageflow.tools import ToolExecutor

executor = ToolExecutor(registry=registry)

# Execute a tool
result = await executor.execute(
    tool_name="calculator",
    arguments={"expression": "2 + 2"},
)

if result.success:
    print(f"Result: {result.output}")
else:
    print(f"Error: {result.error}")
```

### Advanced Executor with Retries

```python
from stageflow.tools import AdvancedToolExecutor

executor = AdvancedToolExecutor(
    registry=registry,
    max_retries=3,
    retry_delay_ms=1000,
    timeout_ms=5000,
)

# Execute with automatic retries
result = await executor.execute(
    tool_name="external_api",
    arguments={"query": "data"},
)
```

### Tool Execution Stage

```python
class ToolExecutionStage:
    """Stage that executes tools from LLM decisions."""

    name = "tool_exec"
    kind = StageKind.WORK

    def __init__(self, executor: ToolExecutor):
        self._executor = executor

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get tool calls from LLM stage and resolve via registry helper
        tool_calls = ctx.inputs.get_from("llm", "tool_calls", [])
        resolved, unresolved = self._executor.registry.parse_and_resolve(tool_calls)

        for call in unresolved:
            ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})

        tool_calls = resolved

        if not tool_calls:
            return StageOutput.skip(reason="No tool calls")

        results = []
        for call in tool_calls:
            result = await self._executor.execute(
                tool_name=call.name,
                arguments=call.arguments,
            )
            results.append({
                "tool": call.name,
                "success": result.success,
                "output": result.output,
                "error": result.error,
            })

            # Emit event for observability
            if ctx.event_sink:
                ctx.event_sink.try_emit(
                    type=f"tool.{call['name']}.executed",
                    data={"success": result.success},
                )

        return StageOutput.ok(
            tool_results=results,
            all_succeeded=all(r["success"] for r in results),
        )
```

## Approval Workflows

### Approval Service

```python
from stageflow.tools import ApprovalService, ApprovalRequest

# Create approval service
approval_service = ApprovalService(
    store=approval_store,  # Persistent storage
    timeout_seconds=300,   # 5 minute timeout
)

# Request approval
request = ApprovalRequest(
    action="delete_user",
    resource_id="user-123",
    requester_id=str(ctx.snapshot.user_id),
    context={"reason": "User requested account deletion"},
)

approval_id = await approval_service.request_approval(request)
```

### Approval Stage Pattern

```python
class ApprovalRequiredStage:
    """Stage that requires human approval before proceeding."""

    name = "approval"
    kind = StageKind.GUARD

    def __init__(self, approval_service: ApprovalService):
        self._service = approval_service

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get action requiring approval
        action = ctx.inputs.get_from("router", "action")
        if not action or action.get("approval_required") is False:
            return StageOutput.ok(approval_needed=False)

        # Create approval request
        request = ApprovalRequest(
            action=action["name"],
            resource_id=action.get("resource_id"),
            requester_id=str(ctx.snapshot.user_id),
            context=action.get("context", {}),
        )

        # Request and wait for approval
        try:
            approval = await self._service.request_and_wait(request)

            if approval.approved:
                return StageOutput.ok(
                    approved=True,
                    approver_id=approval.approver_id,
                    approval_time=approval.approved_at.isoformat(),
                )
            else:
                return StageOutput.cancel(
                    cancel_reason=f"Approval denied: {approval.reason}",
                    approved=False,
                )
        except TimeoutError:
            return StageOutput.cancel(
                cancel_reason="Approval timeout",
                approved=False,
            )
```

### Async Approval Flow

For long-running approvals, use async patterns:

```python
class AsyncApprovalStage:
    """Request approval without blocking pipeline."""

    name = "request_approval"
    kind = StageKind.WORK

    async def execute(self, ctx: StageContext) -> StageOutput:
        action = ctx.inputs.get_from("llm", "action")

        # Request approval (non-blocking)
        approval_id = await self._service.request_approval(
            ApprovalRequest(
                action=action["name"],
                resource_id=action.get("resource_id"),
                requester_id=str(ctx.snapshot.user_id),
            )
        )

        return StageOutput.ok(
            approval_id=approval_id,
            status="pending",
            message="Approval requested. Pipeline will continue when approved.",
        )


# Separate pipeline to check and execute after approval
approval_check_pipeline = (
    Pipeline()
    .with_stage("check_approval", CheckApprovalStage, StageKind.GUARD)
    .with_stage("execute_action", ExecuteActionStage, StageKind.WORK,
                dependencies=("check_approval",))
)
```

## Testing Tools and Approvals

### Mock Tool Executor

```python
from stageflow.helpers import MockToolExecutor

# Create mock with predefined tools
executor = MockToolExecutor(
    tools={
        "calculator": lambda args: {"result": eval(args["expression"])},
        "weather": lambda args: {"temp": 72, "condition": "sunny"},
    },
    latency_ms=10,
)

# Test tool execution
result = await executor.execute("calculator", {"expression": "2+2"})
assert result.success
assert result.output["result"] == 4

# Check execution history
assert executor.execution_count == 1
assert executor.execution_history[0]["tool"] == "calculator"
```

### Scripted Approvals

```python
class ScriptedApprovalService:
    """Approval service that auto-approves for testing."""

    def __init__(self, auto_approve: bool = True, delay_ms: int = 0):
        self._auto_approve = auto_approve
        self._delay_ms = delay_ms

    async def request_and_wait(self, request: ApprovalRequest):
        if self._delay_ms:
            await asyncio.sleep(self._delay_ms / 1000)

        return ApprovalResult(
            approved=self._auto_approve,
            approver_id="test-approver",
            reason="Auto-approved for testing" if self._auto_approve else "Auto-denied",
        )


# Use in tests
async def test_approval_flow():
    service = ScriptedApprovalService(auto_approve=True)
    stage = ApprovalRequiredStage(service)

    ctx = create_test_stage_context(
        prior_outputs={
            "router": StageOutput.ok(action={"name": "delete", "approval_required": True})
        }
    )

    result = await stage.execute(ctx)
    assert result.data["approved"] is True
```

## Adapter Patterns

### Timeout Adapter

Wrap tools with timeout handling:

```python
from stageflow.tools.adapters import TimeoutAdapter

# Wrap tool with timeout
adapted_tool = TimeoutAdapter(
    tool=slow_api_tool,
    timeout_ms=5000,
    on_timeout="fail",  # or "return_default"
    default_value={"status": "timeout"},
)

result = await adapted_tool.execute(args)
```

### Retry Adapter

Add retry logic:

```python
from stageflow.tools.adapters import RetryAdapter

# Wrap tool with retries
adapted_tool = RetryAdapter(
    tool=flaky_tool,
    max_retries=3,
    retry_on=[TimeoutError, ConnectionError],
    backoff="exponential",  # or "linear", "constant"
    initial_delay_ms=100,
)

result = await adapted_tool.execute(args)
```

### Circuit Breaker Adapter

Prevent cascading failures:

```python
from stageflow.tools.adapters import CircuitBreakerAdapter

adapted_tool = CircuitBreakerAdapter(
    tool=external_service_tool,
    failure_threshold=5,      # Open after 5 failures
    reset_timeout_seconds=30, # Try again after 30s
    half_open_requests=2,     # Allow 2 test requests
)

try:
    result = await adapted_tool.execute(args)
except CircuitOpenError:
    # Circuit is open, use fallback
    result = fallback_result
```

## Complete Agent Pipeline

```python
from stageflow import Pipeline, StageKind
from stageflow.tools import ToolRegistry, AdvancedToolExecutor
from stageflow.helpers import MemoryFetchStage, MemoryWriteStage

# Set up tools
registry = ToolRegistry()
registry.register_tool(calculator_tool)
registry.register_tool(weather_tool)
registry.register_tool(database_tool)

executor = AdvancedToolExecutor(
    registry=registry,
    max_retries=2,
    timeout_ms=10000,
)

# Memory store
memory_store = InMemoryStore()

# Build pipeline
agent_pipeline = (
    Pipeline()
    # 1. Fetch conversation memory
    .with_stage("memory", MemoryFetchStage(memory_store), StageKind.ENRICH)

    # 2. Route request (decide if tools needed)
    .with_stage("router", RouterStage, StageKind.ROUTE,
                dependencies=("memory",))

    # 3. Check if approval needed
    .with_stage("approval", ApprovalCheckStage(approval_service), StageKind.GUARD,
                dependencies=("router",))

    # 4. Execute tools if approved
    .with_stage("tools", ToolExecutionStage(executor), StageKind.WORK,
                dependencies=("router", "approval"))

    # 5. Generate response with LLM
    .with_stage("llm", LLMStage, StageKind.TRANSFORM,
                dependencies=("memory", "router", "tools"))

    # 6. Save to memory
    .with_stage("save", MemoryWriteStage(memory_store), StageKind.WORK,
                dependencies=("llm",))
)
```

## Event Tracking

### Tool Execution Events

```python
class ObservableToolExecutor:
    """Executor that emits events for all tool calls."""

    def __init__(self, executor: ToolExecutor, event_sink):
        self._executor = executor
        self._sink = event_sink

    async def execute(self, tool_name: str, arguments: dict):
        # Emit start event
        self._sink.try_emit(
            type=f"tool.{tool_name}.started",
            data={"arguments": arguments},
        )

        start = datetime.now(UTC)
        result = await self._executor.execute(tool_name, arguments)
        duration_ms = (datetime.now(UTC) - start).total_seconds() * 1000

        # Emit completion event
        self._sink.try_emit(
            type=f"tool.{tool_name}.completed",
            data={
                "success": result.success,
                "duration_ms": duration_ms,
                "error": result.error,
            },
        )

        return result
```

### Approval Events

```python
# Request event
event_sink.try_emit(
    type="approval.requested",
    data={
        "approval_id": approval_id,
        "action": action_name,
        "requester_id": requester_id,
    },
)

# Decision event
event_sink.try_emit(
    type="approval.decided",
    data={
        "approval_id": approval_id,
        "approved": True,
        "approver_id": approver_id,
        "decision_time_ms": decision_time,
    },
)
```

## Best Practices

### 1. Validate Tool Inputs

```python
# Always validate before execution
if not registry.validate_input(tool_input):
    return StageOutput.fail(error="Invalid tool input")
```

### 2. Handle Partial Failures

```python
# Don't fail entire pipeline on one tool failure
results = []
failed = []

for call in tool_calls:
    result = await executor.execute(call["name"], call["arguments"])
    if result.success:
        results.append(result)
    else:
        failed.append({"tool": call["name"], "error": result.error})

return StageOutput.ok(
    results=results,
    failed=failed,
    partial_success=len(failed) > 0 and len(results) > 0,
)
```

### 3. Log Everything

```python
# Log tool calls for debugging and audit
logger.info(
    "Tool executed",
    extra={
        "tool": tool_name,
        "success": result.success,
        "duration_ms": duration_ms,
        "user_id": str(ctx.snapshot.user_id),
    },
)
```

### 4. Set Appropriate Timeouts

```python
# Different timeouts for different tools
timeouts = {
    "quick_lookup": 1000,    # 1 second
    "api_call": 5000,        # 5 seconds
    "heavy_compute": 30000,  # 30 seconds
}
```

## Next Steps

- [Tools API Reference](../api/tools.md) - Complete tools API
- [Governance Guide](governance.md) - Security patterns
- [Testing Guide](../advanced/testing.md) - Testing agent pipelines
