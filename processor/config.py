"""
Configuration management for the Checklist Processor.

Implements fail-fast validation and SOLID principles.
Supports overridable agent-resources for custom deployments.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from enum import Enum
import os
import importlib.resources


def get_default_agent_resources_dir() -> Path:
    """Get the default agent-resources directory from package data.

    Falls back to looking relative to repo_root if not installed as package.
    """
    try:
        # Try to get from package resources (when installed as package)
        pkg_files = importlib.resources.files("processor")
        parent = Path(str(pkg_files)).parent
        resources_dir = parent / "agent-resources"
        if resources_dir.exists():
            return resources_dir
    except Exception:
        pass

    # Fallback: return None to indicate using repo_root default
    return None


class ProcessingMode(str, Enum):
    """Processing mode for the checklist processor."""
    FINITE = "finite"
    INFINITE = "infinite"


class AgentRuntime(str, Enum):
    """Supported agent runtimes."""
    OPENCODE = "opencode"
    CLAUDE_CODE = "claude-code"


@dataclass
class RuntimeConfig:
    """Configuration for a specific agent runtime."""
    label: str
    default_model: str
    command_env: str
    default_command: str
    
    def build_args(self, model: str) -> list[str]:
        """Build command line arguments for this runtime."""
        raise NotImplementedError


@dataclass
class OpenCodeConfig(RuntimeConfig):
    """OpenCode runtime configuration."""
    label: str = "OpenCode"
    default_model: str = "minimax-coding-plan/MiniMax-M2.1"
    command_env: str = "OPENCODE_BIN"
    default_command: str = "opencode"
    
    def build_args(self, model: str) -> list[str]:
        return ["run", "--model", model]


@dataclass
class ClaudeCodeConfig(RuntimeConfig):
    """Claude Code runtime configuration."""
    label: str = "Claude Code"
    default_model: str = "claude-4.5-sonnet"
    command_env: str = "CLAUDE_CODE_BIN"
    default_command: str = "claude"
    
    def build_args(self, model: str) -> list[str]:
        return ["code", "--model", model]


RUNTIME_CONFIGS: dict[AgentRuntime, RuntimeConfig] = {
    AgentRuntime.OPENCODE: OpenCodeConfig(),
    AgentRuntime.CLAUDE_CODE: ClaudeCodeConfig(),
}


@dataclass
class TimeoutConfig:
    """Dynamic timeout configuration based on item priority.

    When a base_timeout_ms is provided (e.g., via CLI --timeout), all priority
    timeouts are scaled relative to this base value using multipliers.
    Otherwise, hardcoded defaults are used.
    """
    # Priority multipliers (relative to base timeout)
    p0_critical_multiplier: float = 1.5   # 150% of base for critical items
    p1_high_multiplier: float = 1.2       # 120% of base for high priority
    p1_medium_multiplier: float = 1.0     # 100% of base for medium priority
    p2_low_multiplier: float = 1.0        # 100% of base for low priority
    default_multiplier: float = 1.0       # 100% of base for unspecified priority

    # Hardcoded defaults (used only when base_timeout_ms is not provided)
    p0_critical_ms: int = 900000   # 15 minutes
    p1_high_ms: int = 720000       # 12 minutes
    p1_medium_ms: int = 600000     # 10 minutes
    p2_low_ms: int = 600000        # 10 minutes
    default_ms: int = 600000       # 10 minutes

    # Base timeout override (typically from CLI --timeout)
    base_timeout_ms: int | None = None

    # Timeout multiplier for retries (attempt 2 gets 20% more time)
    retry_multiplier: float = 1.2

    def get_timeout_for_priority(self, priority: str, attempt: int = 1) -> int:
        """Get timeout in ms based on priority string and attempt number.

        If base_timeout_ms is set, uses multipliers relative to base.
        Otherwise, uses hardcoded defaults for backward compatibility.
        """
        priority_lower = priority.lower().strip()

        # Determine if we're using base timeout with multipliers or hardcoded defaults
        if self.base_timeout_ms is not None:
            # Use multiplier-based scaling from CLI override
            if "p0" in priority_lower or "critical" in priority_lower:
                base = int(self.base_timeout_ms * self.p0_critical_multiplier)
            elif "p1" in priority_lower and "high" in priority_lower:
                base = int(self.base_timeout_ms * self.p1_high_multiplier)
            elif "p1" in priority_lower:
                base = int(self.base_timeout_ms * self.p1_medium_multiplier)
            elif "p2" in priority_lower or "low" in priority_lower:
                base = int(self.base_timeout_ms * self.p2_low_multiplier)
            elif "high" in priority_lower:
                base = int(self.base_timeout_ms * self.p1_high_multiplier)
            elif "medium" in priority_lower:
                base = int(self.base_timeout_ms * self.p1_medium_multiplier)
            elif "low" in priority_lower:
                base = int(self.base_timeout_ms * self.p2_low_multiplier)
            else:
                base = int(self.base_timeout_ms * self.default_multiplier)
        else:
            # Use hardcoded defaults (backward compatibility)
            if "p0" in priority_lower or "critical" in priority_lower:
                base = self.p0_critical_ms
            elif "p1" in priority_lower and "high" in priority_lower:
                base = self.p1_high_ms
            elif "p1" in priority_lower:
                base = self.p1_medium_ms
            elif "p2" in priority_lower or "low" in priority_lower:
                base = self.p2_low_ms
            elif "high" in priority_lower:
                base = self.p1_high_ms
            elif "medium" in priority_lower:
                base = self.p1_medium_ms
            elif "low" in priority_lower:
                base = self.p2_low_ms
            else:
                base = self.default_ms

        # Apply retry multiplier for subsequent attempts
        if attempt > 1:
            multiplier = self.retry_multiplier ** (attempt - 1)
            return int(base * multiplier)

        return base


@dataclass
class RetryConfig:
    """Progressive retry policy configuration."""
    max_retries: int = 3
    base_delay_ms: int = 5000
    max_delay_ms: int = 30000
    backoff_multiplier: float = 2.0
    retryable_errors: list[str] = field(default_factory=lambda: [
        "ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "EPIPE", "ENOTFOUND"
    ])

    # Progressive retry modes
    # Attempt 1: Full run
    # Attempt 2: Resume from checkpoint + more time
    # Attempt 3: Simplified mode (skip secondary platforms)
    use_checkpoint_on_retry: bool = True
    simplified_mode_on_final_retry: bool = True


@dataclass
class ProcessorConfig:
    """
    Main configuration for the Checklist Processor.

    Implements fail-fast validation - raises on invalid configuration.

    agent_resources_dir: Override default agent-resources with custom directory.
                        If not specified, falls back to repo_root/agent-resources
                        or package default.
    """
    repo_root: Path
    checklist_path: Path | None = None
    mission_brief_path: Path | None = None
    agent_prompt_path: Path | None = None
    runs_dir: Path | None = None
    state_dir: Path | None = None

    # Agent resources override - allows custom prompts/templates
    agent_resources_dir: Path | None = None

    # Processing settings
    batch_size: int = 5
    max_iterations: int = 20
    mode: ProcessingMode = ProcessingMode.FINITE
    dry_run: bool = False

    # Checkpoint settings
    enable_checkpoints: bool = True  # Save/resume from phase checkpoints

    # Timeout settings (dynamic based on priority)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)

    # Agent settings
    runtime: AgentRuntime = AgentRuntime.OPENCODE
    model: str | None = None
    timeout_ms: int = 300000  # 5 minutes

    # Retry settings
    retry: RetryConfig = field(default_factory=RetryConfig)

    # Observability
    verbose: bool = False

    def __post_init__(self):
        """Validate and resolve paths after initialization."""
        self.repo_root = Path(self.repo_root).resolve()

        if not self.repo_root.exists():
            raise ValueError(f"Repository root does not exist: {self.repo_root}")

        # Set base timeout on TimeoutConfig if CLI timeout was provided
        # This ensures priority-based timeouts scale from the CLI value
        if self.timeout_ms != 300000:  # 300000 is the default, any other value is user-provided
            self.timeouts.base_timeout_ms = self.timeout_ms

        # Resolve agent resources directory (supports override for custom deployments)
        if self.agent_resources_dir is not None:
            self.agent_resources_dir = Path(self.agent_resources_dir)
            if not self.agent_resources_dir.is_absolute():
                self.agent_resources_dir = self.repo_root / self.agent_resources_dir
        else:
            # Try repo_root first, then package default
            repo_resources = self.repo_root / "agent-resources"
            if repo_resources.exists():
                self.agent_resources_dir = repo_resources
            else:
                pkg_default = get_default_agent_resources_dir()
                self.agent_resources_dir = pkg_default if pkg_default else repo_resources

        # Resolve default paths
        if self.checklist_path is None:
            self.checklist_path = self.repo_root / "SUT-CHECKLIST.md"
        else:
            self.checklist_path = Path(self.checklist_path)
            if not self.checklist_path.is_absolute():
                self.checklist_path = self.repo_root / self.checklist_path

        if self.mission_brief_path is None:
            primary = self.repo_root / "SUT-PACKET.md"
            fallback = self.repo_root / "README.md"
            self.mission_brief_path = primary if primary.exists() else fallback
        else:
            self.mission_brief_path = Path(self.mission_brief_path)
            if not self.mission_brief_path.is_absolute():
                self.mission_brief_path = self.repo_root / self.mission_brief_path

        # Use agent_resources_dir for prompt path if not explicitly set
        if self.agent_prompt_path is None:
            self.agent_prompt_path = self.agent_resources_dir / "prompts" / "AGENT_SYSTEM_PROMPT.md"
        else:
            self.agent_prompt_path = Path(self.agent_prompt_path)
            if not self.agent_prompt_path.is_absolute():
                self.agent_prompt_path = self.repo_root / self.agent_prompt_path

        if self.runs_dir is None:
            self.runs_dir = self.repo_root / "runs"
        else:
            self.runs_dir = Path(self.runs_dir)
            if not self.runs_dir.is_absolute():
                self.runs_dir = self.repo_root / self.runs_dir

        if self.state_dir is None:
            self.state_dir = self.repo_root / ".processor"
        else:
            self.state_dir = Path(self.state_dir)
            if not self.state_dir.is_absolute():
                self.state_dir = self.repo_root / self.state_dir

        # Validate batch size
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size}")

        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")

        if self.timeout_ms < 1000:
            raise ValueError(f"timeout_ms must be >= 1000, got {self.timeout_ms}")
    
    def get_runtime_config(self) -> RuntimeConfig:
        """Get the configuration for the selected runtime."""
        return RUNTIME_CONFIGS[self.runtime]
    
    def get_runtime_command(self) -> str:
        """Get the command to invoke the runtime."""
        config = self.get_runtime_config()
        return os.environ.get(config.command_env, config.default_command)
    
    def get_model(self) -> str:
        """Get the model to use, defaulting to runtime default."""
        if self.model:
            return self.model
        return self.get_runtime_config().default_model
    
    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
