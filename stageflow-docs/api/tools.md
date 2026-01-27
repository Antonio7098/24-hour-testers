# Tools API Reference

This document provides the API reference for the tool execution system.

## Tool Protocol

```python
from stageflow.tools import Tool
```

Protocol for self-describing capability units.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Unique tool identifier |
| `description` | `str` | Human-readable description |
| `action_type` | `str` | Action type this tool handles |

### Methods

#### `execute(input: ToolInput, ctx: dict) -> ToolOutput`

Execute the tool.

**Parameters:**
- `input`: `ToolInput` — Wrapped action with context
- `ctx`: `dict` — Pipeline context as dictionary. This is typically produced via `PipelineContext.to_dict()` by the engine.

**Returns:** `ToolOutput` with success status and data

---

## BaseTool

```python
from stageflow.tools import BaseTool
```

Base class for implementing tools.

```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    action_type = "MY_ACTION"
    
    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        return ToolOutput(success=True, data={"result": "done"})
```

---

## ToolInput

```python
from stageflow.tools import ToolInput
```

Input schema for a tool.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `action_id` | `UUID` | Unique action identifier |
| `tool_name` | `str` | Name of the tool |
| `payload` | `dict[str, Any]` | Action payload data |
| `behavior` | `str \| None` | Current execution mode |
| `pipeline_run_id` | `UUID \| None` | Pipeline run ID |
| `request_id` | `UUID \| None` | Request ID |

### Class Methods

#### `from_action(action, tool_name, ctx=None) -> ToolInput`

Create ToolInput from an Action and context.

```python
tool_input = ToolInput.from_action(action, "my_tool", ctx)
```

---

## ToolOutput

```python
from stageflow.tools import ToolOutput
```

Output from tool execution.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `success` | `bool` | Whether execution succeeded |
| `data` | `dict \| None` | Output data |
| `error` | `str \| None` | Error message if failed |
| `artifacts` | `list[dict] \| None` | Produced artifacts |
| `undo_metadata` | `dict \| None` | Data for undoing action |

### Class Methods

#### `ok(data=None, artifacts=None, undo_metadata=None) -> ToolOutput`

Create a successful output.

```python
return ToolOutput.ok(data={"result": "done"})
```

#### `fail(error: str) -> ToolOutput`

Create a failed output.

```python
return ToolOutput.fail("Something went wrong")
```

---

## ToolDefinition

```python
from stageflow.tools import ToolDefinition
```

Enhanced tool definition with gating, undo, and approval.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Tool identifier |
| `action_type` | `str` | Action type handled |
| `handler` | `ToolHandler` | Async execution function |
| `description` | `str` | Tool description |
| `input_schema` | `dict` | JSON Schema for input |
| `allowed_behaviors` | `tuple[str, ...]` | Allowed execution modes |
| `requires_approval` | `bool` | Needs HITL approval |
| `approval_message` | `str \| None` | Approval UI message |
| `undoable` | `bool` | Can be undone |
| `undo_handler` | `UndoHandler \| None` | Undo function |
| `artifact_type` | `str \| None` | Artifact type produced |

### Methods

#### `is_behavior_allowed(behavior: str | None) -> bool`

Check if behavior can use this tool.

```python
if tool.is_behavior_allowed(ctx.execution_mode):
    result = await tool.handler(input)
```

---

## Action Protocol

```python
from stageflow.tools import Action
```

Protocol for action objects.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `UUID` | Unique action identifier |
| `type` | `str` | Action type string |
| `payload` | `dict[str, Any]` | Action payload |

---

## ToolRegistry

```python
from stageflow.tools import ToolRegistry, get_tool_registry
```

Registry for tool discovery and execution.

### Methods

#### `register(tool: Tool) -> None`

Register a tool instance.

```python
registry = get_tool_registry()
registry.register(MyTool())
```

#### `get(name: str) -> Tool | None`

Get tool by name.

#### `get_by_action_type(action_type: str) -> Tool | None`

Get tool by action type.

#### `list() -> list[Tool]`

List all registered tools.

#### `has(name: str) -> bool`

Check if tool is registered.

#### `execute(action, ctx: dict) -> ToolOutput`

Execute a tool for an action.

```python
result = await registry.execute(action, ctx)
```

#### `parse_and_resolve(tool_calls: list[dict], *, id_field="id", name_field="name", arguments_field="arguments", function_wrapper="function") -> tuple[list[ResolvedToolCall], list[UnresolvedToolCall]]`

Parse provider-native tool call objects (e.g., OpenAI/Anthropic) and resolve them against registered tools.

```python
# Example: OpenAI-style tool calls
tool_calls = [
    {
        "id": "call_123",
        "function": {
            "name": "store_memory",
            "arguments": '{"content": "hello"}'
        }
    }
]

resolved, unresolved = registry.parse_and_resolve(tool_calls)

for call in unresolved:
    # Emit observability event for triage
    ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})

for call in resolved:
    tool_input = ToolInput(action=call.arguments)
    result = await call.tool.execute(tool_input, ctx={"call_id": call.call_id})
```

Supports alternate field names and disabling the `function` wrapper via `function_wrapper=None`.

### Dataclasses

```python
@dataclass(frozen=True, slots=True)
class ResolvedToolCall:
    tool: Tool
    call_id: str
    name: str
    arguments: dict[str, Any]
    raw: Any | None = None

@dataclass(frozen=True, slots=True)
class UnresolvedToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    error: str
    raw: Any | None = None
```

### Decorator

```python
from stageflow.tools import register_tool

@register_tool
class MyTool(BaseTool):
    name = "my_tool"
    ...
```

---

## ToolExecutor

```python
from stageflow.tools import ToolExecutor
```

Basic tool executor.

### Methods

#### `execute(action, ctx: dict) -> ToolOutput`

Execute a tool for an action.

---

## AdvancedToolExecutor

```python
from stageflow.tools import AdvancedToolExecutor, ToolExecutorConfig, ExecutionResult
```

Advanced executor with observability and behavior gating.

### ToolExecutorConfig

| Attribute | Type | Description |
|-----------|------|-------------|
| `emit_events` | `bool` | Emit tool events |
| `store_undo_data` | `bool` | Store undo metadata |
| `require_approval_for_risky` | `bool` | Require HITL approval |

### ExecutionResult

| Attribute | Type | Description |
|-----------|------|-------------|
| `success` | `bool` | Execution succeeded |
| `output` | `ToolOutput` | Tool output |
| `events` | `list` | Emitted events |

---

## UndoMetadata

```python
from stageflow.tools import UndoMetadata
```

Metadata for undoable actions.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `action_id` | `UUID` | Action identifier |
| `tool_name` | `str` | Tool name |
| `undo_data` | `dict` | Data for undo |
| `created_at` | `str` | Creation timestamp |

---

## UndoStore

```python
from stageflow.tools import UndoStore, get_undo_store, set_undo_store
```

Storage for undo metadata.

### Methods

#### `store(metadata: UndoMetadata) -> None`

Store undo metadata.

#### `get(action_id: UUID) -> UndoMetadata | None`

Retrieve undo metadata.

#### `remove(action_id: UUID) -> None`

Remove undo metadata.

---

## Diff Utilities

```python
from stageflow.tools import DiffType, DiffResult, diff_text, diff_json, diff_structured
```

Utilities for generating diffs between content, useful for showing changes and supporting undo.

### DiffType

Enum for diff format types.

| Value | Description |
|-------|-------------|
| `UNIFIED` | Unified diff format (default) |
| `CONTEXT` | Context diff format |
| `JSON_PATCH` | JSON Patch format (RFC 6902) |
| `LINE_BY_LINE` | Simple line-by-line comparison |

### DiffLine

```python
@dataclass(frozen=True)
class DiffLine:
    type: str           # "equal", "add", "remove"
    content: str
    line_number_old: int | None
    line_number_new: int | None
```

A single line in a diff.

### DiffResult

```python
@dataclass(frozen=True)
class DiffResult:
    diff_type: DiffType
    diff_output: str
    changes: list[DiffLine]
    additions: int
    deletions: int
    unchanged: int
    similarity: float
    old_content: str | None
    new_content: str | None
```

Result of a diff operation.

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `has_changes` | `bool` | True if there are any changes |
| `change_summary` | `str` | Human-readable summary like "+5 -3" |

#### Methods

##### `to_dict() -> dict`

Convert to dictionary for serialization.

```python
result = diff_text(old, new)
serialized = result.to_dict()
```

### diff_text()

```python
def diff_text(
    old: str,
    new: str,
    diff_type: DiffType = DiffType.UNIFIED,
    context_lines: int = 3,
    fromfile: str = "a/original",
    tofile: str = "b/modified",
) -> DiffResult
```

Generate a unified diff between two text strings.

```python
old = "Hello\nWorld"
new = "Hello\nPython\nWorld"
result = diff_text(old, new)
print(result.diff_output)
# --- a/original
# +++ b/modified
# @@ -1,2 +1,3 @@
#  Hello
# +Python
#  World
```

### diff_json()

```python
def diff_json(
    old: dict | list | None,
    new: dict | list | None,
) -> DiffResult
```

Generate a JSON Patch-style diff between two JSON-ifiable objects.

```python
old = {"name": "Alice", "age": 30}
new = {"name": "Alice", "age": 31, "city": "NYC"}
result = diff_json(old, new)
print(result.diff_output)
# [
#   {"op": "replace", "path": "/age", "value": 31},
#   {"op": "add", "path": "/city", "value": "NYC"}
# ]
```

### diff_structured()

```python
def diff_structured(
    old: dict[str, Any],
    new: dict[str, Any],
    ignore_keys: set[str] | None = None,
) -> DiffResult
```

Generate a structured diff between two dictionaries.

```python
old = {"status": "draft", "title": "My Post"}
new = {"status": "published", "title": "My Post"}
result = diff_structured(old, new)
```

---

## ApprovalService

```python
from stageflow.tools import (
    ApprovalService,
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStatus,
    get_approval_service,
)
```

Service for HITL approval flows.

### ApprovalStatus

| Value | Description |
|-------|-------------|
| `PENDING` | Awaiting decision |
| `APPROVED` | User approved |
| `DENIED` | User denied |
| `EXPIRED` | Request expired |

### ApprovalRequest

| Attribute | Type | Description |
|-----------|------|-------------|
| `action_id` | `UUID` | Action identifier |
| `tool_name` | `str` | Tool name |
| `message` | `str` | Approval message |
| `payload` | `dict` | Action payload |

### Methods

#### `request(request: ApprovalRequest) -> None`

Request approval.

#### `get_status(action_id: UUID) -> ApprovalStatus`

Get approval status.

#### `decide(action_id: UUID, decision: ApprovalDecision) -> None`

Record approval decision.

---

## Errors

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
```

| Error | Description |
|-------|-------------|
| `ToolError` | Base tool error |
| `ToolNotFoundError` | Tool not registered |
| `ToolDeniedError` | Tool denied (behavior gating) |
| `ToolExecutionError` | Execution failed |
| `ToolApprovalDeniedError` | Approval denied |
| `ToolApprovalTimeoutError` | Approval timed out |
| `ToolUndoError` | Undo operation failed |

---

## Events

```python
from stageflow.tools import (
    ToolInvokedEvent,
    ToolStartedEvent,
    ToolCompletedEvent,
    ToolFailedEvent,
    ToolDeniedEvent,
    ToolUndoneEvent,
    ToolUndoFailedEvent,
)
```

Tool execution events for observability.

---

## Usage Example

```python
from uuid import uuid4
from dataclasses import dataclass
from stageflow.tools import (
    BaseTool,
    ToolInput,
    ToolOutput,
    ToolDefinition,
    get_tool_registry,
    register_tool,
)

# Simple tool using BaseTool
@register_tool
class GreetTool(BaseTool):
    name = "greet"
    description = "Greet a user"
    action_type = "GREET"
    
    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        name = input.action.payload.get("name", "World")
        return ToolOutput.ok(data={"message": f"Hello, {name}!"})

# Advanced tool with undo
async def edit_handler(input: ToolInput) -> ToolOutput:
    doc_id = input.payload["document_id"]
    content = input.payload["content"]
    original = get_document(doc_id)
    set_document(doc_id, content)
    return ToolOutput.ok(
        data={"updated": True},
        undo_metadata={"doc_id": doc_id, "original": original},
    )

async def edit_undo(metadata):
    set_document(metadata.undo_data["doc_id"], metadata.undo_data["original"])

edit_tool = ToolDefinition(
    name="edit_document",
    action_type="EDIT_DOCUMENT",
    handler=edit_handler,
    undoable=True,
    undo_handler=edit_undo,
    requires_approval=True,
    allowed_behaviors=("doc_edit",),
)

# Execute tools
@dataclass
class Action:
    id: uuid4
    type: str
    payload: dict

registry = get_tool_registry()
action = Action(id=uuid4(), type="GREET", payload={"name": "Alice"})
result = await registry.execute(action, ctx={})
print(result.data)  # {"message": "Hello, Alice!"}
```
