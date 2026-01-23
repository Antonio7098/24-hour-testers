const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');

const {
  runAgentWithPrompt,
  applyCliArgs,
  getHardeningConfig,
  resetHardeningConfig,
  setSpawnImplementation,
  assignAgentConfigFromEnv,
  resetAgentConfig,
} = require('../../scripts/checklist-processor');

function resetAgentRuntime() {
  resetAgentConfig();
  assignAgentConfigFromEnv();
}

class FakeChild extends EventEmitter {
  constructor(config = {}) {
    super();
    this.config = config;
    this.stdout = new EventEmitter();
    this.stderr = new EventEmitter();
    this.stdin = {
      write: () => {},
      end: () => {},
    };
    this.killCalls = 0;
    this.killed = false;

    this.kill = () => {
      this.killCalls += 1;
      this.killed = true;
      if (typeof config.onKill === 'function') {
        config.onKill(this);
      }
      if (config.emitCloseOnKill !== false) {
        const code = config.killExitCode ?? 1;
        process.nextTick(() => this.emit('close', code));
      }
    };

    if (config.emitImmediately !== false) {
      process.nextTick(() => {
        for (const chunk of config.stdout || []) {
          this.stdout.emit('data', Buffer.from(chunk));
        }
        for (const chunk of config.stderr || []) {
          this.stderr.emit('data', Buffer.from(chunk));
        }
        if (config.emitError) {
          this.emit('error', config.emitError);
          return;
        }
        if (config.autoClose !== false) {
          const code = 'code' in config ? config.code : 0;
          this.emit('close', code);
        }
      });
    }
  }
}

function mockSpawn(sequence) {
  let callIndex = 0;
  const children = [];
  setSpawnImplementation(() => {
    const config = sequence[Math.min(callIndex, sequence.length - 1)] || {};
    const child = new FakeChild(config);
    children.push(child);
    callIndex += 1;
    return child;
  });
  return {
    getCallCount: () => callIndex,
    getChild: index => children[index],
  };
}

function restoreDefaults() {
  setSpawnImplementation();
  resetHardeningConfig();
  resetAgentRuntime();
}

test.afterEach(restoreDefaults);

test('applyCliArgs updates agent hardening configuration knobs', () => {
  resetHardeningConfig();
  applyCliArgs([
    '--agent-max-retries', '7',
    '--agent-retry-delay-seconds', '2',
    '--agent-freeze-timeout-seconds', '9',
    '--rate-limit-wait-minutes', '3',
  ]);
  const config = getHardeningConfig();
  assert.equal(config.agentMaxRetries, 7);
  assert.equal(config.agentRetryDelayMs, 2000);
  assert.equal(config.agentFreezeTimeoutMs, 9000);
  assert.equal(config.rateLimitWaitMinutes, 3);
});

test('runAgentWithPrompt retries on rate limit output and eventually succeeds', async () => {
  resetAgentRuntime();
  const tracker = mockSpawn([
    { stderr: ['HTTP 429: plan limit reached'], code: 1 },
    { stdout: ['Task complete!'], code: 0 },
  ]);

  const output = await runAgentWithPrompt('payload', 'rate-limit-test', {
    maxAttempts: 2,
    retryDelayMs: 0,
    rateLimitWaitMinutes: 0,
    freezeTimeoutMs: 200,
  });

  assert.equal(tracker.getCallCount(), 2);
  assert.match(output, /Task complete!/);
});

test('runAgentWithPrompt retries when permission errors are detected', async () => {
  resetAgentRuntime();
  const tracker = mockSpawn([
    { stderr: ['EACCES: Permission denied'], code: 1 },
    { stdout: ['Recovered after permissions fix'], code: 0 },
  ]);

  const output = await runAgentWithPrompt('payload', 'permission-test', {
    maxAttempts: 2,
    retryDelayMs: 0,
    freezeTimeoutMs: 200,
  });

  assert.equal(tracker.getCallCount(), 2);
  assert.match(output, /Recovered after permissions fix/);
});

test('runAgentWithPrompt detects frozen agents and surfaces the error', async () => {
  resetAgentRuntime();
  const tracker = mockSpawn([
    { autoClose: false, emitImmediately: false },
  ]);

  await assert.rejects(
    runAgentWithPrompt('payload', 'freeze-test', {
      maxAttempts: 1,
      freezeTimeoutMs: 30,
      retryDelayMs: 0,
    }),
    /unresponsive/i,
  );

  const child = tracker.getChild(0);
  assert.ok(child.killed);
  assert.equal(child.killCalls, 1);
});
