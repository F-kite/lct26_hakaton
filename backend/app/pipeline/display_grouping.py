"""Группировка кандидатов только для отображения числа источников на
карточке сигнала — не влияет на скоринг (оценка уже сделана в
classifier.score()). Группируем по близости к исходному seed-кандидату,
не к последнему добавленному — иначе цепное слипание разных тем.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sklearn.metrics.pairwise import cosine_similarity

from .classifier import ScoringResult, SignalCandidate, _clean_model_input

SIMILARITY_THRESHOLD = 0.35


@dataclass
class DisplayGroup:
    representative: SignalCandidate  # кандидат с максимальным score в группе
    result: ScoringResult            # его оценка — представляет группу целиком
    feed_item_ids: list[int]         # объединённые ID всех членов группы
    members: list[SignalCandidate] = field(default_factory=list)  # все кандидаты группы


def group_for_display(
    classifier,
    scored: list[tuple[SignalCandidate, ScoringResult]],
) -> list[DisplayGroup]:
    if not scored:
        return []
    if not hasattr(classifier, "vectorize"):
        return _group_by_title(scored)

    texts =[_clean_model_input(c) or f"{c.title}. {c.summary or ''}" for c, _ in scored]
    vectors = classifier.vectorize(texts)

    groups: list[dict] = []
    for i, (candidate, result) in enumerate(scored):
        vec = vectors[i]
        best_group = None
        best_sim = 0.0
        for group in groups:
            sim = float(cosine_similarity(vec, group["seed_vec"])[0, 0])
            if sim > best_sim:
                best_sim = sim
                best_group = group

        if best_group is not None and best_sim >= SIMILARITY_THRESHOLD:
            best_group["feed_item_ids"].extend(candidate.feed_item_ids)
            best_group["members"].append(candidate)
            if result.confidence > best_group["result"].confidence:
                best_group["candidate"] = candidate
                best_group["result"] = result
        else:
            groups.append(
                {
                    "seed_vec": vec,
                    "candidate": candidate,
                    "result": result,
                    "feed_item_ids": list(candidate.feed_item_ids),
                    "members": [candidate],
                }
            )

    return [
        DisplayGroup(
            representative=g["candidate"],
            result=g["result"],
            feed_item_ids=g["feed_item_ids"],
            members=g["members"],
        )
        for g in groups
    ]


def _group_by_title(scored: list[tuple[SignalCandidate, ScoringResult]]) -> list[DisplayGroup]:
    """Модель v2 (без TF-IDF): склеиваем только одинаковые по названию записи,
    как SignalAnalyzer.rank у аналитика. E5-векторы для порога близости не
    годятся — у них почти любые тексты одной темы близки (косинус 0.77–0.87)."""
    groups: dict[str, DisplayGroup] = {}
    for candidate, result in scored:
        key = re.sub(r"\W+", " ", (candidate.title or "").lower()).strip()
        group = groups.get(key)
        if group is None:
            groups[key] = DisplayGroup(candidate, result, list(candidate.feed_item_ids), [candidate])
            continue
        group.feed_item_ids.extend(candidate.feed_item_ids)
        group.members.append(candidate)
        if result.confidence > group.result.confidence:
            group.representative, group.result = candidate, result
    return list(groups.values())
