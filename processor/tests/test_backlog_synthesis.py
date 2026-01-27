"""
Tests for backlog synthesis and tier report generation.

These are real integration tests - no mocks.
"""

import asyncio
import json
import tempfile
from pathlib import Path
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from processor.config import ProcessorConfig, ProcessingMode
from processor.models import ChecklistItem
from processor.processor import ChecklistProcessor
from processor.stages.generate_report import GenerateTierReportStage
from processor.utils.checklist_parser import ChecklistParser


class TestJsonPayloadExtraction:
    """Test JSON extraction from agent output."""
    
    def setup_method(self):
        """Create a processor with minimal config for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.checklist_path = Path(self.temp_dir) / "SUT-CHECKLIST.md"
        self.checklist_path.write_text("""# Test Checklist

## Tier 1: Basics

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| T-001 | Test item 1 | High | Low | ✅ Completed |
""")
        
        self.config = ProcessorConfig(
            repo_root=Path(self.temp_dir),
            checklist_path=self.checklist_path,
            mode=ProcessingMode.INFINITE,
            dry_run=True,
        )
        self.processor = ChecklistProcessor(self.config)
    
    def test_extract_json_from_markdown_block(self):
        """Test extracting JSON from markdown code block."""
        output = '''Here is the generated items:

```json
{
  "items": [
    {
      "id": "INF-001",
      "target": "Test target",
      "priority": "High",
      "risk": "Medium",
      "status": "☐ Not Started",
      "tier": "Tier 4: Reliability"
    }
  ]
}
```

Done!'''
        
        payload = self.processor._extract_json_payload(output)
        
        assert payload is not None
        assert "items" in payload
        assert len(payload["items"]) == 1
        assert payload["items"][0]["id"] == "INF-001"
    
    def test_extract_json_from_generic_code_block(self):
        """Test extracting JSON from generic code block."""
        output = '''```
{
  "items": [
    {"id": "INF-002", "target": "Another target", "priority": "Low", "risk": "Low", "status": "☐ Not Started", "tier": "Tier 2"}
  ]
}
```'''
        
        payload = self.processor._extract_json_payload(output)
        
        assert payload is not None
        assert payload["items"][0]["id"] == "INF-002"
    
    def test_extract_raw_json(self):
        """Test extracting raw JSON without code blocks."""
        output = '{"items": [{"id": "INF-003", "target": "Raw JSON", "priority": "Medium", "risk": "High", "status": "☐ Not Started", "tier": "Tier 3"}]}'
        
        payload = self.processor._extract_json_payload(output)
        
        assert payload is not None
        assert payload["items"][0]["id"] == "INF-003"
    
    def test_extract_json_with_ansi_codes(self):
        """Test extracting JSON with ANSI escape codes."""
        output = '\x1b[32m```json\n{"items": [{"id": "INF-004", "target": "ANSI test", "priority": "High", "risk": "Low", "status": "☐ Not Started", "tier": "Tier 1"}]}\n```\x1b[0m'
        
        payload = self.processor._extract_json_payload(output)
        
        assert payload is not None
        assert payload["items"][0]["id"] == "INF-004"
    
    def test_extract_json_empty_output(self):
        """Test handling empty output."""
        assert self.processor._extract_json_payload("") is None
        assert self.processor._extract_json_payload(None) is None
    
    def test_extract_json_invalid_json(self):
        """Test handling invalid JSON."""
        output = "This is not JSON at all"
        assert self.processor._extract_json_payload(output) is None


class TestItemCoercion:
    """Test coercing JSON to ChecklistItem objects."""
    
    def setup_method(self):
        """Create a processor with minimal config for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.checklist_path = Path(self.temp_dir) / "SUT-CHECKLIST.md"
        self.checklist_path.write_text("# Empty Checklist\n")
        
        self.config = ProcessorConfig(
            repo_root=Path(self.temp_dir),
            checklist_path=self.checklist_path,
            mode=ProcessingMode.INFINITE,
            dry_run=True,
        )
        self.processor = ChecklistProcessor(self.config)
    
    def test_coerce_valid_items(self):
        """Test coercing valid item data."""
        payload = {
            "items": [
                {
                    "id": "INF-001",
                    "target": "Test target 1",
                    "priority": "High",
                    "risk": "Medium",
                    "status": "☐ Not Started",
                    "tier": "Tier 4: Reliability"
                },
                {
                    "id": "INF-002",
                    "target": "Test target 2",
                    "priority": "Low",
                    "risk": "Low",
                    "status": "☐ Not Started",
                    "tier": "Tier 3: Error Handling"
                }
            ]
        }
        
        items = self.processor._coerce_generated_items(payload)
        
        assert len(items) == 2
        assert items[0].id == "INF-001"
        assert items[0].target == "Test target 1"
        assert items[0].priority == "High"
        assert items[1].id == "INF-002"
    
    def test_coerce_partial_items(self):
        """Test coercing items with missing fields (uses defaults)."""
        payload = {
            "items": [
                {"id": "INF-003", "target": "Partial item"}
            ]
        }
        
        items = self.processor._coerce_generated_items(payload)
        
        assert len(items) == 1
        assert items[0].id == "INF-003"
        assert items[0].priority == "Medium"  # Default
        assert items[0].risk == "Medium"  # Default
        assert items[0].status == "☐ Not Started"  # Default
    
    def test_coerce_empty_payload(self):
        """Test handling empty payload."""
        assert self.processor._coerce_generated_items({}) == []
        assert self.processor._coerce_generated_items(None) == []
        assert self.processor._coerce_generated_items({"items": []}) == []
    
    def test_coerce_invalid_items_structure(self):
        """Test handling invalid items structure."""
        assert self.processor._coerce_generated_items({"items": "not a list"}) == []
        assert self.processor._coerce_generated_items({"items": [None, "string", 123]}) == []


class TestBacklogPromptBuilding:
    """Test building backlog synthesis prompts."""
    
    def setup_method(self):
        """Create a processor with minimal config for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.checklist_path = Path(self.temp_dir) / "SUT-CHECKLIST.md"
        self.checklist_content = """# Test Checklist

## Tier 1: API Basics

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| API-001 | Test endpoint | High | Low | ✅ Completed |
"""
        self.checklist_path.write_text(self.checklist_content)
        
        self.config = ProcessorConfig(
            repo_root=Path(self.temp_dir),
            checklist_path=self.checklist_path,
            mode=ProcessingMode.INFINITE,
            dry_run=True,
        )
        self.processor = ChecklistProcessor(self.config)
    
    def test_build_prompt_with_mission_brief(self):
        """Test prompt building with mission brief."""
        prompt = self.processor._build_backlog_synthesis_prompt(
            mission_brief="Test the Sample API",
            checklist_content=self.checklist_content,
            needed_count=3,
        )
        
        assert prompt is not None
        assert "Mission Brief:" in prompt
        assert "Test the Sample API" in prompt
        assert "3" in prompt
        assert self.checklist_content in prompt
    
    def test_build_prompt_without_mission_brief(self):
        """Test prompt building without mission brief."""
        prompt = self.processor._build_backlog_synthesis_prompt(
            mission_brief=None,
            checklist_content=self.checklist_content,
            needed_count=5,
        )
        
        assert prompt is not None
        assert "Mission Brief:" not in prompt
        assert "5" in prompt
    
    def test_build_prompt_includes_json_schema(self):
        """Test that prompt includes JSON schema."""
        prompt = self.processor._build_backlog_synthesis_prompt(
            mission_brief=None,
            checklist_content=self.checklist_content,
            needed_count=2,
        )
        
        assert '"items"' in prompt
        assert '"id"' in prompt
        assert '"target"' in prompt


class TestTierReportCleaning:
    """Test cleaning agent output for tier reports."""
    
    def setup_method(self):
        """Create a GenerateTierReportStage for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.parser = ChecklistParser(
            Path(self.temp_dir) / "SUT-CHECKLIST.md",
            Path(self.temp_dir)
        )
        
        self.stage = GenerateTierReportStage(
            parser=self.parser,
            runs_dir=Path(self.temp_dir) / "runs",
            repo_root=Path(self.temp_dir),
        )
    
    def test_clean_ansi_codes(self):
        """Test removing ANSI escape codes."""
        output = "\x1b[32m# Tier Report\x1b[0m\n\nContent here"
        
        cleaned = self.stage._clean_agent_output(output)
        
        assert "\x1b[" not in cleaned
        assert "# Tier Report" in cleaned
    
    def test_extract_markdown_from_first_heading(self):
        """Test extracting content from first heading."""
        output = """Tool output here
Read file...
Glob pattern...

# Tier 1 Report

## Executive Summary
- Item completed successfully

## Key Findings
| ID | Status |
|----|--------|
| T-001 | Done |
"""
        
        cleaned = self.stage._clean_agent_output(output)
        
        assert cleaned.startswith("# Tier 1 Report")
        assert "Tool output" not in cleaned
        assert "Executive Summary" in cleaned
    
    def test_clean_empty_output(self):
        """Test handling empty output."""
        assert self.stage._clean_agent_output("") == ""
        assert self.stage._clean_agent_output(None) == ""
    
    def test_fallback_filtering(self):
        """Test fallback filtering when no heading found."""
        output = "Some content without markdown heading\nGlob pattern match\nActual content line"
        
        cleaned = self.stage._clean_agent_output(output)
        
        # Should filter out Glob line
        assert "Glob" not in cleaned
        assert "Actual content line" in cleaned


class TestChecklistAppend:
    """Test appending synthesized items to checklist."""
    
    def setup_method(self):
        """Create a parser with a test checklist."""
        self.temp_dir = tempfile.mkdtemp()
        self.checklist_path = Path(self.temp_dir) / "SUT-CHECKLIST.md"
        self.checklist_path.write_text("""# Test Checklist

## Tier 1: API Basics

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| API-001 | Test endpoint | High | Low | ✅ Completed |

## Tier 2: Error Handling

| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| API-002 | Error test | Medium | Medium | ☐ Not Started |
""")
        
        self.parser = ChecklistParser(self.checklist_path, Path(self.temp_dir))
    
    @pytest.mark.asyncio
    async def test_append_items_to_existing_tier(self):
        """Test appending items to an existing tier."""
        new_items = [
            ChecklistItem(
                id="API-003",
                target="New test item",
                priority="High",
                risk="Low",
                status="☐ Not Started",
                tier="Tier 1: API Basics",
                section="",
            )
        ]
        
        await self.parser.append_rows(new_items)
        
        content = self.checklist_path.read_text()
        assert "API-003" in content
        assert "New test item" in content
    
    @pytest.mark.asyncio
    async def test_append_items_to_new_tier(self):
        """Test appending items creates new tier if needed."""
        new_items = [
            ChecklistItem(
                id="INF-001",
                target="Infinite mode item",
                priority="Medium",
                risk="Medium",
                status="☐ Not Started",
                tier="Tier 4: Reliability & Backlog Expansion",
                section="",
            )
        ]
        
        await self.parser.append_rows(new_items)
        
        content = self.checklist_path.read_text()
        assert "INF-001" in content
        assert "Tier 4" in content or "Reliability" in content
    
    @pytest.mark.asyncio
    async def test_append_multiple_items(self):
        """Test appending multiple items at once."""
        new_items = [
            ChecklistItem(
                id="INF-002",
                target="Item 2",
                priority="High",
                risk="Low",
                status="☐ Not Started",
                tier="Tier 2: Error Handling",
                section="",
            ),
            ChecklistItem(
                id="INF-003",
                target="Item 3",
                priority="Low",
                risk="High",
                status="☐ Not Started",
                tier="Tier 2: Error Handling",
                section="",
            ),
        ]
        
        await self.parser.append_rows(new_items)
        
        content = self.checklist_path.read_text()
        assert "INF-002" in content
        assert "INF-003" in content


def run_tests():
    """Run all tests."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
