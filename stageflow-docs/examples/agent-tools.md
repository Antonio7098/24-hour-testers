# Agent with Tools Example

This example demonstrates an agent stage that can execute tools based on user input, including tool registration, execution, and response generation.

## Overview

```
[dispatch] → [agent]
```

A ROUTE stage dispatches to the appropriate handler, then an AGENT stage parses intent and executes tools.

## The Tool

### TogglePanelTool

```python
from stageflow.tools import BaseTool, ToolInput, ToolOutput


class TogglePanelTool(BaseTool):
    """Tool to toggle a UI panel on/off."""

    name = "toggle_panel"
    description = "Toggle a UI panel on or off"
    action_type = "TOGGLE_PANEL"

    # Track state (in production, this would be in a database)
    _panel_state: bool = False

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        payload = input.action.payload
        new_state = payload.get("state", not self._panel_state)
        
        # Update state
        old_state = self._panel_state
        TogglePanelTool._panel_state = new_state
        
        # Generate message
        if new_state:
            message = "Panel has been turned ON"
        else:
            message = "Panel has been turned OFF"
        
        return ToolOutput(
            success=True,
            data={
                "message": message,
                "previous_state": old_state,
                "current_state": new_state,
            },
        )
```

## The Stages

### DispatchStage

```python
from stageflow import StageContext, StageKind, StageOutput


class DispatchStage:
    """Dispatch to appropriate handler based on input."""

    name = "dispatch"
    kind = StageKind.ROUTE

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        lower_text = input_text.lower()

        # Route based on keywords
        if "subpipeline" in lower_text:
            route = "worker"
        else:
            route = "agent"

        return StageOutput.ok(route=route, input_text=input_text)
```

### AgentStage

```python
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from stageflow import StageContext, StageKind, StageOutput
from stageflow.tools import get_tool_registry


@dataclass(frozen=True)
class Action:
    """Action to be executed by a tool."""
    id: UUID
    type: str
    payload: dict


class AgentStage:
    """Agent stage that can execute tools based on user input."""

    name = "agent"
    kind = StageKind.AGENT

    def __init__(self):
        self.registry = get_tool_registry()
        self._register_tools()

    def _register_tools(self) -> None:
        """Register available tools."""
        self.registry.register(TogglePanelTool())

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute agent with tool use."""
        input_text = ctx.snapshot.input_text or ""
        route = ctx.inputs.get_from("dispatch", "route", default="agent")

        # Skip if routed elsewhere
        if route != "agent":
            return StageOutput.skip(
                reason=f"routed_to_{route}",
                data={"route": route},
            )

        # Parse intent and create actions
        actions = self._parse_intent(input_text)
        
        # Execute actions
        results = []
        for action in actions:
            try:
                output = await self.registry.execute(action, ctx.to_dict())
                results.append({
                    "action": action.type,
                    "success": output.success if output else False,
                    "data": output.data if output else None,
                })
            except Exception as e:
                results.append({
                    "action": action.type,
                    "success": False,
                    "error": str(e),
                })

        # Generate response
        response = self._generate_response(input_text, results)

        return StageOutput.ok(
            response=response,
            actions_executed=len(results),
            action_results=results,
        )

    def _parse_intent(self, input_text: str) -> list[Action]:
        """Parse user intent and create actions."""
        actions = []
        lower_text = input_text.lower().strip()

        # Intent detection patterns
        turn_on_patterns = [
            r"\bturn(?:\s+\w+)?\s+on\b",
            r"\benable\b",
            r"\bactivate\b",
        ]
        turn_off_patterns = [
            r"\bturn(?:\s+\w+)?\s+off\b",
            r"\bdisable\b",
            r"\bdeactivate\b",
        ]

        matched_on = any(re.search(p, lower_text) for p in turn_on_patterns)
        matched_off = any(re.search(p, lower_text) for p in turn_off_patterns)

        if matched_on:
            actions.append(Action(
                id=uuid4(),
                type="TOGGLE_PANEL",
                payload={"state": True},
            ))
        elif matched_off:
            actions.append(Action(
                id=uuid4(),
                type="TOGGLE_PANEL",
                payload={"state": False},
            ))

        return actions

    def _generate_response(self, input_text: str, results: list[dict]) -> str:
        """Generate response based on action results."""
        if not results:
            return "I didn't understand what you want me to do. Try asking me to turn something on or off."

        responses = []
        for result in results:
            if result["success"]:
                data = result.get("data", {})
                if "message" in data:
                    responses.append(data["message"])
                else:
                    responses.append(f"Executed {result['action']} successfully")
            else:
                error = result.get("error", "Unknown error")
                responses.append(f"Failed to execute {result['action']}: {error}")

        return " ".join(responses)
```

## The Pipeline

```python
from stageflow import Pipeline, StageKind


def create_agent_demo_pipeline() -> Pipeline:
    """Create an agent pipeline with tool execution.
    
    DAG:
        [dispatch] → [agent]
    """
    return (
        Pipeline()
        .with_stage(
            name="dispatch",
            runner=DispatchStage,
            kind=StageKind.ROUTE,
        )
        .with_stage(
            name="agent",
            runner=AgentStage(),
            kind=StageKind.AGENT,
            dependencies=("dispatch",),
        )
    )
```

## Complete Example

```python
import asyncio
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput
from stageflow.context import ContextSnapshot
from stageflow.tools import BaseTool, ToolInput, ToolOutput, get_tool_registry


# Tool
class TogglePanelTool(BaseTool):
    name = "toggle_panel"
    description = "Toggle a UI panel on or off"
    action_type = "TOGGLE_PANEL"
    _panel_state: bool = False

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        new_state = input.action.payload.get("state", not self._panel_state)
        old_state = TogglePanelTool._panel_state
        TogglePanelTool._panel_state = new_state
        
        message = "Panel turned ON" if new_state else "Panel turned OFF"
        return ToolOutput(
            success=True,
            data={"message": message, "state": new_state},
        )


# Action dataclass
@dataclass(frozen=True)
class Action:
    id: UUID
    type: str
    payload: dict


# Stages
class DispatchStage:
    name = "dispatch"
    kind = StageKind.ROUTE

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        route = "worker" if "subpipeline" in input_text.lower() else "agent"
        return StageOutput.ok(route=route)


class AgentStage:
    name = "agent"
    kind = StageKind.AGENT

    def __init__(self):
        self.registry = get_tool_registry()
        self.registry.register(TogglePanelTool())

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        route = ctx.inputs.get("route", "agent")

        if route != "agent":
            return StageOutput.skip(reason=f"routed_to_{route}")

        # Parse intent
        actions = self._parse_intent(input_text)
        
        # Execute tools
        results = []
        for action in actions:
            try:
                output = await self.registry.execute(action, ctx.to_dict())
                results.append({
                    "action": action.type,
                    "success": output.success,
                    "data": output.data,
                })
            except Exception as e:
                results.append({
                    "action": action.type,
                    "success": False,
                    "error": str(e),
                })

        # Generate response
        if not results:
            response = "I can help you turn things on or off. Try saying 'turn it on' or 'turn it off'."
        else:
            messages = [r["data"]["message"] for r in results if r["success"] and r.get("data")]
            response = " ".join(messages) if messages else "Action completed."

        return StageOutput.ok(
            response=response,
            actions_executed=len(results),
            action_results=results,
        )

    def _parse_intent(self, text: str) -> list[Action]:
        lower = text.lower()
        actions = []
        
        if re.search(r"\b(turn|switch).*on\b|\benable\b|\bactivate\b", lower):
            actions.append(Action(id=uuid4(), type="TOGGLE_PANEL", payload={"state": True}))
        elif re.search(r"\b(turn|switch).*off\b|\bdisable\b|\bdeactivate\b", lower):
            actions.append(Action(id=uuid4(), type="TOGGLE_PANEL", payload={"state": False}))
        
        return actions


async def main():
    # Create pipeline
    pipeline = (
        Pipeline()
        .with_stage("dispatch", DispatchStage, StageKind.ROUTE)
        .with_stage("agent", AgentStage(), StageKind.AGENT, dependencies=("dispatch",))
    )
    
    graph = pipeline.build()
    
    # Test inputs
    test_inputs = [
        "Hello there!",
        "Turn it on please",
        "Can you turn it off?",
        "Enable the panel",
        "Disable everything",
    ]
    
    for input_text in test_inputs:
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
            topology="agent_demo",
            execution_mode="default",
            input_text=input_text,
        )
        
        ctx = StageContext(snapshot=snapshot)
        results = await graph.run(ctx)
        
        agent_output = results["agent"]
        print(f"Input: {input_text}")
        print(f"Response: {agent_output.data.get('response')}")
        print(f"Actions: {agent_output.data.get('actions_executed', 0)}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
```

## Output

```
Input: Hello there!
Response: I can help you turn things on or off. Try saying 'turn it on' or 'turn it off'.
Actions: 0

Input: Turn it on please
Response: Panel turned ON
Actions: 1

Input: Can you turn it off?
Response: Panel turned OFF
Actions: 1

Input: Enable the panel
Response: Panel turned ON
Actions: 1

Input: Disable everything
Response: Panel turned ON
Panel turned OFF
Action completed.
Actions: 1
```

## Guard Retry Cookbook

Autocorrection loops often need to retry an AGENT stage when a GUARD
rejects its output. Stageflow stops execution when a guard returns
`StageOutput.fail()`, so you must explicitly route retries. The pattern
below uses a WORK stage to orchestrate retries with iteration caps and
hash-based stagnation detection.

```python
from dataclasses import dataclass
from stageflow import Pipeline, StageKind, StageOutput
from stageflow.pipeline.guard_retry import GuardRetryPolicy, GuardRetryStrategy
from stageflow.testing import create_test_stage_context

MAX_RETRIES = 3


class GuardStage:
    name = "output_guard"
    kind = StageKind.GUARD

    async def execute(self, ctx):
        result = ctx.inputs.get_from("agent", "response", default="")
        if "banned" in result.lower():
            return StageOutput.fail(error="policy_violation")
        return StageOutput.ok(response=result)


class RetryCoordinator:
    name = "retry_loop"
    kind = StageKind.WORK

    async def execute(self, ctx):
        prior = ctx.inputs.get_from("agent", "response", default="")
        failures = ctx.inputs.get("retry_state", {}).get("failures", 0)
        if failures >= MAX_RETRIES:
            return StageOutput.cancel(
                reason="max_guard_failures",
                data={"attempts": failures},
            )

        if ctx.inputs.get("guard_status") == "fail":
            failures += 1
            return StageOutput.retry(
                error="guard_rejected",
                data={"retry_state": {"failures": failures, "last": prior}},
            )

        return StageOutput.ok()


pipeline = (
    Pipeline()
    .with_stage("dispatch", DispatchStage, StageKind.ROUTE)
    .with_stage("agent", AgentStage(), StageKind.AGENT, dependencies=("dispatch",))
    .with_stage("output_guard", GuardStage, StageKind.GUARD, dependencies=("agent",))
    .with_stage(
        "retry_loop",
        RetryCoordinator,
        StageKind.WORK,
        dependencies=("agent", "output_guard"),
    )
)

strategy = GuardRetryStrategy(
    policies={
        "output_guard": GuardRetryPolicy(
            retry_stage="agent",
            max_attempts=MAX_RETRIES,
            stagnation_limit=2,
            timeout_seconds=8.0,
        )
    }
)

# In tests you can shortcut the context wiring:
ctx = create_test_stage_context(input_text="turn it on")
graph = pipeline.build(guard_retry_strategy=strategy)
```

**How it works**

1. `AgentStage` produces a response.
2. `GuardStage` validates the response. If it fails, the coordinator
   emits `StageOutput.retry(...)` with state (iteration count, last
   response, hashes, etc.).
3. The retry controller increments failure counts and can short-circuit
   via `StageOutput.cancel()` when limits are reached, while the
   executor emits `guard_retry.*` events (attempt/scheduled/exhausted/
   recovered) so dashboards can track iteration counts, stagnation hits,
   and timeout triggers.
4. Use `create_test_stage_context()` from `stageflow.testing` in unit
   tests to avoid manually wiring `StageInputs`, timers, and snapshots
   when validating retry paths.

> **Tip**: Combine executor-level `guard_retry_strategy` events with
> coordinator telemetry to distinguish "the guard asked for a retry"
> from "another retry actually ran". Feed those structured metrics into
> whatever WideEvent/Warehouse sink you use for autocorrection loops.

## Advanced: Tool with Undo Support

```python
from stageflow.tools import ToolDefinition, ToolInput, ToolOutput, UndoMetadata

# State storage (in production, use a database)
_document_content = {}

async def edit_document_handler(input: ToolInput) -> ToolOutput:
    doc_id = input.payload.get("document_id")
    new_content = input.payload.get("content")
    
    # Store original for undo
    original = _document_content.get(doc_id, "")
    
    # Apply edit
    _document_content[doc_id] = new_content
    
    return ToolOutput.ok(
        data={"document_id": doc_id, "updated": True},
        undo_metadata={"document_id": doc_id, "original_content": original},
    )

async def edit_document_undo(metadata: UndoMetadata) -> None:
    doc_id = metadata.undo_data["document_id"]
    original = metadata.undo_data["original_content"]
    _document_content[doc_id] = original

edit_document_tool = ToolDefinition(
    name="edit_document",
    action_type="EDIT_DOCUMENT",
    description="Edit a document's content",
    handler=edit_document_handler,
    undoable=True,
    undo_handler=edit_document_undo,
    requires_approval=True,
    approval_message="This will modify the document. Proceed?",
)
```

## Advanced: Behavior-Gated Tools

```python
from stageflow.tools import ToolDefinition

# Tool only available in "admin" mode
admin_tool = ToolDefinition(
    name="admin_action",
    action_type="ADMIN_ACTION",
    handler=admin_handler,
    allowed_behaviors=("admin",),  # Only in admin execution_mode
)

# In the agent stage
class AdminAgentStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        execution_mode = ctx.snapshot.execution_mode
        
        # Check if tool is allowed
        if not admin_tool.is_behavior_allowed(execution_mode):
            return StageOutput.ok(
                response="Admin actions are not available in this mode.",
            )
        
        # Execute tool...
```

## Advanced: LLM-Driven Tool Selection

```python
class LLMAgentStage:
    """Agent that uses LLM to decide which tools to call."""
    
    name = "llm_agent"
    kind = StageKind.AGENT

    def __init__(self, llm_client, tool_registry):
        self.llm = llm_client
        self.registry = tool_registry

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        
        # Get tool schemas for LLM
        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            for tool in self.registry.list()
        ]
        
        # Call LLM with tools
        response = await self.llm.chat(
            messages=[{"role": "user", "content": input_text}],
            tools=tools,
        )
        
        # Execute tool calls parsed via registry helper
        results = []
        tool_calls = getattr(response, "tool_calls", []) or []
        resolved, unresolved = self.registry.parse_and_resolve(tool_calls)

        for call in unresolved:
            ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})

        for call in resolved:
            tool_input = ToolInput(action=call.arguments)
            result = await call.tool.execute(tool_input, ctx.to_dict())
            results.append(result)
        
        return StageOutput.ok(
            response=response.content,
            tool_results=results,
        )
```

## Next Steps

- [Tools Guide](../guides/tools.md) — Deep dive into the tool system
- [Full Pipeline](full.md) — Complete pipeline with all features
- [Advanced Topics](../advanced/custom-interceptors.md) — Custom middleware
