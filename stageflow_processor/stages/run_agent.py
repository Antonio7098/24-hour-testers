"""
Run Agent Stage - executes the agent process for a checklist item.

Single responsibility: Spawn and manage agent subprocess.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from stageflow import StageContext, StageKind, StageOutput

from ..config import ProcessorConfig, AgentRuntime
from ..models import AgentRun, AgentStatus, RunStage
from ..utils.process_utils import resolve_executable

COMPLETION_MARKER = "ITEM_COMPLETE"


class RunAgentStage:
    """Stage that runs the agent process for an item."""
    
    name = "run_agent"
    kind = StageKind.WORK
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self._active_processes: dict[str, asyncio.subprocess.Process] = {}
    
    def _build_command(self) -> tuple[str, list[str]]:
        """Build the command and arguments for the agent runtime."""
        runtime_config = self.config.get_runtime_config()
        command = resolve_executable(self.config.get_runtime_command())
        model = self.config.get_model()
        args = runtime_config.build_args(model)
        return command, args
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute the agent process."""
        # Get inputs from previous stage
        prompt = ctx.inputs.get_from("build_prompt", "prompt")
        if not prompt:
            return StageOutput.fail(error="No prompt provided from build_prompt stage")
        
        item_id = ctx.inputs.get_from("build_prompt", "item_id")
        run_dir = ctx.inputs.get_from("build_prompt", "run_dir")
        completion_marker = ctx.inputs.get_from("build_prompt", "completion_marker", default=COMPLETION_MARKER)
        
        # Get run tracking from context metadata
        metadata = ctx.snapshot.metadata or {}
        run: AgentRun | None = metadata.get("agent_run")
        
        if self.config.dry_run:
            return StageOutput.ok(
                output="[DRY RUN] Would execute agent",
                completed=True,
                dry_run=True,
                item_id=item_id,
            )
        
        # Build command
        command, args = self._build_command()
        
        # Setup logging
        log_dir = Path(run_dir) / "results" if run_dir else self.config.state_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"agent-{item_id}-{int(datetime.now().timestamp() * 1000)}.log"
        
        # Write log header
        with open(log_path, "w") as f:
            f.write(f"=== Agent Run: {item_id} ===\n")
            f.write(f"Started: {datetime.now().isoformat()}\n")
            f.write(f"Runtime: {self.config.runtime.value}\n")
            f.write(f"Model: {self.config.get_model()}\n")
            f.write("=" * 50 + "\n\n")
        
        # Emit start event
        ctx.try_emit_event("agent.started", {
            "item_id": item_id,
            "runtime": self.config.runtime.value,
            "model": self.config.get_model(),
        })
        
        try:
            # Spawn process
            process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            
            self._active_processes[item_id] = process
            
            if run:
                run.pid = process.pid
                run.log_path = log_path
                run.set_status(AgentStatus.RUNNING)
                run.set_stage(RunStage.PROCESSING)
            
            # Write prompt to stdin
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(input=prompt.encode()),
                timeout=self.config.timeout_ms / 1000,
            )
            
            output = stdout_data.decode() + stderr_data.decode()
            
            # Write output to log
            with open(log_path, "a") as f:
                f.write(output)
                f.write("\n" + "=" * 50 + "\n")
                f.write(f"Ended: {datetime.now().isoformat()}\n")
                f.write(f"Exit code: {process.returncode}\n")
            
            # Check exit code
            if process.returncode != 0:
                ctx.try_emit_event("agent.failed", {
                    "item_id": item_id,
                    "exit_code": process.returncode,
                })
                return StageOutput.fail(
                    error=f"Agent exited with code {process.returncode}",
                    data={
                        "output": output[-2000:],  # Last 2000 chars
                        "exit_code": process.returncode,
                        "item_id": item_id,
                        "log_path": str(log_path),
                    },
                )
            
            # Check for completion marker
            has_marker = completion_marker in output
            
            ctx.try_emit_event("agent.completed", {
                "item_id": item_id,
                "has_completion_marker": has_marker,
                "output_length": len(output),
            })
            
            return StageOutput.ok(
                output=output,
                completed=has_marker,
                item_id=item_id,
                log_path=str(log_path),
                exit_code=process.returncode,
            )
            
        except asyncio.TimeoutError:
            ctx.try_emit_event("agent.timeout", {
                "item_id": item_id,
                "timeout_ms": self.config.timeout_ms,
            })
            
            # Try to kill the process
            if item_id in self._active_processes:
                proc = self._active_processes[item_id]
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
            
            return StageOutput.retry(
                error=f"Agent timed out after {self.config.timeout_ms}ms",
                data={
                    "item_id": item_id,
                    "timeout_ms": self.config.timeout_ms,
                    "retryable": True,
                },
            )
            
        except Exception as e:
            ctx.try_emit_event("agent.error", {
                "item_id": item_id,
                "error": str(e),
                "error_type": type(e).__name__,
            })
            return StageOutput.fail(
                error=f"Agent execution failed: {e}",
                data={
                    "item_id": item_id,
                    "error_type": type(e).__name__,
                },
            )
        finally:
            self._active_processes.pop(item_id, None)
    
    def cancel_all(self) -> None:
        """Cancel all active agent processes."""
        for item_id, process in list(self._active_processes.items()):
            try:
                process.terminate()
            except Exception:
                pass
        self._active_processes.clear()
