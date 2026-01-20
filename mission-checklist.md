# Scenario Checklist Skeleton (Lean)

> Fill in only what the loop needs: clear SUT pointers, prioritized tiers, and execution status.

---

## Instructions (keep it short)

- Replace placeholders like `{SUT_component}` with actual assets/endpoints.
- Duplicate rows instead of adding new sections unless your SUT truly needs them.
- Add more tiers only when you introduce a fundamentally new risk class (reuse the same 5-column table).
- Status values: `☐ Not Started`, `🚧 In Progress`, `✅ Completed (YYYY-MM-DD)`.

Each row should describe one autonomous run that fits inside your usual timebox.

---

## Tier 1 · Core Reliability (must exist)

| ID | Target Focus | Priority | Risk | Status |
|----|--------------|----------|------|--------|
| CORE-001 | `{SUT_state_store}` concurrency + isolation | P0 | Catastrophic | ☐ Not Started |
| CORE-002 | `{orchestrator}` scheduling limits (deadlock / starvation) | P0 | Severe | ☐ Not Started |
| CORE-003 | `{contract_layer}` schema enforcement + error surfacing | P1 | High | ☐ Not Started |

> Tip: keep Tier 1 rows rooted in primitives the entire SUT depends on.

---

## Tier 2 · Functional/Stage Risks (pick 3–5 rows that matter)

| ID | Stage / Capability | Priority | Risk | Status |
|----|--------------------|----------|------|--------|
| STAGE-001 | `{critical_stage}` happy-path + adversarial coverage | P1 | High | ☐ Not Started |
| STAGE-002 | `{guardrail}` enforcement (prompt/policy/tool) | P0 | Catastrophic | ☐ Not Started |
| STAGE-003 | `{agent_behavior}` stability past `{iteration_limit}` cycles | P1 | Severe | ☐ Not Started |

Add or swap rows to reflect your top-stage concerns (transform, enrich, guard, route, work, etc.).

---

## Tier 3 · Deployment / Infrastructure (only what you run)

| ID | Environment Target | Priority | Risk | Status |
|----|--------------------|----------|------|--------|
| INFRA-001 | `{primary_env}` scaling + failover playbook | P1 | High | ☐ Not Started |
| INFRA-002 | `{edge_or_dr}` offline / degraded-mode readiness | P1 | Severe | ☐ Not Started |
| INFRA-003 | `{multi_region}` convergence + data sovereignty | P1 | High | ☐ Not Started |

Remove rows you don’t need; the loop only cares that the checklist is truthful and prioritized.
