param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ChecklistArgs
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $PSCommandPath
$repoRoot = Split-Path -Parent $scriptRoot

if (-not (Test-Path $repoRoot)) {
    Write-Error "Unable to determine repository root from script location."
    exit 1
}

Push-Location $repoRoot
try {
    Write-Host "🚀 Starting Parallel Checklist Processor..."

    $batchSize = if ($env:BATCH_SIZE) { $env:BATCH_SIZE } else { 5 }
    $agentRuntime = if ($env:AGENT_RUNTIME) { $env:AGENT_RUNTIME.ToLowerInvariant() } else { "opencode" }

    Write-Host "Processing mission-checklist.md with $batchSize parallel $agentRuntime subagents"
    Write-Host "(override with --batch-size, BATCH_SIZE, --runtime, or AGENT_RUNTIME)"
    Write-Host ""

    $checklistPath = Join-Path $repoRoot "mission-checklist.md"
    if (-not (Test-Path $checklistPath)) {
        Write-Error "❌ mission-checklist.md not found at $checklistPath"
        exit 1
    }

    $missionBriefPath = Join-Path $repoRoot "mission-brief.md"
    if (-not (Test-Path $missionBriefPath)) {
        Write-Warning "⚠️ mission-brief.md not found. Agents will fall back to README.md"
    }

    $runtimeCommandVar = "OPENCODE_BIN"
    $runtimeCommandDefault = "opencode"

    if ($agentRuntime -eq "claude-code") {
        $runtimeCommandVar = "CLAUDE_CODE_BIN"
        $runtimeCommandDefault = "claude"
    }

    $runtimeCommand = if ($env:$runtimeCommandVar) { $env:$runtimeCommandVar } else { $runtimeCommandDefault }

    if (-not (Get-Command $runtimeCommand -ErrorAction SilentlyContinue)) {
        Write-Error "❌ Runtime command '$runtimeCommand' (runtime: $agentRuntime) not found in PATH"
        Write-Host "Set $runtimeCommandVar to the absolute path if it's installed elsewhere."
        exit 1
    }

    $env:AGENT_RUNTIME = $agentRuntime

    & node "scripts/checklist-processor.js" @ChecklistArgs
}
finally {
    Pop-Location
}
