"""
Run Agent Stage - executes the agent process for a checklist item.

Features:
- Dynamic timeout based on item priority
- Phase-based checkpoints with resume capability
- Real-time output streaming to log file
- Early warning system for hanging processes
- Progressive retry support
"""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from stageflow import StageContext, StageKind, StageOutput

from ..config import ProcessorConfig, AgentRuntime
from ..models import AgentRun, AgentStatus, RunStage, ChecklistItem
from ..utils.process_utils import resolve_executable, normalize_path
from ..utils.logger import get_logger
from ..checkpoint import CheckpointManager, Checkpoint, Phase, detect_phase_completion

logger = get_logger("run_agent")

COMPLETION_MARKER = "ITEM_COMPLETE"

# Early warning thresholds (seconds)
NO_OUTPUT_WARNING_THRESHOLD = 120  # Warn if no output for 2 minutes
RESEARCH_PHASE_WARNING_THRESHOLD = 180  # Warn if research takes > 3 minutes


class OutputMonitor:
    """Monitors agent output for early warning detection."""

    def __init__(self, item_id: str, log_path: Path):
        self.item_id = item_id
        self.log_path = log_path
        self.last_output_time = time.time()
        self.total_bytes = 0
        self.warnings_emitted: set[str] = set()
        self.phase_start_times: dict[str, float] = {}

    def on_output(self, data: bytes, ctx: StageContext | None = None) -> None:
        """Called when output is received."""
        if data:
            self.last_output_time = time.time()
            self.total_bytes += len(data)

            # Append to log file in real-time
            try:
                with open(self.log_path, "ab") as f:
                    f.write(data)
            except Exception as e:
                logger.warning(f"Failed to write to log: {e}")

            # Detect phase transitions from output
            text = data.decode(errors="replace").lower()
            if "research" in text and "research" not in self.phase_start_times:
                self.phase_start_times["research"] = time.time()
            elif "test" in text and "tests" not in self.phase_start_times:
                self.phase_start_times["tests"] = time.time()
            elif "execut" in text and "execution" not in self.phase_start_times:
                self.phase_start_times["execution"] = time.time()

    def check_warnings(self, ctx: StageContext | None = None) -> list[str]:
        """Check for warning conditions. Returns list of warnings."""
        warnings = []
        now = time.time()

        # Check for no output
        silence_duration = now - self.last_output_time
        if silence_duration > NO_OUTPUT_WARNING_THRESHOLD:
            warning_key = f"no_output_{int(silence_duration // 60)}"
            if warning_key not in self.warnings_emitted:
                self.warnings_emitted.add(warning_key)
                msg = f"No output for {int(silence_duration)}s - possible hang"
                warnings.append(msg)
                logger.warning(f"[{self.item_id}] {msg}")
                if ctx:
                    ctx.try_emit_event("agent.warning", {
                        "item_id": self.item_id,
                        "warning": "no_output",
                        "duration_sec": int(silence_duration),
                    })

        # Check research phase duration
        if "research" in self.phase_start_times:
            research_duration = now - self.phase_start_times["research"]
            if research_duration > RESEARCH_PHASE_WARNING_THRESHOLD:
                warning_key = "research_slow"
                if warning_key not in self.warnings_emitted:
                    self.warnings_emitted.add(warning_key)
                    msg = f"Research phase taking {int(research_duration)}s"
                    warnings.append(msg)
                    logger.warning(f"[{self.item_id}] {msg}")

        return warnings


class RunAgentStage:
    """Stage that runs the agent process for an item."""

    name = "run_agent"
    kind = StageKind.WORK

    def __init__(self, config: ProcessorConfig):
        self.config = config
        self._active_processes: dict[str, asyncio.subprocess.Process] = {}
        self._monitors: dict[str, OutputMonitor] = {}
        self._checkpoint_manager = CheckpointManager(config.runs_dir) if config.enable_checkpoints else None

    def _build_command(self) -> tuple[str, list[str]]:
        """Build the command and arguments for the agent runtime."""
        runtime_config = self.config.get_runtime_config()
        command = resolve_executable(self.config.get_runtime_command())
        model = self.config.get_model()
        args = runtime_config.build_args(model)
        return command, args

    def _get_timeout_for_item(self, item: ChecklistItem, attempt: int = 1) -> int:
        """Get dynamic timeout based on item priority and attempt number."""
        return self.config.timeouts.get_timeout_for_priority(item.priority, attempt)

    def _build_resume_prompt(self, prompt: str, checkpoint: Checkpoint) -> str:
        """Modify prompt with resume instructions if resuming from checkpoint."""
        if checkpoint.phase == Phase.INIT:
            return prompt

        resume_instructions = self._checkpoint_manager.get_resume_instructions(checkpoint)
        if resume_instructions:
            # Insert resume instructions after the main prompt header
            return f"{prompt}\n\n{resume_instructions}"

        return prompt

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute the agent process."""
        # Get inputs from previous stage
        prompt = ctx.inputs.get_from("build_prompt", "prompt")
        if not prompt:
            return StageOutput.fail(error="No prompt provided from build_prompt stage")

        item_id = ctx.inputs.get_from("build_prompt", "item_id")
        run_dir = ctx.inputs.get_from("build_prompt", "run_dir")
        completion_marker = ctx.inputs.get_from("build_prompt", "completion_marker", default=COMPLETION_MARKER)

        # Get item and run tracking from context metadata
        metadata = ctx.snapshot.metadata or {}
        run: AgentRun | None = metadata.get("agent_run")
        item_data = metadata.get("item")
        item = ChecklistItem(**item_data) if isinstance(item_data, dict) else item_data

        # Get attempt number for progressive retry
        attempt = metadata.get("attempt", 1)

        if self.config.dry_run:
            return StageOutput.ok(
                output="[DRY RUN] Would execute agent",
                completed=True,
                dry_run=True,
                item_id=item_id,
            )

        # Load or create checkpoint
        checkpoint = None
        run_dir_path = Path(run_dir) if run_dir else None

        if self._checkpoint_manager and run_dir_path:
            checkpoint = self._checkpoint_manager.load(run_dir_path, item_id)

            # On retry attempts, try to resume from checkpoint
            if attempt > 1 and self.config.retry.use_checkpoint_on_retry:
                if checkpoint.phase not in (Phase.INIT, Phase.COMPLETE):
                    logger.info(f"Resuming {item_id} from checkpoint: phase={checkpoint.phase.value}")
                    prompt = self._build_resume_prompt(prompt, checkpoint)
                    checkpoint.attempt = attempt

        # Get dynamic timeout based on priority
        timeout_ms = self._get_timeout_for_item(item, attempt) if item else self.config.timeout_ms
        timeout_sec = timeout_ms / 1000

        # Build command
        command, args = self._build_command()

        # Setup logging with normalized paths
        if run_dir_path:
            log_dir = Path(normalize_path(run_dir_path)) / "results"
        else:
            log_dir = Path(normalize_path(self.config.state_dir))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"agent-{item_id}-{int(datetime.now().timestamp() * 1000)}.log"

        # Write log header
        with open(log_path, "w") as f:
            f.write(f"=== Agent Run: {item_id} ===\n")
            f.write(f"Started: {datetime.now().isoformat()}\n")
            f.write(f"Runtime: {self.config.runtime.value}\n")
            f.write(f"Model: {self.config.get_model()}\n")
            f.write(f"Timeout: {timeout_ms}ms ({timeout_sec:.0f}s)\n")
            f.write(f"Attempt: {attempt}\n")
            if checkpoint and checkpoint.phase != Phase.INIT:
                f.write(f"Resuming from: {checkpoint.phase.value}\n")
            f.write("=" * 50 + "\n\n")

        # Create output monitor for early warning detection
        monitor = OutputMonitor(item_id, log_path)
        self._monitors[item_id] = monitor

        # Emit start event
        ctx.try_emit_event("agent.started", {
            "item_id": item_id,
            "runtime": self.config.runtime.value,
            "model": self.config.get_model(),
            "timeout_ms": timeout_ms,
            "attempt": attempt,
            "resuming_from": checkpoint.phase.value if checkpoint and checkpoint.phase != Phase.INIT else None,
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

            # Send prompt to stdin
            process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()

            # Read output with real-time streaming and monitoring
            output_chunks = []
            start_time = time.time()
            warning_check_interval = 30  # Check for warnings every 30 seconds
            last_warning_check = start_time

            async def read_stream(stream, is_stderr=False):
                """Read from stream and update monitor."""
                while True:
                    # Check if overall timeout has been exceeded
                    elapsed = time.time() - start_time
                    if elapsed > timeout_sec:
                        # Timeout exceeded - exit loop
                        break
                    
                    try:
                        # Use a shorter timeout to allow frequent checks
                        read_timeout = min(10.0, timeout_sec - elapsed + 1)
                        if read_timeout <= 0:
                            break
                            
                        chunk = await asyncio.wait_for(
                            stream.read(4096),
                            timeout=read_timeout
                        )
                        if not chunk:
                            break
                        monitor.on_output(chunk, ctx)
                        output_chunks.append(chunk)
                    except asyncio.TimeoutError:
                        # Inner read timeout - check if process is still running
                        if process.returncode is not None:
                            break
                        # Check for warnings during read timeout
                        nonlocal last_warning_check
                        now = time.time()
                        if now - last_warning_check > warning_check_interval:
                            monitor.check_warnings(ctx)
                            last_warning_check = now
                        continue
                    except Exception:
                        break

            # Create tasks for reading both streams with watchdog timeout
            stdout_task = asyncio.create_task(read_stream(process.stdout))
            stderr_task = asyncio.create_task(read_stream(process.stderr, is_stderr=True))
            
            timed_out = False
            try:
                # Use asyncio.wait with timeout for proper cancellation
                done, pending = await asyncio.wait(
                    [stdout_task, stderr_task],
                    timeout=timeout_sec,
                    return_when=asyncio.ALL_COMPLETED
                )
                
                # Cancel any pending tasks (shouldn't happen unless timeout)
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check if tasks completed or timed out
                if stdout_task in done and stderr_task in done:
                    # Both completed - check exit code
                    await process.wait()
                else:
                    # Timeout occurred
                    raise asyncio.TimeoutError()
                    
            except asyncio.TimeoutError:
                timed_out = True
                elapsed = time.time() - start_time

                if checkpoint and self._checkpoint_manager and run_dir_path:
                    # Detect what phase we reached
                    detected_phase = Phase.from_artifacts(run_dir_path)
                    if detected_phase != checkpoint.phase:
                        checkpoint.phase = detected_phase
                        checkpoint.elapsed_ms = int(elapsed * 1000)
                        checkpoint.add_error(f"Timeout after {elapsed:.0f}s at phase {detected_phase.value}")
                        self._checkpoint_manager.save(run_dir_path, checkpoint)
                        logger.info(f"Saved checkpoint for {item_id}: phase={detected_phase.value}")

                # Write timeout info to log
                with open(log_path, "a") as f:
                    f.write(f"\n{'=' * 50}\n")
                    f.write(f"TIMEOUT after {elapsed:.0f}s (limit: {timeout_sec:.0f}s)\n")
                    f.write(f"Phase reached: {detected_phase.value if checkpoint else 'unknown'}\n")
                    f.write(f"Output bytes: {monitor.total_bytes}\n")

                ctx.try_emit_event("agent.timeout", {
                    "item_id": item_id,
                    "timeout_ms": timeout_ms,
                    "elapsed_ms": int(elapsed * 1000),
                    "phase_reached": detected_phase.value if checkpoint else None,
                    "output_bytes": monitor.total_bytes,
                })

                # Kill the process
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()

                return StageOutput.retry(
                    error=f"Agent timed out after {int(elapsed)}s (phase: {detected_phase.value if checkpoint else 'unknown'})",
                    data={
                        "item_id": item_id,
                        "timeout_ms": timeout_ms,
                        "elapsed_ms": int(elapsed * 1000),
                        "phase_reached": detected_phase.value if checkpoint else None,
                        "output_bytes": monitor.total_bytes,
                        "retryable": True,
                        "has_checkpoint": checkpoint is not None and checkpoint.phase != Phase.INIT,
                    },
                )

            # Process completed - combine output
            output = b"".join(output_chunks).decode(errors="replace")

            # Write completion to log
            with open(log_path, "a") as f:
                f.write(f"\n{'=' * 50}\n")
                f.write(f"Ended: {datetime.now().isoformat()}\n")
                f.write(f"Exit code: {process.returncode}\n")
                f.write(f"Total output: {len(output)} bytes\n")

            # Update checkpoint on completion
            if checkpoint and self._checkpoint_manager and run_dir_path:
                detected_phase = Phase.from_artifacts(run_dir_path)
                checkpoint.phase = detected_phase
                self._checkpoint_manager.save(run_dir_path, checkpoint)

            # Check exit code
            if process.returncode != 0:
                ctx.try_emit_event("agent.failed", {
                    "item_id": item_id,
                    "exit_code": process.returncode,
                    "output_bytes": len(output),
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

            # Delete checkpoint on successful completion
            if has_marker and self._checkpoint_manager and run_dir_path:
                self._checkpoint_manager.delete(run_dir_path)

            return StageOutput.ok(
                output=output,
                completed=has_marker,
                item_id=item_id,
                log_path=str(log_path),
                exit_code=process.returncode,
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
            self._monitors.pop(item_id, None)

    def cancel_all(self) -> None:
        """Cancel all active agent processes."""
        for item_id, process in list(self._active_processes.items()):
            try:
                process.terminate()
            except Exception:
                pass
        self._active_processes.clear()
        self._monitors.clear()
