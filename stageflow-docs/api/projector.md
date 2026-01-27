# Projector API Reference

This document provides the API reference for Stageflow's WebSocket projection services, which handle real-time message projection and metadata normalization for WebSocket connections.

## Overview

The projector module provides utilities for processing and validating WebSocket messages with proper metadata handling. It ensures consistent message formatting and UUID validation across the system.

## Core Classes

### WSMessageProjector

```python
from stageflow.projector import WSMessageProjector
```

Main projector class for processing WebSocket messages with metadata normalization.

#### Methods

##### `project(message, *, connection_org_id, context_request_id, context_pipeline_run_id) -> dict[str, Any]`

Process and validate a WebSocket message, normalizing metadata and ensuring proper UUID formatting.

**Parameters:**
- `message`: `dict[str, Any]` — The incoming message to process
- `connection_org_id`: `Any | None` — Organization ID from the WebSocket connection
- `context_request_id`: `Any | None` — Request ID from the current context
- `context_pipeline_run_id`: `Any | None` — Pipeline run ID from the current context

**Returns:** `dict[str, Any]` — The processed and validated message

**Raises:** `ValueError` — If message validation fails

**Example:**
```python
projector = WSMessageProjector()

message = {
    "type": "status.update",
    "payload": {
        "service": "chat",
        "status": "processing",
        "metadata": {"stage": "llm"}
    }
}

processed = projector.project(
    message,
    connection_org_id="org-123",
    context_request_id="req-456",
    context_pipeline_run_id="run-789"
)

print(processed["metadata"])
# {
#     "pipeline_run_id": "run-789",
#     "request_id": "req-456", 
#     "org_id": "org-123"
# }
```

**Metadata Resolution Logic:**

The projector follows this priority order for metadata resolution:

1. **Request ID Priority:**
   - `message.metadata.request_id`
   - `message.payload.request_id`
   - `message.payload.requestId`
   - `message.payload.metadata.request_id`
   - `message.payload.metadata.requestId`
   - `context_request_id`
   - Generate new UUID if none found

2. **Pipeline Run ID Priority:**
   - `message.metadata.pipeline_run_id`
   - `message.payload.pipeline_run_id`
   - `message.payload.pipelineRunId`
   - `message.payload.metadata.pipeline_run_id`
   - `message.payload.metadata.pipelineRunId`
   - `context_pipeline_run_id`
   - Generate new UUID if none found

3. **Organization ID:**
   - Uses `connection_org_id` if provided
   - Coerced to valid UUID string format

---

### ProjectorService

```python
from stageflow.projector import ProjectorService
```

**Alias:** `ProjectorService` is an alias for `WSMessageProjector` for backward compatibility.

```python
# These are equivalent:
projector = WSMessageProjector()
projector = ProjectorService()
```

---

## Data Models

### WSMetadata

```python
from stageflow.projector import WSMetadata
```

Pydantic model for WebSocket message metadata.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `pipeline_run_id` | `str` | Pipeline run identifier (UUID string) |
| `request_id` | `str` | Request identifier (UUID string) |
| `org_id` | `str \| None` | Organization identifier (UUID string, optional) |

**Example:**
```python
metadata = WSMetadata(
    pipeline_run_id="550e8400-e29b-41d4-a716-446655440000",
    request_id="550e8400-e29b-41d4-a716-446655440001",
    org_id="550e8400-e29b-41d4-a716-446655440002"
)
```

---

### WSOutboundMessage

```python
from stageflow.projector import WSOutboundMessage
```

Pydantic model for validated outbound WebSocket messages.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `type` | `str` | Message type identifier |
| `payload` | `Any \| None` | Message payload data |
| `metadata` | `WSMetadata` | Normalized message metadata |

**Example:**
```python
message = WSOutboundMessage(
    type="stage.completed",
    payload={"stage": "process", "duration_ms": 1500},
    metadata=WSMetadata(
        pipeline_run_id="550e8400-e29b-41d4-a716-446655440000",
        request_id="550e8400-e29b-41d4-a716-446655440001"
    )
)
```

---

### WSStatusUpdatePayload

```python
from stageflow.projector import WSStatusUpdatePayload
```

Pydantic model for status update message payloads.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `service` | `str` | Service name (e.g., "chat", "voice") |
| `status` | `str` | Status value (e.g., "processing", "completed") |
| `metadata` | `dict[str, Any] \| None` | Additional status metadata |

**Example:**
```python
payload = WSStatusUpdatePayload(
    service="chat",
    status="processing",
    metadata={"stage": "llm", "progress": 0.6}
)
```

---

## Utility Functions

### _coerce_uuid_str()

```python
from stageflow.projector import _coerce_uuid_str
```

Convert a value to a valid UUID string, returning None if conversion fails.

**Parameters:**
- `value`: `Any` — Value to convert to UUID string

**Returns:** `str | None` — Valid UUID string or None

**Example:**
```python
# Valid UUID
uuid_str = _coerce_uuid_str("550e8400-e29b-41d4-a716-446655440000")
print(uuid_str)  # "550e8400-e29b-41d4-a716-446655440000"

# Invalid value
uuid_str = _coerce_uuid_str("invalid-uuid")
print(uuid_str)  # None

# None input
uuid_str = _coerce_uuid_str(None)
print(uuid_str)  # None
```

---

## Usage Examples

### Basic Message Processing

```python
from stageflow.projector import WSMessageProjector

projector = WSMessageProjector()

# Process a simple status update
message = {
    "type": "status.update",
    "payload": {
        "service": "chat",
        "status": "processing"
    }
}

result = projector.project(
    message,
    connection_org_id="org-123",
    context_request_id=None,
    context_pipeline_run_id="run-456"
)

print(result["type"])  # "status.update"
print(result["metadata"]["pipeline_run_id"])  # "run-456"
print(result["metadata"]["request_id"])  # Auto-generated UUID
```

### Processing Complex Messages

```python
# Message with nested metadata
message = {
    "type": "stage.completed",
    "payload": {
        "stage": "llm",
        "result": "Hello, world!",
        "metadata": {
            "request_id": "req-789",
            "pipeline_run_id": "run-456"
        }
    }
}

result = projector.project(
    message,
    connection_org_id="org-123",
    context_request_id="req-fallback",  # Won't be used, payload takes priority
    context_pipeline_run_id="run-fallback"  # Won't be used, payload takes priority
)

print(result["metadata"]["request_id"])  # "req-789" (from payload)
print(result["metadata"]["pipeline_run_id"])  # "run-456" (from payload)
```

### Handling Status Updates

```python
# Valid status update
message = {
    "type": "status.update",
    "payload": {
        "service": "voice",
        "status": "transcribing",
        "metadata": {"confidence": 0.95}
    }
}

result = projector.project(
    message,
    connection_org_id=None,
    context_request_id="req-123",
    context_pipeline_run_id="run-456"
)

# Invalid status update (will raise ValueError)
invalid_message = {
    "type": "status.update", 
    "payload": "should be an object"  # Wrong type
}

try:
    projector.project(invalid_message, ...)
except ValueError as e:
    print(f"Validation failed: {e}")
```

---

## Integration Patterns

### WebSocket Handler Integration

```python
import asyncio
import json
from stageflow.projector import WSMessageProjector

class WebSocketHandler:
    def __init__(self):
        self.projector = WSMessageProjector()
        self.org_id = None  # Set during authentication
    
    async def handle_message(self, websocket, message_data, context):
        try:
            # Project and validate the message
            projected = self.projector.project(
                message_data,
                connection_org_id=self.org_id,
                context_request_id=context.request_id,
                context_pipeline_run_id=context.pipeline_run_id
            )
            
            # Send validated message
            await websocket.send(json.dumps(projected))
            
        except ValueError as e:
            # Handle validation errors
            error_msg = {
                "type": "error",
                "payload": {"error": str(e)},
                "metadata": {
                    "request_id": context.request_id,
                    "pipeline_run_id": context.pipeline_run_id
                }
            }
            await websocket.send(json.dumps(error_msg))
```

### Message Broadcasting

```python
class MessageBroadcaster:
    def __init__(self):
        self.projector = WSMessageProjector()
        self.connections = {}  # org_id -> [websockets]
    
    async def broadcast_to_org(self, message, org_id, context):
        """Broadcast a message to all connections in an organization."""
        projected = self.projector.project(
            message,
            connection_org_id=org_id,
            context_request_id=context.request_id,
            context_pipeline_run_id=context.pipeline_run_id
        )
        
        message_str = json.dumps(projected)
        
        # Send to all connections in the org
        for ws in self.connections.get(org_id, []):
            try:
                await ws.send(message_str)
            except Exception:
                # Handle connection errors
                pass
```

---

## Error Handling

### Common Validation Errors

#### 1. Invalid Status Update Payload
```python
message = {
    "type": "status.update",
    "payload": "invalid"  # Should be object
}
# Raises: ValueError("status.update payload must be an object")
```

#### 2. UUID Coercion Failures
The projector gracefully handles invalid UUIDs by generating new ones or using fallbacks.

#### 3. Missing Required Fields
```python
message = {
    "type": "status.update"
    # Missing payload - will be handled gracefully
}
```

### Logging and Monitoring

The projector logs validation failures with structured data:

```python
import logging

logger = logging.getLogger("ws_projector")

# Validation failures are logged with:
# - service: "ws_projector"
# - message_type: The message type that failed
# - error: The validation error message
```

---

## Performance Considerations

### UUID Generation
- The projector generates UUIDs for missing identifiers
- Consider pre-generating UUIDs in high-throughput scenarios
- UUID generation is thread-safe but has overhead

### Validation Overhead
- Pydantic validation adds overhead but ensures data consistency
- Consider caching validation for repeated message patterns
- Use `exclude_none=True` to reduce message size

### Memory Usage
- Messages are copied during projection
- Large payloads should be handled carefully
- Consider streaming for very large messages

---

## Testing

### Unit Testing Projector

```python
import pytest
from stageflow.projector import WSMessageProjector, WSMetadata

def test_basic_projection():
    projector = WSMessageProjector()
    
    message = {
        "type": "test",
        "payload": {"data": "value"}
    }
    
    result = projector.project(
        message,
        connection_org_id=None,
        context_request_id="req-123",
        context_pipeline_run_id="run-456"
    )
    
    assert result["type"] == "test"
    assert result["metadata"]["request_id"] == "req-123"
    assert result["metadata"]["pipeline_run_id"] == "run-456"

def test_status_update_validation():
    projector = WSMessageProjector()
    
    # Valid status update
    valid_message = {
        "type": "status.update",
        "payload": {
            "service": "test",
            "status": "running"
        }
    }
    
    result = projector.project(valid_message, ...)
    assert result["type"] == "status.update"
    
    # Invalid status update
    invalid_message = {
        "type": "status.update",
        "payload": "invalid"
    }
    
    with pytest.raises(ValueError):
        projector.project(invalid_message, ...)
```

---

## Migration Notes

### From ProjectorService to WSMessageProjector

```python
# Old code (still works for backward compatibility)
from stageflow.projector import ProjectorService
projector = ProjectorService()

# New code (recommended)
from stageflow.projector import WSMessageProjector
projector = WSMessageProjector()
```

Both classes are identical; `ProjectorService` is maintained for backward compatibility.

---

## Best Practices

1. **Always provide context IDs** when available to ensure proper correlation
2. **Handle validation errors gracefully** in production code
3. **Use structured logging** to monitor projector performance
4. **Test with various message formats** to ensure robustness
5. **Consider message size** when working with large payloads
6. **Use organization-based filtering** for multi-tenant applications
