# Routing Loop Detection & Prevention

Routing loops occur when stages create circular dependencies—request A routes to B,
which routes back to A. This guide covers detection strategies, prevention patterns,
and configuration for loop-safe pipelines.

## Loop Types

| Type | Description | Detection |
|------|-------------|-----------|
| **Direct** | Stage routes to itself | Simple counter |
| **Indirect** | A→B→C→A cycle | Path tracking |
| **Semantic** | Similar context re-routed | Hash comparison |
| **Temporal** | Time-delayed loops | Session tracking |

## Loop Detection Strategies

### Direct Loop Detection

Count consecutive visits to the same stage:

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoopDetector:
    """Detect routing loops via visit counting."""
    
    max_iterations: int = 100
    _visit_counts: dict[str, int] = field(default_factory=dict)
    _path: list[str] = field(default_factory=list)
    
    def visit(self, stage_name: str) -> bool:
        """Record a visit to a stage.
        
        Args:
            stage_name: Name of the stage being visited
        
        Returns:
            True if loop detected (should abort)
        """
        self._path.append(stage_name)
        self._visit_counts[stage_name] = self._visit_counts.get(stage_name, 0) + 1
        
        return self._visit_counts[stage_name] > self.max_iterations
    
    def is_loop(self, stage_name: str) -> bool:
        """Check if visiting stage would create a loop."""
        return self._visit_counts.get(stage_name, 0) >= self.max_iterations
    
    def get_path(self) -> list[str]:
        """Get the routing path taken."""
        return self._path.copy()
    
    def reset(self) -> None:
        """Reset detector state for new request."""
        self._visit_counts.clear()
        self._path.clear()


class LoopSafeRouterStage:
    """Router stage with built-in loop detection."""
    
    name = "loop_safe_router"
    kind = StageKind.ROUTE
    max_iterations: int = 100
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get or create loop detector
        detector = ctx.data.get("_loop_detector")
        if detector is None:
            detector = LoopDetector(max_iterations=self.max_iterations)
            ctx.data["_loop_detector"] = detector
        
        # Check for loop
        if detector.is_loop(self.name):
            ctx.event_sink.try_emit(
                "route.loop_detected",
                {
                    "stage": self.name,
                    "iterations": detector._visit_counts.get(self.name, 0),
                    "path": detector.get_path(),
                    "type": "direct",
                },
            )
            return StageOutput.cancel(
                reason=f"Loop detected: {self.name} visited {self.max_iterations} times"
            )
        
        # Record visit
        detector.visit(self.name)
        
        # Compute route
        route = await self._compute_route(ctx)
        
        return StageOutput.ok(
            route=route,
            iterations=detector._visit_counts.get(self.name, 0),
        )
    
    async def _compute_route(self, ctx: StageContext) -> str:
        # Implementation: compute next route
        ...
```

### Indirect Loop Detection

Track full routing path to detect cycles:

```python
from typing import Any


class CycleDetector:
    """Detect indirect routing cycles via path tracking."""
    
    def __init__(self, max_path_length: int = 50) -> None:
        self.max_path_length = max_path_length
        self._path: list[str] = []
    
    def visit(self, stage_name: str) -> tuple[bool, list[str] | None]:
        """Record a visit and check for cycles.
        
        Returns:
            (is_cycle, cycle_path) - cycle_path is None if no cycle
        """
        # Check if stage already in path (cycle)
        if stage_name in self._path:
            cycle_start = self._path.index(stage_name)
            cycle = self._path[cycle_start:] + [stage_name]
            return True, cycle
        
        # Check path length limit
        if len(self._path) >= self.max_path_length:
            return True, self._path + [stage_name]
        
        self._path.append(stage_name)
        return False, None
    
    def get_path(self) -> list[str]:
        return self._path.copy()


class CycleSafeRouterStage:
    """Router with indirect cycle detection."""
    
    name = "cycle_safe_router"
    kind = StageKind.ROUTE
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get or create cycle detector
        detector = ctx.data.get("_cycle_detector")
        if detector is None:
            detector = CycleDetector()
            ctx.data["_cycle_detector"] = detector
        
        # Check for cycle
        is_cycle, cycle_path = detector.visit(self.name)
        
        if is_cycle:
            ctx.event_sink.try_emit(
                "route.cycle_detected",
                {
                    "stage": self.name,
                    "cycle": cycle_path,
                    "type": "indirect",
                },
            )
            return StageOutput.cancel(
                reason=f"Routing cycle detected: {' → '.join(cycle_path)}"
            )
        
        route = await self._compute_route(ctx)
        return StageOutput.ok(route=route)
```

### Semantic Loop Detection

Detect loops where context is similar but not identical:

```python
import hashlib
from typing import Any


class SemanticLoopDetector:
    """Detect loops based on context similarity."""
    
    def __init__(
        self,
        similarity_threshold: float = 0.99,
        max_similar_visits: int = 3,
    ) -> None:
        """Initialize semantic loop detector.
        
        Args:
            similarity_threshold: Hash similarity threshold (0.99 = very similar)
            max_similar_visits: Max visits with similar context
        """
        self.similarity_threshold = similarity_threshold
        self.max_similar_visits = max_similar_visits
        self._context_hashes: list[str] = []
    
    def check(self, context: dict[str, Any]) -> tuple[bool, str]:
        """Check if context is too similar to previous visits.
        
        Returns:
            (is_loop, reason)
        """
        # Compute context hash
        current_hash = self._hash_context(context)
        
        # Count similar hashes
        similar_count = sum(
            1 for h in self._context_hashes
            if self._is_similar(h, current_hash)
        )
        
        # Record this hash
        self._context_hashes.append(current_hash)
        
        if similar_count >= self.max_similar_visits:
            return True, f"Context seen {similar_count + 1} times with >{self.similarity_threshold * 100}% similarity"
        
        return False, ""
    
    def _hash_context(self, context: dict[str, Any]) -> str:
        """Create hash of context for comparison."""
        import json
        
        # Sort keys for consistent hashing
        serialized = json.dumps(context, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()
    
    def _is_similar(self, hash1: str, hash2: str) -> bool:
        """Check if two hashes are similar.
        
        For exact matching, compare directly.
        For fuzzy matching, could use locality-sensitive hashing.
        """
        if self.similarity_threshold >= 0.99:
            return hash1 == hash2
        
        # Simple character similarity for lower thresholds
        matches = sum(c1 == c2 for c1, c2 in zip(hash1, hash2))
        similarity = matches / len(hash1)
        return similarity >= self.similarity_threshold
```

## Loop Prevention Interceptor

Add loop detection to all ROUTE stages:

```python
from stageflow.pipeline.interceptors import BaseInterceptor, InterceptorResult
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult


class LoopPreventionInterceptor(BaseInterceptor):
    """Interceptor that prevents routing loops."""
    
    name = "loop_prevention"
    priority = 12  # Run early, after circuit breaker
    
    def __init__(
        self,
        max_iterations: int = 100,
        max_path_length: int = 50,
        detect_semantic_loops: bool = True,
        semantic_threshold: float = 0.99,
    ) -> None:
        self.max_iterations = max_iterations
        self.max_path_length = max_path_length
        self.detect_semantic = detect_semantic_loops
        self.semantic_threshold = semantic_threshold
    
    async def before(
        self, stage_name: str, ctx: PipelineContext
    ) -> InterceptorResult | None:
        # Only check ROUTE stages
        stage = ctx.data.get("_current_stage")
        if stage and getattr(stage, "kind", None) != StageKind.ROUTE:
            return None
        
        # Get or create detectors
        if "_loop_detector" not in ctx.data:
            ctx.data["_loop_detector"] = LoopDetector(self.max_iterations)
        if "_cycle_detector" not in ctx.data:
            ctx.data["_cycle_detector"] = CycleDetector(self.max_path_length)
        if "_semantic_detector" not in ctx.data and self.detect_semantic:
            ctx.data["_semantic_detector"] = SemanticLoopDetector(
                similarity_threshold=self.semantic_threshold,
            )
        
        loop_detector = ctx.data["_loop_detector"]
        cycle_detector = ctx.data["_cycle_detector"]
        
        # Check direct loop
        if loop_detector.is_loop(stage_name):
            return InterceptorResult(
                stage_ran=False,
                error=f"Direct loop: {stage_name} visited {self.max_iterations}+ times",
            )
        
        # Check indirect cycle
        is_cycle, cycle_path = cycle_detector.visit(stage_name)
        if is_cycle:
            return InterceptorResult(
                stage_ran=False,
                error=f"Indirect cycle: {' → '.join(cycle_path)}",
            )
        
        # Check semantic loop
        if self.detect_semantic:
            semantic_detector = ctx.data["_semantic_detector"]
            # Extract routing-relevant context
            route_context = {
                k: v for k, v in ctx.data.items()
                if not k.startswith("_")
            }
            is_semantic_loop, reason = semantic_detector.check(route_context)
            if is_semantic_loop:
                return InterceptorResult(
                    stage_ran=False,
                    error=f"Semantic loop: {reason}",
                )
        
        # Record visit
        loop_detector.visit(stage_name)
        
        return None
    
    async def after(
        self, stage_name: str, result: StageResult, ctx: PipelineContext
    ) -> None:
        # Emit loop metrics
        if "_loop_detector" in ctx.data:
            detector = ctx.data["_loop_detector"]
            ctx.data.setdefault("_loop_metrics", {})
            ctx.data["_loop_metrics"][stage_name] = detector._visit_counts.get(stage_name, 0)
```

## Configuration Patterns

### Per-Stage Loop Limits

```python
class ConfigurableRouterStage:
    """Router with configurable loop limits."""
    
    name = "configurable_router"
    kind = StageKind.ROUTE
    
    # Stage-specific configuration
    max_iterations: int = 10  # Stricter limit for this stage
    loop_detection_mode: str = "all"  # "direct", "indirect", "semantic", "all"
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Use stage-specific limits
        detector = LoopDetector(max_iterations=self.max_iterations)
        
        if detector.is_loop(self.name):
            return StageOutput.cancel(reason="Loop limit reached")
        
        detector.visit(self.name)
        route = await self._compute_route(ctx)
        
        return StageOutput.ok(route=route)
```

### Pipeline-Level Configuration

```python
from stageflow.pipeline import Pipeline


def build_loop_safe_pipeline() -> Pipeline:
    """Build a pipeline with loop protection."""
    
    return (
        Pipeline("loop_safe")
        .with_interceptor(LoopPreventionInterceptor(
            max_iterations=50,
            max_path_length=20,
            detect_semantic_loops=True,
        ))
        .with_stage(InputRouterStage())
        .with_stage(ProcessingRouterStage())
        .with_stage(OutputRouterStage())
    )
```

## Handling Intentional Loops

Some pipelines legitimately need loops (e.g., guard retry):

```python
class IntentionalLoopStage:
    """Stage that intentionally loops with explicit limit."""
    
    name = "retry_loop"
    kind = StageKind.ROUTE
    
    # Mark as intentional loop
    intentional_loop = True
    loop_limit = 5  # Explicit, tight limit
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        iteration = ctx.data.get("_retry_iteration", 0)
        
        if iteration >= self.loop_limit:
            return StageOutput.fail(
                error=f"Max retries ({self.loop_limit}) exceeded"
            )
        
        # Check if retry needed
        if self._should_retry(ctx):
            ctx.data["_retry_iteration"] = iteration + 1
            return StageOutput.ok(route="retry_target")
        
        return StageOutput.ok(route="success_path")
    
    def _should_retry(self, ctx: StageContext) -> bool:
        # Check if previous stage needs retry
        ...
```

## Observability

| Event | Description | Fields |
|-------|-------------|--------|
| `route.loop_detected` | Direct loop detected | `stage`, `iterations`, `path`, `type` |
| `route.cycle_detected` | Indirect cycle detected | `stage`, `cycle`, `type` |
| `route.semantic_loop` | Similar context loop | `stage`, `similarity`, `visits` |
| `route.loop_prevented` | Loop prevention triggered | `stage`, `reason`, `action` |

## Testing

```python
import pytest
from stageflow.testing import create_test_stage_context


@pytest.mark.asyncio
async def test_direct_loop_detection():
    """Verify direct loops are detected."""
    
    detector = LoopDetector(max_iterations=3)
    
    # First 3 visits OK
    assert not detector.visit("stage_a")
    assert not detector.visit("stage_a")
    assert not detector.visit("stage_a")
    
    # 4th visit triggers loop
    assert detector.visit("stage_a")


@pytest.mark.asyncio
async def test_indirect_cycle_detection():
    """Verify indirect cycles are detected."""
    
    detector = CycleDetector()
    
    # A → B → C is fine
    is_cycle, _ = detector.visit("a")
    assert not is_cycle
    is_cycle, _ = detector.visit("b")
    assert not is_cycle
    is_cycle, _ = detector.visit("c")
    assert not is_cycle
    
    # C → A creates cycle
    is_cycle, cycle = detector.visit("a")
    assert is_cycle
    assert cycle == ["a", "b", "c", "a"]


@pytest.mark.asyncio
async def test_semantic_loop_detection():
    """Verify semantic loops are detected."""
    
    detector = SemanticLoopDetector(
        similarity_threshold=0.99,
        max_similar_visits=2,
    )
    
    context = {"query": "test", "user_id": "123"}
    
    # First 2 visits OK
    is_loop, _ = detector.check(context)
    assert not is_loop
    is_loop, _ = detector.check(context)
    assert not is_loop
    
    # 3rd visit with same context triggers loop
    is_loop, _ = detector.check(context)
    assert is_loop


@pytest.mark.asyncio
async def test_loop_prevention_interceptor():
    """Test loop prevention interceptor."""
    
    ctx = create_test_pipeline_context()
    interceptor = LoopPreventionInterceptor(max_iterations=2)
    
    # First 2 visits pass
    result = await interceptor.before("router", ctx)
    assert result is None
    result = await interceptor.before("router", ctx)
    assert result is None
    
    # 3rd visit blocked
    result = await interceptor.before("router", ctx)
    assert result is not None
    assert "loop" in result.error.lower()
```

## Related Guides

- [A/B Testing](../examples/ab-testing.md) - Traffic routing patterns
- [Routing Confidence](./routing-confidence.md) - Threshold tuning
- [Guard Retry](../examples/agent-tools.md#guard-retry) - Intentional retry loops
