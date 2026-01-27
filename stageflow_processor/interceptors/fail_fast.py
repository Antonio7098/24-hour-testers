"""
Fail Fast Interceptor - validates inputs before stage execution.

Implements fail-fast principles to catch configuration errors early.
"""

from typing import Any

from stageflow import BaseInterceptor, InterceptorResult

from ..utils.logger import get_logger

logger = get_logger("fail_fast")


class FailFastInterceptor(BaseInterceptor):
    """
    Interceptor that validates inputs before stage execution.
    
    Features:
    - Required input validation
    - Configuration validation
    - Early failure with clear error messages
    """
    
    name = "fail_fast"
    priority = 3  # Very early, after auth
    
    # Required inputs per stage
    STAGE_REQUIREMENTS: dict[str, list[str]] = {
        "build_prompt": ["item", "run_dir"],
        "run_agent": [],  # Gets inputs from previous stage
        "validate_output": [],
        "update_status": [],
    }
    
    def __init__(self, strict: bool = True):
        self.strict = strict
        self._validation_errors: list[dict[str, Any]] = []
    
    async def before(self, stage_name: str, ctx) -> InterceptorResult | None:
        """Validate stage inputs before execution."""
        requirements = self.STAGE_REQUIREMENTS.get(stage_name, [])
        
        if not requirements:
            return None
        
        missing = []
        for req in requirements:
            value = getattr(ctx.snapshot, req, None) if hasattr(ctx, "snapshot") else None
            if value is None:
                # Also check ctx.data
                if hasattr(ctx, "data"):
                    value = ctx.data.get(req)
            if value is None:
                missing.append(req)
        
        if missing:
            error_msg = f"Stage '{stage_name}' missing required inputs: {', '.join(missing)}"
            
            self._validation_errors.append({
                "stage": stage_name,
                "missing": missing,
                "timestamp": str(__import__("datetime").datetime.now()),
            })
            
            if self.strict:
                logger.error(error_msg)
                return InterceptorResult(
                    stage_ran=False,
                    error=error_msg,
                    result={"validation_failed": True, "missing_inputs": missing},
                )
            else:
                logger.warning(f"Non-strict validation: {error_msg}")
        
        return None
    
    async def after(self, stage_name: str, result, ctx) -> None:
        """No-op for successful stages."""
        pass
    
    async def on_error(self, stage_name: str, error: Exception, ctx):
        """Log validation-related errors."""
        if "missing" in str(error).lower() or "required" in str(error).lower():
            logger.error(f"Possible validation error in {stage_name}: {error}")
        return None  # Don't override error handling
    
    def get_validation_errors(self) -> list[dict[str, Any]]:
        """Get accumulated validation errors."""
        return list(self._validation_errors)
    
    def clear_errors(self) -> None:
        """Clear accumulated validation errors."""
        self._validation_errors.clear()
