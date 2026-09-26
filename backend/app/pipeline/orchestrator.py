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

from ..config import (
    MODEL_PATH,
    OLLAMA_MODEL,
    SEARCH_CANDIDATE_LIMIT,
    SEARCH_EXCLUDED_LIMIT,
    SEARCH_TOP_N,
    SIGNAL_SCORE_THRESHOLD,
)
from ..db import FeedItem, SearchQuery, Signal, SignalSource
from .candidates import find_candidates
from .classifier import LABEL_MATURE, ScoringResult, SignalCandidate, SignalClassifier, TrainedModelClassifier
from .display_grouping import group_for_display
from .enrichment import enrich_signal, enrichment_available, translate_query_to_english
from .live_sources import _detect_language, fetch_all_live, persist_live_items

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


def _was_scored(result: ScoringResult) -> bool:
    """True, если кандидат реально дошёл до модели (не отфильтрован на
    входе classifier.py по языку/длине текста — см. _clean_model_input).
    Такие "неоценённые" кандидаты не показываем и на вкладке "Исключённые":
    это не то же самое, что "модель посчитала зрелой технологией/шумом"."""
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
) -> None:
    enrichment = enrich_signal(llm_client, candidate.title, candidate.summary or "")

    explanation = dict(result.explanation)
    if enrichment is not None:
        explanation["enrichment_model"] = OLLAMA_MODEL

    signal = Signal(
        query_id=q.id,
        title=candidate.title,
        description=enrichment.description if enrichment else None,
        potential_advantage=enrichment.potential_advantage if enrichment else None,
        case_example=enrichment.case_example if enrichment else None,
        # Модель — только 3-классовый классификатор, стадию не предсказывает
        # (см. classifier.py). Не фабрикуем ложную точность: для прошедших
        # порог сигналов подписываем статично "Ранняя стадия" — это и есть
        # определение слабого сигнала по методологии, не гадание модели.
        stage="Ранняя стадия" if status == "included" else None,
        score=result.confidence,
        is_mainstream=_is_mainstream(result),
        status=status,
        explanation=explanation,
        model_version=getattr(classifier, "model_version", "unknown"),
    )
    session.add(signal)
    session.flush()  # нужен signal.id для SignalSource ниже
    # Представитель группы (candidate) — тот единственный источник, чей
    # текст реально ушёл в LLM и стал description/case_example. Помечаем
    # его как primary, чтобы фронт мог подписать "Где это уже проявилось"
    # именно платформой этого источника (arXiv/SiliconANGLE/...), а не
    # первым попавшимся в списке.
    primary_feed_item_id = candidate.feed_item_ids[0]
    for feed_item_id in feed_item_ids:
        session.add(SignalSource(
            signal_id=signal.id,
            feed_item_id=feed_item_id,
            is_primary=(feed_item_id == primary_feed_item_id),
        ))


def run_search(
    session: Session, query_id: int, classifier: SignalClassifier = DEFAULT_CLASSIFIER,
) -> None:
    """Выполнить пайплайн для уже созданной строки search_queries.

    Вызывается из BackgroundTasks — исключения не должны ронять процесс
    FastAPI, поэтому ловятся здесь и пишутся в SearchQuery.error, а не
    всплывают наружу (тот же принцип изоляции, что в RSS-collector:
    падение одного прогона не должно портить сервис целиком).

    phase — грубые этапы для модалки прогресса на фронте (макет: "Источники
    собраны" -> "Проверка стадии" -> "Формируем ТОП-15"). Отмена поиска
    сделана только на фронте (прекращение поллинга) — пайплайн здесь не
    проверяет никакого флага отмены и всегда доходит до конца.
    """
    q = session.get(SearchQuery, query_id)
    if q is None:
        log.error("search_query %s не найден", query_id)
        return

    q.status = "running"
    q.phase = "collecting"
    session.commit()

    try:
        # Поиск (find_candidates по накопленной БД + fetch_all_live) ищет
        # буквальные совпадения слов запроса — русский запрос почти
        # никогда не встретит англоязычные заголовки, а модель ниже всё
        # равно проверена только на английском (см. classifier.py), так
        # что даже найденный русскоязычный материал не дошёл бы до
        # скоринга. Переводим ЗАПРОС (не контент) на английский перед
        # поиском — единый языковой формат для матчинга. q.query_text
        # (оригинал, как ввёл пользователь) в БД и в выдаче не меняется,
        # переведённая версия используется только локально здесь.
        search_query_text = q.query_text
        if _detect_language(q.query_text) != "EN" and enrichment_available():
            with httpx.Client() as translate_client:
                translated = translate_query_to_english(translate_client, q.query_text)
            if translated:
                log.info("запрос переведён для поиска: %r -> %r", q.query_text, translated)
                search_query_text = translated

        db_candidates = find_candidates(session, search_query_text, limit=SEARCH_CANDIDATE_LIMIT)
        candidates = list(db_candidates)
        seen_feed_item_ids = {c.feed_item_ids[0] for c in candidates}

        # Живой поиск во внешних API (arXiv, Semantic Scholar, Crossref,
        # OpenAlex, GitHub, Hacker News — USPTO ODP/EPO OPS пропущены,
        # ключей не будет) — то самое "в реальном времени, не
        # ограничиваясь датасетом" из ТЗ. Найденное сразу пишется в
        # feed_items (обогащение БД для будущих поисков), не только
        # используется здесь.
        live_items = fetch_all_live(search_query_text)
        live_feed_items = persist_live_items(session, live_items)
        for fi in live_feed_items:
            if fi.id not in seen_feed_item_ids:
                candidates.append(_feed_item_to_candidate(fi))
                seen_feed_item_ids.add(fi.id)

        q.candidates_found = len(candidates)
        # "Обработано источников" — количество отдельных МАТЕРИАЛОВ
        # (публикаций/патентов/отчётов), которые система реально просмотрела,
        # а не количество разных платформ (было len({source_key}) — почти
        # всегда 1-3 при десятках найденных кандидатов, выглядело как явная
        # недосчёт). db_candidates — уже найденное в накопленной БД,
        # len(live_items) — сырое количество, вернувшееся от внешних API до
        # дедупа с уже увиденными записями.
        q.sources_processed = len(db_candidates) + len(live_items)
        session.commit()

        q.phase = "scoring"
        session.commit()

        scored = [(c, classifier.score(c)) for c in candidates]
        q.signals_above_75 = sum(1 for _, r in scored if r.confidence >= 0.75)

        passed = [(c, r) for c, r in scored if r.confidence >= SIGNAL_SCORE_THRESHOLD]
        passed.sort(key=lambda pair: pair[1].confidence, reverse=True)

        # Отклонённые, но реально оценённые моделью — топ-N по убыванию
        # оценки для вкладки "Исключённые" (причина = predicted_class +
        # key_predictors из explanation, читается на фронте).
        rejected = [
            (c, r) for c, r in scored
            if _was_scored(r) and (r.confidence < SIGNAL_SCORE_THRESHOLD or _is_mainstream(r))
        ]
        rejected.sort(key=lambda pair: pair[1].confidence, reverse=True)
        rejected = rejected[:SEARCH_EXCLUDED_LIMIT]

        q.phase = "ranking"
        session.commit()

        # Группировка похожих кандидатов ТОЛЬКО для отображения числа
        # источников на карточке — на уже отфильтрованном по порогу пуле,
        # не на сырых сотнях кандидатов (см. display_grouping.py). Скоринг
        # каждого кандидата уже посчитан индивидуально выше и не меняется.
        groups = group_for_display(classifier, passed)
        groups.sort(key=lambda g: g.result.confidence, reverse=True)
        top_groups = groups[:SEARCH_TOP_N]

        # LLM-обогащение (описание/преимущество/кейс-пример) — только для
        # финального топа и исключённых, не для всех сотен кандидатов (см.
        # enrichment.py). Один httpx.Client на весь пайплайн.
        with httpx.Client() as llm_client:
            for group in top_groups:
                _persist_signal(
                    session, q, group.representative, group.result,
                    feed_item_ids=group.feed_item_ids, status="included",
                    classifier=classifier, llm_client=llm_client,
                )
            for candidate, result in rejected:
                _persist_signal(
                    session, q, candidate, result,
                    feed_item_ids=candidate.feed_item_ids, status="excluded",
                    classifier=classifier, llm_client=llm_client,
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
            q.error = str(exc)[:1000]
            q.finished_at = datetime.now(timezone.utc)
            session.commit()
        log.error("пайплайн упал для query_id=%s: %s", query_id, exc)
