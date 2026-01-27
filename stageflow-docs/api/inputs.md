# StageInputs API Reference

```python
from stageflow.stages.inputs import StageInputs, create_stage_inputs, UndeclaredDependencyError
```

Immutable view of prior stage outputs available to a stage. Provides validated access to dependency outputs and injected services.

## UndeclaredDependencyError

```python
from stageflow.stages.inputs import UndeclaredDependencyError
```

Raised when a stage accesses an undeclared dependency in strict mode.

**Attributes:**
- `stage_name`: The undeclared dependency that was accessed
- `declared_deps`: The set of declared dependencies
- `accessing_stage`: The stage that tried to access the dependency

**Example:**
```python
try:
    value = ctx.inputs.get_from("undeclared_stage", "key")
except UndeclaredDependencyError as e:
    print(f"Stage '{e.accessing_stage}' tried to access '{e.stage_name}'")
    print(f"Declared dependencies: {e.declared_deps}")
```

---

## StageInputs

```python
from stageflow.stages.inputs import StageInputs
```

Immutable dataclass providing access to prior stage outputs and injected services.

### Constructor

```python
StageInputs(
    snapshot: ContextSnapshot,
    prior_outputs: dict[str, StageOutput] = {},
    ports: CorePorts | LLMPorts | AudioPorts | None = None,
    declared_deps: frozenset[str] = frozenset(),
    stage_name: str | None = None,
    strict: bool = True
)
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `snapshot` | `ContextSnapshot` | Original immutable snapshot with run identity |
| `prior_outputs` | `dict[str, StageOutput]` | Outputs from declared dependency stages only |
| `ports` | `CorePorts \| LLMPorts \| AudioPorts \| None` | Injected capabilities for the stage |
| `declared_deps` | `frozenset[str]` | Set of declared dependency stage names |
| `stage_name` | `str \| None` | Name of the receiving stage (for error messages) |
| `strict` | `bool` | If True, validates dependency access |

### Methods

#### `get(key: str, default: Any = None) -> Any`

Get a value from any prior stage's output data.

**Parameters:**
- `key`: The key to search for in output.data dicts
- `default`: Value to return if key not found

**Returns:** The value from the first prior output containing the key, or default

**Raises:**
- `TypeError`: Key is None or not a string
- `ValueError`: Key is an empty string

**Example:**
```python
# Search all prior outputs for "text"
text = ctx.inputs.get("text", default="")

# This will raise TypeError:
text = ctx.inputs.get(None)  # TypeError: StageInputs key must be provided
```

#### `get_from(stage_name: str, key: str, default: Any = None) -> Any`

Get a specific value from a specific stage's output.

**Parameters:**
- `stage_name`: Name of the dependency stage
- `key`: The key to look up in that stage's output.data
- `default`: Value to return if stage not found or key not present

**Returns:** The value from the specified stage's output, or default

**Raises:**
- `TypeError`: Key is None or not a string
- `ValueError`: Key is an empty string
- `UndeclaredDependencyError`: If strict=True and stage is not in declared_deps

**Example:**
```python
# Get route from router stage
route = ctx.inputs.get_from("router", "route", default="general")

# These will raise errors:
route = ctx.inputs.get_from("router", None)       # TypeError: StageInputs key must be a string
route = ctx.inputs.get_from("router", "")        # ValueError: StageInputs key cannot be empty
```

#### `has_output(stage_name: str) -> bool`

Check if a stage has produced output.

**Parameters:**
- `stage_name`: Name of the stage to check

**Returns:** True if the stage has been executed and produced output

**Raises:**
- `UndeclaredDependencyError`: If strict=True and stage is not in declared_deps

**Example:**
```python
if ctx.inputs.has_output("validator"):
    output = ctx.inputs.get_output("validator")
```

#### `get_output(stage_name: str) -> StageOutput | None`

Get a stage's complete output.

**Parameters:**
- `stage_name`: Name of the stage

**Returns:** The StageOutput if found, None otherwise

**Raises:**
- `UndeclaredDependencyError`: If strict=True and stage is not in declared_deps

**Example:**
```python
output = ctx.inputs.get_output("llm_stage")
if output and output.data:
    response = output.data.get("response")
```

#### `require_from(stage_name: str, key: str) -> Any`

Get a required value from a specific stage's output.

**Parameters:**
- `stage_name`: Name of the dependency stage
- `key`: The key to look up in that stage's output.data

**Returns:** The value from the specified stage's output

**Raises:**
- `TypeError`: Key is None or not a string
- `ValueError`: Key is an empty string
- `UndeclaredDependencyError`: If strict=True and stage is not declared
- `KeyError`: If stage has no output or key is not in output.data

**Example:**
```python
# Get required token (will raise KeyError if missing)
token = ctx.inputs.require_from("auth", "token")

# These will raise errors:
token = ctx.inputs.require_from("auth", None)     # TypeError: StageInputs key must be provided
token = ctx.inputs.require_from("auth", "")      # ValueError: StageInputs key cannot be empty
```

---

## Factory Functions

### `create_stage_inputs(...)`

Factory function to create StageInputs instances.

```python
from stageflow.stages.inputs import create_stage_inputs

inputs = create_stage_inputs(
    snapshot=snapshot,
    prior_outputs={"stage_a": output},
    ports=CorePorts(db=db_session),
    declared_deps=["stage_a"],
    stage_name="my_stage",
    strict=True
)
```

**Parameters:**
- `snapshot`: The original immutable ContextSnapshot
- `prior_outputs`: Dict of outputs from dependency stages (optional)
- `ports`: Injected capabilities for the stage (optional)
- `declared_deps`: Set of declared dependency stage names (optional)
- `stage_name`: Name of the stage receiving these inputs (optional)
- `strict`: If True, validates dependency access (default: True)

**Returns:** StageInputs instance ready for use by stages

---

## Usage Examples

### Basic Input Access

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Get any value from prior stages
    text = ctx.inputs.get("text", default="")
    
    # Get specific value from a stage
    route = ctx.inputs.get_from("router", "route", default="general")
    
    # Get required value (raises if missing)
    user_id = ctx.inputs.require_from("auth", "user_id")
    
    return StageOutput.ok(processed_text=text.upper())
```

### Dependency Validation

```python
# In pipeline definition
pipeline.with_stage("my_stage", MyStage, StageKind.WORK, 
                   dependencies=["auth", "router"]))  # Declared deps

# In stage implementation
async def execute(self, ctx: StageContext) -> StageOutput:
    # This works - "auth" is declared
    token = ctx.inputs.get_from("auth", "token")
    
    # This raises UndeclaredDependencyError - "cache" not declared
    cached = ctx.inputs.get_from("cache", "data")  # Error!
```

### Error Handling

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    try:
        # Get required value
        token = ctx.inputs.require_from("auth", "token")
    except KeyError as e:
        return StageOutput.fail(error=f"Missing auth token: {e}")
    except UndeclaredDependencyError as e:
        return StageOutput.fail(error=f"Dependency error: {e}")
    
    # Continue with token...
```

### Ports Access

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Access injected services
    ports = ctx.inputs.ports
    if ports and ports.db:
        await ports.db.save_interaction(...)
    
    if ports and hasattr(ports, 'llm') and ports.llm:
        response = await ports.llm.chat(messages)
    
    return StageOutput.ok()
```

---

## Best Practices

1. **Use explicit dependencies** - Declare dependencies in pipeline and use `get_from()`
2. **Validate required inputs** - Use `require_from()` for critical data
3. **Handle missing data gracefully** - Provide defaults for optional data
4. **Use strict mode in production** - Catch undeclared dependencies early
5. **Type check keys** - All methods validate that keys are non-empty strings
6. **Document expected outputs** - Clearly document what keys each stage provides
