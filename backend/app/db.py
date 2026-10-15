"""ORM-модели и подключение к БД.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Зеркало схемы collector
# --------------------------------------------------------------------------

class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    feed_url: Mapped[str | None] = mapped_column(Text)
    site_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(64))
    trust_level: Mapped[str] = mapped_column(String(16))
    language: Mapped[str] = mapped_column(String(8))
    topics: Mapped[str] = mapped_column(Text)
    is_indicator_only: Mapped[bool] = mapped_column(Boolean, default=False)
    sponsored_possible: Mapped[bool] = mapped_column(Boolean, default=False)
    attribution_required: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class FeedItem(Base):
    __tablename__ = "feed_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_categories: Mapped[str | None] = mapped_column(Text)
    trust_level: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8))
    is_indicator_only: Mapped[bool] = mapped_column(Boolean, default=False)
    sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[Source] = relationship()


# --------------------------------------------------------------------------
# Новые таблицы
# --------------------------------------------------------------------------

class SearchQuery(Base):
    """Один открытый запрос пользователя (POST /search). Статус и счётчики
    для прогресса через поллинг (GET /search/{id}/status).
    """

    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|failed
    sources_processed: Mapped[int] = mapped_column(Integer, default=0)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    signals_above_75: Mapped[int] = mapped_column(Integer, default=0)
    phase: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    signals: Mapped[list[Signal]] = relationship(back_populates="query")


class Signal(Base):
    """Результат анализа — один потенциальный слабый сигнал. query_id
    сделан nullable заранее, под возможные сигналы вне конкретного запроса
    (сейчас пайплайн всегда создаёт их с query_id).
    """

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int | None] = mapped_column(ForeignKey("search_queries.id"))
    title: Mapped[str] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    problem: Mapped[str | None] = mapped_column(Text)
    potential_advantage: Mapped[str | None] = mapped_column(Text)
    case_example: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(String(64))
    mention_trend: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    is_mainstream: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="included")
    explanation: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    query: Mapped[SearchQuery | None] = relationship(back_populates="signals")
    sources: Mapped[list[SignalSource]] = relationship(back_populates="signal")


class SignalSource(Base):
    """Связь сигнала с подтверждающими записями."""

    __tablename__ = "signal_sources"

    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), primary_key=True)
    feed_item_id: Mapped[int] = mapped_column(ForeignKey("feed_items.id"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    signal: Mapped[Signal] = relationship(back_populates="sources")
    feed_item: Mapped[FeedItem] = relationship()


class SignalEnrichment(Base):
    """Кэш LLM-обогащения по feed_item_id: один и тот же материал может
    попадать в сигналы разных запросов — повторно LLM не вызываем.
    model нужна, чтобы смена модели не отдавала устаревший текст.
    """

    __tablename__ = "signal_enrichments"

    feed_item_id: Mapped[int] = mapped_column(ForeignKey("feed_items.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    problem: Mapped[str | None] = mapped_column(Text)
    potential_advantage: Mapped[str | None] = mapped_column(Text)
    case_example: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
