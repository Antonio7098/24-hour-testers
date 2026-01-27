# Saga Pattern for Distributed Transactions

The **Saga pattern** enables long-running, multi-step workflows where each step can be
compensated (rolled back) if a later step fails. Stageflow's stage-based architecture
maps naturally to Sagas: each WORK stage is an operation, and you can define
compensation handlers to reverse side effects.

## When to Use Sagas

| Scenario | Recommendation |
|----------|----------------|
| Multi-service transactions | Use Saga when changes span databases/APIs and cannot use traditional ACID transactions |
| Order fulfillment | Reserve inventory → charge payment → ship → notify. If shipping fails, refund payment and release inventory |
| User onboarding | Create account → provision resources → send welcome email. If provisioning fails, delete account |
| Booking systems | Reserve flight → reserve hotel → reserve car. If any fails, release prior reservations |

**Rule of thumb:** If your workflow has side effects across multiple services and you
need to maintain consistency, use a Saga.

## Saga Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Saga Orchestrator                         │
├──────────────────────────────────────────────────────────────────┤
│  Step 1: Reserve     Step 2: Charge      Step 3: Ship           │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐        │
│  │   Execute   │────▶│   Execute   │────▶│   Execute   │        │
│  └─────────────┘     └─────────────┘     └─────────────┘        │
│        │                   │                   │                 │
│        ▼                   ▼                   ▼                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐        │
│  │ Compensate  │◀────│ Compensate  │◀────│   (failed)  │        │
│  │ (release)   │     │  (refund)   │     │             │        │
│  └─────────────┘     └─────────────┘     └─────────────┘        │
└──────────────────────────────────────────────────────────────────┘
```

## Implementing a Saga

### Step 1: Define Compensatable Stages

Each stage in a Saga should capture enough metadata to reverse its effects:

```python
from dataclasses import dataclass
from typing import Any
from datetime import datetime, timezone

from stageflow.core import StageKind, StageOutput
from stageflow.stages.context import StageContext


@dataclass
class SagaStepResult:
    """Result from a Saga step with compensation data."""
    success: bool
    data: dict[str, Any]
    compensation_data: dict[str, Any] | None = None
    error: str | None = None


class ReserveInventoryStage:
    """Reserve inventory for an order."""
    
    name = "reserve_inventory"
    kind = StageKind.WORK
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        order_id = ctx.inputs["order_id"]
        items = ctx.inputs["items"]
        
        # Perform reservation
        reservation_ids = await self._reserve_items(items)
        
        # Store compensation data for potential rollback
        return StageOutput.ok(
            reservation_ids=reservation_ids,
            order_id=order_id,
            _saga_compensation={
                "action": "release_inventory",
                "reservation_ids": reservation_ids,
                "reserved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    
    async def _reserve_items(self, items: list[dict]) -> list[str]:
        # Implementation: call inventory service
        ...


class ChargePaymentStage:
    """Charge customer payment."""
    
    name = "charge_payment"
    kind = StageKind.WORK
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        order_id = ctx.inputs["order_id"]
        amount = ctx.inputs["amount"]
        payment_method = ctx.inputs["payment_method"]
        
        # Charge payment
        charge_id = await self._charge(amount, payment_method)
        
        return StageOutput.ok(
            charge_id=charge_id,
            amount=amount,
            _saga_compensation={
                "action": "refund_payment",
                "charge_id": charge_id,
                "amount": amount,
                "charged_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    
    async def _charge(self, amount: int, method: dict) -> str:
        # Implementation: call payment service
        ...
```

### Step 2: Create a Saga State Machine

Track execution state and compensation order:

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
import logging

logger = logging.getLogger("stageflow.saga")


class SagaState(Enum):
    """Saga execution state."""
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    COMPENSATING = auto()
    COMPENSATED = auto()
    FAILED = auto()


@dataclass
class SagaStep:
    """A single step in a Saga."""
    name: str
    stage: Any  # Stage instance
    compensation_data: dict[str, Any] | None = None
    executed: bool = False
    compensated: bool = False


@dataclass
class SagaStateMachine:
    """Orchestrates Saga execution and compensation.
    
    Compensation is always executed in reverse order to maintain
    consistency (LIFO - Last In, First Out).
    """
    
    saga_id: str
    steps: list[SagaStep] = field(default_factory=list)
    state: SagaState = SagaState.PENDING
    current_step: int = 0
    error: str | None = None
    
    def add_step(self, name: str, stage: Any) -> None:
        """Add a step to the Saga."""
        self.steps.append(SagaStep(name=name, stage=stage))
    
    async def execute(self, ctx: Any) -> dict[str, Any]:
        """Execute all Saga steps.
        
        If any step fails, automatically triggers compensation
        for all previously completed steps in reverse order.
        """
        self.state = SagaState.RUNNING
        results: dict[str, Any] = {}
        
        for i, step in enumerate(self.steps):
            self.current_step = i
            
            try:
                logger.info(
                    f"Saga {self.saga_id}: executing step {step.name}",
                    extra={"saga_id": self.saga_id, "step": step.name, "index": i},
                )
                
                result = await step.stage.execute(ctx)
                
                if result.status == "failed":
                    self.error = result.error
                    await self._compensate(ctx)
                    return {"success": False, "error": self.error, "results": results}
                
                # Store compensation data from result
                step.compensation_data = result.data.get("_saga_compensation")
                step.executed = True
                results[step.name] = result.data
                
                # Update context for next step
                ctx.data.update(result.data)
                
            except Exception as e:
                logger.error(
                    f"Saga {self.saga_id}: step {step.name} failed: {e}",
                    extra={"saga_id": self.saga_id, "step": step.name, "error": str(e)},
                )
                self.error = str(e)
                await self._compensate(ctx)
                return {"success": False, "error": self.error, "results": results}
        
        self.state = SagaState.COMPLETED
        logger.info(
            f"Saga {self.saga_id}: completed successfully",
            extra={"saga_id": self.saga_id, "steps_executed": len(self.steps)},
        )
        return {"success": True, "results": results}
    
    async def _compensate(self, ctx: Any) -> None:
        """Compensate all executed steps in reverse order."""
        self.state = SagaState.COMPENSATING
        
        # Reverse order: last executed step compensates first
        for step in reversed(self.steps[:self.current_step + 1]):
            if not step.executed or step.compensated:
                continue
            
            if step.compensation_data is None:
                logger.warning(
                    f"Saga {self.saga_id}: no compensation data for {step.name}",
                    extra={"saga_id": self.saga_id, "step": step.name},
                )
                continue
            
            try:
                logger.info(
                    f"Saga {self.saga_id}: compensating step {step.name}",
                    extra={
                        "saga_id": self.saga_id,
                        "step": step.name,
                        "compensation": step.compensation_data,
                    },
                )
                
                await self._execute_compensation(step.compensation_data, ctx)
                step.compensated = True
                
                # Emit compensation event
                if hasattr(ctx, "event_sink"):
                    ctx.event_sink.try_emit(
                        "saga.step_compensated",
                        {
                            "saga_id": self.saga_id,
                            "step": step.name,
                            "compensation": step.compensation_data,
                        },
                    )
                
            except Exception as e:
                logger.error(
                    f"Saga {self.saga_id}: compensation failed for {step.name}: {e}",
                    extra={
                        "saga_id": self.saga_id,
                        "step": step.name,
                        "error": str(e),
                    },
                )
                # Continue compensating other steps even if one fails
        
        self.state = SagaState.COMPENSATED
    
    async def _execute_compensation(
        self, compensation_data: dict[str, Any], ctx: Any
    ) -> None:
        """Execute a compensation action.
        
        Override this method to dispatch to actual compensation handlers.
        """
        action = compensation_data.get("action")
        
        # Dispatch to compensation handler based on action type
        handlers = {
            "release_inventory": self._compensate_inventory,
            "refund_payment": self._compensate_payment,
            # Add more handlers as needed
        }
        
        handler = handlers.get(action)
        if handler:
            await handler(compensation_data, ctx)
        else:
            logger.warning(f"No handler for compensation action: {action}")
    
    async def _compensate_inventory(
        self, data: dict[str, Any], ctx: Any
    ) -> None:
        """Release reserved inventory."""
        # Implementation: call inventory service to release
        ...
    
    async def _compensate_payment(
        self, data: dict[str, Any], ctx: Any
    ) -> None:
        """Refund a payment."""
        # Implementation: call payment service to refund
        ...
```

### Step 3: Use the Saga in a Pipeline

```python
from uuid import uuid4


async def process_order(ctx: PipelineContext, order: dict) -> dict:
    """Process an order using the Saga pattern."""
    
    saga = SagaStateMachine(saga_id=str(uuid4()))
    
    # Add steps in execution order
    saga.add_step("reserve_inventory", ReserveInventoryStage())
    saga.add_step("charge_payment", ChargePaymentStage())
    saga.add_step("ship_order", ShipOrderStage())
    saga.add_step("send_confirmation", SendConfirmationStage())
    
    # Prepare context with order data
    ctx.data.update({
        "order_id": order["id"],
        "items": order["items"],
        "amount": order["total_cents"],
        "payment_method": order["payment_method"],
        "shipping_address": order["shipping_address"],
    })
    
    # Execute the Saga
    result = await saga.execute(ctx)
    
    if not result["success"]:
        # Saga failed and compensated
        ctx.event_sink.try_emit(
            "order.processing_failed",
            {
                "order_id": order["id"],
                "error": result["error"],
                "saga_id": saga.saga_id,
            },
        )
    
    return result
```

## Observability

The Saga pattern integrates with Stageflow's event system:

| Event | Description |
|-------|-------------|
| `saga.step_started` | Step execution began |
| `saga.step_completed` | Step completed successfully |
| `saga.step_failed` | Step execution failed |
| `saga.step_compensated` | Step was compensated |
| `saga.completed` | Entire Saga completed |
| `saga.compensation_failed` | Compensation failed (requires manual intervention) |

## Best Practices

### 1. Idempotent Compensation

Compensation handlers should be idempotent—safe to retry if they fail:

```python
async def compensate_refund(data: dict, ctx: Any) -> None:
    charge_id = data["charge_id"]
    
    # Check if already refunded (idempotent)
    existing_refund = await payment_service.get_refund(charge_id)
    if existing_refund:
        logger.info(f"Refund already exists for {charge_id}")
        return
    
    await payment_service.refund(charge_id, data["amount"])
```

### 2. Store Sufficient Context

Compensation data should include everything needed to reverse the action:

```python
# Good: includes all context needed for compensation
compensation_data = {
    "action": "release_inventory",
    "reservation_ids": ["res_123", "res_456"],
    "warehouse_id": "wh_001",
    "reserved_at": "2024-01-23T12:00:00Z",
}

# Bad: missing context for compensation
compensation_data = {
    "action": "release_inventory",
    "order_id": "ord_789",  # Need to look up reservation IDs
}
```

### 3. Handle Partial Compensation Failures

Log and alert when compensation fails, as manual intervention may be needed:

```python
async def _compensate(self, ctx: Any) -> None:
    failed_compensations = []
    
    for step in reversed(executed_steps):
        try:
            await self._execute_compensation(step.compensation_data, ctx)
        except Exception as e:
            failed_compensations.append({
                "step": step.name,
                "error": str(e),
                "compensation_data": step.compensation_data,
            })
    
    if failed_compensations:
        # Emit alert for manual intervention
        ctx.event_sink.try_emit(
            "saga.compensation_failed",
            {
                "saga_id": self.saga_id,
                "failed_steps": failed_compensations,
                "requires_manual_intervention": True,
            },
        )
```

### 4. Set Timeouts

Use timeouts to prevent Sagas from hanging:

```python
import asyncio

async def execute_with_timeout(self, ctx: Any, timeout_seconds: int = 300) -> dict:
    """Execute Saga with overall timeout."""
    try:
        return await asyncio.wait_for(
            self.execute(ctx),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        self.error = f"Saga timed out after {timeout_seconds}s"
        await self._compensate(ctx)
        return {"success": False, "error": self.error}
```

## Testing Sagas

```python
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_saga_compensates_on_failure():
    """Verify compensation runs in reverse order on failure."""
    
    # Create mock stages
    step1 = AsyncMock()
    step1.execute.return_value = StageOutput.ok(
        _saga_compensation={"action": "undo_step1"}
    )
    
    step2 = AsyncMock()
    step2.execute.return_value = StageOutput.ok(
        _saga_compensation={"action": "undo_step2"}
    )
    
    step3 = AsyncMock()
    step3.execute.return_value = StageOutput.fail("Step 3 failed")
    
    # Build Saga
    saga = SagaStateMachine(saga_id="test-saga")
    saga.add_step("step1", step1)
    saga.add_step("step2", step2)
    saga.add_step("step3", step3)
    
    # Mock compensation handlers
    compensations_called = []
    saga._execute_compensation = AsyncMock(
        side_effect=lambda data, ctx: compensations_called.append(data["action"])
    )
    
    # Execute
    ctx = create_test_pipeline_context()
    result = await saga.execute(ctx)
    
    # Verify failure
    assert not result["success"]
    assert saga.state == SagaState.COMPENSATED
    
    # Verify compensation order (reverse)
    assert compensations_called == ["undo_step2", "undo_step1"]


@pytest.mark.asyncio
async def test_saga_completes_without_compensation():
    """Verify successful Saga doesn't trigger compensation."""
    
    saga = SagaStateMachine(saga_id="test-saga")
    
    for i in range(3):
        step = AsyncMock()
        step.execute.return_value = StageOutput.ok(value=i)
        saga.add_step(f"step{i}", step)
    
    ctx = create_test_pipeline_context()
    result = await saga.execute(ctx)
    
    assert result["success"]
    assert saga.state == SagaState.COMPLETED
```

## Related Guides

- [Idempotency Patterns](./idempotency.md) - Ensure Saga steps are safe to retry
- [Retry & Backoff](./retry-backoff.md) - Configure retry behavior for transient failures
- [Checkpointing](./checkpointing.md) - Persist Saga state for crash recovery
