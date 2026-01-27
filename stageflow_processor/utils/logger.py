"""
Structured logging setup for the Checklist Processor.

Provides consistent, observable logging across all components.
"""

import logging
import sys
from datetime import datetime
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Formatter that outputs structured log data."""
    
    COLORS = {
        logging.DEBUG: "\033[90m",    # Gray
        logging.INFO: "\033[36m",     # Cyan
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",    # Red
        logging.CRITICAL: "\033[35m", # Magenta
    }
    RESET = "\033[0m"
    
    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().isoformat()
        level = record.levelname.ljust(5)
        name = record.name
        message = record.getMessage()
        
        # Format extra data if present
        extra = ""
        if hasattr(record, "extra_data") and record.extra_data:
            extra = f" {record.extra_data}"
        
        if self.use_colors:
            color = self.COLORS.get(record.levelno, "")
            return f"{color}[{timestamp}][{name}][{level}]{self.RESET} {message}{extra}"
        return f"[{timestamp}][{name}][{level}] {message}{extra}"


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that adds context to all log messages."""
    
    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = kwargs.get("extra", {})
        if self.extra:
            extra.update(self.extra)
        kwargs["extra"] = extra
        
        # Store extra data for formatter
        if extra:
            kwargs.setdefault("extra", {})["extra_data"] = extra
        
        return msg, kwargs


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    if quiet:
        level = logging.WARNING
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter(use_colors=True))
    
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    
    # Reduce noise from external libraries
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str, **context) -> ContextLogger:
    """Get a context-aware logger."""
    logger = logging.getLogger(name)
    return ContextLogger(logger, context)
