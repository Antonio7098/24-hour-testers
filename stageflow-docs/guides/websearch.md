# Web Search Module

The `websearch` module provides async web fetching, HTML content extraction with structure preservation, and navigation capabilities for agents to explore web pages.

## Installation

The websearch module requires optional dependencies:

```bash
pip install stageflow-core[websearch]
```

Or install dependencies directly:

```bash
pip install httpx selectolax
```

> **Note:** `selectolax` provides the high-performance HTML parser used by
> `DefaultContentExtractor` and `PageNavigator`. If it isn't installed, Stageflow
> automatically falls back to regex-based extractors/navigators so everything still
> works, but parsing is slower and navigation detection is less precise. Installing
> `selectolax` is strongly recommended for production workloads.

## Quick Start

```python
import asyncio
from stageflow.websearch import WebSearchClient

async def main():
    async with WebSearchClient() as client:
        # Fetch a single page
        page = await client.fetch("https://example.com")
        
        print(f"Title: {page.title}")
        print(f"Content:\n{page.markdown}")
        print(f"Links found: {len(page.links)}")

asyncio.run(main())
```

### Client Lifecycle & Resource Management

- **Short-lived scripts/tests**: Use `async with WebSearchClient()` so the underlying
  `httpx.AsyncClient` is opened/closed automatically.
- **Batch jobs and agents**: Create a single `WebSearchClient` and reuse it for the
  entire run to take advantage of connection pooling. Call `await client.close()`
  during shutdown to release sockets.
- **Custom fetchers**: When providing your own `Fetcher`, the lifecycle is controlled
  by that instance. Only call `client.close()` if your code created the fetcher; this
  avoids double-closing shared resources.

```python
client = WebSearchClient()
try:
    pages = await client.fetch_many(urls, concurrency=8)
    # ... process pages ...
finally:
    await client.close()
```

## Core Concepts

### WebPage

The `WebPage` dataclass is the primary result type, containing:

- **`url`**: Original requested URL
- **`final_url`**: Final URL after redirects
- **`status_code`**: HTTP status code
- **`markdown`**: Structured content as markdown (preserves headings, lists, links)
- **`plain_text`**: Plain text content without formatting
- **`metadata`**: Page metadata (title, description, language, etc.)
- **`links`**: Extracted links from the page
- **`navigation_actions`**: Available navigation actions for agents
- **`pagination`**: Pagination info if detected
- **`word_count`**: Number of words in content

```python
page = await client.fetch("https://example.com/article")

# Access structured content
print(page.markdown)  # "# Article Title\n\nFirst paragraph..."

# Access metadata
print(page.metadata.title)
print(page.metadata.description)
print(page.metadata.author)

# Work with links
for link in page.links[:5]:
    print(f"- [{link.text}]({link.url})")

# Filter links
internal_links = page.internal_links
external_links = page.external_links
```

### Structure Preservation

The extractor preserves semantic structure from HTML:

| HTML Element | Markdown Output |
|--------------|-----------------|
| `<h1>` - `<h6>` | `#` - `######` |
| `<ul>/<li>` | `- item` |
| `<ol>/<li>` | `1. item` |
| `<strong>/<b>` | `**bold**` |
| `<em>/<i>` | `_italic_` |
| `<code>` | `` `code` `` |
| `<pre><code>` | ` ```code block``` ` |
| `<blockquote>` | `> quote` |
| `<a href>` | `[text](url)` |
| `<table>` | Markdown table |

Example:

```python
html = """
<article>
    <h1>Getting Started</h1>
    <p>This guide covers <strong>important</strong> concepts.</p>
    <h2>Prerequisites</h2>
    <ul>
        <li>Python 3.11+</li>
        <li>Basic asyncio knowledge</li>
    </ul>
</article>
"""

page = client.extract_content(html)
print(page.markdown)
# Output:
# # Getting Started
#
# This guide covers **important** concepts.
#
# ## Prerequisites
#
# - Python 3.11+
# - Basic asyncio knowledge
```

## Batch Fetching

Fetch multiple URLs concurrently with automatic parallelization:

```python
urls = [
    "https://example.com/page1",
    "https://example.com/page2",
    "https://example.com/page3",
]

# Fetch all pages concurrently (default: 5 concurrent requests)
pages = await client.fetch_many(urls)

# Custom concurrency limit
pages = await client.fetch_many(urls, concurrency=10)

# Results maintain URL order
for url, page in zip(urls, pages):
    if page.success:
        print(f"{url}: {page.word_count} words")
    else:
        print(f"{url}: Error - {page.error}")
```

## Navigation

### Pagination Following

Automatically follow pagination links:

```python
# Fetch page and follow "Next" links
pages = await client.fetch_with_navigation(
    "https://example.com/articles",
    max_pages=10,
    follow_pagination=True,
)

for i, page in enumerate(pages, 1):
    print(f"Page {i}: {page.title}")
```

### Crawling

Crawl a site by following links:

```python
# Basic crawl
pages = await client.crawl(
    "https://example.com",
    max_pages=50,
    max_depth=3,
    same_domain_only=True,
)

# With link filter
def articles_only(link):
    return "/article/" in link.url or "/blog/" in link.url

pages = await client.crawl(
    "https://example.com",
    max_pages=20,
    link_filter=articles_only,
)
```

### Navigation Actions

Pages expose available navigation actions for agents:

```python
page = await client.fetch("https://example.com")

for action in page.navigation_actions:
    print(f"[{action.action_type}] {action.label}: {action.url}")

# Example output:
# [pagination] Next page: https://example.com/page/2
# [nav_link] About: https://example.com/about
# [content_link] Related Article: https://example.com/article/123
```

### Pagination Info

Access pagination details:

```python
page = await client.fetch("https://example.com/results?page=2")

if page.pagination:
    print(f"Current page: {page.pagination.current_page}")
    print(f"Total pages: {page.pagination.total_pages}")
    
    if page.pagination.has_next:
        next_page = await client.fetch(page.pagination.next_url)
    
    if page.pagination.has_prev:
        prev_page = await client.fetch(page.pagination.prev_url)
```

## Configuration

### WebSearchConfig

```python
from stageflow.websearch import (
    WebSearchClient,
    WebSearchConfig,
    FetchConfig,
    ExtractionConfig,
    NavigationConfig,
)

config = WebSearchConfig(
    # Fetch settings
    fetch=FetchConfig(
        timeout=30.0,
        max_retries=3,
        retry_delay=1.0,
        user_agent="MyBot/1.0",
        follow_redirects=True,
        max_content_length=10_000_000,
    ),
    # Extraction settings
    extraction=ExtractionConfig(
        preserve_headings=True,
        preserve_lists=True,
        preserve_links=True,
        preserve_emphasis=True,
        preserve_code=True,
        preserve_tables=True,
        max_link_text_length=100,
    ),
    # Navigation settings
    navigation=NavigationConfig(
        max_actions=20,
    ),
    # Client settings
    max_concurrent=5,
    auto_extract=True,
    auto_navigate=True,
)

client = WebSearchClient(config)
```

### Custom Selectors

Target specific content areas:

```python
# Extract only article content
page = await client.fetch(
    "https://example.com/article",
    selector="article.post-content",
)

# Extract main content ignoring sidebar
page = await client.fetch(
    "https://example.com",
    selector="main",
)
```

## Observability

### Callbacks

Monitor fetch and extraction operations:

```python
def on_fetch_start(url: str, request_id: str) -> None:
    print(f"[{request_id}] Starting fetch: {url}")

def on_fetch_complete(
    url: str,
    request_id: str,
    status: int,
    duration_ms: float,
    size: int,
    from_cache: bool,
) -> None:
    print(f"[{request_id}] Completed: {url} ({status}) in {duration_ms:.1f}ms")

def on_fetch_error(
    url: str,
    request_id: str,
    error: str,
    duration_ms: float,
    retryable: bool,
) -> None:
    print(f"[{request_id}] Error: {url} - {error}")

def on_extract_complete(
    url: str,
    request_id: str,
    duration_ms: float,
    chars: int,
    links: int,
) -> None:
    print(f"[{request_id}] Extracted {chars} chars, {links} links in {duration_ms:.1f}ms")

client = WebSearchClient(
    on_fetch_start=on_fetch_start,
    on_fetch_complete=on_fetch_complete,
    on_fetch_error=on_fetch_error,
    on_extract_complete=on_extract_complete,
)
```

### Timing Data

Access timing information from results:

```python
page = await client.fetch("https://example.com")

print(f"Fetch time: {page.fetch_duration_ms:.1f}ms")
print(f"Extract time: {page.extract_duration_ms:.1f}ms")
print(f"Total time: {page.fetch_duration_ms + page.extract_duration_ms:.1f}ms")
print(f"Fetched at: {page.fetched_at}")
```

## Integration with Stageflow

### Using in Stages

```python
from stageflow import Stage, StageContext, StageOutput, StageKind
from stageflow.websearch import WebSearchClient

class WebSearchStage:
    name = "web_search"
    kind = StageKind.ENRICH
    
    def __init__(self):
        self.client = WebSearchClient()
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        url = ctx.inputs.get_from("router", "search_url")
        
        page = await self.client.fetch(url)
        
        if not page.success:
            return StageOutput.error(f"Failed to fetch: {page.error}")
        
        # Store in enrichments format
        web_results = [page.to_dict()]
        
        return StageOutput.ok(
            web_results=web_results,
            page_title=page.title,
            page_content=page.markdown,
        )
```

### Using in Tools

```python
from stageflow.tools import BaseTool, ToolInput, ToolOutput
from stageflow.websearch import WebSearchClient

class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch and extract content from a web page"
    action_type = "WEB_FETCH"
    
    def __init__(self):
        self.client = WebSearchClient()
    
    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        url = input.action.payload.get("url")
        selector = input.action.payload.get("selector")
        
        page = await self.client.fetch(url, selector=selector)
        
        if not page.success:
            return ToolOutput(
                success=False,
                error=page.error,
            )
        
        return ToolOutput(
            success=True,
            data={
                "title": page.title,
                "content": page.markdown,
                "word_count": page.word_count,
                "links": [l.to_dict() for l in page.links[:10]],
            },
        )
```

### Storing in Enrichments

```python
from stageflow.context import Enrichments, ContextSnapshot

# Fetch pages
pages = await client.fetch_many(urls)

# Convert to enrichments format
web_results = [page.to_dict() for page in pages if page.success]

# Create enrichments
enrichments = Enrichments(web_results=web_results)

# Use in snapshot
snapshot = ContextSnapshot(
    enrichments=enrichments,
    # ... other fields
)
```

## Testing

Use `create_mock_client` for testing:

```python
import pytest
from stageflow.websearch import create_mock_client

@pytest.mark.asyncio
async def test_web_search_stage():
    # Set up mock responses
    responses = {
        "https://example.com": (
            200,
            "<html><body><h1>Test</h1><p>Content</p></body></html>",
            {"content-type": "text/html"},
        ),
    }
    
    client = create_mock_client(responses)
    page = await client.fetch("https://example.com")
    
    assert page.success
    assert "Test" in page.markdown
```

## Run Utilities

The `stageflow.websearch` module includes high-level utilities for common workflows.

### Quick Fetch Functions

```python
from stageflow.websearch import fetch_page, fetch_pages, fetch_with_retry

# Single page with minimal boilerplate
page = await fetch_page("https://example.com")

# Batch fetch with progress tracking
def show_progress(p):
    print(f"[{p.percent:.0f}%] {p.completed}/{p.total}")

pages = await fetch_pages(
    urls,
    concurrency=10,
    on_progress=show_progress,
    parallel_extraction=True,  # Use thread pool for CPU-bound extraction
)

# Fetch with automatic retry
page = await fetch_with_retry(
    "https://flaky-server.com",
    max_retries=3,
    retry_delay=1.0,
)
```

### Search and Extract

Crawl a site and find pages relevant to a query:

```python
from stageflow.websearch import search_and_extract

result = await search_and_extract(
    start_url="https://docs.python.org",
    query="asyncio tutorial",
    max_pages=50,
    max_depth=2,
)

print(f"Found {len(result.relevant_pages)} relevant pages")
for page in result.relevant_pages[:5]:
    print(f"- {page.title}: {page.url}")
```

### Site Mapping

Map a website's structure and collect all links:

```python
from stageflow.websearch import map_site

sitemap = await map_site(
    "https://example.com",
    max_pages=200,
    max_depth=4,
)

print(f"Pages crawled: {len(sitemap.pages)}")
print(f"Internal links: {len(sitemap.internal_links)}")
print(f"External links: {len(sitemap.external_links)}")
```

### Link Extraction

Extract and deduplicate links from multiple pages:

```python
from stageflow.websearch import extract_all_links

links = await extract_all_links(
    seed_urls,
    concurrency=10,
    internal_only=True,
)

print(f"Found {len(links)} unique internal links")
```

### Parallel Extraction

The `fetch_pages` function supports parallel content extraction using a thread pool.
This overlaps CPU-bound HTML parsing with network I/O for better throughput:

```python
# Enable parallel extraction (default: True)
pages = await fetch_pages(urls, parallel_extraction=True)

# Shutdown the thread pool during app cleanup
from stageflow.websearch import shutdown_extraction_pool
shutdown_extraction_pool()
```

---

## Error Handling

```python
page = await client.fetch("https://example.com")

if page.success:
    process_content(page.markdown)
else:
    if page.status_code == 404:
        handle_not_found(page.url)
    elif page.status_code >= 500:
        handle_server_error(page.url, page.error)
    else:
        handle_error(page.url, page.error)
```

## Content Truncation

Limit content size for LLM context windows:

```python
page = await client.fetch("https://example.com/long-article")

# Truncate to fit context
truncated = page.truncate(max_chars=8000)
print(len(truncated.markdown))  # <= 8000 (approximately)
```

## API Reference

### Main Classes

| Class | Description |
|-------|-------------|
| `WebSearchClient` | High-level client for fetching and processing |
| `WebPage` | Immutable result container |
| `PageMetadata` | Page metadata (title, description, etc.) |
| `ExtractedLink` | Link with URL, text, and context |
| `NavigationAction` | Available navigation action |
| `PaginationInfo` | Pagination details |

### Protocols (for extension)

| Protocol | Description |
|----------|-------------|
| `FetcherProtocol` | HTTP fetching interface |
| `ContentExtractorProtocol` | Content extraction interface |
| `NavigatorProtocol` | Navigation detection interface |

### Configuration Classes

| Class | Description |
|-------|-------------|
| `WebSearchConfig` | Client configuration |
| `FetchConfig` | HTTP fetch settings |
| `ExtractionConfig` | Content extraction settings |
| `NavigationConfig` | Navigation detection settings |

### Run Utilities

| Function/Class | Description |
|----------------|-------------|
| `fetch_page()` | Fetch single page with minimal boilerplate |
| `fetch_pages()` | Batch fetch with progress and parallel extraction |
| `fetch_with_retry()` | Fetch with automatic retry on failure |
| `search_and_extract()` | Crawl and filter pages by query relevance |
| `map_site()` | Map website structure and collect links |
| `extract_all_links()` | Extract deduplicated links from multiple pages |
| `FetchProgress` | Progress info dataclass for batch fetches |
| `SearchResult` | Result from `search_and_extract()` |
| `SiteMap` | Result from `map_site()` |
| `shutdown_extraction_pool()` | Cleanup thread pool on shutdown |
