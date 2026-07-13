"""SQLAlchemy models. SQLite via aiosqlite."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(1024))
    url: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    simhash: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_canonical: Mapped[bool] = mapped_column(default=True, index=True)
    canonical_uid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    extra_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class ItemAlias(Base):
    __tablename__ = "item_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    canonical_uid: Mapped[str] = mapped_column(String(64), index=True)


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("item_uid", "analyzer_version", name="uq_analysis_item_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_uid: Mapped[str] = mapped_column(String(64), index=True)
    analysis_type: Mapped[str] = mapped_column(String(32), index=True)
    analyzer_version: Mapped[str] = mapped_column(String(16), default="v1")
    importance: Mapped[float] = mapped_column(Float, default=0.0)
    novelty: Mapped[float] = mapped_column(Float, default=0.0)
    long_term_impact: Mapped[float] = mapped_column(Float, default=0.0)
    title: Mapped[str] = mapped_column(String(1024), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    beginner_explain: Mapped[str] = mapped_column(Text, default="")
    expert_explain: Mapped[str] = mapped_column(Text, default="")
    entities_json: Mapped[str] = mapped_column(Text, default="[]")
    relations_json: Mapped[str] = mapped_column(Text, default="[]")
    claims_json: Mapped[str] = mapped_column(Text, default="[]")
    type_specific_json: Mapped[str] = mapped_column(Text, default="{}")
    engineering_implications: Mapped[str] = mapped_column(Text, default="")
    model_used: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(256), default="")
    item_uids_json: Mapped[str] = mapped_column(Text, default="[]")
    run_date: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class TrendSnapshot(Base):
    __tablename__ = "trend_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    topic: Mapped[str] = mapped_column(String(256), index=True)
    metric: Mapped[str] = mapped_column(String(32), default="mentions")
    value: Mapped[float] = mapped_column(Float, default=0.0)
    delta: Mapped[float] = mapped_column(Float, default=0.0)
    direction: Mapped[str] = mapped_column(String(16), default="flat")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, unique=True)
    path: Mapped[str] = mapped_column(Text, default="")
    md_sha256: Mapped[str] = mapped_column(String(64), default="")
    sections_count: Mapped[int] = mapped_column(Integer, default=0)
    items_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    sources_checked_json: Mapped[str] = mapped_column(Text, default="[]")
    sources_failed_json: Mapped[str] = mapped_column(Text, default="[]")
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    # Fraction of raw sources dropped as URL/cross-post duplicates (0.0–1.0).
    # Added in response to the 2026-07-13 monthly report citing the same HN
    # Cat's-grant repost 3× as if it were 3 independent signals. The collapse
    # rate makes this observable in the run manifest instead of hidden.
    duplication_collapse_rate: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(256))
    canonical_name: Mapped[str] = mapped_column(String(256), index=True)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (UniqueConstraint("type", "canonical_name", name="uq_entity_type_name"),)


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(256), index=True)
    predicate: Mapped[str] = mapped_column(String(32), index=True)
    object: Mapped[str] = mapped_column(String(256), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_item_uid: Mapped[str] = mapped_column(String(64), index=True)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class VectorRow(Base):
    """Optional raw vector storage fallback (Qdrant is primary)."""

    __tablename__ = "vectors"

    uid: Mapped[str] = mapped_column(String(64), primary_key=True)
    vec: Mapped[bytes] = mapped_column(LargeBinary)


class Lesson(Base):
    """Self-improving memory: critiques/quality findings persisted across runs so the
    agent avoids repeating past weaknesses. Fed back into writer/critic prompts."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="critic")  # critic|quality|research
    text: Mapped[str] = mapped_column(Text, default="")
    dimension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolved: Mapped[bool] = mapped_column(default=False, index=True)


class ReportEval(Base):
    """Evaluation scores for a report — tracks quality over time."""

    __tablename__ = "report_evals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_path: Mapped[str] = mapped_column(Text, index=True)
    prompt_path: Mapped[str] = mapped_column(Text, index=True)
    cadence: Mapped[str] = mapped_column(String(16), default="daily")
    coverage_score: Mapped[float] = mapped_column(Float, default=0.0)
    citation_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    cadence_score: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    feedback: Mapped[str] = mapped_column(Text, default="")
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    run_date: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


# Research Intelligence Layer (added via _add_missing_columns)


class ResearchPlanRow(Base):
    """Structured research plan from clustered docs before LLM analysis
    (HERMES_DESIGN §12.5). One per cluster per run; drives evidence-graph + report generation.
    """

    __tablename__ = "research_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    central_question: Mapped[str] = mapped_column(Text, default="")
    objectives_json: Mapped[str] = mapped_column(Text, default="[]")
    sub_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    contradictions_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence_target: Mapped[float] = mapped_column(Float, default=0.7)
    expected_deliverables_json: Mapped[str] = mapped_column(Text, default="[]")
    item_uids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class ClaimRow(Base):
    """Structured claim with provenance + verification status. The Evidence Graph reasons
    over claims, not articles (Research Intelligence Layer §2).
    """

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    item_uid: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    claim_type: Mapped[str] = mapped_column(String(32), default="statement")
    # CORROBORATED | CONFLICTING | SINGLE_SOURCE | UNVERIFIABLE
    status: Mapped[str] = mapped_column(String(32), default="SINGLE_SOURCE", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    entities_json: Mapped[str] = mapped_column(Text, default="[]")
    plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class EvidenceRow(Base):
    """Evidence linked to a claim (Document→Claim→Evidence→…→Confidence graph).

    ``direction`` distinguishes support vs. counter-evidence without a separate table.
    """

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(64), index=True)
    item_uid: Mapped[str] = mapped_column(String(64), index=True)
    # supports | contradicts | references | extends | duplicates | supersedes
    direction: Mapped[str] = mapped_column(String(32), default="supports", index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(32), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class EvidenceRelationshipRow(Base):
    """Edge table of the Evidence Graph (Research Intelligence Layer §2).

    Predicates extend the KG's closed set: supports, contradicts, references,
    extends, duplicates, supersedes.
    """

    __tablename__ = "evidence_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_claim_id: Mapped[str] = mapped_column(String(64), index=True)
    target_claim_id: Mapped[str] = mapped_column(String(64), index=True)
    predicate: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_item_uid: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class EntityAliasRow(Base):
    """Canonical entity resolution mapping (Research Intelligence Layer §3).

    ``match_method`` records how the alias was resolved:
    exact | normalized | fuzzy | manual | embedding.
    """

    __tablename__ = "entity_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    alias: Mapped[str] = mapped_column(String(256), index=True)
    alias_normalized: Mapped[str] = mapped_column(String(256), index=True)
    match_method: Mapped[str] = mapped_column(String(32), default="normalized")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    is_manual: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (UniqueConstraint("alias_normalized", "entity_id", name="uq_alias_entity"),)


class EntityHistoryRow(Base):
    """Temporal memory of an entity's evolution (Research Intelligence Layer §4).

    Each row is a dated lifecycle event:
    release | paper | benchmark | pricing | funding | repository | leadership | event.
    """

    __tablename__ = "entity_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    event_date: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_item_uid: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class TimelineRow(Base):
    """Materialized timeline (one row per entity_id+event_date, derived from
    EntityHistoryRow) so temporal APIs avoid scanning full history each call.
    """

    __tablename__ = "timelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    event_date: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
