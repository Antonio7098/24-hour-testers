# Knowledge Verification Patterns

Legal, medical, and financial assistants must defend every statement they produce. Knowledge verification layers guard ENRICH pipelines against citation hallucinations by forcing structured checkpoints between retrieval and generation.

This guide focuses on two complementary patterns:

1. **Entity Grounding (EG)** – prove that each cited entity exists in the retrieved corpus.
2. **Relation Preservation (RP)** – ensure that relationships between entities match the source material.

> Use both patterns together to minimize false positives: EG keeps citations honest, RP keeps reasoning chains intact.

---

## Entity Grounding (EG)

### What EG Protects

| Risk | Example | EG Safeguard |
|------|---------|--------------|
| Fabricated entities | "The *Lexora Act* (nonexistent) authorized the merger" | Cross-check entity against retrieval graph, emit failure if not found. |
| Misattributed roles | "Dr. Patel is the CFO" when docs list Dr. Patel as CIO | Compare role metadata with authoritative documents. |
| Missing provenance | Answer references "Study 42" without URL | Require StageOutput artifacts to include citation payloads and `provenance_id`. |

### Wiring an EntityGroundingGuard

```
[retrieval] → [entity_grounding_guard] → [llm]
```

```python
from stageflow import StageContext, StageKind, StageOutput


class EntityGroundingGuard:
    name = "entity_grounding_guard"
    kind = StageKind.GUARD

    def __init__(self, *, required_confidence: float = 0.6):
        self._required_confidence = required_confidence

    async def execute(self, ctx: StageContext) -> StageOutput:
        entities = ctx.inputs.get_from("retrieval", "entities", default=[])
        corpus_index = ctx.inputs.get_from("retrieval", "corpus_index", default={})

        missing = []
        for entity in entities:
            evidence = corpus_index.get(entity["id"])
            if not evidence:
                missing.append({"entity": entity, "reason": "not_found"})
            elif evidence["confidence"] < self._required_confidence:
                missing.append({"entity": entity, "reason": "low_confidence"})

        if missing:
            ctx.event_sink.try_emit(
                "knowledge.eg.failed",
                {"missing_entities": missing, "required_confidence": self._required_confidence},
            )
            return StageOutput.fail(
                error="entity_grounding_failed",
                data={"missing_entities": missing},
            )

        return StageOutput.ok(grounded_entities=entities)
```

### EG Checklist

- `retrieval` stage must return `entities` + `corpus_index` keyed by entity ID.
- Guard emits `knowledge.eg.failed` with structured payload on failure.
- Tests cover: found, not found, low confidence, empty input.

---

## Relation Preservation (RP)

EG validates *what* is cited. RP validates *how* entities relate.

### RP Risks

| Failure | Impact |
|---------|--------|
| Relation inversion | Swapping plaintiff/defendant flips legal outcome. |
| Time-travel errors | Quoting a superseded regulation version corrupts guidance. |
| Missing qualifiers | Statement omits jurisdiction or contractual scope. |

### RP Stage Skeleton

```python
class RelationPreservationGuard:
    name = "relation_preservation_guard"
    kind = StageKind.GUARD

    def __init__(self, relation_resolver):
        self._relation_resolver = relation_resolver

    async def execute(self, ctx: StageContext) -> StageOutput:
        hops = ctx.inputs.get_from("multi_hop_retrieval", "hop_results", default=[])
        llm_claims = ctx.inputs.get_from("draft_answer", "claims", default=[])

        violations: list[dict] = []
        for claim in llm_claims:
            ground_truth = self._relation_resolver.lookup(
                subject=claim["subject"],
                relation=claim["relation"],
                obj=claim["object"],
                timestamp=claim.get("timestamp"),
            )
            if not ground_truth:
                violations.append({"claim": claim, "reason": "missing_source"})
                continue

            if ground_truth["version"] != claim.get("version"):
                violations.append({
                    "claim": claim,
                    "reason": "version_mismatch",
                    "expected_version": ground_truth["version"],
                })
            if ground_truth["relation"] != claim["relation"]:
                violations.append({"claim": claim, "reason": "relation_mismatch"})

        if violations:
            ctx.event_sink.try_emit(
                "knowledge.rp.violation",
                {"violations": violations, "claim_count": len(llm_claims)},
            )
            return StageOutput.fail(
                error="relation_preservation_failed",
                data={"violations": violations},
            )

        return StageOutput.ok(
            grounded_claims=len(llm_claims),
            hop_evidence=hops,
        )
```

### RP Implementation Notes

1. **Relation Resolver** – Backed by graph DB or vector store with predicate tags.
2. **Temporal Awareness** – Always compare `version` and `timestamp` fields.
3. **Hop Evidence** – Provide the guard with hop-level context to trace chain-of-thought.

---

## Testing Guidance

| Layer | Tests |
|-------|-------|
| Unit | EG guard: missing entity, low confidence, empty corpus. RP guard: missing relation, version mismatch. |
| Integration | Replay real incidents (e.g., ENRICH-003) and assert guard emits violations before LLM stage executes. |
| Load | Stress-test with >1k entities/claims to ensure guards remain O(n) and event payloads stay bounded. |

---

## Observability Signals

- `knowledge.eg.failed` – Missing/low-confidence entities. Attach `entity_count` and `tenant_id`.
- `knowledge.rp.violation` – Relation mismatch or missing source.
- `enrich.version_conflict` – Emit from retrieval when multiple document versions match (see [Version-aware Enrichment](../guides/enrich.md)).

Stream these events into your telemetry sink for proactive alerting.

---

## Related Reading

- [Multi-hop Retrieval Example](../examples/multi-hop-rag.md)
- [Context Management Best Practices](./context-management.md)
- [StageOutput Version Metadata](../guides/enrich.md#version-metadata-contracts)
