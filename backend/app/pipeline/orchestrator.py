"""Оркестрация: запрос -> кандидаты -> оценка моделью -> топ-N -> запись в БД.

Стыкует candidates.py (данные) и classifier.py (модель) — сам оркестратор
работает с Protocol SignalClassifier, не знает деталей конкретной модели.

DEFAULT_CLASSIFIER грузится на импорте модуля (при старте приложения) и
падает громко, если файл модели недоступен/битый — раньше здесь был тихий
откат на эвристику, но эвристику убрали совсем (см. classifier.py), так что
скрывать сбой загрузки молчаливой деградацией больше нечем и незачем:
лучше сервис не поднимется и будет сразу видно, что не так, чем он молча
станет отвечать пустыми результатами.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..config import MODEL_PATH, SEARCH_CANDIDATE_LIMIT, SEARCH_TOP_N, SIGNAL_SCORE_THRESHOLD, YANDEX_GPT_MODEL
from ..db import FeedItem, SearchQuery, Signal, SignalSource
from .candidates import find_candidates
from .classifier import LABEL_MATURE, SignalCandidate, SignalClassifier, TrainedModelClassifier
from .enrichment import enrich_signal
from .live_sources import fetch_all_live, persist_live_items

log = logging.getLogger(__name__)

DEFAULT_CLASSIFIER: SignalClassifier = TrainedModelClassifier(MODEL_PATH)


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


def run_search(
    session: Session, query_id: int, classifier: SignalClassifier = DEFAULT_CLASSIFIER,
) -> None:
    """Выполнить пайплайн для уже созданной строки search_queries.

    Вызывается из BackgroundTasks — исключения не должны ронять процесс
    FastAPI, поэтому ловятся здесь и пишутся в SearchQuery.error, а не
    всплывают наружу (тот же принцип изоляции, что в RSS-collector:
    падение одного прогона не должно портить сервис целиком).
    """
    q = session.get(SearchQuery, query_id)
    if q is None:
        log.error("search_query %s не найден", query_id)
        return

    q.status = "running"
    session.commit()

    try:
        candidates = find_candidates(session, q.query_text, limit=SEARCH_CANDIDATE_LIMIT)
        seen_feed_item_ids = {c.feed_item_ids[0] for c in candidates}

        # Живой поиск во внешних API (arXiv, Semantic Scholar, Crossref,
        # USPTO ODP, EPO OPS — последние два молча пропускают себя без
        # ключа) — то самое "в реальном времени, не ограничиваясь
        # датасетом" из ТЗ. Найденное сразу пишется в feed_items
        # (обогащение БД для будущих поисков), не только используется здесь.
        live_items = fetch_all_live(q.query_text)
        live_feed_items = persist_live_items(session, live_items)
        for fi in live_feed_items:
            if fi.id not in seen_feed_item_ids:
                candidates.append(_feed_item_to_candidate(fi))
                seen_feed_item_ids.add(fi.id)

        q.candidates_found = len(candidates)
        q.sources_processed = len({s for c in candidates for s in c.sources})
        session.commit()

        scored = [(c, classifier.score(c)) for c in candidates]
        q.signals_above_75 = sum(1 for _, r in scored if r.confidence >= 0.75)

        passed = [(c, r) for c, r in scored if r.confidence >= SIGNAL_SCORE_THRESHOLD]
        passed.sort(key=lambda pair: pair[1].confidence, reverse=True)

        # LLM-обогащение (описание/преимущество/кейс-пример) — только для
        # финальных топ-N, не для всех сотен кандидатов (см. enrichment.py).
        # Один httpx.Client на весь топ-N, не на каждый сигнал отдельно.
        with httpx.Client() as llm_client:
            for candidate, result in passed[:SEARCH_TOP_N]:
                enrichment = enrich_signal(llm_client, candidate.title, candidate.summary or "")

                explanation = dict(result.explanation)
                if enrichment is not None:
                    explanation["enrichment_model"] = YANDEX_GPT_MODEL

                signal = Signal(
                    query_id=q.id,
                    title=candidate.title,
                    description=enrichment.description if enrichment else None,
                    potential_advantage=enrichment.potential_advantage if enrichment else None,
                    case_example=enrichment.case_example if enrichment else None,
                    stage=result.stage,
                    score=result.confidence,
                    is_mainstream=_is_mainstream(result),
                    explanation=explanation,
                    model_version=getattr(classifier, "model_version", "unknown"),
                )
                session.add(signal)
                session.flush()  # нужен signal.id для SignalSource ниже
                for feed_item_id in candidate.feed_item_ids:
                    session.add(SignalSource(signal_id=signal.id, feed_item_id=feed_item_id))

        q.status = "done"
        q.finished_at = datetime.now(timezone.utc)
        session.commit()

    except Exception as exc:
        session.rollback()
        q = session.get(SearchQuery, query_id)
        if q is not None:
            q.status = "failed"
            q.error = str(exc)[:1000]
            q.finished_at = datetime.now(timezone.utc)
            session.commit()
        log.error("пайплайн упал для query_id=%s: %s", query_id, exc)
