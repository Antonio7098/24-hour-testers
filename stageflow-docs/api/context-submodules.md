# Context Sub-modules API Reference

This document provides the API reference for Stageflow's context sub-modules, which provide specialized context handling for different use cases.

## ContextBag

```python
from stageflow.context import ContextBag, DataConflictError
```

Thread-safe output bag with conflict detection for parallel stage execution.

### DataConflictError

```python
from stageflow.context import DataConflictError
```

Raised when multiple stages attempt to write the same key.

**Attributes:**
- `key`: The conflicting key
- `existing_writer`: Stage that first wrote the key
- `new_writer`: Stage attempting to overwrite

**Example:**
```python
try:
    await bag.write("result", "value1", "stage_a")
    await bag.write("result", "value2", "stage_b")  # Raises
except DataConflictError as e:
    print(f"Conflict on key '{e.key}': {e.existing_writer} vs {e.new_writer}")
```

---

### ContextBag

```python
from stageflow.context import ContextBag
```

Thread-safe output bag with conflict detection.

**Constructor:**
```python
bag = ContextBag()
```

**Methods:**

#### `async write(key: str, value: Any, stage_name: str) -> None`

Write a key-value pair, rejecting duplicates.

**Parameters:**
- `key`: The key to write
- `value`: The value to store
- `stage_name`: Name of the stage performing the write

**Raises:** `DataConflictError` if key was already written by another stage

**Example:**
```python
bag = ContextBag()
await bag.write("user_input", "Hello", "stt_stage")
await bag.write("llm_response", "Hi there!", "llm_stage")
```

#### `read(key: str, default: Any = None) -> Any`

Read a value (no lock needed for reads).

**Parameters:**
- `key`: The key to read
- `default`: Value to return if key not found

**Returns:** The stored value or default

**Example:**
```python
value = bag.read("user_input", "default_value")
```

#### `has(key: str) -> bool`

Check if a key exists.

**Parameters:**
- `key`: The key to check

**Returns:** `True` if key exists, `False` otherwise

**Example:**
```python
if bag.has("llm_response"):
    print("LLM has responded")
```

#### `keys() -> list[str]`

Get all stored keys.

**Returns:** List of all keys in the bag

**Example:**
```python
all_keys = bag.keys()
print(f"Available keys: {all_keys}")
```

#### `get_writer(key: str) -> str | None`

Get the stage that wrote a specific key.

**Parameters:**
- `key`: The key to look up

**Returns:** Stage name that wrote the key, or None if not found

**Example:**
```python
writer = bag.get_writer("user_input")
print(f"Key written by: {writer}")
```

#### `to_dict() -> dict[str, Any]`

Convert bag contents to a dictionary.

**Returns:** Copy of the internal data dictionary

**Example:**
```python
data = bag.to_dict()
print(f"Bag contents: {data}")
```

---

## Conversation

```python
from stageflow.context import Conversation
```

Grouped conversation data bundle with message history and routing decisions.

### Constructor

```python
Conversation(
    messages: list[Message] = [],
    routing_decision: RoutingDecision | None = None
)
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `messages` | `list[Message]` | Ordered list of conversation messages |
| `routing_decision` | `RoutingDecision \| None` | The routing decision made by the router |

**Example:**
```python
from stageflow.context import Conversation, Message, RoutingDecision

conversation = Conversation(
    messages=[
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi there!"),
    ],
    routing_decision=RoutingDecision(
        agent_id="coach",
        pipeline_name="practice",
        topology="fast_kernel",
    )
)
```

### Methods

#### `to_dict() -> dict[str, Any]`

Convert to JSON-serializable dictionary.

**Returns:** Dictionary representation of the conversation

**Example:**
```python
data = conversation.to_dict()
print(f"Message count: {len(data['messages'])}")
```

#### `from_dict(data: dict[str, Any]) -> Conversation`

Create from dictionary.

**Parameters:**
- `data`: Dictionary representation of conversation

**Returns:** New Conversation instance

**Example:**
```python
data = {
    "messages": [
        {"role": "user", "content": "Hello", "timestamp": None, "metadata": {}},
        {"role": "assistant", "content": "Hi there!", "timestamp": None, "metadata": {}}
    ],
    "routing_decision": None
}

conversation = Conversation.from_dict(data)
```

#### `with_message(message: Message) -> Conversation`

Return a new Conversation with an additional message.

**Parameters:**
- `message`: The message to add

**Returns:** New Conversation with the message appended

**Example:**
```python
new_message = Message(role="user", content="How are you?")
updated_conversation = conversation.with_message(new_message)
```

### Properties

#### `last_user_message -> Message | None`

Get the last user message in the conversation.

**Returns:** The most recent user message or None

**Example:**
```python
last_user = conversation.last_user_message
if last_user:
    print(f"Last user said: {last_user.content}")
```

#### `last_assistant_message -> Message | None`

Get the last assistant message in the conversation.

**Returns:** The most recent assistant message or None

**Example:**
```python
last_assistant = conversation.last_assistant_message
if last_assistant:
    print(f"Last assistant said: {last_assistant.content}")
```

#### `message_count -> int`

Get the number of messages in the conversation.

**Returns:** Total message count

**Example:**
```python
count = conversation.message_count
print(f"Conversation has {count} messages")
```

---

## Enrichments

```python
from stageflow.context import ProfileEnrichment, MemoryEnrichment, DocumentEnrichment
```

Context enrichment types for adding metadata to conversations.

### ProfileEnrichment

```python
from stageflow.context import ProfileEnrichment
```

User profile enrichment data.

**Constructor:**
```python
ProfileEnrichment(
    user_id: str,
    preferences: dict[str, Any] = {},
    history: list[dict[str, Any]] = [],
    metadata: dict[str, Any] = {}
)
```

**Attributes:**
- `user_id`: User identifier
- `preferences`: User preferences and settings
- `history`: User interaction history
- `metadata`: Additional profile metadata

**Example:**
```python
profile = ProfileEnrichment(
    user_id="user123",
    preferences={"language": "en", "theme": "dark"},
    history=[{"action": "login", "timestamp": "2023-01-01"}],
    metadata={"tier": "premium"}
)
```

### MemoryEnrichment

```python
from stageflow.context import MemoryEnrichment
```

Memory enrichment data describing what the pipeline already knows about the user.

**Constructor:**
```python
MemoryEnrichment(
    recent_topics: list[str] | None = None,
    key_facts: list[str] | None = None,
    interaction_history_summary: str | None = None,
)
```

**Attributes:**
- `recent_topics`: Short bullet list of what has been discussed recently.
- `key_facts`: Canonical facts we want to retain (preferences, goals, etc.).
- `interaction_history_summary`: Optional natural-language summary of the chat history.

> Legacy aliases `short_term`, `long_term`, and `summary` are still accepted but emit a
> warning at runtime. Prefer the canonical field names above going forward.

**Example:**
```python
memory = MemoryEnrichment(
    recent_topics=["Onboarding", "SDK"],
    key_facts=["Prefers async examples"],
    interaction_history_summary="Walked through Stageflow install, now exploring agents",
)
```

### DocumentEnrichment

```python
from stageflow.context import DocumentEnrichment
```

Document enrichment data for context-aware processing.

**Constructor:**
```python
DocumentEnrichment(
    document_id: str | None = None,
    document_type: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
)
```

**Attributes:**
- `document_id`: Stable identifier for the document.
- `document_type`: Format label such as `pdf`, `markdown`, etc.
- `blocks`: Structured blocks (text, tables, etc.) already extracted from the document.
- `metadata`: Additional structured metadata (page counts, tags, source system, ...).

The constructor also accepts legacy aliases (`doc_id`, `doc_type`, and `content`/`documents`).
They are automatically converted into the canonical fields while emitting warnings so you can
modernize gradually.

**Example:**
```python
doc = DocumentEnrichment(
    document_id="kb-42",
    document_type="markdown",
    blocks=[
        {"type": "heading", "level": 2, "content": "Install"},
        {"type": "text", "content": "Run `pip install stageflow-core`."},
    ],
    metadata={"source": "knowledge_base", "language": "en"},
)
```

---

## Extensions

```python
from stageflow.context import ExtensionRegistry, ExtensionHelper, TypedExtension
```

Extension system for adding application-specific data to contexts.

### ExtensionRegistry

```python
from stageflow.context import ExtensionRegistry
```

Registry for managing context extensions.

**Constructor:**
```python
registry = ExtensionRegistry()
```

**Methods:**

#### `register(extension: TypedExtension) -> None`

Register an extension.

**Parameters:**
- `extension`: The extension to register

**Example:**
```python
registry.register(TypedExtension("user_prefs", UserPrefsExtension))
```

#### `get(name: str) -> TypedExtension | None`

Get a registered extension.

**Parameters:**
- `name`: Extension name

**Returns:** The extension or None if not found

**Example:**
```python
ext = registry.get("user_prefs")
if ext:
    data = ext.extract(ctx)
```

### ExtensionHelper

```python
from stageflow.context import ExtensionHelper
```

Utility class for working with extensions.

**Methods:**

#### `get_extension(ctx, name: str) -> Any`

Get extension data from context.

**Parameters:**
- `ctx`: Context snapshot
- `name`: Extension name

**Returns:** Extension data or None

**Example:**
```python
prefs = ExtensionHelper.get_extension(ctx, "user_prefs")
if prefs:
    print(f"User language: {prefs.language}")
```

#### `has_extension(ctx, name: str) -> bool`

Check if extension exists in context.

**Parameters:**
- `ctx`: Context snapshot
- `name`: Extension name

**Returns:** True if extension exists

**Example:**
```python
if ExtensionHelper.has_extension(ctx, "user_prefs"):
    # Use user preferences
    pass
```

### TypedExtension

```python
from stageflow.context import TypedExtension
```

Base class for typed extensions.

**Constructor:**
```python
TypedExtension(name: str, extractor: Callable)
```

**Parameters:**
- `name`: Extension name
- `extractor`: Function to extract extension data

**Example:**
```python
def extract_user_prefs(ctx):
    return ctx.extensions.get("user_prefs")

ext = TypedExtension("user_prefs", extract_user_prefs)
```

---

## Identity

```python
from stageflow.context import RunIdentity
```

Identity information for pipeline runs.

### RunIdentity

```python
from stageflow.context import RunIdentity
```

Run identity with user and organization information.

**Constructor:**
```python
RunIdentity(
    user_id: UUID,
    org_id: UUID | None = None,
    session_id: UUID | None = None,
    metadata: dict[str, Any] = {}
)
```

**Attributes:**
- `user_id`: User identifier
- `org_id`: Organization identifier (optional)
- `session_id`: Session identifier (optional)
- `metadata`: Additional identity metadata

**Methods:**

#### `to_dict() -> dict[str, Any]`

Convert to dictionary.

**Example:**
```python
identity = RunIdentity(
    user_id=uuid4(),
    org_id=uuid4(),
    session_id=uuid4()
)

data = identity.to_dict()
print(f"User: {data['user_id']}")
```

---

## Output Bag

```python
from stageflow.context import OutputBag
```

Output bag for collecting stage results.

### OutputBag

```python
from stageflow.context import OutputBag
```

Bag for collecting and managing stage outputs.

**Constructor:**
```python
bag = OutputBag()
```

**Methods:**

#### `add_output(stage_name: str, output: StageOutput) -> None`

Add a stage output to the bag.

**Parameters:**
- `stage_name`: Name of the stage
- `output`: The stage output

**Example:**
```python
bag.add_output("llm_stage", StageOutput.ok(response="Hello!"))
```

#### `get_output(stage_name: str) -> StageOutput | None`

Get output for a specific stage.

**Parameters:**
- `stage_name`: Name of the stage

**Returns:** Stage output or None

**Example:**
```python
output = bag.get_output("llm_stage")
if output and output.data:
    print(f"LLM said: {output.data.get('response')}")
```

#### `get_all_outputs() -> dict[str, StageOutput]`

Get all stage outputs.

**Returns:** Dictionary mapping stage names to outputs

**Example:**
```python
all_outputs = bag.get_all_outputs()
for stage_name, output in all_outputs.items():
    print(f"{stage_name}: {output.status}")
```

---

## Types

```python
from stageflow.context import Message, RoutingDecision
```

Core context types.

### Message

```python
from stageflow.context import Message
```

Represents a conversation message.

**Constructor:**
```python
Message(
    role: str,
    content: str,
    timestamp: datetime | None = None,
    metadata: dict[str, Any] = {}
)
```

**Attributes:**
- `role`: Message role (user, assistant, system)
- `content`: Message content
- `timestamp`: Message timestamp (optional)
- `metadata`: Additional message metadata

**Example:**
```python
msg = Message(
    role="user",
    content="Hello, how are you?",
    timestamp=datetime.now(UTC),
    metadata={"source": "web"}
)
```

### RoutingDecision

```python
from stageflow.context import RoutingDecision
```

Represents a routing decision for conversation handling.

**Constructor:**
```python
RoutingDecision(
    agent_id: str,
    pipeline_name: str,
    topology: str,
    reason: str | None = None
)
```

**Attributes:**
- `agent_id`: Selected agent identifier
- `pipeline_name`: Pipeline to use
- `topology`: Pipeline topology
- `reason`: Reason for the decision (optional)

**Example:**
```python
decision = RoutingDecision(
    agent_id="coach",
    pipeline_name="practice",
    topology="fast_kernel",
    reason="User wants to practice coding"
)
```

---

## Usage Examples

### Using ContextBag for Parallel Stages

```python
from stageflow.context import ContextBag, DataConflictError

async def parallel_processing():
    bag = ContextBag()
    
    # Parallel stages can safely write different keys
    tasks = [
        write_to_bag(bag, "stt_result", "transcribed text", "stt_stage"),
        write_to_bag(bag, "llm_result", "LLM response", "llm_stage"),
        write_to_bag(bag, "tts_result", "audio data", "tts_stage"),
    ]
    
    await asyncio.gather(*tasks)
    
    # Read results
    return {
        "transcript": bag.read("stt_result"),
        "response": bag.read("llm_result"),
        "audio": bag.read("tts_result")
    }

async def write_to_bag(bag, key, value, stage_name):
    try:
        await bag.write(key, value, stage_name)
    except DataConflictError as e:
        print(f"Conflict detected: {e}")
```

### Building Conversations

```python
from stageflow.context import Conversation, Message, RoutingDecision

# Create conversation incrementally
conversation = Conversation()

# Add messages
conversation = conversation.with_message(
    Message(role="user", content="What's Python?")
)

conversation = conversation.with_message(
    Message(role="assistant", content="Python is a programming language...")
)

# Add routing decision
conversation.routing_decision = RoutingDecision(
    agent_id="tutor",
    pipeline_name="educational",
    topology="simple"
)

# Access conversation data
print(f"Messages: {conversation.message_count}")
print(f"Last user: {conversation.last_user_message.content if conversation.last_user_message else 'None'}")

# Serialize for storage
data = conversation.to_dict()
```

### Working with Extensions

```python
from stageflow.context import ExtensionRegistry, ExtensionHelper, TypedExtension

# Define custom extension
class UserPreferences:
    def __init__(self, language="en", theme="light"):
        self.language = language
        self.theme = theme

def extract_prefs(ctx):
    prefs_data = ctx.extensions.get("user_preferences", {})
    return UserPreferences(
        language=prefs_data.get("language", "en"),
        theme=prefs_data.get("theme", "light")
    )

# Register extension
registry = ExtensionRegistry()
registry.register(TypedExtension("user_preferences", extract_prefs))

# Use in pipeline
def process_with_preferences(ctx):
    prefs = ExtensionHelper.get_extension(ctx, "user_preferences")
    if prefs:
        return f"Response in {prefs.language} with {prefs.theme} theme"
    return "Default response"
```

### Managing Output Bags

```python
from stageflow.context import OutputBag
from stageflow.core import StageOutput

# Collect stage outputs
bag = OutputBag()

# Add outputs from different stages
bag.add_output("input_stage", StageOutput.ok(text="Hello"))
bag.add_output("process_stage", StageOutput.ok(processed="HELLO"))
bag.add_output("output_stage", StageOutput.ok(final="HELLO!"))

# Access specific outputs
input_output = bag.get_output("input_stage")
if input_output:
    print(f"Input: {input_output.data.get('text')}")

# Get all outputs for debugging
all_outputs = bag.get_all_outputs()
for stage_name, output in all_outputs.items():
    print(f"{stage_name}: {output.status.name}")
```

---

## Best Practices

1. **Use ContextBag for parallel stages** - Prevents data races and conflicts
2. **Structure conversations logically** - Use Message roles consistently
3. **Type extensions properly** - Use TypedExtension for type safety
4. **Handle conflicts gracefully** - Catch DataConflictError and provide fallbacks
5. **Serialize contexts properly** - Use to_dict()/from_dict() for persistence
6. **Keep metadata minimal** - Store only necessary enrichment data
7. **Use OutputBag for collection** - Centralize stage result management
