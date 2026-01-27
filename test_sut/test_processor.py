"""
Comprehensive test suite for the Stageflow Checklist Processor.

Tests cover:
- Configuration validation (fail-fast)
- Checklist parsing
- Pipeline execution
- Retry logic
- Observability
- Error handling
- State persistence
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from uuid import uuid4

# Add parent directory to path to import stageflow_processor
sys.path.insert(0, str(Path(__file__).parent.parent))

from stageflow_processor.config import ProcessorConfig, ProcessingMode, AgentRuntime, RetryConfig
from stageflow_processor.models import ChecklistItem, AgentRun, AgentStatus, RunStage
from stageflow_processor.utils.checklist_parser import ChecklistParser
from stageflow_processor.run_manager import RunManager
from stageflow_processor.processor import ChecklistProcessor


class TestResults:
    """Collects test results."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def record(self, name: str, passed: bool, error: str = None):
        if passed:
            self.passed += 1
            print(f"  ✅ {name}")
        else:
            self.failed += 1
            self.errors.append((name, error))
            print(f"  ❌ {name}: {error}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Test Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailed tests:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        return self.failed == 0


results = TestResults()


# ============================================================================
# Configuration Tests
# ============================================================================

def test_config_validation():
    """Test that configuration validates correctly."""
    print("\n📋 Configuration Tests")
    
    # Test valid config
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ProcessorConfig(
                repo_root=Path(tmpdir),
                batch_size=5,
                mode=ProcessingMode.FINITE,
            )
            results.record("Valid config creates successfully", True)
    except Exception as e:
        results.record("Valid config creates successfully", False, str(e))
    
    # Test invalid batch size
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ProcessorConfig(
                repo_root=Path(tmpdir),
                batch_size=0,  # Invalid
            )
            results.record("Invalid batch_size raises error", False, "Should have raised ValueError")
    except ValueError:
        results.record("Invalid batch_size raises error", True)
    except Exception as e:
        results.record("Invalid batch_size raises error", False, f"Wrong exception: {e}")
    
    # Test invalid timeout
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ProcessorConfig(
                repo_root=Path(tmpdir),
                timeout_ms=100,  # Too low
            )
            results.record("Invalid timeout_ms raises error", False, "Should have raised ValueError")
    except ValueError:
        results.record("Invalid timeout_ms raises error", True)
    except Exception as e:
        results.record("Invalid timeout_ms raises error", False, f"Wrong exception: {e}")
    
    # Test runtime config
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ProcessorConfig(
                repo_root=Path(tmpdir),
                runtime=AgentRuntime.OPENCODE,
            )
            runtime_config = config.get_runtime_config()
            assert runtime_config.label == "OpenCode"
            assert config.get_model() == "minimax-coding-plan/MiniMax-M2.1"
            results.record("Runtime config resolves correctly", True)
    except Exception as e:
        results.record("Runtime config resolves correctly", False, str(e))


# ============================================================================
# Checklist Parser Tests
# ============================================================================

def test_checklist_parser():
    """Test checklist parsing functionality."""
    print("\n📋 Checklist Parser Tests")
    
    test_checklist = """# Test Checklist

## Tier 1: Basic Tests

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| T1-001 | First test | High | Low | ☐ Not Started |
| T1-002 | Second test | Medium | Medium | ✅ Completed |
| T1-003 | Third test | Low | High | ❌ Failed |

## Tier 2: Advanced Tests

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| T2-001 | Advanced test | High | High | ☐ Not Started |
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checklist_path = tmpdir / "CHECKLIST.md"
        checklist_path.write_text(test_checklist)
        
        parser = ChecklistParser(checklist_path, tmpdir)
        
        # Test parsing
        try:
            items = parser.parse()
            assert len(items) == 4, f"Expected 4 items, got {len(items)}"
            results.record("Parses all items correctly", True)
        except Exception as e:
            results.record("Parses all items correctly", False, str(e))
        
        # Test item properties
        try:
            item = items[0]
            assert item.id == "T1-001"
            assert item.target == "First test"
            assert item.priority == "High"
            assert item.risk == "Low"
            assert item.tier == "Tier 1: Basic Tests"
            results.record("Item properties parsed correctly", True)
        except Exception as e:
            results.record("Item properties parsed correctly", False, str(e))
        
        # Test status detection
        try:
            assert items[0].is_pending()
            assert items[1].is_completed()
            assert items[2].is_failed()
            results.record("Status detection works", True)
        except Exception as e:
            results.record("Status detection works", False, str(e))
        
        # Test get_remaining
        try:
            remaining = parser.get_remaining(items)
            assert len(remaining) == 2, f"Expected 2 remaining, got {len(remaining)}"
            assert remaining[0].id == "T1-001"
            assert remaining[1].id == "T2-001"
            results.record("Get remaining items works", True)
        except Exception as e:
            results.record("Get remaining items works", False, str(e))
        
        # Test prefix tier map
        try:
            prefix_map = parser.build_prefix_tier_map(items)
            assert "T1" in prefix_map
            assert "T2" in prefix_map
            results.record("Prefix tier map builds correctly", True)
        except Exception as e:
            results.record("Prefix tier map builds correctly", False, str(e))
        
        # Test tier name sanitization
        try:
            name = parser.get_sanitized_tier_name("## Tier 1: Basic Tests")
            assert name == "tier_1_basic_tests", f"Got: {name}"
            results.record("Tier name sanitization works", True)
        except Exception as e:
            results.record("Tier name sanitization works", False, str(e))


# ============================================================================
# Checklist Status Update Tests
# ============================================================================

async def test_checklist_status_update():
    """Test updating item status in checklist."""
    print("\n📋 Checklist Status Update Tests")
    
    test_checklist = """# Test Checklist

## Test Tier

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| TEST-001 | Test item | High | Low | ☐ Not Started |
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checklist_path = tmpdir / "CHECKLIST.md"
        checklist_path.write_text(test_checklist)
        
        parser = ChecklistParser(checklist_path, tmpdir)
        
        # Update status
        try:
            await parser.update_item_status("TEST-001", "✅ Completed")
            
            # Re-parse and verify
            items = parser.parse()
            assert items[0].is_completed(), "Item should be completed"
            results.record("Status update works", True)
        except Exception as e:
            results.record("Status update works", False, str(e))
        
        # Test concurrent updates
        try:
            # Reset
            checklist_path.write_text(test_checklist.replace("TEST-001", "TEST-001"))
            
            # Concurrent updates (simulate)
            await asyncio.gather(
                parser.update_item_status("TEST-001", "✅ Completed"),
                parser.update_item_status("TEST-001", "❌ Failed"),
            )
            
            # Should not crash
            results.record("Concurrent updates don't crash", True)
        except Exception as e:
            results.record("Concurrent updates don't crash", False, str(e))


# ============================================================================
# Model Tests
# ============================================================================

def test_models():
    """Test data models."""
    print("\n📋 Model Tests")
    
    # Test ChecklistItem
    try:
        item = ChecklistItem(
            id="TEST-001",
            target="Test target",
            priority="High",
            risk="Low",
            status="☐ Not Started",
            tier="Test Tier",
        )
        
        assert item.is_pending()
        assert not item.is_completed()
        assert not item.is_failed()
        
        # Test with_status
        completed_item = item.with_status("✅ Completed")
        assert completed_item.is_completed()
        assert item.is_pending()  # Original unchanged (immutable)
        
        results.record("ChecklistItem works correctly", True)
    except Exception as e:
        results.record("ChecklistItem works correctly", False, str(e))
    
    # Test AgentRun
    try:
        item = ChecklistItem(
            id="TEST-001",
            target="Test",
            priority="High",
            risk="Low",
            status="☐ Not Started",
        )
        
        run = AgentRun.create(item, max_attempts=3)
        
        assert run.item_id == "TEST-001"
        assert run.status == AgentStatus.PENDING
        assert run.attempt == 0
        assert run.max_attempts == 3
        
        # Test status transitions
        run.set_status(AgentStatus.RUNNING)
        assert run.status == AgentStatus.RUNNING
        assert run.started_at is not None
        
        run.set_status(AgentStatus.COMPLETED)
        assert run.is_terminal()
        assert run.completed_at is not None
        
        results.record("AgentRun state management works", True)
    except Exception as e:
        results.record("AgentRun state management works", False, str(e))
    
    # Test AgentRun event subscription
    try:
        item = ChecklistItem(
            id="TEST-001",
            target="Test",
            priority="High",
            risk="Low",
            status="☐ Not Started",
        )
        
        run = AgentRun.create(item)
        events = []
        
        run.subscribe(lambda e: events.append(e))
        
        run.set_status(AgentStatus.RUNNING)
        run.set_stage(RunStage.PROCESSING)
        run.append_output("test output")
        
        assert len(events) == 3
        assert events[0]["event"] == "status"
        assert events[1]["event"] == "stage"
        assert events[2]["event"] == "output"
        
        results.record("AgentRun event subscription works", True)
    except Exception as e:
        results.record("AgentRun event subscription works", False, str(e))


# ============================================================================
# Run Manager Tests
# ============================================================================

def test_run_manager():
    """Test run manager functionality."""
    print("\n📋 Run Manager Tests")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Test basic functionality
        try:
            manager = RunManager(state_dir=tmpdir)
            
            assert manager.status == "idle"
            
            manager.start()
            assert manager.status == "running"
            assert manager.started_at is not None
            
            results.record("Run manager starts correctly", True)
        except Exception as e:
            results.record("Run manager starts correctly", False, str(e))
        
        # Test run creation
        try:
            item = ChecklistItem(
                id="TEST-001",
                target="Test",
                priority="High",
                risk="Low",
                status="☐ Not Started",
            )
            
            run = manager.create_run(item, run_dir=tmpdir / "runs" / "TEST-001")
            
            assert manager.get_run(run.id) is run
            assert manager.get_run_by_item("TEST-001") is run
            
            results.record("Run creation and retrieval works", True)
        except Exception as e:
            results.record("Run creation and retrieval works", False, str(e))
        
        # Test summary
        try:
            run.set_status(AgentStatus.COMPLETED)
            
            summary = manager.get_summary()
            assert summary.total == 1
            assert summary.completed == 1
            
            results.record("Run summary works", True)
        except Exception as e:
            results.record("Run summary works", False, str(e))
        
        # Test state persistence
        try:
            manager.persist_state()
            
            state_file = tmpdir / "active-runs.json"
            assert state_file.exists()
            
            state = json.loads(state_file.read_text())
            assert state["status"] == "running"
            assert len(state["runs"]) == 1
            
            results.record("State persistence works", True)
        except Exception as e:
            results.record("State persistence works", False, str(e))
        
        # Test completion
        try:
            manager.complete()
            assert manager.status == "completed"
            assert manager.completed_at is not None
            
            results.record("Run manager completes correctly", True)
        except Exception as e:
            results.record("Run manager completes correctly", False, str(e))


# ============================================================================
# Interceptor Tests
# ============================================================================

def test_interceptors():
    """Test custom interceptors."""
    print("\n📋 Interceptor Tests")
    
    from stageflow_processor.interceptors import RetryInterceptor, ObservabilityInterceptor, FailFastInterceptor
    from stageflow_processor.config import RetryConfig
    
    # Test RetryInterceptor
    try:
        config = RetryConfig(max_retries=3, base_delay_ms=100)
        interceptor = RetryInterceptor(config)
        
        # Test retryable error detection
        timeout_err = TimeoutError("Connection timed out")
        assert interceptor._is_retryable(timeout_err)
        
        value_err = ValueError("Invalid input")
        assert not interceptor._is_retryable(value_err)
        
        # Test delay calculation
        delay_0 = interceptor._calculate_delay(0)
        delay_1 = interceptor._calculate_delay(1)
        assert delay_1 > delay_0  # Exponential backoff
        
        results.record("RetryInterceptor works correctly", True)
    except Exception as e:
        results.record("RetryInterceptor works correctly", False, str(e))
    
    # Test ObservabilityInterceptor
    try:
        interceptor = ObservabilityInterceptor(verbose=True)
        
        # Verify metrics tracking
        assert hasattr(interceptor, "_stage_timings")
        assert hasattr(interceptor, "_stage_counts")
        
        metrics = interceptor.get_metrics()
        assert "stage_counts" in metrics
        
        results.record("ObservabilityInterceptor works correctly", True)
    except Exception as e:
        results.record("ObservabilityInterceptor works correctly", False, str(e))
    
    # Test FailFastInterceptor
    try:
        interceptor = FailFastInterceptor(strict=True)
        
        # Verify requirements are defined
        assert "build_prompt" in interceptor.STAGE_REQUIREMENTS
        
        errors = interceptor.get_validation_errors()
        assert isinstance(errors, list)
        
        results.record("FailFastInterceptor works correctly", True)
    except Exception as e:
        results.record("FailFastInterceptor works correctly", False, str(e))


# ============================================================================
# Stage Tests
# ============================================================================

async def test_stages():
    """Test individual pipeline stages."""
    print("\n📋 Stage Tests")
    
    from stageflow import StageContext, PipelineTimer
    from stageflow.context import ContextSnapshot, RunIdentity
    from stageflow.stages import StageInputs
    
    from stageflow_processor.stages import ParseChecklistStage, BuildPromptStage
    
    test_checklist = """# Test Checklist

## Test Tier

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| TEST-001 | Test item | High | Low | ☐ Not Started |
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checklist_path = tmpdir / "CHECKLIST.md"
        checklist_path.write_text(test_checklist)
        
        parser = ChecklistParser(checklist_path, tmpdir)
        
        # Test ParseChecklistStage
        try:
            stage = ParseChecklistStage(parser=parser, batch_size=5)
            
            snapshot = ContextSnapshot(
                run_id=RunIdentity(
                    pipeline_run_id=uuid4(),
                    request_id=uuid4(),
                    session_id=uuid4(),
                    user_id=None,
                    org_id=None,
                    interaction_id=uuid4(),
                ),
                topology="test",
                execution_mode="test",
                metadata={},
            )
            
            inputs = StageInputs(snapshot=snapshot)
            ctx = StageContext(
                snapshot=snapshot,
                inputs=inputs,
                stage_name="parse_checklist",
                timer=PipelineTimer(),
            )
            
            result = await stage.execute(ctx)
            
            # StageOutput uses .status property that returns string representation
            assert hasattr(result, 'data'), f"Result has no data: {result}"
            assert result.data["total_count"] == 1, f"Expected 1 total, got {result.data.get('total_count')}"
            assert result.data["remaining_count"] == 1
            assert len(result.data["batch_items"]) == 1
            
            results.record("ParseChecklistStage works", True)
        except Exception as e:
            import traceback
            results.record("ParseChecklistStage works", False, f"{e}\n{traceback.format_exc()}")
        
        # Test BuildPromptStage
        try:
            stage = BuildPromptStage(
                repo_root=tmpdir,
                agent_prompt_path=tmpdir / "PROMPT.md",  # Doesn't exist, will use default
                checklist_path=checklist_path,
            )
            
            item_data = {
                "id": "TEST-001",
                "target": "Test item",
                "priority": "High",
                "risk": "Low",
                "status": "☐ Not Started",
                "tier": "Test Tier",
                "section": "",
            }
            
            snapshot = ContextSnapshot(
                run_id=RunIdentity(
                    pipeline_run_id=uuid4(),
                    request_id=uuid4(),
                    session_id=uuid4(),
                    user_id=None,
                    org_id=None,
                    interaction_id=uuid4(),
                ),
                topology="test",
                execution_mode="test",
                metadata={
                    "item": item_data,
                    "run_dir": str(tmpdir / "runs" / "TEST-001"),
                    "mission_brief": "Test mission",
                },
            )
            
            inputs = StageInputs(snapshot=snapshot)
            ctx = StageContext(
                snapshot=snapshot,
                inputs=inputs,
                stage_name="build_prompt",
                timer=PipelineTimer(),
            )
            
            result = await stage.execute(ctx)
            
            assert hasattr(result, 'data'), f"Result has no data: {result}"
            assert "prompt" in result.data, f"No prompt in result: {result.data}"
            assert "TEST-001" in result.data["prompt"], f"TEST-001 not in prompt"
            assert "ITEM_COMPLETE" in result.data["prompt"], f"ITEM_COMPLETE not in prompt"
            
            results.record("BuildPromptStage works", True)
        except Exception as e:
            import traceback
            results.record("BuildPromptStage works", False, f"{e}\n{traceback.format_exc()}")


# ============================================================================
# Integration Tests
# ============================================================================

async def test_processor_dry_run():
    """Test processor in dry-run mode."""
    print("\n📋 Processor Integration Tests")
    
    test_checklist = """# Test Checklist

## Test Tier

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| TEST-001 | Test item | High | Low | ☐ Not Started |
| TEST-002 | Another test | Medium | Medium | ☐ Not Started |
"""
    
    test_brief = """# Test Mission Brief
This is a test.
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Setup test files
        checklist_path = tmpdir / "SUT-CHECKLIST.md"
        checklist_path.write_text(test_checklist)
        
        brief_path = tmpdir / "SUT-PACKET.md"
        brief_path.write_text(test_brief)
        
        # Test dry run
        try:
            config = ProcessorConfig(
                repo_root=tmpdir,
                checklist_path=checklist_path,
                mission_brief_path=brief_path,
                batch_size=2,
                dry_run=True,
                verbose=False,
            )
            
            processor = ChecklistProcessor(config)
            result = await processor.process()
            
            assert result.dry_run
            assert result.processed == 2
            
            results.record("Processor dry-run works", True)
        except Exception as e:
            results.record("Processor dry-run works", False, str(e))
        
        # Test status retrieval
        try:
            status = processor.get_status()
            
            assert "session" in status
            assert "summary" in status
            assert "config" in status
            
            results.record("Processor status retrieval works", True)
        except Exception as e:
            results.record("Processor status retrieval works", False, str(e))


async def test_all_items_complete():
    """Test processor behavior when all items are complete."""
    print("\n📋 All Items Complete Test")
    
    test_checklist = """# Test Checklist

## Test Tier

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| TEST-001 | Test item | High | Low | ✅ Completed |
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        checklist_path = tmpdir / "SUT-CHECKLIST.md"
        checklist_path.write_text(test_checklist)
        
        try:
            config = ProcessorConfig(
                repo_root=tmpdir,
                checklist_path=checklist_path,
                batch_size=1,
                dry_run=True,
            )
            
            processor = ChecklistProcessor(config)
            result = await processor.process()
            
            assert result.processed == 0
            
            results.record("Handles all-complete correctly", True)
        except Exception as e:
            results.record("Handles all-complete correctly", False, str(e))


# ============================================================================
# Event System Tests
# ============================================================================

async def test_event_system():
    """Test event emission and subscription."""
    print("\n📋 Event System Tests")
    
    test_checklist = """# Test Checklist

## Test Tier

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| TEST-001 | Test item | High | Low | ☐ Not Started |
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        checklist_path = tmpdir / "SUT-CHECKLIST.md"
        checklist_path.write_text(test_checklist)
        
        try:
            config = ProcessorConfig(
                repo_root=tmpdir,
                checklist_path=checklist_path,
                batch_size=1,
                dry_run=True,
            )
            
            processor = ChecklistProcessor(config)
            
            events = []
            processor.subscribe(lambda event, data: events.append((event, data)))
            
            await processor.process()
            
            # Should have at least session:start and session:complete
            event_types = [e[0] for e in events]
            
            # The run manager should emit session events
            assert any("session" in et for et in event_types), f"Got events: {event_types}"
            
            results.record("Event subscription works", True)
        except Exception as e:
            results.record("Event subscription works", False, str(e))


# ============================================================================
# Main Test Runner
# ============================================================================

async def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Stageflow Checklist Processor - Test Suite")
    print("=" * 60)
    
    # Synchronous tests
    test_config_validation()
    test_checklist_parser()
    test_models()
    test_run_manager()
    test_interceptors()
    
    # Async tests
    await test_checklist_status_update()
    await test_stages()
    await test_processor_dry_run()
    await test_all_items_complete()
    await test_event_system()
    
    # Summary
    success = results.summary()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
