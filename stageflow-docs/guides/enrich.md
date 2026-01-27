# ENRICH Stage Guide

ENRICH stages add or refine context before generation stages execute. They typically fetch documents, memories, or knowledge graph nodes, and must emit structured metadata for downstream observability.

## Design Goals

1. **Deterministic provenance** – every enrichment should be traceable back to the original document, version, and retrieval strategy.
2. **Tunable breadth** – configure hop counts, degree caps, or confidence thresholds per tenant.
3. **Explainable failure** – emit events for truncation, version conflicts, and distractor filtering instead of silently degrading output.

## Version-aware Retrieval

LLMs often receive multiple revisions of the same document. Adopt temporal filtering patterns to guarantee consistent evidence:

| Strategy | Description | Use When |
|----------|-------------|----------|
| `LATEST_DATE` | Select entries with the most recent `effective_at` timestamp. | Compliance, policy updates. |
| `LATEST_VERSION` | Select entries with the highest semantic version (e.g., `v3.2.1`). | API or schema references. |
| `ALL_VERSIONS` | Return every matching version plus `version_history` metadata. | Audits, litigation holds. |

### Implementation Steps

1. **Annotate Retrieval Outputs** – include `document_id`, `version`, `effective_at`, and `source_uri` in each record.
2. **Emit Version Conflicts** – if more than one version survives filtering, emit `enrich.version_conflict` with payload `{document_id, versions}`.
3. **Tag StageOutput** – return `StageOutput.ok(..., version="<schema_version>")` to advertise the enrichment schema to downstream stages. StageOutput already exposes a `version` field for this purpose (@stageflow/core/stage_output.py#35-158).
4. **Surface Resolution Strategy** – add `resolution_strategy` to payloads so later stages can explain why certain documents were omitted.

### Example Snippet

```python
results = _filter_versions(docs, strategy)
if len({doc.version for doc in results}) > 1:
    ctx.event_sink.try_emit(
        "enrich.version_conflict",
        {"document_id": docs[0].document_id, "versions": [doc.version for doc in results]},
    )

return StageOutput.ok(
    documents=[doc.to_dict() for doc in results],
    resolution_strategy=strategy,
    version="enrich.docs.v1",
)
```

## Composing ENRICH Pipelines

```
[input] → [seed_entities] → [retrieval] → [entity_grounding_guard] → [context_compactor]
```

- **Seed Entity Extractors** convert natural language to structured pivots (entities, timestamps, jurisdictions).
- **Retrieval ENRICH stages** implement version-aware filtering plus hop control (see [Multi-hop Retrieval Example](../examples/multi-hop-rag.md)).
- **Guards** such as Entity Grounding or Relation Preservation (see [Knowledge Verification](../advanced/knowledge-verification.md)) validate evidence before generation.
- **Context Compactors** cap token budgets and emit truncation events (see [Context Management](../advanced/context-management.md)).

## Observability Checklist

| Signal | When to Emit | Payload |
|--------|--------------|---------|
| `enrich.version_conflict` | Multiple versions remain after filtering. | `document_id`, `versions`, `resolution_strategy`. |
| `enrich.multi_hop.degradation` | Hop confidence drop exceeds SLA. | `confidence_drop`, `hop_count`, `last_nonempty_hop`. |
| `context.truncated` | Content removed to fit limits. | `bytes_dropped`, `reason`, `affected_keys`, `tokens_limit`. |
| `context.distractor_detected` | High-similarity but irrelevant docs pruned. | `entity_id`, `hop`, `distractor_reason`. |

## Testing Recommendations

- **Unit Tests** for filtering helpers covering each resolution strategy plus conflict emission.
- **Integration Tests** replaying ENRICH incident transcripts to ensure correct version selection.
- **Property Tests** that fuzz timestamps and version strings to prevent silent ordering regressions.
