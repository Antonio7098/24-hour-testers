"""
Stageflow-based Checklist Processor for 24h Testers.

A robust, observable pipeline for autonomous agent orchestration.

Features:
- Phase-based checkpoints with resume capability
- Dynamic timeout scaling based on priority
- Progressive retry strategy
- Real-time output monitoring
- Early warning system for hanging processes
"""

__version__ = "0.3.0"

from .processor import ChecklistProcessor
from .config import ProcessorConfig, TimeoutConfig, RetryConfig
from .checkpoint import CheckpointManager, Checkpoint, Phase

__all__ = [
    "ChecklistProcessor",
    "ProcessorConfig",
    "TimeoutConfig",
    "RetryConfig",
    "CheckpointManager",
    "Checkpoint",
    "Phase",
    "__version__",
]
