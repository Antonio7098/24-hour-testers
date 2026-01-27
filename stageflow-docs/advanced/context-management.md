# Context Management Best Practices

Complex retrieval pipelines succeed or fail based on how well they budget context. This guide consolidates ENRICH incident findings into actionable patterns covering token tracking, truncation transparency, and distractor detection.

## Token Tracking

### Goals

1. Prevent silent context window overruns.
2. Emit utilization telemetry for dashboards.
3. Provide per-stage accountability for token-heavy outputs.

### StageContext Patterns

While StageContext does not yet expose a built-in `context_utilization` helper, you can track consumption explicitly:

```python
from stageflow import StageContext, StageOutput

TOKEN_LIMIT = 16_000


def tally_tokens(payload: list[str]) -> int:
    # Approximate token count (replace with tokenizer integration in prod)
    return sum(len(chunk) // 4 for chunk in payload)


async def execute(self, ctx: StageContext) -> StageOutput:
    snippets = ctx.inputs.get_from("retrieval", "documents", default=[])
    used = tally_tokens(snippets)
    utilization = used / TOKEN_LIMIT

    ctx.event_sink.try_emit(
        "context.utilization",
        {"stage": ctx.stage_name, "tokens_used": used, "tokens_limit": TOKEN_LIMIT, "pct": utilization},
    )

    return StageOutput.ok(documents=snippets, tokens_used=used, tokens_limit=TOKEN_LIMIT)
```

**Checklist**

- Include `tokens_used` + `tokens_limit` in every enrichment StageOutput.
- Emit `context.utilization` when utilization exceeds 70% so downstream stages can shrink payloads.
- Surface utilization metrics in dashboards per tenant / pipeline / stage.

## Truncation Transparency

### Why It Matters

- Silent truncation (ENRICH-005) erodes trust—pipelines pass even though evidence is missing.
- Observability depends on consistent events containing what was removed and why.

### Event Contract

Emit `context.truncated` whenever content is dropped:

```python
removed = snippets[token_budget:]
if removed:
    ctx.event_sink.try_emit(
        "context.truncated",
        {
            "stage": ctx.stage_name,
            "bytes_dropped": sum(len(s.encode("utf-8")) for s in removed),
            "reason": "token_budget",
            "affected_keys": ["documents"],
            "tokens_limit": TOKEN_LIMIT,
        },
    )
    snippets = snippets[:token_budget]
```

**Payload Guidelines**

| Field | Description |
|-------|-------------|
| `stage` | Name of the emitting stage. |
| `bytes_dropped` | Size of removed payload before truncation. |
| `reason` | `token_budget`, `redaction`, `safety`, etc. |
| `affected_keys` | Context keys impacted (e.g., `documents`, `memory_entries`). |
| `tokens_limit` | Budget used to justify truncation. |

## Distractor Detection

Distractors are high-similarity but irrelevant snippets that push out critical evidence.

### Detection Flow

1. Score each snippet relative to the query intent.
2. Flag items with high similarity but missing required entity matches.
3. Emit `context.distractor_detected` before removal.

```python
for doc in snippets:
    if doc.similarity >= 0.75 and not doc.metadata.get("bridging_entity"):
        ctx.event_sink.try_emit(
            "context.distractor_detected",
            {
                "stage": ctx.stage_name,
                "doc_id": doc.id,
                "reason": "similarity_plateau",
                "similarity": doc.similarity,
            },
        )
        distractors.append(doc)

snippets = [doc for doc in snippets if doc not in distractors]
```

### Observability Tips

- Aggregate distractor counts per tenant to tune retrieval prompts.
- Correlate with `enrich.multi_hop.degradation` events to identify hop-specific issues.

## Putting It Together

| Concern | Signal | Mitigation |
|---------|--------|------------|
| High utilization | `context.utilization` | Shrink memory window, down-rank low-confidence hops. |
| Truncation | `context.truncated` | Stream drop reasons to alerting + escalate to UX copy. |
| Distractors | `context.distractor_detected` | Adjust retriever filters, enforce bridging-entity gating. |

## Testing Strategy

- **Unit**: deterministic token counters + truncation payload assertions.
- **Integration**: replay adversarial transcripts to confirm events fire when budgets exceeded.
- **Load**: ensure event emission remains O(1) per drop to avoid telemetry amplification.

## Related Docs

- [Multi-hop Retrieval Example](../examples/multi-hop-rag.md)
- [Knowledge Verification](./knowledge-verification.md)
- [ENRICH Stage Guide](../guides/enrich.md)
