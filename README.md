# 24h Testers Autonomous Reliability Loop

> **Mission**: Keep an autonomous finding loop running. Describe the system under test (SUT), hand the loop a checklist, and let agents execute forever with zero manual babysitting.

---

## Overview

24h Testers is an autonomous reliability harness. You supply **one SUT packet** (what to test, how to reach it, which credentials + datasets to use) and **one canonical checklist**. The loop continuously:

1. Reads the packet + checklist context.
2. Picks unfinished checklist rows.
3. Spawns autonomous OpenCode or Claude Code agents to research, simulate, build, and test.
4. Writes structured findings and reports.
5. Synthesizes fresh backlog when existing work is exhausted (infinite mode).

No manual step is required beyond updating config/checklist inputs.

---

## Quick Start: Running the Loop

### 1. Describe the SUT Packet

Populate the following before starting automation:

| File / Input | Purpose |
|--------------|---------|
| `mission-brief.md` | Narrative SUT packet: mission, personas, system boundaries, high-risk areas, known integrations. Include live endpoints, ports, and rate limits. |
| `config/run_config.json` | Machine-friendly knobs referenced by the SUT packet (SUT name/version, credentials key, datasets, stress parameters, success criteria). |
| `.env` / secrets manager | Authentication material the agent needs (API keys, SSH tunnels, dataset URLs). Reference these names in `run_config.json`. |
| `mission-checklist.md` | Canonical backlog of everything to test. Update priorities/risks and mark ✅/☐ as automation progresses. |

The loop will refuse to run if required keys are missing in `run_config.json` (see "Required SUT Inputs" below).

### 2. Configure Agent Permissions (Crucial)

For the autonomous loop to run without manual intervention, the binaries that the checklist processor launches must already bypass permission prompts. The processor simply shells out to whatever command is resolved via `AGENT_RUNTIME`, `CLAUDE_CODE_BIN`, or `OPENCODE_BIN`; it does **not** inject flags on your behalf. Make sure the binary you expose to the processor already runs in "auto-approve" mode.

**Claude Code**:
- Configure the runtime (settings file or CLI alias) so the `code` subcommand always includes `--dangerously-skip-permissions`.
- If you cannot change global settings, point `CLAUDE_CODE_BIN` at a tiny wrapper script:
  ```bash
  # claude-auto.sh
  exec claude code --dangerously-skip-permissions "$@"
  ```
  ```bash
  export CLAUDE_CODE_BIN="$(pwd)/claude-auto.sh"
  ```

**OpenCode**:
- Enable `bypassPermissions` (or the equivalent flag) in your user config so the automation can write files and run commands without prompting.
- Override `OPENCODE_BIN` if you need to point at a wrapper that enforces those flags.

### 3. Scaffold or Reuse a Run Directory

```bash
ENTRY_ID="CORE-001"
RUN_DATE=$(date +%Y-%m-%d)
RUN_SEQ="001"
RUN_DIR="runs/${ENTRY_ID}/run-${RUN_DATE}-${RUN_SEQ}"

mkdir -p "${RUN_DIR}"/{research,mocks/data/{happy_path,edge_cases,adversarial,scale},mocks/services,mocks/fixtures,tests,results/{metrics,traces,logs},dx_evaluation,config}
```

### 4. Launch the Automated Loop

#### Option A – Unified CLI (recommended)

```bash
npm run start -- --batch-size 5 --mode infinite \
  --checklist mission-checklist.md --mission-brief mission-brief.md
```

#### Option B – Direct script invocation

```
# Windows (PowerShell)
pwsh scripts/run-checklist.ps1 --batch-size 5 --mode infinite \
  --checklist mission-checklist.md --mission-brief mission-brief.md

# macOS / Linux
bash scripts/run-checklist.sh --batch-size 5 --mode infinite \
  --checklist mission-checklist.md --mission-brief mission-brief.md
```

### Unified CLI capabilities

| Command | Description |
|---------|-------------|
| `npm run start -- [flags]` | Pass-through runner for `checklist-processor.js` with consistent env setup. |
| `npm run status` | Calls `--status` and prints agent/session progress. |
| `npm run dashboard` | Renders tier-level breakdowns plus active-session metadata. |
| `npm run clean:dry` | Shows what would be archived/reset without touching files. |
| `npm run clean` | Archives `runs/` + `tier-reports/`, resets checklist rows to ☐ Not Started, and wipes `.checklist-processor/` state. |

The CLI lives in `scripts/24h-cli.js` so the same workflow works on Windows, macOS, and Linux without PowerShell/Bash conditionals.

### Runtime + Model Selection

The processor can target multiple agent runtimes. Configure them via flags or env vars:

| Runtime | Flag value | Default model | Override env vars |
|---------|------------|---------------|-------------------|
| OpenCode | `--runtime opencode` | `opencode/minimax-m2.1-free` | `OPENCODE_BIN`, `OPENCODE_MODEL` |
| Claude Code | `--runtime claude-code` | `claude-4.5-sonnet` | `CLAUDE_CODE_BIN`, `CLAUDE_CODE_MODEL` |

- `--model <slug>` or `AGENT_MODEL` forces a model regardless of runtime defaults.
- Platform runners automatically export `AGENT_RUNTIME` based on `--runtime` / `AGENT_RUNTIME` to keep scripts portable.

In infinite mode the processor monitors how many unfinished checklist rows remain. Whenever the remaining pool drops below the configured `--batch-size`, it automatically:

1. Reads the SUT packet (`mission-brief.md`) plus the current contents of `mission-checklist.md`.
2. Prompts the synthesis agent (see `agent-resources/prompts/INFINITE_BACKLOG_PROMPT.md`) to generate just enough tier-appropriate rows to refill the batch.
3. Inserts those rows back into the matching tier tables of the checklist before continuing.

Finite mode still stops when every row is ✅; infinite mode keeps the pipeline full forever.

### Directory Layout (Conceptual)

```
24h-testers/
├── agent-resources/
│   ├── prompts/                  # System prompts for agents (e.g. infinite backlog, tier reports)
│   └── templates/                # Document templates (e.g. Final Report)
├── mission-brief.md              # SUT packet / dossier
├── mission-checklist.md          # Canonical backlog
├── scripts/                      # Automation utilities (e.g., checklist processor)
├── tests/                        # Harness + fixtures reused across runs
└── runs/ENTRY/run-YYYY-MM-DD-NN  # Per-run artifacts emitted by automation
```

---

## Key References

| File | Purpose |
|------|---------|
| `mission-brief.md` | SUT packet consumed by every agent |
| `mission-checklist.md` | **Only** backlog file processed by automation |
| `config/run_config.json` | Structured inputs (access, datasets, experiment knobs) |
| `agent-resources/prompts/AGENT_SYSTEM_PROMPT.md` | Canonical instructions for autonomous agents |
| `agent-resources/prompts/INFINITE_BACKLOG_PROMPT.md` | Template used when synthesizing new backlog rows in infinite mode |
| `agent-resources/prompts/TIER_REPORT_PROMPT.md` | Prompt used when a tier completes to synthesize stakeholder reports |
| `agent-resources/templates/FINAL_REPORT_TEMPLATE.md` | Markdown template for final reports |

---

## Required SUT Inputs

`config/run_config.json` must include at least:

| Field | Description |
|-------|-------------|
| `sut_name` / `sut_version` | Human-readable identifier + commit/tag under test. |
| `access.instructions` | Plain-language steps for bootstrapping connectivity (e.g., SSH jump host, tunnel commands, VPN, package installation). |
| `access.credentials_key` | Name of the secret (ENV or vault path) that stores auth tokens. |
| `datasets` | Paths or URLs for happy-path, adversarial, scale, and compliance datasets. |
| `environments` | Targets (dev/staging/prod), including base URLs and feature flags. |
| `success_criteria` | Quantitative targets the agent should treat as pass/fail gates. |

Agents merge this with `mission-brief.md` to render prompts. Missing information halts the loop so misconfigured runs fail fast.

---

## Severity Levels

| Severity | Description | Response Target |
|----------|-------------|-----------------|
| `critical` | Outage, irreversible impact | Immediate mitigation |
| `high` | Major functionality broken, no workaround | < 1 week |
| `medium` | Partial impairment with workaround | < 1 month |
| `low` | Minor or cosmetic | Backlog |
| `info` | Observation / suggestion | Optional |

---

## Agent Operating Principles

**Do**

- Research before touching code.
- Start with minimal reproductions, then scale up.
- Capture logs, metrics, and traces for every experiment.
- Think adversarially and hunt for silent failures.
- Document DX friction honestly.

**Avoid**

- Skipping context gathering.
- Writing unverified or uninstrumented code.
- Assuming behavior without evidence.
- Letting artifacts drift from the shared folder structure.

---

## Automation: Checklist Processor

`scripts/checklist-processor.js` is the only orchestrator you run. It streams new checklist rows into OpenCode sessions while persisting checkpoints.

- **Finite mode** – stop when all rows in `mission-checklist.md` are ✅.
- **Infinite mode** – whenever the number of unfinished rows dips below the batch size, the processor invokes the backlog synthesis agent (feeding it `mission-brief.md` + the existing checklist) to append enough tier-matched rows to restore a full batch.

### Tier-Level Reports (Automatic)

- After every batch, the processor checks whether an entire tier has reached ✅ status. When it has, `generateTierReportsIfNeeded` stitches together the individual run reports stored under `runs/<tier>/<ID>/` and writes an aggregated summary to `runs/<tier>/<tier>-FINAL-REPORT.md`.
- The template for these summaries lives in `agent-resources/prompts/TIER_REPORT_PROMPT.md`. Customize that file if you want different output, but no manual invocation is required—the aggregation happens automatically as soon as a tier finishes.

Helpful flags:

```
node scripts/checklist-processor.js --dry-run
node scripts/checklist-processor.js --batch-size 3
node scripts/checklist-processor.js --max-iterations 30
node scripts/checklist-processor.js --runtime claude-code
node scripts/checklist-processor.js --model claude-4.5-sonnet
node scripts/checklist-processor.js --resume
node scripts/checklist-processor.js --status
```

State is persisted under `.checklist-processor/`. Always version-control `mission-checklist.md` (or your chosen checklist) to audit automated edits.

---

## Design Principles

1. **Lean** – Focus on high-signal experiments and automation.
2. **Portable** – Avoid assumptions about the underlying SUT.
3. **Observable** – Every run should emit actionable telemetry.
4. **Actionable** – Findings must map to concrete recommendations.

---

## Contributing Workflow

1. Update `mission-brief.md`, `config/run_config.json`, and `mission-checklist.md` to describe the new SUT.
2. Open secrets/credential PRs or ops requests needed for the agent to reach the SUT.
3. Run `scripts/checklist-processor.js` (finite or infinite) and let it loop.
4. Commit artifacts + findings.
5. Submit a PR summarizing changes + notable findings.

If you fork this lab for a product, keep the loop structure intact—only swap the inputs.
