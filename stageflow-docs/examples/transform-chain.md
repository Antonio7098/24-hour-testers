# Transform Chain Example

This example demonstrates a linear chain of transform stages, where each stage processes the output of the previous one.

## Overview

```
[uppercase] → [reverse] → [summarize]
```

Three TRANSFORM stages in sequence, each modifying the text.

## The Stages

### UppercaseStage

```python
import asyncio
from stageflow import StageContext, StageKind, StageOutput


class UppercaseStage:
    """Transform text to uppercase."""

    name = "uppercase"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.15)

        # Get input from snapshot (first stage)
        text = ctx.snapshot.input_text or ""

        result = text.upper()

        from stageflow.helpers import LLMResponse

        llm = LLMResponse(
            content=result,
            provider="demo",
            model="uppercase-sim",
            input_tokens=len(text),
            output_tokens=len(result),
        )
        return StageOutput.ok(text=result, transformed=True, llm=llm.to_dict())
```

### ReverseStage

```python
class ReverseStage:
    """Reverse the text."""

    name = "reverse"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.15)

        text = ctx.inputs.get("text") or ctx.snapshot.input_text or ""

        result = text[::-1]

        from stageflow.helpers import LLMResponse

        llm = LLMResponse(
            content=result,
            provider="demo",
            model="reverse-sim",
            input_tokens=len(text),
            output_tokens=len(result),
        )
        return StageOutput.ok(text=result, reversed=True, llm=llm.to_dict())
```

### SummarizeStage

```python
class SummarizeStage:
    """Summarize/truncate text (mock summarization)."""

    name = "summarize"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.2)

        text = ctx.inputs.get("text") or ctx.snapshot.input_text or ""

        # Simple truncation as mock summarization
        if len(text) > 100:
            summary = text[:100] + "..."
        else:
            summary = text

        from stageflow.helpers import LLMResponse

        llm = LLMResponse(
            content=summary,
            provider="demo",
            model="summarize-sim",
            input_tokens=len(text),
            output_tokens=len(summary),
        )

        return StageOutput.ok(
            text=summary,
            summary=summary,
            original_length=len(text),
            summarized=True,
            llm=llm.to_dict(),
        )
```

## The Pipeline

```python
from stageflow import Pipeline, StageKind


def create_transform_pipeline() -> Pipeline:
    """Create a linear chain of transform stages.
    
    DAG:
        [uppercase] → [reverse] → [summarize]
    """
    return (
        Pipeline()
        .with_stage(
            name="uppercase",
            runner=UppercaseStage,
            kind=StageKind.TRANSFORM,
        )
        .with_stage(
            name="reverse",
            runner=ReverseStage,
            kind=StageKind.TRANSFORM,
            dependencies=("uppercase",),  # Waits for uppercase
        )
        .with_stage(
            name="summarize",
            runner=SummarizeStage,
            kind=StageKind.TRANSFORM,
            dependencies=("reverse",),  # Waits for reverse
        )
    )
```

### Key Points

1. **Dependencies**: Each stage lists its predecessor in `dependencies`
2. **Sequential Execution**: Stages run one after another
3. **Data Flow**: Each stage reads `text` from the previous stage's output

## Complete Example

```python
import asyncio
from uuid import uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput, PipelineTimer
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.stages import StageInputs


class UppercaseStage:
    name = "uppercase"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        from stageflow.helpers import LLMResponse

        text = ctx.snapshot.input_text or ""
        upper = text.upper()
        llm = LLMResponse(
            content=upper,
            provider="demo",
            model="uppercase-sim",
            input_tokens=len(text),
            output_tokens=len(upper),
        )
        return StageOutput.ok(text=upper, llm=llm.to_dict())


class ReverseStage:
    name = "reverse"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        from stageflow.helpers import LLMResponse

        text = ctx.inputs.get("text", "")
        reversed_text = text[::-1]
        llm = LLMResponse(
            content=reversed_text,
            provider="demo",
            model="reverse-sim",
            input_tokens=len(text),
            output_tokens=len(reversed_text),
        )
        return StageOutput.ok(text=reversed_text, llm=llm.to_dict())


class SummarizeStage:
    name = "summarize"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.inputs.get("text", "")
        from stageflow.helpers import LLMResponse

        summary = text[:50] + "..." if len(text) > 50 else text
        llm = LLMResponse(
            content=summary,
            provider="demo",
            model="summarize-sim",
            input_tokens=len(text),
            output_tokens=len(summary),
        )
        return StageOutput.ok(text=summary, original_length=len(text), llm=llm.to_dict())


async def main():
    # Create the pipeline
    pipeline = (
        Pipeline()
        .with_stage("uppercase", UppercaseStage, StageKind.TRANSFORM)
        .with_stage("reverse", ReverseStage, StageKind.TRANSFORM, dependencies=("uppercase",))
        .with_stage("summarize", SummarizeStage, StageKind.TRANSFORM, dependencies=("reverse",))
    )
    
    # Build and create context
    graph = pipeline.build()
    
    snapshot = ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        ),
        topology="transform_chain",
        execution_mode="default",
        input_text="Hello, this is a test of the transform chain!",
    )
    
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )
    
    # Run
    results = await graph.run(ctx)
    
    # Show transformation at each step
    print("Input:", snapshot.input_text)
    print()
    print("After uppercase:", results["uppercase"].data["text"])
    print("After reverse:", results["reverse"].data["text"])
    print("After summarize:", results["summarize"].data["text"])


if __name__ == "__main__":
    asyncio.run(main())
```

## Output

```
Input: Hello, this is a test of the transform chain!

After uppercase: HELLO, THIS IS A TEST OF THE TRANSFORM CHAIN!
After reverse: !NIAHC MROFSNART EHT FO TSET A SI SIHT ,OLLEH
After summarize: !NIAHC MROFSNART EHT FO TSET A SI SIHT ,OLLEH
```

## Data Flow Explained

```
┌─────────────────────────────────────────────────────────────┐
│ ContextSnapshot                                             │
│   input_text: "Hello, this is a test..."                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ UppercaseStage                                              │
│   reads: ctx.snapshot.input_text                            │
│   outputs: {text: "HELLO, THIS IS A TEST..."}               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ ReverseStage                                                │
│   reads: inputs.get("text") → "HELLO, THIS IS A TEST..."    │
│   outputs: {text: "...TSET A SI SIHT ,OLLEH"}               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ SummarizeStage                                              │
│   reads: inputs.get("text") → "...TSET A SI SIHT ,OLLEH"    │
│   outputs: {text: "...TSET A SI SIHT ,OLLEH", ...}          │
└─────────────────────────────────────────────────────────────┘
```

## Accessing Specific Stage Outputs

```python
# Get output from a specific stage
# inside a stage execution
text = ctx.inputs.get("text")
uppercase_text = ctx.inputs.get_from("uppercase", "text")
```

## Conditional Chains

You can make stages conditional:

```python
pipeline = (
    Pipeline()
    .with_stage("uppercase", UppercaseStage, StageKind.TRANSFORM)
    .with_stage(
        "reverse",
        ReverseStage,
        StageKind.TRANSFORM,
        dependencies=("uppercase",),
        conditional=True,  # May be skipped
    )
    .with_stage("summarize", SummarizeStage, StageKind.TRANSFORM, dependencies=("reverse",))
)

# Add streaming telemetry emitters if this pipeline processes audio/text concurrently
queue = ChunkQueue(event_emitter=lambda event, attrs: logger.info("telemetry", extra=attrs))
```

A conditional stage can return `StageOutput.skip()` to be skipped:

```python
class ConditionalReverseStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.inputs.get("text", "")
        
        # Skip if text is too short
        if len(text) < 10:
            return StageOutput.skip(reason="Text too short to reverse")
        
        return StageOutput.ok(text=text[::-1])
```

## Next Steps

- [Parallel Enrichment](parallel.md) — Stages running concurrently
- [Full Pipeline](full.md) — Complete pipeline with all features
- [Context & Data Flow](../guides/context.md) — Deep dive into data passing
