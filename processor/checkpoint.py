"""
Checkpoint Manager for phase-based state persistence.

Enables resuming from last completed phase after timeout/failure.
Phases: RESEARCH → TESTS → EXECUTION → REPORT
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .utils.logger import get_logger

logger = get_logger("checkpoint")


class Phase(str, Enum):
    """Processing phases for an item."""
    INIT = "init"
    RESEARCH = "research"
    TESTS = "tests"
    EXECUTION = "execution"
    REPORT = "report"
    COMPLETE = "complete"

    @classmethod
    def next_phase(cls, current: "Phase") -> "Phase | None":
        """Get the next phase after current."""
        order = [cls.INIT, cls.RESEARCH, cls.TESTS, cls.EXECUTION, cls.REPORT, cls.COMPLETE]
        try:
            idx = order.index(current)
            if idx < len(order) - 1:
                return order[idx + 1]
        except ValueError:
            pass
        return None

    @classmethod
    def from_artifacts(cls, run_dir: Path) -> "Phase":
        """Detect current phase from existing artifacts."""
        if not run_dir.exists():
            return cls.INIT

        # Check for FINAL_REPORT.md
        final_report = run_dir / "FINAL_REPORT.md"
        if final_report.exists() and final_report.stat().st_size > 100:
            return cls.COMPLETE

        # Check for results
        results_dir = run_dir / "results"
        if results_dir.exists():
            result_files = list(results_dir.glob("*_results.json")) + list(results_dir.glob("results.json"))
            if result_files:
                return cls.REPORT  # Ready to generate report

        # Check for test files
        tests_dir = run_dir / "tests"
        if tests_dir.exists():
            test_files = list(tests_dir.glob("*_test.py")) + list(tests_dir.glob("test_*.py"))
            test_files += list(tests_dir.glob("*_test.js")) + list(tests_dir.glob("*.test.js"))
            test_files += list(tests_dir.glob("*_test.rs"))
            if test_files:
                return cls.EXECUTION  # Ready to execute tests

        # Check for research
        research_dir = run_dir / "research"
        if research_dir.exists():
            research_files = list(research_dir.glob("*.md"))
            if research_files:
                return cls.TESTS  # Ready to create tests

        return cls.INIT


@dataclass
class Checkpoint:
    """Checkpoint state for an item run."""
    item_id: str
    phase: Phase
    attempt: int = 1
    started_at: str = ""
    updated_at: str = ""
    elapsed_ms: int = 0
    artifacts: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        d = asdict(self)
        d["phase"] = self.phase.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        """Create from dictionary."""
        data = data.copy()
        data["phase"] = Phase(data["phase"])
        return cls(**data)

    def advance_phase(self) -> bool:
        """Advance to next phase. Returns True if advanced."""
        next_phase = Phase.next_phase(self.phase)
        if next_phase:
            self.phase = next_phase
            self.updated_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def add_artifact(self, phase: str, path: str) -> None:
        """Record an artifact created in a phase."""
        if phase not in self.artifacts:
            self.artifacts[phase] = []
        if path not in self.artifacts[phase]:
            self.artifacts[phase].append(path)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_error(self, error: str) -> None:
        """Record an error."""
        self.errors.append(f"[{datetime.now(timezone.utc).isoformat()}] {error}")
        self.updated_at = datetime.now(timezone.utc).isoformat()


class CheckpointManager:
    """Manages checkpoints for item runs."""

    CHECKPOINT_FILE = ".checkpoint.json"

    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)

    def get_checkpoint_path(self, run_dir: Path) -> Path:
        """Get checkpoint file path for a run directory."""
        return Path(run_dir) / self.CHECKPOINT_FILE

    def load(self, run_dir: Path, item_id: str) -> Checkpoint:
        """Load checkpoint or create new one."""
        checkpoint_path = self.get_checkpoint_path(run_dir)

        if checkpoint_path.exists():
            try:
                data = json.loads(checkpoint_path.read_text())
                checkpoint = Checkpoint.from_dict(data)
                logger.debug(f"Loaded checkpoint for {item_id}: phase={checkpoint.phase.value}")
                return checkpoint
            except Exception as e:
                logger.warning(f"Failed to load checkpoint for {item_id}: {e}")

        # Create new checkpoint, detecting phase from artifacts
        detected_phase = Phase.from_artifacts(run_dir)
        checkpoint = Checkpoint(item_id=item_id, phase=detected_phase)

        if detected_phase != Phase.INIT:
            logger.info(f"Detected existing progress for {item_id}: phase={detected_phase.value}")
            # Scan for existing artifacts
            self._scan_artifacts(run_dir, checkpoint)

        return checkpoint

    def save(self, run_dir: Path, checkpoint: Checkpoint) -> None:
        """Save checkpoint to file."""
        checkpoint_path = self.get_checkpoint_path(run_dir)
        checkpoint.updated_at = datetime.now(timezone.utc).isoformat()

        try:
            Path(run_dir).mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(json.dumps(checkpoint.to_dict(), indent=2))
            logger.debug(f"Saved checkpoint for {checkpoint.item_id}: phase={checkpoint.phase.value}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint for {checkpoint.item_id}: {e}")

    def delete(self, run_dir: Path) -> None:
        """Delete checkpoint file."""
        checkpoint_path = self.get_checkpoint_path(run_dir)
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    def _scan_artifacts(self, run_dir: Path, checkpoint: Checkpoint) -> None:
        """Scan run directory for existing artifacts."""
        run_dir = Path(run_dir)

        # Research artifacts
        research_dir = run_dir / "research"
        if research_dir.exists():
            for f in research_dir.glob("*.md"):
                checkpoint.add_artifact("research", str(f.relative_to(run_dir)))

        # Test artifacts
        tests_dir = run_dir / "tests"
        if tests_dir.exists():
            for pattern in ["*_test.py", "test_*.py", "*_test.js", "*.test.js", "*_test.rs"]:
                for f in tests_dir.glob(pattern):
                    checkpoint.add_artifact("tests", str(f.relative_to(run_dir)))

        # Result artifacts
        results_dir = run_dir / "results"
        if results_dir.exists():
            for f in results_dir.glob("*.json"):
                checkpoint.add_artifact("execution", str(f.relative_to(run_dir)))

    def can_resume(self, run_dir: Path, item_id: str) -> bool:
        """Check if an item can be resumed from checkpoint."""
        checkpoint = self.load(run_dir, item_id)
        return checkpoint.phase not in (Phase.INIT, Phase.COMPLETE)

    def get_resume_instructions(self, checkpoint: Checkpoint) -> str:
        """Generate instructions for resuming from checkpoint."""
        phase = checkpoint.phase

        if phase == Phase.TESTS:
            artifacts = checkpoint.artifacts.get("research", [])
            return f"""
RESUMING FROM CHECKPOINT: Research phase complete.
Existing research artifacts: {', '.join(artifacts) if artifacts else 'None found'}

SKIP research phase. Proceed directly to:
1. Read existing research from research/ directory
2. Create test implementations in tests/
3. Execute tests and save results to results/
4. Generate FINAL_REPORT.md
"""

        elif phase == Phase.EXECUTION:
            test_artifacts = checkpoint.artifacts.get("tests", [])
            return f"""
RESUMING FROM CHECKPOINT: Tests created.
Existing test files: {', '.join(test_artifacts) if test_artifacts else 'None found'}

SKIP research and test creation phases. Proceed directly to:
1. Execute existing tests in tests/ directory
2. Save results to results/
3. Generate FINAL_REPORT.md
"""

        elif phase == Phase.REPORT:
            result_artifacts = checkpoint.artifacts.get("execution", [])
            return f"""
RESUMING FROM CHECKPOINT: Tests executed.
Existing result files: {', '.join(result_artifacts) if result_artifacts else 'None found'}

SKIP all phases except report generation. Proceed directly to:
1. Read results from results/ directory
2. Generate FINAL_REPORT.md with all findings
"""

        return ""  # No special instructions for INIT or COMPLETE


def detect_phase_completion(run_dir: Path, phase: Phase) -> bool:
    """Check if a phase has completed based on artifacts."""
    run_dir = Path(run_dir)

    if phase == Phase.RESEARCH:
        research_dir = run_dir / "research"
        if research_dir.exists():
            return bool(list(research_dir.glob("*.md")))
        return False

    elif phase == Phase.TESTS:
        tests_dir = run_dir / "tests"
        if tests_dir.exists():
            patterns = ["*_test.py", "test_*.py", "*_test.js", "*.test.js", "*_test.rs"]
            for pattern in patterns:
                if list(tests_dir.glob(pattern)):
                    return True
        return False

    elif phase == Phase.EXECUTION:
        results_dir = run_dir / "results"
        if results_dir.exists():
            return bool(list(results_dir.glob("*.json")))
        return False

    elif phase == Phase.REPORT:
        final_report = run_dir / "FINAL_REPORT.md"
        return final_report.exists() and final_report.stat().st_size > 100

    return False
