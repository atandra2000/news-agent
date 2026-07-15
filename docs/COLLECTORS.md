# Collectors

> Source plugins: the 15 registered collectors, how they work, and how to add
> a new one.

---

## 1. Collector contract

Every collector subclasses `CollectorAdapter` and implements one method:

```python
class CollectorAdapter(abc.ABC):
    source_type: ClassVar[str]

    @abc.abstractmethod
    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        ...
```

A `RawItem` is the normalized unit collected from any source:

```python
@dataclass
class RawItem:
    source_type: str
    title: str
    url: str
    content: str = ""
    summary: str | None = None       # auto-fills from content[:400] if not set
    author: str | None = None
    published_at: datetime | None = None
    extra: dict = field(default_factory=dict)  # source-specific metadata

    @property
    def uid(self) -> str:
        # Stable SHA-256 of canonical url, else content hash.
```

---

## 2. Registered collectors

| Name | Source | Module | Extra fields |
|------|--------|--------|--------------|
| `arxiv` | arXiv API | `arxiv.py` | `authors`, `categories`, `pdf_url` |
| `rss` | RSS/Atom feeds | `rss.py` | `feed_url` |
| `github_trending` | GitHub Trending HTML | `github_trending.py` | `stars_today`, `language`, `repo_url` |
| `github_releases` | GitHub Releases API | `github_releases.py` | `repo`, `tag`, `published_at` |
| `huggingface` | HuggingFace Hub API | `huggingface.py` | `subtype` (model/dataset/space), `likes`, `downloads` |
| `blog` | Curated blog RSS | `blog.py` | `feed_url` |
| `hacker_news` | HN Algolia API | `hn.py` | `points`, `num_comments` |
| `semantic_scholar` | Semantic Scholar API | `semantic_scholar.py` | `authors`, `venue`, `citation_count` |
| `openreview` | OpenReview API | `openreview.py` | `venue`, `keywords` |
| `bluesky` | Bluesky AT Protocol | `bluesky.py` | `author_handle`, `repost_count` |
| `youtube` | YouTube Data API | `youtube.py` | `channel`, `video_id`, `duration` |
| `tavily` | Tavily Search API | `tavily.py` | `score`, `published_date` |
| `context7` | Context7 library docs | `context7.py` | `library_id`, `version` |
| `devto` | Dev.to articles | `devto.py` | `positive_reactions_count`, `tag_list` |
| `lobsters` | Lobsters curated tech | `lobsters.py` | `score`, `comments_url` |

> **Excluded by design:** the `reddit` and `papers_with_code` modules exist in
> `newsagent/collectors/` but are **not registered** (their public web APIs are
> unreliable). The coverage they would have provided is filled by `tavily`,
> `context7`, `github_releases`, `devto`, and `lobsters`. Do not enable them
> unless you have a stable, authenticated endpoint.

---

## 3. Runner (`newsagent/collectors/registry.py`)

```python
async def run_collector(
    name: str, *, since: datetime, limit: int = 50,
    timeout: float = 30.0, retry_once: bool = True,
) -> list[RawItem]:
```

- **Timeout:** `asyncio.wait_for` wraps each `collect()` call.
- **Retry:** If `retry_once=True`, retries once after a timeout/HTTP error.
- **Skip-on-failure:** After retry exhaustion, logs `collector.skipped` and
  returns `[]`. One dead collector never blocks the report.
- **Unknown collector:** Returns `[]` (logged as `collector.unknown`).

---

## 4. Enabling collectors

In `.env`:

```bash
# Comma-separated list of collector names (reddit/papers_with_code are excluded by design).
NEWSAGENT_COLLECTOR_ENABLED=arxiv,rss,github_trending,huggingface,hacker_news,semantic_scholar
```

Or override per profile in `newsagent/profiles.py`:

```python
"custom": ReportProfile(
    name="custom",
    collectors=["arxiv", "huggingface"],  # override
    ...
)
```

Check enabled vs. registered:

```bash
newsagent sources
```

---

## 5. Adding a new collector

1. **Create the module** `newsagent/collectors/<name>.py`:

   ```python
   from datetime import datetime
   from newsagent.collectors.base import CollectorAdapter, RawItem

   class MyCollector(CollectorAdapter):
       source_type = "my_source"

       async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
           # Fetch from your API.
           # Return a list of RawItem with source_type="my_source".
           return [
               RawItem(
                   source_type="my_source",
                   title=item["title"],
                   url=item["url"],
                   content=item["description"],
                   published_at=datetime.fromisoformat(item["date"]),
                   extra={"custom_field": item["custom"]},
               )
               for item in data[:limit]
           ]
   ```

2. **Register it** in `newsagent/collectors/registry.py`:

   ```python
   from newsagent.collectors.my_source import MyCollector

   REGISTRY: dict[str, type[CollectorAdapter]] = {
       ...
       "my_source": MyCollector,
   }
   ```

3. **Enable it** in `.env`:

   ```bash
   NEWSAGENT_COLLECTOR_ENABLED=...,my_source
   ```

4. **Test it:**

   ```bash
   newsagent sources  # should list my_source
   ```

5. **Write a test** (offline, using `respx` to mock the API):

   ```python
   @respx.mock
   @pytest.mark.asyncio
   async def test_my_collector():
       respx.get("https://my-api.example.com/items").mock(
           return_value=httpx.Response(200, json=[{"title": "X", "url": "..."}])
       )
       collector = MyCollector()
       items = await collector.collect(since=datetime(2026, 1, 1, tzinfo=timezone.utc), limit=10)
       assert len(items) == 1
       assert items[0].source_type == "my_source"
   ```

---

## 6. HTTP utilities

`newsagent/collectors/http.py` provides shared helpers:
- Retry with exponential backoff (via `tenacity`).
- Common timeout defaults.
- Rate-limit header parsing.

Collectors that need authenticated APIs (YouTube, Semantic Scholar) read their
API keys from environment variables specific to that collector.