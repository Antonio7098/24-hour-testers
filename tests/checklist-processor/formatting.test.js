const test = require('node:test');
const assert = require('node:assert/strict');

const {
  ensureInfiniteBacklogSection,
  formatChecklistRow,
  extractJsonPayload,
  coerceGeneratedItems,
} = require('../../scripts/checklist-processor');

const normalize = text => text.replace(/\r\n/g, '\n');

test('ensureInfiniteBacklogSection adds the missing section once', () => {
  const base = '# Checklist\nIntro copy';
  const firstPass = ensureInfiniteBacklogSection(base);
  assert.match(firstPass, /## Tier 4: Reliability & Backlog Expansion/);
  assert.match(firstPass, /\| ID \| Target \| Priority \| Risk \| Status \|/);

  const secondPass = ensureInfiniteBacklogSection(firstPass);
  assert.equal(normalize(firstPass), normalize(secondPass));
});

test('formatChecklistRow renders a markdown row and defaults status', () => {
  const explicit = formatChecklistRow({
    id: 'INF-101',
    target: 'Stress payment rails',
    priority: 'P1',
    risk: 'High',
    status: '✅ Completed',
  });
  assert.equal(explicit, '| INF-101 | Stress payment rails | P1 | High | ✅ Completed |');

  const fallback = formatChecklistRow({
    id: 'INF-102',
    target: 'Latency guardrails',
    priority: 'P2',
    risk: 'Moderate',
  });
  assert.equal(fallback, '| INF-102 | Latency guardrails | P2 | Moderate | ☐ Not Started |');
});

test('extractJsonPayload supports fenced code blocks, raw JSON, and rejects invalid payloads', () => {
  const fenced = '```json\n{"items":[{"id":"INF-200"}]}\n```';
  const raw = '{"items":[{"id":"INF-201"}]}' ;
  const invalid = 'not json at all';

  assert.deepEqual(extractJsonPayload(fenced), { items: [{ id: 'INF-200' }] });
  assert.deepEqual(extractJsonPayload(raw), { items: [{ id: 'INF-201' }] });
  assert.equal(extractJsonPayload(invalid), null);
});

test('coerceGeneratedItems applies safe defaults and preserves provided fields', () => {
  const now = Date.now();
  const payload = {
    items: [
      { id: 'INF-300', target: 'Scenario', priority: 'P0', risk: 'Severe', status: '🚧 In Progress' },
      { target: 'Fallback scenario' },
    ],
  };

  const coerced = coerceGeneratedItems(payload);
  assert.equal(coerced.length, 2);
  assert.deepEqual(coerced[0], {
    id: 'INF-300',
    target: 'Scenario',
    priority: 'P0',
    risk: 'Severe',
    status: '🚧 In Progress',
    tier: 'Tier 4: Reliability & Backlog Expansion',
  });
  assert.equal(coerced[1].target, 'Fallback scenario');
  assert.equal(coerced[1].priority, 'P2');
  assert.equal(coerced[1].risk, 'Moderate');
  assert.equal(coerced[1].status, '☐ Not Started');
  assert.equal(coerced[1].tier, 'Tier 4: Reliability & Backlog Expansion');
  assert.match(coerced[1].id, /^INF-\d+-2$/);
  assert.ok(parseInt(coerced[1].id.split('-')[1], 10) >= now);
});
