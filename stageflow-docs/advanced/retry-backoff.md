# Retry & Backoff Patterns

Transient failures—network timeouts, rate limits, service unavailability—are inevitable
in distributed systems. This guide covers retry strategies, backoff algorithms, and
jitter configurations to build resilient pipelines.

## When to Retry

| Error Type | Retry? | Rationale |
|------------|--------|-----------|
| Network timeout | ✅ Yes | Transient connectivity issue |
| 429 Too Many Requests | ✅ Yes | Rate limit, back off and retry |
| 503 Service Unavailable | ✅ Yes | Temporary overload |
| 500 Internal Server Error | ⚠️ Maybe | May be transient or persistent |
| 400 Bad Request | ❌ No | Client error, won't change |
| 401 Unauthorized | ❌ No | Auth issue, need new credentials |
| 404 Not Found | ❌ No | Resource doesn't exist |

**Rule of thumb:** Retry transient errors with backoff. Fail fast on client errors.

## Backoff Strategies

### Exponential Backoff

Delays grow exponentially: `base * 2^attempt`. Reduces load during outages.

```python
def exponential_delay(attempt: int, base_ms: int = 1000) -> int:
    """Calculate exponential backoff delay.
    
    Args:
        attempt: Current attempt number (0-indexed)
        base_ms: Base delay in milliseconds
    
    Returns:
        Delay in milliseconds
    
    Example:
        attempt 0: 1000ms
        attempt 1: 2000ms
        attempt 2: 4000ms
        attempt 3: 8000ms
    """
    return base_ms * (2 ** attempt)
```

### Linear Backoff

Delays grow linearly: `base * attempt`. Simpler but slower to reduce load.

```python
def linear_delay(attempt: int, base_ms: int = 1000) -> int:
    """Calculate linear backoff delay.
    
    Example:
        attempt 0: 1000ms
        attempt 1: 2000ms
        attempt 2: 3000ms
        attempt 3: 4000ms
    """
    return base_ms * (attempt + 1)
```

### Constant Backoff

Fixed delay between retries. Use for predictable systems.

```python
def constant_delay(attempt: int, base_ms: int = 1000) -> int:
    """Fixed delay regardless of attempt."""
    return base_ms
```

## Jitter Strategies

Jitter adds randomness to prevent **thundering herd**—when many clients retry
simultaneously after an outage.

### Full Jitter

Random delay from 0 to calculated backoff. Maximum spread.

```python
import random

def full_jitter(base_delay_ms: int) -> int:
    """Random delay from 0 to base_delay_ms.
    
    Provides maximum spread to prevent thundering herd.
    """
    return random.randint(0, base_delay_ms)
```

### Equal Jitter

Half fixed, half random. Balances predictability and spread.

```python
def equal_jitter(base_delay_ms: int) -> int:
    """Half fixed delay, half random.
    
    Guarantees minimum wait while adding spread.
    """
    half = base_delay_ms // 2
    return half + random.randint(0, half)
```

### Decorrelated Jitter

Each delay is independent, bounded by previous. Good for correlated failures.

```python
def decorrelated_jitter(
    previous_delay_ms: int,
    base_ms: int = 1000,
    max_ms: int = 30000,
) -> int:
    """Decorrelated jitter per AWS recommendations.
    
    delay = min(max_delay, random(base, prev * 3))
    """
    return min(max_ms, random.randint(base_ms, previous_delay_ms * 3))
```

## RetryInterceptor Implementation

Use an interceptor to add retry logic across all stages:

```python
import asyncio
import random
import logging
from enum import Enum
from typing import Any

from stageflow.pipeline.interceptors import BaseInterceptor, ErrorAction
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

logger = logging.getLogger("stageflow.retry")


class BackoffStrategy(Enum):
    """Backoff strategy options."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    CONSTANT = "constant"


class JitterStrategy(Enum):
    """Jitter strategy options."""
    NONE = "none"
    FULL = "full"
    EQUAL = "equal"
    DECORRELATED = "decorrelated"


class RetryInterceptor(BaseInterceptor):
    """Interceptor that automatically retries failed stages.
    
    Configurable backoff and jitter strategies prevent thundering herd
    and gracefully handle transient failures.
    """
    
    name = "retry"
    priority = 15  # Run after circuit breaker, before tracing
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_ms: int = 1000,
        max_delay_ms: int = 30000,
        backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
        jitter_strategy: JitterStrategy = JitterStrategy.FULL,
        retryable_errors: tuple[type[Exception], ...] = (
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    ) -> None:
        """Initialize retry interceptor.
        
        Args:
            max_attempts: Maximum retry attempts (including initial)
            base_delay_ms: Base delay between retries
            max_delay_ms: Maximum delay cap
            backoff_strategy: How delays grow between attempts
            jitter_strategy: Randomization to prevent thundering herd
            retryable_errors: Exception types that trigger retry
        """
        self.max_attempts = max_attempts
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.backoff_strategy = backoff_strategy
        self.jitter_strategy = jitter_strategy
        self.retryable_errors = retryable_errors
        
        # Track delays for decorrelated jitter
        self._previous_delays: dict[str, int] = {}
    
    async def before(
        self, stage_name: str, ctx: PipelineContext
    ) -> None:
        """Initialize retry state before stage execution."""
        # Initialize attempt counter if not present
        if "_retry.attempt" not in ctx.data:
            ctx.data["_retry.attempt"] = 0
            ctx.data["_retry.stage"] = stage_name
    
    async def after(
        self, stage_name: str, result: StageResult, ctx: PipelineContext
    ) -> None:
        """Clean up retry state after successful completion."""
        # Clear retry state on success
        if result.status != "failed":
            ctx.data.pop("_retry.attempt", None)
            ctx.data.pop("_retry.stage", None)
            self._previous_delays.pop(stage_name, None)
    
    async def on_error(
        self, stage_name: str, error: Exception, ctx: PipelineContext
    ) -> ErrorAction:
        """Handle stage errors with configurable retry logic."""
        
        # Check if error is retryable
        if not isinstance(error, self.retryable_errors):
            logger.debug(
                f"Error {type(error).__name__} is not retryable",
                extra={"stage": stage_name, "error": str(error)},
            )
            return ErrorAction.FAIL
        
        # Get current attempt
        attempt = ctx.data.get("_retry.attempt", 0)
        
        # Check if we've exhausted retries
        if attempt >= self.max_attempts - 1:
            logger.warning(
                f"Stage {stage_name} exhausted {self.max_attempts} attempts",
                extra={
                    "stage": stage_name,
                    "attempts": attempt + 1,
                    "error": str(error),
                },
            )
            return ErrorAction.FAIL
        
        # Calculate delay
        delay_ms = self._calculate_delay(stage_name, attempt)
        
        logger.info(
            f"Retrying stage {stage_name} in {delay_ms}ms (attempt {attempt + 2}/{self.max_attempts})",
            extra={
                "stage": stage_name,
                "attempt": attempt + 1,
                "delay_ms": delay_ms,
                "error": str(error),
            },
        )
        
        # Emit retry event
        if hasattr(ctx, "event_sink"):
            ctx.event_sink.try_emit(
                "stage.retry_scheduled",
                {
                    "stage": stage_name,
                    "attempt": attempt + 1,
                    "delay_ms": delay_ms,
                    "error": str(error),
                    "error_type": type(error).__name__,
                },
            )
        
        # Wait before retry
        await asyncio.sleep(delay_ms / 1000.0)
        
        # Increment attempt counter
        ctx.data["_retry.attempt"] = attempt + 1
        
        return ErrorAction.RETRY
    
    def _calculate_delay(self, stage_name: str, attempt: int) -> int:
        """Calculate delay with backoff and jitter."""
        
        # Base delay from backoff strategy
        if self.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            base_delay = self.base_delay_ms * (2 ** attempt)
        elif self.backoff_strategy == BackoffStrategy.LINEAR:
            base_delay = self.base_delay_ms * (attempt + 1)
        else:  # CONSTANT
            base_delay = self.base_delay_ms
        
        # Cap at max delay
        base_delay = min(base_delay, self.max_delay_ms)
        
        # Apply jitter
        if self.jitter_strategy == JitterStrategy.NONE:
            delay = base_delay
        elif self.jitter_strategy == JitterStrategy.FULL:
            delay = random.randint(0, base_delay)
        elif self.jitter_strategy == JitterStrategy.EQUAL:
            half = base_delay // 2
            delay = half + random.randint(0, half)
        else:  # DECORRELATED
            prev = self._previous_delays.get(stage_name, self.base_delay_ms)
            delay = min(self.max_delay_ms, random.randint(self.base_delay_ms, prev * 3))
        
        # Store for decorrelated jitter
        self._previous_delays[stage_name] = delay
        
        return delay
```

## Using RetryInterceptor

### Basic Usage

```python
from stageflow.pipeline.interceptors import get_default_interceptors

# Add retry interceptor to default set
interceptors = get_default_interceptors()
interceptors.append(RetryInterceptor(
    max_attempts=5,
    base_delay_ms=500,
    backoff_strategy=BackoffStrategy.EXPONENTIAL,
    jitter_strategy=JitterStrategy.FULL,
))
```

### Per-Stage Configuration

Override retry settings for specific stages:

```python
class HighReliabilityStage:
    """Stage that needs aggressive retries."""
    
    name = "high_reliability"
    kind = StageKind.WORK
    
    # Stage-specific retry config
    retry_config = {
        "max_attempts": 10,
        "base_delay_ms": 100,
        "backoff_strategy": "exponential",
    }
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Stage implementation
        ...
```

### Custom Retryable Errors

Define which errors trigger retries:

```python
class RateLimitError(Exception):
    """Raised when API rate limit is hit."""
    pass


class ServiceUnavailableError(Exception):
    """Raised when downstream service is unavailable."""
    pass


retry_interceptor = RetryInterceptor(
    retryable_errors=(
        TimeoutError,
        ConnectionError,
        RateLimitError,
        ServiceUnavailableError,
    ),
)
```

## Retry with StageOutput

Stages can signal retry eligibility via `StageOutput.retry()`:

```python
from stageflow.core import StageOutput


class APICallStage:
    """Stage that calls an external API."""
    
    name = "api_call"
    kind = StageKind.WORK
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        try:
            response = await self._call_api(ctx.inputs["request"])
            return StageOutput.ok(response=response)
            
        except RateLimitError as e:
            # Signal that this stage should be retried
            return StageOutput.retry(
                reason=str(e),
                retry_after_ms=e.retry_after * 1000,  # From API response
            )
            
        except ValidationError as e:
            # Don't retry validation errors
            return StageOutput.fail(error=str(e))
```

## Observability

Retry events provide visibility into failure patterns:

| Event | Description | Fields |
|-------|-------------|--------|
| `stage.retry_scheduled` | Retry scheduled after failure | `stage`, `attempt`, `delay_ms`, `error` |
| `stage.retry_succeeded` | Retry attempt succeeded | `stage`, `attempt`, `total_time_ms` |
| `stage.retry_exhausted` | All retries failed | `stage`, `attempts`, `total_time_ms`, `error` |

### Metrics Dashboard

Track retry patterns with these metrics:

```python
# Prometheus-style metrics
retry_attempts_total = Counter(
    "stageflow_retry_attempts_total",
    "Total retry attempts",
    ["stage", "error_type"],
)

retry_success_total = Counter(
    "stageflow_retry_success_total",
    "Successful retries",
    ["stage", "attempt"],
)

retry_delay_histogram = Histogram(
    "stageflow_retry_delay_seconds",
    "Retry delay distribution",
    ["stage"],
)
```

## Best Practices

### 1. Set Reasonable Limits

```python
# Good: bounded retries with max delay cap
RetryInterceptor(
    max_attempts=5,
    base_delay_ms=1000,
    max_delay_ms=30000,  # Never wait more than 30s
)

# Bad: unlimited retries can hang forever
RetryInterceptor(
    max_attempts=100,  # Too many
    max_delay_ms=300000,  # 5 minutes is too long
)
```

### 2. Use Jitter Always

```python
# Good: prevents thundering herd
RetryInterceptor(
    jitter_strategy=JitterStrategy.FULL,
)

# Bad: all clients retry at same time
RetryInterceptor(
    jitter_strategy=JitterStrategy.NONE,
)
```

### 3. Combine with Circuit Breaker

```python
from stageflow.pipeline.interceptors import CircuitBreakerInterceptor

interceptors = [
    CircuitBreakerInterceptor(),  # Fail fast if service is down
    RetryInterceptor(),  # Retry transient errors
]
```

### 4. Log Retry Context

```python
async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext):
    logger.warning(
        f"Stage {stage_name} failed, scheduling retry",
        extra={
            "stage": stage_name,
            "error": str(error),
            "error_type": type(error).__name__,
            "attempt": ctx.data.get("_retry.attempt", 0),
            "pipeline_run_id": str(ctx.pipeline_run_id),
            "request_id": str(ctx.request_id),
        },
    )
```

## Testing Retries

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_retry_on_transient_error():
    """Verify retry occurs on transient errors."""
    
    call_count = 0
    
    async def flaky_operation():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Temporary failure")
        return {"success": True}
    
    stage = AsyncMock()
    stage.execute = flaky_operation
    
    interceptor = RetryInterceptor(max_attempts=5)
    
    # Execute with retry
    result = await run_with_retry(stage, interceptor)
    
    assert result["success"]
    assert call_count == 3  # Failed twice, succeeded on third


@pytest.mark.asyncio
async def test_no_retry_on_client_error():
    """Verify no retry on non-transient errors."""
    
    call_count = 0
    
    async def validation_error():
        nonlocal call_count
        call_count += 1
        raise ValueError("Invalid input")
    
    stage = AsyncMock()
    stage.execute = validation_error
    
    interceptor = RetryInterceptor(max_attempts=5)
    
    with pytest.raises(ValueError):
        await run_with_retry(stage, interceptor)
    
    assert call_count == 1  # No retries


@pytest.mark.asyncio
async def test_exponential_backoff_delays():
    """Verify exponential delay calculation."""
    
    interceptor = RetryInterceptor(
        base_delay_ms=1000,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        jitter_strategy=JitterStrategy.NONE,
    )
    
    delays = [
        interceptor._calculate_delay("test", attempt)
        for attempt in range(5)
    ]
    
    assert delays == [1000, 2000, 4000, 8000, 16000]
```

## Related Guides

- [Idempotency Patterns](./idempotency.md) - Ensure retries don't cause duplicates
- [Saga Pattern](./saga-pattern.md) - Compensate on permanent failures
- [Circuit Breaker](../guides/interceptors.md#circuit-breaker) - Fail fast during outages
