#!/usr/bin/env bash
# Parallel Checklist Processor Runner (Unix shells)

set -euo pipefail

echo "🚀 Starting Parallel Checklist Processor..."

BATCH_SIZE=${BATCH_SIZE:-5}
AGENT_RUNTIME=${AGENT_RUNTIME:-opencode}

echo "This will process mission-checklist.md using ${BATCH_SIZE} parallel ${AGENT_RUNTIME} subagents"
echo "(override with --batch-size, BATCH_SIZE, --runtime, or AGENT_RUNTIME)"
echo ""

# Check if checklist file exists
if [ ! -f "mission-checklist.md" ]; then
    echo "❌ Error: mission-checklist.md not found"
    exit 1
fi

# Warn if mission brief missing (agents fall back to README)
if [ ! -f "mission-brief.md" ]; then
    echo "⚠️  mission-brief.md not found. Agents will fall back to README.md"
fi

runtime_command_var="OPENCODE_BIN"
runtime_command_default="opencode"

if [ "$AGENT_RUNTIME" = "claude-code" ]; then
    runtime_command_var="CLAUDE_CODE_BIN"
    runtime_command_default="claude"
fi

runtime_command=${!runtime_command_var:-$runtime_command_default}

if ! command -v "$runtime_command" &> /dev/null; then
    echo "❌ Error: $runtime_command (runtime: $AGENT_RUNTIME) not found in PATH"
    echo "Set $runtime_command_var to the absolute path if it's installed elsewhere."
    exit 1
fi

export AGENT_RUNTIME

# Run the processor
node checklist-processor.js "$@"