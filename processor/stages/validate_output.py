"""
Validate Output Stage - validates agent output and determines success.

Single responsibility: Validate agent output meets completion criteria.
Strict mode: Requires FINAL_REPORT.md to be present, not just completion marker.
"""

from pathlib import Path
from stageflow import StageContext, StageKind, StageOutput


class ValidateOutputStage:
    """Stage that validates agent output."""

    name = "validate_output"
    kind = StageKind.GUARD

    def __init__(
        self,
        require_completion_marker: bool = True,
        require_final_report: bool = True,
    ):
        self.require_completion_marker = require_completion_marker
        self.require_final_report = require_final_report

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

        # Check for final report first (stricter validation)
        metadata = ctx.snapshot.metadata or {}
        run_dir = metadata.get("run_dir")
        has_report = False

        if run_dir:
            final_report = Path(run_dir) / f"{item_id}-FINAL-REPORT.md"
            has_report = final_report.exists()

        # Strict validation: require FINAL_REPORT.md
        if self.require_final_report and not has_report:
            # Check if we have completion marker but no report
            if completed:
                ctx.try_emit_event("validation.failed", {
                    "item_id": item_id,
                    "reason": "missing_final_report",
                    "has_completion_marker": True,
                })
                return StageOutput.fail(
                    error="Agent finished without FINAL_REPORT.md (completion marker present but report missing)",
                    data={
                        "item_id": item_id,
                        "log_path": log_path,
                        "has_completion_marker": True,
                        "expected_report": str(Path(run_dir) / f"{item_id}-FINAL-REPORT.md") if run_dir else None,
                        "output_tail": output[-500:] if output else "",
                    },
                )
            else:
                ctx.try_emit_event("validation.failed", {
                    "item_id": item_id,
                    "reason": "missing_completion_marker_and_report",
                })
                return StageOutput.fail(
                    error="Agent finished without completion marker and without FINAL_REPORT.md",
                    data={
                        "item_id": item_id,
                        "log_path": log_path,
                        "has_completion_marker": False,
                        "output_tail": output[-500:] if output else "",
                    },
                )

        # If we have the report but missing completion marker, that's acceptable
        # (the report is the primary deliverable)
        if has_report and not completed:
            ctx.try_emit_event("validation.passed", {
                "item_id": item_id,
                "has_completion_marker": False,
                "has_final_report": True,
                "note": "Completed via final report creation",
            })
            return StageOutput.ok(
                validated=True,
                item_id=item_id,
                has_completion_marker=False,
                has_final_report=True,
                output_length=len(output),
                note="Completed via final report creation",
            )

        # Check for completion marker (secondary check)
        if self.require_completion_marker and not completed and not has_report:
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
