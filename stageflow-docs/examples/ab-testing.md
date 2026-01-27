# A/B Testing Patterns

A/B testing enables controlled experiments in production pipelines—testing new models,
prompts, or processing strategies. This guide covers traffic splitting, consistent
bucketing, and experiment tracking in Stageflow.

## Architecture Overview

```
                    ┌─────────────────┐
                    │   User Request  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Traffic Router │
                    │   (ROUTE stage) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
      ┌───────▼───────┐ ┌───▼───┐ ┌───────▼───────┐
      │  Variant A    │ │Control│ │  Variant B    │
      │  (50% traffic)│ │ (10%) │ │  (40% traffic)│
      └───────┬───────┘ └───┬───┘ └───────┬───────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │ Experiment      │
                    │ Tracker         │
                    └─────────────────┘
```

## Consistent Bucketing

Ensure users always see the same variant using hash-based assignment:

```python
import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass
class ExperimentConfig:
    """Configuration for an A/B experiment."""
    
    experiment_id: str
    variants: dict[str, float]  # variant_name -> traffic_percentage
    salt: str = ""  # Additional entropy for bucketing
    
    def __post_init__(self) -> None:
        # Validate percentages sum to 100
        total = sum(self.variants.values())
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Variant percentages must sum to 100, got {total}")


class ConsistentBucketer:
    """Assign users to variants consistently using hash bucketing."""
    
    def __init__(self, config: ExperimentConfig) -> None:
        self.config = config
        self._boundaries = self._compute_boundaries()
    
    def _compute_boundaries(self) -> list[tuple[str, float]]:
        """Compute bucket boundaries from percentages."""
        boundaries = []
        cumulative = 0.0
        
        for variant, percentage in self.config.variants.items():
            cumulative += percentage
            boundaries.append((variant, cumulative))
        
        return boundaries
    
    def assign(self, user_id: str) -> str:
        """Assign a user to a variant.
        
        Uses SHA-256 hash of (experiment_id, salt, user_id) to generate
        a deterministic bucket value in [0, 100).
        
        Args:
            user_id: Unique user identifier
        
        Returns:
            Variant name the user is assigned to
        """
        # Create deterministic hash
        hash_input = f"{self.config.experiment_id}:{self.config.salt}:{user_id}"
        hash_bytes = hashlib.sha256(hash_input.encode()).digest()
        
        # Convert first 8 bytes to bucket value [0, 100)
        hash_int = int.from_bytes(hash_bytes[:8], byteorder="big")
        bucket = (hash_int % 10000) / 100.0  # 0.00 to 99.99
        
        # Find variant for this bucket
        for variant, boundary in self._boundaries:
            if bucket < boundary:
                return variant
        
        # Fallback to last variant (should never happen)
        return self._boundaries[-1][0]
    
    def get_assignment_reason(self, user_id: str) -> dict[str, Any]:
        """Get detailed assignment info for debugging."""
        hash_input = f"{self.config.experiment_id}:{self.config.salt}:{user_id}"
        hash_bytes = hashlib.sha256(hash_input.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:8], byteorder="big")
        bucket = (hash_int % 10000) / 100.0
        
        return {
            "user_id": user_id,
            "experiment_id": self.config.experiment_id,
            "bucket": bucket,
            "variant": self.assign(user_id),
            "boundaries": self._boundaries,
        }
```

## A/B Test Router Stage

```python
from stageflow.core import StageKind, StageOutput
from stageflow.stages.context import StageContext


class ABTestRouterStage:
    """Route requests to experiment variants."""
    
    name = "ab_test_router"
    kind = StageKind.ROUTE
    
    def __init__(
        self,
        experiment: ExperimentConfig,
        user_id_extractor: callable | None = None,
    ) -> None:
        self.bucketer = ConsistentBucketer(experiment)
        self.experiment = experiment
        self.user_id_extractor = user_id_extractor or self._default_user_id
    
    def _default_user_id(self, ctx: StageContext) -> str:
        """Extract user ID from context."""
        return str(ctx.snapshot.run_id.user_id or ctx.snapshot.run_id.session_id)
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Extract user ID for bucketing
        user_id = self.user_id_extractor(ctx)
        
        # Assign variant
        variant = self.bucketer.assign(user_id)
        
        # Emit experiment assignment event
        ctx.event_sink.try_emit(
            "experiment.assignment",
            {
                "experiment_id": self.experiment.experiment_id,
                "variant": variant,
                "user_id": user_id,
            },
        )
        
        return StageOutput.ok(
            route=variant,
            experiment_id=self.experiment.experiment_id,
            variant=variant,
            confidence=1.0,  # Deterministic assignment
        )
```

## Building Experiment Pipelines

```python
from stageflow.pipeline import Pipeline


def build_llm_experiment_pipeline() -> Pipeline:
    """Pipeline with A/B test for different LLM models."""
    
    experiment = ExperimentConfig(
        experiment_id="llm_model_comparison_v1",
        variants={
            "gpt4": 50.0,
            "claude": 40.0,
            "control": 10.0,
        },
        salt="2024-01-23",
    )
    
    return (
        Pipeline("llm_experiment")
        # Route based on experiment
        .with_stage(ABTestRouterStage(experiment))
        
        # Variant A: GPT-4
        .with_stage(
            GPT4GenerationStage(),
            name="gpt4_generation",
            depends_on=["ab_test_router"],
            when=lambda ctx: ctx.data.get("variant") == "gpt4",
        )
        
        # Variant B: Claude
        .with_stage(
            ClaudeGenerationStage(),
            name="claude_generation",
            depends_on=["ab_test_router"],
            when=lambda ctx: ctx.data.get("variant") == "claude",
        )
        
        # Control: existing model
        .with_stage(
            LegacyGenerationStage(),
            name="control_generation",
            depends_on=["ab_test_router"],
            when=lambda ctx: ctx.data.get("variant") == "control",
        )
        
        # Merge results
        .with_stage(
            ExperimentResultCollectorStage(),
            depends_on=["gpt4_generation", "claude_generation", "control_generation"],
        )
    )
```

## Experiment Tracking

Track metrics per variant:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import statistics


@dataclass
class VariantMetrics:
    """Metrics collected for a single variant."""
    
    variant: str
    impressions: int = 0
    conversions: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    custom_metrics: dict[str, list[float]] = field(default_factory=dict)
    
    @property
    def conversion_rate(self) -> float:
        return self.conversions / self.impressions if self.impressions > 0 else 0.0
    
    @property
    def error_rate(self) -> float:
        return self.errors / self.impressions if self.impressions > 0 else 0.0
    
    @property
    def p50_latency(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0
    
    @property
    def p95_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx]


class ExperimentTracker:
    """Track experiment metrics and compute statistical significance."""
    
    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id
        self.variants: dict[str, VariantMetrics] = {}
        self.started_at = datetime.now(timezone.utc)
    
    def record_impression(
        self,
        variant: str,
        latency_ms: float | None = None,
        converted: bool = False,
        error: bool = False,
        custom_metrics: dict[str, float] | None = None,
    ) -> None:
        """Record an impression for a variant."""
        if variant not in self.variants:
            self.variants[variant] = VariantMetrics(variant=variant)
        
        metrics = self.variants[variant]
        metrics.impressions += 1
        
        if latency_ms is not None:
            metrics.latencies_ms.append(latency_ms)
        
        if converted:
            metrics.conversions += 1
        
        if error:
            metrics.errors += 1
        
        if custom_metrics:
            for key, value in custom_metrics.items():
                if key not in metrics.custom_metrics:
                    metrics.custom_metrics[key] = []
                metrics.custom_metrics[key].append(value)
    
    def get_summary(self) -> dict[str, Any]:
        """Get experiment summary with statistical analysis."""
        summary = {
            "experiment_id": self.experiment_id,
            "started_at": self.started_at.isoformat(),
            "duration_hours": (datetime.now(timezone.utc) - self.started_at).total_seconds() / 3600,
            "total_impressions": sum(v.impressions for v in self.variants.values()),
            "variants": {},
        }
        
        for name, metrics in self.variants.items():
            summary["variants"][name] = {
                "impressions": metrics.impressions,
                "conversion_rate": metrics.conversion_rate,
                "error_rate": metrics.error_rate,
                "p50_latency_ms": metrics.p50_latency,
                "p95_latency_ms": metrics.p95_latency,
            }
        
        # Compute statistical significance if we have control
        if "control" in self.variants and len(self.variants) > 1:
            control = self.variants["control"]
            for name, metrics in self.variants.items():
                if name != "control":
                    summary["variants"][name]["vs_control"] = {
                        "conversion_lift": (
                            (metrics.conversion_rate - control.conversion_rate)
                            / control.conversion_rate * 100
                            if control.conversion_rate > 0 else 0
                        ),
                        "significant": self._is_significant(control, metrics),
                    }
        
        return summary
    
    def _is_significant(
        self,
        control: VariantMetrics,
        treatment: VariantMetrics,
        confidence: float = 0.95,
    ) -> bool:
        """Check if difference is statistically significant using z-test."""
        import math
        
        n1, n2 = control.impressions, treatment.impressions
        if n1 < 100 or n2 < 100:
            return False  # Not enough samples
        
        p1, p2 = control.conversion_rate, treatment.conversion_rate
        p_pool = (control.conversions + treatment.conversions) / (n1 + n2)
        
        if p_pool == 0 or p_pool == 1:
            return False
        
        se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
        if se == 0:
            return False
        
        z = abs(p1 - p2) / se
        
        # z > 1.96 for 95% confidence
        z_threshold = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}.get(confidence, 1.96)
        return z > z_threshold
```

## Experiment Result Stage

```python
class ExperimentResultCollectorStage:
    """Collect and track experiment results."""
    
    name = "experiment_collector"
    kind = StageKind.WORK
    
    def __init__(self, tracker: ExperimentTracker | None = None) -> None:
        self.tracker = tracker
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        import time
        
        # Get experiment metadata from routing stage
        experiment_id = ctx.inputs.get("experiment_id")
        variant = ctx.inputs.get("variant")
        
        if not experiment_id or not variant:
            return StageOutput.ok(tracked=False)
        
        # Get result from variant stage
        result_key = f"{variant}_generation"
        generation_result = ctx.inputs.get(result_key, {})
        
        # Compute metrics
        latency_ms = generation_result.get("latency_ms")
        success = generation_result.get("success", False)
        
        # Track if we have a tracker
        if self.tracker:
            self.tracker.record_impression(
                variant=variant,
                latency_ms=latency_ms,
                converted=success,
                error=not success,
            )
        
        # Emit tracking event
        ctx.event_sink.try_emit(
            "experiment.result",
            {
                "experiment_id": experiment_id,
                "variant": variant,
                "success": success,
                "latency_ms": latency_ms,
            },
        )
        
        return StageOutput.ok(
            tracked=True,
            experiment_id=experiment_id,
            variant=variant,
        )
```

## Multi-Armed Bandit

For adaptive traffic allocation:

```python
import random
import math


class ThompsonSamplingBucketer:
    """Adaptive bucketing using Thompson Sampling."""
    
    def __init__(self, variants: list[str]) -> None:
        self.variants = variants
        # Beta distribution parameters (successes, failures)
        self.alpha = {v: 1.0 for v in variants}  # Prior successes
        self.beta = {v: 1.0 for v in variants}   # Prior failures
    
    def assign(self, user_id: str | None = None) -> str:
        """Assign variant using Thompson Sampling.
        
        Note: This is NOT consistent - same user may get different
        variants on different requests. Use for exploration.
        """
        # Sample from beta distribution for each variant
        samples = {
            v: random.betavariate(self.alpha[v], self.beta[v])
            for v in self.variants
        }
        
        # Return variant with highest sample
        return max(samples, key=samples.get)
    
    def update(self, variant: str, success: bool) -> None:
        """Update beliefs based on observed outcome."""
        if success:
            self.alpha[variant] += 1
        else:
            self.beta[variant] += 1
    
    def get_expected_values(self) -> dict[str, float]:
        """Get expected value (mean) for each variant."""
        return {
            v: self.alpha[v] / (self.alpha[v] + self.beta[v])
            for v in self.variants
        }
```

## Testing

```python
import pytest


def test_consistent_bucketing():
    """Verify same user always gets same variant."""
    config = ExperimentConfig(
        experiment_id="test_exp",
        variants={"a": 50, "b": 50},
    )
    bucketer = ConsistentBucketer(config)
    
    user_id = "user_123"
    
    # Multiple calls should return same variant
    assignments = [bucketer.assign(user_id) for _ in range(100)]
    assert len(set(assignments)) == 1


def test_traffic_distribution():
    """Verify traffic split matches configuration."""
    config = ExperimentConfig(
        experiment_id="test_exp",
        variants={"a": 70, "b": 30},
    )
    bucketer = ConsistentBucketer(config)
    
    # Assign many users
    assignments = [bucketer.assign(f"user_{i}") for i in range(10000)]
    
    a_count = assignments.count("a")
    b_count = assignments.count("b")
    
    # Should be within 5% of target
    assert 0.65 < a_count / 10000 < 0.75
    assert 0.25 < b_count / 10000 < 0.35


def test_statistical_significance():
    """Test significance calculation."""
    tracker = ExperimentTracker("test")
    
    # Simulate clear winner
    for _ in range(1000):
        tracker.record_impression("control", converted=random.random() < 0.10)
        tracker.record_impression("treatment", converted=random.random() < 0.15)
    
    summary = tracker.get_summary()
    
    # Treatment should show significant lift
    assert summary["variants"]["treatment"]["vs_control"]["significant"]
```

## Observability

| Event | Description | Fields |
|-------|-------------|--------|
| `experiment.assignment` | User assigned to variant | `experiment_id`, `variant`, `user_id` |
| `experiment.result` | Experiment outcome recorded | `experiment_id`, `variant`, `success`, `latency_ms` |
| `experiment.summary` | Periodic experiment summary | `experiment_id`, `variants`, `significant_results` |

## Related Guides

- [Routing Confidence](../advanced/routing-confidence.md) - Threshold tuning
- [Loop Detection](../advanced/routing-loops.md) - Prevent routing loops
- [Observability](./observability.md) - Experiment metrics
