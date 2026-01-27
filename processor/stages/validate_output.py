"""
Validate Output Stage - validates agent output and determines success.

Single responsibility: Validate agent output meets completion criteria.
"""

from pathlib import Path
from stageflow import StageContext, StageKind, StageOutput


class ValidateOutputStage:
    """Stage that validates agent output."""
    
    name = "validate_output"
    kind = StageKind.GUARD
    
    def __init__(self, require_completion_marker: bool = True):
        self.require_completion_marker = require_completion_marker
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Validate the agent output."""
        # Get output from run_agent stage
        output = ctx.inputs.get_from("run_agent", "output", default="")
        completed = ctx.inputs.get_from("run_agent", "completed", default=False)
        item_id = ctx.inputs.get_from("run_agent", "item_id")
        log_path = ctx.inputs.get_from("run_agent", "log_path")
        dry_run = ctx.inputs.get_from("run_agent", "dry_run", default=False)
        
        if dry_run:
            return StageOutput.ok(
                validated=True,
                dry_run=True,
                item_id=item_id,
            )
        
        # Check for completion marker
        if self.require_completion_marker and not completed:
            ctx.try_emit_event("validation.failed", {
                "item_id": item_id,
                "reason": "missing_completion_marker",
            })
            return StageOutput.fail(
                error="Agent finished without completion marker",
                data={
                    "item_id": item_id,
                    "log_path": log_path,
                    "output_tail": output[-500:] if output else "",
                },
            )
        
        # Check for final report
        metadata = ctx.snapshot.metadata or {}
        run_dir = metadata.get("run_dir")
        if run_dir:
            final_report = Path(run_dir) / f"{item_id}-FINAL-REPORT.md"
            has_report = final_report.exists()
        else:
            has_report = False
        
        ctx.try_emit_event("validation.passed", {
            "item_id": item_id,
            "has_completion_marker": completed,
            "has_final_report": has_report,
        })
        
        return StageOutput.ok(
            validated=True,
            item_id=item_id,
            has_completion_marker=completed,
            has_final_report=has_report,
            output_length=len(output),
        )
