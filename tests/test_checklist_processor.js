const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  ensureInfiniteBacklogSection,
  formatChecklistRow,
  extractJsonPayload,
  coerceGeneratedItems,
  readFileSafe,
  appendRowsToChecklist,
  buildAgentInvocation,
  resetAgentConfig,
  assignAgentConfigFromEnv,
  setAgentConfig,
} = require('../scripts/checklist-processor');

const normalize = text => text.replace(/\r\n/g, '\n');

test('ensureInfiniteBacklogSection adds section only once', () => {
  const base = '# Checklist\nIntro';
  const first = ensureInfiniteBacklogSection(base);
  assert.match(first, /## Infinite Backlog/);
  assert.match(first, /\| ID \| Target \| Priority \| Risk \| Status \|/);

  const second = ensureInfiniteBacklogSection(first);
  assert.equal(normalize(first), normalize(second));
});

test('buildAgentInvocation honors runtime defaults and env overrides', () => {
  const originalEnv = { ...process.env };
  try {
    resetAgentConfig();
    process.env.AGENT_RUNTIME = 'opencode';
    delete process.env.AGENT_MODEL;
    delete process.env.OPENCODE_MODEL;
    assignAgentConfigFromEnv();
    const { command, args } = buildAgentInvocation();
    assert.equal(command, 'opencode');
    assert.deepEqual(args, ['run', '--model', 'opencode/minimax-m2.1-free']);

    process.env.AGENT_RUNTIME = 'claude-code';
    process.env.CLAUDE_CODE_MODEL = 'claude-3.5-haiku';
    assignAgentConfigFromEnv();
    const claude = buildAgentInvocation();
    assert.equal(claude.command, 'claude');
    assert.deepEqual(claude.args, ['code', '--model', 'claude-3.5-haiku']);

    setAgentConfig('opencode', 'custom/model');
    const forced = buildAgentInvocation();
    assert.equal(forced.command, 'opencode');
    assert.deepEqual(forced.args, ['run', '--model', 'custom/model']);
  } finally {
    Object.keys(process.env).forEach(key => {
      if (!(key in originalEnv)) {
        delete process.env[key];
      }
    });
    Object.entries(originalEnv).forEach(([key, value]) => {
      process.env[key] = value;
    });
    assignAgentConfigFromEnv();
  }
});

test('formatChecklistRow renders markdown row', () => {
  const row = formatChecklistRow({
    id: 'INF-101',
    target: 'Stress payment rails',
    priority: 'P1',
    risk: 'High',
    status: '☐ Not Started',
  });

  assert.equal(row, '| INF-101 | Stress payment rails | P1 | High | ☐ Not Started |');
});

test('extractJsonPayload handles fenced and raw JSON', () => {
  const fenced = '```json\n{"items":[{"id":"INF-200"}]}\n```';
  const raw = '{"items":[{"id":"INF-201"}]}';

  assert.deepEqual(extractJsonPayload(fenced), { items: [{ id: 'INF-200' }] });
  assert.deepEqual(extractJsonPayload(raw), { items: [{ id: 'INF-201' }] });
  assert.equal(extractJsonPayload('not json'), null);
});

test('coerceGeneratedItems applies defaults when missing', () => {
  const payload = {
    items: [
      { id: 'INF-300', target: 'Scenario', priority: 'P0', risk: 'Severe', status: '☐ Not Started' },
      { target: 'Fallback scenario' },
    ],
  };

  const items = coerceGeneratedItems(payload);
  assert.equal(items.length, 2);
  assert.equal(items[0].id, 'INF-300');
  assert.equal(items[1].target, 'Fallback scenario');
  assert.equal(items[1].priority, 'P2');
  assert.equal(items[1].risk, 'Moderate');
  assert.equal(items[1].status, '☐ Not Started');
});

test('readFileSafe returns empty string for missing file and contents otherwise', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'checklist-tests-'));
  const filePath = path.join(tempDir, 'sample.txt');
  fs.writeFileSync(filePath, 'hello world', 'utf-8');

  assert.equal(readFileSafe(filePath), 'hello world');
  assert.equal(readFileSafe(path.join(tempDir, 'missing.txt')), '');
});

test('appendRowsToChecklist inserts rows into tier tables via prefix map', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'checklist-tests-'));
  const checklistPath = path.join(tempDir, 'checklist.md');
  const base = `## Tier 2 · Functional/Stage Risks (pick 3–5 rows that matter)

| ID | Stage / Capability | Priority | Risk | Status |
|----|--------------------|----------|------|--------|
| STAGE-001 | Alpha | P1 | High | ☑️  Completed |
| STAGE-002 | Beta | P0 | Catastrophic | ☒ Blocked |
`;
  fs.writeFileSync(checklistPath, base, 'utf-8');

  const newItems = [{
    id: 'STAGE-010',
    target: 'New stage scenario',
    priority: 'P1',
    risk: 'High',
    status: '☐ Not Started',
  }];

  appendRowsToChecklist(newItems, {
    targetFile: checklistPath,
    prefixTierMap: {
      STAGE: '## Tier 2 · Functional/Stage Risks (pick 3–5 rows that matter)',
    },
  });

  const updated = fs.readFileSync(checklistPath, 'utf-8');
  assert.match(
    updated,
    /\| STAGE-010 \| New stage scenario \| P1 \| High \| ☂?☐ Not Started \|/u
  );
  const lines = updated.trimEnd().split('\n');
  const newRowIndex = lines.findIndex(line => line.includes('STAGE-010'));
  const stage002Index = lines.findIndex(line => line.includes('STAGE-002'));
  assert(newRowIndex > -1, 'new row not inserted');
  assert(stage002Index > -1, 'baseline row missing');
  assert(newRowIndex > stage002Index, 'new row should be appended after existing Tier 2 rows');
});

test('appendRowsToChecklist respects explicit tier metadata', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'checklist-tests-'));
  const checklistPath = path.join(tempDir, 'checklist.md');
  const tierHeading = '## Tier 3 · Deployment / Infrastructure (only what you run)';
  const base = `${tierHeading}

| ID | Environment Target | Priority | Risk | Status |
|----|--------------------|----------|------|--------|
| INFRA-001 | Primary env | P1 | High | ☑️  Completed |
`;
  fs.writeFileSync(checklistPath, base, 'utf-8');

  const newItems = [{
    id: 'INFRA-010',
    target: 'Edge failover drill',
    priority: 'P2',
    risk: 'Moderate',
    status: '☐ Not Started',
    tier: tierHeading,
  }];

  appendRowsToChecklist(newItems, { targetFile: checklistPath });

  const updated = fs.readFileSync(checklistPath, 'utf-8');
  assert.match(
    updated,
    /\| INFRA-010 \| Edge failover drill \| P2 \| Moderate \| ☂?☐ Not Started \|/u
  );
});
