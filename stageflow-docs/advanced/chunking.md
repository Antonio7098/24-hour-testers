# Chunking Patterns

Large payloads—documents, audio files, datasets—often exceed memory limits or API
constraints. **Chunking** splits data into manageable pieces for parallel processing
and reassembles results. This guide covers chunking strategies and implementation.

## Chunking Strategies

| Strategy | Best For | Trade-offs |
|----------|----------|------------|
| Fixed-size | Binary data, uniform processing | May split semantic units |
| Semantic | Text, documents | Variable sizes, more complex |
| Recursive | Hierarchical data | Preserves structure, higher overhead |
| Sliding window | Context overlap needed | Duplication, larger total size |

## Fixed-Size Chunking

Split data into equal-sized pieces:

```python
from dataclasses import dataclass
from typing import Any, Iterator
import hashlib


@dataclass(frozen=True)
class Chunk:
    """A single chunk of data."""
    
    sequence: int
    data: bytes | str
    total_chunks: int
    checksum: str
    metadata: dict[str, Any] | None = None


def fixed_size_chunk(
    data: bytes | str,
    chunk_size: int = 16384,
    overlap: int = 0,
) -> Iterator[Chunk]:
    """Split data into fixed-size chunks.
    
    Args:
        data: Data to chunk
        chunk_size: Size of each chunk
        overlap: Bytes/chars to overlap between chunks
    
    Yields:
        Chunk objects with sequence numbers and checksums
    """
    is_bytes = isinstance(data, bytes)
    total_length = len(data)
    
    # Calculate total chunks
    step = chunk_size - overlap
    total_chunks = (total_length + step - 1) // step if step > 0 else 1
    
    sequence = 0
    position = 0
    
    while position < total_length:
        end = min(position + chunk_size, total_length)
        chunk_data = data[position:end]
        
        # Calculate checksum
        if is_bytes:
            checksum = hashlib.sha256(chunk_data).hexdigest()[:16]
        else:
            checksum = hashlib.sha256(chunk_data.encode()).hexdigest()[:16]
        
        yield Chunk(
            sequence=sequence,
            data=chunk_data,
            total_chunks=total_chunks,
            checksum=checksum,
            metadata={"start": position, "end": end},
        )
        
        sequence += 1
        position += step


# Example usage
data = b"x" * 100000  # 100KB
chunks = list(fixed_size_chunk(data, chunk_size=16384))
print(f"Split into {len(chunks)} chunks")
```

## Semantic Chunking

Split text at natural boundaries (sentences, paragraphs):

```python
import re
from dataclasses import dataclass
from typing import Iterator


@dataclass
class SemanticChunk:
    """A semantically meaningful chunk."""
    
    sequence: int
    text: str
    total_chunks: int
    token_count: int
    boundary_type: str  # "paragraph", "sentence", "heading"


def semantic_chunk(
    text: str,
    max_tokens: int = 512,
    overlap_sentences: int = 1,
) -> Iterator[SemanticChunk]:
    """Split text at semantic boundaries.
    
    Args:
        text: Text to chunk
        max_tokens: Maximum tokens per chunk (approximate)
        overlap_sentences: Sentences to overlap between chunks
    
    Yields:
        SemanticChunk objects
    """
    # Split into paragraphs first
    paragraphs = re.split(r'\n\s*\n', text.strip())
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for para in paragraphs:
        # Estimate tokens (rough: 4 chars per token)
        para_tokens = len(para) // 4
        
        if current_tokens + para_tokens > max_tokens and current_chunk:
            # Emit current chunk
            chunk_text = "\n\n".join(current_chunk)
            chunks.append({
                "text": chunk_text,
                "tokens": current_tokens,
                "boundary": "paragraph",
            })
            
            # Start new chunk with overlap
            if overlap_sentences > 0:
                sentences = _split_sentences(current_chunk[-1])
                overlap_text = " ".join(sentences[-overlap_sentences:])
                current_chunk = [overlap_text, para]
                current_tokens = len(overlap_text) // 4 + para_tokens
            else:
                current_chunk = [para]
                current_tokens = para_tokens
        else:
            current_chunk.append(para)
            current_tokens += para_tokens
    
    # Emit final chunk
    if current_chunk:
        chunks.append({
            "text": "\n\n".join(current_chunk),
            "tokens": current_tokens,
            "boundary": "paragraph",
        })
    
    # Convert to SemanticChunk objects
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        yield SemanticChunk(
            sequence=i,
            text=chunk["text"],
            total_chunks=total,
            token_count=chunk["tokens"],
            boundary_type=chunk["boundary"],
        )


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    return re.split(r'(?<=[.!?])\s+', text)
```

## Recursive Chunking

For hierarchical documents (Markdown, HTML):

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HierarchicalChunk:
    """Chunk preserving document hierarchy."""
    
    sequence: int
    content: str
    level: int  # Heading level (1-6) or 0 for body
    path: list[str]  # Hierarchy path
    total_chunks: int
    children: list["HierarchicalChunk"] = field(default_factory=list)


def recursive_chunk_markdown(
    markdown: str,
    max_tokens: int = 1024,
) -> list[HierarchicalChunk]:
    """Recursively chunk Markdown preserving heading hierarchy.
    
    Args:
        markdown: Markdown text
        max_tokens: Maximum tokens per leaf chunk
    
    Returns:
        List of hierarchical chunks
    """
    import re
    
    # Parse headings and content
    sections = _parse_markdown_sections(markdown)
    
    chunks = []
    sequence = [0]  # Mutable counter
    
    def process_section(section: dict, path: list[str], level: int) -> HierarchicalChunk:
        content = section.get("content", "")
        heading = section.get("heading", "")
        current_path = path + [heading] if heading else path
        
        # Estimate tokens
        tokens = len(content) // 4
        
        if tokens <= max_tokens:
            # Leaf chunk
            chunk = HierarchicalChunk(
                sequence=sequence[0],
                content=content,
                level=level,
                path=current_path,
                total_chunks=0,  # Updated later
            )
            sequence[0] += 1
            chunks.append(chunk)
        else:
            # Split content further
            sub_chunks = list(semantic_chunk(content, max_tokens=max_tokens))
            for sub in sub_chunks:
                chunk = HierarchicalChunk(
                    sequence=sequence[0],
                    content=sub.text,
                    level=level,
                    path=current_path,
                    total_chunks=0,
                )
                sequence[0] += 1
                chunks.append(chunk)
        
        # Process children
        for child in section.get("children", []):
            process_section(child, current_path, level + 1)
        
        return chunks[-1] if chunks else None
    
    for section in sections:
        process_section(section, [], 0)
    
    # Update total_chunks
    for chunk in chunks:
        chunk.total_chunks = len(chunks)
    
    return chunks


def _parse_markdown_sections(markdown: str) -> list[dict]:
    """Parse Markdown into hierarchical sections."""
    import re
    
    lines = markdown.split("\n")
    sections = []
    current = {"content": [], "children": []}
    stack = [current]
    
    for line in lines:
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        
        if heading_match:
            level = len(heading_match.group(1))
            heading = heading_match.group(2)
            
            new_section = {
                "heading": heading,
                "level": level,
                "content": [],
                "children": [],
            }
            
            # Find parent
            while len(stack) > level:
                completed = stack.pop()
                completed["content"] = "\n".join(completed["content"])
            
            stack[-1]["children"].append(new_section)
            stack.append(new_section)
        else:
            stack[-1]["content"].append(line)
    
    # Finalize content
    while stack:
        section = stack.pop()
        if isinstance(section["content"], list):
            section["content"] = "\n".join(section["content"])
    
    return current["children"]
```

## Chunk Assembler

Reassemble chunks with validation:

```python
from dataclasses import dataclass
from typing import Any
import hashlib


@dataclass
class AssemblyResult:
    """Result of chunk assembly."""
    
    success: bool
    data: bytes | str | None
    missing_chunks: list[int]
    checksum_failures: list[int]
    total_chunks: int


class ChunkAssembler:
    """Reassemble chunks into original data."""
    
    def __init__(
        self,
        validate_checksums: bool = True,
        fail_on_missing: bool = True,
    ) -> None:
        self.validate_checksums = validate_checksums
        self.fail_on_missing = fail_on_missing
        self._chunks: dict[int, Chunk] = {}
        self._total_chunks: int | None = None
    
    def add_chunk(self, chunk: Chunk) -> None:
        """Add a chunk to the assembler."""
        self._chunks[chunk.sequence] = chunk
        
        if self._total_chunks is None:
            self._total_chunks = chunk.total_chunks
        elif self._total_chunks != chunk.total_chunks:
            raise ValueError(
                f"Inconsistent total_chunks: {self._total_chunks} vs {chunk.total_chunks}"
            )
    
    def assemble(self) -> AssemblyResult:
        """Assemble all chunks into original data."""
        if self._total_chunks is None:
            return AssemblyResult(
                success=False,
                data=None,
                missing_chunks=[],
                checksum_failures=[],
                total_chunks=0,
            )
        
        missing = []
        checksum_failures = []
        
        # Check for missing chunks
        for i in range(self._total_chunks):
            if i not in self._chunks:
                missing.append(i)
        
        if missing and self.fail_on_missing:
            return AssemblyResult(
                success=False,
                data=None,
                missing_chunks=missing,
                checksum_failures=[],
                total_chunks=self._total_chunks,
            )
        
        # Assemble in order
        parts = []
        is_bytes = isinstance(self._chunks[0].data, bytes) if self._chunks else True
        
        for i in range(self._total_chunks):
            if i in self._chunks:
                chunk = self._chunks[i]
                
                # Validate checksum
                if self.validate_checksums:
                    if is_bytes:
                        computed = hashlib.sha256(chunk.data).hexdigest()[:16]
                    else:
                        computed = hashlib.sha256(chunk.data.encode()).hexdigest()[:16]
                    
                    if computed != chunk.checksum:
                        checksum_failures.append(i)
                
                parts.append(chunk.data)
            else:
                # Fill missing with placeholder
                parts.append(b"" if is_bytes else "")
        
        if checksum_failures:
            return AssemblyResult(
                success=False,
                data=None,
                missing_chunks=missing,
                checksum_failures=checksum_failures,
                total_chunks=self._total_chunks,
            )
        
        # Combine parts
        if is_bytes:
            data = b"".join(parts)
        else:
            data = "".join(parts)
        
        return AssemblyResult(
            success=True,
            data=data,
            missing_chunks=missing,
            checksum_failures=[],
            total_chunks=self._total_chunks,
        )
    
    def is_complete(self) -> bool:
        """Check if all chunks have been received."""
        if self._total_chunks is None:
            return False
        return len(self._chunks) == self._total_chunks
```

## Chunking Stage

Integrate chunking into pipelines:

```python
from stageflow.core import StageKind, StageOutput
from stageflow.stages.context import StageContext


class ChunkingStage:
    """Stage that chunks large payloads for parallel processing."""
    
    name = "chunking"
    kind = StageKind.TRANSFORM
    
    def __init__(
        self,
        chunk_size: int = 16384,
        strategy: str = "fixed_size",
        overlap: int = 0,
        enforce_size_limit: bool = True,
    ) -> None:
        self.chunk_size = chunk_size
        self.strategy = strategy
        self.overlap = overlap
        self.enforce_size_limit = enforce_size_limit
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        data = ctx.inputs["data"]
        
        # Choose chunking strategy
        if self.strategy == "fixed_size":
            chunks = list(fixed_size_chunk(
                data,
                chunk_size=self.chunk_size,
                overlap=self.overlap,
            ))
        elif self.strategy == "semantic":
            chunks = list(semantic_chunk(
                data,
                max_tokens=self.chunk_size // 4,
                overlap_sentences=1,
            ))
        else:
            return StageOutput.fail(
                error=f"Unknown chunking strategy: {self.strategy}"
            )
        
        # Validate size limits
        if self.enforce_size_limit:
            oversized = [
                c for c in chunks
                if len(c.data if hasattr(c, 'data') else c.text) > self.chunk_size * 1.1
            ]
            if oversized:
                ctx.event_sink.try_emit(
                    "chunking.size_violation",
                    {"oversized_count": len(oversized)},
                )
                return StageOutput.fail(
                    error=f"{len(oversized)} chunks exceed size limit"
                )
        
        ctx.event_sink.try_emit(
            "chunking.completed",
            {
                "strategy": self.strategy,
                "total_chunks": len(chunks),
                "original_size": len(data),
            },
        )
        
        return StageOutput.ok(
            chunks=chunks,
            total_chunks=len(chunks),
            strategy=self.strategy,
        )


class ChunkAssemblerStage:
    """Stage that reassembles processed chunks."""
    
    name = "chunk_assembler"
    kind = StageKind.TRANSFORM
    
    def __init__(
        self,
        validate_checksums: bool = True,
        fail_on_missing: bool = True,
    ) -> None:
        self.validate_checksums = validate_checksums
        self.fail_on_missing = fail_on_missing
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        chunks = ctx.inputs["processed_chunks"]
        
        assembler = ChunkAssembler(
            validate_checksums=self.validate_checksums,
            fail_on_missing=self.fail_on_missing,
        )
        
        for chunk in chunks:
            assembler.add_chunk(chunk)
        
        result = assembler.assemble()
        
        if not result.success:
            ctx.event_sink.try_emit(
                "chunking.assembly_failed",
                {
                    "missing_chunks": result.missing_chunks,
                    "checksum_failures": result.checksum_failures,
                },
            )
            return StageOutput.fail(
                error="Chunk assembly failed",
                error_metadata={
                    "missing": result.missing_chunks,
                    "checksum_failures": result.checksum_failures,
                },
            )
        
        return StageOutput.ok(
            assembled_data=result.data,
            total_chunks=result.total_chunks,
        )
```

## Parallel Chunk Processing

Process chunks concurrently:

```python
import asyncio
from typing import Any, Callable


async def process_chunks_parallel(
    chunks: list[Chunk],
    processor: Callable[[Chunk], Any],
    max_concurrency: int = 10,
) -> list[Any]:
    """Process chunks in parallel with concurrency limit.
    
    Args:
        chunks: Chunks to process
        processor: Async function to process each chunk
        max_concurrency: Maximum concurrent processors
    
    Returns:
        List of processed results in original order
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def process_with_limit(chunk: Chunk) -> tuple[int, Any]:
        async with semaphore:
            result = await processor(chunk)
            return (chunk.sequence, result)
    
    # Process all chunks concurrently
    tasks = [process_with_limit(chunk) for chunk in chunks]
    results = await asyncio.gather(*tasks)
    
    # Sort by sequence number
    results.sort(key=lambda x: x[0])
    
    return [r[1] for r in results]
```

## Testing

```python
import pytest


def test_fixed_size_chunking():
    """Test fixed-size chunk generation."""
    data = b"x" * 100
    chunks = list(fixed_size_chunk(data, chunk_size=30))
    
    assert len(chunks) == 4
    assert all(c.checksum for c in chunks)
    assert chunks[0].total_chunks == 4


def test_chunk_assembly():
    """Test chunk reassembly."""
    original = b"Hello, World! This is a test."
    chunks = list(fixed_size_chunk(original, chunk_size=10))
    
    assembler = ChunkAssembler()
    for chunk in chunks:
        assembler.add_chunk(chunk)
    
    result = assembler.assemble()
    
    assert result.success
    assert result.data == original


def test_missing_chunk_detection():
    """Test detection of missing chunks."""
    original = b"Hello, World!"
    chunks = list(fixed_size_chunk(original, chunk_size=5))
    
    assembler = ChunkAssembler(fail_on_missing=True)
    # Skip chunk 1
    for chunk in chunks:
        if chunk.sequence != 1:
            assembler.add_chunk(chunk)
    
    result = assembler.assemble()
    
    assert not result.success
    assert 1 in result.missing_chunks


def test_semantic_chunking():
    """Test semantic text chunking."""
    text = """
    First paragraph with some content.
    
    Second paragraph with more content.
    
    Third paragraph to ensure multiple chunks.
    """
    
    chunks = list(semantic_chunk(text, max_tokens=20))
    
    assert len(chunks) >= 2
    assert all(c.boundary_type == "paragraph" for c in chunks)
```

## Related Guides

- [Transform Chain](../examples/transform-chain.md) - Sequential transformations
- [Multimodal Fusion](../examples/multimodal-fusion.md) - Processing multiple data types
- [Streaming Patterns](./streaming.md) - Real-time data processing
