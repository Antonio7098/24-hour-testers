"""
Tests for robustness improvements:
- Phase-based checkpoints
- Dynamic timeout scaling
- Progressive retry
- Output monitoring
- Early warning system
"""

import tempfile
from pathlib import Path

import pytest

from ..config import ProcessorConfig, TimeoutConfig, RetryConfig
from ..checkpoint import CheckpointManager, Checkpoint, Phase, detect_phase_completion


class TestTimeoutConfig:
    """Tests for dynamic timeout scaling."""

    def test_p0_critical_timeout(self):
        """P0 Critical items should get 15 minutes."""
        config = TimeoutConfig()
        timeout = config.get_timeout_for_priority("P0 Critical")
        assert timeout == 900000  # 15 min

    def test_p1_high_timeout(self):
        """P1 High items should get 12 minutes."""
        config = TimeoutConfig()
        timeout = config.get_timeout_for_priority("P1 High")
        assert timeout == 720000  # 12 min

    def test_p1_medium_timeout(self):
        """P1 Medium items should get 10 minutes."""
        config = TimeoutConfig()
        timeout = config.get_timeout_for_priority("P1 Medium")
        assert timeout == 600000  # 10 min

    def test_low_priority_timeout(self):
        """Low priority items should get 10 minutes."""
        config = TimeoutConfig()
        timeout = config.get_timeout_for_priority("Low")
        assert timeout == 600000  # 10 min

    def test_default_timeout(self):
        """Unknown priorities should get default timeout."""
        config = TimeoutConfig()
        timeout = config.get_timeout_for_priority("Unknown")
        assert timeout == 600000  # 10 min default

    def test_retry_multiplier(self):
        """Retry attempts should get more time."""
        config = TimeoutConfig()
        base = config.get_timeout_for_priority("P1 High", attempt=1)
        retry = config.get_timeout_for_priority("P1 High", attempt=2)
        assert retry > base
        assert retry == int(base * 1.2)  # 20% more

    def test_third_attempt_timeout(self):
        """Third attempt should get even more time."""
        config = TimeoutConfig()
        base = config.get_timeout_for_priority("P1 High", attempt=1)
        third = config.get_timeout_for_priority("P1 High", attempt=3)
        # 1.2^2 = 1.44
        assert third == int(base * 1.44)


class TestRetryConfig:
    """Tests for progressive retry configuration."""

    def test_default_max_retries(self):
        """Default should be 3 retries."""
        config = RetryConfig()
        assert config.max_retries == 3

    def test_checkpoint_on_retry_enabled(self):
        """Checkpoint resume should be enabled by default."""
        config = RetryConfig()
        assert config.use_checkpoint_on_retry is True

    def test_simplified_mode_on_final_retry(self):
        """Simplified mode should be enabled by default."""
        config = RetryConfig()
        assert config.simplified_mode_on_final_retry is True


class TestPhase:
    """Tests for Phase enum."""

    def test_phase_order(self):
        """Phases should progress in correct order."""
        assert Phase.next_phase(Phase.INIT) == Phase.RESEARCH
        assert Phase.next_phase(Phase.RESEARCH) == Phase.TESTS
        assert Phase.next_phase(Phase.TESTS) == Phase.EXECUTION
        assert Phase.next_phase(Phase.EXECUTION) == Phase.REPORT
        assert Phase.next_phase(Phase.REPORT) == Phase.COMPLETE
        assert Phase.next_phase(Phase.COMPLETE) is None

    def test_detect_phase_from_empty_dir(self):
        """Empty directory should be INIT phase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            phase = Phase.from_artifacts(Path(tmpdir))
            assert phase == Phase.INIT

    def test_detect_phase_from_research(self):
        """Directory with research should be TESTS phase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            research_dir = Path(tmpdir) / "research"
            research_dir.mkdir()
            (research_dir / "understanding.md").write_text("# Research")

            phase = Phase.from_artifacts(Path(tmpdir))
            assert phase == Phase.TESTS

    def test_detect_phase_from_tests(self):
        """Directory with tests should be EXECUTION phase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tests_dir = Path(tmpdir) / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_example.py").write_text("def test_foo(): pass")

            phase = Phase.from_artifacts(Path(tmpdir))
            assert phase == Phase.EXECUTION

    def test_detect_phase_from_results(self):
        """Directory with results should be REPORT phase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            results_dir.mkdir()
            (results_dir / "results.json").write_text("{}")

            phase = Phase.from_artifacts(Path(tmpdir))
            assert phase == Phase.REPORT

    def test_detect_phase_complete(self):
        """Directory with FINAL_REPORT.md should be COMPLETE phase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "FINAL_REPORT.md").write_text("# Final Report\n" + "x" * 200)

            phase = Phase.from_artifacts(Path(tmpdir))
            assert phase == Phase.COMPLETE


class TestCheckpoint:
    """Tests for Checkpoint dataclass."""

    def test_checkpoint_creation(self):
        """Checkpoint should be created with defaults."""
        cp = Checkpoint(item_id="TEST-001", phase=Phase.INIT)
        assert cp.item_id == "TEST-001"
        assert cp.phase == Phase.INIT
        assert cp.attempt == 1
        assert cp.started_at != ""
        assert cp.artifacts == {}

    def test_checkpoint_advance_phase(self):
        """Checkpoint should advance to next phase."""
        cp = Checkpoint(item_id="TEST-001", phase=Phase.INIT)
        assert cp.advance_phase() is True
        assert cp.phase == Phase.RESEARCH

    def test_checkpoint_add_artifact(self):
        """Checkpoint should track artifacts."""
        cp = Checkpoint(item_id="TEST-001", phase=Phase.RESEARCH)
        cp.add_artifact("research", "research/summary.md")
        assert "research" in cp.artifacts
        assert "research/summary.md" in cp.artifacts["research"]

    def test_checkpoint_serialization(self):
        """Checkpoint should serialize to/from dict."""
        cp = Checkpoint(item_id="TEST-001", phase=Phase.TESTS)
        cp.add_artifact("research", "research/summary.md")

        d = cp.to_dict()
        assert d["item_id"] == "TEST-001"
        assert d["phase"] == "tests"

        cp2 = Checkpoint.from_dict(d)
        assert cp2.item_id == cp.item_id
        assert cp2.phase == cp.phase


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def test_load_creates_new_checkpoint(self):
        """Loading non-existent checkpoint should create new one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            run_dir = Path(tmpdir) / "runs" / "TEST-001"
            run_dir.mkdir(parents=True)

            cp = manager.load(run_dir, "TEST-001")
            assert cp.item_id == "TEST-001"
            assert cp.phase == Phase.INIT

    def test_save_and_load_checkpoint(self):
        """Checkpoint should be saved and loadable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            run_dir = Path(tmpdir) / "runs" / "TEST-001"
            run_dir.mkdir(parents=True)

            cp = Checkpoint(item_id="TEST-001", phase=Phase.TESTS)
            cp.add_artifact("research", "research/summary.md")
            manager.save(run_dir, cp)

            cp2 = manager.load(run_dir, "TEST-001")
            assert cp2.phase == Phase.TESTS
            assert "research" in cp2.artifacts

    def test_delete_checkpoint(self):
        """Checkpoint should be deletable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            run_dir = Path(tmpdir) / "runs" / "TEST-001"
            run_dir.mkdir(parents=True)

            cp = Checkpoint(item_id="TEST-001", phase=Phase.TESTS)
            manager.save(run_dir, cp)

            checkpoint_file = manager.get_checkpoint_path(run_dir)
            assert checkpoint_file.exists()

            manager.delete(run_dir)
            assert not checkpoint_file.exists()

    def test_can_resume(self):
        """can_resume should return True for non-INIT checkpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            run_dir = Path(tmpdir) / "runs" / "TEST-001"
            run_dir.mkdir(parents=True)

            # Create research artifact to trigger TESTS phase detection
            research_dir = run_dir / "research"
            research_dir.mkdir()
            (research_dir / "understanding.md").write_text("# Research")

            assert manager.can_resume(run_dir, "TEST-001") is True

    def test_get_resume_instructions_tests_phase(self):
        """Resume instructions should be generated for TESTS phase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            cp = Checkpoint(item_id="TEST-001", phase=Phase.TESTS)
            cp.add_artifact("research", "research/summary.md")

            instructions = manager.get_resume_instructions(cp)
            assert "RESUMING FROM CHECKPOINT" in instructions
            assert "Research phase complete" in instructions

    def test_get_resume_instructions_execution_phase(self):
        """Resume instructions should be generated for EXECUTION phase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))

            cp = Checkpoint(item_id="TEST-001", phase=Phase.EXECUTION)
            cp.add_artifact("tests", "tests/test_example.py")

            instructions = manager.get_resume_instructions(cp)
            assert "RESUMING FROM CHECKPOINT" in instructions
            assert "Tests created" in instructions


class TestProcessorConfigWithRobustness:
    """Tests for ProcessorConfig with robustness settings."""

    def test_config_has_timeouts(self):
        """ProcessorConfig should have TimeoutConfig."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            config = ProcessorConfig(repo_root=tmpdir)
            assert hasattr(config, "timeouts")
            assert isinstance(config.timeouts, TimeoutConfig)

    def test_config_has_checkpoints_enabled(self):
        """ProcessorConfig should have checkpoints enabled by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            config = ProcessorConfig(repo_root=tmpdir)
            assert config.enable_checkpoints is True

    def test_config_custom_timeout(self):
        """ProcessorConfig should accept custom TimeoutConfig."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            custom_timeouts = TimeoutConfig(p0_critical_ms=1800000)  # 30 min
            config = ProcessorConfig(repo_root=tmpdir, timeouts=custom_timeouts)
            assert config.timeouts.p0_critical_ms == 1800000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
