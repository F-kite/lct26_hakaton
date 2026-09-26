"""ORM-модели и подключение к БД.

Source/FeedItem — зеркало схемы RSS-collector (collector/db.py), та же
таблица в той же Postgres `signals`, но определены заново: backend и
collector — независимо разворачиваемые Docker-образы, кросс-импорт
Python-модулей между ними не делаем.

Изначально были только на чтение, теперь backend тоже пишет сюда:
live-поиск (pipeline/live_sources.py) обогащает feed_items результатами
arXiv/Semantic Scholar/Crossref/USPTO/EPO OPS прямо во время поиска —
поэтому здесь нужны ВСЕ колонки реальной таблицы (включая NOT NULL без
дефолта на уровне БД — is_indicator_only, sponsored_possible и т.д.),
не только то, что было нужно для чтения.

Signal/SignalSource/SearchQuery — новые таблицы, которыми владеет backend.

Base.metadata.create_all() (см. init_db.py) безопасен для существующих
sources/feed_items: create_all по умолчанию проверяет, что таблица уже
есть в БД, и пропускает её — создаст только новые три таблицы.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Зеркало схемы collector — только чтение
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
# Новые таблицы — владелец backend
# --------------------------------------------------------------------------

class SearchQuery(Base):
    """Один открытый запрос пользователя (POST /search). Статус и счётчики
    для стриминга прогресса через поллинг (GET /search/{id}/status) —
    бонусные пункты ТЗ: обработано источников, кандидатов, сигналов >75%.
    """

    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|failed
    sources_processed: Mapped[int] = mapped_column(Integer, default=0)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    signals_above_75: Mapped[int] = mapped_column(Integer, default=0)
    # этап пайплайна для модалки прогресса на фронте: collecting -> scoring
    # -> ranking -> done — грубее реального пайплайна, но даёт честные (не
    # выдуманные) промежуточные шаги вместо мгновенного скачка в "готово"
    phase: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    signals: Mapped[list["Signal"]] = relationship(back_populates="query")


class Signal(Base):
    """Результат анализа — один потенциальный слабый сигнал. query_id=None
    зарезервировано под накопленные сигналы вне конкретного запроса
    пользователя (например, фоновая переоценка корпуса) — сейчас пайплайн
    всегда создаёт их с query_id, но поле сделано nullable заранее.
    """

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int | None] = mapped_column(ForeignKey("search_queries.id"))
    title: Mapped[str] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(String(64))
    # description/potential_advantage/case_example — три поля ТЗ ("описание
    # технологии, потенциальное преимущество, кейс-пример"), заполняются
    # LLM-обогащением (pipeline/enrichment.py) строго по тексту источника,
    # не из общих знаний модели. Обоснование КЛАССИФИКАЦИИ (почему слабый
    # сигнал) — отдельно, в explanation, не путать с описанием технологии.
    description: Mapped[str | None] = mapped_column(Text)
    potential_advantage: Mapped[str | None] = mapped_column(Text)
    case_example: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(String(64))
    mention_trend: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    is_mainstream: Mapped[bool] = mapped_column(Boolean, default=False)
    # included — прошёл порог, показывается на вкладке "Слабые сигналы";
    # excluded — не прошёл (низкая оценка и/или зрелая технология/шум),
    # показывается на вкладке "Исключённые" с причиной в explanation —
    # отдельное поле, а не is_mainstream: исключить может и "шум", не
    # только зрелая технология
    status: Mapped[str] = mapped_column(String(16), default="included")
    explanation: Mapped[dict] = mapped_column(JSONB, default=dict)  # интерпретируемость: ТЗ §2, §8.3
    model_version: Mapped[str] = mapped_column(String(64))  # какая модель/эвристика дала оценку
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    query: Mapped[SearchQuery | None] = relationship(back_populates="signals")
    sources: Mapped[list["SignalSource"]] = relationship(back_populates="signal")


class SignalSource(Base):
    """Связь сигнала с подтверждающими записями — кросс-источниковое
    подтверждение (⚑-источники по ТЗ не могут быть единственным основанием).
    """

    __tablename__ = "signal_sources"

    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), primary_key=True)
    feed_item_id: Mapped[int] = mapped_column(ForeignKey("feed_items.id"), primary_key=True)
    # true — этот источник дал текст для LLM-обогащения (description/
    # case_example), т.е. "где это уже проявилось" на самом деле про него;
    # у остальных источников группы (см. display_grouping.py) — false.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    signal: Mapped[Signal] = relationship(back_populates="sources")
    feed_item: Mapped[FeedItem] = relationship()


engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
