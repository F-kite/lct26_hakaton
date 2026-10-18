"""Шаг 1 пайплайна: кандидаты в сигналы — ILIKE по заголовку/summary в
feed_items за окно свежести. Группировки по пересечению слов заголовка нет
намеренно: слова запроса есть в каждой найденной записи по построению,
группировка схлопывает всю выдачу в один кластер.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import FeedItem, Source
from .classifier import SignalCandidate

CANDIDATE_LOOKBACK_DAYS = 365
_WORD_RE = re.compile(r"[a-zа-я0-9]+", re.IGNORECASE)


def find_candidates(
    session: Session, query: str, *, limit: int = 200,
    date_from: date | None = None, date_to: date | None = None,
) -> list[SignalCandidate]:
    """date_from/date_to — диапазон дат публикации включительно. Без date_from
    действует окно свежести CANDIDATE_LOOKBACK_DAYS, без date_to верхней
    границы нет."""
    terms = [t for t in _WORD_RE.findall(query.lower()) if len(t) > 2]
    if not terms:
        return []

    if date_from is not None:
        since = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=CANDIDATE_LOOKBACK_DAYS)
    stmt = (
        select(FeedItem, Source)
        .join(Source, Source.id == FeedItem.source_id)
        .where(FeedItem.published_at >= since)
    )
    if date_to is not None:
        stmt = stmt.where(FeedItem.published_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    for term in terms:
        pattern = f"%{term}%"
        stmt = stmt.where((FeedItem.title.ilike(pattern)) | (FeedItem.summary.ilike(pattern)))
    stmt = stmt.order_by(FeedItem.published_at.desc()).limit(limit)

    rows = session.execute(stmt).all()

    return [
        SignalCandidate(
            feed_item_ids=[item.id],
            title=item.title,
            summary=item.summary,
            sources=[source.key],
            trust_levels=[item.trust_level],
            published_at=item.published_at,
            language=item.language,
        )
        for item, source in rows
    ]
