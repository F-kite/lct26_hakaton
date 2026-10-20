"""Обогащение сигналов с кэшем по feed_item_id и ленивым дообогащением.

Кэш пишется отдельной короткой сессией: результат дорогого LLM-вызова
не теряется, если основная транзакция поиска откатывается (в том числе
при отмене пользователем).
"""

from __future__ import annotations

import logging
import threading

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..config import ENRICHMENT_MODEL
from ..db import SessionLocal, Signal, SignalEnrichment
from .enrichment import EnrichmentResult, enrich_signal, enrichment_available

log = logging.getLogger(__name__)

# Ollama на CPU всё равно обрабатывает запросы по очереди — общий замок
# заодно исключает двойную генерацию для одного сигнала при параллельных
# открытиях карточки.
_lazy_lock = threading.Lock()


def _get_cached(session: Session, feed_item_id: int) -> EnrichmentResult | None:
    row = session.get(SignalEnrichment, feed_item_id)
    if row is None or row.model != ENRICHMENT_MODEL or row.weak_criteria is None:
        return None
    return EnrichmentResult(
        description=row.description,
        problem=row.problem,
        potential_advantage=row.potential_advantage,
        case_example=row.case_example,
        model=row.model,
        weak_criteria=row.weak_criteria,
        manifestations=row.manifestations,
    )


def _store(feed_item_id: int, result: EnrichmentResult) -> None:
    values = dict(
        model=result.model or ENRICHMENT_MODEL,
        description=result.description,
        problem=result.problem,
        potential_advantage=result.potential_advantage,
        case_example=result.case_example,
        weak_criteria=result.weak_criteria,
        manifestations=result.manifestations,
    )
    stmt = pg_insert(SignalEnrichment).values(feed_item_id=feed_item_id, **values)
    stmt = stmt.on_conflict_do_update(index_elements=[SignalEnrichment.feed_item_id], set_=values)
    try:
        with SessionLocal() as cache_session:
            cache_session.execute(stmt)
            cache_session.commit()
    except Exception as exc:
        log.error("не удалось записать кэш обогащения feed_item_id=%s: %s", feed_item_id, exc)


def enrich_cached(
    session: Session,
    client: httpx.Client,
    feed_item_id: int,
    title: str,
    summary: str,
    *,
    allow_llm: bool = True,
) -> EnrichmentResult | None:
    """Результат из кэша; при промахе — вызов LLM (если allow_llm) и запись в кэш."""
    cached = _get_cached(session, feed_item_id)
    if cached is not None:
        return cached
    if not allow_llm:
        return None
    result = enrich_signal(client, title, summary)
    if result is not None:
        _store(feed_item_id, result)
    return result


def _is_enriched(signal: Signal) -> bool:
    return bool(signal.explanation.get("enrichment_model")) and signal.weak_criteria is not None


def ensure_enriched(session: Session, signal: Signal) -> None:
    """Дообогатить сигнал при открытии карточки, если описание ещё не
    сгенерировано (исключённые не обогащаются при поиске; также подхватывает
    сигналы, у которых обогащение раньше не удалось)."""
    if _is_enriched(signal) or not enrichment_available():
        return

    with _lazy_lock:
        session.refresh(signal)
        if _is_enriched(signal):
            return

        primary = next((ss for ss in signal.sources if ss.is_primary), None)
        if primary is None and signal.sources:
            primary = signal.sources[0]
        if primary is None:
            return

        item = primary.feed_item
        with httpx.Client() as client:
            result = enrich_cached(session, client, item.id, item.title, item.summary or "")
        if result is None:
            return

        signal.description = result.description
        signal.problem = result.problem
        signal.potential_advantage = result.potential_advantage
        signal.case_example = result.case_example
        signal.weak_criteria = result.weak_criteria
        signal.manifestations = result.manifestations
        explanation = dict(signal.explanation)
        explanation["enrichment_model"] = result.model or ENRICHMENT_MODEL
        signal.explanation = explanation
        session.commit()
