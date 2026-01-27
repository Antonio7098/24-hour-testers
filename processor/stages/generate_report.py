"""
Generate Tier Report Stage - generates aggregated reports when tiers complete.

Single responsibility: Generate tier-level summary reports.
"""

import asyncio
import os
import re
from pathlib import Path
from stageflow import StageContext, StageKind, StageOutput

from ..config import ProcessorConfig
from ..utils.checklist_parser import ChecklistParser
from ..utils.logger import get_logger
from ..models import ChecklistItem

logger = get_logger("generate_report")


class GenerateTierReportStage:
    """Stage that generates tier reports when all items in a tier complete.
    
    Enhanced to call OpenCode agent for rich, stakeholder-ready tier reports.
    """
    
    name = "generate_tier_report"
    kind = StageKind.WORK
    
    def __init__(
        self,
        parser: ChecklistParser,
        runs_dir: Path,
        repo_root: Path,
        tier_report_template_path: Path | None = None,
        config: ProcessorConfig | None = None,
    ):
        self.parser = parser
        self.runs_dir = Path(runs_dir)
        self.repo_root = Path(repo_root)
        self.tier_report_template_path = tier_report_template_path
        self.config = config
        self._template_cache: str | None = None
        self._timeout_seconds = 180  # 3 min timeout for tier report generation
    
    def _load_template(self) -> str | None:
        """Load the tier report template."""
        if self._template_cache is not None:
            return self._template_cache
        
        if self.tier_report_template_path and self.tier_report_template_path.exists():
            self._template_cache = self.tier_report_template_path.read_text(encoding="utf-8")
        return self._template_cache
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Check for completed tiers and generate reports."""
        # Get all items from metadata
        metadata = ctx.snapshot.metadata or {}
        all_items_data = metadata.get("all_items") or []
        if not all_items_data:
            return StageOutput.skip(reason="No items to check for tier reports")
        
        all_items = [
            ChecklistItem(**item) if isinstance(item, dict) else item 
            for item in all_items_data
        ]
        
        mission_brief = metadata.get("mission_brief") or ""
        prefix_tier_map = self.parser.build_prefix_tier_map(all_items)
        
        # Group by tier
        tiers: dict[str, list[ChecklistItem]] = {}
        for item in all_items:
            heading = self.parser.resolve_tier_heading(item, prefix_tier_map)
            if heading:
                tier_name = heading.replace("## ", "")
                if tier_name not in tiers:
                    tiers[tier_name] = []
                tiers[tier_name].append(item)
        
        reports_generated = []
        
        for tier_name, tier_items in tiers.items():
            # Check if all items are complete
            is_complete = all(item.is_completed() for item in tier_items)
            if not is_complete:
                continue
            
            # Check if report already exists
            sanitized_name = self.parser.get_sanitized_tier_name(tier_name)
            tier_dir = self.runs_dir / sanitized_name
            report_path = tier_dir / f"{sanitized_name}-FINAL-REPORT.md"
            
            if report_path.exists():
                continue
            
            # Generate report
            ctx.try_emit_event("tier_report.generating", {
                "tier": tier_name,
                "item_count": len(tier_items),
            })
            
            tier_dir.mkdir(parents=True, exist_ok=True)
            
            # Collect individual reports
            reports_content = []
            for item in tier_items:
                item_heading = self.parser.resolve_tier_heading(item, prefix_tier_map)
                item_tier = self.parser.get_sanitized_tier_name(item_heading or "uncategorized")
                item_run_dir = self.runs_dir / item_tier / item.id
                item_report = item_run_dir / f"{item.id}-FINAL-REPORT.md"
                
                reports_content.append(f"\n\n### Report for {item.id}: {item.target}\n")
                if item_report.exists():
                    reports_content.append(item_report.read_text(encoding="utf-8"))
                else:
                    reports_content.append("*No final report found for this item.*")
                reports_content.append("\n\n---")
            
            accumulated_reports = "".join(reports_content)
            
            # Generate final report using OpenCode agent
            template = self._load_template()
            checklist_rows = "\n".join(
                self.parser.format_checklist_row(item) for item in tier_items
            )
            
            if template and self.config:
                # Build prompt from template
                prompt = template
                prompt = prompt.replace("{{TIER_NAME}}", tier_name)
                prompt = prompt.replace("{{CHECKLIST_ROWS}}", checklist_rows)
                prompt = prompt.replace("{{MISSION_BRIEF}}", mission_brief)
                prompt = prompt.replace("{{FINAL_REPORT_DIGEST}}", accumulated_reports)
                
                # Call OpenCode agent for rich report
                report_content = await self._generate_report_with_agent(prompt, tier_name)
                if not report_content:
                    # Fallback to simple report if agent fails
                    logger.warning(f"Agent failed for {tier_name}, using fallback report")
                    report_content = f"# {tier_name} - Tier Report\n\n{accumulated_reports}"
            else:
                # Simple fallback report (no template or no config)
                report_content = f"# {tier_name} - Tier Report\n\n{accumulated_reports}"
            
            report_path.write_text(report_content, encoding="utf-8")
            reports_generated.append({
                "tier": tier_name,
                "path": str(report_path),
                "items": len(tier_items),
            })
            
            ctx.try_emit_event("tier_report.generated", {
                "tier": tier_name,
                "path": str(report_path),
            })
        
        return StageOutput.ok(
            reports_generated=reports_generated,
            tiers_checked=len(tiers),
        )
    
    async def _generate_report_with_agent(self, prompt: str, tier_name: str) -> str | None:
        """Call OpenCode agent to generate a rich tier report."""
        if not self.config:
            return None
        
        try:
            command, args = self._build_command()
            logger.info(f"Generating tier report for {tier_name} via {command}")
            
            process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    process.communicate(input=prompt.encode()),
                    timeout=self._timeout_seconds,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.error(f"Tier report generation timed out for {tier_name}")
                return None
            
            if process.returncode != 0:
                logger.error(f"Agent failed for tier report: exit code {process.returncode}")
                return None
            
            output = stdout_data.decode() + stderr_data.decode()
            cleaned = self._clean_agent_output(output)
            
            if not cleaned or len(cleaned) < 50:
                logger.warning(f"Agent output too short for {tier_name}")
                return None
            
            logger.info(f"Generated rich tier report for {tier_name} ({len(cleaned)} chars)")
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to generate tier report with agent: {e}")
            return None
    
    def _build_command(self) -> tuple[str, list[str]]:
        """Build the command and arguments for the agent."""
        if not self.config:
            raise ValueError("Config not set")
        
        runtime_cmd = self.config.get_runtime_command()
        runtime_config = self.config.get_runtime_config()
        model = self.config.get_model()
        args = runtime_config.build_args(model)
        
        return runtime_cmd, args
    
    def _clean_agent_output(self, text: str) -> str:
        """Clean agent output, removing ANSI codes and extracting markdown report."""
        if not text:
            return ""
        
        # Remove ANSI escape codes
        clean = re.sub(r'\x1b\[[0-9;]*m', '', text)
        
        # Try to find the start of the markdown report (first heading)
        header_match = re.search(r'^# ', clean, re.MULTILINE)
        if header_match:
            return clean[header_match.start():].strip()
        
        # Fallback: filter out tool output lines
        lines = clean.split('\n')
        filtered = [
            line for line in lines
            if not line.strip().startswith('|') 
            and 'Glob' not in line 
            and 'Read' not in line
            and 'Tool' not in line
        ]
        
        return '\n'.join(filtered).strip()
