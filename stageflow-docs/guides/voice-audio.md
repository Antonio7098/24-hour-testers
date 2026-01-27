# Voice & Real-Time Audio Guide

This guide covers building voice pipelines with STT, TTS, streaming, and real-time audio handling in Stageflow.

## Overview

Voice pipelines typically involve:
- **STT (Speech-to-Text)**: Converting audio to text
- **Processing**: LLM or business logic on the transcript
- **TTS (Text-to-Speech)**: Converting response to audio
- **Streaming**: Real-time audio chunk handling

Stageflow provides:
- `AudioPorts` for typed audio service injection
- Streaming primitives for chunk handling
- Mock providers for testing without real APIs

## Audio Ports

Use `AudioPorts` to inject audio services into stages:

```python
from stageflow.stages.ports import AudioPorts, create_audio_ports

# Create ports with your providers
ports = create_audio_ports(
    stt_client=my_stt_client,
    tts_client=my_tts_client,
    audio_callback=handle_audio_output,
)

# Use in stage context
ctx = StageContext(
    snapshot=snapshot,
    inputs=create_stage_inputs(snapshot, ports=ports),
)
```

### Accessing Ports in Stages

```python
class STTStage:
    name = "stt"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get audio ports
        ports = ctx.inputs.ports
        if not isinstance(ports, AudioPorts):
            return StageOutput.fail(error="AudioPorts required")

        # Use STT client
        audio_data = ctx.snapshot.extensions.get("audio_input")
        transcript = await ports.stt_client.transcribe(audio_data)

        return StageOutput.ok(
            transcript=transcript.text,
            confidence=transcript.confidence,
        )
```

## Streaming Primitives

### Chunk Queue with Backpressure

Handle streaming audio with backpressure support:

```python
from stageflow.helpers import ChunkQueue, AudioChunk, BackpressureMonitor

# Create queue with max size
queue = ChunkQueue[AudioChunk](max_size=100)

# Producer (e.g., microphone input)
async def audio_producer():
    async for raw_chunk in microphone.stream():
        chunk = AudioChunk(
            data=raw_chunk,
            sample_rate=16000,
            timestamp_ms=get_timestamp(),
        )
        await queue.put(chunk)

    await queue.close()

# Consumer (e.g., STT processor)
async def audio_consumer():
    async for chunk in queue:
        await process_chunk(chunk)

# Monitor backpressure and emit telemetry
queue = ChunkQueue(event_emitter=lambda event, attrs: ctx.emit_event(event, attrs))
if queue.monitor.should_throttle():
    await asyncio.sleep(0.01)  # Slow down producer

print(queue.monitor.stats.to_dict())
```

### Streaming Buffer

Buffer chunks for jitter smoothing:

```python
from stageflow.helpers import StreamingBuffer, AudioChunk

# Create buffer with target duration
buffer = StreamingBuffer(
    target_duration_ms=200,  # Buffer 200ms before starting playback
    max_duration_ms=2000,    # Maximum buffer size
    sample_rate=16000,
    event_emitter=lambda event, attrs: ctx.emit_event(event, attrs),
)

# Add incoming chunks
for chunk in incoming_chunks:
    dropped = buffer.add_chunk(chunk)
    if dropped > 0:
        print(f"Dropped {dropped} bytes due to buffer overflow")

# Read when ready
if buffer.is_ready():
    # Read 20ms of audio for playback
    audio_data = buffer.read(duration_ms=20)
    play_audio(audio_data)

# Get buffer stats
print(buffer.stats)
```

### Audio Chunk Management

```python
from stageflow.helpers import AudioChunk, AudioFormat

# Create a chunk
chunk = AudioChunk(
    data=raw_audio_bytes,
    sample_rate=16000,
    channels=1,
    format=AudioFormat.PCM_16,
    timestamp_ms=150.5,
    sequence=42,
    is_final=False,
)

# Get duration
print(f"Chunk duration: {chunk.duration_ms}ms")

# Serialize for transport
chunk_dict = chunk.to_dict()  # Data is base64 encoded

# Deserialize
restored = AudioChunk.from_dict(chunk_dict)
```

## Voice Pipeline Pattern

### Basic Voice Chat Pipeline

```python
from stageflow import Pipeline, StageKind

pipeline = (
    Pipeline()
    # 1. Transcribe audio to text
    .with_stage("stt", STTStage, StageKind.TRANSFORM)

    # 2. Fetch conversation memory
    .with_stage("memory", MemoryFetchStage(store), StageKind.ENRICH,
                dependencies=("stt",))

    # 3. Generate response with LLM
    .with_stage("llm", LLMStage, StageKind.TRANSFORM,
                dependencies=("stt", "memory"))

    # 4. Convert response to speech
    .with_stage("tts", TTSStage, StageKind.TRANSFORM,
                dependencies=("llm",))

    # 5. Save to memory
    .with_stage("save_memory", MemoryWriteStage(store), StageKind.WORK,
                dependencies=("llm",))
)
```

### STT Stage Implementation

```python
class STTStage:
    """Speech-to-Text stage."""

    name = "stt"
    kind = StageKind.TRANSFORM

    def __init__(self, stt_provider):
        self._stt = stt_provider

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get audio from context
        audio_data = ctx.snapshot.extensions.get("audio_input")
        if not audio_data:
            return StageOutput.skip(reason="No audio input")

        # Decode if base64
        if isinstance(audio_data, str):
            import base64
            audio_data = base64.b64decode(audio_data)

        try:
            result = await self._stt.transcribe(
                audio_data,
                language=ctx.snapshot.extensions.get("language", "en"),
            )

            from stageflow.helpers import STTResponse

            stt = STTResponse(
                text=result.text,
                confidence=result.confidence,
                duration_ms=result.duration_ms,
                provider=getattr(result, "provider", "unknown"),
                model=getattr(result, "model", "unknown"),
            )

            return StageOutput.ok(
                transcript=stt.text,
                stt=stt.to_dict(),
            )
        except Exception as e:
            return StageOutput.fail(error=f"STT failed: {e}")
```

### TTS Stage Implementation

```python
class TTSStage:
    """Text-to-Speech stage."""

    name = "tts"
    kind = StageKind.TRANSFORM

    def __init__(self, tts_provider):
        self._tts = tts_provider

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get response text from LLM stage
        response_text = ctx.inputs.get_from("llm", "response")
        if not response_text:
            return StageOutput.skip(reason="No response text")

        try:
            audio_data = await self._tts.synthesize(
                response_text,
                voice=ctx.snapshot.extensions.get("voice", "default"),
            )

            # Encode for transport
            import base64
            audio_b64 = base64.b64encode(audio_data).decode("ascii")

            from stageflow.helpers import TTSResponse

            tts = TTSResponse(
                audio=audio_data,
                duration_ms=len(audio_data) / (16000 * 2) * 1000,
                provider=getattr(self._tts, "provider_name", "custom"),
                model=getattr(self._tts, "voice", "default"),
            )

            return StageOutput.ok(
                audio=audio_b64,
                duration_ms=tts.duration_ms,
                text=response_text,
                tts=tts.to_dict(),
            )
        except Exception as e:
            return StageOutput.fail(error=f"TTS failed: {e}")
```

### Streaming TTS Stage

For real-time audio output:

```python
class StreamingTTSStage:
    """Streaming Text-to-Speech stage."""

    name = "streaming_tts"
    kind = StageKind.TRANSFORM

    def __init__(self, tts_provider, chunk_callback):
        self._tts = tts_provider
        self._callback = chunk_callback

    async def execute(self, ctx: StageContext) -> StageOutput:
        response_text = ctx.inputs.get_from("llm", "response")
        if not response_text:
            return StageOutput.skip(reason="No response text")

        chunks_sent = 0
        total_bytes = 0

        try:
            async for chunk in self._tts.stream(response_text):
                # Send chunk to playback
                await self._callback(chunk)
                chunks_sent += 1
                total_bytes += len(chunk.data)

            return StageOutput.ok(
                chunks_sent=chunks_sent,
                total_bytes=total_bytes,
                text=response_text,
            )
        except Exception as e:
            return StageOutput.fail(error=f"Streaming TTS failed: {e}")
```

## Observability Hooks

- Wire `ChunkQueue` and `StreamingBuffer` telemetry emitters to your pipeline event sink to track drops, throttle windows, and underruns.
- Use `BufferedExporter(on_overflow=...)` on any analytics pipeline that batches streaming metrics (e.g., voice quality scores).
- Attach `ToolRegistry.parse_and_resolve()` to voice agents so tool requests from speech can be validated before execution.

## Binary-Safe Logging

Audio data can corrupt logs. Use safe encoding:

```python
from stageflow.helpers import encode_audio_for_logging

# Safe logging
audio_repr = encode_audio_for_logging(audio_bytes, max_bytes=100)
logger.info(f"Received audio: {audio_repr}")
# Output: "Received audio: <audio:32000B,sample:SGVsbG8gV29y...>"
```

### Stage Output with Audio

```python
# Don't put raw bytes in output data
# Bad: StageOutput.ok(audio=raw_audio_bytes)

# Good: Base64 encode
import base64
StageOutput.ok(
    audio=base64.b64encode(raw_audio_bytes).decode("ascii"),
    audio_size=len(raw_audio_bytes),
)
```

## Testing Voice Pipelines

### Mock Providers

Test without real STT/TTS APIs:

```python
from stageflow.helpers import MockSTTProvider, MockTTSProvider

# Create mock STT
stt = MockSTTProvider(
    transcriptions=["Hello", "How are you?", "Goodbye"],
    latency_ms=100,
)

# Create mock TTS
tts = MockTTSProvider(
    sample_rate=16000,
    latency_ms=50,
)

# Use in tests
async def test_voice_pipeline():
    result = await stt.transcribe(fake_audio_bytes)
    assert result.text == "Hello"

    audio = await tts.synthesize("Hello back!")
    assert len(audio) > 0
```

### Deterministic Audio Testing

```python
# Mock STT with audio hash mapping
stt = MockSTTProvider(
    audio_map={
        "abc123": "Hello world",  # Audio hash -> transcription
        "def456": "Goodbye",
    }
)

# Same audio always produces same transcription
result1 = await stt.transcribe(audio_with_hash_abc123)
result2 = await stt.transcribe(audio_with_hash_abc123)
assert result1.text == result2.text == "Hello world"
```

### Testing Streaming

```python
from stageflow.helpers import ChunkQueue, AudioChunk

async def test_streaming_backpressure():
    queue = ChunkQueue[AudioChunk](max_size=10, drop_on_overflow=True)

    # Fill queue
    for i in range(15):
        chunk = AudioChunk(data=b"x" * 100, sequence=i)
        await queue.put(chunk)

    # Check backpressure stats
    assert queue.monitor.stats.dropped_items == 5
    assert len(queue) == 10
```

## Performance Considerations

### Latency Optimization

```python
# Bad: Sequential STT then TTS
result = await stt.transcribe(audio)
text = await llm.complete(result.text)
audio = await tts.synthesize(text)

# Good: Use pipeline for parallel where possible
pipeline = (
    Pipeline()
    .with_stage("stt", STTStage, StageKind.TRANSFORM)
    # Memory fetch can run in parallel with STT if it doesn't need transcript
    .with_stage("prefetch_memory", MemoryFetchStage, StageKind.ENRICH)
    .with_stage("llm", LLMStage, dependencies=("stt", "prefetch_memory"))
    .with_stage("tts", TTSStage, dependencies=("llm",))
)
```

### Buffer Sizing

```python
# For voice chat (low latency priority)
buffer = StreamingBuffer(
    target_duration_ms=100,  # Start playback after 100ms
    max_duration_ms=500,     # Drop old audio if too far behind
    event_emitter=lambda event, attrs: ctx.emit_event(event, attrs),
)

# For audio recording (quality priority)
buffer = StreamingBuffer(
    target_duration_ms=500,   # More buffering OK
    max_duration_ms=5000,     # Keep more history
    event_emitter=lambda event, attrs: ctx.emit_event(event, attrs),
)
```

### Chunk Size Selection

```python
# Small chunks = lower latency, more overhead
chunk_size = 1024  # ~32ms at 16kHz mono 16-bit

# Large chunks = higher latency, less overhead
chunk_size = 8192  # ~256ms at 16kHz mono 16-bit

# Typical voice chat balance
chunk_size = 3200  # 100ms at 16kHz mono 16-bit
```

## Error Handling

### Graceful Degradation

```python
class RobustSTTStage:
    name = "stt"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        audio = ctx.snapshot.extensions.get("audio_input")

        try:
            result = await self._stt.transcribe(audio)
            return StageOutput.ok(transcript=result.text)
        except TimeoutError:
            # Log and continue with empty transcript
            logger.warning("STT timeout, continuing with empty transcript")
            return StageOutput.ok(transcript="", stt_timeout=True)
        except Exception as e:
            # Fail the stage
            return StageOutput.fail(error=f"STT error: {e}")
```

### Retry with Backoff

```python
async def transcribe_with_retry(stt, audio, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await stt.transcribe(audio)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## Next Steps

- [Streaming Guide](streaming.md) - Advanced streaming patterns
- [Tools Guide](tools.md) - Voice-triggered tool execution
- [Testing Guide](../advanced/testing.md) - Comprehensive testing strategies
