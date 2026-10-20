"""Оркестрация: запрос -> кандидаты -> оценка моделью -> топ-N -> запись в БД.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..config import (
    MODEL_PATH,
    MODEL_VERSION,
    ENRICHMENT_MODEL,
    SEARCH_CANDIDATE_LIMIT,
    SEARCH_EXCLUDED_LIMIT,
    SEARCH_TOP_N,
    SIGNAL_SCORE_THRESHOLD,
)
from ..db import FeedItem, SearchQuery, Signal, SignalSource
from .candidates import find_candidates
from .corroboration import Corroboration, corroborate
from .classifier import (
    LABEL_MATURE,
    ScoringResult,
    SignalCandidate,
    SignalClassifier,
    TrainedModelClassifier,
)
from .display_grouping import DisplayGroup, group_for_display
from .enrichment import translate_query_to_english, translation_available
from .enrichment_service import enrich_cached
from .live_sources import _detect_language, fetch_all_live, fetch_analyst_reports, persist_live_items

log = logging.getLogger(__name__)

def _build_classifier() -> SignalClassifier:
    if MODEL_VERSION == "v2":
        from .classifier_v2 import E5SignalClassifier

        return E5SignalClassifier()
    return TrainedModelClassifier(MODEL_PATH)


DEFAULT_CLASSIFIER: SignalClassifier = _build_classifier()

# In-memory отметка отменённых поисков — run_search() выполняется в том же
# процессе backend'а (FastAPI BackgroundTasks), поэтому БД/новая колонка
# не нужны: достаточно обычного set(), видимого обоим — эндпоинту отмены
# и самому пайплайну.
_cancelled_queries: set[int] = set()


class _SearchCancelled(Exception):
    """Внутренний сигнал остановки — ловится в run_search() тем же except,
    что и обычные сбои, но с другим текстом ошибки."""


def cancel_search(query_id: int) -> None:
    _cancelled_queries.add(query_id)


def _check_cancelled(query_id: int) -> None:
    if query_id in _cancelled_queries:
        raise _SearchCancelled()


def _feed_item_to_candidate(item: FeedItem) -> SignalCandidate:
    return SignalCandidate(
        feed_item_ids=[item.id],
        title=item.title,
        summary=item.summary,
        sources=[item.source.key],
        trust_levels=[item.trust_level],
        published_at=item.published_at,
        language=item.language,
    )


def _is_mainstream(result) -> bool:
    return result.explanation.get("predicted_class") == LABEL_MATURE


GRANT_SOURCES = {"nsf", "ukri", "cordis"}
SCIENTIFIC_SOURCES = {"arxiv", "semantic_scholar", "openalex", "crossref", "europepmc"}
FRESH_DAYS = 365


def _signal_predictors(group: DisplayGroup, corroboration: Corroboration | None = None) -> list[str]:
    indicators = set(group.result.explanation.get("indicators") or [])
    sources = {key for member in group.members for key in member.sources}
    dates = [m.published_at for m in group.members if m.published_at]
    now = datetime.now(timezone.utc)

    tags = []
    if sources & GRANT_SOURCES:
        tags.append("Получен грант")
    if "early" in indicators:
        tags.append("Первые пилоты")
    if "funding" in indicators:
        tags.append("Привлечены инвестиции")
    if "research" in indicators:
        tags.append("Новые исследования")
    if sources & SCIENTIFIC_SOURCES:
        tags.append("Научная публикация")
    if corroboration is not None and corroboration.citation_growth:
        tags.append("Рост цитирований")
    if "github" in sources:
        tags.append("Код в открытом доступе")
    if dates and (now - max(_aware(d) for d in dates)).days <= FRESH_DAYS:
        tags.append("Свежая публикация")
    return tags


def _publication_key(candidate: SignalCandidate) -> str:
    return re.sub(r"\W+", " ", (candidate.title or "").lower()).strip()


def _unique_publication_ids(group: DisplayGroup) -> list[int]:
    seen = {_publication_key(group.representative)}
    ids = list(group.representative.feed_item_ids)
    for member in group.members:
        key = _publication_key(member)
        if key not in seen:
            seen.add(key)
            ids.extend(member.feed_item_ids)
    return ids


def _dedupe_publications(pairs: list[tuple[SignalCandidate, ScoringResult]]):
    seen: set[str] = set()
    unique = []
    for candidate, result in pairs:
        key = _publication_key(candidate)
        if key not in seen:
            seen.add(key)
            unique.append((candidate, result))
    return unique


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _rank_key(result: ScoringResult) -> tuple[float, float]:
    return (result.explanation.get("relevance", 0.0), result.confidence)


def _was_scored(result: ScoringResult) -> bool:
    """True, если кандидат реально дошёл до модели (не отфильтрован на
    входе classifier.py по языку/длине текста — см. _clean_model_input).
    Такие кандидаты не показываем и на вкладке "Исключённые" — это не то
    же самое, что "модель посчитала зрелой технологией/шумом"."""
    return result.explanation.get("predicted_class") is not None


def _persist_signal(
    session: Session,
    q: SearchQuery,
    candidate: SignalCandidate,
    result: ScoringResult,
    *,
    feed_item_ids: list[int],
    status: str,
    classifier: SignalClassifier,
    llm_client: httpx.Client,
    allow_llm: bool = True,
    extra_sources: list[tuple[int, str]] = (),
) -> None:
    # Исключённые при поиске обогащаются только из кэша (бесплатно);
    # недостающее досчитывается лениво при открытии карточки.
    enrichment = enrich_cached(
        session, llm_client, candidate.feed_item_ids[0],
        candidate.title, candidate.summary or "", allow_llm=allow_llm,
    )

    explanation = dict(result.explanation)
    if enrichment is not None:
        explanation["enrichment_model"] = enrichment.model or ENRICHMENT_MODEL

    signal = Signal(
        query_id=q.id,
        title=candidate.title,
        description=enrichment.description if enrichment else None,
        problem=enrichment.problem if enrichment else None,
        potential_advantage=enrichment.potential_advantage if enrichment else None,
        case_example=enrichment.case_example if enrichment else None,
        weak_criteria=enrichment.weak_criteria if enrichment else None,
        manifestations=enrichment.manifestations if enrichment else None,
        stage="Ранняя стадия" if status == "included" else None,
        score=result.confidence,
        is_mainstream=_is_mainstream(result),
        status=status,
        explanation=explanation,
        model_version=getattr(classifier, "model_version", "unknown"),
    )
    session.add(signal)
    session.flush()
    primary_feed_item_id = candidate.feed_item_ids[0]
    linked = [
        (fid, "primary" if fid == primary_feed_item_id else "similar") for fid in feed_item_ids
    ] + list(extra_sources)
    seen: set[int] = set()
    for feed_item_id, relation in linked:
        if feed_item_id in seen:
            continue
        seen.add(feed_item_id)
        session.add(SignalSource(
            signal_id=signal.id,
            feed_item_id=feed_item_id,
            is_primary=(feed_item_id == primary_feed_item_id),
            relation=relation,
        ))


def run_search(
    session: Session, query_id: int, classifier: SignalClassifier = DEFAULT_CLASSIFIER,
) -> None:
    """Исключения ловятся здесь и пишутся в SearchQuery.error. Отмена —
    кооперативная: cancel_search() ставит отметку, а пайплайн сам проверяет
    её в нескольких точках (перед live-поиском и перед каждым LLM-вызовом)
    и останавливается, откатывая ещё не закоммиченные сигналы этого прогона.
    """
    q = session.get(SearchQuery, query_id)
    if q is None:
        log.error("search_query %s не найден", query_id)
        return

    q.status = "running"
    q.phase = "collecting"
    session.commit()

    try:
        _check_cancelled(query_id)

        search_query_text = q.query_text
        if _detect_language(q.query_text) != "EN" and translation_available():
            with httpx.Client() as translate_client:
                translated = translate_query_to_english(translate_client, q.query_text)
            if translated:
                log.info("запрос переведён для поиска: %r -> %r", q.query_text, translated)
                search_query_text = translated

        db_candidates = find_candidates(
            session, search_query_text, limit=SEARCH_CANDIDATE_LIMIT,
            date_from=q.date_from, date_to=q.date_to,
        )
        if search_query_text != q.query_text:
            seen = {c.feed_item_ids[0] for c in db_candidates}
            db_candidates += [
                c for c in find_candidates(
                    session, q.query_text, limit=SEARCH_CANDIDATE_LIMIT,
                    date_from=q.date_from, date_to=q.date_to,
                )
                if c.feed_item_ids[0] not in seen
            ]
        candidates = list(db_candidates)
        seen_feed_item_ids = {c.feed_item_ids[0] for c in candidates}

        live_items = fetch_all_live(
            search_query_text, q.date_from, q.date_to, original_query=q.query_text,
        )
        live_feed_items = persist_live_items(session, live_items)
        report_items = persist_live_items(
            session, fetch_analyst_reports(search_query_text, q.query_text, q.date_from, q.date_to),
        )
        for fi in live_feed_items:
            if fi.id not in seen_feed_item_ids:
                candidates.append(_feed_item_to_candidate(fi))
                seen_feed_item_ids.add(fi.id)

        q.candidates_found = len(candidates)
        q.sources_processed = len(db_candidates) + len(live_items)
        session.commit()

        q.phase = "scoring"
        session.commit()

        if hasattr(classifier, "score_batch"):
            results = classifier.score_batch(q.query_text, candidates)
        else:
            results = [classifier.score(c) for c in candidates]
        scored = list(zip(candidates, results))
        q.signals_above_75 = sum(1 for _, r in scored if r.confidence >= 0.75)

        passed = [
            (c, r) for c, r in scored
            if r.is_weak_signal and r.confidence >= SIGNAL_SCORE_THRESHOLD
        ]
        passed.sort(key=lambda pair: _rank_key(pair[1]), reverse=True)

        passed_ids = {id(c) for c, _ in passed}
        rejected = [(c, r) for c, r in scored if _was_scored(r) and id(c) not in passed_ids]
        rejected.sort(
            key=lambda pair: (pair[1].explanation.get("enough_text", True), *_rank_key(pair[1])),
            reverse=True,
        )
        rejected = _dedupe_publications(rejected)[:SEARCH_EXCLUDED_LIMIT]

        q.phase = "ranking"
        session.commit()

        groups = group_for_display(classifier, passed)
        groups.sort(key=lambda g: _rank_key(g.result), reverse=True)
        top_groups = groups[:SEARCH_TOP_N]

        _check_cancelled(query_id)
        primary_urls = [
            (session.get(FeedItem, g.representative.feed_item_ids[0]).url or "") for g in top_groups
        ]
        corroborations = corroborate(
            session, getattr(classifier, "encoder", None), top_groups, candidates, primary_urls,
            reports=[_feed_item_to_candidate(fi) for fi in report_items],
            queries=list(dict.fromkeys([q.query_text, search_query_text])),
        )

        with httpx.Client() as llm_client:
            for group, corroboration in zip(top_groups, corroborations):
                _check_cancelled(query_id)
                if "indicators" in group.result.explanation:
                    group.result.explanation["key_predictors"] = _signal_predictors(group, corroboration)
                _persist_signal(
                    session, q, group.representative, group.result,
                    feed_item_ids=_unique_publication_ids(group), status="included",
                    classifier=classifier, llm_client=llm_client,
                    extra_sources=corroboration.sources,
                )
            for candidate, result in rejected:
                _check_cancelled(query_id)
                _persist_signal(
                    session, q, candidate, result,
                    feed_item_ids=candidate.feed_item_ids, status="excluded",
                    classifier=classifier, llm_client=llm_client, allow_llm=False,
                )

        q.status = "done"
        q.phase = "done"
        q.finished_at = datetime.now(timezone.utc)
        session.commit()

    except Exception as exc:
        session.rollback()
        q = session.get(SearchQuery, query_id)
        if q is not None:
            q.status = "failed"
            q.error = (
                "Поиск остановлен пользователем" if isinstance(exc, _SearchCancelled)
                else str(exc)[:1000]
            )
            q.finished_at = datetime.now(timezone.utc)
            session.commit()
        if isinstance(exc, _SearchCancelled):
            log.info("поиск query_id=%s остановлен пользователем", query_id)
        else:
            log.error("пайплайн упал для query_id=%s: %s", query_id, exc)

    finally:
        _cancelled_queries.discard(query_id)
