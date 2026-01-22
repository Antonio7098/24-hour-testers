#!/usr/bin/env node
const { spawnSync } = require("child_process");
const {
  existsSync,
  mkdirSync,
  readdirSync,
  statSync,
  renameSync,
  readFileSync,
  writeFileSync,
  rmSync,
} = require("fs");
const { join, resolve } = require("path");

const repoRoot = resolve(__dirname, "..");
process.chdir(repoRoot);

const processor = require("./checklist-processor");
const { parseChecklist } = processor;

const stateDir = join(repoRoot, ".checklist-processor");
const runsDir = join(repoRoot, "runs");
const tierReportsDir = join(repoRoot, "tier-reports");
const checklistFile = join(repoRoot, "SUT-CHECKLIST.md");
const missionBriefFile = join(repoRoot, "SUT-PACKET.md");

const commands = {
  start: runProcessor,
  status: showStatus,
  dashboard: showDashboard,
  clean: cleanWorkspace,
};

(function main() {
  const [command, ...args] = process.argv.slice(2);
  if (!command || !commands[command]) {
    printHelp();
    process.exit(command ? 1 : 0);
  }
  commands[command](args);
})();

function printHelp() {
  console.log(`
24h Testers CLI
Usage: node scripts/24h-cli.js <command> [options]

Commands:
  start [--batch-size N ...]   Run checklist-processor with optional flags
  status                       Show processor status summary
  dashboard                    Render aggregated checklist/tier stats
  clean [--apply] [--keep-tier-reports]
                               Archive runs, reset checklist, and clear state

Examples:
  node scripts/24h-cli.js start --batch-size 3 --mode finite
  node scripts/24h-cli.js clean --apply
  node scripts/24h-cli.js dashboard
`);
}

function runProcessor(args) {
  const result = spawnSync(process.execPath, [join(__dirname, "checklist-processor.js"), ...args], {
    cwd: repoRoot,
    env: process.env,
    stdio: "inherit",
  });
  process.exit(result.status ?? 0);
}

function showStatus() {
  const result = spawnSync(process.execPath, [join(__dirname, "checklist-processor.js"), "--status"], {
    cwd: repoRoot,
    env: process.env,
    stdio: "inherit",
  });
  process.exit(result.status ?? 0);
}

function showDashboard() {
  const items = safeParseChecklist();
  const summary = items.reduce(
    (acc, item) => {
      acc.total++;
      if ((item.status || "").includes("❌")) {
        acc.failed++;
      } else if ((item.status || "").includes("✅")) {
        acc.completed++;
      } else {
        acc.remaining++;
      }
      const tier = item.tier || "Uncategorized";
      acc.tiers[tier] = acc.tiers[tier] || { total: 0, completed: 0, remaining: 0, failed: 0 };
      acc.tiers[tier].total++;
      if ((item.status || "").includes("❌")) {
        acc.tiers[tier].failed++;
      } else if ((item.status || "").includes("✅")) {
        acc.tiers[tier].completed++;
      } else {
        acc.tiers[tier].remaining++;
      }
      return acc;
    },
    { total: 0, completed: 0, remaining: 0, failed: 0, tiers: {} }
  );

  console.log(`\n📋 Checklist Overview\n---------------------`);
  console.log(`Total rows: ${summary.total}`);
  console.log(`✅ Completed: ${summary.completed}`);
  console.log(`❌ Failed: ${summary.failed}`);
  console.log(`☐ Remaining: ${summary.remaining}`);

  console.log(`\n📊 Tier Breakdown`);
  Object.entries(summary.tiers).forEach(([tier, stats]) => {
    console.log(`- ${tier}: ${stats.completed}/${stats.total} complete, ${stats.failed} failed, ${stats.remaining} remaining`);
  });

  const state = safeReadJson(join(stateDir, "state.json"));
  if (state) {
    console.log(`\n🧠 Active Session`);
    console.log(`  Active: ${state.active ? "Yes" : "No"}`);
    console.log(`  Current batch: ${state.currentBatch}/${state.totalBatches}`);
    console.log(`  Started: ${state.startedAt}`);
    if (state.itemsFailed?.length) {
      console.log(`  Outstanding failures: ${state.itemsFailed.join(", ")}`);
    }
  }
}

function cleanWorkspace(args) {
  const flags = parseCleanFlags(args);
  const dryRun = !flags.apply;
  console.log(dryRun ? "🧪 Clean (dry run)" : "🧹 Cleaning workspace");

  const steps = [
    () => archiveRuns(dryRun),
    () => archiveTierReports(dryRun, flags.keepTierReports),
    () => resetChecklist(dryRun),
    () => resetProcessorState(dryRun),
  ];

  steps.forEach(step => step());

  console.log(
    dryRun
      ? '\nNo changes were made. Re-run with --apply to perform the cleanup.'
      : '\nCleanup complete. Checklist and state have been reset.'
  );
}

function parseCleanFlags(args) {
  return args.reduce(
    (acc, arg) => {
      if (arg === "--apply" || arg === "--yes") {
        acc.apply = true;
      } else if (arg === "--keep-tier-reports") {
        acc.keepTierReports = true;
      }
      return acc;
    },
    { apply: false, keepTierReports: false }
  );
}

function archiveRuns(dryRun) {
  if (!existsSync(runsDir)) {
    console.log("- runs/ directory not found (skipping)");
    return;
  }
  const entries = readdirSync(runsDir).filter(name => !name.startsWith(".") && name !== "archive");
  if (entries.length === 0) {
    console.log("- runs/ has no artifacts to archive");
    return;
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const archiveDir = join(runsDir, "archive", stamp);
  console.log(`- Archiving ${entries.length} run folder(s) to runs/archive/${stamp}`);
  if (!dryRun) {
    mkdirSync(archiveDir, { recursive: true });
    entries.forEach(name => {
      const source = join(runsDir, name);
      if (statSync(source).isDirectory() || statSync(source).isFile()) {
        renameSync(source, join(archiveDir, name));
      }
    });
  }
}

function archiveTierReports(dryRun, keepTierReports) {
  if (keepTierReports || !existsSync(tierReportsDir)) {
    console.log("- Tier reports retained");
    return;
  }
  const entries = readdirSync(tierReportsDir).filter(name => !name.startsWith("."));
  if (entries.length === 0) {
    console.log("- No tier reports to archive");
    return;
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const archiveDir = join(tierReportsDir, "archive", stamp);
  console.log(`- Moving ${entries.length} tier report(s) to tier-reports/archive/${stamp}`);
  if (!dryRun) {
    mkdirSync(archiveDir, { recursive: true });
    entries.forEach(name => {
      const source = join(tierReportsDir, name);
      if (statSync(source).isFile()) {
        renameSync(source, join(archiveDir, name));
      }
    });
  }
}

function resetChecklist(dryRun) {
  if (!existsSync(checklistFile)) {
    console.log("- Checklist file not found (skipping reset)");
    return;
  }
  const original = readFileSync(checklistFile, "utf-8").split("\n");
  let changed = false;
  const next = original.map(line => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("|") || trimmed.includes("| Status |")) {
      return line;
    }
    const parts = line.split("|");
    if (parts.length < 6) return line;
    const idCell = parts[1]?.trim();
    if (idCell === "ID" || idCell === "----") {
      return line;
    }
    if (parts[5]?.trim() !== "☐ Not Started") {
      parts[5] = " ☐ Not Started ";
      changed = true;
      return parts.join("|");
    }
    return line;
  });

  if (!changed) {
    console.log("- Checklist already in Not Started state");
    return;
  }
  if (dryRun) {
    console.log("- Checklist would be reset to Not Started");
  } else {
    writeFileSync(checklistFile, next.join("\n"));
    console.log("- Checklist statuses reset to Not Started");
  }
}

function resetProcessorState(dryRun) {
  if (!existsSync(stateDir)) {
    console.log("- .checklist-processor directory not found");
    if (!dryRun) {
      mkdirSync(stateDir, { recursive: true });
    }
    return;
  }
  console.log("- Clearing .checklist-processor state");
  if (!dryRun) {
    rmSync(stateDir, { recursive: true, force: true });
    mkdirSync(stateDir, { recursive: true });
  }
}

function safeParseChecklist() {
  try {
    return parseChecklist();
  } catch (err) {
    console.warn("Unable to parse checklist:", err.message);
    return [];
  }
}

function safeReadJson(target) {
  try {
    return existsSync(target) ? JSON.parse(readFileSync(target, "utf-8")) : null;
  } catch (err) {
    console.warn(`Unable to read ${target}:`, err.message);
    return null;
  }
}
