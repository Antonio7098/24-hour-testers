#!/usr/bin/env node
/**
 * Checklist Processor v2.0
 * 
 * Robust, observable agent orchestration system with:
 * - OOP architecture following SOLID principles
 * - Retry logic with exponential backoff
 * - Real-time state tracking and persistence
 * - Interactive CLI with multiple commands
 * - Live TUI for monitoring
 */

const { resolve } = require('path');
const {
  Logger,
  LogLevel,
  ChecklistProcessor,
  CLI,
  TUI,
  RunManager,
} = require('./lib');

const repoRoot = resolve(__dirname, '..');

async function main() {
  const cli = new CLI(repoRoot);
  const options = cli.parse(process.argv.slice(2));
  
  // Setup logger
  const logger = new Logger({
    prefix: 'Processor',
    level: options.verbose ? LogLevel.DEBUG : LogLevel.INFO,
  });

  try {
    switch (options.command) {
      case 'run':
        await runProcessor(options, logger);
        break;
        
      case 'status':
        cli.showStatus();
        break;
        
      case 'agents':
        cli.showAgents();
        break;
        
      case 'logs':
        cli.showLogs(options.agentId, { tail: options.tail });
        break;
        
      case 'watch':
        const tui = new TUI({
          stateDir: resolve(repoRoot, '.checklist-processor'),
          repoRoot,
        });
        tui.start();
        break;
        
      case 'history':
        cli.showHistory();
        break;
        
      case 'cancel':
        await cancelAll(logger);
        break;
        
      default:
        logger.error(`Unknown command: ${options.command}`);
        process.exit(1);
    }
  } catch (error) {
    logger.fatal('Unhandled error', { error: error.message, stack: error.stack });
    process.exit(1);
  }
}

async function runProcessor(options, logger) {
  logger.info('Initializing checklist processor', {
    batchSize: options.batchSize,
    runtime: options.runtime,
    mode: options.mode,
    dryRun: options.dryRun,
  });

  const processor = new ChecklistProcessor({
    repoRoot,
    batchSize: options.batchSize,
    maxIterations: options.maxIterations,
    mode: options.mode,
    dryRun: options.dryRun,
    runtime: options.runtime,
    model: options.model,
    checklistPath: options.checklistPath,
    missionBriefPath: options.missionBriefPath,
    logger,
  });

  // Wire up event handlers for observability
  processor.on('run:update', ({ event, run, data }) => {
    if (event === 'status') {
      logger.debug(`Agent ${run.itemId}: ${data.prev} -> ${data.current}`);
    } else if (event === 'stage') {
      logger.debug(`Agent ${run.itemId} stage: ${data.current}`);
    }
  });

  processor.on('session:start', ({ sessionId }) => {
    logger.info(`Session started: ${sessionId}`);
  });

  processor.on('session:complete', ({ sessionId, summary }) => {
    logger.info(`Session complete: ${sessionId}`, summary);
  });

  // Handle graceful shutdown
  let shuttingDown = false;
  const shutdown = async (signal) => {
    if (shuttingDown) return;
    shuttingDown = true;
    
    logger.warn(`Received ${signal}, cancelling agents...`);
    processor.cancelAll();
    
    // Give agents time to clean up
    await new Promise(resolve => setTimeout(resolve, 2000));
    process.exit(0);
  };

  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));

  // Start processing
  const result = await processor.process();
  
  // Report results
  if (result.dryRun) {
    logger.info('Dry run complete', result);
  } else {
    logger.info('Processing complete', result);
    
    if (result.failed > 0) {
      logger.warn(`${result.failed} item(s) failed. Use 'logs' command to investigate.`);
      process.exit(1);
    }
  }
}

async function cancelAll(logger) {
  logger.info('Cancelling all running agents...');
  
  // Send SIGTERM to any agent processes
  // This is a simple implementation - in production you'd track PIDs
  const { execSync } = require('child_process');
  
  try {
    // Find and kill opencode/claude processes started by this tool
    execSync('pkill -f "opencode run" || true', { stdio: 'ignore' });
    execSync('pkill -f "claude code" || true', { stdio: 'ignore' });
    logger.info('Cancel signal sent to all agents');
  } catch (e) {
    logger.warn('No agents to cancel or cancel failed');
  }
}

// Run main
main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
