# Extensions

This guide covers the extension system for adding application-specific data to contexts.

## Overview

Extensions allow you to add custom, type-safe data to `ContextSnapshot` without modifying core stageflow types. This is useful for:

- Application-specific configuration
- Feature flags
- Custom enrichments
- Domain-specific data

## Basic Usage

### Adding Extension Data

```python
from stageflow.context import ContextSnapshot

snapshot = ContextSnapshot(
    pipeline_run_id=uuid4(),
    request_id=uuid4(),
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=None,
    interaction_id=uuid4(),
    topology="chat",
    execution_mode="default",
    extensions={
        "skills": {
            "active_skill_ids": ["python", "javascript"],
            "current_level": "intermediate",
        },
        "feature_flags": {
            "new_ui": True,
            "beta_features": False,
        },
    },
)
```

### Accessing Extension Data

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Access extensions dict
    extensions = ctx.snapshot.extensions
    
    # Get specific extension
    skills = extensions.get("skills", {})
    active_skills = skills.get("active_skill_ids", [])
    
    # Use in logic
    if "python" in active_skills:
        # Python-specific handling
        ...
```

## Typed Extensions

For type safety, use the extension registry system.

### Define Extension Type

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SkillsExtension:
    """Skills configuration extension."""
    
    active_skill_ids: list[str] = field(default_factory=list)
    current_level: str | None = None
    skill_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "SkillsExtension":
        return cls(
            active_skill_ids=data.get("active_skill_ids", []),
            current_level=data.get("current_level"),
            skill_metadata=data.get("skill_metadata", {}),
        )

    def to_dict(self) -> dict:
        return {
            "active_skill_ids": self.active_skill_ids,
            "current_level": self.current_level,
            "skill_metadata": self.skill_metadata,
        }
```

### Register Extension Type

```python
from stageflow.extensions import ExtensionRegistry

# Register the extension type
ExtensionRegistry.register("skills", SkillsExtension)
```

### Use Typed Extension

```python
from stageflow.extensions import ExtensionHelper

async def execute(self, ctx: StageContext) -> StageOutput:
    # Get typed extension
    skills = ExtensionHelper.get(
        ctx.snapshot.extensions,
        "skills",
        SkillsExtension,
    )
    
    if skills:
        # IDE knows skills.active_skill_ids is list[str]
        for skill_id in skills.active_skill_ids:
            ...
        
        # Type-safe access
        level = skills.current_level
```

## Extension Registry

### Registration

```python
from stageflow.extensions import ExtensionRegistry

# Register with type
ExtensionRegistry.register("skills", SkillsExtension)
ExtensionRegistry.register("feature_flags", FeatureFlagsExtension)
ExtensionRegistry.register("custom_config", CustomConfigExtension)

# Check if registered
if ExtensionRegistry.is_registered("skills"):
    ...

# Get registered type
ext_type = ExtensionRegistry.get_type("skills")
```

### Validation

```python
# Validate extension data against registered type
from stageflow.extensions import ExtensionRegistry

def validate_extensions(extensions: dict) -> list[str]:
    """Validate extension data against registered types."""
    errors = []
    
    for key, data in extensions.items():
        if ExtensionRegistry.is_registered(key):
            ext_type = ExtensionRegistry.get_type(key)
            try:
                ext_type.from_dict(data)
            except Exception as e:
                errors.append(f"Invalid {key} extension: {e}")
    
    return errors
```

## Extension Helper

### Getting Extensions

```python
from stageflow.extensions import ExtensionHelper

# Get with type
skills = ExtensionHelper.get(
    extensions=ctx.snapshot.extensions,
    key="skills",
    extension_type=SkillsExtension,
)

# Returns None if not present or invalid
if skills is None:
    skills = SkillsExtension()  # Use default
```

### Creating Extensions

```python
from stageflow.extensions import ExtensionHelper

# Create extension helper for building snapshots
def create_skills_extension(
    active_skill_ids: list[str],
    current_level: str | None = None,
) -> dict:
    """Create skills extension data."""
    return {
        "active_skill_ids": active_skill_ids,
        "current_level": current_level,
    }

# Use when creating snapshot
snapshot = ContextSnapshot(
    ...,
    extensions={
        "skills": create_skills_extension(
            active_skill_ids=["python"],
            current_level="beginner",
        ),
    },
)
```

## Common Extension Patterns

### Feature Flags

```python
@dataclass
class FeatureFlagsExtension:
    """Feature flags for the current user/org."""
    
    flags: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureFlagsExtension":
        return cls(flags=data.get("flags", data))

    def is_enabled(self, flag: str) -> bool:
        return self.flags.get(flag, False)


# Usage in stage
async def execute(self, ctx: StageContext) -> StageOutput:
    flags = ExtensionHelper.get(
        ctx.snapshot.extensions,
        "feature_flags",
        FeatureFlagsExtension,
    )
    
    if flags and flags.is_enabled("new_algorithm"):
        return await self._new_algorithm(ctx)
    else:
        return await self._old_algorithm(ctx)
```

### Telemetry & Streaming Configuration

Extensions can store per-tenant telemetry preferences that stages and interceptors consume:

```python
@dataclass
class TelemetryExtension:
    enable_streaming_events: bool = True
    buffered_exporter_threshold: float = 0.8
    allowed_stream_events: set[str] = field(default_factory=lambda: {"stream.chunk_dropped", "stream.buffer_overflow"})

    @classmethod
    def from_dict(cls, data: dict) -> "TelemetryExtension":
        return cls(
            enable_streaming_events=data.get("enable_streaming_events", True),
            buffered_exporter_threshold=data.get("buffered_exporter_threshold", 0.8),
            allowed_stream_events=set(data.get("allowed_stream_events", [])) or {"stream.chunk_dropped", "stream.buffer_overflow"},
        )
```

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    telemetry = ExtensionHelper.get(ctx.snapshot.extensions, "telemetry", TelemetryExtension)

    if telemetry and telemetry.enable_streaming_events:
        queue = ChunkQueue(event_emitter=ctx.try_emit_event)
        buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)
        exporter = BufferedExporter(
            sink=my_sink,
            on_overflow=lambda dropped, size: ctx.try_emit_event(
                "analytics.overflow",
                {"dropped": dropped, "buffer_size": size},
            ),
            high_water_mark=telemetry.buffered_exporter_threshold,
        )
```


### Application Config

```python
@dataclass
class AppConfigExtension:
    """Application-specific configuration."""
    
    theme: str = "default"
    language: str = "en"
    timezone: str = "UTC"
    custom_settings: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfigExtension":
        return cls(
            theme=data.get("theme", "default"),
            language=data.get("language", "en"),
            timezone=data.get("timezone", "UTC"),
            custom_settings=data.get("custom_settings", {}),
        )
```

### Domain-Specific Data

```python
@dataclass
class SalesExtension:
    """Sales-specific context data."""
    
    opportunity_id: str | None = None
    deal_stage: str | None = None
    account_tier: str = "standard"
    sales_rep_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SalesExtension":
        return cls(
            opportunity_id=data.get("opportunity_id"),
            deal_stage=data.get("deal_stage"),
            account_tier=data.get("account_tier", "standard"),
            sales_rep_id=data.get("sales_rep_id"),
        )


# Usage
async def execute(self, ctx: StageContext) -> StageOutput:
    sales = ExtensionHelper.get(
        ctx.snapshot.extensions,
        "sales",
        SalesExtension,
    )
    
    if sales and sales.deal_stage == "negotiation":
        # Special handling for negotiation stage
        ...
```

### Experiment Configuration

```python
@dataclass
class ExperimentExtension:
    """A/B testing and experiment configuration."""
    
    experiment_id: str | None = None
    variant: str = "control"
    cohort: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentExtension":
        return cls(
            experiment_id=data.get("experiment_id"),
            variant=data.get("variant", "control"),
            cohort=data.get("cohort"),
            metadata=data.get("metadata", {}),
        )

    def is_treatment(self) -> bool:
        return self.variant != "control"
```

## Serialization

Extensions are automatically serialized with the snapshot:

```python
# Snapshot with extensions
snapshot = ContextSnapshot(
    ...,
    extensions={
        "skills": {"active_skill_ids": ["python"]},
        "config": {"theme": "dark"},
    },
)

# Serialize
data = snapshot.to_dict()
# data["extensions"] = {"skills": {...}, "config": {...}}

# Deserialize
restored = ContextSnapshot.from_dict(data)
# restored.extensions == snapshot.extensions
```

## Best Practices

### 1. Use Descriptive Keys

```python
# Good
extensions = {
    "skills_configuration": {...},
    "user_preferences": {...},
    "experiment_assignment": {...},
}

# Bad
extensions = {
    "s": {...},
    "data": {...},
    "x": {...},
}
```

### 2. Provide Defaults

```python
@dataclass
class MyExtension:
    required_field: str
    optional_field: str = "default"
    list_field: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "MyExtension":
        return cls(
            required_field=data.get("required_field", ""),
            optional_field=data.get("optional_field", "default"),
            list_field=data.get("list_field", []),
        )
```

### 3. Handle Missing Extensions

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    skills = ExtensionHelper.get(
        ctx.snapshot.extensions,
        "skills",
        SkillsExtension,
    )
    
    # Always handle None case
    if skills is None:
        # Use sensible defaults
        active_skills = []
    else:
        active_skills = skills.active_skill_ids
```

### 4. Keep Extensions Focused

```python
# Good: Separate concerns
extensions = {
    "skills": {...},
    "preferences": {...},
    "experiments": {...},
}

# Bad: Kitchen sink
extensions = {
    "everything": {
        "skills": {...},
        "preferences": {...},
        "experiments": {...},
        "config": {...},
        "flags": {...},
    },
}
```

### 5. Document Extensions

```python
@dataclass
class SkillsExtension:
    """Skills configuration for the current user.
    
    Attributes:
        active_skill_ids: List of skill IDs the user is currently practicing
        current_level: User's current proficiency level
        skill_metadata: Additional skill-specific data
    
    Example:
        {
            "active_skill_ids": ["python", "javascript"],
            "current_level": "intermediate",
            "skill_metadata": {"python": {"lessons_completed": 5}}
        }
    """
    ...
```

## Testing Extensions

```python
import pytest
from stageflow.extensions import ExtensionRegistry, ExtensionHelper

@pytest.fixture
def skills_extension():
    return SkillsExtension(
        active_skill_ids=["python"],
        current_level="beginner",
    )

def test_extension_from_dict():
    data = {"active_skill_ids": ["python"], "current_level": "beginner"}
    ext = SkillsExtension.from_dict(data)
    
    assert ext.active_skill_ids == ["python"]
    assert ext.current_level == "beginner"

def test_extension_to_dict(skills_extension):
    data = skills_extension.to_dict()
    
    assert data["active_skill_ids"] == ["python"]
    assert data["current_level"] == "beginner"

def test_extension_helper_get():
    extensions = {"skills": {"active_skill_ids": ["python"]}}
    
    skills = ExtensionHelper.get(extensions, "skills", SkillsExtension)
    
    assert skills is not None
    assert skills.active_skill_ids == ["python"]

def test_extension_helper_returns_none_for_missing():
    extensions = {}
    
    skills = ExtensionHelper.get(extensions, "skills", SkillsExtension)
    
    assert skills is None
```

## Next Steps

- [Context & Data Flow](../guides/context.md) — How extensions fit in context
- [Testing Strategies](testing.md) — Test your extensions
- [Building Stages](../guides/stages.md) — Use extensions in stages
