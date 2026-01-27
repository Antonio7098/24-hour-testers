# Stageflow Documentation

**Stageflow** is a Python framework for building observable, composable pipeline architectures with parallel execution, cancellation support, and middleware interceptors.

## What is Stageflow?

Stageflow provides a **DAG-based execution substrate** for building complex data processing and AI agent pipelines. It separates the concerns of *orchestration* (how stages run) from *business logic* (what stages do), enabling you to build maintainable, testable, and observable systems.

```python
from stageflow import Pipeline, StageKind, StageOutput

class GreetStage:
    name = "greet"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx):
        name = ctx.snapshot.input_text or "World"
        return StageOutput.ok(message=f"Hello, {name}!")

# Build and run the pipeline
pipeline = Pipeline().with_stage("greet", GreetStage, StageKind.TRANSFORM)
graph = pipeline.build()
results = await graph.run(ctx)
```

## Key Features

- **DAG-Based Execution** — Stages run as soon as their dependencies resolve, enabling maximum parallelism
- **Type-Safe Pipelines** — Define pipelines in Python code with full IDE support and compile-time safety
- **Composable Architecture** — Combine pipelines, share stages, and build complex workflows from simple parts
- **Built-in Observability** — Structured logging, streaming telemetry events, analytics buffering with overflow callbacks, and distributed tracing out of the box
- **Interceptor Middleware** — Add cross-cutting concerns (auth, timeouts, circuit breakers) without modifying stages
- **Cancellation Support** — Graceful pipeline cancellation with structured cleanup and resource management
- **Multi-Tenant Isolation** — Built-in tenant validation, isolation tracking, and tenant-aware logging
- **Event Backpressure** — Bounded event queues with backpressure handling to prevent memory exhaustion
- **Tool Execution System** — First-class support for agent tools with undo, approval, and behavior gating

## Documentation Structure

The docs are organized into the following sections:

- [Getting Started](getting-started/) - installation, quickstart, concepts
- [Guides](guides/) - stages, pipelines, dependencies, governance, observability, release workflow, tools, approval
- [Examples](examples/) - simple pipeline, transform chain, parallel enrichment, chat pipeline, full pipeline, agent with tools
- [API Reference](api/) - core types, pipeline, context, interceptors, events, protocols, observability, extensions
- [Advanced Topics](advanced/) - pipeline composition, subpipeline runs, custom interceptors, error handling, testing strategies, extensions

> **New in Stageflow 0.9.1**
> 
> - **StageContext Integration**: Added record_stage_event() method for pipeline lifecycle tracking
> - **Documentation Fixes**: Updated installation guide with correct ContextSnapshot API
> - **Integration Tests**: Comprehensive tests for v0.9.0 feature integration
> - **Failure Tolerance**: Continue-on-failure mode, conditional dependencies, and burst load backpressure for DAG resilience
> - **Pipeline Builder Helpers**: Ergonomic utilities for constructing complex DAGs (linear chains, parallel stages, fan-out/fan-in, conditional branches)
> - **ENRICH Context Utilities**: Token tracking, truncation event emission, version metadata, and conflict detection for context enrichment
> - **Comprehensive Documentation**: 16 new guides covering retry patterns, saga patterns, checkpointing, sandboxing, multimodal fusion, timestamps, chunking, security, A/B testing, and routing patterns

## Links

- [GitHub Repository](https://github.com/yourorg/stageflow)
- [Issue Tracker](https://github.com/yourorg/stageflow/issues)
- [**Composing Pipelines**](guides/pipelines.md) — Build complex DAGs from simple stages
- [**Context & Data Flow**](guides/context.md) — Pass data between stages
- [**Interceptors**](guides/interceptors.md) — Add middleware for cross-cutting concerns
- [**Tools & Agents**](guides/tools.md) — Build agent capabilities with tools and parse LLM tool calls safely
- [**Observability**](guides/observability.md) — Monitor and debug your pipelines with telemetry streams and analytics exporters

## Getting Started
- [**Installation**](getting-started/installation.md) — Install stageflow and set up your environment
- [**Quick Start**](getting-started/quickstart.md) — Build your first pipeline in 5 minutes
- [**Core Concepts**](getting-started/concepts.md) — Understand the fundamental ideas

### Guides
- [**Building Stages**](guides/stages.md) — Create custom stages for your pipelines
- [**Composing Pipelines**](guides/pipelines.md) — Build complex DAGs from simple stages
- [**Dependency Declaration**](guides/dependencies.md) — Declare and manage stage dependencies
- [**Context & Data Flow**](guides/context.md) — Pass data between stages
- [**Interceptors**](guides/interceptors.md) — Add middleware for cross-cutting concerns
- [**Tools & Agents**](guides/tools.md) — Build agent capabilities with tools and parse LLM tool calls safely
- [**Tools & Approval Workflows**](guides/tools-approval.md) — Implement HITL approval flows for tools
- [**Observability**](guides/observability.md) — Monitor and debug your pipelines with telemetry streams and analytics exporters
- [**Authentication**](guides/authentication.md) — Secure your pipelines with auth interceptors
- [**Governance & Security**](guides/governance.md) — Multi-tenant isolation, guardrails, and audit patterns
- [**Voice & Audio**](guides/voice-audio.md) — Build voice pipelines with STT/TTS and streaming
- [**Releasing**](guides/releasing.md) — Step-by-step instructions for cutting a new Stageflow release

### Examples
- [**Simple Pipeline**](examples/simple.md) — Single-stage echo pipeline
- [**Transform Chain**](examples/transform-chain.md) — Sequential data transformations
- [**Parallel Enrichment**](examples/parallel.md) — Fan-out/fan-in patterns
- [**Chat Pipeline**](examples/chat.md) — LLM-powered conversational pipeline
- [**Full Pipeline**](examples/full.md) — Complete pipeline with all features
- [**Agent with Tools**](examples/agent-tools.md) — Agent stage with tool execution

### API Reference
- [**Core Types**](api/core.md) — Stage, StageOutput, StageContext, StageKind
- [**Pipeline**](api/pipeline.md) — Pipeline builder and StageGraph
- [**Context**](api/context.md) — ContextSnapshot, ContextBag, StageInputs, StagePorts
- [**StageInputs**](api/inputs.md) — Immutable access to prior stage outputs with validation
- [**Context Sub-modules**](api/context-submodules.md) — ContextBag, Conversation, Enrichments, Extensions
- [**Interceptors**](api/interceptors.md) — BaseInterceptor and built-in interceptors
- [**Tools**](api/tools.md) — Tool definitions, registry, and executor
- [**Events**](api/events.md) — EventSink and event types
- [**Protocols**](api/protocols.md) — ExecutionContext, RunStore, ConfigProvider, CorrelationIds
- [**Observability**](api/observability.md) — Logging protocols and utilities
- [**Wide Events**](api/wide-events.md) — Pipeline-level and stage-level event emission
- [**Auth**](api/auth.md) — AuthContext, OrgContext, and auth interceptors
- [**Helper Modules**](api/helpers.md) — Memory, Guardrails, Streaming, Analytics, Mocks
- [**CLI**](api/cli.md) — Dependency linting and pipeline validation tools
- [**Projector**](api/projector.md) — WebSocket projection services
- [**Testing**](api/testing.md) — Testing utilities and helpers

### Advanced Topics
- [**Pipeline Composition**](advanced/composition.md) — Merging and extending pipelines
- [**Subpipeline Runs**](advanced/subpipelines.md) — Nested pipeline execution
- [**Custom Interceptors**](advanced/custom-interceptors.md) — Build your own middleware
- [**Idempotency Patterns**](advanced/idempotency.md) — Enforce duplicate suppression for WORK stages
- [**Error Handling**](advanced/errors.md) — Error taxonomy and recovery strategies
- [**Testing Strategies**](advanced/testing.md) — Unit, integration, and contract testing
- [**Extensions**](advanced/extensions.md) — Add application-specific data to contexts

## Root Exports Index

The following symbols are exported from `stageflow` and can be imported directly:

| Symbol | Category | Documentation |
|--------|----------|---------------|
| `Stage`, `StageKind`, `StageStatus`, `StageOutput` | Core | [Core Types](api/core.md) |
| `StageContext`, `StageArtifact`, `StageEvent` | Core | [Core Types](api/core.md) |
| `PipelineTimer`, `create_stage_context` | Core | [Core Types](api/core.md) |
| `Pipeline`, `UnifiedStageSpec` | Pipeline | [Pipeline](api/pipeline.md) |
| `StageGraph`, `StageSpec`, `StageExecutionError` | Pipeline | [Pipeline](api/pipeline.md) |
| `PipelineRegistry`, `pipeline_registry` | Pipeline | [Pipeline](api/pipeline.md) |
| `PipelineContext`, `StageResult`, `StageError` | Context | [Context](api/context.md) |
| `extract_service` | Context | [Context](api/context.md) |
| `BaseInterceptor`, `InterceptorResult`, `InterceptorContext` | Interceptors | [Interceptors](api/interceptors.md) |
| `ErrorAction`, `get_default_interceptors`, `run_with_interceptors` | Interceptors | [Interceptors](api/interceptors.md) |
| `TimeoutInterceptor`, `CircuitBreakerInterceptor` | Interceptors | [Interceptors](api/interceptors.md) |
| `LoggingInterceptor`, `MetricsInterceptor`, `ChildTrackerMetricsInterceptor`, `TracingInterceptor` | Interceptors | [Interceptors](api/interceptors.md) |
| `EventSink`, `NoOpEventSink`, `LoggingEventSink` | Events | [Events](api/events.md) |
| `get_event_sink`, `set_event_sink`, `clear_event_sink` | Events | [Events](api/events.md) |
| `RunStore`, `ConfigProvider`, `CorrelationIds` | Protocols | [Protocols](api/protocols.md) |
| `CircuitBreaker`, `CircuitBreakerOpenError` | Observability | [Observability](api/observability.md) |
| `PipelineRunLogger`, `ProviderCallLogger` | Observability | [Observability](api/observability.md) |
| `summarize_pipeline_error`, `get_circuit_breaker` | Observability | [Observability](api/observability.md) |
| `ExtensionRegistry`, `ExtensionHelper`, `TypedExtension` | Extensions | [Extensions](advanced/extensions.md) |

**Context module** (`from stageflow.context import ...`):

| Symbol | Documentation |
|--------|---------------|
| `ContextSnapshot`, `ContextBag`, `DataConflictError` | [Context](api/context.md) |
| `Message`, `RoutingDecision` | [Context](api/context.md) |
| `ProfileEnrichment`, `MemoryEnrichment`, `DocumentEnrichment` | [Context](api/context.md) |

**Stages module** (`from stageflow.stages.inputs import ...`):

| Symbol | Documentation |
|--------|---------------|
| `StageInputs`, `create_stage_inputs` | [Context](api/context.md#stageinputs) |
| `StagePorts`, `create_stage_ports` | [Context](api/context.md#stageports) |

**Subpipeline module** (`from stageflow.pipeline.subpipeline import ...`):

| Symbol | Documentation |
|--------|---------------|
| `SubpipelineSpawner`, `SubpipelineResult` | [Subpipelines](advanced/subpipelines.md) |
| `ChildRunTracker`, `get_child_tracker` | [Subpipelines](advanced/subpipelines.md) |
| `PipelineSpawnedChildEvent`, `PipelineChildCompletedEvent` | [Subpipelines](advanced/subpipelines.md) |
| `PipelineChildFailedEvent`, `PipelineCanceledEvent` | [Subpipelines](advanced/subpipelines.md) |

## Philosophy

Stageflow is built on several core principles:

1. **Containers vs. Payloads** — Stages own orchestration (timeouts, retries, telemetry). Business logic lives in the payloads (agents, tools, enrichers).

2. **Separation of Concerns** — Topology (DAG structure), Configuration (provider/model wiring), and Behavior (runtime hints) are kept separate.

3. **Observability is Reality** — If it's not logged, traced, and replayable, it didn't happen.

4. **Parallel by Default** — Stages run as soon as dependencies resolve. The framework handles concurrency.

5. **Immutable Data Flow** — Context snapshots are frozen. Stages read inputs and produce outputs without side effects on shared state.

## Requirements

- Python 3.11+
- asyncio-based runtime

## License

MIT License
