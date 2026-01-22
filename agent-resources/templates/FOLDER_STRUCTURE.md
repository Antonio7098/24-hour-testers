# 24h Testers Folder Structure

> **Purpose**: Standardized folder structure for each agent run targeting a roadmap entry.

---

## Root Structure

```
24h-testers/
├── SUT-PACKET.md               # SUT packet / dossier
├── SUT-CHECKLIST.md           # Canonical backlog processed by automation
├── agent-resources/
│   ├── prompts/AGENT_SYSTEM_PROMPT.md
│   └── templates/
│       ├── FOLDER_STRUCTURE.md
│       └── FINAL_REPORT_TEMPLATE.md
├── scripts/                      # checklist-processor, etc.
├── tests/                        # Shared harnesses/fixtures
├── runs/                         # All agent runs organized by Tier and ID
│   ├── tier_1_research_compliance/
│   │   ├── RES-001/              # Individual Item Run
│   │   │   ├── FINAL_REPORT.md   # Report with embedded findings
│   │   │   ├── research/
│   │   │   ├── mocks/
│   │   │   ├── tests/
│   │   │   └── results/
│   │   └── tier_1_research_compliance-FINAL-REPORT.md # Aggregated Tier Report
│   └── ...
└── README.md
```

---

## Individual Run Structure

Each run folder (`runs/{TIER_NAME}/{ENTRY_ID}/`) follows this exact structure:

```
runs/{TIER_NAME}/{ENTRY_ID}/
│
├── FINAL_REPORT.md              # Human-readable final report (required)
│                                # *Contains Finding details and recommendations*
│
├── research/                     # Phase 1: Research outputs
│   ├── summary.md               # Research summary
│   └── ...
│
├── mocks/                        # Phase 2: Environment simulation
│   └── ...
│
├── tests/                        # Phase 3: Test execution harnesses
│   └── ...
│
├── results/                      # Phase 4: Test results
│   ├── agent-log.txt            # Raw agent execution log
│   ├── logs/                    # Execution logs
│   └── ...
```

---

## File Specifications

### `FINAL_REPORT.md`

Instead of separate JSON ledgers, the Final Report is the source of truth.

```markdown
# {ENTRY_ID}: {ENTRY_TITLE}

**Status**: {PASS|FAIL|WARNING}
**Date**: {ISO_TIMESTAMP}

## Executive Summary
{One paragraph summary}

## Findings

### BUG-001: {Title}
- **Severity**: {Critical|High|Medium|Low}
- **Description**: ...
- **Reproduction**: ...
- **Evidence**: [Link to log](results/logs/run.log)

### SEC-001: {Title}
...

## Research & Context
...
```

---

## Naming Conventions

### Tier Folders
Derived from checklist headers (sanitized):
- `## Tier 1: Research & Compliance` -> `tier_1_research_compliance`
- `## Tier 2: Security Testing` -> `tier_2_security_testing`

### Run Folders
Matches the Checklist ID:
- `RES-001`
- `SMK-002`
- `INF-123`

---

## Required vs Optional Files

### Required (every run must have)
- `FINAL_REPORT.md`
- `results/agent-log.txt`

### Required if applicable
- `research/` - Always required for first run of an entry
- `mocks/` - Required if custom mocks or fixtures were created
- `tests/` - Required if automated harnesses were written


---

## Git Ignore Patterns

Add to `.gitignore`:

```gitignore
# Large generated files
runs/*/results/logs/*.log
runs/*/mocks/data/scale/*.json

# Temporary files
runs/*/.pytest_cache/
runs/*/__pycache__/

# Sensitive data (if any)
runs/*/mocks/data/**/sensitive_*
```

---

## Archival Policy

- **Active runs**: Keep in `runs/` folder
- **After 90 days**: Compress to `runs/{ENTRY_ID}/archive/`
- **Keep forever**: `FINAL_REPORT.md`, `config/`
- **Can delete**: `results/logs/`, large mock data files
