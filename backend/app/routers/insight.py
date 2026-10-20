"""GET /insight/{signal_id} — страница-отчёт по одному сигналу."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Signal, SourceSummary
from ..deps import get_session
from ..pipeline.enrichment_service import ensure_enriched
from ..pipeline.source_summary_service import source_summary
from ..presenters import signal_to_out
from ..schemas import SignalOut, SignalSourceDetailOut, SignalSourcesResponse

router = APIRouter(tags=["insight"])


def _get_signal(session: Session, signal_id: int) -> Signal:
    signal = session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="сигнал не найден")
    return signal


@router.get("/insight/{signal_id}", response_model=SignalOut)
def get_insight(signal_id: int, session: Session = Depends(get_session)) -> SignalOut:
    signal = _get_signal(session, signal_id)
    ensure_enriched(session, signal)
    return signal_to_out(signal)


@router.get("/insight/{signal_id}/sources", response_model=SignalSourcesResponse)
def get_insight_sources(signal_id: int, session: Session = Depends(get_session)) -> SignalSourcesResponse:
    signal = _get_signal(session, signal_id)
    base = {s.feed_item_id: s for s in signal_to_out(signal).sources}
    sources = []
    for ss in signal.sources:
        item = ss.feed_item
        extra = source_summary(item, session.get(SourceSummary, item.id))
        sources.append(SignalSourceDetailOut(**base[item.id].model_dump(), **extra))
    return SignalSourcesResponse(signal_id=signal.id, title=signal.title, sources=sources)
