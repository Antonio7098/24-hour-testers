# Checkpoint & Restore Patterns

Long-running pipelines can fail mid-execution due to crashes, deployments, or resource
limits. **Checkpointing** captures pipeline state at strategic points so execution can
resume from the last successful checkpoint rather than restarting from scratch.

## When to Checkpoint

| Scenario | Recommendation |
|----------|----------------|
| Long-running batch jobs | Checkpoint every N items or M minutes |
| Multi-stage workflows | Checkpoint after expensive stages |
| External API calls | Checkpoint before/after rate-limited calls |
| User-facing pipelines | Checkpoint to enable "continue where you left off" |
| Cost-sensitive operations | Checkpoint before expensive LLM calls |

**Rule of thumb:** Checkpoint after any stage that is expensive to re-execute.

## ContextSnapshot

Stageflow's `ContextSnapshot` provides immutable state capture:

```python
from stageflow.context import ContextSnapshot
from stageflow.context.identity import RunIdentity


# Create a snapshot from current context
snapshot = ContextSnapshot(
    run_id=RunIdentity(
        pipeline_run_id=ctx.pipeline_run_id,
        request_id=ctx.request_id,
        session_id=ctx.session_id,
        user_id=ctx.user_id,
        org_id=ctx.org_id,
    ),
    topology=ctx.topology,
    execution_mode=ctx.execution_mode,
    data=ctx.data.copy(),  # Shallow copy of mutable data
)
```

### Serialization

Snapshots serialize to/from dictionaries for persistence:

```python
# Serialize to dict (for storage)
snapshot_dict = snapshot.to_dict()

# Restore from dict
restored = ContextSnapshot.from_dict(snapshot_dict)
```

## Checkpoint Store Protocol

Define a store for persisting checkpoints:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class Checkpoint:
    """A saved pipeline checkpoint."""
    
    checkpoint_id: str
    pipeline_run_id: UUID
    stage_name: str
    snapshot: dict[str, Any]
    created_at: datetime
    metadata: dict[str, Any] | None = None


class CheckpointStore(ABC):
    """Protocol for checkpoint persistence."""
    
    @abstractmethod
    async def save(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint."""
        ...
    
    @abstractmethod
    async def load(self, pipeline_run_id: UUID) -> Checkpoint | None:
        """Load the latest checkpoint for a pipeline run."""
        ...
    
    @abstractmethod
    async def load_by_id(self, checkpoint_id: str) -> Checkpoint | None:
        """Load a specific checkpoint by ID."""
        ...
    
    @abstractmethod
    async def list_checkpoints(
        self, pipeline_run_id: UUID
    ) -> list[Checkpoint]:
        """List all checkpoints for a pipeline run."""
        ...
    
    @abstractmethod
    async def delete(self, checkpoint_id: str) -> None:
        """Delete a checkpoint."""
        ...
```

### In-Memory Store (Testing)

```python
from collections import defaultdict


class InMemoryCheckpointStore(CheckpointStore):
    """In-memory checkpoint store for testing."""
    
    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}
        self._by_run: dict[UUID, list[str]] = defaultdict(list)
    
    async def save(self, checkpoint: Checkpoint) -> None:
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        self._by_run[checkpoint.pipeline_run_id].append(checkpoint.checkpoint_id)
    
    async def load(self, pipeline_run_id: UUID) -> Checkpoint | None:
        checkpoint_ids = self._by_run.get(pipeline_run_id, [])
        if not checkpoint_ids:
            return None
        # Return most recent
        return self._checkpoints.get(checkpoint_ids[-1])
    
    async def load_by_id(self, checkpoint_id: str) -> Checkpoint | None:
        return self._checkpoints.get(checkpoint_id)
    
    async def list_checkpoints(self, pipeline_run_id: UUID) -> list[Checkpoint]:
        checkpoint_ids = self._by_run.get(pipeline_run_id, [])
        return [self._checkpoints[cid] for cid in checkpoint_ids if cid in self._checkpoints]
    
    async def delete(self, checkpoint_id: str) -> None:
        checkpoint = self._checkpoints.pop(checkpoint_id, None)
        if checkpoint:
            self._by_run[checkpoint.pipeline_run_id].remove(checkpoint_id)
```

### Redis Store (Production)

```python
import json
from redis.asyncio import Redis


class RedisCheckpointStore(CheckpointStore):
    """Redis-backed checkpoint store for production."""
    
    def __init__(self, redis: Redis, ttl_seconds: int = 86400) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
    
    async def save(self, checkpoint: Checkpoint) -> None:
        key = f"checkpoint:{checkpoint.checkpoint_id}"
        run_key = f"checkpoints:run:{checkpoint.pipeline_run_id}"
        
        data = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "pipeline_run_id": str(checkpoint.pipeline_run_id),
            "stage_name": checkpoint.stage_name,
            "snapshot": checkpoint.snapshot,
            "created_at": checkpoint.created_at.isoformat(),
            "metadata": checkpoint.metadata,
        }
        
        async with self._redis.pipeline() as pipe:
            pipe.setex(key, self._ttl, json.dumps(data))
            pipe.rpush(run_key, checkpoint.checkpoint_id)
            pipe.expire(run_key, self._ttl)
            await pipe.execute()
    
    async def load(self, pipeline_run_id: UUID) -> Checkpoint | None:
        run_key = f"checkpoints:run:{pipeline_run_id}"
        checkpoint_ids = await self._redis.lrange(run_key, -1, -1)
        
        if not checkpoint_ids:
            return None
        
        return await self.load_by_id(checkpoint_ids[0].decode())
    
    async def load_by_id(self, checkpoint_id: str) -> Checkpoint | None:
        key = f"checkpoint:{checkpoint_id}"
        data = await self._redis.get(key)
        
        if not data:
            return None
        
        parsed = json.loads(data)
        return Checkpoint(
            checkpoint_id=parsed["checkpoint_id"],
            pipeline_run_id=UUID(parsed["pipeline_run_id"]),
            stage_name=parsed["stage_name"],
            snapshot=parsed["snapshot"],
            created_at=datetime.fromisoformat(parsed["created_at"]),
            metadata=parsed.get("metadata"),
        )
    
    async def list_checkpoints(self, pipeline_run_id: UUID) -> list[Checkpoint]:
        run_key = f"checkpoints:run:{pipeline_run_id}"
        checkpoint_ids = await self._redis.lrange(run_key, 0, -1)
        
        checkpoints = []
        for cid in checkpoint_ids:
            checkpoint = await self.load_by_id(cid.decode())
            if checkpoint:
                checkpoints.append(checkpoint)
        return checkpoints
    
    async def delete(self, checkpoint_id: str) -> None:
        key = f"checkpoint:{checkpoint_id}"
        await self._redis.delete(key)
```

## CheckpointInterceptor

Automatically checkpoint after specified stages:

```python
import logging
from datetime import datetime, timezone
from uuid import uuid4

from stageflow.pipeline.interceptors import BaseInterceptor, InterceptorResult
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

logger = logging.getLogger("stageflow.checkpoint")


class CheckpointInterceptor(BaseInterceptor):
    """Interceptor that saves checkpoints after stage completion.
    
    Configure which stages to checkpoint via `checkpoint_stages` or
    checkpoint all stages with `checkpoint_all=True`.
    """
    
    name = "checkpoint"
    priority = 55  # Run after logging
    
    def __init__(
        self,
        store: CheckpointStore,
        checkpoint_stages: set[str] | None = None,
        checkpoint_all: bool = False,
    ) -> None:
        """Initialize checkpoint interceptor.
        
        Args:
            store: Checkpoint persistence store
            checkpoint_stages: Set of stage names to checkpoint
            checkpoint_all: If True, checkpoint after every stage
        """
        self.store = store
        self.checkpoint_stages = checkpoint_stages or set()
        self.checkpoint_all = checkpoint_all
    
    async def before(
        self, stage_name: str, ctx: PipelineContext
    ) -> InterceptorResult | None:
        """Check for existing checkpoint to restore."""
        
        # Check if we should restore from checkpoint
        if ctx.data.get("_checkpoint.restore"):
            checkpoint = await self.store.load(ctx.pipeline_run_id)
            if checkpoint and checkpoint.stage_name == stage_name:
                logger.info(
                    f"Restoring from checkpoint at stage {stage_name}",
                    extra={
                        "stage": stage_name,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "pipeline_run_id": str(ctx.pipeline_run_id),
                    },
                )
                # Restore context data from checkpoint
                ctx.data.update(checkpoint.snapshot.get("data", {}))
                ctx.data.pop("_checkpoint.restore", None)
        
        return None
    
    async def after(
        self, stage_name: str, result: StageResult, ctx: PipelineContext
    ) -> None:
        """Save checkpoint after successful stage completion."""
        
        # Skip failed stages
        if result.status == "failed":
            return
        
        # Check if this stage should be checkpointed
        should_checkpoint = (
            self.checkpoint_all
            or stage_name in self.checkpoint_stages
            or ctx.data.get("_checkpoint.force")
        )
        
        if not should_checkpoint:
            return
        
        # Create checkpoint
        checkpoint = Checkpoint(
            checkpoint_id=f"ckpt_{uuid4().hex[:12]}",
            pipeline_run_id=ctx.pipeline_run_id,
            stage_name=stage_name,
            snapshot={
                "data": ctx.data.copy(),
                "topology": ctx.topology,
                "execution_mode": ctx.execution_mode,
            },
            created_at=datetime.now(timezone.utc),
            metadata={
                "stage_result_status": result.status,
                "stage_duration_ms": int(
                    (result.ended_at - result.started_at).total_seconds() * 1000
                ),
            },
        )
        
        await self.store.save(checkpoint)
        
        logger.info(
            f"Checkpoint saved after stage {stage_name}",
            extra={
                "stage": stage_name,
                "checkpoint_id": checkpoint.checkpoint_id,
                "pipeline_run_id": str(ctx.pipeline_run_id),
            },
        )
        
        # Emit event
        if hasattr(ctx, "event_sink"):
            ctx.event_sink.try_emit(
                "pipeline.checkpoint_saved",
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "stage": stage_name,
                    "pipeline_run_id": str(ctx.pipeline_run_id),
                },
            )
        
        # Clear force flag
        ctx.data.pop("_checkpoint.force", None)
```

## Usage Patterns

### Checkpoint After Expensive Stages

```python
from stageflow.pipeline.interceptors import get_default_interceptors

# Configure checkpointing for specific stages
checkpoint_interceptor = CheckpointInterceptor(
    store=RedisCheckpointStore(redis_client),
    checkpoint_stages={
        "llm_generation",
        "document_processing",
        "external_api_call",
    },
)

interceptors = get_default_interceptors()
interceptors.append(checkpoint_interceptor)
```

### Force Checkpoint from Stage

```python
class ExpensiveStage:
    """Stage that should always checkpoint."""
    
    name = "expensive_computation"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Expensive computation
        result = await self._compute(ctx.inputs["data"])
        
        # Force checkpoint after this stage
        ctx.data["_checkpoint.force"] = True
        
        return StageOutput.ok(result=result)
```

### Resume from Checkpoint

```python
async def run_pipeline_with_resume(
    pipeline: Pipeline,
    ctx: PipelineContext,
    checkpoint_store: CheckpointStore,
) -> dict:
    """Run pipeline with checkpoint restoration."""
    
    # Check for existing checkpoint
    checkpoint = await checkpoint_store.load(ctx.pipeline_run_id)
    
    if checkpoint:
        logger.info(
            f"Found checkpoint at stage {checkpoint.stage_name}",
            extra={"checkpoint_id": checkpoint.checkpoint_id},
        )
        
        # Restore context from checkpoint
        ctx.data.update(checkpoint.snapshot.get("data", {}))
        ctx.data["_checkpoint.restore"] = True
        
        # Run from checkpoint stage
        return await pipeline.run_from_stage(
            ctx,
            start_stage=checkpoint.stage_name,
        )
    
    # No checkpoint, run from beginning
    return await pipeline.run(ctx)
```

### Periodic Checkpointing

```python
import time


class PeriodicCheckpointInterceptor(BaseInterceptor):
    """Checkpoint every N seconds or M stages."""
    
    name = "periodic_checkpoint"
    priority = 55
    
    def __init__(
        self,
        store: CheckpointStore,
        interval_seconds: int = 60,
        interval_stages: int = 10,
    ) -> None:
        self.store = store
        self.interval_seconds = interval_seconds
        self.interval_stages = interval_stages
        self._last_checkpoint_time = time.time()
        self._stages_since_checkpoint = 0
    
    async def after(
        self, stage_name: str, result: StageResult, ctx: PipelineContext
    ) -> None:
        if result.status == "failed":
            return
        
        self._stages_since_checkpoint += 1
        elapsed = time.time() - self._last_checkpoint_time
        
        should_checkpoint = (
            elapsed >= self.interval_seconds
            or self._stages_since_checkpoint >= self.interval_stages
        )
        
        if should_checkpoint:
            await self._save_checkpoint(stage_name, ctx)
            self._last_checkpoint_time = time.time()
            self._stages_since_checkpoint = 0
```

## Observability

| Event | Description | Fields |
|-------|-------------|--------|
| `pipeline.checkpoint_saved` | Checkpoint persisted | `checkpoint_id`, `stage`, `pipeline_run_id` |
| `pipeline.checkpoint_restored` | Resumed from checkpoint | `checkpoint_id`, `stage`, `pipeline_run_id` |
| `pipeline.checkpoint_deleted` | Cleanup after completion | `checkpoint_id`, `pipeline_run_id` |

## Best Practices

### 1. Checkpoint Serializable State Only

```python
# Good: only serializable data
checkpoint_data = {
    "user_id": str(ctx.user_id),
    "processed_items": processed_count,
    "last_item_id": last_id,
}

# Bad: non-serializable objects
checkpoint_data = {
    "db_connection": db,  # Can't serialize
    "file_handle": f,  # Can't serialize
}
```

### 2. Clean Up Old Checkpoints

```python
async def cleanup_checkpoints(
    store: CheckpointStore,
    pipeline_run_id: UUID,
    keep_last: int = 1,
) -> None:
    """Remove old checkpoints after successful completion."""
    checkpoints = await store.list_checkpoints(pipeline_run_id)
    
    # Keep only the most recent N checkpoints
    for checkpoint in checkpoints[:-keep_last]:
        await store.delete(checkpoint.checkpoint_id)
```

### 3. Version Checkpoint Schema

```python
CHECKPOINT_SCHEMA_VERSION = 2

checkpoint = Checkpoint(
    checkpoint_id=checkpoint_id,
    pipeline_run_id=run_id,
    stage_name=stage_name,
    snapshot={
        "_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "data": ctx.data.copy(),
    },
    created_at=datetime.now(timezone.utc),
)

# On restore, handle schema migrations
def migrate_checkpoint(snapshot: dict) -> dict:
    version = snapshot.get("_schema_version", 1)
    if version < 2:
        # Migrate from v1 to v2
        snapshot["data"]["new_field"] = "default_value"
    return snapshot
```

### 4. Test Checkpoint Restore

```python
@pytest.mark.asyncio
async def test_pipeline_resumes_from_checkpoint():
    """Verify pipeline continues from checkpoint after restart."""
    
    store = InMemoryCheckpointStore()
    
    # Simulate first run that fails mid-way
    ctx1 = create_test_pipeline_context()
    
    # Save checkpoint at stage 2
    checkpoint = Checkpoint(
        checkpoint_id="test_ckpt",
        pipeline_run_id=ctx1.pipeline_run_id,
        stage_name="stage_2",
        snapshot={"data": {"stage_1_result": "done"}},
        created_at=datetime.now(timezone.utc),
    )
    await store.save(checkpoint)
    
    # Resume from checkpoint
    ctx2 = create_test_pipeline_context(
        pipeline_run_id=ctx1.pipeline_run_id,
    )
    ctx2.data["_checkpoint.restore"] = True
    
    # Run pipeline with checkpoint interceptor
    interceptor = CheckpointInterceptor(store=store, checkpoint_all=True)
    result = await run_pipeline(ctx2, interceptors=[interceptor])
    
    # Verify stage_1 was skipped
    assert "stage_1" not in result["executed_stages"]
    assert "stage_2" in result["executed_stages"]
```

## Related Guides

- [Saga Pattern](./saga-pattern.md) - Compensation when checkpointed stages fail
- [Idempotency Patterns](./idempotency.md) - Ensure resumed stages don't duplicate
- [Retry & Backoff](./retry-backoff.md) - Handle transient failures before checkpointing
