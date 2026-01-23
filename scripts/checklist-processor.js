#!/usr/bin/env node
/**
 * Parallel Checklist Processor for OpenCode / Claude Code
 *
 * Iterates through mission-checklist.md, spawning configurable parallel subagents
 * to work on items in batches until all are complete.
 */


const { spawn } = require("child_process");
const { readFileSync, writeFileSync, existsSync, mkdirSync, openSync, closeSync, readdirSync, renameSync } = require("fs");
const { join, resolve, isAbsolute, relative, dirname } = require("path");
const { randomUUID } = require("crypto");

const VERSION = "1.2.0";

let spawnImplementation = spawn;

function setSpawnImplementation(fn) {
  spawnImplementation = typeof fn === "function" ? fn : spawn;
}

const repoRoot = resolve(__dirname, "..");

function resolveRepoPath(targetPath) {
  if (!targetPath) return null;
  return isAbsolute(targetPath) ? targetPath : resolve(repoRoot, targetPath);
}

function formatPathForPrompt(targetPath) {
  if (!targetPath) return "";
  const relativePath = relative(repoRoot, targetPath);
  return relativePath && !relativePath.startsWith("..") ? relativePath : targetPath;
}

// Configuration
let CHECKLIST_FILE = resolveRepoPath("SUT-CHECKLIST.md");
const DEFAULT_MISSION_BRIEF_FILE = resolveRepoPath("SUT-PACKET.md");
const FALLBACK_MISSION_BRIEF_FILE = resolveRepoPath("README.md");
const AGENT_PROMPT_FILE = resolveRepoPath("agent-resources/prompts/AGENT_SYSTEM_PROMPT.md");
const TIER_REPORT_PROMPT_FILE = resolveRepoPath("agent-resources/prompts/TIER_REPORT_PROMPT.md");
const TIER_REPORTS_DIR = resolveRepoPath("tier-reports");
const TIER_METADATA_FILE = join(TIER_REPORTS_DIR, "index.json");
const RUNS_DIR = resolveRepoPath("runs");
const FINAL_REPORT_FILENAME = resolveRepoPath("FINAL_REPORT.md");
const BATCH_SIZE = 5;

const MAX_ITERATIONS_PER_ITEM = 20;
const COMPLETION_PROMISE = "ITEM_COMPLETE";
const DEFAULT_AGENT_MAX_RETRIES = 3;
const DEFAULT_AGENT_RETRY_DELAY_MS = 15_000;
const DEFAULT_AGENT_FREEZE_TIMEOUT_MS = 5 * 60 * 1000;
const DEFAULT_RATE_LIMIT_WAIT_MINUTES = 60;
const PERMISSION_ERROR_PATTERNS = [
  /permission denied/i,
  /access is denied/i,
  /access denied/i,
  /eacces/i,
  /eperm/i,
  /insufficient permissions/i,
  /operation not permitted/i,
];
const RATE_LIMIT_PATTERNS = [
  /rate limit/i,
  /plan limit/i,
  /quota/i,
  /too many requests/i,
  /http\s*429/i,
  /billing hard limit/i,
  /temporarily unavailable due to usage/i,
];

const MODE_FINITE = "finite";
const MODE_INFINITE = "infinite";
const RUNTIME_OPEN_CODE = "opencode";
const RUNTIME_CLAUDE_CODE = "claude-code";
const RUNTIMES = {
  [RUNTIME_OPEN_CODE]: {
    label: "OpenCode",
    defaultModel: "opencode/minimax-m2.1-free",
    commandEnv: "OPENCODE_BIN",
    defaultCommand: "opencode",
    buildArgs: model => ["run", "--model", model].filter(Boolean),
  },
  [RUNTIME_CLAUDE_CODE]: {
    label: "Claude Code",
    defaultModel: "claude-4.5-sonnet",
    commandEnv: "CLAUDE_CODE_BIN",
    defaultCommand: "claude",
    buildArgs: model => ["code", "--model", model].filter(Boolean),
  },
};

const RUNTIME_MODEL_ENV_VARS = {
  [RUNTIME_OPEN_CODE]: "OPENCODE_MODEL",
  [RUNTIME_CLAUDE_CODE]: "CLAUDE_CODE_MODEL",
};

function resolveRuntimeFromEnv(value) {
  const normalized = (value || "").toLowerCase();
  return RUNTIMES[normalized] ? normalized : null;
}

function requireRuntime(value) {
  const normalized = (value || "").toLowerCase();
  if (!RUNTIMES[normalized]) {
    console.error(
      `Error: Unsupported runtime "${value}". Valid options: ${Object.keys(RUNTIMES).join(", ")}`
    );
    process.exit(1);
  }
  return normalized;
}

function getRuntimeModelFromEnv(runtime) {
  const envVar = RUNTIME_MODEL_ENV_VARS[runtime];
  return envVar ? process.env[envVar] : undefined;
}

let agentRuntime;
let agentModel;
let modelExplicitlySet;

function assignAgentConfigFromEnv() {
  agentRuntime = resolveRuntimeFromEnv(process.env.AGENT_RUNTIME) || RUNTIME_OPEN_CODE;
  const runtimeModel = getRuntimeModelFromEnv(agentRuntime);
  const explicitModel = process.env.AGENT_MODEL || runtimeModel;
  agentModel = explicitModel || RUNTIMES[agentRuntime].defaultModel;
  modelExplicitlySet = Boolean(explicitModel);
}

function resetAgentConfig() {
  agentRuntime = undefined;
  agentModel = undefined;
  modelExplicitlySet = undefined;
}

function setAgentConfig(runtime, model) {
  agentRuntime = runtime;
  agentModel = model;
  modelExplicitlySet = Boolean(model);
}

assignAgentConfigFromEnv();

let MISSION_BRIEF_FILE = existsSync(DEFAULT_MISSION_BRIEF_FILE)
  ? DEFAULT_MISSION_BRIEF_FILE
  : FALLBACK_MISSION_BRIEF_FILE;

let missionBriefCache = null;
let tierReportPromptTemplate = existsSync(TIER_REPORT_PROMPT_FILE)
  ? readFileSync(TIER_REPORT_PROMPT_FILE, "utf-8")
  : null;
let agentMaxRetries;
let agentRetryDelayMs;
let agentFreezeTimeoutMs;
let rateLimitWaitMinutes;

function getHardeningConfig() {
  return {
    agentMaxRetries,
    agentRetryDelayMs,
    agentFreezeTimeoutMs,
    rateLimitWaitMinutes,
  };
}

function resetHardeningConfig() {
  agentMaxRetries = DEFAULT_AGENT_MAX_RETRIES;
  agentRetryDelayMs = DEFAULT_AGENT_RETRY_DELAY_MS;
  agentFreezeTimeoutMs = DEFAULT_AGENT_FREEZE_TIMEOUT_MS;
  rateLimitWaitMinutes = DEFAULT_RATE_LIMIT_WAIT_MINUTES;
}

resetHardeningConfig();

// Lazy-load mission brief (if present)
function loadMissionBrief() {
  if (missionBriefCache) return missionBriefCache;
  if (!existsSync(MISSION_BRIEF_FILE)) {
    console.warn(`⚠️  Missing ${MISSION_BRIEF_FILE}.`);
    return null;
  }
  try {
    const content = readFileSync(MISSION_BRIEF_FILE, "utf-8");
    missionBriefCache = content;
    return content;
  } catch (err) {
    console.error(`Error loading mission brief: ${err}`);
    return null;
  }
}

/**
 * @typedef {Object} ChecklistItem
 * @property {string} id
 * @property {string} target
 * @property {string} priority
 * @property {string} risk
 * @property {string} status
 * @property {string} tier
 * @property {string} section
 */

/**
 * @typedef {Object} BatchResult
 * @property {ChecklistItem} item
 * @property {boolean} success
 * @property {string} [error]
 * @property {string} [output]
 */

// Lazy-load agent system prompt (if present)
let agentSystemPrompt = "";
if (existsSync(AGENT_PROMPT_FILE)) {
  agentSystemPrompt = readFileSync(AGENT_PROMPT_FILE, "utf-8");
} else {
  console.warn(`⚠️  Missing ${AGENT_PROMPT_FILE}. Agents will only receive checklist instructions.`);
}

// State management paths (needed before we parse CLI flags that inspect state)
const stateDir = join(repoRoot, ".checklist-processor");
const statePath = join(stateDir, "state.json");
const checkpointPath = join(stateDir, "checkpoint.json");

let batchSize = BATCH_SIZE;
let maxIterations = MAX_ITERATIONS_PER_ITEM;
let dryRun = false;
let resume = false;
let mode = MODE_FINITE;

function setChecklistFilePath(filePath) {
  if (typeof filePath !== "string" || !filePath.trim()) {
    throw new Error("Checklist file path must be a non-empty string");
  }
  CHECKLIST_FILE = resolveRepoPath(filePath.trim());
}

function applyCliArgs(args) {
  const argv = Array.isArray(args) ? args : [];

  const runtimeOptions = Object.keys(RUNTIMES).join(", ");

  if (argv.includes("--help") || argv.includes("-h")) {
    console.log(`
Parallel Checklist Processor - Task Tool Orchestration

Usage:
  node checklist-processor.js [options]

Options:
  --batch-size N        Number of parallel items to process (default: 5)
  --max-iterations N   Max iterations per item (default: 20)
  --agent-max-retries N  Number of restart attempts per agent (default: ${DEFAULT_AGENT_MAX_RETRIES})
  --agent-retry-delay-seconds N  Delay between agent retries in seconds (default: ${DEFAULT_AGENT_RETRY_DELAY_MS / 1000})
  --agent-freeze-timeout-seconds N  Inactivity window before an agent is considered frozen (default: ${DEFAULT_AGENT_FREEZE_TIMEOUT_MS / 1000})
  --rate-limit-wait-minutes N  Cooldown when hitting plan/rate limits (default: ${DEFAULT_RATE_LIMIT_WAIT_MINUTES})
  --dry-run            Show what would be processed without running
  --resume             Resume from last checkpoint
  --mode TYPE          Mode: "finite" (default) or "infinite"
  --checklist PATH     Override scenario checklist file
  --mission-brief PATH Override mission brief file
  --runtime NAME       Agent runtime (${runtimeOptions})
  --model MODEL        Override the model slug passed to the runtime

  --status             Show current processing status
  --version, -v        Show version
  --help, -h           Show this help

Examples:
  node checklist-processor.js                    # Process all items in batches of 5
  node checklist-processor.js --batch-size 3     # Process 3 items at a time
  node checklist-processor.js --dry-run          # Preview without execution
  node checklist-processor.js --status           # Check current status
`);
    process.exit(0);
  }

  if (argv.includes("--version") || argv.includes("-v")) {
    console.log(`checklist-processor v${VERSION}`);
    process.exit(0);
  }

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];

    if (arg === "--batch-size") {
      const val = argv[++i];
      if (!val || isNaN(parseInt(val))) {
        console.error("Error: --batch-size requires a number");
        process.exit(1);
      }
      batchSize = parseInt(val);
    } else if (arg === "--max-iterations") {
      const val = argv[++i];
      if (!val || isNaN(parseInt(val))) {
        console.error("Error: --max-iterations requires a number");
        process.exit(1);
      }
      maxIterations = parseInt(val);
    } else if (arg === "--dry-run") {
      dryRun = true;
    } else if (arg === "--resume") {
      resume = true;
    } else if (arg === "--agent-max-retries") {
      const val = argv[++i];
      if (!val || isNaN(parseInt(val))) {
        console.error("Error: --agent-max-retries requires a number");
        process.exit(1);
      }
      agentMaxRetries = Math.max(1, parseInt(val));
    } else if (arg === "--agent-retry-delay-seconds") {
      const val = argv[++i];
      if (!val || isNaN(parseInt(val))) {
        console.error("Error: --agent-retry-delay-seconds requires a number");
        process.exit(1);
      }
      agentRetryDelayMs = Math.max(0, parseInt(val) * 1000);
    } else if (arg === "--agent-freeze-timeout-seconds") {
      const val = argv[++i];
      if (!val || isNaN(parseInt(val))) {
        console.error("Error: --agent-freeze-timeout-seconds requires a number");
        process.exit(1);
      }
      agentFreezeTimeoutMs = Math.max(0, parseInt(val) * 1000);
    } else if (arg === "--rate-limit-wait-minutes") {
      const val = argv[++i];
      if (!val || isNaN(parseInt(val))) {
        console.error("Error: --rate-limit-wait-minutes requires a number");
        process.exit(1);
      }
      rateLimitWaitMinutes = Math.max(0, parseInt(val));
    } else if (arg === "--mode") {
      const val = (argv[++i] || "").toLowerCase();
      if (![MODE_FINITE, MODE_INFINITE].includes(val)) {
        console.error("Error: --mode must be 'finite' or 'infinite'");
        process.exit(1);
      }
      mode = val;
    } else if (arg === "--checklist") {
      const val = argv[++i];
      if (!val) {
        console.error("Error: --checklist requires a file path");
        process.exit(1);
      }
      CHECKLIST_FILE = resolveRepoPath(val);
    } else if (arg === "--mission-brief") {
      const val = argv[++i];
      if (!val) {
        console.error("Error: --mission-brief requires a file path");
        process.exit(1);
      }
      MISSION_BRIEF_FILE = resolveRepoPath(val);
      missionBriefCache = null;
    } else if (arg === "--runtime" || arg === "--agent-runtime") {
      const val = argv[++i];
      if (!val) {
        console.error("Error: --runtime requires a value");
        process.exit(1);
      }
      agentRuntime = requireRuntime(val);
      if (!modelExplicitlySet) {
        agentModel = getRuntimeModelFromEnv(agentRuntime) || RUNTIMES[agentRuntime].defaultModel;
      }
    } else if (arg === "--model") {
      const val = argv[++i];
      if (!val) {
        console.error("Error: --model requires a value");
        process.exit(1);
      }
      agentModel = val;
      modelExplicitlySet = true;
    } else if (arg === "--status") {
      showStatus();
      process.exit(0);
    } else if (arg.startsWith("-")) {
      console.error(`Error: Unknown option: ${arg}`);
      process.exit(1);
    }
  }
}

/**
 * @typedef {Object} ProcessorState
 * @property {boolean} active
 * @property {number} currentBatch
 * @property {number} totalBatches
 * @property {string[]} itemsProcessed
 * @property {string[]} itemsCompleted
 * @property {string[]} itemsFailed
 * @property {string} startedAt
 * @property {string} lastCheckpoint
 * @property {string} [completedAt]
 */

function ensureStateDir() {
  if (!existsSync(stateDir)) {
    mkdirSync(stateDir, { recursive: true });
  }
}

function saveState(state) {
  ensureStateDir();
  writeFileSync(statePath, JSON.stringify(state, null, 2));
}

function loadState() {
  if (!existsSync(statePath)) {
    return null;
  }
  try {
    return JSON.parse(readFileSync(statePath, "utf-8"));
  } catch {
    return null;
  }
}

function saveCheckpoint(items) {
  ensureStateDir();
  const checkpoint = {
    timestamp: new Date().toISOString(),
    items: items.map(item => ({
      id: item.id,
      status: item.status
    }))
  };
  writeFileSync(checkpointPath, JSON.stringify(checkpoint, null, 2));
}

// Parse checklist from markdown
function parseChecklist() {
  if (!existsSync(CHECKLIST_FILE)) {
    console.error(`Error: Checklist file not found: ${CHECKLIST_FILE}`);
    process.exit(1);
  }

  const content = readFileSync(CHECKLIST_FILE, "utf-8");
  const lines = content.split("\n");
  const items = [];
  
  let currentTier = "";
  let currentSection = "";
  let inTable = false;

  for (const line of lines) {
    // Track tier and section
    if (line.startsWith("## Tier ")) {
      currentTier = line.replace("## ", "").trim();
      currentSection = "";
      continue;
    }
    
    if (line.startsWith("### ")) {
      currentSection = line.replace("### ", "");
      continue;
    }

    // Track table headers
    if (line.includes("| ID |") && line.includes("| Target |")) {
      inTable = true;
      continue;
    }

    const trimmed = line.trim();

    // Parse table rows (markdown rows start with '|')
    if (inTable && trimmed.startsWith("|")) {
      const cols = trimmed
        .split("|")
        .map(c => c.trim())
        .filter(Boolean);
      if (cols.length >= 5) {
        const id = cols[0];
        const target = cols[1];
        const priority = cols[2];
        const risk = cols[3];
        const status = cols[4];

        // Skip header rows and separators
        if (id === "ID" || id === "----") continue;

        items.push({
          id,
          target,
          priority,
          risk,
          status,
          tier: currentTier,
          section: currentSection
        });
      }
    }

    // Exit table when we hit a non-table line
    if (inTable && trimmed && !trimmed.includes("|")) {
      inTable = false;
    }
  }

  return items;
}

function getRemainingChecklistItems(items) {
  return items.filter(item => !(item.status || "").includes("✅"));
}

function buildBacklogSynthesisPrompt({ missionBrief, checklistContent, neededCount }) {
  const brief = missionBrief?.trim() ? missionBrief.trim() : "Mission brief not provided.";

  return `You are an autonomous reliability planner. When the existing backlog runs dry you must synthesize new checklist rows that feel like thoughtful follow-ons, not duplicates.

Context about the system under test (SUT):
${brief}

Current checklist markdown (for reference, do not rewrite existing rows):
${checklistContent}

Generate ${neededCount} brand-new checklist rows that are scoped to one autonomous run each. Keep the same five-column structure (ID, Target, Priority, Risk, Status) and prefer concrete targets over placeholders.

Respond ONLY with JSON using the shape:
{
  "items": [
    {"id": "INF-123", "target": "...", "priority": "P1", "risk": "High", "status": "☐ Not Started"}
  ]
}`;
}

async function extendChecklistIfNeeded(missionBrief) {
  if (mode !== MODE_INFINITE) {
    return false;
  }

  const checklistContent = readFileSafe(CHECKLIST_FILE);
  const items = parseChecklist();
  const prefixTierMap = buildPrefixTierMap(items);
  const remaining = getRemainingChecklistItems(items);
  const needed = Math.max(batchSize - remaining.length, 0);

  console.log(`DEBUG: Infinite Mode Check - batchSize=${batchSize}, remaining=${remaining.length}, needed=${needed}`);

  if (needed <= 0) {
    return false;
  }

  console.log(`Infinite mode: need ${needed} additional checklist item(s) to reach the batch target of ${batchSize}. Invoking synthesis agent...`);

  const missionBriefLocal = missionBrief || loadMissionBrief();
  const prompt = buildBacklogSynthesisPrompt({
    missionBrief: missionBriefLocal,
    checklistContent,
    neededCount: needed,
  });

  let output;
  try {
    output = await runAgentWithPrompt(prompt, "infinite-backlog");
  } catch (error) {
    console.error("Failed to run backlog synthesis agent:", error);
    throw error;
  }

  const payload = extractJsonPayload(output);
  let generatedItems = coerceGeneratedItems(payload);

  if (generatedItems.length === 0) {
    console.warn("Synthesis agent returned no usable checklist rows."
      + " Check the prompt output logs for details.");
    return false;
  }

  generatedItems = generatedItems.slice(0, needed);
  appendRowsToChecklist(generatedItems, { prefixTierMap });
  console.log(`Appended ${generatedItems.length} synthesized checklist item(s).`);
  return true;
}

async function generateTierReportsIfNeeded(items, missionBrief) {
  // Use prefix map to group items correctly
  const prefixTierMap = buildPrefixTierMap(items);
  
  // Group by sanitized tier name for reporting
  const grouped = items.reduce((acc, item) => {
    const heading = resolveTierHeading(item, prefixTierMap);
    if (heading) {
        const tierName = heading.replace(/^##\s*/, "");
        acc[tierName] = acc[tierName] || [];
        acc[tierName].push(item);
    }
    return acc;
  }, {});

  for (const [tierName, tierItems] of Object.entries(grouped)) {
    const isComplete = tierItems.every(item => (item.status || "").includes("✅"));
    if (!isComplete) continue;

    const sanitizedTierName = getSanitizedTierName(tierName);
    const tierDir = join(RUNS_DIR, sanitizedTierName);
    
    // Ensure tier directory exists
    if (!existsSync(tierDir)) {
        mkdirSync(tierDir, { recursive: true });
    }

    const reportPath = join(tierDir, `${sanitizedTierName}-FINAL-REPORT.md`);

    if (existsSync(reportPath)) continue;

    console.log(`Tier "${tierName}" is complete. Generating aggregated report...`);

    // Collect individual run reports
    let accumulatedReports = "";
    for (const item of tierItems) {
        const itemRunDir = getRunDir(item, prefixTierMap);
        const itemReportPath = join(itemRunDir, `${item.id}-FINAL-REPORT.md`);
        
        accumulatedReports += `\n\n### Report for ${item.id}: ${item.target}\n`;
        if (existsSync(itemReportPath)) {
            accumulatedReports += readFileSync(itemReportPath, "utf-8");
        } else {
            accumulatedReports += "*No final report found for this item.*";
        }
        accumulatedReports += "\n\n---";
    }

    // Prepare prompt
    if (!tierReportPromptTemplate) {
        // Fallback if no template
        writeFileSync(reportPath, `# ${tierName} - Tier Report\n\n${accumulatedReports}`);
        console.log(`Generated simple tier report: ${reportPath}`);
        continue;
    }

    const checklistRows = tierItems.map(formatChecklistRow).join("\n");

    const missionBrief = loadMissionBrief();
    const prompt = tierReportPromptTemplate
      .replace("{{TIER_NAME}}", tierName)
      .replace("{{CHECKLIST_ROWS}}", checklistRows)
      .replace("{{MISSION_BRIEF}}", missionBrief || "")
      .replace("{{FINAL_REPORT_DIGEST}}", accumulatedReports);

    try {
      const rawOutput = await runAgentWithPrompt(prompt, `tier-report-${sanitizedTierName}`);
      const cleanedOutput = cleanAgentOutput(rawOutput);
      writeFileSync(reportPath, cleanedOutput);
      console.log(`Generated aggregated tier report: ${reportPath}`);
    } catch (err) {
      console.error(`Failed to generate tier report for ${tierName}:`, err);
    }
  }
}

function getSanitizedTierName(tierHeading) {
  return tierHeading.replace(/^##\s*/, "").replace(/[^a-zA-Z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "").toLowerCase();
}

function getRunDir(item, prefixTierMap) {
  const heading = resolveTierHeading(item, prefixTierMap);
  const tierName = heading ? getSanitizedTierName(heading) : "uncategorized";
  return join(RUNS_DIR, tierName, item.id);
}

const fileLocks = new Map();

function withFileLock(targetFile, callback) {
  const absoluteTarget = resolveRepoPath(targetFile);
  const key = absoluteTarget || targetFile;
  const previous = fileLocks.get(key) || Promise.resolve();

  const next = previous.then(() => Promise.resolve().then(() => callback(absoluteTarget || targetFile)));
  fileLocks.set(key, next.catch(() => {}));

  return next.finally(() => {
    if (fileLocks.get(key) === next || !fileLocks.has(key)) {
      fileLocks.delete(key);
    }
  });
}

function writeFileAtomically(targetPath, contents) {
  const absoluteTarget = resolveRepoPath(targetPath);
  if (!absoluteTarget) {
    writeFileSync(targetPath, contents);
    return;
  }
  const tempFile = join(dirname(absoluteTarget), `${randomUUID()}.tmp`);
  writeFileSync(tempFile, contents);
  renameSync(tempFile, absoluteTarget);
}

function updateChecklistItemStatus(itemId, newStatus) {
  return withFileLock(CHECKLIST_FILE, () => {
    try {
      const content = readFileSafe(CHECKLIST_FILE);
      const lines = content.split("\n");
      const newLines = lines.map(line => {
        const trimmed = line.trim();
        if (trimmed.startsWith("|") && trimmed.includes(` ${itemId} `)) {
          const parts = line.split("|");
          if (parts.length >= 6) {
            parts[5] = ` ${newStatus} `;
            return parts.join("|");
          }
        }
        return line;
      });
      writeFileAtomically(CHECKLIST_FILE, newLines.join("\n"));
    } catch (err) {
      console.error(`Failed to update status for ${itemId}:`, err);
      throw err;
    }
  });
}

function getSanitizedTierName(tierHeading) {
  return tierHeading.replace(/^##\s*/, "").replace(/[^a-zA-Z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "").toLowerCase();
}

function getRunDir(item, prefixTierMap) {
  const heading = resolveTierHeading(item, prefixTierMap);
  const tierName = heading ? getSanitizedTierName(heading) : "uncategorized";
  return join(RUNS_DIR, tierName, item.id);
}

async function processChecklist() {
  const missionBrief = loadMissionBrief();

  let initialExtensionPerformed = false;

  if (mode === MODE_INFINITE) {
    initialExtensionPerformed = await extendChecklistIfNeeded(missionBrief);
    if (initialExtensionPerformed) {
      console.log("Checklist extended to satisfy batch requirements. Continuing with processing loop.");
    }
  }

  let items = parseChecklist();
  await generateTierReportsIfNeeded(items, missionBrief);
  let remaining = getRemainingChecklistItems(items);

  if (remaining.length === 0 && mode === MODE_INFINITE) {
    const synthesized = await extendChecklistIfNeeded(missionBrief);
    if (synthesized) {
      console.log("Infinite mode: synthesized additional backlog after initial parse. Recomputing remaining items...");
      items = parseChecklist();
      remaining = getRemainingChecklistItems(items);
    }
  }

  if (remaining.length === 0) {
    console.log(mode === MODE_INFINITE
      ? "No remaining items after attempting to synthesize backlog. Nothing to process."
      : "All checklist items are already complete. Nothing to process.");
    return;
  }

  const batch = remaining.slice(0, batchSize);

  if (dryRun) {
    console.log(`[Dry run] Next batch (${batch.length} item(s)) would be: ${batch.map(item => item.id).join(", ")}`);
    return;
  }

  console.log("Next batch ready for processing:", batch.map(item => item.id).join(", "));
  
  // Build prefix map for run dir resolution
  const prefixTierMap = buildPrefixTierMap(items);

  const promises = batch.map(async (item) => {
    console.log(`Starting processing for ${item.id}...`);
    
    // Determine Run Directory
    const runDir = getRunDir(item, prefixTierMap);
    
    // Create directory structure
    if (!dryRun) {
        mkdirSync(runDir, { recursive: true });
        mkdirSync(join(runDir, "config"), { recursive: true });
        mkdirSync(join(runDir, "dx_evaluation"), { recursive: true });
        mkdirSync(join(runDir, "mocks"), { recursive: true });
        mkdirSync(join(runDir, "pipelines"), { recursive: true });
        mkdirSync(join(runDir, "research"), { recursive: true });
        mkdirSync(join(runDir, "results"), { recursive: true });
        mkdirSync(join(runDir, "tests"), { recursive: true });
    }

    // Prepare the specific prompt for this item
    let prompt = agentSystemPrompt || "";
    
    // Simple substitutions
    prompt = prompt.replace("{{ENTRY_ID}}", item.id)
                   .replace("{{ENTRY_TITLE}}", item.target)
                   .replace("{{PRIORITY}}", item.priority)
                   .replace("{{RISK_CLASS}}", item.risk)
                   .replace("{{INDUSTRY}}", "Tech") // Default
                   .replace("{{DEPLOYMENT_MODE}}", "Dev") // Default
                   .replace("{{CHECKLIST_FILE}}", CHECKLIST_FILE)
                   .replace("{{MISSION_BRIEF}}", missionBrief || "No brief provided")
                   .replace("{{RUN_DIR}}", formatPathForPrompt(runDir).replace(/\\/g, "/"));

    // Append specific instruction
    prompt += `\n\nYOUR CURRENT TASK:\nExecute checklist item ${item.id}: ${item.target}\n`;
    prompt += `Perform the necessary tests/research. All artifacts MUST be saved in: ${formatPathForPrompt(runDir)}\n`;
    prompt += `When you have completed the task and generated the FINAL-REPORT.md, you MUST output: "${COMPLETION_PROMISE}" to signal completion.\n`;

    try {
        if (dryRun) {
            console.log(`[Dry Run] Would execute agent for ${item.id} in ${runDir}`);
            return;
        }

        // Run the agent
        const output = await runAgentWithPrompt(prompt, `task-${item.id}`);
        
        // Log output for debugging
        const logPath = join(runDir, "results", "agent-log.txt");
        writeFileSync(logPath, output);

        console.log(`Item ${item.id} processed. Output saved to ${logPath}`);
        
        // Mark as complete
        await updateChecklistItemStatus(item.id, "✅ Completed");
        
    } catch (err) {
        console.error(`Error processing ${item.id}:`, err);
        await updateChecklistItemStatus(item.id, "❌ Failed");
    }
  });

  await Promise.all(promises);
  console.log("Batch processing complete.");
}

function showStatus() {
  const state = loadState();
  const items = parseChecklist();

  console.log(`
╔══════════════════════════════════════════════════════════════════╗
║                Checklist Processor Status                         ║
╚══════════════════════════════════════════════════════════════════╝
`);

  if (!state) {
    console.log("⏹️  No active processing session");
    console.log(`📋 Total items in checklist: ${items.length}`);
    return;
  }

  const completed = items.filter(item => item.status.includes("✅") || state.itemsCompleted.includes(item.id));
  const failed = items.filter(item => state.itemsFailed.includes(item.id));
  const remaining = Math.max(items.length - completed.length - failed.length, 0);

  console.log(`🔄 Active session: ${state.active ? "Yes" : "No"}`);
  console.log(`📊 Progress: ${completed.length} completed, ${failed.length} failed, ${remaining} remaining`);
  console.log(`📦 Current batch: ${state.currentBatch} / ${state.totalBatches}`);
  console.log(`⏱️  Started: ${state.startedAt}`);
  console.log(`🕐 Last checkpoint: ${state.lastCheckpoint}`);

  if (state.itemsFailed.length > 0) {
    console.log(`\n❌ Failed items: ${state.itemsFailed.join(", ")}`);
    console.log(`💡 Run with --resume to retry failed items`);
  }
}

function readFileSafe(path) {
  if (!path || !existsSync(path)) {
    return "";
  }
  return readFileSync(path, "utf-8");
}

function ensureTierSection(content, tierName) {
  const header = tierName.startsWith("## ") ? tierName : `## ${tierName}`;
  const tableHeader = "| ID | Target | Priority | Risk | Status |";
  const divider = "|----|--------|----------|------|--------|";

  if (content.includes(header)) {
    return content.endsWith("\n") ? content : `${content}\n`;
  }

  const trimmed = content.trimEnd();
  const separator = trimmed ? "\n\n" : "";
  return `${trimmed}${separator}${header}\n${tableHeader}\n${divider}\n`;
}

function ensureInfiniteBacklogSection(content) {
   return ensureTierSection(content, "Tier 4: Reliability & Backlog Expansion");
}

function formatChecklistRow(item) {
  const status = item.status || "☐ Not Started";
  return `| ${item.id} | ${item.target} | ${item.priority} | ${item.risk} | ${status} |`;
}

function buildPrefixTierMap(items) {
  return items.reduce((map, item) => {
    const prefix = (item.id || "").split("-")[0];
    if (prefix && item.tier) {
      map[prefix.toUpperCase()] = item.tier;
    }
    return map;
  }, {});
}

function resolveTierHeading(item, prefixTierMap) {
  const normalizedTier = item.tier?.trim();
  if (normalizedTier) {
    return normalizedTier.startsWith("## ") ? normalizedTier : `## ${normalizedTier}`;
  }
  const prefix = (item.id || "").split("-")[0]?.toUpperCase();
  const tierLabel = prefix ? prefixTierMap?.[prefix] : null;
  if (tierLabel) {
    return tierLabel.startsWith("## ") ? tierLabel : `## ${tierLabel}`;
  }
  return null;
}

function buildTierTableMetadata(lines) {
  const metadata = {};
  let currentTier = null;
  let inTable = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("## ")) {
      currentTier = line.trim();
      inTable = false;
      metadata[currentTier] = metadata[currentTier] || {};
    }

    if (!currentTier) continue;

    if (line.includes("| ID |") && line.includes("| Status |")) {
      metadata[currentTier] = metadata[currentTier] || {};
      metadata[currentTier].tableHeaderLine = i;
      metadata[currentTier].tableEndLine = i;
      inTable = true;
      continue;
    }

    if (inTable) {
      if (line.trim().startsWith("|")) {
        metadata[currentTier].tableEndLine = i;
      } else if (line.trim() === "" || line.trim().startsWith("-")) {
        inTable = false;
      }
    }
  }

  Object.values(metadata).forEach(meta => {
    if (typeof meta.tableEndLine === "number") {
      meta.insertLine = meta.tableEndLine + 1;
    } else if (typeof meta.tableHeaderLine === "number") {
      meta.insertLine = meta.tableHeaderLine + 1;
    }
  });

  return metadata;
}

function groupItemsByTierHeading(items, prefixTierMap) {
  return items.reduce((groups, item) => {
    const tierHeading = resolveTierHeading(item, prefixTierMap);
    if (!tierHeading) {
      console.warn(`Unable to determine tier for synthesized item ${item.id}. Skipping.`);
      return groups;
    }
    groups[tierHeading] = groups[tierHeading] || [];
    groups[tierHeading].push(item);
    return groups;
  }, {});
}

function appendRowsToChecklist(items, options = {}) {
  if (!items || items.length === 0) return;
  const targetFile = resolveRepoPath(options.targetFile || CHECKLIST_FILE);

  return withFileLock(targetFile, () => {
    let content = readFileSafe(targetFile) || "";
    
    // Ensure section exists for any new tiers
    const uniqueTiers = [...new Set(items.map(i => i.tier).filter(Boolean))];
    for (const tier of uniqueTiers) {
      if (!content.includes(tier)) {
         content = ensureTierSection(content, tier);
      }
    }

    const lines = content ? content.split("\n") : [];
    const tierMetadata = buildTierTableMetadata(lines);
    const prefixTierMap = options.prefixTierMap || buildPrefixTierMap(parseChecklist());
    const grouped = groupItemsByTierHeading(items, prefixTierMap);

    const insertions = Object.entries(grouped)
      .map(([tierHeading, groupedItems]) => {
        const meta = tierMetadata[tierHeading];
        if (!meta || typeof meta.insertLine !== "number") {
          console.warn(`Tier heading "${tierHeading}" not found in checklist. Skipping ${groupedItems.length} item(s).`);
          return null;
        }
        return {
          insertLine: meta.insertLine,
          rows: groupedItems.map(formatChecklistRow),
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.insertLine - a.insertLine);

    for (const insertion of insertions) {
      lines.splice(insertion.insertLine, 0, ...insertion.rows);
    }

    writeFileAtomically(targetFile, lines.join("\n"));
  });
}

function cleanAgentOutput(text) {
  if (!text) return "";
  // 1. Remove ANSI escape codes
  let clean = text.replace(/\u001b\[[0-9;]*m/g, "");
  
  // 2. Remove "thought/action" lines often emitted by OpenCode/Claude
  // Heuristic: If we find a line starting with "# ", treat that as the start of the document.
  const headerMatch = clean.match(/^# /m);
  if (headerMatch && typeof headerMatch.index === "number") {
    return clean.slice(headerMatch.index).trimStart();
  }

  // Fallback: Remove lines starting with pipe | or specific tool call patterns
  clean = clean.split("\n")
    .filter(line => !line.trim().startsWith("|") && !line.includes("Glob") && !line.includes("Read"))
    .join("\n");
    
  return clean.trim();
}

function extractJsonPayload(text) {
  if (!text) return null;
  const fenced = text.match(/```json([\s\S]*?)```/i) || text.match(/```([\s\S]*?)```/i);
  let candidate = fenced ? fenced[1].trim() : text.trim();
  
  try {
    return JSON.parse(candidate);
  } catch (err) {
    // If strict parsing failed, try to locate the first outer-most {} block
    if (!fenced) {
       const jsonBlock = text.match(/\{[\s\S]*\}/);
       if (jsonBlock) {
         try {
           return JSON.parse(jsonBlock[0]);
         } catch (e) {
           // ignore inner parse error, fall through to warning
         }
       }
    }

    console.warn("JSON Parse Error:", err.message);
    console.warn("Candidate JSON was:", candidate.substring(0, 500) + "...");
    return null;
  }
}

function coerceGeneratedItems(payload) {
  if (!payload) return [];
  const rawItems = Array.isArray(payload.items)
    ? payload.items
    : Array.isArray(payload)
      ? payload
      : [];

  return rawItems.map((item, index) => ({
    id: item.id || `INF-${Date.now()}-${index + 1}`,
    target: item.target || "Backlog scenario",
    priority: item.priority || "P2",
    risk: item.risk || "Moderate",
    status: item.status || "☐ Not Started",
    tier: item.tier || "Tier 4: Reliability & Backlog Expansion"
  }));
}

function buildAgentInvocation() {
  const runtime = RUNTIMES[agentRuntime];
  if (!runtime) {
    throw new Error(`Unsupported runtime: ${agentRuntime}`);
  }
  const command = process.env[runtime.commandEnv] || runtime.defaultCommand;
  const args = typeof runtime.buildArgs === "function" ? runtime.buildArgs(agentModel) : [];
  return { command, args, label: runtime.label };
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function formatDuration(ms) {
  if (!ms) return "0s";
  const parts = [];
  const hours = Math.floor(ms / 3_600_000);
  const minutes = Math.floor((ms % 3_600_000) / 60_000);
  const seconds = Math.floor((ms % 60_000) / 1000);
  if (hours) parts.push(`${hours}h`);
  if (minutes) parts.push(`${minutes}m`);
  if (seconds || parts.length === 0) parts.push(`${seconds}s`);
  return parts.join(" ");
}

function isRateLimitMessage(text) {
  if (!text) return false;
  return RATE_LIMIT_PATTERNS.some(pattern => pattern.test(text));
}

function isPermissionMessage(text) {
  if (!text) return false;
  return PERMISSION_ERROR_PATTERNS.some(pattern => pattern.test(text));
}

function withRetryMetadata(error, reason, details = {}) {
  error.retryMetadata = {
    retryable: true,
    reason,
    ...details,
  };
  return error;
}

function executeAgentAttempt({ prompt, label, freezeTimeoutMs }) {
  return new Promise((resolve, reject) => {
    const sessionId = randomUUID();
    const { command, args } = buildAgentInvocation();
    const child = spawnImplementation(command, args, {
      env: process.env,
      shell: process.platform === "win32",
    });
    ensureStateDir();
    const logPath = join(stateDir, `${label || "agent"}-${sessionId}.log`);
    const logFd = openSync(logPath, "w");
    let logClosed = false;
    const closeLog = () => {
      if (!logClosed) {
        closeSync(logFd);
        logClosed = true;
      }
    };
    writeFileSync(logPath, `=== ${label || "agent"} ===\n\n`);
    let output = "";
    let freezeTimer;
    let freezeTriggered = false;

    const refreshFreezeTimer = () => {
      if (!freezeTimeoutMs) return;
      clearTimeout(freezeTimer);
      freezeTimer = setTimeout(() => {
        freezeTriggered = true;
        console.warn(`[${label || "agent"}] No output for ${formatDuration(freezeTimeoutMs)}. Terminating agent...`);
        try {
          child.kill();
        } catch (killErr) {
          console.error(`Failed to terminate frozen agent: ${killErr}`);
        }
      }, freezeTimeoutMs);
    };

    refreshFreezeTimer();

    child.stdin.write(prompt);
    child.stdin.end();

    child.stdout.on("data", chunk => {
      const text = chunk.toString();
      output += text;
      writeFileSync(logPath, text, { flag: "a" });
      refreshFreezeTimer();
    });

    child.stderr.on("data", chunk => {
      const text = chunk.toString();
      output += text;
      writeFileSync(logPath, text, { flag: "a" });
      refreshFreezeTimer();
    });

    child.on("error", err => {
      clearTimeout(freezeTimer);
      closeLog();
      reject(err);
    });

    child.on("close", code => {
      clearTimeout(freezeTimer);
      closeLog();

      if (freezeTriggered) {
        return reject(withRetryMetadata(new Error("Agent became unresponsive and was terminated."), "freeze"));
      }

      if (code !== 0) {
        if (isRateLimitMessage(output)) {
          return reject(withRetryMetadata(new Error(`Agent exited with rate limit (code ${code}).`), "rate_limit"));
        }
        if (isPermissionMessage(output)) {
          return reject(withRetryMetadata(new Error(`Agent exited due to permission issues (code ${code}).`), "permission"));
        }
        return reject(new Error(`Agent exited with code ${code}`));
      }

      if (isRateLimitMessage(output)) {
        return reject(withRetryMetadata(new Error("Agent output indicates plan/rate limits were hit."), "rate_limit"));
      }

      if (isPermissionMessage(output)) {
        return reject(withRetryMetadata(new Error("Agent encountered permission issues."), "permission"));
      }

      resolve(output);
    });
  });
}

async function runAgentWithPrompt(prompt, label, options = {}) {
  const maxAttempts = Math.max(1, options.maxAttempts || agentMaxRetries);
  const freezeTimeoutMs = options.freezeTimeoutMs ?? agentFreezeTimeoutMs;
  const retryDelayMs = options.retryDelayMs ?? agentRetryDelayMs;
  const rateLimitWaitMs = (options.rateLimitWaitMinutes ?? rateLimitWaitMinutes) * 60 * 1000;

  let attempt = 0;
  let lastError;

  while (attempt < maxAttempts) {
    attempt += 1;
    console.log(`[${label || "agent"}] Attempt ${attempt}/${maxAttempts}`);
    try {
      const output = await executeAgentAttempt({ prompt, label, freezeTimeoutMs });
      return output;
    } catch (error) {
      lastError = error;
      const { retryMetadata } = error;
      const retryable = retryMetadata?.retryable;
      const reason = retryMetadata?.reason;

      if (!retryable || attempt >= maxAttempts) {
        throw error;
      }

      if (reason === "rate_limit") {
        const waitMs = rateLimitWaitMs || retryDelayMs;
        console.warn(`[${label || "agent"}] Rate limit hit. Cooling down for ${formatDuration(waitMs)} before retrying...`);
        await sleep(waitMs);
      } else if (reason === "permission") {
        console.warn(`[${label || "agent"}] Permission issue detected. Retrying in ${formatDuration(retryDelayMs)}...`);
        await sleep(retryDelayMs);
      } else if (reason === "freeze") {
        console.warn(`[${label || "agent"}] Agent became unresponsive. Retrying in ${formatDuration(retryDelayMs)}...`);
        await sleep(retryDelayMs);
      } else {
        throw error;
      }
    }
  }

  throw lastError || new Error("Agent failed after all retry attempts.");
}

if (require.main === module) {
  applyCliArgs(process.argv.slice(2));
  processChecklist().catch(error => {
    console.error("Fatal error:", error);
    process.exit(1);
  });
}

module.exports = {
  ensureInfiniteBacklogSection,
  ensureTierSection,
  formatChecklistRow,
  extractJsonPayload,
  coerceGeneratedItems,
  readFileSafe,
  appendRowsToChecklist,
  runAgentWithPrompt,
  buildAgentInvocation,
  showStatus,
  parseChecklist,
  buildPrefixTierMap,
  resolveTierHeading,
  getRemainingChecklistItems,
  assignAgentConfigFromEnv,
  resetAgentConfig,
  setAgentConfig,
  setChecklistFilePath,
  setSpawnImplementation,
  getHardeningConfig,
  resetHardeningConfig,
  applyCliArgs,
};
