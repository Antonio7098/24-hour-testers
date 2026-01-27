# Routing Confidence & Threshold Tuning

Confidence-based routing directs requests based on model certainty. This guide covers
threshold calibration, drift detection, and production tuning patterns.

## Confidence Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Input     │────▶│  Classifier │────▶│  Confidence │
│             │     │   Model     │     │   Score     │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                           ┌───────────────────┼───────────────────┐
                           │                   │                   │
                    ┌──────▼──────┐     ┌──────▼──────┐     ┌──────▼──────┐
                    │  High Conf  │     │  Medium     │     │  Low Conf   │
                    │  (>0.9)     │     │  (0.5-0.9)  │     │  (<0.5)     │
                    │  Auto-route │     │  Review     │     │  Escalate   │
                    └─────────────┘     └─────────────┘     └─────────────┘
```

## Threshold Configuration

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class ConfidenceThresholds:
    """Thresholds for confidence-based routing."""
    
    high_confidence: float = 0.9   # Auto-process
    medium_confidence: float = 0.5  # Review queue
    # Below medium = escalate
    
    def get_route(self, confidence: float) -> str:
        """Determine route based on confidence."""
        if confidence >= self.high_confidence:
            return "auto_process"
        elif confidence >= self.medium_confidence:
            return "review_queue"
        else:
            return "escalate"
    
    def validate(self) -> None:
        """Validate threshold configuration."""
        if not (0 <= self.medium_confidence <= self.high_confidence <= 1):
            raise ValueError(
                f"Invalid thresholds: medium={self.medium_confidence}, "
                f"high={self.high_confidence}. Must be 0 <= medium <= high <= 1"
            )


class ConfidenceRouterStage:
    """Route requests based on classifier confidence."""
    
    name = "confidence_router"
    kind = StageKind.ROUTE
    
    def __init__(
        self,
        thresholds: ConfidenceThresholds | None = None,
        classifier: Any = None,
    ) -> None:
        self.thresholds = thresholds or ConfidenceThresholds()
        self.thresholds.validate()
        self.classifier = classifier
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get classification result
        content = ctx.inputs.get("content", "")
        
        if self.classifier:
            result = await self.classifier.classify(content)
            confidence = result.confidence
            label = result.label
        else:
            confidence = ctx.inputs.get("confidence", 0.5)
            label = ctx.inputs.get("label", "unknown")
        
        # Determine route
        route = self.thresholds.get_route(confidence)
        
        # Emit routing decision
        ctx.event_sink.try_emit(
            "route.confidence_decision",
            {
                "confidence": confidence,
                "label": label,
                "route": route,
                "thresholds": {
                    "high": self.thresholds.high_confidence,
                    "medium": self.thresholds.medium_confidence,
                },
            },
        )
        
        return StageOutput.ok(
            route=route,
            confidence=confidence,
            label=label,
        )
```

## Threshold Calibration

### Calibration from Historical Data

```python
import statistics
from dataclasses import dataclass
from typing import Any


@dataclass
class CalibrationResult:
    """Result of threshold calibration."""
    
    recommended_high: float
    recommended_medium: float
    precision_at_high: float
    recall_at_high: float
    samples_analyzed: int
    
    def to_thresholds(self) -> ConfidenceThresholds:
        return ConfidenceThresholds(
            high_confidence=self.recommended_high,
            medium_confidence=self.recommended_medium,
        )


class ThresholdCalibrator:
    """Calibrate thresholds from historical routing decisions."""
    
    def __init__(
        self,
        target_precision: float = 0.95,
        target_auto_rate: float = 0.70,
    ) -> None:
        """Initialize calibrator.
        
        Args:
            target_precision: Target precision for auto-processing
            target_auto_rate: Target percentage to auto-process
        """
        self.target_precision = target_precision
        self.target_auto_rate = target_auto_rate
    
    def calibrate(
        self,
        predictions: list[dict[str, Any]],
    ) -> CalibrationResult:
        """Calibrate thresholds from prediction history.
        
        Args:
            predictions: List of {"confidence": float, "was_correct": bool}
        
        Returns:
            Calibration result with recommended thresholds
        """
        if not predictions:
            return CalibrationResult(
                recommended_high=0.9,
                recommended_medium=0.5,
                precision_at_high=0.0,
                recall_at_high=0.0,
                samples_analyzed=0,
            )
        
        # Sort by confidence descending
        sorted_preds = sorted(
            predictions,
            key=lambda p: p["confidence"],
            reverse=True,
        )
        
        # Find threshold that achieves target precision
        high_threshold = self._find_precision_threshold(
            sorted_preds,
            self.target_precision,
        )
        
        # Find medium threshold based on auto-rate
        medium_threshold = self._find_rate_threshold(
            sorted_preds,
            self.target_auto_rate,
        )
        
        # Ensure medium <= high
        medium_threshold = min(medium_threshold, high_threshold - 0.05)
        
        # Calculate metrics at high threshold
        high_preds = [p for p in sorted_preds if p["confidence"] >= high_threshold]
        if high_preds:
            precision = sum(p["was_correct"] for p in high_preds) / len(high_preds)
            total_correct = sum(p["was_correct"] for p in sorted_preds)
            recall = sum(p["was_correct"] for p in high_preds) / total_correct if total_correct else 0
        else:
            precision = recall = 0.0
        
        return CalibrationResult(
            recommended_high=high_threshold,
            recommended_medium=medium_threshold,
            precision_at_high=precision,
            recall_at_high=recall,
            samples_analyzed=len(predictions),
        )
    
    def _find_precision_threshold(
        self,
        sorted_preds: list[dict],
        target: float,
    ) -> float:
        """Find lowest threshold achieving target precision."""
        for i in range(len(sorted_preds)):
            subset = sorted_preds[:i + 1]
            precision = sum(p["was_correct"] for p in subset) / len(subset)
            
            if precision < target:
                # Previous threshold was better
                if i > 0:
                    return sorted_preds[i - 1]["confidence"]
                return sorted_preds[0]["confidence"]
        
        return sorted_preds[-1]["confidence"]
    
    def _find_rate_threshold(
        self,
        sorted_preds: list[dict],
        target_rate: float,
    ) -> float:
        """Find threshold that auto-processes target percentage."""
        target_count = int(len(sorted_preds) * target_rate)
        if target_count == 0:
            return 1.0
        if target_count >= len(sorted_preds):
            return 0.0
        
        return sorted_preds[target_count - 1]["confidence"]
```

## Calibration Drift Detection

Monitor for threshold degradation over time:

```python
from datetime import datetime, timezone, timedelta
from collections import deque
from typing import Any
import statistics


class CalibrationDriftDetector:
    """Detect when confidence calibration has drifted."""
    
    def __init__(
        self,
        window_size: int = 1000,
        drift_threshold: float = 0.05,
        check_interval: int = 100,
    ) -> None:
        """Initialize drift detector.
        
        Args:
            window_size: Number of predictions to track
            drift_threshold: Precision drop that triggers alert
            check_interval: Check drift every N predictions
        """
        self.window_size = window_size
        self.drift_threshold = drift_threshold
        self.check_interval = check_interval
        
        self._predictions: deque = deque(maxlen=window_size)
        self._baseline_precision: float | None = None
        self._check_counter = 0
    
    def record(
        self,
        confidence: float,
        was_correct: bool,
        threshold_used: float,
    ) -> dict[str, Any] | None:
        """Record a prediction and check for drift.
        
        Returns:
            Drift alert dict if drift detected, None otherwise
        """
        self._predictions.append({
            "confidence": confidence,
            "was_correct": was_correct,
            "threshold": threshold_used,
            "timestamp": datetime.now(timezone.utc),
        })
        
        self._check_counter += 1
        
        # Periodically check for drift
        if self._check_counter >= self.check_interval:
            self._check_counter = 0
            return self._check_drift()
        
        return None
    
    def _check_drift(self) -> dict[str, Any] | None:
        """Check if calibration has drifted."""
        if len(self._predictions) < self.window_size // 2:
            return None  # Not enough data
        
        # Calculate current precision for high-confidence predictions
        high_conf_preds = [
            p for p in self._predictions
            if p["confidence"] >= p["threshold"]
        ]
        
        if not high_conf_preds:
            return None
        
        current_precision = (
            sum(p["was_correct"] for p in high_conf_preds)
            / len(high_conf_preds)
        )
        
        # Set baseline on first check
        if self._baseline_precision is None:
            self._baseline_precision = current_precision
            return None
        
        # Check for drift
        drift = self._baseline_precision - current_precision
        
        if drift > self.drift_threshold:
            return {
                "type": "calibration_drift",
                "baseline_precision": self._baseline_precision,
                "current_precision": current_precision,
                "drift": drift,
                "samples": len(high_conf_preds),
                "recommendation": "recalibrate_thresholds",
            }
        
        return None
    
    def reset_baseline(self) -> None:
        """Reset baseline precision (after recalibration)."""
        self._baseline_precision = None
```

## Production Tuning

### Staged Rollout

```python
class StagedConfidenceRouter:
    """Router with staged threshold rollout."""
    
    name = "staged_router"
    kind = StageKind.ROUTE
    
    def __init__(
        self,
        current_thresholds: ConfidenceThresholds,
        new_thresholds: ConfidenceThresholds,
        rollout_percentage: float = 0.0,  # 0-100
    ) -> None:
        self.current = current_thresholds
        self.new = new_thresholds
        self.rollout_pct = rollout_percentage
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        import random
        
        confidence = ctx.inputs.get("confidence", 0.5)
        
        # Decide which thresholds to use
        use_new = random.random() * 100 < self.rollout_pct
        thresholds = self.new if use_new else self.current
        
        route = thresholds.get_route(confidence)
        
        ctx.event_sink.try_emit(
            "route.threshold_decision",
            {
                "confidence": confidence,
                "route": route,
                "used_new_thresholds": use_new,
                "rollout_percentage": self.rollout_pct,
            },
        )
        
        return StageOutput.ok(
            route=route,
            confidence=confidence,
            threshold_version="new" if use_new else "current",
        )
```

### A/B Testing Thresholds

```python
class ThresholdExperiment:
    """Run A/B test on confidence thresholds."""
    
    def __init__(
        self,
        experiment_id: str,
        control_thresholds: ConfidenceThresholds,
        treatment_thresholds: ConfidenceThresholds,
        traffic_split: float = 0.5,
    ) -> None:
        self.experiment_id = experiment_id
        self.control = control_thresholds
        self.treatment = treatment_thresholds
        self.traffic_split = traffic_split
        
        # Metrics tracking
        self.control_metrics = {"correct": 0, "total": 0}
        self.treatment_metrics = {"correct": 0, "total": 0}
    
    def get_thresholds(self, user_id: str) -> tuple[ConfidenceThresholds, str]:
        """Get thresholds for user with consistent assignment."""
        import hashlib
        
        # Consistent bucketing
        hash_input = f"{self.experiment_id}:{user_id}"
        hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest()[:8], 16)
        bucket = (hash_val % 100) / 100.0
        
        if bucket < self.traffic_split:
            return self.treatment, "treatment"
        return self.control, "control"
    
    def record_outcome(self, variant: str, was_correct: bool) -> None:
        """Record experiment outcome."""
        metrics = self.treatment_metrics if variant == "treatment" else self.control_metrics
        metrics["total"] += 1
        if was_correct:
            metrics["correct"] += 1
    
    def get_results(self) -> dict[str, Any]:
        """Get experiment results."""
        control_precision = (
            self.control_metrics["correct"] / self.control_metrics["total"]
            if self.control_metrics["total"] > 0 else 0
        )
        treatment_precision = (
            self.treatment_metrics["correct"] / self.treatment_metrics["total"]
            if self.treatment_metrics["total"] > 0 else 0
        )
        
        return {
            "experiment_id": self.experiment_id,
            "control": {
                "thresholds": {
                    "high": self.control.high_confidence,
                    "medium": self.control.medium_confidence,
                },
                "samples": self.control_metrics["total"],
                "precision": control_precision,
            },
            "treatment": {
                "thresholds": {
                    "high": self.treatment.high_confidence,
                    "medium": self.treatment.medium_confidence,
                },
                "samples": self.treatment_metrics["total"],
                "precision": treatment_precision,
            },
            "lift": treatment_precision - control_precision,
        }
```

## Observability

| Event | Description | Fields |
|-------|-------------|--------|
| `route.confidence_decision` | Routing decision made | `confidence`, `label`, `route`, `thresholds` |
| `route.calibration_drift` | Threshold drift detected | `baseline`, `current`, `drift`, `recommendation` |
| `route.threshold_experiment` | A/B test assignment | `experiment_id`, `variant`, `thresholds` |

## Testing

```python
import pytest


def test_threshold_routing():
    """Test confidence-based routing."""
    thresholds = ConfidenceThresholds(
        high_confidence=0.9,
        medium_confidence=0.5,
    )
    
    assert thresholds.get_route(0.95) == "auto_process"
    assert thresholds.get_route(0.7) == "review_queue"
    assert thresholds.get_route(0.3) == "escalate"


def test_calibration():
    """Test threshold calibration."""
    predictions = [
        {"confidence": 0.95, "was_correct": True},
        {"confidence": 0.90, "was_correct": True},
        {"confidence": 0.85, "was_correct": True},
        {"confidence": 0.80, "was_correct": False},
        {"confidence": 0.70, "was_correct": True},
        {"confidence": 0.60, "was_correct": False},
    ]
    
    calibrator = ThresholdCalibrator(target_precision=0.95)
    result = calibrator.calibrate(predictions)
    
    assert result.recommended_high >= 0.85  # Should exclude 0.80 failure
    assert result.samples_analyzed == 6


def test_drift_detection():
    """Test calibration drift detection."""
    detector = CalibrationDriftDetector(
        window_size=100,
        drift_threshold=0.1,
        check_interval=10,
    )
    
    # Record good predictions
    for _ in range(50):
        detector.record(0.9, True, 0.8)
    
    # Record degraded predictions
    for _ in range(50):
        alert = detector.record(0.9, False, 0.8)
    
    # Should detect drift
    assert alert is not None or detector._check_drift() is not None
```

## Related Guides

- [A/B Testing](../examples/ab-testing.md) - Experiment with thresholds
- [Loop Detection](./routing-loops.md) - Prevent routing loops
- [Observability](../guides/observability.md) - Monitor routing metrics
