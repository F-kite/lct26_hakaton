"""GET /insight/{signal_id} — страница-отчёт по одному сигналу."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import AnalystAssessment, Signal, SourceSummary
from ..deps import get_session
from ..pipeline.enrichment_service import ensure_enriched
from ..pipeline.live_sources import _CJK_RE
from ..pipeline.source_summary_service import analyst_assessment, reports_summary, source_summary
from ..presenters import signal_to_out
from ..schemas import AnalystsResponse, SignalOut, SignalSourceDetailOut, SignalSourcesResponse

router = APIRouter(tags=["insight"])


def _is_assessment(relation: str | None) -> bool:
    return bool(relation) and relation.startswith("assessment")


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
        if _is_assessment(ss.relation):
            continue
        item = ss.feed_item
        extra = source_summary(item, session.get(SourceSummary, item.id))
        sources.append(SignalSourceDetailOut(**base[item.id].model_dump(), **extra))
    return SignalSourcesResponse(signal_id=signal.id, title=signal.title, sources=sources)


@router.get("/insight/{signal_id}/analysts", response_model=AnalystsResponse)
def get_insight_analysts(signal_id: int, session: Session = Depends(get_session)) -> AnalystsResponse:
    signal = _get_signal(session, signal_id)
    base = {s.feed_item_id: s for s in signal_to_out(signal).sources}
    links = [ss for ss in signal.sources if _is_assessment(ss.relation) and not _CJK_RE.search(ss.feed_item.title or "")]
    reports = []
    for ss in links:
        item = ss.feed_item
        extra = analyst_assessment(item, session.get(AnalystAssessment, item.id))
        reports.append(SignalSourceDetailOut(**base[item.id].model_dump(), **extra))
    scope = "none" if not links else ("signal" if any(ss.relation == "assessment" for ss in links) else "topic")
    return AnalystsResponse(
        signal_id=signal.id, title=signal.title, scope=scope, reports=reports,
        summary=reports_summary(signal, [ss.feed_item_id for ss in links]),
    )
