# Chat Pipeline Example

This example demonstrates an LLM-powered conversational pipeline with real API integration.

## Overview

```
[router] → [llm]
```

A ROUTE stage determines the conversation path, then a TRANSFORM stage calls an LLM for response generation.

## The Stages

### RouterStage

```python
from stageflow import StageContext, StageKind, StageOutput


class RouterStage:
    """Route conversations based on intent."""

    name = "router"
    kind = StageKind.ROUTE

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""

        # Simple keyword-based routing
        lower_text = input_text.lower()
        
        if any(word in lower_text for word in ["help", "support", "issue"]):
            route = "support"
            confidence = 0.9
        elif any(word in lower_text for word in ["buy", "purchase", "price"]):
            route = "sales"
            confidence = 0.85
        else:
            route = "general"
            confidence = 0.7

        return StageOutput.ok(
            route=route,
            confidence=confidence,
            input_text=input_text,
        )
```

### LLMStage

```python
class LLMStage:
    """Stage that calls an LLM for response generation."""

    name = "llm"
    kind = StageKind.TRANSFORM

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        route = ctx.inputs.get("route", "general")
        messages = list(ctx.snapshot.messages) if ctx.snapshot.messages else []

        # Build system prompt based on route
        system_prompt = self._get_system_prompt(route)

        # Prepare messages for LLM
        llm_messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history
        for msg in messages[-10:]:  # Last 10 messages
            llm_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        # Add current input
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
                provider="mock" if isinstance(self.llm_client, MockLLMClient) else "groq",
                model="llama-3.1-8b-instant",
                input_tokens=sum(len(m["content"]) for m in llm_messages),
                output_tokens=len(response),
            )
            
            return StageOutput.ok(
                response=llm.content,
                route=route,
                model="llm-content",
                llm=llm.to_dict(),
            )
        except Exception as e:
            return StageOutput.fail(
                error=f"LLM call failed: {str(e)}",
                data={"error_type": type(e).__name__},
            )

    def _get_system_prompt(self, route: str) -> str:
        prompts = {
            "support": "You are a helpful support agent. Be empathetic and solution-focused.",
            "sales": "You are a friendly sales assistant. Be helpful but not pushy.",
            "general": "You are a helpful AI assistant. Be friendly and informative.",
        }
        return prompts.get(route, prompts["general"])
```

## The Pipeline

```python
from stageflow import Pipeline, StageKind


def create_chat_pipeline(llm_client=None) -> Pipeline:
    """Create an LLM chat pipeline.
    
    DAG:
        [router] → [llm]
    """
    return (
        Pipeline()
        .with_stage(
            name="router",
            runner=RouterStage,
            kind=StageKind.ROUTE,
        )
        .with_stage(
            name="llm",
            runner=LLMStage(llm_client=llm_client),
            kind=StageKind.TRANSFORM,
            dependencies=("router",),
        )
    )
```

## Complete Example with Mock LLM

```python
import asyncio
from uuid import uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput, PipelineTimer
from stageflow.context import ContextSnapshot, Message, RunIdentity
from stageflow.stages import StageInputs


class MockLLMClient:
    """Mock LLM client for testing."""
    
    async def chat(self, messages, model, temperature, max_tokens):
        # Simulate API latency
        await asyncio.sleep(0.5)
        
        # Get the last user message
        user_message = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_message = msg["content"]
                break
        
        # Generate mock response
        return f"I received your message: '{user_message}'. How can I help you further?"


class RouterStage:
    name = "router"
    kind = StageKind.ROUTE

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        lower_text = input_text.lower()
        
        if "help" in lower_text:
            route = "support"
        elif "buy" in lower_text:
            route = "sales"
        else:
            route = "general"
        
        return StageOutput.ok(route=route)


class LLMStage:
    name = "llm"
    kind = StageKind.TRANSFORM

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        route = ctx.inputs.get("route", "general")
        
        system_prompts = {
            "support": "You are a support agent.",
            "sales": "You are a sales assistant.",
            "general": "You are a helpful assistant.",
        }
        
        messages = [
            {"role": "system", "content": system_prompts.get(route, system_prompts["general"])},
            {"role": "user", "content": input_text},
        ]
        
        response = await self.llm_client.chat(
            messages=messages,
            model="mock-model",
            temperature=0.7,
            max_tokens=1024,
        )

        from stageflow.helpers import LLMResponse

        llm = LLMResponse(
            content=response,
            provider="mock",
            model="mock-model",
            input_tokens=sum(len(m["content"]) for m in messages),
            output_tokens=len(response),
        )
        
        return StageOutput.ok(response=llm.content, route=route, llm=llm.to_dict())


async def main():
    # Create pipeline with mock client
    llm_client = MockLLMClient()
    
    pipeline = (
        Pipeline()
        .with_stage("router", RouterStage, StageKind.ROUTE)
        .with_stage("llm", LLMStage(llm_client), StageKind.TRANSFORM, dependencies=("router",))
    )
    
    graph = pipeline.build()
    
    # Test different inputs
    test_inputs = [
        "Hello, how are you?",
        "I need help with my account",
        "I want to buy a subscription",
    ]
    
    for input_text in test_inputs:
        snapshot = ContextSnapshot(
            run_id=RunIdentity(
                pipeline_run_id=uuid4(),
                request_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                org_id=None,
                interaction_id=uuid4(),
            ),
            topology="chat",
            execution_mode="default",
            input_text=input_text,
        )
        
        ctx = StageContext(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="chat_entry",
            timer=PipelineTimer(),
        )
        results = await graph.run(ctx)
        
        print(f"Input: {input_text}")
        print(f"Route: {results['router'].data['route']}")
        print(f"Response: {results['llm'].data['response']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
```

## Output

```
Input: Hello, how are you?
Route: general
Response: I received your message: 'Hello, how are you?'. How can I help you further?

Input: I need help with my account
Route: support
Response: I received your message: 'I need help with my account'. How can I help you further?

Input: I want to buy a subscription
Route: sales
Response: I received your message: 'I want to buy a subscription'. How can I help you further?
```

## With Conversation History

```python
from datetime import datetime, timezone

# Create snapshot with message history
snapshot = ContextSnapshot(
    pipeline_run_id=uuid4(),
    request_id=uuid4(),
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=None,
    interaction_id=uuid4(),
    topology="chat",
    execution_mode="default",
    input_text="Can you explain more?",
    messages=[
        Message(
            role="user",
            content="What is Python?",
            timestamp=datetime.now(timezone.utc),
        ),
        Message(
            role="assistant",
            content="Python is a programming language known for its simplicity.",
            timestamp=datetime.now(timezone.utc),
        ),
    ],
)
```

## With Real LLM (Groq Example)

```python
import os
from groq import AsyncGroq


class GroqClient:
    """Real Groq LLM client."""
    
    def __init__(self):
        self.client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))
    
    async def chat(self, messages, model, temperature, max_tokens):
        response = await self.client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


# Use real client
pipeline = create_chat_pipeline(llm_client=GroqClient())
```

## Adding Enrichment

Enhance the chat pipeline with user context:

```python
def create_enriched_chat_pipeline(llm_client, profile_service, memory_service) -> Pipeline:
    """
    DAG:
        [router] ──────────────┐
                               │
        [profile_enrich] ──────┼─> [llm]
                               │
        [memory_enrich] ───────┘
    """
    return (
        Pipeline()
        .with_stage("router", RouterStage, StageKind.ROUTE)
        .with_stage("profile_enrich", ProfileEnrichStage(profile_service), StageKind.ENRICH)
        .with_stage("memory_enrich", MemoryEnrichStage(memory_service), StageKind.ENRICH)
        .with_stage(
            "llm",
            EnrichedLLMStage(llm_client),
            StageKind.TRANSFORM,
            dependencies=("router", "profile_enrich", "memory_enrich"),
        )
    )


class EnrichedLLMStage:
    """LLM stage that uses enrichment data."""
    
    name = "llm"
    kind = StageKind.TRANSFORM

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        route = ctx.inputs.get("route", "general")
        profile = ctx.inputs.get("profile", {})
        memory = ctx.inputs.get("memory", {})
        
        # Build personalized system prompt
        system_prompt = self._build_system_prompt(route, profile, memory)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": input_text},
        ]
        
        response = await self.llm_client.chat(
            messages=messages,
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=1024,
        )
        
        return StageOutput.ok(response=response)
    
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

## Streaming Responses

For streaming LLM responses, emit events during execution:

```python
class StreamingLLMStage:
    name = "llm"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # ... setup ...
        
        full_response = ""
        async for chunk in self.llm_client.stream_chat(messages):
            full_response += chunk
            
            # Emit streaming event
            ctx.emit_event("chat.token", {
                "token": chunk,
                "partial_response": full_response,
            })
        
        return StageOutput.ok(response=full_response)
```

## Next Steps

- [Full Pipeline](full.md) — Complete pipeline with guards and enrichment
- [Agent with Tools](agent-tools.md) — Add tool execution to chat
- [Observability](../guides/observability.md) — Monitor your chat pipeline
