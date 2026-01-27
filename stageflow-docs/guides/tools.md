# Tools & Agents

Stageflow provides a comprehensive tool system for building agent capabilities. This guide covers tool definitions, registration, execution, and advanced features like undo and approval flows.

## Overview

Tools are **capability units** that agents can invoke to perform actions. The tool system provides:

- **Tool definitions** with schemas and handlers
- **Tool registry** for discovery and registration
- **Tool executor** with observability and error handling
- **Behavior gating** to restrict tools by execution mode
- **Undo support** for reversible actions
- **Approval flows** for human-in-the-loop (HITL)

## Defining Tools

### Basic Tool

Implement the `Tool` protocol:

```python
from stageflow.tools import Tool, ToolInput, ToolOutput

class GreetTool:
    """A simple greeting tool."""
    
    @property
    def name(self) -> str:
        return "greet"
    
    @property
    def description(self) -> str:
        return "Greet a user by name"
    
    @property
    def action_type(self) -> str:
        return "GREET"
    
    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        name = input.action.payload.get("name", "World")
        return ToolOutput(
            success=True,
            data={"message": f"Hello, {name}!"},
        )
```

### Using BaseTool

Extend `BaseTool` for a cleaner implementation:

```python
from stageflow.tools import BaseTool, ToolInput, ToolOutput

class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Perform basic arithmetic"
    action_type = "CALCULATE"
    
    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        payload = input.action.payload
        operation = payload.get("operation")
        a = payload.get("a", 0)
        b = payload.get("b", 0)
        
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            if b == 0:
                return ToolOutput(success=False, error="Division by zero")
            result = a / b
        else:
            return ToolOutput(success=False, error=f"Unknown operation: {operation}")
        
        return ToolOutput(success=True, data={"result": result})
```

## Tool Registry

### Registering Tools

```python
from stageflow.tools import get_tool_registry, register_tool

# Get the global registry
registry = get_tool_registry()

# Register a tool instance
registry.register(GreetTool())
registry.register(CalculatorTool())

# Or use the decorator
@register_tool
class SearchTool(BaseTool):
    name = "search"
    description = "Search for information"
    action_type = "SEARCH"
    
    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        query = input.action.payload.get("query", "")
        # Perform search...
        return ToolOutput(success=True, data={"results": []})
```

### Retrieving Tools

```python
registry = get_tool_registry()

# Get by name
tool = registry.get("calculator")

# Get by action type
tool = registry.get_by_action_type("CALCULATE")

# List all tools
all_tools = registry.list()

# Check if tool exists
if registry.has("calculator"):
    ...
```

### Parsing LLM Tool Calls

Connect LLM provider outputs to Stageflow tools without manual JSON parsing:

```python
tool_calls = llm_response.tool_calls  # e.g., OpenAI function calls

resolved, unresolved = registry.parse_and_resolve(tool_calls)

for call in unresolved:
    ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})

for call in resolved:
    tool_input = ToolInput(action=call.arguments)
    result = await call.tool.execute(tool_input, ctx={"call_id": call.call_id})
```

The helper understands OpenAI/Anthropic formats (and custom field names) and returns `ResolvedToolCall` / `UnresolvedToolCall` dataclasses for observability.

## Executing Tools

### Direct Execution

```python
from dataclasses import dataclass
from uuid import uuid4

@dataclass
class Action:
    id: uuid4
    type: str
    payload: dict

# Create an action
action = Action(
    id=uuid4(),
    type="CALCULATE",
    payload={"operation": "add", "a": 5, "b": 3},
)

# Execute via registry
result = await registry.execute(action, ctx={})
print(result.data)  # {"result": 8}
```

### Using ToolExecutor

The `ToolExecutor` provides additional features:

```python
from stageflow.tools import ToolExecutor

executor = ToolExecutor(registry=registry)

result = await executor.execute(action, ctx={
    "pipeline_run_id": str(uuid4()),
    "user_id": str(uuid4()),
})
```

### Using AdvancedToolExecutor

For full observability and advanced features:

```python
from stageflow.tools import AdvancedToolExecutor, ToolExecutorConfig

config = ToolExecutorConfig(
    emit_events=True,
    store_undo_data=True,
    require_approval_for_risky=True,
)

executor = AdvancedToolExecutor(
    registry=registry,
    config=config,
    event_sink=my_event_sink,
)

result = await executor.execute(action, ctx)
```

## Tool Definitions

For advanced tools, use `ToolDefinition`:

```python
from stageflow.tools import ToolDefinition, ToolInput, ToolOutput

async def edit_document_handler(input: ToolInput) -> ToolOutput:
    """Handler for document editing."""
    doc_id = input.payload.get("document_id")
    changes = input.payload.get("changes", [])
    
    # Apply changes...
    
    return ToolOutput.ok(
        data={"document_id": doc_id, "changes_applied": len(changes)},
        undo_metadata={"original_content": "..."},  # For undo
    )

edit_document_tool = ToolDefinition(
    name="edit_document",
    action_type="EDIT_DOCUMENT",
    description="Edit a document's content",
    input_schema={
        "type": "object",
        "properties": {
            "document_id": {"type": "string"},
            "changes": {"type": "array"},
        },
        "required": ["document_id", "changes"],
    },
    handler=edit_document_handler,
    allowed_behaviors=("doc_edit",),  # Only allowed in doc_edit mode
    requires_approval=True,  # Needs human approval
    approval_message="This will modify the document. Proceed?",
    undoable=True,
    undo_handler=undo_edit_document,
)
```

## Behavior Gating

Restrict tools to specific execution modes:

```python
tool = ToolDefinition(
    name="dangerous_tool",
    action_type="DANGEROUS",
    handler=dangerous_handler,
    allowed_behaviors=("admin", "debug"),  # Only in admin or debug mode
)

# Check if behavior is allowed
if tool.is_behavior_allowed(ctx.execution_mode):
    result = await tool.handler(input)
else:
    # Tool denied for this behavior
    raise ToolDeniedError("Tool not allowed in this mode")
```

## Undo Support

### Making Tools Undoable

```python
async def toggle_handler(input: ToolInput) -> ToolOutput:
    current_state = get_current_state()
    new_state = input.payload.get("state", not current_state)
    
    set_state(new_state)
    
    return ToolOutput.ok(
        data={"state": new_state},
        undo_metadata={"previous_state": current_state},
    )

async def toggle_undo_handler(undo_metadata: UndoMetadata) -> None:
    previous_state = undo_metadata.undo_data["previous_state"]
    set_state(previous_state)

toggle_tool = ToolDefinition(
    name="toggle",
    action_type="TOGGLE",
    handler=toggle_handler,
    undoable=True,
    undo_handler=toggle_undo_handler,
)
```

## Diff Support

The Stageflow tool system includes diff utilities for tracking and displaying changes made by tools. Diffs are essential for:

- Showing users what changed after an edit
- Generating audit trails
- Supporting undo/redo functionality
- Calculating similarity metrics

### Text Diff

Generate unified diffs between text content:

```python
from stageflow.tools import diff_text, DiffType

old_content = """Welcome to our application.

Features:
- Fast processing
- Secure storage
"""

new_content = """Welcome to our application.

Features:
- Fast processing
- Secure storage
- Cloud sync
"""

result = diff_text(old_content, new_content)

# Access diff output
print(result.diff_output)
# --- a/original
# +++ b/modified
# @@ -3,4 +3,5 @@
#  Features:
#  - Fast processing
#  - Secure storage
# +Cloud sync

# Check statistics
print(f"Additions: {result.additions}")  # 1
print(f"Deletions: {result.deletions}")  # 0
print(f"Similarity: {result.similarity}")  # 0.941
print(f"Has changes: {result.has_changes}")  # True
print(f"Summary: {result.change_summary}")  # "+1"

# Serialize for storage
serialized = result.to_dict()
```

### JSON Diff

Generate JSON Patch format for structured data:

```python
from stageflow.tools import diff_json

old_config = {
    "theme": "dark",
    "notifications": True,
    "timeout": 30,
}

new_config = {
    "theme": "light",
    "notifications": False,
    "timeout": 60,
    "language": "en",
}

result = diff_json(old_config, new_config)
print(result.diff_output)
# [
#   {"op": "replace", "path": "/theme", "value": "light"},
#   {"op": "replace", "path": "/notifications", "value": false},
#   {"op": "replace", "path": "/timeout", "value": 60},
#   {"op": "add", "path": "/language", "value": "en"}
# ]
```

### Structured Dict Diff

Compare dictionaries with detailed field-level output:

```python
from stageflow.tools import diff_structured

old_record = {"id": 1, "status": "pending", "priority": "high"}
new_record = {"id": 1, "status": "done", "priority": "medium"}

result = diff_structured(old_record, new_record, ignore_keys={"id"})
print(result.diff_output)
# --- old
# +++ new
# - priority: 'high'
# + priority: 'medium'
# - status: 'pending'
# + status: 'done'
```

### Using Diffs with Tools

Combine diffs with undoable tools to track changes:

```python
from stageflow.tools import (
    ToolDefinition,
    ToolInput,
    ToolOutput,
    diff_text,
    UndoMetadata,
)

# In-memory storage for demo (use database in production)
_document_content: dict[str, str] = {}

async def edit_document_handler(input: ToolInput) -> ToolOutput:
    doc_id = input.payload["document_id"]
    new_content = input.payload["content"]

    # Get original content
    original = _document_content.get(doc_id, "")

    # Generate diff before applying changes
    diff_result = diff_text(original, new_content)

    # Apply the edit
    _document_content[doc_id] = new_content

    return ToolOutput.ok(
        data={
            "document_id": doc_id,
            "updated": True,
            "changes_summary": diff_result.change_summary,
            "diff": diff_result.diff_output,
        },
        undo_metadata={
            "document_id": doc_id,
            "original_content": original,
            "diff_result": diff_result.to_dict(),
        },
    )

async def edit_document_undo(metadata: UndoMetadata) -> None:
    doc_id = metadata.undo_data["document_id"]
    original = metadata.undo_data["original_content"]
    _document_content[doc_id] = original

edit_tool = ToolDefinition(
    name="edit_document",
    action_type="EDIT_DOCUMENT",
    handler=edit_document_handler,
    description="Edit a document's content",
    undoable=True,
    undo_handler=edit_document_undo,
)
```

### Using the Undo Store

```python
from stageflow.tools import get_undo_store, UndoMetadata

undo_store = get_undo_store()

# Store undo data (done automatically by executor)
metadata = UndoMetadata(
    action_id=action.id,
    tool_name="toggle",
    undo_data={"previous_state": True},
)
await undo_store.store(metadata)

# Retrieve and execute undo
stored = await undo_store.get(action.id)
if stored:
    await toggle_undo_handler(stored)
    await undo_store.remove(action.id)
```

## Approval Flows

### Requiring Approval

```python
tool = ToolDefinition(
    name="delete_account",
    action_type="DELETE_ACCOUNT",
    handler=delete_handler,
    requires_approval=True,
    approval_message="This will permanently delete the account. Are you sure?",
)
```

### Approval Service

```python
from stageflow.tools import (
    get_approval_service,
    ApprovalRequest,
    ApprovalStatus,
)

approval_service = get_approval_service()

# Request approval
request = ApprovalRequest(
    action_id=action.id,
    tool_name="delete_account",
    message="Delete account for user@example.com?",
    payload=action.payload,
)
await approval_service.request(request)

# Check status
status = await approval_service.get_status(action.id)
if status == ApprovalStatus.APPROVED:
    result = await tool.handler(input)
elif status == ApprovalStatus.DENIED:
    raise ToolApprovalDeniedError("User denied the action")
elif status == ApprovalStatus.PENDING:
    # Wait or timeout
    ...
```

## Tool Events

The tool system emits events for observability:

| Event | Description |
|-------|-------------|
| `tool.invoked` | Tool execution requested |
| `tool.started` | Tool execution began |
| `tool.completed` | Tool executed successfully |
| `tool.failed` | Tool execution failed |
| `tool.denied` | Tool denied (behavior gating) |
| `tool.undone` | Tool action was undone |
| `tool.undo_failed` | Undo operation failed |
| `approval.requested` | Approval requested |
| `approval.decided` | Approval granted or denied |

```python
from stageflow.tools import ToolCompletedEvent, ToolFailedEvent

# Events are emitted through the event sink
# Example event data:
{
    "action_id": "...",
    "tool_name": "calculator",
    "pipeline_run_id": "...",
    "duration_ms": 15,
    "success": True,
}
```

## Building Agent Stages with Tools

### Basic Agent Stage

```python
from stageflow import StageContext, StageKind, StageOutput
from stageflow.tools import get_tool_registry

class AgentStage:
    name = "agent"
    kind = StageKind.AGENT
    
    def __init__(self):
        self.registry = get_tool_registry()
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        
        # Parse intent and create actions
        actions = self._parse_intent(input_text)
        
        # Execute actions
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
        response = self._generate_response(results)
        
        return StageOutput.ok(
            response=response,
            actions_executed=len(results),
            action_results=results,
        )
    
    def _parse_intent(self, text: str) -> list:
        """Parse user intent into actions."""
        # Your intent parsing logic here
        ...
    
    def _generate_response(self, results: list) -> str:
        """Generate response based on action results."""
        # Your response generation logic here
        ...
```

### Agent with LLM Tool Calling

```python
class LLMAgentStage:
    name = "llm_agent"
    kind = StageKind.AGENT
    
    def __init__(self, llm_client, tool_registry):
        self.llm_client = llm_client
        self.registry = tool_registry
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        messages = self._build_messages(ctx)
        tools = self._get_tool_schemas()
        
        # Call LLM with tools
        response = await self.llm_client.chat(
            messages=messages,
            tools=tools,
        )
        
        # Execute any tool calls
        tool_results = []
        for tool_call in response.tool_calls:
            action = self._tool_call_to_action(tool_call)
            result = await self.registry.execute(action, ctx.to_dict())
            tool_results.append(result)
        
        # If tools were called, get final response
        if tool_results:
            messages.append({"role": "assistant", "tool_calls": response.tool_calls})
            messages.append({"role": "tool", "content": str(tool_results)})
            response = await self.llm_client.chat(messages=messages)
        
        return StageOutput.ok(
            response=response.content,
            tool_results=tool_results,
        )
    
    def _get_tool_schemas(self) -> list:
        """Get tool schemas for LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self.registry.list()
        ]
```

## Error Handling

### Tool Errors

```python
from stageflow.tools import (
    ToolError,
    ToolNotFoundError,
    ToolDeniedError,
    ToolExecutionError,
    ToolApprovalDeniedError,
    ToolApprovalTimeoutError,
    ToolUndoError,
)

try:
    result = await registry.execute(action, ctx)
except ToolNotFoundError as e:
    print(f"Tool not found: {e}")
except ToolDeniedError as e:
    print(f"Tool denied: {e}")
except ToolExecutionError as e:
    print(f"Tool execution failed: {e}")
except ToolApprovalDeniedError as e:
    print(f"Approval denied: {e}")
except ToolApprovalTimeoutError as e:
    print(f"Approval timed out: {e}")
```

### Graceful Degradation

```python
async def execute_with_fallback(action, ctx):
    try:
        return await registry.execute(action, ctx)
    except ToolNotFoundError:
        return ToolOutput(
            success=False,
            error=f"Unknown action: {action.type}",
        )
    except ToolDeniedError:
        return ToolOutput(
            success=False,
            error="This action is not available in the current mode",
        )
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return ToolOutput(
            success=False,
            error="An unexpected error occurred",
        )
```

## Best Practices

### 1. Keep Tools Focused

Each tool should do one thing well:

```python
# Good: Single responsibility
class CreateDocumentTool: ...
class EditDocumentTool: ...
class DeleteDocumentTool: ...

# Bad: Too many responsibilities
class DocumentTool:
    async def execute(self, input, ctx):
        if input.payload["action"] == "create": ...
        elif input.payload["action"] == "edit": ...
        elif input.payload["action"] == "delete": ...
```

### 2. Validate Input

Always validate tool input:

```python
async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
    # Validate required fields
    if "document_id" not in input.action.payload:
        return ToolOutput.fail("document_id is required")
    
    # Validate types
    doc_id = input.action.payload["document_id"]
    if not isinstance(doc_id, str):
        return ToolOutput.fail("document_id must be a string")
    
    # Continue with valid input...
```

### 3. Return Meaningful Errors

Provide helpful error messages:

```python
return ToolOutput.fail(
    error="Document not found",
    # Include context for debugging
    data={"document_id": doc_id, "searched_locations": ["db", "cache"]},
)
```

### 4. Support Undo When Possible

Make destructive actions undoable:

```python
async def delete_handler(input: ToolInput) -> ToolOutput:
    # Store data needed for undo
    item = await get_item(input.payload["id"])
    
    # Perform deletion
    await delete_item(input.payload["id"])
    
    return ToolOutput.ok(
        data={"deleted_id": input.payload["id"]},
        undo_metadata={"item_data": item.to_dict()},
    )
```

## Next Steps

- [Observability](observability.md) — Monitor tool execution
- [Agent Tools Example](../examples/agent-tools.md) — Complete agent example
- [Advanced Tool Executor](../advanced/custom-interceptors.md) — Custom execution logic
