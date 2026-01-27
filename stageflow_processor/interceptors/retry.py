"""
Retry Interceptor - handles retry logic with exponential backoff.

Implements robust retry patterns for transient failures.
"""

import asyncio
import random
from collections import defaultdict
from typing import Any

from stageflow import BaseInterceptor, ErrorAction

from ..config import RetryConfig
from ..utils.logger import get_logger

logger = get_logger("retry_interceptor")


class RetryInterceptor(BaseInterceptor):
    """
    Interceptor that implements retry logic with exponential backoff.
    
    Features:
    - Exponential backoff with jitter
    - Per-stage retry tracking
    - Configurable retryable error detection
    - Automatic cleanup of retry state
    """
    
    name = "retry"
    priority = 12  # After circuit breaker, before tracing
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self._retry_counts: dict[str, int] = defaultdict(int)
        self._last_errors: dict[str, Exception] = {}
    
    def _get_key(self, pipeline_run_id: Any, stage_name: str) -> str:
        """Generate a unique key for tracking retries."""
        return f"{pipeline_run_id}:{stage_name}"
    
    def _is_retryable(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        error_msg = str(error).lower()
        
        # Check error codes
        for code in self.config.retryable_errors:
            if code.lower() in error_msg:
                return True
        
        # Check for timeout errors
        if "timeout" in error_msg or "timed out" in error_msg:
            return True
        
        # Check for connection errors
        if any(x in error_msg for x in ["connection", "network", "eagain"]):
            return True
        
        # Check for exit code errors (potentially retryable)
        if "exited with code" in error_msg:
            return True
        
        # Check if error has a 'retryable' attribute
        if hasattr(error, "retryable") and error.retryable:
            return True
        
        return False
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        delay = self.config.base_delay_ms * (self.config.backoff_multiplier ** attempt)
        jitter = random.random() * 0.3 * delay  # 0-30% jitter
        return min(delay + jitter, self.config.max_delay_ms) / 1000  # Convert to seconds
    
    async def before(self, stage_name: str, ctx) -> None:
        """Called before stage execution."""
        key = self._get_key(ctx.pipeline_run_id, stage_name)
        attempt = self._retry_counts.get(key, 0)
        
        if attempt > 0:
            logger.info(
                f"Retry attempt {attempt}/{self.config.max_retries} for stage {stage_name}",
                extra={"stage": stage_name, "attempt": attempt},
            )
    
    async def after(self, stage_name: str, result, ctx) -> None:
        """Called after successful stage completion - cleanup retry state."""
        key = self._get_key(ctx.pipeline_run_id, stage_name)
        self._retry_counts.pop(key, None)
        self._last_errors.pop(key, None)
    
    async def on_error(self, stage_name: str, error: Exception, ctx) -> ErrorAction:
        """Handle errors and decide whether to retry."""
        key = self._get_key(ctx.pipeline_run_id, stage_name)
        
        # Check if error is retryable
        if not self._is_retryable(error):
            logger.debug(f"Error not retryable: {error}")
            self._retry_counts.pop(key, None)
            return ErrorAction.FAIL
        
        # Check retry count
        current_count = self._retry_counts[key]
        if current_count >= self.config.max_retries:
            logger.warning(
                f"Max retries ({self.config.max_retries}) exceeded for {stage_name}",
                extra={"stage": stage_name, "attempts": current_count + 1},
            )
            self._retry_counts.pop(key, None)
            return ErrorAction.FAIL
        
        # Calculate delay and wait
        delay = self._calculate_delay(current_count)
        logger.info(
            f"Retrying {stage_name} in {delay:.1f}s (attempt {current_count + 1}/{self.config.max_retries})",
            extra={"stage": stage_name, "delay_s": delay, "attempt": current_count + 1},
        )
        
        await asyncio.sleep(delay)
        
        # Increment counter and retry
        self._retry_counts[key] = current_count + 1
        self._last_errors[key] = error
        
        return ErrorAction.RETRY
    
    def get_retry_stats(self) -> dict[str, Any]:
        """Get current retry statistics."""
        return {
            "active_retries": len(self._retry_counts),
            "retry_counts": dict(self._retry_counts),
        }
    
    def reset(self) -> None:
        """Reset all retry state."""
        self._retry_counts.clear()
        self._last_errors.clear()
