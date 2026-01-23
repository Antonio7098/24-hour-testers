const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  parseChecklist,
  getRemainingChecklistItems,
  appendRowsToChecklist,
  readFileSafe,
  setChecklistFilePath,
  ensureTierSection,
  buildPrefixTierMap,
  resolveTierHeading,
} = require('../../scripts/checklist-processor');

const { repoPath, writeTempFile } = require('../helpers/test-utils');

const DEFAULT_CHECKLIST = repoPath("SUT-CHECKLIST.md");

async function withChecklistFile(markdown, fn) {
  const { filePath } = writeTempFile(markdown, 'checklist.md');
  const previous = DEFAULT_CHECKLIST;
  setChecklistFilePath(filePath);
  try {
    return await fn(filePath);
  } finally {
    setChecklistFilePath(previous);
  }
}

test('parseChecklist captures tiers, sections, and columns from markdown tables', async () => {
  const markdown = `## Tier 9 · Experimental

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| EXP-001 | Focus area | P2 | Moderate | ☐ Not Started |

### Section Alpha
| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| EXP-002 | Section row | P1 | High | ✅ Completed |
`;

  await withChecklistFile(markdown, () => {
    const items = parseChecklist();
    assert.equal(items.length, 2);
    assert.deepEqual(items[0], {
      id: 'EXP-001',
      target: 'Focus area',
      priority: 'P2',
      risk: 'Moderate',
      status: '☐ Not Started',
      tier: 'Tier 9 · Experimental',
      section: '',
    });
    assert.equal(items[1].section, 'Section Alpha');
  });
});

test('getRemainingChecklistItems filters out ✅ rows', async () => {
  const markdown = `## Tier 1

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| CORE-001 | Target | P0 | High | ✅ Completed |
| CORE-002 | Target | P1 | High | ☐ Not Started |
`;

  await withChecklistFile(markdown, () => {
    const items = parseChecklist();
    const remaining = getRemainingChecklistItems(items);
    assert.equal(remaining.length, 1);
    assert.equal(remaining[0].id, 'CORE-002');
  });
});

test('ensureTierSection appends missing tier scaffolding exactly once', () => {
  const base = '# Intro copy\n';
  const tierName = 'Tier 9 · Experimental';
  const first = ensureTierSection(base, tierName);
  assert.match(first, /## Tier 9 · Experimental/);
  assert.match(first, /\| ID \| Target \| Priority \| Risk \| Status \|/);
  const second = ensureTierSection(first, tierName);
  assert.equal(second, first);
});

test('buildPrefixTierMap indexes prefixes and resolveTierHeading leverages them', () => {
  const items = [
    { id: 'WEB-001', tier: '## Tier Web Ops' },
    { id: 'API-777', tier: 'Tier 2 · API Surface' },
  ];
  const map = buildPrefixTierMap(items);
  assert.deepEqual(map, {
    WEB: '## Tier Web Ops',
    API: 'Tier 2 · API Surface',
  });

  const explicitTier = resolveTierHeading({ id: 'WEB-999', tier: 'Tier Override' }, map);
  assert.equal(explicitTier, '## Tier Override');

  const fromPrefix = resolveTierHeading({ id: 'API-123' }, map);
  assert.equal(fromPrefix, '## Tier 2 · API Surface');

  const missing = resolveTierHeading({ id: 'MISC-1' }, map);
  assert.equal(missing, null);
});

test('appendRowsToChecklist creates missing tier sections before inserting rows', async () => {
  const markdown = `## Tier 1 · Core\n\n| ID | Target | Priority | Risk | Status |\n|----|--------|----------|------|--------|\n| CORE-001 | Target | P1 | High | ☐ Not Started |\n`;

  await withChecklistFile(markdown, async filePath => {
    await appendRowsToChecklist([
      {
        id: 'OBS-200',
        target: 'Observability drill',
        priority: 'P2',
        risk: 'Moderate',
        status: '☐ Not Started',
        tier: 'Tier 5 · Observability',
      },
    ], { targetFile: filePath });

    const updated = fs.readFileSync(filePath, 'utf-8');
    assert.match(updated, /## Tier 5 · Observability/);
    const lines = updated.trim().split('\n');
    const headerIndex = lines.findIndex(line => line.includes('Tier 5 · Observability'));
    assert.ok(headerIndex >= 0, 'new tier header is present');
    const rowLine = lines[headerIndex + 3];
    assert.match(rowLine, /OBS-200/);
  });
});

test('appendRowsToChecklist inserts new rows after the tier table, preserving existing content', async () => {
  const markdown = `## Tier 3 · Deployment

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| INFRA-001 | Baseline | P1 | High | ☐ Not Started |
`;

  await withChecklistFile(markdown, async filePath => {
    await appendRowsToChecklist([
      {
        id: 'INFRA-010',
        target: 'Edge failover drill',
        priority: 'P2',
        risk: 'Moderate',
        status: '☐ Not Started',
        tier: '## Tier 3 · Deployment',
      },
    ], { targetFile: filePath });

    const updated = fs.readFileSync(filePath, 'utf-8');
    const lines = updated.trim().split('\n');
    const newIndex = lines.findIndex(line => line.includes('INFRA-010'));
    const oldIndex = lines.findIndex(line => line.includes('INFRA-001'));
    assert.ok(newIndex > oldIndex, 'new row should be appended');
  });
});

test('readFileSafe returns empty string for missing files and contents for existing ones', () => {
  const missing = readFileSafe('non-existent-file.md');
  assert.equal(missing, '');

  const { filePath } = writeTempFile('hello world', 'sample.txt');
  const contents = readFileSafe(filePath);
  assert.equal(contents, 'hello world');
});
