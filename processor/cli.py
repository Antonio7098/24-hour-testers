"""
Command Line Interface for the Stageflow Checklist Processor.

Provides a user-friendly CLI matching the original JS implementation.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from .config import ProcessorConfig, ProcessingMode, AgentRuntime
from .processor import ChecklistProcessor
from .run_manager import RunManager
from .utils.logger import setup_logging, get_logger

__version__ = "1.0.0"

logger = get_logger("cli")


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="stageflow-processor",
        description="Stageflow-based Checklist Processor for 24h Testers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s run --batch-size 5 --mode infinite
  %(prog)s status
  %(prog)s dashboard
  %(prog)s run --dry-run
  %(prog)s run --runtime claude-code --model claude-4.5-sonnet
        """,
    )
    
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the checklist processor")
    run_parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=5,
        help="Number of items to process in parallel (default: 5)",
    )
    run_parser.add_argument(
        "--max-iterations",
        type=int,
        default=20,
        help="Maximum iterations per item (default: 20)",
    )
    run_parser.add_argument(
        "--mode", "-m",
        choices=["finite", "infinite"],
        default="finite",
        help="Processing mode (default: finite)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview processing without executing agents",
    )
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue from last checkpoint",
    )
    run_parser.add_argument(
        "--checklist",
        type=str,
        default=None,
        help="Path to checklist file (default: SUT-CHECKLIST.md)",
    )
    run_parser.add_argument(
        "--mission-brief",
        type=str,
        default=None,
        help="Path to mission brief file (default: SUT-PACKET.md)",
    )
    run_parser.add_argument(
        "--runtime", "-r",
        choices=["opencode", "claude-code"],
        default="opencode",
        help="Agent runtime to use (default: opencode)",
    )
    run_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model to use (default: runtime default)",
    )
    run_parser.add_argument(
        "--timeout",
        type=int,
        default=300000,
        help="Agent timeout in milliseconds (default: 300000)",
    )
    run_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    run_parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Repository root directory (default: current directory)",
    )
    run_parser.add_argument(
        "--agent-resources",
        type=str,
        default=None,
        help="Custom agent-resources directory (prompts/templates override)",
    )
    
    # Status command
    subparsers.add_parser("status", help="Show processor status")
    
    # Dashboard command
    subparsers.add_parser("dashboard", help="Show aggregated checklist stats")
    
    # History command
    subparsers.add_parser("history", help="Show session history")
    
    # Cancel command
    subparsers.add_parser("cancel", help="Cancel all running agents")
    
    return parser


def get_repo_root(args) -> Path:
    """Determine the repository root."""
    if hasattr(args, "repo_root") and args.repo_root:
        return Path(args.repo_root).resolve()
    
    # Try to find repo root by looking for markers
    cwd = Path.cwd()
    for path in [cwd] + list(cwd.parents):
        if (path / "SUT-CHECKLIST.md").exists() or (path / "package.json").exists():
            return path
    
    return cwd


async def run_processor(args) -> int:
    """Run the processor with the given arguments."""
    repo_root = get_repo_root(args)

    config = ProcessorConfig(
        repo_root=repo_root,
        checklist_path=Path(args.checklist) if args.checklist else None,
        mission_brief_path=Path(args.mission_brief) if args.mission_brief else None,
        agent_resources_dir=Path(args.agent_resources) if args.agent_resources else None,
        batch_size=args.batch_size,
        max_iterations=args.max_iterations,
        mode=ProcessingMode(args.mode),
        dry_run=args.dry_run,
        runtime=AgentRuntime(args.runtime),
        model=args.model,
        timeout_ms=args.timeout,
        verbose=args.verbose,
    )
    
    processor = ChecklistProcessor(config)
    
    # Setup signal handlers
    def handle_signal(signum, frame):
        logger.warning(f"Received signal {signum}, cancelling...")
        processor.cancel_all()
    
    import signal
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Run processor
    result = await processor.process()
    
    # Report results
    if result.dry_run:
        logger.info(f"Dry run complete: would process {result.processed} items")
    else:
        logger.info(f"Processing complete: {result.completed}/{result.processed} succeeded, {result.failed} failed")
    
    return 1 if result.failed > 0 else 0


def show_status(args) -> int:
    """Show current processor status."""
    repo_root = get_repo_root(args)
    state_dir = repo_root / ".processor"
    
    if not state_dir.exists():
        print("No processor state found. Run 'stageflow-processor run' first.")
        return 0
    
    state_file = state_dir / "active-runs.json"
    if state_file.exists():
        import json
        state = json.loads(state_file.read_text())
        
        print(f"\n📋 Session Status")
        print(f"─" * 40)
        print(f"Session: {state.get('sessionId', 'unknown')}")
        print(f"Status: {state.get('status', 'unknown')}")
        
        summary = state.get("summary", {})
        print(f"\nProgress:")
        print(f"  Total: {summary.get('total', 0)}")
        print(f"  ✅ Completed: {summary.get('completed', 0)}")
        print(f"  ❌ Failed: {summary.get('failed', 0)}")
        print(f"  ⏳ Active: {summary.get('active', 0)}")
        print(f"  ⏸️  Pending: {summary.get('pending', 0)}")
        
        if state.get("startedAt"):
            print(f"\nStarted: {state['startedAt']}")
        if state.get("completedAt"):
            print(f"Completed: {state['completedAt']}")
    else:
        print("No active session found.")
    
    return 0


def show_dashboard(args) -> int:
    """Show dashboard with tier breakdowns."""
    from .utils.checklist_parser import ChecklistParser
    
    repo_root = get_repo_root(args)
    checklist_path = repo_root / "SUT-CHECKLIST.md"
    
    if not checklist_path.exists():
        print(f"Checklist not found: {checklist_path}")
        return 1
    
    parser = ChecklistParser(checklist_path, repo_root)
    
    try:
        items = parser.parse()
    except Exception as e:
        print(f"Failed to parse checklist: {e}")
        return 1
    
    # Calculate summary
    total = len(items)
    completed = len([i for i in items if i.is_completed()])
    failed = len([i for i in items if i.is_failed()])
    remaining = len([i for i in items if i.is_pending()])
    
    # Group by tier
    tiers: dict[str, dict] = {}
    for item in items:
        tier = item.tier or "Uncategorized"
        if tier not in tiers:
            tiers[tier] = {"total": 0, "completed": 0, "failed": 0, "remaining": 0}
        tiers[tier]["total"] += 1
        if item.is_completed():
            tiers[tier]["completed"] += 1
        elif item.is_failed():
            tiers[tier]["failed"] += 1
        else:
            tiers[tier]["remaining"] += 1
    
    print(f"\n📋 Checklist Overview")
    print(f"─" * 40)
    print(f"Total rows: {total}")
    print(f"✅ Completed: {completed}")
    print(f"❌ Failed: {failed}")
    print(f"☐ Remaining: {remaining}")
    
    print(f"\n📊 Tier Breakdown")
    for tier, stats in tiers.items():
        print(f"  {tier}: {stats['completed']}/{stats['total']} complete, {stats['failed']} failed, {stats['remaining']} remaining")
    
    # Show session info if available
    state_dir = repo_root / ".processor"
    state_file = state_dir / "active-runs.json"
    if state_file.exists():
        import json
        state = json.loads(state_file.read_text())
        print(f"\n🧠 Active Session")
        print(f"  Status: {state.get('status', 'unknown')}")
        if state.get("startedAt"):
            print(f"  Started: {state['startedAt']}")
    
    return 0


def show_history(args) -> int:
    """Show session history."""
    repo_root = get_repo_root(args)
    state_dir = repo_root / ".processor"
    
    sessions = RunManager.get_session_history(state_dir)
    
    if not sessions:
        print("No session history found.")
        return 0
    
    print(f"\n📜 Session History")
    print(f"─" * 60)
    
    for session in sessions[:10]:  # Show last 10
        summary = session.get("summary", {})
        print(f"\n{session.get('sessionId', 'unknown')}")
        print(f"  Status: {session.get('status', 'unknown')}")
        print(f"  Started: {session.get('startedAt', 'unknown')}")
        print(f"  Completed: {summary.get('completed', 0)}/{summary.get('total', 0)}, {summary.get('failed', 0)} failed")
    
    return 0


def cancel_agents(args) -> int:
    """Cancel all running agents."""
    import subprocess
    
    logger.info("Cancelling all running agents...")
    
    try:
        subprocess.run(["pkill", "-f", "opencode run"], capture_output=True)
        subprocess.run(["pkill", "-f", "claude code"], capture_output=True)
        print("Cancel signal sent to all agents")
    except Exception as e:
        print(f"Cancel failed: {e}")
    
    return 0


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        # Default to run if no command specified
        args.command = "run"
        # Re-parse with run defaults
        args = parser.parse_args(["run"])
    
    setup_logging(verbose=getattr(args, "verbose", False))
    
    if args.command == "run":
        return asyncio.run(run_processor(args))
    elif args.command == "status":
        return show_status(args)
    elif args.command == "dashboard":
        return show_dashboard(args)
    elif args.command == "history":
        return show_history(args)
    elif args.command == "cancel":
        return cancel_agents(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
