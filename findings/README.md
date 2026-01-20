# Shared Findings Workspace

This folder holds the canonical JSON ledgers that agents append to using `scripts/add_finding.py`.

## Files

| File | Purpose |
|------|---------|
| `findings.json` | Master ledger of every finding type for the current mission. |
| `bugs.json` | Only defect-level findings. |
| `strengths.json` | Positive signals, reusable patterns, and operational wins. |
| `dx.json` | Developer-experience friction (docs, onboarding, tooling gaps). |
| `improvements.json` | Enhancements, polish items, or roadmap ideas. |

Each file ships with:
- `metadata` block – replace placeholders with the current mission/run identifiers.
- Empty `items`/`findings` array that agents append to.

## Usage

1. Update metadata placeholders once per run (ENTRY_ID, RUN_ID, agent model, etc.).
2. Call:
   ```bash
   python scripts/add_finding.py \
     --type bug \
     --entry '{"title":"Race condition","severity":"critical"}' \
     --agent claude-3.5-sonnet \
     --file-path findings/bugs.json
   ```
3. Commit the updated JSON files alongside the run artifacts.

> Tip: you can keep `findings/findings.json` as the master ledger while copying the specialized files (`bugs.json`, `dx.json`, etc.) into `runs/<ENTRY>/run-*/` when a run needs local state.
