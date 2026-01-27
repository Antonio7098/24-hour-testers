# Full Pipeline Example

This example demonstrates a complete pipeline with all stageflow features: guards, routing, parallel enrichment, and LLM processing.

## Overview

```
[input_guard] → [router] ─┐
                          │
[profile_enrich] ─────────┼─> [llm] → [output_guard]
                          │
[memory_enrich] ──────────┘
```

This pipeline includes:
- **GUARD stages** for input/output validation
- **ROUTE stage** for path selection
- **ENRICH stages** running in parallel
- **TRANSFORM stage** for LLM processing

## The Stages

### InputGuardStage

```python
from stageflow import StageContext, StageKind, StageOutput


class InputGuardStage:
    """Guard stage that validates input."""

    name = "input_guard"
    kind = StageKind.GUARD

    def __init__(self, guard_service=None):
        self.guard_service = guard_service or MockGuardService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""

        is_safe, reason = await self.guard_service.check_input(input_text)

        if not is_safe:
            # Cancel the pipeline - this is not an error, just a stop
            return StageOutput.cancel(
                reason=f"Input blocked: {reason}",
                data={"blocked": True, "reason": reason},
            )

        return StageOutput.ok(
            validated=True,
            text=input_text,
        )
```

### OutputGuardStage

```python
class OutputGuardStage:
    """Guard stage that validates output."""

    name = "output_guard"
    kind = StageKind.GUARD

    def __init__(self, guard_service=None):
        self.guard_service = guard_service or MockGuardService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        response = ctx.inputs.get("response", "")

        is_safe, reason = await self.guard_service.check_output(response)

        if not is_safe:
            # Replace unsafe response with safe message
            return StageOutput.ok(
                response="I apologize, but I cannot provide that response.",
                filtered=True,
                reason=reason,
            )

        return StageOutput.ok(
            response=response,
            validated=True,
        )
```

### RouterStage

```python
class RouterStage:
    """Route conversations based on intent."""

    name = "router"
    kind = StageKind.ROUTE

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.inputs.get("text", ctx.snapshot.input_text or "")

        lower_text = input_text.lower()
        
        if "help" in lower_text or "support" in lower_text:
            route = "support"
        elif "buy" in lower_text or "price" in lower_text:
            route = "sales"
        else:
            route = "general"

        return StageOutput.ok(route=route, input_text=input_text)
```

### ProfileEnrichStage

```python
class ProfileEnrichStage:
    """Enrich context with user profile."""

    name = "profile_enrich"
    kind = StageKind.ENRICH

    def __init__(self, profile_service=None):
        self.profile_service = profile_service or MockProfileService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        user_id = ctx.snapshot.user_id
        if not user_id:
            return StageOutput.skip(reason="No user_id provided")

        profile = await self.profile_service.get_profile(user_id)
        return StageOutput.ok(profile={
            "display_name": profile.display_name,
            "preferences": profile.preferences,
            "goals": profile.goals,
        })
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
        return StageOutput.ok(memory={
            "recent_topics": memory.recent_topics,
            "key_facts": memory.key_facts,
        })
```

### LLMStage

```python
class LLMStage:
    """LLM stage with enrichment support."""

    name = "llm"
    kind = StageKind.TRANSFORM

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        route = ctx.inputs.get("route", "general")
        profile = ctx.inputs.get("profile", {})
        memory = ctx.inputs.get("memory", {})
        messages = list(ctx.snapshot.messages) if ctx.snapshot.messages else []

        system_prompt = self._build_system_prompt(route, profile, memory)

        llm_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages[-10:]:
            llm_messages.append({"role": msg.role, "content": msg.content})
        if input_text:
            llm_messages.append({"role": "user", "content": input_text})

        try:
            response = await self.llm_client.chat(
                messages=llm_messages,
                model="llama-3.1-8b-instant",
                temperature=0.7,
                max_tokens=1024,
            )

            from stageflow.helpers import LLMResponse

            llm = LLMResponse(
                content=response,
                provider="mock",
                model="llama-3.1-8b-instant",
                input_tokens=sum(len(m["content"]) for m in llm_messages),
                output_tokens=len(response),
            )
            return StageOutput.ok(response=llm.content, route=route, llm=llm.to_dict())
        except Exception as e:
            return StageOutput.fail(error=f"LLM call failed: {e}")

    def _build_system_prompt(self, route: str, profile: dict, memory: dict) -> str:
        parts = ["You are a helpful AI assistant."]
        
        if profile.get("display_name"):
            parts.append(f"You're talking to {profile['display_name']}.")
        if profile.get("goals"):
            parts.append(f"Their goals: {', '.join(profile['goals'][:3])}")
        if memory.get("recent_topics"):
            parts.append(f"Recent topics: {', '.join(memory['recent_topics'][:3])}")
        
        return " ".join(parts)
```

## The Pipeline

```python
from stageflow import Pipeline, StageKind


def create_full_pipeline(
    llm_client=None,
    guard_service=None,
    profile_service=None,
    memory_service=None,
) -> Pipeline:
    """Create a full-featured pipeline with all stage types.
    
    DAG:
        [input_guard] → [router] ─┐
                                  │
        [profile_enrich] ─────────┼─> [llm] → [output_guard]
                                  │
        [memory_enrich] ──────────┘
    
    Features:
    - Guard stages (input/output validation)
    - Route stages (path selection)
    - Enrich stages (parallel context enrichment)
    - Transform stages (LLM processing)
    - Dependencies (linear and fan-in)
    """
    return (
        Pipeline()
        # Input guard runs first
        .with_stage(
            name="input_guard",
            runner=InputGuardStage(guard_service),
            kind=StageKind.GUARD,
        )
        # Router decides path after guard
        .with_stage(
            name="router",
            runner=RouterStage,
            kind=StageKind.ROUTE,
            dependencies=("input_guard",),
        )
        # Parallel enrichment stages (no deps on each other)
        .with_stage(
            name="profile_enrich",
            runner=ProfileEnrichStage(profile_service),
            kind=StageKind.ENRICH,
        )
        .with_stage(
            name="memory_enrich",
            runner=MemoryEnrichStage(memory_service),
            kind=StageKind.ENRICH,
        )
        # LLM waits for routing and enrichment
        .with_stage(
            name="llm",
            runner=LLMStage(llm_client),
            kind=StageKind.TRANSFORM,
            dependencies=("router", "profile_enrich", "memory_enrich"),
        )
        # Output guard validates LLM response
        .with_stage(
            name="output_guard",
            runner=OutputGuardStage(guard_service),
            kind=StageKind.GUARD,
            dependencies=("llm",),
        )
    )
```

## Complete Example

```python
import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput, PipelineTimer
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.pipeline.dag import UnifiedPipelineCancelled
from stageflow.stages import StageInputs


# Mock Services
@dataclass
class Profile:
    display_name: str
    preferences: dict
    goals: list


@dataclass
class Memory:
    recent_topics: list
    key_facts: list


class MockGuardService:
    BLOCKED_WORDS = ["spam", "abuse", "hack"]
    
    async def check_input(self, text: str) -> tuple[bool, str]:
        await asyncio.sleep(0.05)
        for word in self.BLOCKED_WORDS:
            if word in text.lower():
                return False, f"Contains blocked word: {word}"
        return True, ""
    
    async def check_output(self, text: str) -> tuple[bool, str]:
        await asyncio.sleep(0.05)
        return True, ""


class MockProfileService:
    async def get_profile(self, user_id: UUID) -> Profile:
        await asyncio.sleep(0.1)
        return Profile(
            display_name="Alice",
            preferences={"tone": "friendly"},
            goals=["Learn Python", "Build APIs"],
        )


class MockMemoryService:
    async def get_memory(self, session_id: UUID) -> Memory:
        await asyncio.sleep(0.1)
        return Memory(
            recent_topics=["async programming", "databases"],
            key_facts=["prefers examples"],
        )


class MockLLMClient:
    async def chat(self, messages, model, temperature, max_tokens):
        await asyncio.sleep(0.2)
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"I understand you said: '{user_msg}'. How can I help?"


# Stages (simplified versions)
class InputGuardStage:
    name = "input_guard"
    kind = StageKind.GUARD
    
    def __init__(self, service):
        self.service = service or MockGuardService()
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.snapshot.input_text or ""
        is_safe, reason = await self.service.check_input(text)
        if not is_safe:
            return StageOutput.cancel(reason=f"Blocked: {reason}")
        return StageOutput.ok(validated=True, text=text)


class RouterStage:
    name = "router"
    kind = StageKind.ROUTE
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.snapshot.input_text or ""
        route = "support" if "help" in text.lower() else "general"
        return StageOutput.ok(route=route)


class ProfileEnrichStage:
    name = "profile_enrich"
    kind = StageKind.ENRICH
    
    def __init__(self, service):
        self.service = service or MockProfileService()
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        if not ctx.snapshot.user_id:
            return StageOutput.skip(reason="No user_id")
        profile = await self.service.get_profile(ctx.snapshot.user_id)
        return StageOutput.ok(profile={"display_name": profile.display_name, "goals": profile.goals})


class MemoryEnrichStage:
    name = "memory_enrich"
    kind = StageKind.ENRICH
    
    def __init__(self, service):
        self.service = service or MockMemoryService()
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        if not ctx.snapshot.session_id:
            return StageOutput.skip(reason="No session_id")
        memory = await self.service.get_memory(ctx.snapshot.session_id)
        return StageOutput.ok(memory={"recent_topics": memory.recent_topics})


class LLMStage:
    name = "llm"
    kind = StageKind.TRANSFORM
    
    def __init__(self, client):
        self.client = client or MockLLMClient()
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.snapshot.input_text or ""
        messages = [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": text}]
        response = await self.client.chat(messages, "model", 0.7, 1024)
        return StageOutput.ok(response=response)


class OutputGuardStage:
    name = "output_guard"
    kind = StageKind.GUARD
    
    def __init__(self, service):
        self.service = service or MockGuardService()
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        response = ctx.inputs.get("response", "")
        return StageOutput.ok(response=response, validated=True)


async def main():
    # Create services
    guard = MockGuardService()
    profile = MockProfileService()
    memory = MockMemoryService()
    llm = MockLLMClient()
    
    # Create pipeline
    pipeline = (
        Pipeline()
        .with_stage("input_guard", InputGuardStage(guard), StageKind.GUARD)
        .with_stage("router", RouterStage, StageKind.ROUTE, dependencies=("input_guard",))
        .with_stage("profile_enrich", ProfileEnrichStage(profile), StageKind.ENRICH)
        .with_stage("memory_enrich", MemoryEnrichStage(memory), StageKind.ENRICH)
        .with_stage("llm", LLMStage(llm), StageKind.TRANSFORM, dependencies=("router", "profile_enrich", "memory_enrich"))
        .with_stage("output_guard", OutputGuardStage(guard), StageKind.GUARD, dependencies=("llm",))
    )
    
    graph = pipeline.build()
    
    # Test 1: Normal input
    print("=== Test 1: Normal Input ===")
    snapshot = ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        ),
        topology="full",
        execution_mode="default",
        input_text="Hello, I need help with Python!",
    )
    
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="full_pipeline_entry",
        timer=PipelineTimer(),
    )
    results = await graph.run(ctx)
    
    print(f"Route: {results['router'].data.get('route')}")
    print(f"Profile: {results['profile_enrich'].data.get('profile')}")
    print(f"Response: {results['output_guard'].data.get('response')}")
    print()
    
    # Test 2: Blocked input
    print("=== Test 2: Blocked Input ===")
    snapshot2 = ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        ),
        topology="full",
        execution_mode="default",
        input_text="How do I hack into systems?",
    )
    
    ctx2 = StageContext(
        snapshot=snapshot2,
        inputs=StageInputs(snapshot=snapshot2),
        stage_name="full_pipeline_entry",
        timer=PipelineTimer(),
    )
    
    try:
        results2 = await graph.run(ctx2)
        print("Pipeline completed normally")
    except UnifiedPipelineCancelled as e:
        print(f"Pipeline cancelled by '{e.stage}': {e.reason}")
        print(f"Completed stages: {list(e.results.keys())}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Output

```
=== Test 1: Normal Input ===
Route: support
Profile: {'display_name': 'Alice', 'goals': ['Learn Python', 'Build APIs']}
Response: I understand you said: 'Hello, I need help with Python!'. How can I help?

=== Test 2: Blocked Input ===
Pipeline cancelled by 'input_guard': Blocked: Contains blocked word: hack
Completed stages: ['input_guard']
```

## Execution Flow

### Normal Input

```
Time →
0.00s  [input_guard] starts
0.05s  [input_guard] completes (validated)
0.05s  [router] starts
0.05s  [profile_enrich] starts (parallel)
0.05s  [memory_enrich] starts (parallel)
0.05s  [router] completes
0.15s  [profile_enrich] completes
0.15s  [memory_enrich] completes
0.15s  [llm] starts (all deps complete)
0.35s  [llm] completes
0.35s  [output_guard] starts
0.40s  [output_guard] completes

Total: ~0.40s
```

### Blocked Input

```
Time →
0.00s  [input_guard] starts
0.05s  [input_guard] returns CANCEL
0.05s  Pipeline stops, no further stages run

Total: ~0.05s
```

## Next Steps

- [Agent with Tools](agent-tools.md) — Add tool execution
- [Interceptors](../guides/interceptors.md) — Add middleware
- [Observability](../guides/observability.md) — Monitor the pipeline
