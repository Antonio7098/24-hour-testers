# Mission Brief Template

> **Purpose**: Give autonomous agents a concise, vendor-neutral packet describing the current system under test (SUT), its constraints, and the goals for this campaign. Replace every placeholder with concrete details before launching the loop.

---

## 1. Snapshot

| Field | Value |
|-------|-------|
| SUT name | {SYSTEM_NAME} |
| SUT version / build | {VERSION_TAG} |
| Primary owner(s) | {TEAM / CONTACT} |
| Last updated | {YYYY-MM-DD} |
| Related roadmap entry | {ID + title} |

**Executive summary:**
- **Mission outcome:** {What success looks like in 1–2 sentences}
- **Primary user personas:** {Operator, customer, partner, etc.}
- **Business impact of failure:** {Downtime, revenue, safety, regulatory}

---

## 2. Architecture & Interfaces

Describe the SUT in layers. Reference diagrams where possible.

### 2.1 High-Level Flow
- {Step 1}
- {Step 2}
- {Step 3}

### 2.2 Interfaces & Protocols
| Interface | Type | Location / URI | Auth | Notes |
|-----------|------|----------------|------|-------|
| {API / UI / Bus} | REST / gRPC / CLI / UI | {https://... / host:port} | {token / basic / keyfile} | {Rate limits, payload caps, retries} |

### 2.3 Dependencies
- **Upstream inputs:** {Queues, event buses, 3rd-party APIs}
- **Downstream outputs:** {Databases, external services, human operators}
- **Tooling contracts:** {LLM providers, feature stores, telemetry sinks}

---

## 3. Environments & Access
| Environment | Purpose | Base URL / Host | Credentials | Feature flags / toggles |
|-------------|---------|-----------------|-------------|-------------------------|
| dev | {Internal testing} | {dev.example.com} | {env ref or vault path} | {e.g., enable_mock_llm=true} |
| staging | {Pre-prod parity} | {staging.example.com} | {...} | {...} |
| prod (read-only) | {Shadow traffic, observability only} | {prod.example.com} | {...} | {...} |

**Access instructions:**
1. `{ssh / vpn / tunnel}`
2. `{export API_KEY=...}`
3. `{opencode login ...}`

**Data sensitivity:** {PII, PHI, PCI, export controls, etc.}

---

## 4. Personas & Workflows
| Persona | Goals | Critical journeys | Failure anxieties |
|---------|-------|-------------------|-------------------|
| {Ops engineer} | {Keep queue < 1s} | {Create ticket → route → resolve} | {Silent drops, SLA breach} |
| {End user} | {...} | {...} | {...} |

---

## 5. Known Risks & Hypotheses

List the active investigation threads.

| ID | Category | Hypothesis / risk statement | Evidence so far | Desired experiment |
|----|----------|----------------------------|-----------------|--------------------|
| RISK-01 | Reliability | {Fan-out deadlocks under >200 TPS} | {Incident #123, telemetry spike} | {Chaos test + watchdog} |
| RISK-02 | Security | {...} | {...} | {...} |

---

## 6. Constraints & Guardrails
- **Regulatory:** {HIPAA, GDPR, FCC, etc.}
- **Safety rules:** {Never mutate prod, read-only datasets, require human approval before actuation}
- **Performance SLOs:** {e.g., P95 latency < 250ms, error rate < 0.1%}
- **Budget limits:** {Daily token spend, API credits}
- **Blacklisted actions:** {No schema migrations, no external webhooks}

---

## 7. Telemetry & Evidence Requirements
| Artifact | Location | Retention | Notes |
|----------|----------|-----------|-------|
| Logs | `runs/{ENTRY}/run-*/results/logs/` | 30 days | Include correlation IDs |
| Metrics | `runs/.../results/metrics/` | 30 days | Capture P50/P95/P99 |
| Traces | `runs/.../results/traces/` | 60 days | Use OpenTelemetry IDs |
| Findings | `findings/{bugs|improvements|strengths}.json` | Permanent | Append via `scripts/add_finding.py` |

---

## 8. Automation Objectives
- **Primary objective:** {e.g., Validate failover under multi-region partition}
- **Secondary objectives:** {DX assessment, performance envelopes, etc.}
- **Exit criteria:** {X critical bugs fixed, Y% coverage, Z successful reruns}
- **Reporting cadence:** {Daily sync, weekly digest}

---

## 9. Reference Assets
- `mission-checklist.md` – canonical backlog
- `config/run_config.json` – machine-readable knobs
- `docs/reference/FINAL_REPORT_TEMPLATE.md` – reporting format
- {Links to design docs, dashboards, past incidents}

---

## 10. Change Log
| Date | Author | Change |
|------|--------|--------|
| {YYYY-MM-DD} | {Name} | {Added new risk thread / updated endpoints} |

> Keep this document terse. If a section becomes verbose, link to a deeper artifact instead of expanding in place.
