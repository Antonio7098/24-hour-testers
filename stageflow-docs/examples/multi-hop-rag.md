# Multi-hop Retrieval Example

Multi-hop retrieval pipelines gather evidence across multiple documents or data sources before generating a response. This example demonstrates how to orchestrate entity chain traversal, hop limits, and degradation detection with Stageflow.

## When to Use Multi-hop Retrieval

Use a multi-hop RAG pattern when:

- Answers require bridging entities (e.g., "Which CEO succeeded the founder of the company that built the Falcon 9?").
- Evidence spans documents with sparse linking structure.
- You must surface partial progress (per-hop findings) for audit or user feedback.

## Pipeline Overview

```
[input] → [seed_entities] → [multi_hop_retrieval] → [evidence_ranker] → [llm_answer]
```

| Stage | Kind | Purpose |
|-------|------|---------|
| `seed_entities` | ENRICH | Extract initial entities and relationships from the query. |
| `multi_hop_retrieval` | ENRICH | Traverse knowledge sources hop-by-hop with guardrails. |
| `evidence_ranker` | TRANSFORM | Score retrieved nodes, prune distractors, tag coverage gaps. |
| `llm_answer` | TRANSFORM | Generate the final answer citing hop outputs. |

## MultiHopRetrievalStage Skeleton

```python
from collections import deque
from typing import Iterable

from stageflow import StageContext, StageKind, StageOutput


class MultiHopRetrievalStage:
    name = "multi_hop_retrieval"
    kind = StageKind.ENRICH

    def __init__(
        self,
        retriever,
        *,
        max_hops: int = 3,
        max_entities: int = 128,
        hop_score_threshold: float = 0.45,
    ) -> None:
        self._retriever = retriever
        self._max_hops = max_hops
        self._max_entities = max_entities
        self._hop_score_threshold = hop_score_threshold

    async def execute(self, ctx: StageContext) -> StageOutput:
        seed_entities: list[dict] = ctx.inputs.get_from(
            "seed_entities", "entities", default=[]
        )
        if not seed_entities:
            return StageOutput.skip(reason="no_seed_entities")

        frontier = deque([(entity, 0) for entity in seed_entities])
        visited_ids: set[str] = set()
        hop_results: list[dict] = []
        coverage_metrics = {"hops_attempted": 0, "hops_completed": 0}

        while frontier and len(hop_results) < self._max_entities:
            entity, hop = frontier.popleft()
            if entity["id"] in visited_ids or hop >= self._max_hops:
                continue

            coverage_metrics["hops_attempted"] += 1
            docs = await self._retriever.fetch_related(entity)
            filtered = [d for d in docs if d.score >= self._hop_score_threshold]
            coverage_metrics["hops_completed"] += 1

            hop_results.append({
                "hop": hop,
                "entity": entity,
                "documents": [d.to_dict() for d in filtered],
            })

            for doc in filtered:
                bridge_entity = doc.metadata.get("bridging_entity")
                if bridge_entity and bridge_entity not in visited_ids:
                    frontier.append((bridge_entity, hop + 1))

            visited_ids.add(entity["id"])

        degradation = _compute_degradation(hop_results)
        if degradation["confidence_drop"] >= 0.15:
            ctx.event_sink.try_emit(
                "enrich.multi_hop.degradation",
                {
                    "confidence_drop": degradation["confidence_drop"],
                    "hop_count": degradation["hop_count"],
                    "last_nonempty_hop": degradation["last_nonempty_hop"],
                },
            )

        return StageOutput.ok(
            hop_results=hop_results,
            coverage=coverage_metrics,
            degradation=degradation,
        )


def _compute_degradation(hops: Iterable[dict]) -> dict:
    """Detects hop-count degradation for observability dashboards."""
    if not hops:
        return {"confidence_drop": 1.0, "hop_count": 0, "last_nonempty_hop": -1}

    scores = [
        max((doc["score"] for doc in hop["documents"]), default=0.0)
        for hop in hops
    ]
    return {
        "confidence_drop": max(scores[:1] or [0]) - min(scores or [0]),
        "hop_count": len(hops),
        "last_nonempty_hop": max((i for i, s in enumerate(scores) if s > 0), default=-1),
    }
```

### Key Design Notes

1. **Fail Explicitly:** Emit `enrich.multi_hop.degradation` instead of silently returning degraded results.
2. **Bounded Search:** Cap both hop depth and total entities to avoid runaway traversals.
3. **Structured Outputs:** Return per-hop metadata so downstream stages can explain reasoning paths.
4. **Token Hygiene:** Attach `memory_tokens` or `context_tokens` metadata before passing to LLM stages.

## Bridging Entity Detection

- Annotate retriever results with `metadata.bridging_entity` or `metadata.relation_span`.
- Maintain a queue of unexplored bridging entities to continue traversal.
- Emit `context.distractor_detected` when new hops return redundant information.<br>
  Example payload:
  ```json
  {
    "entity_id": "doc#42",
    "hop": 2,
    "distractor_reason": "similarity_plateau"
  }
  ```

## Hop-count Degradation Mitigation

| Symptom | Mitigation |
|---------|------------|
| Confidence plateaus after hop 1 | Reduce `max_hops`, refresh seed entities from LLM critique stage. |
| Empty hops with distractors | Add semantic filters (e.g., hybrid search) and enforce `distractor_reason`. |
| Latency spikes | Parallelize retriever fetches per hop with `asyncio.gather` and budgeted timeouts. |

## Testing Checklist

- **Unit:** Mock retriever returning deterministic hops; assert `hop_results` ordering and event emission.
- **Integration:** Replay real incident transcripts to verify bridging entity coverage.
- **Load:** Ensure queue growth remains bounded by `max_entities` under adversarial inputs.

## Related Guides

- [Knowledge Verification](../advanced/knowledge-verification.md)
- [Context Management](../advanced/context-management.md)
- [Version-aware Enrichment](../guides/enrich.md)
