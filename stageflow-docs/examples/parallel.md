# Parallel Enrichment Example

This example demonstrates parallel stage execution with a fan-out/fan-in pattern.

## Overview

```
[profile_enrich] ─┐
                  ├─> [summarize]
[memory_enrich] ──┘
```

Two ENRICH stages run in parallel, then a TRANSFORM stage aggregates their outputs.

## The Stages

### ProfileEnrichStage

```python
from stageflow import StageContext, StageKind, StageOutput


class ProfileEnrichmentStage:
    """Enrich context with user profile information."""

    name = "profile_enrich"
    kind = StageKind.ENRICH

    def __init__(self, profile_service=None):
        self.profile_service = profile_service or MockProfileService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        user_id = ctx.snapshot.user_id

        if not user_id:
            return StageOutput.skip(reason="No user_id provided")

        profile = await self.profile_service.get_profile(user_id)

        return StageOutput.ok(
            profile={
                "user_id": str(profile.user_id),
                "display_name": profile.display_name,
                "preferences": profile.preferences,
                "goals": profile.goals,
            },
            enriched=True,
        )
```

### MemoryEnrichStage

```python
class MemoryEnrichStage:
    """Enrich context with conversation memory."""

    name = "memory_enrich"
    kind = StageKind.ENRICH

    def __init__(self, memory_service=None):
        self.memory_service = memory_service or MockMemoryService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        session_id = ctx.snapshot.session_id

        if not session_id:
            return StageOutput.skip(reason="No session_id provided")

        memory = await self.memory_service.get_memory(session_id)

        return StageOutput.ok(
            memory={
                "recent_topics": memory.recent_topics,
                "key_facts": memory.key_facts,
                "long_term_goals": memory.long_term_goals,
            },
            enriched=True,
        )
```

### SummarizeStage (Aggregator)

```python
class SummarizeStage:
    """Summarize combined profile + memory data."""
    """Summarize combined profile + memory data."""

    name = "summarize"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get outputs from both enrichment stages
        profile = ctx.inputs.get("profile", {})
        memory = ctx.inputs.get("memory", {})

        # Build summary
        summary_parts = []
        
        if profile.get("display_name"):
            summary_parts.append(f"User: {profile['display_name']}")
        
        if profile.get("goals"):
            summary_parts.append(f"Goals: {', '.join(profile['goals'][:2])}")
        
        if memory.get("recent_topics"):
            summary_parts.append(f"Recent topics: {', '.join(memory['recent_topics'][:3])}")
        
        if memory.get("key_facts"):
            summary_parts.append(f"Key facts: {', '.join(memory['key_facts'][:2])}")

        combined = f"User {profile['display_name']} talked about {', '.join(memory['recent_topics'])}"

        from stageflow.helpers import LLMResponse

        llm = LLMResponse(
            content=combined,
            provider="demo",
            model="summary-sim",
            input_tokens=len(profile["display_name"]) + len(memory["recent_topics"]) * 5,
            output_tokens=len(combined),
        )

        return StageOutput.ok(
            summary=combined,
            profile=profile,
            memory=memory,
            llm=llm.to_dict(),
        )
```

## The Pipeline

```python
from stageflow import Pipeline, StageKind


def create_parallel_pipeline() -> Pipeline:
    """Create a pipeline with parallel enrichment stages.
    
    DAG:
        [profile_enrich] ─┐
                          ├─> [summarize]
        [memory_enrich] ──┘
    """
    return (
        Pipeline()
        # These two stages have no dependencies on each other
        # They will run in parallel
        .with_stage(
            name="profile_enrich",
            runner=ProfileEnrichmentStage(),
            kind=StageKind.ENRICH,
        )
        .with_stage(
            name="memory_enrich",
            runner=MemoryEnrichStage(),
            kind=StageKind.ENRICH,
        )
        # This stage depends on both enrichment stages
        # It waits for both to complete before running
        .with_stage(
            name="summarize",
            runner=SummarizeStage,
            kind=StageKind.TRANSFORM,
            dependencies=("profile_enrich", "memory_enrich"),
        )
    )
```

### Key Points

1. **No Dependencies = Parallel**: `profile_enrich` and `memory_enrich` have no dependencies, so they run concurrently
2. **Fan-In**: `summarize` depends on both enrichment stages, creating a fan-in pattern
3. **Automatic Parallelism**: The framework handles concurrent execution automatically

## Complete Example

```python
import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput
from stageflow.context import ContextSnapshot


# Mock services
@dataclass
class Profile:
    user_id: UUID
    display_name: str
    preferences: dict
    goals: list


@dataclass
class Memory:
    recent_topics: list
    key_facts: list
    interaction_count: int


class MockProfileService:
    async def get_profile(self, user_id: UUID) -> Profile:
        await asyncio.sleep(0.3)  # Simulate latency
        return Profile(
            user_id=user_id,
            display_name="Alice",
            preferences={"tone": "friendly"},
            goals=["Learn Python", "Build APIs"],
        )


class MockMemoryService:
    async def get_memory(self, session_id: UUID) -> Memory:
        await asyncio.sleep(0.25)  # Simulate latency
        return Memory(
            recent_topics=["async programming", "databases"],
            key_facts=["prefers examples", "works at TechCorp"],
            interaction_count=15,
        )


# Stages
class ProfileEnrichStage:
    name = "profile_enrich"
    kind = StageKind.ENRICH

    def __init__(self):
        self.service = MockProfileService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        user_id = ctx.snapshot.user_id
        if not user_id:
            return StageOutput.skip(reason="No user_id")
        
        profile = await self.service.get_profile(user_id)
        return StageOutput.ok(profile={
            "display_name": profile.display_name,
            "goals": profile.goals,
        })


class MemoryEnrichStage:
    name = "memory_enrich"
    kind = StageKind.ENRICH

    def __init__(self):
        self.service = MockMemoryService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        session_id = ctx.snapshot.session_id
        if not session_id:
            return StageOutput.skip(reason="No session_id")
        
        memory = await self.service.get_memory(session_id)
        return StageOutput.ok(memory={
            "recent_topics": memory.recent_topics,
            "key_facts": memory.key_facts,
        })


class SummarizeStage:
    name = "summarize"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        profile = ctx.inputs.get("profile", {})
        memory = ctx.inputs.get("memory", {})
        
        summary = f"User: {profile.get('display_name', 'Unknown')}"
        if memory.get("recent_topics"):
            summary += f" | Topics: {', '.join(memory['recent_topics'])}"
        
        return StageOutput.ok(summary=summary)


async def main():
    import time
    
    # Create pipeline
    pipeline = (
        Pipeline()
        .with_stage("profile_enrich", ProfileEnrichStage(), StageKind.ENRICH)
        .with_stage("memory_enrich", MemoryEnrichStage(), StageKind.ENRICH)
        .with_stage(
            "summarize",
            SummarizeStage,
            StageKind.TRANSFORM,
            dependencies=("profile_enrich", "memory_enrich"),
        )
    )
    
    graph = pipeline.build()
    
    snapshot = ContextSnapshot(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=None,
        interaction_id=uuid4(),
        topology="parallel",
        execution_mode="default",
    )
    
    ctx = StageContext(snapshot=snapshot)
    
    # Time the execution
    start = time.time()
    results = await graph.run(ctx)
    elapsed = time.time() - start
    
    # Results
    print("Profile:", results["profile_enrich"].data.get("profile"))
    print("Memory:", results["memory_enrich"].data.get("memory"))
    print("Summary:", results["summarize"].data.get("summary"))
    print(f"\nTotal time: {elapsed:.2f}s")
    print("(Sequential would be ~0.55s, parallel is ~0.30s)")


if __name__ == "__main__":
    asyncio.run(main())
```

## Output

```
Profile: {'display_name': 'Alice', 'goals': ['Learn Python', 'Build APIs']}
Memory: {'recent_topics': ['async programming', 'databases'], 'key_facts': ['prefers examples', 'works at TechCorp']}
Summary: User: Alice | Topics: async programming, databases

Total time: 0.31s
(Sequential would be ~0.55s, parallel is ~0.30s)
```

## Parallel Execution Explained

```
Time →
0.00s  [profile_enrich] starts ─────────────────────┐
0.00s  [memory_enrich] starts  ─────────────────┐   │
0.25s  [memory_enrich] completes ───────────────┘   │
0.30s  [profile_enrich] completes ──────────────────┘
0.30s  [summarize] starts (both deps complete) ─────┐
0.30s  [summarize] completes ───────────────────────┘

Total: ~0.30s (not 0.55s if sequential)
```

## Handling Skipped Stages

When an enrichment stage skips, the aggregator still runs:

```python
        summary = " | ".join(parts) if parts else "No enrichment data available"
        
        return StageOutput.ok(summary=summary)
```

## More Complex Fan-Out/Fan-In

```python
def create_complex_parallel_pipeline() -> Pipeline:
    """
    DAG:
        [input] ─┬─> [enrich_a] ─┬─> [aggregate]
                 ├─> [enrich_b] ─┤
                 └─> [enrich_c] ─┘
    """
    return (
        Pipeline()
        .with_stage("input", InputStage, StageKind.TRANSFORM)
        .with_stage("enrich_a", EnrichAStage, StageKind.ENRICH, dependencies=("input",))
        .with_stage("enrich_b", EnrichBStage, StageKind.ENRICH, dependencies=("input",))
        .with_stage("enrich_c", EnrichCStage, StageKind.ENRICH, dependencies=("input",))
        .with_stage(
            "aggregate",
            AggregateStage,
            StageKind.TRANSFORM,
            dependencies=("enrich_a", "enrich_b", "enrich_c"),
        )
    )
```

## Next Steps

- [Chat Pipeline](chat.md) — LLM-powered conversational pipeline
- [Full Pipeline](full.md) — Complete pipeline with all features
- [Composing Pipelines](../guides/pipelines.md) — Advanced composition patterns
