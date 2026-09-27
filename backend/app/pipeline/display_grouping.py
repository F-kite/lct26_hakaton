"""Группировка кандидатов только для отображения числа источников на
карточке сигнала — не влияет на скоринг (оценка уже сделана в
classifier.score()). Группируем по близости к исходному seed-кандидату,
не к последнему добавленному — иначе цепное слипание разных тем.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.metrics.pairwise import cosine_similarity

from .classifier import ScoringResult, SignalCandidate, _clean_model_input

SIMILARITY_THRESHOLD = 0.35


@dataclass
class DisplayGroup:
    representative: SignalCandidate  # кандидат с максимальным score в группе
    result: ScoringResult            # его оценка — представляет группу целиком
    feed_item_ids: list[int]         # объединённые ID всех членов группы


def group_for_display(
    classifier,
    scored: list[tuple[SignalCandidate, ScoringResult]],
) -> list[DisplayGroup]:
    if not scored:
        return []

    texts = [_clean_model_input(c) or f"{c.title}. {c.summary or ''}" for c, _ in scored]
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
                }
            )

    return [
        DisplayGroup(
            representative=g["candidate"],
            result=g["result"],
            feed_item_ids=g["feed_item_ids"],
        )
        for g in groups
    ]
