"""Схема БД. Соответствует полям Source из рабочей таблицы источников."""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
    create_engine, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://signals:signals@localhost:5432/signals",
)


class Base(DeclarativeBase):
    pass


class Source(Base):
    """Источник целиком (одна строка на ленту). Метаданные из feeds.py."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    feed_url: Mapped[str | None] = mapped_column(Text)
    site_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(64))
    trust_level: Mapped[str] = mapped_column(String(16))
    language: Mapped[str] = mapped_column(String(8))
    topics: Mapped[str] = mapped_column(Text)              # через запятую
    is_indicator_only: Mapped[bool] = mapped_column(Boolean, default=False)
    sponsored_possible: Mapped[bool] = mapped_column(Boolean, default=False)
    attribution_required: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")

    # состояние поллинга — для условных запросов
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["FeedItem"]] = relationship(back_populates="source")


class FeedItem(Base):
    """Одна публикация из ленты.

    Полный текст статьи НЕ хранится — только то, что отдаёт лента.
    Для источников с attribution_required храним ссылку на оригинал
    и не модифицируем содержимое.
    """

    __tablename__ = "feed_items"
    __table_args__ = (UniqueConstraint("url_hash", name="uq_feed_items_url_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)

    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)        # None, если store_summary=False
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    raw_categories: Mapped[str | None] = mapped_column(Text)  # теги ленты через запятую

    # денормализация из Source — чтобы выдача строилась одним запросом
    trust_level: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8))
    is_indicator_only: Mapped[bool] = mapped_column(Boolean, default=False)
    sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False)

    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped[Source] = relationship(back_populates="items")


engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
