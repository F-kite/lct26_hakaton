"""Шаг 1 пайплайна — кандидаты в сигналы.

Поиск по уже накопленному корпусу (feed_items) — ILIKE по заголовку/summary
в окне свежести. Это НЕ то же самое, что закрытый датасет из ТЗ: feed_items
— собственный растущий корпус (11 источников, пополняется каждые 30 минут
через RSS-collector), плюс живой fan-out по arXiv/Semantic Scholar/Crossref/
USPTO/EPO OPS для конкретного запроса пользователя (live_sources.py,
вызывается из orchestrator.py уже после find_candidates).

Раньше здесь была ещё и группировка похожих записей в один "кандидат"
(по пересечению слов заголовка) — убрал. Она ломалась именно на словах
самого поискового запроса: они есть в каждой найденной записи по
построению (это же критерий, по которому запись сюда попала), поэтому
вся выдача схлопывалась в один гигантский кластер вместо разбивки на
темы. Понимание «что здесь на самом деле про одно и то же» — смысловая
задача, ей место в classifier.py (модели), не в наивном сравнении слов
тут. Каждая запись идёт как отдельный кандидат с одним источником.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import FeedItem, Source
from .classifier import SignalCandidate

CANDIDATE_LOOKBACK_DAYS = 365  # ТЗ: горизонт тренда 12-24 мес, берём консервативно 12
_WORD_RE = re.compile(r"[a-zа-я0-9]+", re.IGNORECASE)


def find_candidates(session: Session, query: str, *, limit: int = 200) -> list[SignalCandidate]:
    terms = [t for t in _WORD_RE.findall(query.lower()) if len(t) > 2]
    if not terms:
        return []

    stmt = (
        select(FeedItem, Source)
        .join(Source, Source.id == FeedItem.source_id)
        .where(FeedItem.published_at >= datetime.now(timezone.utc) - timedelta(days=CANDIDATE_LOOKBACK_DAYS))
    )
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
