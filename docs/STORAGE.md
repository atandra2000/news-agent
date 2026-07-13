# Storage

> SQLite schema (18 tables), vector store, knowledge graph, and
> forward-migration strategy.

---

## 1. SQLite — one file, zero infra

Hermes uses a single SQLite file (default: `storage/hermes.db`) accessed via
SQLAlchemy async + aiosqlite. No Postgres, no Alembic, no DB server.

**Engine:** `hermes/storage/db.py: make_engine()` →
`create_async_engine("sqlite+aiosqlite:///<path>")`

**Schema creation:** `create_schema()` runs `Base.metadata.create_all` then
`_add_missing_columns()` for forward-migration.

### Forward-migration (no Alembic)

When new columns are added to a model, `_add_missing_columns()` introspects
the existing schema and runs `ALTER TABLE ... ADD COLUMN` for any missing
columns. This means existing databases are upgraded in-place on the next
`hermes news` without manual migration scripts.

```python
async def _add_missing_columns(engine):
    def _migrate(sync_conn):
        inspector = inspect(sync_conn)
        for table in Base.metadata.tables.values():
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    sync_conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}'))
```

`SCHEMA_VERSION = 2` is tracked but not enforced — the migration is
column-additive and always runs.

---

## 1.1 KG tables are not written

The KG tables (`entities`, `relationships`, `entity_aliases`, `entity_history`,
`timelines`) are defined but **not** written by the pipeline. The in-memory
`EvidenceGraph` (`stages/evidence_graph.py::build_evidence_graph`) is the only
graph used at runtime; past-reports RAG (via `pipeline/synthesize.py`) provides
cross-run memory. The KG tables remain in the schema for forward-compatibility
and so that any older data already in them can still be queried via
`search_entities` / `relations_for`.

## 1.2 Active vs legacy tables

The 18 tables fall into two groups:

- **Actively written by the pipeline (6):** `items`, `item_aliases`,
  `vectors`, `reports`, `report_evals`, `lessons`. The unified pipeline
  writes `items` / `item_aliases` / `vectors` during the search→synthesis
  pass, `reports` + `lessons` from the orchestrator / quality stage;
  `hermes eval` writes `report_evals`. The `trend_snapshots` table is
  defined but no longer written (`pipeline/trend.py` was removed during
  the unification) — keep the schema entry for forward-compatibility.
- **Legacy (not written by the pipeline):** `analyses`, `clusters`,
  `research_plans`, `claims`, `evidence`, `evidence_relationships`. These
  belong to the older `hermes.analyzers` / Research-Intelligence path. They
  remain in the schema for forward-compatibility and are safe to ignore when
  reasoning about the pipeline. The KG tables (`entities`, `relationships`,
  `entity_aliases`, `entity_history`, `timelines`) are documented separately
  in §1.1 — they are also not written.

---

## 2. Tables (18 total)

### Core pipeline tables

#### `items`
Canonical ingested items (one per unique URL).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `uid` | String(64) | SHA-256 of canonical URL; unique, indexed |
| `source_type` | String(32) | `arxiv`, `rss`, `huggingface`, ...; indexed |
| `title` | String(1024) | |
| `url` | Text | |
| `content` | Text | |
| `summary` | Text | Auto-filled from content[:400] |
| `author` | String(512) | Nullable |
| `published_at` | DateTime | Nullable |
| `simhash` | Integer | 64-bit SimHash; indexed |
| `is_canonical` | Bool | `True` = new canonical; `False` = near-dup alias; indexed |
| `canonical_uid` | String(64) | Points to canonical item for near-dups; indexed |
| `extra_json` | Text | JSON: source-specific metadata |
| `created_at` | DateTime | |

#### `item_aliases`
Near-duplicate URL mappings.

| Column | Type |
|--------|------|
| `id` | Integer PK |
| `uid` | String(64), indexed |
| `canonical_uid` | String(64), indexed |

#### `analyses`  *(legacy — not written by the pipeline)*
Typed LLM analyses (older `hermes.analyzers` path). Idempotent by `(item_uid, analyzer_version)`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `item_uid` | String(64), indexed | |
| `analysis_type` | String(32), indexed | paper / model_release / product / benchmark / industry_event / community_signal |
| `analyzer_version` | String(16) | `v1` |
| `importance` | Float | 0.0–1.0 |
| `novelty` | Float | 0.0–1.0 |
| `long_term_impact` | Float | 0.0–1.0 |
| `title` | String(1024) | |
| `summary` | Text | |
| `beginner_explain` | Text | Plain-language analogy |
| `expert_explain` | Text | Technical mechanism |
| `entities_json` | Text | JSON: `[{name, type}]` |
| `relations_json` | Text | JSON: `[{subject, predicate, object, confidence}]` |
| `claims_json` | Text | JSON: `[{text, status, sources, confidence}]` |
| `type_specific_json` | Text | JSON: type-specific fields |
| `engineering_implications` | Text | |
| `model_used` | String(64) | LLM model that produced this analysis |
| `created_at` | DateTime | |

Unique constraint: `(item_uid, analyzer_version)`.

#### `clusters`  *(legacy — not written by the pipeline)*

| Column | Type |
|--------|------|
| `id` | Integer PK |
| `cluster_id` | Integer, indexed |
| `label` | String(256) |
| `item_uids_json` | Text (JSON list) |
| `run_date` | DateTime |

#### `trend_snapshots`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `run_date` | DateTime, indexed | |
| `topic` | String(256), indexed | |
| `metric` | String(32) | `mentions` |
| `value` | Float | |
| `delta` | Float | Day-over-day change |
| `direction` | String(16) | `rising` / `fading` / `flat` |

#### `reports`
Archive of rendered reports.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `run_date` | DateTime, unique | |
| `path` | Text | |
| `md_sha256` | String(64) | Content hash |
| `sections_count` | Integer | |
| `items_analyzed` | Integer | |
| `sources_checked_json` | Text (JSON) | Real collector names that ran. Populated by `_gather_sources_fallback` returning `(results, checked, failed)`. |
| `sources_failed_json` | Text (JSON) | Real collector names that failed (timeout / exception). |
| `duplication_collapse_rate` | Float, default 0.0 | Fraction of sources dropped as URL or cross-post duplicates (0.0 = no dedup, 1.0 = all dupes). Computed by `search.py::duplication_collapse_rate` over the raw→deduped delta. Auto-migrated by `_add_missing_columns()`. |
| `token_usage` | Integer | |
| `created_at` | DateTime | |

#### `lessons`
Self-improving memory.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `run_date` | DateTime, indexed | |
| `kind` | String(32) | `critic`, `quality`, `research` |
| `text` | Text | The improvement note |
| `dimension` | String(32), nullable | Optional quality dimension |
| `resolved` | Bool, indexed | `False` = loaded into next run |

#### `report_evals`
Brief pipeline evaluation scores.

| Column | Type |
|--------|------|
| `id` | Integer PK |
| `report_path` | Text, indexed |
| `prompt_path` | Text, indexed |
| `cadence` | String(16) |
| `coverage_score` | Float |
| `citation_score` | Float |
| `quality_score` | Float |
| `cadence_score` | Float |
| `overall_score` | Float |
| `feedback` | Text |
| `token_usage` | Integer |
| `run_date` | DateTime, indexed |

### Knowledge graph tables  *(legacy — not populated by the pipeline)*

#### `entities`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `type` | String(32), indexed | `model`, `company`, `person`, ... |
| `name` | String(256) | |
| `canonical_name` | String(256), indexed | Normalized key |
| `aliases_json` | Text (JSON list) | |
| `first_seen` | DateTime | |
| `last_seen` | DateTime | |

Unique constraint: `(type, canonical_name)`.

#### `relationships`

| Column | Type |
|--------|------|
| `id` | Integer PK |
| `subject` | String(256), indexed |
| `predicate` | String(32), indexed |
| `object` | String(256), indexed |
| `confidence` | Float |
| `source_item_uid` | String(64), indexed |
| `first_seen` | DateTime |

#### `vectors`
Optional raw vector storage fallback (Qdrant is primary when enabled).

| Column | Type |
|--------|------|
| `uid` | String(64) PK |
| `vec` | LargeBinary |

### Research Intelligence Layer tables  *(legacy — not written by the pipeline)*

#### `research_plans`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `run_date` | DateTime, indexed | |
| `cluster_id` | Integer, nullable, indexed | |
| `central_question` | Text | "What is the significance of: X?" |
| `objectives_json` | Text (JSON) | |
| `sub_questions_json` | Text (JSON) | |
| `contradictions_json` | Text (JSON) | |
| `missing_evidence_json` | Text (JSON) | |
| `confidence_target` | Float | 0.7 |
| `expected_deliverables_json` | Text (JSON) | |
| `item_uids_json` | Text (JSON) | |
| `created_at` | DateTime | |

#### `claims`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `claim_id` | String(64), unique, indexed | Stable id |
| `item_uid` | String(64), indexed | |
| `text` | Text | |
| `claim_type` | String(32) | `statement` |
| `status` | String(32), indexed | `CORROBORATED` / `CONFLICTING` / `SINGLE_SOURCE` / `UNVERIFIABLE` |
| `confidence` | Float | |
| `sources_json` | Text (JSON) | |
| `entities_json` | Text (JSON) | |
| `plan_id` | Integer, nullable, indexed | FK to `research_plans` |
| `created_at` | DateTime | |

#### `evidence`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `claim_id` | String(64), indexed | |
| `item_uid` | String(64), indexed | |
| `direction` | String(32), indexed | `supports` / `contradicts` / `references` / `extends` / `duplicates` / `supersedes` |
| `text` | Text | |
| `source_url` | Text | |
| `source_type` | String(32) | |
| `confidence` | Float | |
| `created_at` | DateTime | |

#### `evidence_relationships`
Typed edges between evidence nodes and claims.

| Column | Type |
|--------|------|
| `id` | Integer PK |
| `source_claim_id` | String(64), indexed |
| `target_claim_id` | String(64), indexed |
| `predicate` | String(32), indexed |
| `confidence` | Float |
| `source_item_uid` | String(64), indexed |
| `created_at` | DateTime |

#### `entity_aliases`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `entity_id` | String(64), indexed | Canonical id (`gpt-5`) |
| `alias` | String(256), indexed | Raw alias (`GPT 5`) |
| `alias_normalized` | String(256), indexed | Normalized (`gpt-5`) |
| `match_method` | String(32) | `exact` / `normalized` / `fuzzy` / `manual` / `embedding` |
| `confidence` | Float | |
| `is_manual` | Bool, indexed | |
| `created_at` | DateTime | |

Unique constraint: `(alias_normalized, entity_id)`.

#### `entity_history`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `entity_id` | String(64), indexed | |
| `event_type` | String(32), indexed | `release` / `paper` / `benchmark` / `pricing` / `funding` / `repository` / `leadership` / `event` |
| `event_date` | DateTime, nullable, indexed | |
| `title` | String(512) | |
| `description` | Text | |
| `source_url` | Text | |
| `source_item_uid` | String(64), indexed | |
| `metadata_json` | Text (JSON) | |
| `created_at` | DateTime | |

#### `timelines`
Materialized timeline entries for fast temporal queries.

| Column | Type |
|--------|------|
| `id` | Integer PK |
| `entity_id` | String(64), indexed |
| `event_date` | DateTime, nullable, indexed |
| `event_type` | String(32), indexed |
| `title` | String(512) |
| `description` | Text |
| `source_url` | Text |
| `created_at` | DateTime |

---

## 3. Vector store

**Module:** `hermes/storage/vectorstore.py`

`VectorStore` protocol with two implementations:

| Backend | Config | When to use |
|---------|--------|-------------|
| `numpy` (default) | `HERMES_STORAGE_VECTOR_BACKEND=numpy` | <100K items, zero-dep, brute-force cosine |
| `qdrant` (embedded) | `HERMES_STORAGE_VECTOR_BACKEND=qdrant` | Larger corpora, HNSW index |

Both persist vectors to disk (numpy: SQLite `vectors` table; Qdrant: local
on-disk at `storage/vectors/`).

```python
class VectorStore(abc.ABC):
    @abc.abstractmethod
    async def upsert(self, uids: list[str], vectors: np.ndarray) -> None: ...
    @abc.abstractmethod
    async def search(self, query: np.ndarray, top_k: int = 10) -> list[tuple[str, float]]: ...
```

---

## 4. Knowledge graph

**Module:** `hermes/storage/kg.py`

Query helpers over the `entities` and `relationships` tables:

- `search_entities(ctx, query)` — fuzzy entity search by name.
- `relations_for(ctx, entity_name)` — all relationships involving an entity.

The KG tables (`entities`, `relationships`, `entity_aliases`, `entity_history`,
`timelines`) are populated by the legacy `hermes.analyzers` / Research-Intelligence
path, **not** by the daily pipeline. `search_entities` / `relations_for` remain
available as query helpers over whatever data is present.