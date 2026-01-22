const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const {
  parseChecklist,
  getRemainingChecklistItems,
  appendRowsToChecklist,
  readFileSafe,
  setChecklistFilePath,
} = require('../../scripts/checklist-processor');

const { repoPath, writeTempFile } = require('../helpers/test-utils');

const DEFAULT_CHECKLIST = repoPath('mission-checklist.md');

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
