"""
Observability Interceptor - provides detailed logging and metrics.

Implements comprehensive observability for debugging and monitoring.
"""

import time
from datetime import datetime
from typing import Any

from stageflow import BaseInterceptor

from ..utils.logger import get_logger

logger = get_logger("observability")


class ObservabilityInterceptor(BaseInterceptor):
    """
    Interceptor that provides detailed observability.
    
    Features:
    - Stage timing metrics
    - Structured logging with context
    - Event emission for monitoring
    - Error tracking and summarization
    """
    
    name = "observability"
    priority = 45  # After metrics, before logging
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._stage_timings: dict[str, float] = {}
        self._stage_counts: dict[str, dict[str, int]] = {}
    
    def _get_key(self, pipeline_run_id: Any, stage_name: str) -> str:
        """Generate a unique key for tracking."""
        return f"{pipeline_run_id}:{stage_name}"
    
    async def before(self, stage_name: str, ctx) -> None:
        """Log stage start and record timing."""
        key = self._get_key(ctx.pipeline_run_id, stage_name)
        self._stage_timings[key] = time.time()
        
        # Initialize counts
        if stage_name not in self._stage_counts:
            self._stage_counts[stage_name] = {"started": 0, "completed": 0, "failed": 0}
        self._stage_counts[stage_name]["started"] += 1
        
        log_data = {
            "stage": stage_name,
            "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
            "timestamp": datetime.now().isoformat(),
        }
        
        if self.verbose:
            logger.debug(f"Stage starting: {stage_name}", extra=log_data)
        else:
            logger.info(f"▶ {stage_name}", extra=log_data)
    
    async def after(self, stage_name: str, result, ctx) -> None:
        """Log stage completion with timing."""
        key = self._get_key(ctx.pipeline_run_id, stage_name)
        start_time = self._stage_timings.pop(key, None)
        
        duration_ms = int((time.time() - start_time) * 1000) if start_time else 0
        
        # Update counts
        status = getattr(result, "status", "unknown")
        if status == "completed":
            self._stage_counts[stage_name]["completed"] += 1
        elif status in ("failed", "error"):
            self._stage_counts[stage_name]["failed"] += 1
        
        log_data = {
            "stage": stage_name,
            "status": status,
            "duration_ms": duration_ms,
            "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
        }
        
        # Include output summary if verbose
        if self.verbose and hasattr(result, "data"):
            log_data["output_keys"] = list(result.data.keys()) if result.data else []
        
        if status in ("failed", "error"):
            error_msg = getattr(result, "error", None)
            logger.warning(f"✗ {stage_name} ({duration_ms}ms) - {error_msg}", extra=log_data)
        elif status == "skipped":
            reason = getattr(result, "reason", "unknown")
            logger.info(f"⊘ {stage_name} skipped: {reason}", extra=log_data)
        else:
            logger.info(f"✓ {stage_name} ({duration_ms}ms)", extra=log_data)
    
    async def on_error(self, stage_name: str, error: Exception, ctx):
        """Log errors with full context."""
        key = self._get_key(ctx.pipeline_run_id, stage_name)
        start_time = self._stage_timings.pop(key, None)
        duration_ms = int((time.time() - start_time) * 1000) if start_time else 0
        
        self._stage_counts.get(stage_name, {})["failed"] = \
            self._stage_counts.get(stage_name, {}).get("failed", 0) + 1
        
        log_data = {
            "stage": stage_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "duration_ms": duration_ms,
            "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
        }
        
        logger.error(f"✗ {stage_name} error: {error}", extra=log_data)
        
        # Don't override error handling - let other interceptors decide
        return None
    
    def get_metrics(self) -> dict[str, Any]:
        """Get accumulated metrics."""
        return {
            "stage_counts": dict(self._stage_counts),
            "active_stages": len(self._stage_timings),
        }
    
    def reset_metrics(self) -> None:
        """Reset accumulated metrics."""
        self._stage_counts.clear()
        self._stage_timings.clear()
