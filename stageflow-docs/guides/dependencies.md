# Dependency Declaration Guide

This guide covers how to declare and manage stage dependencies in Stageflow pipelines.

## Overview

Stageflow enforces explicit dependency contracts between stages. When a stage tries to access output from another stage that isn't declared as a dependency, you'll get an `UndeclaredDependencyError`.

This strictness prevents subtle bugs from implicit data flow and enables the DAG executor to optimize parallel execution.

## Declaring Dependencies

Dependencies are declared when adding stages to a pipeline:

```python
from stageflow import Pipeline, StageKind

pipeline = (
    Pipeline()
    .with_stage("fetch_data", FetchStage, StageKind.ENRICH)
    .with_stage("transform", TransformStage, StageKind.TRANSFORM,
                dependencies=("fetch_data",))  # Declares dependency
    .with_stage("output", OutputStage, StageKind.WORK,
                dependencies=("transform",))
)
```

The `dependencies` parameter is a tuple of stage names that must complete before this stage runs.

## Accessing Upstream Data

In your stage's `execute` method, use `ctx.inputs` to access upstream outputs:

```python
class TransformStage:
    name = "transform"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Access specific data from a declared dependency
        data = ctx.inputs.get_from("fetch_data", "records")

        # Search all prior outputs for a key
        user_id = ctx.inputs.get("user_id")

        # Require a value (raises KeyError if missing)
        required_data = ctx.inputs.require_from("fetch_data", "records")

        # Downstream stages expect standardized provider metadata
        from stageflow.helpers import LLMResponse

        llm = LLMResponse(
            content=process(data),
            model="demo-mini",
            provider="mock",
            input_tokens=len(str(data)),
            output_tokens=42,
        )

        return StageOutput.ok(
            transformed=llm.content,
            llm=llm.to_dict(),
        )
```

### Input Methods

| Method | Description | Validates Dependency |
|--------|-------------|---------------------|
| `get_from(stage, key, default)` | Get specific key from specific stage | Yes |
| `require_from(stage, key)` | Get required key, raises if missing | Yes |
| `get(key, default)` | Search all outputs for key | No |
| `has_output(stage)` | Check if stage produced output | Yes |
| `get_output(stage)` | Get full StageOutput | Yes |

## Common Errors

### UndeclaredDependencyError

```
UndeclaredDependencyError: Stage 'transform': Attempted to access
undeclared dependency 'fetch_data'. Declared dependencies: ['router'].
Add 'fetch_data' to depends_on to fix this error.
```

**Fix**: Add the missing dependency:

```python
.with_stage("transform", TransformStage, StageKind.TRANSFORM,
            dependencies=("router", "fetch_data"))  # Add fetch_data
```

### Missing Required Dependency

```
KeyError: Required dependency 'fetch_data' has no output.
Ensure 'fetch_data' executes before this stage.
```

**Fix**: Ensure the dependency stage is in the pipeline and completes successfully.

## Dependency Linting

Use the CLI linter to detect dependency issues before runtime:

```bash
# Lint a pipeline file
python -m stageflow.cli lint my_pipeline.py

# Verbose output
python -m stageflow.cli lint my_pipeline.py --verbose

# JSON output for CI integration
python -m stageflow.cli lint my_pipeline.py --json

# Treat warnings as errors (strict mode)
python -m stageflow.cli lint my_pipeline.py --strict
```

### Programmatic Linting

```python
from stageflow.cli import lint_pipeline

pipeline = (
    Pipeline()
    .with_stage("a", StageA, StageKind.TRANSFORM)
    .with_stage("b", StageB, StageKind.TRANSFORM, dependencies=("a",))
)

result = lint_pipeline(pipeline)

if not result.valid:
    for issue in result.errors:
        print(f"{issue.stage_name}: {issue.message}")
        print(f"  Suggestion: {issue.suggestion}")
```

### Detected Issues

The linter detects:

1. **Circular dependencies**: A -> B -> C -> A
2. **Non-existent dependencies**: Depending on a stage not in the pipeline
3. **Self-dependencies**: A stage depending on itself
4. **Orphaned stages**: Stages with no connections (warning)

## Dependency Patterns

### Sequential Chain

```python
pipeline = (
    Pipeline()
    .with_stage("step1", Step1, StageKind.TRANSFORM)
    .with_stage("step2", Step2, StageKind.TRANSFORM, dependencies=("step1",))
    .with_stage("step3", Step3, StageKind.TRANSFORM, dependencies=("step2",))
)
```

### Fan-Out (Parallel)

```python
pipeline = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    # These run in parallel after input
    .with_stage("branch_a", BranchA, StageKind.TRANSFORM, dependencies=("input",))
    .with_stage("branch_b", BranchB, StageKind.TRANSFORM, dependencies=("input",))
    .with_stage("branch_c", BranchC, StageKind.TRANSFORM, dependencies=("input",))
)
```

### Fan-In (Merge)

```python
pipeline = (
    Pipeline()
    .with_stage("source_a", SourceA, StageKind.TRANSFORM)
    .with_stage("source_b", SourceB, StageKind.TRANSFORM)
    # Waits for both sources to complete
    .with_stage("merge", MergeStage, StageKind.TRANSFORM,
                dependencies=("source_a", "source_b"))
)
```

### Diamond Pattern

```python
pipeline = (
    Pipeline()
    .with_stage("start", StartStage, StageKind.TRANSFORM)
    .with_stage("left", LeftStage, StageKind.TRANSFORM, dependencies=("start",))
    .with_stage("right", RightStage, StageKind.TRANSFORM, dependencies=("start",))
    .with_stage("end", EndStage, StageKind.TRANSFORM,
                dependencies=("left", "right"))
)
```

## Best Practices

### 1. Minimize Dependencies

Only declare dependencies you actually need:

```python
# Good: Only depends on what it uses
.with_stage("llm", LLMStage, StageKind.TRANSFORM,
            dependencies=("router",))

# Bad: Unnecessary dependencies slow execution
.with_stage("llm", LLMStage, StageKind.TRANSFORM,
            dependencies=("router", "logger", "metrics", "unused"))
```

### 2. Use Descriptive Stage Names

```python
# Good: Clear what each stage does
.with_stage("fetch_user_profile", ProfileStage, ...)
.with_stage("enrich_with_history", HistoryStage, ...)

# Bad: Unclear names
.with_stage("stage1", ProfileStage, ...)
.with_stage("s2", HistoryStage, ...)
```

### 3. Document Complex Dependencies

```python
pipeline = (
    Pipeline()
    # Stage 1: Fetch user data (no deps, runs first)
    .with_stage("fetch_user", FetchUserStage, StageKind.ENRICH)

    # Stage 2: Fetch product data (parallel with fetch_user)
    .with_stage("fetch_products", FetchProductsStage, StageKind.ENRICH)

    # Stage 3: Combine data (waits for both fetches)
    .with_stage("combine", CombineStage, StageKind.TRANSFORM,
                dependencies=("fetch_user", "fetch_products"))
)
```

### 4. Run Linter in CI

```yaml
# .github/workflows/lint.yml
- name: Lint pipelines
  run: python -m stageflow.cli lint pipelines/ --strict --json > lint-results.json
```

### 5. Keep Telemetry Observable

When stages depend on streaming helpers or analytics exporters, wire telemetry emitters in the same dependency chain so backpressure events have a clear owner:

```python
from stageflow.helpers import ChunkQueue

class StreamingStage:
    dependencies = ("ingest_audio",)

    async def execute(self, ctx: StageContext) -> StageOutput:
        queue = ChunkQueue(event_emitter=ctx.emit_event)
        ...
```

This ensures dependency ordering matches telemetry ownership (e.g., `ingest_audio` must run before any queue events fire).

## Troubleshooting

### "Why is my stage running before its dependency?"

Stages run as soon as their dependencies complete. Check:
1. Is the dependency actually declared?
2. Did the dependency stage fail? (Failed stages still "complete")

### "Why is my stage waiting too long?"

The DAG executor maximizes parallelism. If a stage waits:
1. Its dependencies haven't completed yet
2. Check if you have unnecessary dependencies creating bottlenecks

### "How do I pass data between non-dependent stages?"

You can't - by design. If stage B needs data from stage A, declare the dependency:

```python
# This won't work - B can't access A's output
.with_stage("a", StageA, StageKind.TRANSFORM)
.with_stage("b", StageB, StageKind.TRANSFORM)  # No dependency on A

# This works
.with_stage("a", StageA, StageKind.TRANSFORM)
.with_stage("b", StageB, StageKind.TRANSFORM, dependencies=("a",))

# Make tool-call parsing explicit too
.with_stage(
    "agent",
    AgentStage,
    StageKind.AGENT,
    dependencies=("b",),
)
```

## Next Steps

- [Pipeline Building Guide](pipelines.md) - More on composing pipelines
- [Context Guide](context.md) - Data flow and context management
- [Testing Guide](../advanced/testing.md) - Testing pipeline dependencies
