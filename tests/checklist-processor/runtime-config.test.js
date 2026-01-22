const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  buildAgentInvocation,
  assignAgentConfigFromEnv,
  resetAgentConfig,
  setAgentConfig,
  setChecklistFilePath,
} = require('../../scripts/checklist-processor');

const { repoPath } = require('../helpers/test-utils');

const missionBriefPath = path.join(__dirname, "..", "..", "SEU-PACKET.md");

const DEFAULT_CHECKLIST = repoPath("SUT-CHECKLIST.md");

function withEnv(overrides, fn) {
  const originalEnv = { ...process.env };
  Object.entries(overrides).forEach(([key, value]) => {
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  });
  try {
    return fn();
  } finally {
    Object.keys(process.env).forEach(key => {
      if (!(key in originalEnv)) {
        delete process.env[key];
      }
    });
    Object.entries(originalEnv).forEach(([key, value]) => {
      process.env[key] = value;
    });
  }
}

test('buildAgentInvocation uses OpenCode defaults when no env overrides are set', () => {
  withEnv({
    AGENT_RUNTIME: undefined,
    AGENT_MODEL: undefined,
    OPENCODE_MODEL: undefined,
  }, () => {
    resetAgentConfig();
    assignAgentConfigFromEnv();
    const { command, args, label } = buildAgentInvocation();
    assert.equal(command, 'opencode');
    assert.deepEqual(args, ['run', '--model', 'opencode/minimax-m2.1-free']);
    assert.equal(label, 'OpenCode');
  });
});

test('buildAgentInvocation respects CLAUDE_CODE_MODEL env override', () => {
  withEnv({
    AGENT_RUNTIME: 'claude-code',
    CLAUDE_CODE_MODEL: 'claude-3.5-haiku',
  }, () => {
    resetAgentConfig();
    assignAgentConfigFromEnv();
    const result = buildAgentInvocation();
    assert.equal(result.command, 'claude');
    assert.deepEqual(result.args, ['code', '--model', 'claude-3.5-haiku']);
  });
});

test('setAgentConfig forces custom runtime/model regardless of env vars', () => {
  withEnv({ AGENT_RUNTIME: 'claude-code' }, () => {
    resetAgentConfig();
    setAgentConfig('opencode', 'custom/model');
    const result = buildAgentInvocation();
    assert.equal(result.command, 'opencode');
    assert.deepEqual(result.args, ['run', '--model', 'custom/model']);
  });
});

test('setChecklistFilePath enforces non-empty string input', () => {
  assert.throws(() => setChecklistFilePath(''), /non-empty string/);
  setChecklistFilePath(DEFAULT_CHECKLIST);
});
