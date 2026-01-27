# Idempotency Patterns for WORK Stages

Stageflow's WORK stages typically perform side effects (database writes, API calls,
payments). **Idempotency** ensures that retries, duplicate HTTP requests, or replay
attacks never trigger the same side effect twice. This guide shows how to wire the
built-in `IdempotencyInterceptor`, design idempotency keys, validate parameters, and
choose the right backing store.

## When to Enforce Idempotency

| Scenario | Recommended Approach |
|----------|---------------------|
| Incoming HTTP POST/PUT | Use the client-provided request ID / payment intent ID as the idempotency key. |
| Background jobs with retries | Derive the key from `(job_id, attempt_group)` to collapse duplicate retries. |
| Tool executions inside agents | Have the tool populate `ctx.data["idempotency_key"]` using the tool call ID. |
| Replay protection | Combine `(client_id, natural_key, time_bucket)` and enforce TTLs on the store. |

**Rule of thumb:** every WORK stage that mutates external state should set an
idempotency key before the stage executes.

```python
from stageflow.stages.context import PipelineContext

async def add_idempotency(ctx: PipelineContext, *, client_id: str, charge_id: str) -> None:
    ctx.data["idempotency_key"] = f"{client_id}:{charge_id}"
    ctx.data["idempotency_params"] = {
        "client_id": client_id,
        "charge_id": charge_id,
    }
```

## Wiring the Interceptor

`IdempotencyInterceptor` is part of `get_default_interceptors()`. To share a store
across pipelines, pass it explicitly:

```python
from stageflow.pipeline.interceptors import get_default_interceptors
from stageflow.pipeline.idempotency import InMemoryIdempotencyStore

store = InMemoryIdempotencyStore()
interceptors = get_default_interceptors(idempotency_store=store)
```

### Atomic Duplicate Handling

As of `stageflow-core v0.8.1`, the interceptor coordinates **per-key asyncio locks**
so only the first in-flight request executes the stage. Any concurrent duplicate:

1. Waits on the per-key lock while the first request runs.
2. Receives the cached `StageResult` once the lock owner stores the result.
3. Fails fast with `IdempotencyParamMismatch` if parameters differ.

This guarantees duplicate suppression even when the underlying store is an eventually
consistent cache, and it closes BUG-072 / BUG-073 for high-concurrency workloads.

### Parameter Validation

Provide a stable dict via `ctx.data["idempotency_params"]` so the interceptor can
hash arguments and detect intent mismatches:

```python
ctx.data["idempotency_params"] = {
    "amount": request.amount_cents,
    "currency": request.currency,
    "customer_id": request.customer_id,
}
```

If a duplicate arrives with the same key but different params, the interceptor raises
`IdempotencyParamMismatch` (a `CriticalInterceptorError`). Handle it at the pipeline
level or surface it to the caller as a 409 Conflict.

## Store Options

| Store | Best For | Notes |
|-------|----------|-------|
| `InMemoryIdempotencyStore` | Tests, single-process pilots | TTL support, asyncio lock safety only at interceptor layer. |
| Redis / Key-Value cache | Multi-process deployments | Implement `IdempotencyStore` protocol; store hashes + expirations. |
| SQL database | Strong ordering guarantees | Use `SELECT ... FOR UPDATE` or unique constraints to gate writers. |

When implementing a custom store, follow the protocol in
`stageflow.pipeline.idempotency.IdempotencyStore`. Always clone the `StageResult`
before storing or returning cached data to avoid accidental mutation.

## Observability

The interceptor emits structured logs:

- `"Stored idempotent result"` when a stage completes successfully.
- `"Idempotency hit"` when a duplicate is short-circuited.

Forward these to metrics or tracing exporters to build dashboards such as:

| Metric | Description |
|--------|-------------|
| `work.idempotency_hit` | Count of duplicate requests collapsed per stage. |
| `work.idempotency_param_mismatch` | Requests rejected due to parameter drift. |

## Testing Checklist

1. **Cache hit short-circuits**: Assert `before()` returns an `InterceptorResult` with
   `stage_ran=False` when the store has an entry.
2. **Parameter mismatch**: Ensure duplicates with differing params raise
   `IdempotencyParamMismatch`.
3. **Concurrent duplicates**: Fire two tasks with the same key and assert the second
   receives a cached result once the first finishes.
4. **TTL expiry**: Confirm store entries expire and new work executes once TTL lapses.

With these patterns in place, WORK stages become safe to retry, resilient to client
replays, and observable in production.
