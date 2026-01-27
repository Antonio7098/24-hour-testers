# 24h Testers Autonomous Reliability Loop

> **Mission**: Keep an autonomous finding loop running. Feed it a mission packet and a checklist, then let Stageflow agents execute forever with zero babysitting.

---

## Overview

24h Testers now runs on a **Python 3.11 Stageflow** pipeline (see the `processor/` package). The Stageflow DAG powers finite and infinite modes, backlog synthesis, tier reports, structured retries, and a modern CLI—delivering the same autonomous reliability loop with deeper observability and fail-fast behavior.

You supply two canonical inputs:

1. **SUT Packet (`SUT-PACKET.md`)** – mission context, interfaces, constraints, datasets, personas.
2. **Checklist (`SUT-CHECKLIST.md`)** – tiered backlog where agents record ✅/☐ progress.

The Stageflow pipeline continuously:

1. Parses the mission brief + backlog.
2. Builds prompts per checklist item.
3. Spawns OpenCode or Claude Code agents (`opencode run --model …` / `claude code …`).
4. Validates completion markers and final reports.
5. Writes back status to the checklist.
6. Generates stakeholder-ready tier summaries once an entire tier is ✅.
7. In **infinite mode**, fills the backlog by asking an LLM to synthesize new rows.

State persists under `.processor/`; per-item artifacts live in `runs/<tier>/<item-id>/`.

---

## Quick Start

### 1. Prepare Inputs

| File / Input | Purpose |
|--------------|---------|
| `SUT-PACKET.md` | Narrative mission brief (architecture, risks, endpoints, personas, SLAs). |
| `SUT-CHECKLIST.md` | Canonical backlog grouped by tiers. The processor edits this file in place. |
| `config/run_config.json` | Machine-parsable knobs used by prompts (SUT name, credential keys, datasets, success criteria). |
| Secrets / `.env` / Vault | Tokens referenced by `run_config.json`. Ensure binaries can read them non-interactively. |

### 2. Configure Agent Permissions

The processor **does not** inject permission flags. Configure your binaries up-front:

- **OpenCode** – enable `bypassPermissions` (or equivalent) in your profile; override `OPENCODE_BIN` if you need a wrapper.
- **Claude Code** – ensure `claude code` always runs with `--dangerously-skip-permissions`; wrap it if necessary and point `CLAUDE_CODE_BIN` to the wrapper.

### 3. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r processor/requirements.txt
```

### 4. Run the Stageflow Processor

#### CLI entry point

```bash
# Infinite mode with OpenCode + Minimax M2.1
python -m processor.cli run \
  --checklist SUT-CHECKLIST.md \
  --mission-brief SUT-PACKET.md \
  --mode infinite \
  --batch-size 5 \
  --runtime opencode \
  --model minimax-coding-plan/MiniMax-M2.1
```

Additional examples:

```bash
# Finite mode, 3-at-a-time, Claude Code runtime
python -m processor.cli run \
  --batch-size 3 \
  --mode finite \
  --runtime claude-code \
  --model anthropic/claude-3-5-sonnet-20241022

# Dry run to see which rows would be processed
python -m processor.cli run --dry-run

# Resume using a custom checklist + mission brief
python -m processor.cli run \
  --checklist ./custom/checklist.md \
  --mission-brief ./custom/packet.md \
  --resume

# Increase timeout and enable verbose logging
python -m processor.cli run \
  --timeout 600000 \
  --verbose

# Watch live progress (auto-refreshing status)
python -m processor.cli run --watch
```

Key subcommands:

| Command | Description |
|---------|-------------|
| `python -m processor.cli run [flags]` | Execute the Stageflow DAG (finite/infinite). |
| `python -m processor.cli status` | Show active session from `.processor/active-runs.json`. |
| `python -m processor.cli history` | List historical sessions stored under `.processor/`. |
| `python -m processor.cli dashboard` | Tier-level summary + backlog snapshot. |
| `python -m processor.cli cancel` | Cancel all active agent subprocesses.

Pass `--verbose` for Stageflow debug logs; combine `--dry-run` with other flags to preview a batch.

---

## Configuration & Flags

### ProcessorConfig defaults

- `runtime`: `opencode`
- `model`: `minimax-coding-plan/MiniMax-M2.1`
- `batch_size`: `5`
- `mode`: `finite`
- `timeout_ms`: `300000`
- `state_dir`: `.processor`
- `runs_dir`: `runs/`

CLI flags override these defaults:

| Flag | Description |
|------|-------------|
| `--batch-size N` | Number of checklist rows processed in parallel. |
| `--mode {finite,infinite}` | Stop at ✅ or keep synthesizing backlog. |
| `--runtime {opencode,claude-code}` | Agent runtime. |
| `--model SLUG` | Model slug for the runtime. |
| `--timeout MS` | Agent execution timeout. |
| `--dry-run` | Build prompts but skip agent subprocesses. |
| `--checklist PATH` / `--mission-brief PATH` | Custom file locations. |
| `--verbose` | Emit Stageflow debug logs. |

Environment helpers:

```bash
export AGENT_RUNTIME=claude-code
export AGENT_MODEL=claude-3-5-sonnet-20241022
export OPENCODE_BIN=/usr/local/bin/opencode
export CLAUDE_CODE_BIN=/usr/local/bin/claude
```

---

## Pipeline Architecture (processor/processor.py)

1. **ParseChecklistStage** – loads markdown, builds tier map, selects remaining rows.
2. **BuildPromptStage** – injects mission brief + item metadata into `AGENT_SYSTEM_PROMPT`.
3. **RunAgentStage** – runs `opencode run --model …` (or Claude) via asyncio, capturing stdout/stderr, enforcing timeouts, and writing logs under `runs/<tier>/<item>/results/`.
4. **ValidateOutputStage** – checks completion markers + final reports.
5. **UpdateStatusStage** – writes ✅/❌ back to the checklist via `ChecklistParser`.

Additional tasks:

- **GenerateTierReportStage** – when every item in a tier is ✅, crafts a prompt from `agent-resources/prompts/TIER_REPORT_PROMPT.md`, invokes the agent, cleans output, and writes `runs/<tier>/<tier>-FINAL-REPORT.md`.
- **Backlog Synthesis** – `_extend_checklist_if_needed` runs in infinite mode. It reads `INFINITE_BACKLOG_PROMPT.md`, collects JSON, coerces it into `ChecklistItem` entries, appends them to `SUT-CHECKLIST.md`, and logs synthesis output under `.processor/synthesis/`.

---

## Directory Layout

```
24h-testers/
├── agent-resources/
│   ├── prompts/                 # AGENT_SYSTEM_PROMPT, INFINITE_BACKLOG_PROMPT, TIER_REPORT_PROMPT
│   └── templates/               # FINAL_REPORT_TEMPLATE, PR template, etc.
├── config/run_config.json       # Structured SUT config consumed by prompts
├── processor/                   # Stageflow CLI, stages, interceptors, utils
├── runs/                        # Created at runtime (per-tier artifacts)
├── .processor/                  # Session state (created at runtime)
├── SUT-PACKET.md
├── SUT-CHECKLIST.md
└── README.md
```

---

## Key Prompts & Templates

| File | Purpose |
|------|---------|
| `agent-resources/prompts/AGENT_SYSTEM_PROMPT.md` | Primary instructions per checklist item. |
| `agent-resources/prompts/INFINITE_BACKLOG_PROMPT.md` | JSON spec for backlog synthesis. |
| `agent-resources/prompts/TIER_REPORT_PROMPT.md` | Tier aggregation instructions. |
| `agent-resources/templates/FINAL_REPORT_TEMPLATE.md` | Markdown scaffold for per-item final reports. |

---

## Required `run_config.json` Fields

| Field | Description |
|-------|-------------|
| `sut_name` / `sut_version` | Human-readable identifier + build/tag. |
| `access.instructions` | Connectivity steps (VPN, jump host, SSH, tunnels). |
| `access.credentials_key` | Secret name or env key used by agents. |
| `datasets` | Happy-path, adversarial, compliance dataset references. |
| `environments` | Target base URLs, feature flags, staging/prod info. |
| `success_criteria` | Quantitative gates (latency, error rate, coverage thresholds). |

Missing keys halt the run with a descriptive error before any agents start.

---

## Infinite Mode Tips

1. Keep tier headings consistent (`## Tier 1: …`). The parser uses them for routing.
2. The synthesis agent must emit valid JSON. `_extract_json_payload` strips code fences and ANSI sequences, but malformed payloads are discarded.
3. Backlog items can introduce new tiers; `ChecklistParser` will append new tables automatically.

---

## Tier Reports

- Trigger: Entire tier reaches ✅.
- Prompt: `agent-resources/prompts/TIER_REPORT_PROMPT.md`.
- Output: `runs/<sanitized-tier>/<sanitized-tier>-FINAL-REPORT.md`.
- Sections: Executive summary, key findings table, risks/gaps, evidence, next steps.

---

## Observability & State

- **RunManager** stores session metadata in `.processor/active-runs.json` + `session-*.json` files.
- **Agent logs** are written to `runs/<tier>/<item>/results/agent-*.log`.
- **Synthesis logs** (optional) land in `.processor/synthesis/synthesis-*.log`.
- Use `python -m processor.cli status --verbose` to inspect active sessions.

---

## Development & Testing

- Run the full suite: `pytest processor/tests -v`
- Use `--dry-run` when iterating on prompts or checklist parsing.
- Inspect `runs/` artifacts to verify final reports and logs.

---

## Contributing Workflow

1. Update `SUT-PACKET.md`, `SUT-CHECKLIST.md`, and `config/run_config.json` for the target SUT.
2. Verify OpenCode/Claude binaries run non-interactively.
3. Create a virtualenv and install `processor/requirements.txt`.
4. Exercise the CLI (finite + infinite). Capture logs and tier reports as needed.
5. Run `pytest`.
6. Commit artifacts + findings, then open a PR summarizing results.

Keep the loop structure intact; swap in your own packets/checklists/builders as needed.

---

## Design Principles

1. **Fail Fast** – strict validation of prompts, checklist edits, and agent exit codes.
2. **Observable** – structured logging, per-stage telemetry, and durable state files.
3. **Deterministic** – checklist parser enforces consistent markdown; tier reports only emit when appropriate.
4. **Extensible** – new stages/runtimes can be plugged in without touching the DAG core.

---

## Need Help?

- Inspect `runs/<tier>/<item>/results/agent-*.log` for raw subprocess output.
- Tail Stageflow logs with `python -m processor.cli run … --verbose`.
- Customize prompts in `agent-resources/prompts/` to change agent behavior.

Happy automating! 🚀
