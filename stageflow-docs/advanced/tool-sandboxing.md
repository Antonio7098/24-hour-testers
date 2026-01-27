# Tool Sandboxing & Security

Agent tools execute arbitrary code and interact with external systems. **Sandboxing**
isolates tool execution to prevent unauthorized access, resource exhaustion, and
security breaches. This guide covers isolation strategies for production deployments.

## Isolation Levels

| Approach | Isolation | Performance | Use Case |
|----------|-----------|-------------|----------|
| Process | Low | High | Development, trusted tools |
| Container (Docker) | Medium | Medium | Standard production |
| MicroVM (Firecracker) | High | Medium | Multi-tenant, untrusted code |
| WASM | Medium | High | Browser, edge deployments |

## Security Considerations

### Network Egress Control

Restrict which domains tools can access:

```python
from dataclasses import dataclass
from typing import Any
import logging

logger = logging.getLogger("stageflow.sandbox")


@dataclass
class NetworkPolicy:
    """Network egress policy for sandboxed tools."""
    
    allowed_domains: set[str]
    allowed_ports: set[int] = frozenset({80, 443})
    block_private_ranges: bool = True
    max_connections: int = 10
    timeout_seconds: int = 30
    
    def is_allowed(self, host: str, port: int) -> bool:
        """Check if connection is allowed by policy."""
        if port not in self.allowed_ports:
            return False
        
        if self.block_private_ranges and self._is_private(host):
            return False
        
        # Check against allowed domains (exact or wildcard)
        for domain in self.allowed_domains:
            if domain.startswith("*."):
                # Wildcard match
                if host.endswith(domain[1:]):
                    return True
            elif host == domain:
                return True
        
        return False
    
    def _is_private(self, host: str) -> bool:
        """Check if host is a private IP range."""
        import ipaddress
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback
        except ValueError:
            # Not an IP, it's a hostname
            return host in ("localhost", "127.0.0.1", "::1")


# Example: API-only policy
api_policy = NetworkPolicy(
    allowed_domains={
        "api.openai.com",
        "api.anthropic.com",
        "*.amazonaws.com",
    },
    allowed_ports={443},
    block_private_ranges=True,
)
```

### Resource Quotas

Limit CPU, memory, and file system access:

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceQuota:
    """Resource limits for sandboxed execution."""
    
    max_memory_mb: int = 512
    max_cpu_percent: int = 100
    max_execution_seconds: int = 60
    max_file_size_mb: int = 10
    max_open_files: int = 100
    allowed_paths: set[str] = frozenset({"/tmp/sandbox"})
    read_only_paths: set[str] = frozenset()
    
    def to_docker_config(self) -> dict[str, Any]:
        """Convert to Docker container config."""
        return {
            "mem_limit": f"{self.max_memory_mb}m",
            "cpu_period": 100000,
            "cpu_quota": self.max_cpu_percent * 1000,
            "ulimits": [
                {"Name": "nofile", "Soft": self.max_open_files, "Hard": self.max_open_files},
            ],
            "read_only": True,
            "tmpfs": {"/tmp": f"size={self.max_file_size_mb}m"},
        }
```

### Capability Restrictions

Define what tools can do:

```python
from enum import Flag, auto


class ToolCapability(Flag):
    """Capabilities that can be granted to tools."""
    
    NONE = 0
    
    # Network
    NETWORK_READ = auto()  # HTTP GET
    NETWORK_WRITE = auto()  # HTTP POST/PUT/DELETE
    
    # File system
    FILE_READ = auto()
    FILE_WRITE = auto()
    FILE_DELETE = auto()
    
    # System
    SPAWN_PROCESS = auto()
    ENVIRONMENT_ACCESS = auto()
    
    # External services
    DATABASE_READ = auto()
    DATABASE_WRITE = auto()
    CACHE_ACCESS = auto()
    QUEUE_PUBLISH = auto()
    
    # Combinations
    READ_ONLY = NETWORK_READ | FILE_READ | DATABASE_READ
    FULL_NETWORK = NETWORK_READ | NETWORK_WRITE
    FULL_FILE = FILE_READ | FILE_WRITE | FILE_DELETE


@dataclass
class SecurityContext:
    """Security context for tool execution."""
    
    capabilities: ToolCapability
    network_policy: NetworkPolicy | None = None
    resource_quota: ResourceQuota | None = None
    user_id: str | None = None
    org_id: str | None = None
    
    def has_capability(self, cap: ToolCapability) -> bool:
        """Check if context has required capability."""
        return (self.capabilities & cap) == cap
```

## Container-Based Sandboxing

### Docker Sandbox Executor

```python
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger("stageflow.sandbox.docker")


class DockerSandboxExecutor:
    """Execute tools in isolated Docker containers."""
    
    def __init__(
        self,
        image: str = "python:3.11-slim",
        network_policy: NetworkPolicy | None = None,
        resource_quota: ResourceQuota | None = None,
    ) -> None:
        self.image = image
        self.network_policy = network_policy
        self.resource_quota = resource_quota or ResourceQuota()
    
    async def execute(
        self,
        tool_code: str,
        input_data: dict[str, Any],
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """Execute tool code in a sandboxed container.
        
        Args:
            tool_code: Python code to execute
            input_data: JSON-serializable input
            timeout_seconds: Execution timeout
        
        Returns:
            Tool output as dictionary
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write tool code and input
            code_path = Path(tmpdir) / "tool.py"
            input_path = Path(tmpdir) / "input.json"
            output_path = Path(tmpdir) / "output.json"
            
            code_path.write_text(self._wrap_code(tool_code))
            input_path.write_text(json.dumps(input_data))
            
            # Build docker command
            cmd = self._build_docker_command(tmpdir, timeout_seconds)
            
            logger.info(
                "Executing tool in Docker sandbox",
                extra={"image": self.image, "timeout": timeout_seconds},
            )
            
            # Run container
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_seconds + 5,  # Buffer for container startup
                )
                
                if proc.returncode != 0:
                    logger.error(
                        f"Sandbox execution failed: {stderr.decode()}",
                        extra={"returncode": proc.returncode},
                    )
                    return {
                        "success": False,
                        "error": f"Execution failed: {stderr.decode()[:500]}",
                    }
                
                # Read output
                if output_path.exists():
                    return json.loads(output_path.read_text())
                else:
                    return {
                        "success": False,
                        "error": "No output produced",
                    }
                
            except asyncio.TimeoutError:
                logger.warning("Sandbox execution timed out")
                return {
                    "success": False,
                    "error": f"Execution timed out after {timeout_seconds}s",
                }
    
    def _wrap_code(self, tool_code: str) -> str:
        """Wrap tool code with I/O handling."""
        return f'''
import json
import sys

def main():
    with open("/sandbox/input.json") as f:
        input_data = json.load(f)
    
    # User tool code
{self._indent(tool_code, 4)}
    
    # Execute and capture result
    try:
        result = execute(input_data)
        output = {{"success": True, "data": result}}
    except Exception as e:
        output = {{"success": False, "error": str(e)}}
    
    with open("/sandbox/output.json", "w") as f:
        json.dump(output, f)

if __name__ == "__main__":
    main()
'''
    
    def _indent(self, code: str, spaces: int) -> str:
        """Indent code block."""
        prefix = " " * spaces
        return "\n".join(prefix + line for line in code.split("\n"))
    
    def _build_docker_command(self, tmpdir: str, timeout: int) -> list[str]:
        """Build docker run command with security settings."""
        cmd = [
            "docker", "run",
            "--rm",  # Remove container after execution
            "--network", "none" if not self.network_policy else "bridge",
            "-v", f"{tmpdir}:/sandbox:rw",
            "--workdir", "/sandbox",
        ]
        
        # Apply resource limits
        quota = self.resource_quota
        cmd.extend([
            "--memory", f"{quota.max_memory_mb}m",
            "--cpus", str(quota.max_cpu_percent / 100),
            "--ulimit", f"nofile={quota.max_open_files}",
            "--read-only",
            "--tmpfs", f"/tmp:size={quota.max_file_size_mb}m",
        ])
        
        # Security options
        cmd.extend([
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
        ])
        
        # Timeout
        cmd.extend(["--stop-timeout", str(timeout)])
        
        # Image and command
        cmd.extend([self.image, "python", "/sandbox/tool.py"])
        
        return cmd
```

## Process-Based Sandboxing

For development or trusted tools, use process isolation:

```python
import asyncio
import resource
import signal
from typing import Any


class ProcessSandboxExecutor:
    """Execute tools in isolated processes with resource limits."""
    
    def __init__(
        self,
        max_memory_mb: int = 256,
        max_cpu_seconds: int = 30,
    ) -> None:
        self.max_memory_mb = max_memory_mb
        self.max_cpu_seconds = max_cpu_seconds
    
    async def execute(
        self,
        func: callable,
        *args: Any,
        timeout_seconds: int = 60,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute function in sandboxed subprocess."""
        import multiprocessing as mp
        
        # Create result queue
        result_queue = mp.Queue()
        
        # Create process with resource limits
        proc = mp.Process(
            target=self._run_with_limits,
            args=(func, args, kwargs, result_queue),
        )
        
        proc.start()
        
        try:
            # Wait for result with timeout
            proc.join(timeout=timeout_seconds)
            
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.kill()
                return {"success": False, "error": "Execution timed out"}
            
            if result_queue.empty():
                return {"success": False, "error": "No result produced"}
            
            return result_queue.get_nowait()
            
        finally:
            if proc.is_alive():
                proc.kill()
    
    def _run_with_limits(
        self,
        func: callable,
        args: tuple,
        kwargs: dict,
        result_queue: Any,
    ) -> None:
        """Run function with resource limits applied."""
        # Set memory limit
        memory_bytes = self.max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        
        # Set CPU time limit
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (self.max_cpu_seconds, self.max_cpu_seconds),
        )
        
        try:
            result = func(*args, **kwargs)
            result_queue.put({"success": True, "data": result})
        except Exception as e:
            result_queue.put({"success": False, "error": str(e)})
```

## Sandbox Interceptor

Integrate sandboxing into pipeline execution:

```python
from stageflow.pipeline.interceptors import BaseInterceptor, InterceptorResult
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult


class SandboxInterceptor(BaseInterceptor):
    """Interceptor that enforces sandbox policies on tool execution."""
    
    name = "sandbox"
    priority = 8  # Run very early, before most interceptors
    
    def __init__(
        self,
        executor: DockerSandboxExecutor | ProcessSandboxExecutor,
        sandboxed_stages: set[str] | None = None,
    ) -> None:
        self.executor = executor
        self.sandboxed_stages = sandboxed_stages or set()
    
    async def before(
        self, stage_name: str, ctx: PipelineContext
    ) -> InterceptorResult | None:
        """Check sandbox requirements before execution."""
        
        # Verify security context exists for sandboxed stages
        if stage_name in self.sandboxed_stages:
            security_ctx = ctx.data.get("_security_context")
            if not security_ctx:
                logger.warning(
                    f"Sandboxed stage {stage_name} missing security context",
                    extra={"stage": stage_name},
                )
        
        return None
    
    async def after(
        self, stage_name: str, result: StageResult, ctx: PipelineContext
    ) -> None:
        """Log sandbox execution metrics."""
        if stage_name in self.sandboxed_stages:
            logger.info(
                f"Sandboxed stage {stage_name} completed",
                extra={
                    "stage": stage_name,
                    "status": result.status,
                    "sandboxed": True,
                },
            )
```

## Security Best Practices

### 1. Principle of Least Privilege

```python
# Good: minimal capabilities for specific tool
read_only_context = SecurityContext(
    capabilities=ToolCapability.NETWORK_READ | ToolCapability.FILE_READ,
    network_policy=NetworkPolicy(allowed_domains={"api.example.com"}),
)

# Bad: overly permissive
admin_context = SecurityContext(
    capabilities=ToolCapability.FULL_NETWORK | ToolCapability.FULL_FILE,
)
```

### 2. Validate All Inputs

```python
from pydantic import BaseModel, validator


class ToolInput(BaseModel):
    """Validated tool input."""
    
    url: str
    method: str = "GET"
    
    @validator("url")
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must use http or https")
        return v
    
    @validator("method")
    def validate_method(cls, v):
        allowed = {"GET", "POST", "PUT", "DELETE"}
        if v.upper() not in allowed:
            raise ValueError(f"Method must be one of {allowed}")
        return v.upper()
```

### 3. Audit All Tool Executions

```python
async def execute_with_audit(
    tool: Tool,
    input: ToolInput,
    ctx: PipelineContext,
) -> ToolOutput:
    """Execute tool with full audit logging."""
    
    # Log execution start
    ctx.event_sink.try_emit(
        "tool.execution_started",
        {
            "tool_name": tool.name,
            "action_type": tool.action_type,
            "user_id": str(ctx.user_id),
            "org_id": str(ctx.org_id),
            "input_hash": hash_input(input),
        },
    )
    
    try:
        result = await tool.execute(input, ctx.to_dict())
        
        ctx.event_sink.try_emit(
            "tool.execution_completed",
            {
                "tool_name": tool.name,
                "success": result.success,
                "has_artifacts": bool(result.artifacts),
            },
        )
        
        return result
        
    except Exception as e:
        ctx.event_sink.try_emit(
            "tool.execution_failed",
            {
                "tool_name": tool.name,
                "error_type": type(e).__name__,
                "error": str(e)[:500],
            },
        )
        raise
```

### 4. Rotate Credentials

```python
class SecureCredentialProvider:
    """Provide short-lived credentials to sandboxed tools."""
    
    async def get_credentials(
        self,
        tool_name: str,
        ctx: SecurityContext,
    ) -> dict[str, str]:
        """Get short-lived credentials for tool execution."""
        
        # Generate short-lived token
        token = await self._generate_scoped_token(
            tool_name=tool_name,
            user_id=ctx.user_id,
            org_id=ctx.org_id,
            ttl_seconds=300,  # 5 minute expiry
        )
        
        return {
            "TOOL_API_TOKEN": token,
            "TOOL_API_EXPIRES": str(int(time.time()) + 300),
        }
```

## Testing Sandbox Security

```python
import pytest


@pytest.mark.asyncio
async def test_sandbox_blocks_network_access():
    """Verify sandbox blocks unauthorized network access."""
    
    executor = DockerSandboxExecutor(
        network_policy=NetworkPolicy(
            allowed_domains={"api.allowed.com"},
        ),
    )
    
    malicious_code = """
def execute(input_data):
    import urllib.request
    return urllib.request.urlopen("http://evil.com").read()
"""
    
    result = await executor.execute(malicious_code, {})
    
    assert not result["success"]
    assert "network" in result["error"].lower() or "connection" in result["error"].lower()


@pytest.mark.asyncio
async def test_sandbox_enforces_memory_limit():
    """Verify sandbox enforces memory limits."""
    
    executor = DockerSandboxExecutor(
        resource_quota=ResourceQuota(max_memory_mb=64),
    )
    
    memory_bomb = """
def execute(input_data):
    data = []
    while True:
        data.append("x" * 10_000_000)
"""
    
    result = await executor.execute(memory_bomb, {}, timeout_seconds=10)
    
    assert not result["success"]
    assert "memory" in result["error"].lower() or "killed" in result["error"].lower()


@pytest.mark.asyncio
async def test_sandbox_enforces_timeout():
    """Verify sandbox enforces execution timeout."""
    
    executor = DockerSandboxExecutor()
    
    infinite_loop = """
def execute(input_data):
    while True:
        pass
"""
    
    result = await executor.execute(infinite_loop, {}, timeout_seconds=2)
    
    assert not result["success"]
    assert "timeout" in result["error"].lower()
```

## Related Guides

- [Tool Registry](../api/tools.md) - Register and execute tools
- [Custom Interceptors](./custom-interceptors.md) - Add security interceptors
- [Auth & Tenancy](../api/auth.md) - Multi-tenant security contexts
