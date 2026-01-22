# Developer Experience (DX) Report: 24h-Testers

**Date:** 2026-01-21
**Project:** 24h-testers-playground
**Evaluator:** Cascade

## Executive Summary
The `24h-testers` framework provides a powerful, autonomous loop for reliability testing. By combining a narrative Mission Brief, a structured Checklist, and autonomous agents (OpenCode/Claude), it successfully identified critical bugs, verified fixes, and discovered deeper security vulnerabilities (fuzzing) with minimal human intervention.

However, the "out-of-the-box" experience required significant debugging of the tool itself before it ran smoothly. Critical race conditions in file handling and command-line argument mismatches in the system prompts were major blockers.

## 1. Setup & Configuration
**Rating: 4/5**

*   **Strengths:**
    *   The concept of "Mission Brief" + "Checklist" is intuitive and maps well to how QA engineers think.
    *   Configuration via `run_config.json` is straightforward.
    *   The directory structure is logical (`sut-server`, `scripts`, `findings`).

*   **Friction Points:**
    *   **Dependency Management**: The Python scripts (`add_finding.py`) and Node scripts (`checklist-processor.js`) don't have a unified `package.json` or `requirements.txt` at the root, making setup a bit manual.
    *   **Windows Compatibility**: Some default paths and shell commands (like `rm`, `cp`) in the provided documentation or scripts assume a *nix environment, requiring manual translation to PowerShell.

## 2. Execution & Reliability
**Rating: 2/5 (Initial) -> 4/5 (After Fixes)**

*   **Critical Issues Encountered:**
    1.  **Race Conditions**: The original `checklist-processor.js` attempted to update `mission-checklist.md` concurrently from multiple agent threads without locking. This resulted in corrupted files and lost status updates.
        *   *Fix Applied*: Implemented a mutex/promise chain (`fileLock`) for all file writes.
    2.  **Missing Logic**: The function `generateTierReportsIfNeeded` was called but not defined in the provided script.
        *   *Fix Applied*: Implemented the missing function.
    3.  **Prompt/Script Mismatch**: The `AGENT_SYSTEM_PROMPT.md` instructed agents to use `add_finding.py --payload '...'`, but the Python script expected `--entry`. This caused agents to fail when recording bugs.
        *   *Fix Applied*: Updated the system prompt to match the script's API.
    4.  **File Locking (Windows)**: The processor often failed to restart the SUT because the previous `node.exe` process was still holding onto `server.js`.
        *   *Fix Applied*: Added explicit `Stop-Process` steps in the run loop.

*   **Strengths (Once Fixed):**
    *   **Parallelism**: Running tests in parallel (`--batch-size`) significantly sped up the feedback loop.
    
    *   **Autonomy**: Agents successfully navigated the file system, read code, started servers, and performed HTTP requests without hand-holding.

## 3. Output Quality
**Rating: 5/5**

*   **Findings Ledger**: The JSON-based findings (`bugs.json`, `strengths.json`) are excellent for programmatic consumption.
*   **Agent Intelligence**: The agents (OpenCode/Claude) demonstrated high capability:
    *   Correctly identified "Smoke Test" failures (Auth, ID overwrites).
    *   Verified fixes accurately.
    *   **Fuzzing Success**: In Tier 3, the agent autonomously performed fuzzing and discovered sophisticated issues like **Prototype Pollution** (`SEC-001`) and **Injection-like string acceptance** (`BUG-016`), which were not explicitly scripted but inferred from the "Fuzz" instruction.
    *   **Infinite Mode & Complex Bugs**: Successfully synthesized new scenarios (`REL-001`, `REL-002`) and detected complex architectural flaws:
        *   **Race Conditions**: Identified a TOCTOU vulnerability in transfer logic (`BUG-028`) by autonomously running concurrent requests.
        *   **Idempotency Failures**: Detected double-spending issues (`BUG-027`) despite the presence of idempotency headers.
        *   **Account Enumeration**: Confirmed security leakage via error messages (`SEC-001`).
    *   **Security Hardening**: Successfully verified fixes for critical security issues (XSS, Prototype Pollution) in a final regression run, demonstrating the loop's capability to enforce security baselines.

## 4. Recommendations for Improvement

### A. Infrastructure & Code Quality
1.  **Concurrency Safety**: Permanently patch `checklist-processor.js` with file locking for all shared resources (checklist markdown, findings JSONs).
2.  **Unified CLI**: Create a single entry point (e.g., `npm start` or `python main.py`) that handles environment checks, process cleanup, and tool execution.
3.  **Cross-Platform Support**: Use `path.join` and cross-platform shell libraries (like `shelljs` or `execa`) instead of raw strings to support Windows users better.

### B. Developer Experience
1.  **"Clean" Utility**: Add a command to archive previous runs and reset the checklist. Manually moving JSON files and editing Markdown checkboxes is tedious and error-prone.
2.  **Live Dashboard**: A simple CLI dashboard showing the status of parallel agents (Running/Pass/Fail) would be better than raw log scrolling.

### C. Documentation
1.  **Prompt Versioning**: Ensure the `AGENT_SYSTEM_PROMPT.md` is strictly versioned alongside `add_finding.py` to prevent argument mismatches.

## Conclusion
`24h-testers` is a highly effective tool for autonomous reliability engineering once the initial infrastructure hurdles are overcome. The ability of the agents to autonomously explore, attack (fuzz), and report on the SUT provides immense value, turning a 24-hour manual testing cycle into a ~15-minute autonomous loop.
