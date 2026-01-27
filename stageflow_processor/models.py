"""
Data models for the Checklist Processor.

Immutable data structures following SOLID principles.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


class AgentStatus(str, Enum):
    """Status of an agent run."""
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class RunStage(str, Enum):
    """Stages of a run lifecycle."""
    INIT = "initializing"
    PROMPT_BUILD = "building_prompt"
    SPAWNING = "spawning_process"
    PROCESSING = "processing"
    WRITING_OUTPUT = "writing_output"
    VALIDATING = "validating_completion"
    CLEANUP = "cleanup"
    DONE = "done"


@dataclass(frozen=True)
class ChecklistItem:
    """Immutable representation of a checklist item."""
    id: str
    target: str
    priority: str
    risk: str
    status: str
    tier: str = ""
    section: str = ""
    
    def is_completed(self) -> bool:
        """Check if item is marked as completed."""
        return "✅" in self.status
    
    def is_failed(self) -> bool:
        """Check if item is marked as failed."""
        return "❌" in self.status
    
    def is_pending(self) -> bool:
        """Check if item needs processing."""
        return not self.is_completed() and not self.is_failed()
    
    def with_status(self, new_status: str) -> "ChecklistItem":
        """Create a new item with updated status."""
        return ChecklistItem(
            id=self.id,
            target=self.target,
            priority=self.priority,
            risk=self.risk,
            status=new_status,
            tier=self.tier,
            section=self.section,
        )


@dataclass
class AgentRun:
    """
    Mutable state for tracking an agent run.
    
    Provides observability hooks for status changes.
    """
    id: str
    item_id: str
    item: ChecklistItem
    run_dir: Path | None = None
    
    # State
    status: AgentStatus = AgentStatus.PENDING
    stage: RunStage = RunStage.INIT
    attempt: int = 0
    max_attempts: int = 3
    
    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_activity: datetime = field(default_factory=datetime.now)
    
    # Output
    output: str = ""
    error: str | None = None
    pid: int | None = None
    log_path: Path | None = None
    
    # Event listeners
    _listeners: list = field(default_factory=list, repr=False)
    
    @classmethod
    def create(cls, item: ChecklistItem, run_dir: Path | None = None, max_attempts: int = 3) -> "AgentRun":
        """Factory method to create a new run."""
        return cls(
            id=f"{item.id}-{int(datetime.now().timestamp() * 1000)}",
            item_id=item.id,
            item=item,
            run_dir=run_dir,
            max_attempts=max_attempts,
        )
    
    def set_status(self, status: AgentStatus, error: str | None = None) -> None:
        """Update status and notify listeners."""
        prev = self.status
        self.status = status
        self.error = error
        self.last_activity = datetime.now()
        
        if status == AgentStatus.RUNNING and self.started_at is None:
            self.started_at = datetime.now()
        
        terminal_statuses = {AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.TIMEOUT, AgentStatus.CANCELLED}
        if status in terminal_statuses:
            self.completed_at = datetime.now()
        
        self._notify("status", {"prev": prev.value, "current": status.value, "error": error})
    
    def set_stage(self, stage: RunStage) -> None:
        """Update stage and notify listeners."""
        prev = self.stage
        self.stage = stage
        self.last_activity = datetime.now()
        self._notify("stage", {"prev": prev.value, "current": stage.value})
    
    def append_output(self, chunk: str) -> None:
        """Append to output buffer."""
        self.output += chunk
        self.last_activity = datetime.now()
        self._notify("output", {"chunk": chunk, "total_length": len(self.output)})
    
    def increment_attempt(self) -> None:
        """Increment retry attempt counter."""
        self.attempt += 1
        self._notify("retry", {"attempt": self.attempt, "max_attempts": self.max_attempts})
    
    def get_duration_ms(self) -> int:
        """Get run duration in milliseconds."""
        if self.started_at is None:
            return 0
        end = self.completed_at or datetime.now()
        return int((end - self.started_at).total_seconds() * 1000)
    
    def is_terminal(self) -> bool:
        """Check if run is in a terminal state."""
        return self.status in {AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.TIMEOUT, AgentStatus.CANCELLED}
    
    def is_active(self) -> bool:
        """Check if run is currently active."""
        return self.status in {AgentStatus.STARTING, AgentStatus.RUNNING, AgentStatus.RETRYING}
    
    def subscribe(self, listener) -> callable:
        """Subscribe to run events. Returns unsubscribe function."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)
    
    def _notify(self, event: str, data: dict) -> None:
        """Notify all listeners of an event."""
        for listener in self._listeners:
            try:
                listener({"event": event, "run": self, "data": data})
            except Exception:
                pass  # Don't let listener errors break the run
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item": {
                "id": self.item.id,
                "target": self.item.target,
                "priority": self.item.priority,
                "risk": self.item.risk,
                "status": self.item.status,
                "tier": self.item.tier,
            },
            "status": self.status.value,
            "stage": self.stage.value,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.get_duration_ms(),
            "error": self.error,
            "pid": self.pid,
            "run_dir": str(self.run_dir) if self.run_dir else None,
            "log_path": str(self.log_path) if self.log_path else None,
            "output_length": len(self.output),
        }


@dataclass
class ProcessingResult:
    """Result of processing a batch of items."""
    processed: int = 0
    completed: int = 0
    failed: int = 0
    dry_run: bool = False
    runs: list[AgentRun] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "completed": self.completed,
            "failed": self.failed,
            "dry_run": self.dry_run,
        }


@dataclass
class SessionSummary:
    """Summary of a processing session."""
    session_id: str
    status: str
    total: int = 0
    pending: int = 0
    active: int = 0
    completed: int = 0
    failed: int = 0
    timeout: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "total": self.total,
            "pending": self.pending,
            "active": self.active,
            "completed": self.completed,
            "failed": self.failed,
            "timeout": self.timeout,
        }
