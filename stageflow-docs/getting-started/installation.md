# Installation

## Requirements

Stageflow requires:
- **Python 3.11** or higher
- An asyncio-compatible runtime

## Installing from PyPI

```bash
pip install stageflow-core
```

## Installing from Source

Clone the repository and install in development mode:

```bash
git clone https://github.com/your-org/stageflow.git
cd stageflow
pip install -e .
```

## Optional Dependencies

Stageflow has optional dependencies for specific features:

```bash
# For development and testing
pip install stageflow-core[dev]

# For documentation generation
pip install stageflow-core[docs]
```

## Verifying Installation

Verify your installation by running:

```python
import stageflow
print(stageflow.__all__)
```

You should see a list of exported types including `Pipeline`, `Stage`, `StageOutput`, etc.

Stageflow also exports helper modules—confirm the new provider response dataclasses are available:

```python
from stageflow.helpers import LLMResponse, STTResponse, TTSResponse

print(LLMResponse(model="mock", provider="demo", content="hi"))
```

If this import works, your environment is ready for deterministic provider metadata handling in later guides.

## Quick Verification

Run this minimal example to verify everything works:

```python
import asyncio
from stageflow import Pipeline, StageKind, StageOutput, StageContext, PipelineTimer
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.stages import StageInputs

class HelloStage:
    name = "hello"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(message="Hello, Stageflow!")

async def main():
    # Create a minimal context snapshot with RunIdentity
    snapshot = ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=None,
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
        ),
        topology=None,
        execution_mode=None,
    )
    
    # Build the pipeline
    pipeline = Pipeline().with_stage("hello", HelloStage, StageKind.TRANSFORM)
    graph = pipeline.build()
    
    # Create context with required parameters
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )
    
    results = await graph.run(ctx)
    
    print(results["hello"].data)  # {'message': 'Hello, Stageflow!'}

    # Optional: emit quick telemetry from the queue helpers
    from stageflow.helpers import ChunkQueue

    q = ChunkQueue(event_emitter=lambda event, data: print(event, data))
    await q.put("warmup")
    await q.close()

asyncio.run(main())
```

## Next Steps

- Continue to the [Quick Start](quickstart.md) guide to build your first real pipeline
- Read about [Core Concepts](concepts.md) to understand the framework architecture
- Jump to [Observability](../guides/observability.md) once you're ready to wire telemetry, streaming events, and analytics exporters
