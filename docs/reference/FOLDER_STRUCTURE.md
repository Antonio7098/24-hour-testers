# the the system Stress-Testing Folder Structure

> **Purpose**: Standardized folder structure for each agent run targeting a roadmap entry.

---

## Root Structure

```
24h-testers/
├── mission-brief.md              # Canonical SUT context packet
├── scenario-checklist.md         # Only backlog processed by automation
├── docs/
│   ├── prompts/AGENT_SYSTEM_PROMPT.md
│   └── reference/
│       ├── FOLDER_STRUCTURE.md
│       └── FINAL_REPORT_TEMPLATE.md
├── findings/
│   ├── bugs.json
│   ├── strengths.json
│   └── improvements.json         # Canonical ledgers (append-only)
├── scripts/                      # checklist-processor, add_finding, etc.
├── tests/                        # Shared harnesses/fixtures
├── runs/                         # All agent runs organized by roadmap entry
│   ├── CORE-001/
│   │   ├── run-2026-01-14-001/
│   │   ├── run-2026-01-15-001/
│   │   └── ...
│   ├── FIN-001/
│   └── ...
└── aggregated_findings.json      # Optional cross-ledger export
```

---

## Individual Run Structure

Each run folder follows this exact structure:

```
runs/{ROADMAP_ENTRY_ID}/run-{DATE}-{SEQ}/
│
├── README.md                     # Run overview and quick reference
├── findings/
│   ├── bugs.json                # Defects recorded via add_finding.py
│   ├── strengths.json           # Positive signals
│   └── improvements.json        # Enhancements / roadmap ideas
├── FINAL_REPORT.md              # Human-readable final report (required)
│
├── research/                     # Phase 1: Research outputs
│   ├── web_search_results.md    # Raw web search findings
│   ├── industry_context.md      # Industry-specific research
│   ├── technical_context.md     # Technical research
│   ├── hypotheses.md            # Hypotheses to test
│   └── citations.json           # Structured citations
│
├── mocks/                        # Phase 2: Environment simulation
│   ├── data/                    # Mock data files
│   │   ├── happy_path/          # Normal, expected inputs
│   │   ├── edge_cases/          # Boundary conditions
│   │   ├── adversarial/         # Malicious/malformed inputs
│   │   └── scale/               # High-volume test data
│   ├── services/                # Mock service implementations
│   │   ├── __init__.py
│   │   ├── mock_llm.py          # Deterministic LLM responses
│   │   ├── mock_db.py           # Database mocks
│   │   ├── mock_api.py          # External API mocks
│   │   └── mock_infra.py        # Infrastructure mocks
│   └── fixtures/                # Pytest fixtures
│       └── conftest.py
│
├── tests/                        # Phase 3: Test execution harnesses
│   ├── __init__.py
│   ├── conftest.py              # Test configuration
│   ├── test_correctness.py      # Correctness tests
│   ├── test_reliability.py      # Reliability tests
│   ├── test_performance.py      # Performance tests
│   ├── test_security.py         # Security tests
│   ├── test_scalability.py      # Scalability tests
│   └── test_observability.py    # Observability tests
│
├── results/                      # Phase 4: Test results
│   ├── metrics/                 # Performance metrics
│   │   ├── latency.json
│   │   ├── throughput.json
│   │   └── resource_usage.json
│   ├── traces/                  # Execution traces
│   │   └── trace_*.json
│   ├── logs/                    # Execution logs
│   │   └── run_*.log
│   └── screenshots/             # Visual evidence (if applicable)
│
├── dx_evaluation/                # Phase 5: DX evaluation
│   ├── scores.json              # DX scores by category
│   ├── friction_points.md       # Documented pain points
│   └── suggestions.md           # Improvement suggestions
│
└── config/                       # Run configuration
    ├── run_config.json          # Run parameters
    └── environment.json         # Environment details
```

---

## File Specifications

### `README.md`

```markdown
# {ROADMAP_ENTRY_ID}: {ENTRY_TITLE}

**Run ID**: run-{DATE}-{SEQ}  
**Status**: {in_progress|completed|failed|blocked}  
**Started**: {ISO_TIMESTAMP}  
**Completed**: {ISO_TIMESTAMP}  

## Quick Summary

{One paragraph summary of findings}

## Key Findings

- {Critical finding 1}
- {High finding 2}
- ...

## Files

- `findings.json` - {N} findings logged
- `FINAL_REPORT.md` - Detailed analysis

## How to Reproduce

```bash
cd runs/{ROADMAP_ENTRY_ID}/run-{DATE}-{SEQ}
pip install -r requirements.txt
pytest tests/ -v
```
```

### `config/run_config.json`

```json
{
  "roadmap_entry_id": "FIN-001",
  "roadmap_entry_title": "High-frequency fraud detection (5000 TPS)",
  "priority": "P0",
  "risk_class": "Catastrophic",
  "industry": "Finance",
  "deployment_mode": "Active-Active",
  "run_id": "run-2026-01-14-001",
  "started_at": "2026-01-14T09:00:00Z",
  "agent_model": "claude-3.5-sonnet",
  "the the system_version": "0.5.0",
  "test_parameters": {
    "concurrency_level": 100,
    "duration_seconds": 300,
    "data_volume": "10000_records"
  }
}
```

### `config/environment.json`

```json
{
  "python_version": "3.11.5",
  "os": "Linux 6.1.0",
  "cpu": "AMD EPYC 7763 64-Core",
  "memory_gb": 128,
  "gpu": "NVIDIA A100 40GB",
  "dependencies": {
    "the the system": "0.5.0",
    "pydantic": "2.5.0",
    "pytest": "7.4.0",
    "httpx": "0.25.0"
  }
}
```

### `dx_evaluation/scores.json`

```json
{
  "overall_score": 3.8,
  "categories": {
    "discoverability": {
      "score": 4,
      "notes": "APIs were easy to find in documentation"
    },
    "clarity": {
      "score": 4,
      "notes": "Stage definitions are intuitive"
    },
    "documentation": {
      "score": 3,
      "notes": "Missing examples for parallel fan-out"
    },
    "error_messages": {
      "score": 2,
      "notes": "Errors don't indicate which parallel stage failed"
    },
    "debugging": {
      "score": 4,
      "notes": "Tracing is comprehensive"
    },
    "boilerplate": {
      "score": 4,
      "notes": "Minimal boilerplate required"
    },
    "flexibility": {
      "score": 5,
      "notes": "Interceptors allow full customization"
    },
    "performance": {
      "score": 3,
      "notes": "Serialization overhead noticeable at scale"
    }
  },
  "time_to_first_pipeline_minutes": 15,
  "time_to_understand_error_minutes": 45,
  "documentation_gaps": [
    "Parallel execution patterns",
    "Error handling in fan-out"
  ]
}
```

---

## Naming Conventions

### Run Folders
```
run-{YYYY}-{MM}-{DD}-{SEQ}
```
- `SEQ` is a 3-digit sequence number (001, 002, etc.)
- Example: `run-2026-01-14-001`

### Finding IDs
```
{ROADMAP_ENTRY_ID}-{TYPE}-{SEQ}
```
- `TYPE`: BUG, SEC, PERF, REL, DX, IMP, DOC, FEAT
- Example: `FIN-001-BUG-001`

### Mock Data Files
```
{scenario}_{variant}_{size}.{ext}
```
- Example: `transactions_valid_10k.json`
- Example: `transactions_malformed_100.json`

### Test Files
```
test_{category}.py
```
- Categories: correctness, reliability, performance, security, scalability, observability

### Trace Files
```
trace_{timestamp}_{scenario}.json
```
- Example: `trace_20260114_093045_stress.json`

---

## Required vs Optional Files

### Required (every run must have)
- `README.md`
- `findings.json`
- `FINAL_REPORT.md`
- `config/run_config.json`
- `config/environment.json`

### Required if applicable
- `research/` - Always required for first run of an entry
- `mocks/` - Required if custom mocks or fixtures were created
- `tests/` - Required if automated harnesses were written
- `results/` - Required if tests were executed
- `dx_evaluation/` - Required for all runs

### Optional
- `screenshots/` - Only if visual evidence needed
- Additional documentation files

---

## Git Ignore Patterns

Add to `.gitignore`:

```gitignore
# Large generated files
production-testers/runs/*/results/logs/*.log
production-testers/runs/*/mocks/data/scale/*.json

# Temporary files
production-testers/runs/*/.pytest_cache/
production-testers/runs/*/__pycache__/

# Sensitive data (if any)
production-testers/runs/*/mocks/data/**/sensitive_*
```

---

## Archival Policy

- **Active runs**: Keep in `runs/` folder
- **After 90 days**: Compress to `runs/{ENTRY_ID}/archive/`
- **Keep forever**: `findings.json`, `FINAL_REPORT.md`, `config/`
- **Can delete**: `results/logs/`, large mock data files
