"""GET /insight/{signal_id} — страница-отчёт по одному сигналу."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Signal
from ..deps import get_session
from ..pipeline.enrichment_service import ensure_enriched
from ..presenters import signal_to_out
from ..schemas import SignalOut

router = APIRouter(tags=["insight"])


@router.get("/insight/{signal_id}", response_model=SignalOut)
def get_insight(signal_id: int, session: Session = Depends(get_session)) -> SignalOut:
    signal = session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="сигнал не найден")
    ensure_enriched(session, signal)
    return signal_to_out(signal)
