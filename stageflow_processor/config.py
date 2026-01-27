"""
Configuration management for the Checklist Processor.

Implements fail-fast validation and SOLID principles.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from enum import Enum
import os


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
class RetryConfig:
    """Retry policy configuration."""
    max_retries: int = 2
    base_delay_ms: int = 5000
    max_delay_ms: int = 30000
    backoff_multiplier: float = 2.0
    retryable_errors: list[str] = field(default_factory=lambda: [
        "ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "EPIPE", "ENOTFOUND"
    ])


@dataclass
class ProcessorConfig:
    """
    Main configuration for the Checklist Processor.
    
    Implements fail-fast validation - raises on invalid configuration.
    """
    repo_root: Path
    checklist_path: Path | None = None
    mission_brief_path: Path | None = None
    agent_prompt_path: Path | None = None
    runs_dir: Path | None = None
    state_dir: Path | None = None
    
    # Processing settings
    batch_size: int = 5
    max_iterations: int = 20
    mode: ProcessingMode = ProcessingMode.FINITE
    dry_run: bool = False
    
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
        
        if self.agent_prompt_path is None:
            self.agent_prompt_path = self.repo_root / "agent-resources" / "prompts" / "AGENT_SYSTEM_PROMPT.md"
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
            self.state_dir = self.repo_root / ".checklist-processor"
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
