"""
Checklist Processor - main orchestrator using stageflow pipelines.

Coordinates all stages and provides the main entry point for processing.
"""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from stageflow import Pipeline, StageKind, StageContext, PipelineTimer, StageStatus
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.stages import StageInputs
from stageflow import get_default_interceptors, TimeoutInterceptor, CircuitBreakerInterceptor

from .config import ProcessorConfig, ProcessingMode
from .models import AgentRun, AgentStatus, ChecklistItem, ProcessingResult, RunStage
from .run_manager import RunManager
from .utils.checklist_parser import ChecklistParser
from .utils.logger import get_logger, setup_logging

from .stages import (
    ParseChecklistStage,
    BuildPromptStage,
    RunAgentStage,
    ValidateOutputStage,
    UpdateStatusStage,
    GenerateTierReportStage,
)
from .interceptors import (
    RetryInterceptor,
    ObservabilityInterceptor,
    FailFastInterceptor,
)

logger = get_logger("processor")


class ChecklistProcessor:
    """
    Main orchestrator for processing checklist items using stageflow pipelines.
    
    Features:
    - DAG-based pipeline execution
    - Parallel batch processing
    - Automatic retry with exponential backoff
    - Comprehensive observability
    - Graceful cancellation
    - State persistence
    """
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        
        # Setup logging
        setup_logging(verbose=config.verbose)
        
        # Ensure directories exist
        config.ensure_directories()
        
        # Initialize components
        self.parser = ChecklistParser(config.checklist_path, config.repo_root)
        self.run_manager = RunManager(config.state_dir)
        
        # Initialize stages
        self._init_stages()
        
        # Initialize interceptors
        self._init_interceptors()
        
        # Build pipeline
        self._pipeline = self._build_pipeline()
        
        # Event listeners
        self._listeners: list[Callable[[dict], None]] = []
        
        # Wire up run manager events
        self.run_manager.subscribe(lambda e: self._emit_event(e["event"], e))
        
        # Cache for mission brief
        self._mission_brief_cache: str | None = None
        
        # Cancellation flag
        self._cancelled = False
    
    def _init_stages(self) -> None:
        """Initialize pipeline stages."""
        self.parse_stage = ParseChecklistStage(
            parser=self.parser,
            batch_size=self.config.batch_size,
        )
        
        self.build_prompt_stage = BuildPromptStage(
            repo_root=self.config.repo_root,
            agent_prompt_path=self.config.agent_prompt_path,
            checklist_path=self.config.checklist_path,
        )
        
        self.run_agent_stage = RunAgentStage(config=self.config)
        
        self.validate_stage = ValidateOutputStage(
            require_completion_marker=True,
            require_final_report=True,  # Strict: must have FINAL_REPORT.md
        )
        
        self.update_status_stage = UpdateStatusStage(parser=self.parser)
        
        # Use agent_resources_dir from config (supports override)
        tier_report_path = self.config.agent_resources_dir / "prompts" / "TIER_REPORT_PROMPT.md"
        self.generate_report_stage = GenerateTierReportStage(
            parser=self.parser,
            runs_dir=self.config.runs_dir,
            repo_root=self.config.repo_root,
            tier_report_template_path=tier_report_path if tier_report_path.exists() else None,
            config=self.config,
        )

        # Load backlog synthesis prompt template from agent_resources_dir
        self._backlog_prompt_path = self.config.agent_resources_dir / "prompts" / "INFINITE_BACKLOG_PROMPT.md"
        self._backlog_prompt_cache: str | None = None
    
    def _init_interceptors(self) -> None:
        """Initialize pipeline interceptors."""
        self.retry_interceptor = RetryInterceptor(self.config.retry)
        self.observability_interceptor = ObservabilityInterceptor(verbose=self.config.verbose)
        self.fail_fast_interceptor = FailFastInterceptor(strict=True)
        
        # Get default interceptors and add our custom ones
        self.interceptors = [
            self.fail_fast_interceptor,
            TimeoutInterceptor(),
            CircuitBreakerInterceptor(),
            self.retry_interceptor,
            self.observability_interceptor,
        ]
    
    def _build_pipeline(self) -> Pipeline:
        """Build the item processing pipeline."""
        return (
            Pipeline()
            .with_stage("build_prompt", self.build_prompt_stage, StageKind.TRANSFORM)
            .with_stage(
                "run_agent",
                self.run_agent_stage,
                StageKind.WORK,
                dependencies=("build_prompt",),
            )
            .with_stage(
                "validate_output",
                self.validate_stage,
                StageKind.GUARD,
                dependencies=("run_agent",),
            )
            .with_stage(
                "update_status",
                self.update_status_stage,
                StageKind.WORK,
                dependencies=("validate_output",),
            )
        )
    
    def _load_mission_brief(self) -> str | None:
        """Load mission brief from file."""
        if self._mission_brief_cache is not None:
            return self._mission_brief_cache
        
        if not self.config.mission_brief_path.exists():
            logger.warning(f"Mission brief not found: {self.config.mission_brief_path}")
            return None
        
        try:
            self._mission_brief_cache = self.config.mission_brief_path.read_text(encoding="utf-8")
            return self._mission_brief_cache
        except Exception as e:
            logger.error(f"Failed to load mission brief: {e}")
            return None
    
    def _get_run_dir(self, item: ChecklistItem, prefix_tier_map: dict[str, str]) -> Path:
        """Get the run directory for an item."""
        heading = self.parser.resolve_tier_heading(item, prefix_tier_map)
        tier_name = self.parser.get_sanitized_tier_name(heading or "uncategorized")
        return self.config.runs_dir / tier_name / item.id
    
    def _setup_run_directory(self, run_dir: Path) -> None:
        """Create run directory structure."""
        # Generalized folder structure (removed "pipelines")
        subdirs = ["config", "dx_evaluation", "mocks", "research", "results", "tests", "artifacts"]
        run_dir.mkdir(parents=True, exist_ok=True)
        for subdir in subdirs:
            (run_dir / subdir).mkdir(exist_ok=True)
    
    async def _process_item(
        self,
        item: ChecklistItem,
        prefix_tier_map: dict[str, str],
        mission_brief: str | None,
    ) -> dict[str, Any]:
        """Process a single checklist item through the pipeline."""
        run_dir = self._get_run_dir(item, prefix_tier_map)
        
        # Create run tracking
        run = self.run_manager.create_run(
            item,
            run_dir=run_dir,
            max_attempts=self.config.retry.max_retries + 1,
        )
        
        logger.info(f"Starting {item.id}", extra={"tier": item.tier, "target": item.target})
        
        try:
            run.set_stage(RunStage.INIT)
            
            if not self.config.dry_run:
                self._setup_run_directory(run_dir)
            
            # Create context snapshot for this item
            # Custom data goes in metadata dict
            snapshot = ContextSnapshot(
                run_id=RunIdentity(
                    pipeline_run_id=uuid4(),
                    request_id=uuid4(),
                    session_id=uuid4(),
                    user_id=None,
                    org_id=None,
                    interaction_id=uuid4(),
                ),
                topology="checklist_processor",
                execution_mode="default",
                metadata={
                    "item": item.__dict__,
                    "run_dir": str(run_dir),
                    "mission_brief": mission_brief,
                    "agent_run": run,
                },
            )
            
            # Build and run pipeline
            graph = self._pipeline.build()
            inputs = StageInputs(snapshot=snapshot)
            ctx = StageContext(
                snapshot=snapshot,
                inputs=inputs,
                stage_name="pipeline",
                timer=PipelineTimer(),
            )
            
            results = await graph.run(ctx)
            
            # Check results
            update_result = results.get("update_status")
            
            # Check if run_agent returned retry (e.g., timeout with checkpoint)
            run_agent_result = results.get("run_agent")
            if run_agent_result and run_agent_result.status == StageStatus.RETRY:
                retry_data = run_agent_result.data or {}
                if retry_data.get("retryable") and run.attempt < run.max_attempts:
                    run.increment_attempt()
                    logger.info(f"{item.id} timed out, will retry (attempt {run.attempt}/{run.max_attempts})", 
                               extra={"checkpoint": retry_data.get("has_checkpoint")})
                    return {"success": False, "run": run, "error": "timeout_retry", 
                            "retry": True, "checkpoint": retry_data.get("has_checkpoint")}
            
            # Check if overall pipeline succeeded
            if update_result and update_result.status == StageStatus.OK:
                run.set_status(AgentStatus.COMPLETED)
                logger.info(f"Completed {item.id}", extra={"duration_ms": run.get_duration_ms()})
                return {"success": True, "run": run}
            else:
                # Pipeline failed
                run.set_status(AgentStatus.FAILED, "Pipeline did not complete successfully")
                return {"success": False, "run": run, "error": "Pipeline failed"}
                
        except Exception as e:
            # Check if this is a retryable timeout (run_agent returned retry but later stage failed)
            error_msg = str(e).lower()
            error_type = type(e).__name__
            # Check for timeout indicators in error message or type
            is_timeout_error = (
                "timeout" in error_msg or 
                "checkpoint" in error_msg or
                error_type == "UnifiedStageExecutionError" and "without completion marker" in error_msg
            )
            if is_timeout_error and run.attempt < run.max_attempts:
                run.increment_attempt()
                logger.info(f"{item.id} timed out (via exception), will retry (attempt {run.attempt}/{run.max_attempts})")
                return {"success": False, "run": run, "error": "timeout_retry", 
                        "retry": True, "checkpoint": True}
            
            logger.error(f"Failed {item.id}: {e}", extra={"error_type": error_type})
            run.set_status(AgentStatus.FAILED, str(e))
            
            # Update status to failed
            try:
                await self.parser.update_item_status(item.id, "❌ Failed")
            except Exception as update_err:
                logger.error(f"Failed to update status: {update_err}")
            
            return {"success": False, "run": run, "error": str(e)}
    
    async def process(self) -> ProcessingResult:
        """
        Main entry point - process checklist items.

        Loops through batches until all items are complete or max_iterations reached.
        Returns ProcessingResult with counts and run details.
        """
        self.run_manager.start()
        mission_brief = self._load_mission_brief()

        # Aggregate totals across all iterations
        total_processed = 0
        total_completed = 0
        total_failed = 0
        all_runs = []

        try:
            iteration = 0

            while iteration < self.config.max_iterations and not self._cancelled:
                iteration += 1
                logger.info(f"Starting iteration {iteration}/{self.config.max_iterations}")

                # Parse checklist (re-parse each iteration to get updated statuses)
                items = self.parser.parse()
                prefix_tier_map = self.parser.build_prefix_tier_map(items)
                remaining = self.parser.get_remaining(items)

                # Handle infinite mode - extend checklist if needed
                if self.config.mode == ProcessingMode.INFINITE:
                    synthesized = await self._extend_checklist_if_needed(mission_brief)
                    if synthesized:
                        # Re-parse after synthesis
                        items = self.parser.parse()
                        prefix_tier_map = self.parser.build_prefix_tier_map(items)
                        remaining = self.parser.get_remaining(items)

                if not remaining:
                    logger.info("All checklist items are complete. Nothing more to process.")
                    break

                # Select batch
                batch = remaining[:self.config.batch_size]
                logger.info(f"Processing batch of {len(batch)} items (iteration {iteration})",
                           extra={"items": [i.id for i in batch]})

                if self.config.dry_run:
                    logger.info(f"[DRY RUN] Would process: {[i.id for i in batch]}")
                    total_processed += len(batch)
                    continue

                # Process items in parallel
                tasks = [
                    self._process_item(item, prefix_tier_map, mission_brief)
                    for item in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Summarize batch results
                batch_completed = 0
                batch_failed = 0
                retry_items = []  # Items to retry in next iteration

                for i, result in enumerate(results):
                    item = batch[i]
                    if isinstance(result, Exception):
                        batch_failed += 1
                        logger.error(f"Item processing raised exception: {result}")
                    elif isinstance(result, dict):
                        all_runs.append(result.get("run"))
                        if result.get("success"):
                            batch_completed += 1
                        elif result.get("retry"):
                            # Item should be retried (e.g., timeout with checkpoint)
                            retry_items.append(item)
                            logger.info(f"{item.id} will be retried (attempt {result.get('run', {}).attempt if result.get('run') else 'unknown'})")
                        else:
                            batch_failed += 1

                total_processed += len(results)
                total_completed += batch_completed
                total_failed += batch_failed

                logger.info(f"Batch {iteration} complete: {batch_completed} completed, {batch_failed} failed, {len(retry_items)} to retry")

                # Re-queue retry items for next iteration
                if retry_items:
                    # Mark old runs as failed before retrying
                    for item in retry_items:
                        # Find the old run and mark it as failed
                        old_run = self.run_manager.get_run(item.id)
                        if old_run and old_run.status == AgentStatus.RUNNING:
                            old_run.set_status(AgentStatus.FAILED, "Superseded by retry")
                    
                    # Add retry items to the beginning of remaining for next iteration
                    remaining = retry_items + [item for item in remaining if item not in batch and item not in retry_items]
                    logger.info(f"Re-queued {len(retry_items)} items for retry")

                # Generate tier reports after each batch
                items = self.parser.parse()  # Reload to get updated statuses
                await self._generate_tier_reports(items, mission_brief)

            if self._cancelled:
                logger.info("Processing cancelled by user")
            elif iteration >= self.config.max_iterations:
                logger.warning(f"Reached max iterations ({self.config.max_iterations})")

            summary = ProcessingResult(
                processed=total_processed,
                completed=total_completed,
                failed=total_failed,
                runs=all_runs,
                dry_run=self.config.dry_run,
            )

            logger.info(f"Processing complete", extra=summary.to_dict())
            self.run_manager.complete()

            return summary

        except Exception as e:
            logger.fatal(f"Processing failed: {e}")
            self.run_manager.fail(e)
            raise
    
    async def _generate_tier_reports(self, items: list[ChecklistItem], mission_brief: str | None) -> None:
        """Generate tier reports for completed tiers."""
        try:
            # Create context for report generation
            snapshot = ContextSnapshot(
                run_id=RunIdentity(
                    pipeline_run_id=uuid4(),
                    request_id=uuid4(),
                    session_id=uuid4(),
                    user_id=None,
                    org_id=None,
                    interaction_id=uuid4(),
                ),
                topology="tier_report",
                execution_mode="default",
                metadata={
                    "all_items": [item.__dict__ for item in items],
                    "mission_brief": mission_brief,
                },
            )
            
            inputs = StageInputs(snapshot=snapshot)
            ctx = StageContext(
                snapshot=snapshot,
                inputs=inputs,
                stage_name="generate_report",
                timer=PipelineTimer(),
            )
            
            result = await self.generate_report_stage.execute(ctx)
            
            if result.data and result.data.get("reports_generated"):
                for report in result.data["reports_generated"]:
                    logger.info(f"Generated tier report: {report['tier']}", extra=report)
                    
        except Exception as e:
            logger.warning(f"Failed to generate tier reports: {e}")
    
    def cancel_all(self) -> None:
        """Cancel all active runs."""
        self._cancelled = True
        self.run_agent_stage.cancel_all()
        logger.info("Cancellation requested for all agents")
    
    def get_status(self) -> dict[str, Any]:
        """Get current processor status."""
        return {
            "session": self.run_manager.session_id,
            "status": self.run_manager.status,
            "summary": self.run_manager.get_summary().to_dict(),
            "active_runs": [r.to_dict() for r in self.run_manager.get_active_runs()],
            "config": {
                "batch_size": self.config.batch_size,
                "runtime": self.config.runtime.value,
                "model": self.config.get_model(),
                "mode": self.config.mode.value,
            },
        }
    
    def subscribe(self, listener: Callable[[str, dict], None]) -> Callable[[], None]:
        """Subscribe to processor events. Returns unsubscribe function."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)
    
    def _emit_event(self, event: str, data: dict) -> None:
        """Emit an event to all listeners."""
        for listener in self._listeners:
            try:
                listener(event, data)
            except Exception as e:
                logger.warning(f"Event listener error: {e}")
    
    def _load_backlog_prompt_template(self) -> str | None:
        """Load the backlog synthesis prompt template."""
        if self._backlog_prompt_cache is not None:
            return self._backlog_prompt_cache
        
        if self._backlog_prompt_path.exists():
            self._backlog_prompt_cache = self._backlog_prompt_path.read_text(encoding="utf-8")
        return self._backlog_prompt_cache
    
    async def _extend_checklist_if_needed(self, mission_brief: str | None) -> bool:
        """
        Synthesize new checklist items when backlog runs dry in infinite mode.
        
        Returns True if items were synthesized and appended.
        """
        if self.config.mode != ProcessingMode.INFINITE:
            return False
        
        items = self.parser.parse()
        remaining = self.parser.get_remaining(items)
        needed = max(self.config.batch_size - len(remaining), 0)
        
        logger.debug(f"Infinite Mode Check: remaining={len(remaining)}, needed={needed}")
        
        if needed <= 0:
            return False
        
        logger.info(f"Infinite mode: Synthesizing {needed} new items...")
        
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would synthesize {needed} items and append to checklist")
            return True
        
        # Build synthesis prompt
        checklist_content = self.parser.read_safe(self.config.checklist_path)
        prompt = self._build_backlog_synthesis_prompt(
            mission_brief=mission_brief,
            checklist_content=checklist_content,
            needed_count=needed,
        )
        
        if not prompt:
            logger.warning("Could not build backlog synthesis prompt")
            return False
        
        try:
            # Run agent to synthesize new items
            output = await self._run_synthesis_agent(prompt)
            
            if not output:
                logger.warning("Synthesis agent returned no output")
                return False
            
            # Extract JSON payload from agent output
            payload = self._extract_json_payload(output)
            if not payload:
                logger.warning("Could not extract JSON from synthesis output")
                return False
            
            # Coerce to ChecklistItem objects
            generated_items = self._coerce_generated_items(payload)
            
            if not generated_items:
                logger.warning("Synthesis agent returned no usable checklist rows")
                return False
            
            # Limit to needed count
            generated_items = generated_items[:needed]
            
            # Append to checklist
            await self.parser.append_rows(generated_items)
            logger.info(f"Appended {len(generated_items)} synthesized items")
            
            self._emit_event("synthesis.completed", {
                "count": len(generated_items),
                "items": [item.id for item in generated_items],
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Backlog synthesis failed: {e}")
            return False
    
    def _build_backlog_synthesis_prompt(
        self,
        mission_brief: str | None,
        checklist_content: str,
        needed_count: int,
    ) -> str | None:
        """Build the prompt for backlog synthesis using template."""
        template = self._load_backlog_prompt_template()
        if not template:
            # Fallback inline prompt
            template = """You are an autonomous reliability planner. When the existing backlog runs dry you must
synthesize new checklist rows that feel like thoughtful follow-ons, not duplicates.

Current checklist markdown (for reference, do not rewrite existing rows):
{{CHECKLIST_CONTENT}}

Generate exactly {{NEEDED_COUNT}} brand-new checklist rows scoped to one autonomous run each.
Keep the same five-column structure (ID, Target, Priority, Risk, Status) and prefer concrete
SUT targets over placeholders.

Respond ONLY with JSON using the shape:
{
  "items": [
    {
      "id": "INF-123",
      "target": "...",
      "priority": "P1",
      "risk": "High",
      "status": "☐ Not Started",
      "tier": "Tier 4: Reliability & Backlog Expansion"
    }
  ]
}"""
        
        prompt = template.replace("{{CHECKLIST_CONTENT}}", checklist_content)
        prompt = prompt.replace("{{NEEDED_COUNT}}", str(needed_count))
        
        if mission_brief:
            prompt = f"Mission Brief:\n{mission_brief}\n\n{prompt}"
        
        return prompt
    
    async def _run_synthesis_agent(self, prompt: str) -> str | None:
        """Run the agent to synthesize new checklist items."""
        log_dir = self.config.state_dir / "synthesis"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"synthesis-{int(time.time() * 1000)}.log"
        
        try:
            runtime_cmd = self.config.get_runtime_command()
            runtime_config = self.config.get_runtime_config()
            model = self.config.get_model()
            args = runtime_config.build_args(model)
            
            logger.info(f"Running synthesis agent via {runtime_cmd} {' '.join(args)} (log: {log_path})")
            
            process = await asyncio.create_subprocess_exec(
                runtime_cmd,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            
            start_time = time.time()
            timed_out = False
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    process.communicate(input=prompt.encode()),
                    timeout=180,  # 3 min timeout
                )
            except asyncio.TimeoutError:
                timed_out = True
                process.kill()
                stdout_data, stderr_data = await process.communicate()
            
            duration = time.time() - start_time
            stdout_text = stdout_data.decode(errors="replace")
            stderr_text = stderr_data.decode(errors="replace")
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write("=== Synthesis Agent Output ===\n")
                log_file.write(f"Runtime: {runtime_cmd}\nModel: {model}\n")
                log_file.write(f"Duration: {duration:.2f}s\n")
                log_file.write(f"Timed out: {timed_out}\n")
                log_file.write("=" * 60 + "\n\n")
                log_file.write("--- STDOUT ---\n")
                log_file.write(stdout_text or "<empty>\n")
                log_file.write("\n--- STDERR ---\n")
                log_file.write(stderr_text or "<empty>\n")
                log_file.write("\n" + "=" * 60 + "\n")
                log_file.write(f"Exit code: {process.returncode}\n")
                if timed_out:
                    log_file.write("[SYNTHESIS] TIMED OUT AFTER 180s\n")
            
            if timed_out:
                logger.error(f"Synthesis agent timed out after 180s (log: {log_path})")
                return None
            
            if process.returncode != 0:
                logger.error(f"Synthesis agent failed: exit code {process.returncode} (log: {log_path})")
                return None
            
            logger.info(
                "Synthesis agent completed",
                extra={
                    "duration_sec": round(duration, 2),
                    "stdout_bytes": len(stdout_data),
                    "stderr_bytes": len(stderr_data),
                    "log_path": str(log_path),
                },
            )
            # Return stdout only - stderr often contains log noise that breaks JSON parsing
            return stdout_text
            
        except Exception as e:
            logger.error(f"Failed to run synthesis agent: {e} (log: {log_path})")
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n[SYNTHESIS] ERROR: {e}\n")
            return None
    
    def _extract_json_payload(self, text: str) -> dict | None:
        """Extract JSON payload from agent output."""
        if not text:
            return None
        
        # Remove ANSI escape codes
        clean = re.sub(r'\x1b\[[0-9;]*m', '', text)
        
        # Try to find JSON block
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # Markdown code block
            r'```\s*([\s\S]*?)\s*```',       # Generic code block
            r'(\{[\s\S]*"items"[\s\S]*\})',  # Raw JSON with items
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, clean)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        
        # Try parsing the whole output as JSON
        try:
            return json.loads(clean.strip())
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _coerce_generated_items(self, payload: dict) -> list[ChecklistItem]:
        """Convert JSON payload to ChecklistItem objects."""
        if not payload or not isinstance(payload, dict):
            return []
        
        items_data = payload.get("items", [])
        if not isinstance(items_data, list):
            return []
        
        result = []
        for item_data in items_data:
            if not isinstance(item_data, dict):
                continue
            
            try:
                item = ChecklistItem(
                    id=str(item_data.get("id", f"INF-{uuid4().hex[:6]}")),
                    target=str(item_data.get("target", "Unknown target")),
                    priority=str(item_data.get("priority", "Medium")),
                    risk=str(item_data.get("risk", "Medium")),
                    status=str(item_data.get("status", "☐ Not Started")),
                    tier=str(item_data.get("tier", "Tier 4: Reliability & Backlog Expansion")),
                    section="",
                )
                result.append(item)
            except Exception as e:
                logger.warning(f"Failed to coerce item: {e}")
                continue
        
        return result
