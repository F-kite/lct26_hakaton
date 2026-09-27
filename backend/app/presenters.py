"""Сборка Pydantic-ответа из ORM Signal — общее для /search и /insight,
чтобы форма ответа не разошлась между двумя эндпоинтами.
"""

from __future__ import annotations

from .db import Signal
from .schemas import SignalOut, SignalSourceOut


def signal_to_out(signal: Signal) -> SignalOut:
    sources = [
        SignalSourceOut(
            feed_item_id=ss.feed_item.id,
            title=ss.feed_item.title,
            url=ss.feed_item.url,
            source_key=ss.feed_item.source.key,
            source_name=ss.feed_item.source.name,
            source_type=ss.feed_item.source_type,
            trust_level=ss.feed_item.trust_level,
            language=ss.feed_item.language,
            published_at=ss.feed_item.published_at,
            is_primary=ss.is_primary,
        )
        for ss in signal.sources
    ]
    return SignalOut(
        id=signal.id,
        title=signal.title,
        area=signal.area,
        description=signal.description,
        problem=signal.problem,
        potential_advantage=signal.potential_advantage,
        case_example=signal.case_example,
        stage=signal.stage,
        mention_trend=signal.mention_trend,
        score=signal.score,
        is_mainstream=signal.is_mainstream,
        status=signal.status,
        explanation=signal.explanation,
        model_version=signal.model_version,
        created_at=signal.created_at,
        sources=sources,
    )
