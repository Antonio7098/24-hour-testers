# Timestamp Handling Guide

Timestamps appear in diverse formats across APIs, databases, and file systems. This
guide covers parsing, normalization, and best practices for timestamp handling in
Stageflow pipelines.

## Supported Formats

| Format | Example | Use Case |
|--------|---------|----------|
| ISO 8601 | `2024-01-23T14:30:00Z` | Standard API format |
| RFC 2822 | `Tue, 23 Jan 2024 14:30:00 GMT` | Email headers, HTTP |
| Unix (seconds) | `1706020200` | Databases, APIs |
| Unix (milliseconds) | `1706020200000` | JavaScript, Java |
| Unix (microseconds) | `1706020200000000` | High-precision systems |

## Using Stageflow Timestamp Helpers

Stageflow provides utilities in `stageflow.helpers.timestamps`:

```python
from stageflow.helpers import parse_timestamp, detect_unix_precision, normalize_to_utc
```

### parse_timestamp()

Parse timestamps from various formats:

```python
from stageflow.helpers import parse_timestamp

# ISO 8601
dt = parse_timestamp("2024-01-23T14:30:00Z")

# RFC 2822 (email/HTTP headers)
dt = parse_timestamp("Tue, 23 Jan 2024 14:30:00 GMT")

# Unix epoch (auto-detects precision)
dt = parse_timestamp(1706020200)        # seconds
dt = parse_timestamp(1706020200000)     # milliseconds
dt = parse_timestamp(1706020200000000)  # microseconds

# String Unix timestamps
dt = parse_timestamp("1706020200")
```

### detect_unix_precision()

Determine Unix timestamp precision before conversion:

```python
from stageflow.helpers import detect_unix_precision

precision = detect_unix_precision(1706020200)        # "seconds"
precision = detect_unix_precision(1706020200000)     # "milliseconds"
precision = detect_unix_precision(1706020200000000)  # "microseconds"
```

### normalize_to_utc()

Ensure consistent UTC timezone:

```python
from datetime import datetime
from stageflow.helpers import normalize_to_utc

# Naive datetime → UTC
naive = datetime(2024, 1, 23, 14, 30, 0)
utc = normalize_to_utc(naive)  # Assumes UTC, attaches tzinfo

# Aware datetime → UTC
from zoneinfo import ZoneInfo
eastern = datetime(2024, 1, 23, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))
utc = normalize_to_utc(eastern)  # Converts to UTC
```

## Common Patterns

### Extracting Timestamps from Documents

```python
from datetime import datetime, timezone
from stageflow.core import StageKind, StageOutput
from stageflow.stages.context import StageContext
from stageflow.helpers import parse_timestamp


class TimestampExtractStage:
    """Extract and normalize timestamps from documents."""
    
    name = "timestamp_extract"
    kind = StageKind.TRANSFORM
    
    def __init__(self, timestamp_fields: list[str] | None = None) -> None:
        self.timestamp_fields = timestamp_fields or [
            "created_at", "updated_at", "timestamp", "date", "time"
        ]
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        document = ctx.inputs["document"]
        extracted = {}
        
        for field in self.timestamp_fields:
            if field in document:
                try:
                    dt = parse_timestamp(document[field])
                    extracted[field] = dt.isoformat()
                except (ValueError, TypeError) as e:
                    ctx.event_sink.try_emit(
                        "timestamp.parse_failed",
                        {"field": field, "value": str(document[field])[:100], "error": str(e)},
                    )
        
        return StageOutput.ok(
            timestamps=extracted,
            document={**document, **extracted},
        )
```

### Handling API Responses

```python
from stageflow.helpers import parse_timestamp, detect_unix_precision


class APIResponseNormalizerStage:
    """Normalize timestamps in API responses."""
    
    name = "api_normalizer"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        response = ctx.inputs["api_response"]
        
        normalized = self._normalize_timestamps(response)
        
        return StageOutput.ok(normalized_response=normalized)
    
    def _normalize_timestamps(self, data: dict) -> dict:
        """Recursively normalize timestamps in nested data."""
        result = {}
        
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._normalize_timestamps(value)
            elif isinstance(value, list):
                result[key] = [
                    self._normalize_timestamps(item) if isinstance(item, dict)
                    else self._try_parse_timestamp(item)
                    for item in value
                ]
            elif self._looks_like_timestamp(key, value):
                result[key] = self._try_parse_timestamp(value)
            else:
                result[key] = value
        
        return result
    
    def _looks_like_timestamp(self, key: str, value) -> bool:
        """Heuristic check if field might be a timestamp."""
        timestamp_keys = {"timestamp", "time", "date", "created", "updated", "at"}
        key_lower = key.lower()
        
        # Check key name
        if any(ts_key in key_lower for ts_key in timestamp_keys):
            return True
        
        # Check value format
        if isinstance(value, (int, float)) and value > 1_000_000_000:
            return True
        
        if isinstance(value, str) and ("T" in value or "GMT" in value):
            return True
        
        return False
    
    def _try_parse_timestamp(self, value) -> str | Any:
        """Try to parse as timestamp, return original on failure."""
        try:
            dt = parse_timestamp(value)
            return dt.isoformat()
        except (ValueError, TypeError):
            return value
```

### Timezone-Safe Comparisons

```python
from datetime import datetime, timezone
from stageflow.helpers import normalize_to_utc


class TemporalFilterStage:
    """Filter records by timestamp range."""
    
    name = "temporal_filter"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        records = ctx.inputs["records"]
        start_time = ctx.inputs.get("start_time")
        end_time = ctx.inputs.get("end_time")
        
        # Normalize filter bounds to UTC
        start_utc = normalize_to_utc(parse_timestamp(start_time)) if start_time else None
        end_utc = normalize_to_utc(parse_timestamp(end_time)) if end_time else None
        
        filtered = []
        for record in records:
            record_time = normalize_to_utc(parse_timestamp(record["timestamp"]))
            
            if start_utc and record_time < start_utc:
                continue
            if end_utc and record_time > end_utc:
                continue
            
            filtered.append(record)
        
        return StageOutput.ok(
            filtered_records=filtered,
            count=len(filtered),
            time_range={"start": start_utc.isoformat() if start_utc else None,
                       "end": end_utc.isoformat() if end_utc else None},
        )
```

## Best Practices

### 1. Always Use Timezone-Aware Datetimes

```python
from datetime import datetime, timezone

# Good: timezone-aware
now = datetime.now(timezone.utc)
created_at = datetime(2024, 1, 23, 14, 30, 0, tzinfo=timezone.utc)

# Bad: naive datetime (ambiguous)
now = datetime.utcnow()  # Deprecated!
created_at = datetime(2024, 1, 23, 14, 30, 0)  # No timezone
```

### 2. Store and Transmit in ISO 8601

```python
# Good: unambiguous, sortable
timestamp = "2024-01-23T14:30:00Z"
timestamp = "2024-01-23T14:30:00+00:00"

# Avoid: format ambiguity
timestamp = "01/23/2024"  # US format? EU format?
timestamp = "23-01-2024"  # Ambiguous
```

### 3. Validate Timestamp Ranges

```python
from datetime import datetime, timezone


def validate_timestamp(value: int | str) -> datetime:
    """Validate and parse timestamp with sanity checks."""
    dt = parse_timestamp(value)
    
    # Reject future timestamps
    if dt > datetime.now(timezone.utc):
        raise ValueError(f"Timestamp {dt} is in the future")
    
    # Reject very old timestamps (before Unix epoch commonly used)
    min_date = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if dt < min_date:
        raise ValueError(f"Timestamp {dt} is before 1970")
    
    return dt
```

### 4. Handle Missing/Null Timestamps

```python
from datetime import datetime, timezone
from typing import Any


def safe_parse_timestamp(value: Any, default: datetime | None = None) -> datetime | None:
    """Safely parse timestamp with fallback."""
    if value is None:
        return default
    
    if value == "" or value == "null":
        return default
    
    try:
        return parse_timestamp(value)
    except (ValueError, TypeError):
        return default


# Usage
created = safe_parse_timestamp(record.get("created_at"), default=datetime.now(timezone.utc))
```

## Error Handling

```python
from stageflow.helpers import parse_timestamp


class TimestampParseError(Exception):
    """Raised when timestamp parsing fails."""
    
    def __init__(self, value: Any, format_hint: str | None = None) -> None:
        self.value = value
        self.format_hint = format_hint
        super().__init__(f"Cannot parse timestamp: {value}")


def strict_parse_timestamp(value: Any) -> datetime:
    """Parse timestamp with detailed error reporting."""
    try:
        return parse_timestamp(value)
    except ValueError as e:
        # Provide format hint based on value
        hint = None
        if isinstance(value, str):
            if "/" in value:
                hint = "Date contains '/', expected ISO 8601 format (YYYY-MM-DD)"
            elif len(value) > 20 and not value.endswith("Z"):
                hint = "Long timestamp missing timezone, append 'Z' for UTC"
        elif isinstance(value, int):
            if value > 10**18:
                hint = "Integer too large, expected seconds/milliseconds/microseconds"
        
        raise TimestampParseError(value, hint) from e
```

## Observability

Track timestamp handling metrics:

| Event | Description | Fields |
|-------|-------------|--------|
| `timestamp.parsed` | Successfully parsed | `format`, `value`, `result` |
| `timestamp.parse_failed` | Parsing failed | `value`, `error`, `hint` |
| `timestamp.normalized` | Converted to UTC | `original_tz`, `value` |

## Testing

```python
import pytest
from datetime import datetime, timezone
from stageflow.helpers import parse_timestamp, detect_unix_precision


def test_parse_iso_8601():
    """Test ISO 8601 parsing."""
    dt = parse_timestamp("2024-01-23T14:30:00Z")
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 23
    assert dt.tzinfo == timezone.utc


def test_parse_rfc_2822():
    """Test RFC 2822 parsing."""
    dt = parse_timestamp("Tue, 23 Jan 2024 14:30:00 GMT")
    assert dt.year == 2024
    assert dt.tzinfo == timezone.utc


def test_parse_unix_seconds():
    """Test Unix timestamp in seconds."""
    dt = parse_timestamp(1706020200)
    assert dt.year == 2024


def test_parse_unix_milliseconds():
    """Test Unix timestamp in milliseconds."""
    dt = parse_timestamp(1706020200000)
    assert dt.year == 2024


def test_detect_precision():
    """Test precision detection."""
    assert detect_unix_precision(1706020200) == "seconds"
    assert detect_unix_precision(1706020200000) == "milliseconds"
    assert detect_unix_precision(1706020200000000) == "microseconds"


def test_invalid_timestamp():
    """Test error on invalid input."""
    with pytest.raises(ValueError):
        parse_timestamp("not a timestamp")
```

## Related Guides

- [Transform Chain](../examples/transform-chain.md) - Sequential data transformations
- [Context Management](../advanced/context-management.md) - Managing temporal context
