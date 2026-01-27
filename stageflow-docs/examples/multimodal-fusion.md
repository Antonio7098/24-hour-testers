# Multimodal Fusion Cookbook

Multimodal pipelines process multiple data types—text, images, audio—and fuse them
into unified representations. This cookbook covers patterns for combining modalities
in Stageflow pipelines.

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Audio     │     │    Text     │     │   Image     │
│   Input     │     │   Input     │     │   Input     │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  STT Stage  │     │  Embed      │     │  Vision     │
│  (TRANSFORM)│     │  Stage      │     │  Stage      │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                  ┌─────────────────┐
                  │  Fusion Stage   │
                  │   (TRANSFORM)   │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  LLM Generation │
                  │    (GENERATE)   │
                  └─────────────────┘
```

## Basic Fusion Pattern

### Step 1: Define Modality Processors

```python
from dataclasses import dataclass
from typing import Any
from datetime import datetime, timezone

from stageflow.core import StageKind, StageOutput
from stageflow.stages.context import StageContext


@dataclass
class ModalityResult:
    """Result from a modality processor."""
    modality: str
    embedding: list[float] | None = None
    text: str | None = None
    metadata: dict[str, Any] | None = None
    processed_at: datetime | None = None


class AudioProcessorStage:
    """Process audio input via speech-to-text."""
    
    name = "audio_processor"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        audio_data = ctx.inputs.get("audio")
        
        if audio_data is None:
            return StageOutput.skip(reason="No audio input")
        
        # Process audio through STT
        transcript = await self._transcribe(audio_data)
        
        return StageOutput.ok(
            modality_result=ModalityResult(
                modality="audio",
                text=transcript["text"],
                metadata={
                    "duration_seconds": transcript["duration"],
                    "language": transcript["language"],
                    "confidence": transcript["confidence"],
                },
                processed_at=datetime.now(timezone.utc),
            ),
        )
    
    async def _transcribe(self, audio: bytes) -> dict:
        # Implementation: call STT service
        ...


class TextProcessorStage:
    """Process text input and generate embeddings."""
    
    name = "text_processor"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.inputs.get("text")
        
        if not text:
            return StageOutput.skip(reason="No text input")
        
        # Generate embedding
        embedding = await self._embed(text)
        
        return StageOutput.ok(
            modality_result=ModalityResult(
                modality="text",
                text=text,
                embedding=embedding,
                metadata={"token_count": len(text.split())},
                processed_at=datetime.now(timezone.utc),
            ),
        )
    
    async def _embed(self, text: str) -> list[float]:
        # Implementation: call embedding service
        ...


class ImageProcessorStage:
    """Process image input via vision model."""
    
    name = "image_processor"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        image_data = ctx.inputs.get("image")
        
        if image_data is None:
            return StageOutput.skip(reason="No image input")
        
        # Process image through vision model
        description = await self._describe_image(image_data)
        embedding = await self._embed_image(image_data)
        
        return StageOutput.ok(
            modality_result=ModalityResult(
                modality="image",
                text=description["caption"],
                embedding=embedding,
                metadata={
                    "width": description["width"],
                    "height": description["height"],
                    "objects_detected": description["objects"],
                },
                processed_at=datetime.now(timezone.utc),
            ),
        )
    
    async def _describe_image(self, image: bytes) -> dict:
        # Implementation: call vision model
        ...
    
    async def _embed_image(self, image: bytes) -> list[float]:
        # Implementation: call image embedding service
        ...
```

### Step 2: Fusion Stage

```python
from typing import Any
import numpy as np


class MultimodalFusionStage:
    """Fuse multiple modality results into unified representation."""
    
    name = "multimodal_fusion"
    kind = StageKind.TRANSFORM
    
    def __init__(
        self,
        fusion_strategy: str = "concatenate",
        normalize_embeddings: bool = True,
    ) -> None:
        """Initialize fusion stage.
        
        Args:
            fusion_strategy: How to combine embeddings
                - "concatenate": Stack embeddings
                - "average": Mean of embeddings
                - "weighted": Weighted combination
                - "attention": Cross-attention fusion
            normalize_embeddings: L2 normalize before fusion
        """
        self.fusion_strategy = fusion_strategy
        self.normalize = normalize_embeddings
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Collect modality results from upstream stages
        modality_results: list[ModalityResult] = []
        
        for key in ["audio_result", "text_result", "image_result"]:
            result = ctx.inputs.get(key)
            if result and isinstance(result, ModalityResult):
                modality_results.append(result)
        
        if not modality_results:
            return StageOutput.fail(
                error="No modality results to fuse",
                error_metadata={"modality_error": True},
            )
        
        # Fuse embeddings
        fused_embedding = self._fuse_embeddings(modality_results)
        
        # Combine text representations
        combined_text = self._combine_text(modality_results)
        
        # Emit fusion event
        ctx.event_sink.try_emit(
            "multimodal.fusion_completed",
            {
                "modalities": [r.modality for r in modality_results],
                "fusion_strategy": self.fusion_strategy,
                "embedding_dim": len(fused_embedding) if fused_embedding else 0,
            },
        )
        
        return StageOutput.ok(
            fused_embedding=fused_embedding,
            combined_text=combined_text,
            modalities_used=[r.modality for r in modality_results],
            modality_metadata={
                r.modality: r.metadata for r in modality_results
            },
        )
    
    def _fuse_embeddings(
        self, results: list[ModalityResult]
    ) -> list[float] | None:
        """Fuse embeddings from multiple modalities."""
        embeddings = [
            r.embedding for r in results
            if r.embedding is not None
        ]
        
        if not embeddings:
            return None
        
        # Convert to numpy for operations
        arrays = [np.array(e) for e in embeddings]
        
        # Normalize if configured
        if self.normalize:
            arrays = [a / np.linalg.norm(a) for a in arrays]
        
        # Apply fusion strategy
        if self.fusion_strategy == "concatenate":
            fused = np.concatenate(arrays)
        elif self.fusion_strategy == "average":
            # Pad to same length if needed
            max_len = max(len(a) for a in arrays)
            padded = [np.pad(a, (0, max_len - len(a))) for a in arrays]
            fused = np.mean(padded, axis=0)
        elif self.fusion_strategy == "weighted":
            # Weight by confidence or recency
            weights = self._compute_weights(results)
            max_len = max(len(a) for a in arrays)
            padded = [np.pad(a, (0, max_len - len(a))) for a in arrays]
            fused = np.average(padded, axis=0, weights=weights)
        else:
            raise ValueError(f"Unknown fusion strategy: {self.fusion_strategy}")
        
        return fused.tolist()
    
    def _combine_text(self, results: list[ModalityResult]) -> str:
        """Combine text from multiple modalities."""
        text_parts = []
        
        for result in results:
            if result.text:
                text_parts.append(f"[{result.modality.upper()}]: {result.text}")
        
        return "\n\n".join(text_parts)
    
    def _compute_weights(self, results: list[ModalityResult]) -> list[float]:
        """Compute fusion weights based on confidence/recency."""
        weights = []
        for r in results:
            confidence = r.metadata.get("confidence", 0.5) if r.metadata else 0.5
            weights.append(confidence)
        
        # Normalize weights
        total = sum(weights)
        return [w / total for w in weights]
```

## Parallel Processing Pattern

Process modalities in parallel for better performance:

```python
from stageflow.pipeline import Pipeline, UnifiedStageGraph


def build_multimodal_pipeline() -> Pipeline:
    """Build a pipeline that processes modalities in parallel."""
    
    return (
        Pipeline("multimodal_processing")
        .with_stage(AudioProcessorStage())
        .with_stage(TextProcessorStage())
        .with_stage(ImageProcessorStage())
        # Fusion depends on all three processors
        .with_stage(
            MultimodalFusionStage(fusion_strategy="weighted"),
            depends_on=["audio_processor", "text_processor", "image_processor"],
        )
        .with_stage(
            LLMGenerationStage(),
            depends_on=["multimodal_fusion"],
        )
    )
```

## Error Handling

Handle modality-specific errors gracefully:

```python
class RobustFusionStage:
    """Fusion stage with graceful degradation."""
    
    name = "robust_fusion"
    kind = StageKind.TRANSFORM
    
    def __init__(self, min_modalities: int = 1) -> None:
        self.min_modalities = min_modalities
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        # Collect results, tracking failures
        results = []
        failures = []
        
        for modality in ["audio", "text", "image"]:
            result_key = f"{modality}_result"
            error_key = f"{modality}_error"
            
            if result_key in ctx.inputs and ctx.inputs[result_key]:
                results.append(ctx.inputs[result_key])
            elif error_key in ctx.inputs:
                failures.append({
                    "modality": modality,
                    "error": ctx.inputs[error_key],
                })
        
        # Check minimum modalities requirement
        if len(results) < self.min_modalities:
            return StageOutput.fail(
                error=f"Insufficient modalities: {len(results)} < {self.min_modalities}",
                error_metadata={
                    "modality_count": len(results),
                    "failures": failures,
                },
            )
        
        # Log partial failures
        if failures:
            ctx.event_sink.try_emit(
                "multimodal.partial_failure",
                {
                    "successful_modalities": [r.modality for r in results],
                    "failed_modalities": failures,
                },
            )
        
        # Proceed with available modalities
        fused = self._fuse(results)
        
        return StageOutput.ok(
            fused_embedding=fused,
            modalities_used=[r.modality for r in results],
            partial_failure=bool(failures),
        )
```

## Cross-Modal Attention

For advanced fusion, use cross-modal attention:

```python
import torch
import torch.nn as nn


class CrossModalAttention(nn.Module):
    """Cross-modal attention for embedding fusion."""
    
    def __init__(self, embed_dim: int, num_heads: int = 8) -> None:
        super().__init__()
        self.attention = nn.MultiheadAttention(
            embed_dim=embed_dim,
            num_heads=num_heads,
            batch_first=True,
        )
        self.norm = nn.LayerNorm(embed_dim)
    
    def forward(
        self,
        query_modality: torch.Tensor,
        key_modalities: list[torch.Tensor],
    ) -> torch.Tensor:
        """Attend from query modality to all key modalities."""
        # Stack key modalities
        keys = torch.stack(key_modalities, dim=1)
        values = keys
        
        # Cross-attention
        attended, _ = self.attention(
            query_modality.unsqueeze(1),
            keys,
            values,
        )
        
        # Residual connection and normalization
        return self.norm(query_modality + attended.squeeze(1))


class AttentionFusionStage:
    """Fusion using cross-modal attention."""
    
    name = "attention_fusion"
    kind = StageKind.TRANSFORM
    
    def __init__(self, embed_dim: int = 768) -> None:
        self.attention = CrossModalAttention(embed_dim)
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        embeddings = {}
        
        for modality in ["audio", "text", "image"]:
            result = ctx.inputs.get(f"{modality}_result")
            if result and result.embedding:
                embeddings[modality] = torch.tensor(result.embedding)
        
        if len(embeddings) < 2:
            # Fall back to single modality
            single = list(embeddings.values())[0] if embeddings else None
            return StageOutput.ok(
                fused_embedding=single.tolist() if single is not None else None,
            )
        
        # Use text as query, attend to other modalities
        query = embeddings.get("text", list(embeddings.values())[0])
        keys = [e for m, e in embeddings.items() if m != "text"]
        
        fused = self.attention(query, keys)
        
        return StageOutput.ok(
            fused_embedding=fused.tolist(),
            fusion_method="cross_attention",
        )
```

## Real-Time Streaming

For real-time multimodal processing:

```python
from stageflow.helpers import StreamingBuffer, ChunkQueue, BackpressureMonitor


class StreamingMultimodalStage:
    """Process multimodal streams in real-time."""
    
    name = "streaming_multimodal"
    kind = StageKind.TRANSFORM
    
    def __init__(self, buffer_size: int = 10) -> None:
        self.audio_buffer = StreamingBuffer(max_chunks=buffer_size)
        self.video_buffer = StreamingBuffer(max_chunks=buffer_size)
        self.backpressure = BackpressureMonitor(
            high_watermark=0.8,
            low_watermark=0.3,
        )
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        results = []
        
        async for chunk in ctx.inputs["stream"]:
            # Check backpressure
            if self.backpressure.should_pause():
                ctx.event_sink.try_emit(
                    "multimodal.backpressure",
                    {"buffer_utilization": self.backpressure.utilization},
                )
                await self.backpressure.wait_for_capacity()
            
            # Route to appropriate buffer
            if chunk.modality == "audio":
                self.audio_buffer.add(chunk)
            elif chunk.modality == "video":
                self.video_buffer.add(chunk)
            
            # Process when both buffers have data
            if self.audio_buffer.has_data() and self.video_buffer.has_data():
                audio_chunk = self.audio_buffer.pop()
                video_chunk = self.video_buffer.pop()
                
                fused = await self._fuse_chunks(audio_chunk, video_chunk)
                results.append(fused)
        
        return StageOutput.ok(fused_chunks=results)
```

## Observability

Track multimodal processing metrics:

| Event | Description | Fields |
|-------|-------------|--------|
| `multimodal.modality_processed` | Single modality completed | `modality`, `duration_ms`, `success` |
| `multimodal.fusion_completed` | All modalities fused | `modalities`, `strategy`, `embedding_dim` |
| `multimodal.partial_failure` | Some modalities failed | `successful`, `failed` |
| `multimodal.backpressure` | Buffer pressure detected | `buffer_utilization` |

```python
# Example metrics dashboard queries
modality_success_rate = """
SELECT 
    modality,
    COUNT(*) FILTER (WHERE success) / COUNT(*) as success_rate
FROM multimodal_modality_processed
GROUP BY modality
"""

fusion_latency_p95 = """
SELECT 
    percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_ms
FROM multimodal_fusion_completed
WHERE timestamp > NOW() - INTERVAL '1 hour'
"""
```

## Testing

```python
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_fusion_with_all_modalities():
    """Test fusion when all modalities are available."""
    
    ctx = create_test_stage_context(
        inputs={
            "audio_result": ModalityResult(
                modality="audio",
                text="Hello from audio",
                embedding=[0.1] * 768,
            ),
            "text_result": ModalityResult(
                modality="text",
                text="Hello from text",
                embedding=[0.2] * 768,
            ),
            "image_result": ModalityResult(
                modality="image",
                text="A person waving",
                embedding=[0.3] * 768,
            ),
        }
    )
    
    stage = MultimodalFusionStage(fusion_strategy="average")
    result = await stage.execute(ctx)
    
    assert result.status == "completed"
    assert len(result.data["modalities_used"]) == 3
    assert result.data["fused_embedding"] is not None


@pytest.mark.asyncio
async def test_fusion_with_missing_modality():
    """Test graceful handling of missing modality."""
    
    ctx = create_test_stage_context(
        inputs={
            "text_result": ModalityResult(
                modality="text",
                text="Only text available",
                embedding=[0.2] * 768,
            ),
        }
    )
    
    stage = RobustFusionStage(min_modalities=1)
    result = await stage.execute(ctx)
    
    assert result.status == "completed"
    assert result.data["modalities_used"] == ["text"]
```

## Related Guides

- [Streaming Patterns](../guides/streaming.md) - Real-time audio/video processing
- [Transform Chain](./transform-chain.md) - Sequential transformations
- [Chunking Patterns](../advanced/chunking.md) - Large payload handling
