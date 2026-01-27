# Pipeline Composition

This guide covers advanced patterns for composing and extending pipelines.

## Merging Pipelines

### Basic Composition

Use `compose()` to merge two pipelines:

```python
from stageflow import Pipeline, StageKind

# Base pipeline
base = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("input",))
)

# Extension pipeline
extension = (
    Pipeline()
    .with_stage("enrich", EnrichStage, StageKind.ENRICH)
    .with_stage("output", OutputStage, StageKind.TRANSFORM, dependencies=("process", "enrich"))
)

# Merged pipeline contains all stages
full = base.compose(extension)
```

### Stage Name Conflicts

When stage names conflict, the second pipeline wins:

```python
pipeline_a = Pipeline().with_stage("shared", StageA, StageKind.TRANSFORM)
pipeline_b = Pipeline().with_stage("shared", StageB, StageKind.TRANSFORM)

merged = pipeline_a.compose(pipeline_b)
# "shared" stage is now StageB
```

## Reusable Components

### Factory Functions

Create reusable pipeline components:

```python
def create_enrichment_component() -> Pipeline:
    """Reusable enrichment stages."""
    return (
        Pipeline()
        .with_stage("profile", ProfileEnrichStage(), StageKind.ENRICH)
        .with_stage("memory", MemoryEnrichStage(), StageKind.ENRICH)
        .with_stage("documents", DocumentEnrichStage(), StageKind.ENRICH)
    )

def create_guard_component() -> Pipeline:
    """Reusable guard stages."""
    return (
        Pipeline()
        .with_stage("input_guard", InputGuardStage(), StageKind.GUARD)
        .with_stage("output_guard", OutputGuardStage(), StageKind.GUARD)
    )

def create_chat_pipeline(llm_client) -> Pipeline:
    """Compose full chat pipeline from components."""
    return (
        create_guard_component()
        .compose(create_enrichment_component())
        .with_stage(
            "llm",
            LLMStage(llm_client),
            StageKind.TRANSFORM,
            dependencies=("input_guard", "profile", "memory"),
        )
        .with_stage(
            "output_guard",
            OutputGuardStage(),
            StageKind.GUARD,
            dependencies=("llm",),
        )
    )
```

### Parameterized Components

Create configurable components:

```python
def create_llm_component(
    model: str = "gpt-4",
    temperature: float = 0.7,
    dependencies: tuple[str, ...] = (),
) -> Pipeline:
    """Configurable LLM component."""
    return Pipeline().with_stage(
        "llm",
        LLMStage(model=model, temperature=temperature),
        StageKind.TRANSFORM,
        dependencies=dependencies,
    )

# Use with different configurations
fast_llm = create_llm_component(model="gpt-3.5-turbo", dependencies=("router",))
accurate_llm = create_llm_component(model="gpt-4", dependencies=("router", "enrich"))
```

### Instrumentation Hooks in Components

When building reusable components, expose observability hooks so callers can route telemetry consistently across composed pipelines:

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer, BufferedExporter

def create_streaming_component(event_emitter):
    queue = ChunkQueue(event_emitter=event_emitter)
    buffer = StreamingBuffer(event_emitter=event_emitter)

    exporter = BufferedExporter(
        sink=my_sink,
        on_overflow=lambda dropped, size: event_emitter(
            "analytics.overflow",
            {"dropped": dropped, "buffer_size": size},
        ),
        high_water_mark=0.85,
    )
    return queue, buffer, exporter
```

You can pass `ctx.try_emit_event` from any stage to wire telemetry for every subcomponent regardless of where it executes in the composed pipeline.

## Pipeline Variants

### Feature Flags

Create pipeline variants based on features:

```python
def create_pipeline(features: set[str]) -> Pipeline:
    pipeline = Pipeline().with_stage("input", InputStage, StageKind.TRANSFORM)
    
    if "enrichment" in features:
        pipeline = pipeline.with_stage("enrich", EnrichStage, StageKind.ENRICH)
    
    if "guardrails" in features:
        pipeline = pipeline.with_stage(
            "guard",
            GuardStage,
            StageKind.GUARD,
            dependencies=("input",),
        )
    
    # LLM depends on whatever stages are present
    deps = ["input"]
    if "enrichment" in features:
        deps.append("enrich")
    if "guardrails" in features:
        deps.append("guard")
    
    pipeline = pipeline.with_stage(
        "llm",
        LLMStage,
        StageKind.TRANSFORM,
        dependencies=tuple(deps),
    )
    
    return pipeline

# Create variants
basic_pipeline = create_pipeline(set())
enriched_pipeline = create_pipeline({"enrichment"})
full_pipeline = create_pipeline({"enrichment", "guardrails"})
```

### Topology Variants

Create pipelines for different topologies:

```python
def create_fast_pipeline() -> Pipeline:
    """Optimized for speed."""
    return (
        Pipeline()
        .with_stage("router", FastRouterStage, StageKind.ROUTE)
        .with_stage("llm", FastLLMStage, StageKind.TRANSFORM, dependencies=("router",))
    )

def create_accurate_pipeline() -> Pipeline:
    """Optimized for accuracy."""
    return (
        Pipeline()
        .with_stage("router", AccurateRouterStage, StageKind.ROUTE)
        .with_stage("enrich", EnrichStage, StageKind.ENRICH)
        .with_stage(
            "llm",
            AccurateLLMStage,
            StageKind.TRANSFORM,
            dependencies=("router", "enrich"),
        )
        .with_stage("validate", ValidationStage, StageKind.GUARD, dependencies=("llm",))
    )

# Register both
from stageflow import pipeline_registry

pipeline_registry.register("chat_fast", create_fast_pipeline())
pipeline_registry.register("chat_accurate", create_accurate_pipeline())
```

## Dependency Injection

### Service Injection

Inject services into pipeline components:

```python
class PipelineBuilder:
    def __init__(
        self,
        llm_client,
        profile_service,
        memory_service,
        guard_service,
    ):
        self.llm_client = llm_client
        self.profile_service = profile_service
        self.memory_service = memory_service
        self.guard_service = guard_service
    
    def build_chat_pipeline(self) -> Pipeline:
        return (
            Pipeline()
            .with_stage("guard", InputGuardStage(self.guard_service), StageKind.GUARD)
            .with_stage("profile", ProfileEnrichStage(self.profile_service), StageKind.ENRICH)
            .with_stage("memory", MemoryEnrichStage(self.memory_service), StageKind.ENRICH)
            .with_stage(
                "llm",
                LLMStage(self.llm_client),
                StageKind.TRANSFORM,
                dependencies=("guard", "profile", "memory"),
            )
            .with_stage(
                "tool_exec",
                ToolExecutorStage(self.registry),
                StageKind.WORK,
                dependencies=("llm",),
            )
        )

# Production
builder = PipelineBuilder(
    llm_client=RealLLMClient(),
    profile_service=RealProfileService(),
    memory_service=RealMemoryService(),
    guard_service=RealGuardService(),
)
production_pipeline = builder.build_chat_pipeline()

# Testing
test_builder = PipelineBuilder(
    llm_client=MockLLMClient(),
    profile_service=MockProfileService(),
    memory_service=MockMemoryService(),
    guard_service=MockGuardService(),
)
test_pipeline = test_builder.build_chat_pipeline()
```

### Tool Call Resolution in Components

If a composed pipeline includes an agent/tool stage, expose the `ToolRegistry.parse_and_resolve` helper so parent pipelines can emit observability signals consistently:

```python
class ToolExecutorStage:
    name = "tool_exec"
    kind = StageKind.WORK

    def __init__(self, registry):
        self.registry = registry

    async def execute(self, ctx: StageContext) -> StageOutput:
        tool_calls = ctx.inputs.get("llm_tool_calls", [])
        resolved, unresolved = self.registry.parse_and_resolve(tool_calls)

        for call in unresolved:
            ctx.emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})

        results = []
        for call in resolved:
            tool_input = ToolInput(action=call.arguments)
            result = await call.tool.execute(tool_input, ctx={"call_id": call.call_id})
            results.append(result)

        return StageOutput.ok(tool_results=[r.to_dict() for r in results])
```

## Dynamic Pipelines

### Runtime Pipeline Selection

Select pipelines at runtime:

```python
from stageflow import pipeline_registry

def get_pipeline_for_request(request) -> Pipeline:
    # Select based on request attributes
        return pipeline_registry.get("voice_pipeline")
    elif request.execution_mode == "practice":
        return pipeline_registry.get("practice_pipeline")
    else:
        return pipeline_registry.get("default_pipeline")
```

### Conditional Stage Inclusion

Add stages conditionally:

```python
def create_adaptive_pipeline(ctx) -> Pipeline:
    pipeline = Pipeline().with_stage("input", InputStage, StageKind.TRANSFORM)
    
    # Add enrichment only for authenticated users
    if ctx.user_id:
        pipeline = pipeline.with_stage("profile", ProfileEnrichStage, StageKind.ENRICH)
    
    # Add premium features for pro users
    if ctx.plan_tier in ("pro", "enterprise"):
        pipeline = pipeline.with_stage("advanced", AdvancedStage, StageKind.TRANSFORM)
    
    return pipeline

### Conditional Control Flow Tips

Stageflow executes every stage whose dependencies are satisfied. Router
output alone does **not** prevent downstream branches from running—you
must explicitly inspect the router decision and return
`StageOutput.skip()` for non-selected branches.

```python
class RouterStage:
    name = "router"
    kind = StageKind.ROUTE

    async def execute(self, ctx: StageContext) -> StageOutput:
        intent = (ctx.snapshot.input_text or "").strip().lower()
        if "math" in intent:
            return StageOutput.ok(route="math")
        if "sql" in intent:
            return StageOutput.ok(route="sql")
        return StageOutput.ok(route="default")


class MathStage:
    name = "math"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        route = ctx.inputs.get_from("router", "route", default="default")
        if route != "math":
            return StageOutput.skip(reason="not_math_route")
        # business logic here
        return StageOutput.ok()
```

Common patterns:

1. Make routers cheap and deterministic.
2. Downstream branches inspect router outputs and call `skip()` early to
   avoid wasted work.
3. Aggregate branch results via a WORK stage that inspects
   `ctx.inputs.get_output("branch", default=StageOutput.skip(...))`.

### Cancel Semantics

`StageOutput.cancel()` stops the **entire pipeline**, not just the
current branch. When a stage returns CANCEL, the executor raises
`UnifiedPipelineCancelled`, cancels outstanding tasks, and surfaces the
`cancel_reason` you provided. Reserve cancel for intentional shutdowns
(user abort, guardrail hard-stop, feature flag). If you merely want to
skip work, use `StageOutput.skip()` instead.

Recommended workflow:

1. Emit a telemetry event before calling `StageOutput.cancel()` so
   operators know why the run stopped.
2. Include actionable data inside the payload:

```python
return StageOutput.cancel(
    reason="credit_limit_exceeded",
    data={"org_id": str(ctx.snapshot.org_id), "outstanding": outstanding},
)
```

3. Attach a runbook link in the event payload or surrounding docs so
   on-call engineers can follow the remediation steps.

## Best Practices

### 1. Keep Components Focused

Each component should have a single responsibility:

```python
# Good: Focused components
def create_auth_component(): ...
def create_enrichment_component(): ...
def create_processing_component(): ...

# Bad: Monolithic component
def create_everything_component(): ...
```

### 2. Document Dependencies

Make dependencies explicit in factory functions:

```python
def create_llm_component(
    dependencies: tuple[str, ...] = ("router", "enrich"),
) -> Pipeline:
    """Create LLM component.
    
    Args:
        dependencies: Stages that must complete before LLM.
                     Default: ("router", "enrich")
    """
    return Pipeline().with_stage(
        "llm",
        LLMStage,
        StageKind.TRANSFORM,
        dependencies=dependencies,
    )
```

### 3. Use Type Hints

Add type hints for better IDE support:

```python
from stageflow import Pipeline, StageKind

def create_pipeline(
    llm_client: LLMClient,
    features: set[str] | None = None,
) -> Pipeline:
    ...
```

### 4. Test Components Independently

Test each component in isolation:

```python
def test_enrichment_component():
    pipeline = create_enrichment_component()
    graph = pipeline.build()
    
    # Verify stages
    assert "profile" in [s.name for s in graph.stage_specs]
    assert "memory" in [s.name for s in graph.stage_specs]

## Detecting & Preventing Cycles

Complex compositions increase the risk of accidental cycles. Stageflow
provides two layers of defense to keep DAGs acyclic:

1. **Lint before build**: `stageflow.cli.lint_pipeline()` surfaces
   cycles, missing dependencies, and orphans before you even create a
   `StageGraph`.
2. **Structured build errors**: The pipeline builder raises
   `CycleDetectedError` with a `ContractErrorInfo` payload (code,
   summary, fix hint, docs URL) so you can pinpoint the offending stage
   loop immediately.

```python
from stageflow import Pipeline, StageKind
from stageflow.cli.lint import lint_pipeline

pipeline = (
    Pipeline()
    .with_stage("router", RouterStage, StageKind.ROUTE)
    .with_stage("branch_a", BranchAStage, StageKind.TRANSFORM, dependencies=("router",))
    .with_stage("branch_b", BranchBStage, StageKind.TRANSFORM, dependencies=("branch_a",))
    .with_stage("router", RouterStage, StageKind.ROUTE, dependencies=("branch_b",))  # cycle
)

result = lint_pipeline(pipeline)
if not result.valid:
    raise ValueError("Dependency issues detected", result.issues)

graph = pipeline.build()  # Raises CycleDetectedError with detailed guidance
```

> **Operational tip**: Wire `stageflow cli lint` into CI and fail the
> build on any `IssueSeverity.ERROR`. Attach the emitted cycle path to
> your incident tracker so the fix is obvious to reviewers.
```

### 5. Verify Telemetry Contracts

When composing pipelines, add tests that ensure telemetry emitters and analytics exporters remain wired end-to-end:

```python
def test_streaming_component_wires_events():
    events = []

    def emitter(event_type, payload=None):
        events.append(event_type)

    queue, buffer, exporter = create_streaming_component(emitter)
    queue.maxsize = 1
    queue.put_nowait("chunk-a")
    # This dropped chunk should emit telemetry
    queue.put_nowait("chunk-b")
    queue.close()

    assert "stream.chunk_dropped" in events or "stream.producer_blocked" in events
```

## Next Steps

- [Subpipeline Runs](subpipelines.md) — Nested pipeline execution
- [Custom Interceptors](custom-interceptors.md) — Build middleware
- [Testing Strategies](testing.md) — Test your pipelines
