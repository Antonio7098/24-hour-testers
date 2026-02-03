"""
Run Manager - centralized state management for all agent runs.

Single source of truth for processing state, enables observability.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .models import AgentRun, AgentStatus, ChecklistItem, SessionSummary
from .utils.logger import get_logger

logger = get_logger("run_manager")


class RunManager:
    """
    Centralized state management for agent runs.
    
    Features:
    - Run lifecycle tracking
    - State persistence
    - Event emission for observability
    - Session management
    """
    
    def __init__(self, state_dir: Path, session_id: str | None = None):
        self.state_dir = Path(state_dir)
        self.session_id = session_id or f"session-{int(datetime.now().timestamp() * 1000)}"
        
        self._runs: dict[str, AgentRun] = {}
        self._runs_by_item: dict[str, AgentRun] = {}
        self._listeners: list[Callable[[dict], None]] = []
        
        self.status = "idle"
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        
        self._ensure_state_dir()
        self._load_persisted_state()
    
    def _ensure_state_dir(self) -> None:
        """Ensure state directory exists."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_persisted_state(self) -> None:
        """Load any persisted state from previous sessions."""
        state_path = self.state_dir / "active-runs.json"
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text())
                self._previous_session = data
                logger.debug(f"Loaded previous session: {data.get('sessionId')}")
            except Exception as e:
                logger.warning(f"Failed to load persisted state: {e}")
    
    def persist_state(self) -> None:
        """Persist current state to disk."""
        state = {
            "sessionId": self.session_id,
            "status": self.status,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "runs": [run.to_dict() for run in self._runs.values()],
            "summary": self.get_summary().to_dict(),
        }
        
        # Write active runs
        state_path = self.state_dir / "active-runs.json"
        state_path.write_text(json.dumps(state, indent=2))
        
        # Write session log
        session_log_path = self.state_dir / f"{self.session_id}.json"
        session_log_path.write_text(json.dumps(state, indent=2))
    
    def create_run(self, item: ChecklistItem, run_dir: Path | None = None, max_attempts: int = 3) -> AgentRun:
        """Create and track a new run."""
        run = AgentRun.create(item, run_dir=run_dir, max_attempts=max_attempts)
        
        self._runs[run.id] = run
        self._runs_by_item[item.id] = run
        
        # Subscribe to run events
        run.subscribe(lambda event: self._on_run_event(event))
        
        self._emit("run:created", {"run": run.to_dict()})
        self.persist_state()
        
        return run
    
    def get_run(self, run_id: str) -> AgentRun | None:
        """Get a run by ID."""
        return self._runs.get(run_id)
    
    def get_run_by_item(self, item_id: str) -> AgentRun | None:
        """Get a run by item ID."""
        return self._runs_by_item.get(item_id)
    
    def get_active_runs(self) -> list[AgentRun]:
        """Get all active runs."""
        return [run for run in self._runs.values() if run.is_active()]
    
    def get_completed_runs(self) -> list[AgentRun]:
        """Get all completed runs."""
        return [run for run in self._runs.values() if run.status == AgentStatus.COMPLETED]
    
    def get_failed_runs(self) -> list[AgentRun]:
        """Get all failed runs."""
        return [run for run in self._runs.values() if run.status == AgentStatus.FAILED]
    
    def get_all_runs(self) -> list[AgentRun]:
        """Get all runs."""
        return list(self._runs.values())
    
    def start(self) -> None:
        """Start a processing session."""
        self.status = "running"
        self.started_at = datetime.now()
        self._emit("session:start", {"sessionId": self.session_id})
        self.persist_state()
        logger.info(f"Session started: {self.session_id}")
    
    def complete(self) -> None:
        """Mark session as complete."""
        self.status = "completed"
        self.completed_at = datetime.now()
        summary = self.get_summary()
        self._emit("session:complete", {"sessionId": self.session_id, "summary": summary.to_dict()})
        self.persist_state()
        logger.info(f"Session completed: {self.session_id}")
    
    def fail(self, error: Exception) -> None:
        """Mark session as failed."""
        self.status = "failed"
        self.completed_at = datetime.now()
        self._emit("session:fail", {"sessionId": self.session_id, "error": str(error)})
        self.persist_state()
        logger.error(f"Session failed: {self.session_id} - {error}")
    
    def get_summary(self) -> SessionSummary:
        """Get session summary."""
        runs = list(self._runs.values())
        
        # Only count the latest run per item for accurate active/completed counts
        latest_per_item = {}
        for r in runs:
            item_id = r.item_id
            if item_id not in latest_per_item or r.started_at > latest_per_item[item_id].started_at:
                latest_per_item[item_id] = r
        
        latest_runs = list(latest_per_item.values())
        
        return SessionSummary(
            session_id=self.session_id,
            status=self.status,
            total=len(latest_runs),
            pending=len([r for r in latest_runs if r.status == AgentStatus.PENDING]),
            active=len([r for r in latest_runs if r.is_active()]),
            completed=len([r for r in latest_runs if r.status == AgentStatus.COMPLETED]),
            failed=len([r for r in latest_runs if r.status == AgentStatus.FAILED]),
            timeout=len([r for r in latest_runs if r.status == AgentStatus.TIMEOUT]),
        )
    
    def get_status_display(self) -> str:
        """Get human-readable status display."""
        summary = self.get_summary()
        active = self.get_active_runs()
        
        lines = [
            f"Session: {self.session_id}",
            f"Status: {self.status}",
            f"Progress: {summary.completed}/{summary.total} completed, {summary.failed} failed",
            "",
        ]
        
        if active:
            lines.append("Active Agents:")
            for run in active:
                duration = run.get_duration_ms() // 1000
                lines.append(f"  • {run.item_id}: {run.stage.value} ({duration}s) [attempt {run.attempt + 1}/{run.max_attempts}]")
        
        return "\n".join(lines)
    
    def subscribe(self, listener: Callable[[dict], None]) -> Callable[[], None]:
        """Subscribe to manager events. Returns unsubscribe function."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)
    
    def _emit(self, event: str, data: dict) -> None:
        """Emit an event to all listeners."""
        for listener in self._listeners:
            try:
                listener({"event": event, **data})
            except Exception as e:
                logger.warning(f"Listener error: {e}")
    
    def _on_run_event(self, event: dict) -> None:
        """Handle events from individual runs."""
        self._emit("run:update", event)
        self.persist_state()
    
    @staticmethod
    def get_session_history(state_dir: Path) -> list[dict[str, Any]]:
        """Get historical sessions from state directory."""
        state_dir = Path(state_dir)
        if not state_dir.exists():
            return []
        
        sessions = []
        for f in state_dir.glob("session-*.json"):
            try:
                data = json.loads(f.read_text())
                data["file"] = f.name
                data["mtime"] = datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                sessions.append(data)
            except Exception:
                pass
        
        sessions.sort(key=lambda x: x.get("startedAt", ""), reverse=True)
        return sessions
