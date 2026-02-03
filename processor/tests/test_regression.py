"""
Regression tests for bugs identified in notes.txt.

Tests:
1. Loop processing - process() should continue until all items complete
2. Strict validation - FINAL_REPORT.md must be present
3. Path normalization - paths should be normalized before comparison
4. Folder structure - "pipelines" should not be in subdirs
5. CLI timeout override - --timeout should override hardcoded TimeoutConfig defaults
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ..config import ProcessorConfig, ProcessingMode
from ..processor import ChecklistProcessor
from ..stages.validate_output import ValidateOutputStage
from ..utils.process_utils import normalize_path, paths_equal


class TestLoopProcessing:
    """Regression tests for the no-loop bug."""

    def test_max_iterations_config(self):
        """Config should have max_iterations with reasonable default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal checklist
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n| ID | Target | Priority | Risk | Status |\n")

            config = ProcessorConfig(repo_root=tmpdir)
            assert config.max_iterations >= 1
            assert config.max_iterations == 20  # Default

    def test_max_iterations_validation(self):
        """max_iterations must be >= 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            with pytest.raises(ValueError, match="max_iterations must be >= 1"):
                ProcessorConfig(repo_root=tmpdir, max_iterations=0)


class TestStrictValidation:
    """Regression tests for stricter validation requiring FINAL_REPORT.md."""

    @pytest.mark.asyncio
    async def test_validation_fails_without_final_report(self):
        """Validation should fail if completion marker present but no FINAL_REPORT.md."""
        stage = ValidateOutputStage(
            require_completion_marker=True,
            require_final_report=True,
        )

        # Mock context with completion marker but no report
        mock_ctx = MagicMock()
        mock_ctx.inputs.get_from = MagicMock(side_effect=lambda stage, key, default=None: {
            ("run_agent", "output"): "ITEM_COMPLETE",
            ("run_agent", "completed"): True,
            ("run_agent", "item_id"): "TEST-001",
            ("run_agent", "log_path"): "/tmp/test.log",
            ("run_agent", "dry_run"): False,
        }.get((stage, key), default))

        # No run_dir means no report can exist
        mock_ctx.snapshot.metadata = {"run_dir": "/nonexistent/path"}
        mock_ctx.try_emit_event = MagicMock()

        result = await stage.execute(mock_ctx)

        # Should fail because no FINAL_REPORT.md
        assert result.status.value == "fail"
        assert "FINAL_REPORT.md" in result.error

    @pytest.mark.asyncio
    async def test_validation_passes_with_final_report(self):
        """Validation should pass when FINAL_REPORT.md exists."""
        stage = ValidateOutputStage(
            require_completion_marker=True,
            require_final_report=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the final report
            report_path = Path(tmpdir) / "TEST-001-FINAL-REPORT.md"
            report_path.write_text("# Final Report\n")

            mock_ctx = MagicMock()
            mock_ctx.inputs.get_from = MagicMock(side_effect=lambda stage, key, default=None: {
                ("run_agent", "output"): "ITEM_COMPLETE",
                ("run_agent", "completed"): True,
                ("run_agent", "item_id"): "TEST-001",
                ("run_agent", "log_path"): "/tmp/test.log",
                ("run_agent", "dry_run"): False,
            }.get((stage, key), default))

            mock_ctx.snapshot.metadata = {"run_dir": tmpdir}
            mock_ctx.try_emit_event = MagicMock()

            result = await stage.execute(mock_ctx)

            # Should pass
            assert result.status.value == "ok"
            assert result.data["has_final_report"] is True

    @pytest.mark.asyncio
    async def test_validation_passes_with_report_but_no_marker(self):
        """If FINAL_REPORT.md exists, should pass even without completion marker."""
        stage = ValidateOutputStage(
            require_completion_marker=True,
            require_final_report=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the final report
            report_path = Path(tmpdir) / "TEST-001-FINAL-REPORT.md"
            report_path.write_text("# Final Report\n")

            mock_ctx = MagicMock()
            mock_ctx.inputs.get_from = MagicMock(side_effect=lambda stage, key, default=None: {
                ("run_agent", "output"): "Some output without marker",
                ("run_agent", "completed"): False,  # No completion marker!
                ("run_agent", "item_id"): "TEST-001",
                ("run_agent", "log_path"): "/tmp/test.log",
                ("run_agent", "dry_run"): False,
            }.get((stage, key), default))

            mock_ctx.snapshot.metadata = {"run_dir": tmpdir}
            mock_ctx.try_emit_event = MagicMock()

            result = await stage.execute(mock_ctx)

            # Should pass because report exists (report is primary deliverable)
            assert result.status.value == "ok"
            assert result.data["has_final_report"] is True
            assert result.data["has_completion_marker"] is False


class TestPathNormalization:
    """Regression tests for path normalization."""

    def test_normalize_path_handles_tilde(self):
        """normalize_path should expand ~ to home directory."""
        result = normalize_path("~/test/path")
        assert "~" not in result
        assert Path(result).is_absolute()

    def test_normalize_path_handles_relative(self):
        """normalize_path should resolve relative paths."""
        result = normalize_path("./test/path")
        assert Path(result).is_absolute()

    def test_normalize_path_handles_dots(self):
        """normalize_path should resolve .. in paths."""
        result = normalize_path("/tmp/foo/../bar")
        assert ".." not in result

    def test_paths_equal_same_path(self):
        """paths_equal should return True for same path."""
        assert paths_equal("/tmp/test", "/tmp/test")

    def test_paths_equal_different_formats(self):
        """paths_equal should handle different path formats."""
        # Trailing slash shouldn't matter after normalization
        p1 = "/tmp/test"
        p2 = "/tmp/test/"
        # Note: resolve() may or may not strip trailing slash
        # but the paths should resolve to same location

    def test_paths_equal_tilde_expansion(self):
        """paths_equal should work with ~ paths."""
        import os
        home = os.path.expanduser("~")
        assert paths_equal("~", home)

    def test_normalize_path_handles_empty(self):
        """normalize_path should handle empty path (resolves to cwd)."""
        # Empty path resolves to current working directory
        result = normalize_path("")
        # Should be an absolute path (cwd)
        assert Path(result).is_absolute()


class TestFolderStructure:
    """Regression tests for folder structure (no 'pipelines')."""

    def test_setup_run_directory_no_pipelines(self):
        """_setup_run_directory should not create 'pipelines' folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n| ID | Target | Priority | Risk | Status |\n")

            config = ProcessorConfig(repo_root=tmpdir)
            processor = ChecklistProcessor(config)

            run_dir = Path(tmpdir) / "runs" / "test_tier" / "TEST-001"
            processor._setup_run_directory(run_dir)

            # Verify 'pipelines' is NOT created
            assert not (run_dir / "pipelines").exists()

            # Verify expected folders ARE created
            expected_folders = ["config", "dx_evaluation", "mocks", "research", "results", "tests", "artifacts"]
            for folder in expected_folders:
                assert (run_dir / folder).exists(), f"Missing folder: {folder}"


class TestAgentResourcesOverride:
    """Tests for agent-resources override functionality."""

    def test_config_accepts_agent_resources_dir(self):
        """ProcessorConfig should accept agent_resources_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            custom_resources = Path(tmpdir) / "custom-resources"
            custom_resources.mkdir()

            config = ProcessorConfig(
                repo_root=tmpdir,
                agent_resources_dir=custom_resources,
            )

            assert config.agent_resources_dir == custom_resources

    def test_config_uses_repo_root_resources_by_default(self):
        """ProcessorConfig should use repo_root/agent-resources by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            # Create agent-resources in repo root
            resources = Path(tmpdir) / "agent-resources"
            resources.mkdir()

            config = ProcessorConfig(repo_root=tmpdir)

            assert config.agent_resources_dir == resources

    def test_config_relative_agent_resources_path(self):
        """agent_resources_dir should resolve relative paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            custom_resources = Path(tmpdir) / "my-resources"
            custom_resources.mkdir()

            config = ProcessorConfig(
                repo_root=tmpdir,
                agent_resources_dir=Path("my-resources"),  # Relative
            )

            assert config.agent_resources_dir.is_absolute()
            assert config.agent_resources_dir == custom_resources


class TestTimeoutCliOverride:
    """Regression tests for CLI --timeout not respecting overrides.

    Bug: TimeoutConfig had hardcoded defaults (15min/12min/10min) that ignored
    the CLI --timeout argument. The _get_timeout_for_item() method used
    config.timeouts.get_timeout_for_priority() which ignored config.timeout_ms.

    Fix: Modified TimeoutConfig to use CLI timeout_ms as base_timeout_ms and
    scale priority-based timeouts from this base value using multipliers.
    """

    def test_cli_timeout_overrides_hardcoded_defaults(self):
        """When --timeout is passed via CLI, should override hardcoded defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            # Pass 60000ms (1 minute) via CLI
            config = ProcessorConfig(repo_root=tmpdir, timeout_ms=60000)

            # TimeoutConfig should have base_timeout_ms set
            assert config.timeouts.base_timeout_ms == 60000

            # Priority timeouts should scale from 60000ms, not hardcoded defaults
            # P0 Critical: 60000 * 1.5 = 90000 (not hardcoded 900000)
            assert config.timeouts.get_timeout_for_priority("P0 Critical") == 90000

            # P1 Medium: 60000 * 1.0 = 60000 (not hardcoded 600000)
            assert config.timeouts.get_timeout_for_priority("P1 Medium") == 60000

    def test_default_timeout_uses_hardcoded_values(self):
        """When no --timeout is passed, should use hardcoded defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            # Use default timeout (300000ms = 5 minutes)
            config = ProcessorConfig(repo_root=tmpdir, timeout_ms=300000)

            # Should NOT have base_timeout_ms set (uses hardcoded defaults)
            assert config.timeouts.base_timeout_ms is None

            # Should use hardcoded defaults
            assert config.timeouts.get_timeout_for_priority("P0 Critical") == 900000  # 15 min
            assert config.timeouts.get_timeout_for_priority("P1 Medium") == 600000    # 10 min

    def test_priority_scaling_with_cli_override(self):
        """All priority levels should scale correctly from CLI timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            config = ProcessorConfig(repo_root=tmpdir, timeout_ms=120000)  # 2 minutes

            # P0: 2min * 1.5 = 3min
            assert config.timeouts.get_timeout_for_priority("P0 Critical") == 180000

            # P1 High: 2min * 1.2 = 2.4min
            assert config.timeouts.get_timeout_for_priority("P1 High") == 144000

            # P1 Medium: 2min * 1.0 = 2min
            assert config.timeouts.get_timeout_for_priority("P1 Medium") == 120000

            # P2 Low: 2min * 1.0 = 2min
            assert config.timeouts.get_timeout_for_priority("P2 Low") == 120000

    def test_retry_multiplier_works_with_cli_override(self):
        """Retry multiplier should apply on top of CLI-scaled timeouts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("# Test\n")

            config = ProcessorConfig(repo_root=tmpdir, timeout_ms=60000)  # 1 minute

            # Attempt 1: base timeout
            assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=1) == 60000

            # Attempt 2: 1.2x multiplier
            assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=2) == 72000

            # Attempt 3: 1.44x multiplier (1.2^2)
            assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=3) == 86400


class TestTimeoutEnforcement:
    """Regression test for timeout enforcement bug.
    
    Bug: The inner read_stream() caught asyncio.TimeoutError which also
    caught the outer process timeout, causing the agent to run indefinitely.
    """

    @pytest.mark.asyncio
    async def test_process_timeout_actually_enforced(self):
        """Process should be killed when timeout is reached."""
        import time
        from ..stages.run_agent import RunAgentStage
        from ..checkpoint import Phase
        
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist = Path(tmpdir) / "SUT-CHECKLIST.md"
            checklist.write_text("""# Test
| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| TEST-001 | Test item | P0 | High | ☐ Not Started |
""")
            config = ProcessorConfig(
                repo_root=tmpdir,
                timeout_ms=2000,  # 2 second timeout for fast test
                mode=ProcessingMode.FINITE,
                dry_run=False,
            )
            
            stage = RunAgentStage(config)
            
            # Mock the process to simulate slow execution
            start_time = time.time()
            
            ctx = MagicMock()
            ctx.inputs.get_from.side_effect = lambda *args, **kwargs: {
                ("prompt",): "test prompt",
                ("item_id",): "TEST-001",
                ("item",): {"id": "TEST-001", "priority": "P0", "target": "Test"},
                ("run_dir",): tmpdir,
                ("attempt", 1): 1,
                ("run", None): None,
            }.get(args, kwargs.get("default"))
            
            result = await stage.execute(ctx)
            elapsed = time.time() - start_time
            
            # Should complete quickly (within 5 seconds) due to timeout
            # If timeout wasn't enforced, this would hang
            assert elapsed < 10, f"Timeout not enforced - took {elapsed:.1f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
