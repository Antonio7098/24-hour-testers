"""
Stageflow-based Checklist Processor for 24h Testers.

A robust, observable pipeline for autonomous agent orchestration.
"""

__version__ = "1.0.0"

from .processor import ChecklistProcessor
from .config import ProcessorConfig

__all__ = ["ChecklistProcessor", "ProcessorConfig", "__version__"]
