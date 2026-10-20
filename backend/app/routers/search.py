"""POST /search — открытый запрос → пайплайн → ТОП-15.
GET /search/{id}/status
GET /search/{id}/summary — итоговый вывод GigaChat по ТОП-15
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import SearchQuery, SearchSummary, SessionLocal
from ..deps import get_session
from ..pipeline import gigachat, summary_service
from ..pipeline.orchestrator import cancel_search, run_search
from ..presenters import signal_to_out
from ..schemas import (
    SearchCreatedResponse,
    SearchRequest,
    SearchStatusResponse,
    SearchSummaryResponse,
    SummarySignalOut,
)

router = APIRouter(tags=["search"])


def _run_search_job(query_id: int) -> None:
    """Отдельная сессия — BackgroundTasks выполняется уже после того, как
    ответ ушёл клиенту, к этому моменту сессия из запроса уже закрыта."""
    session = SessionLocal()
    try:
        run_search(session, query_id)
    finally:
        session.close()


@router.post("/search", response_model=SearchCreatedResponse)
def create_search(
    body: SearchRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> SearchCreatedResponse:
    q = SearchQuery(
        query_text=body.query, status="pending", date_from=body.date_from, date_to=body.date_to,
    )
    session.add(q)
    session.commit()
    session.refresh(q)

    background_tasks.add_task(_run_search_job, q.id)
    return SearchCreatedResponse(query_id=q.id, status=q.status)


@router.post("/search/{query_id}/cancel", status_code=204, response_model=None)
def cancel_search_endpoint(query_id: int, session: Session = Depends(get_session)) -> None:
    q = session.get(SearchQuery, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="запрос не найден")
    cancel_search(query_id)


TOP_SIGNALS_COUNT = 3


def _summary_response(q: SearchQuery, session: Session) -> SearchSummaryResponse:
    if q.status != "done":
        return SearchSummaryResponse(status="pending")
    included = sorted((s for s in q.signals if s.status == "included"), key=lambda s: s.score, reverse=True)
    if not included:
        return SearchSummaryResponse(status="empty")
    by_id = {s.id: s for s in included}
    top = [SummarySignalOut(signal_id=s.id, title=s.title, score=s.score) for s in included[:TOP_SIGNALS_COUNT]]
    if not gigachat.is_configured():
        return SearchSummaryResponse(status="disabled", top_signals=top)

    # сначала очередь, потом БД: исполнитель пишет результат до того, как
    # снимает «running», так что готовый вывод не будет поставлен повторно
    state = summary_service.queue_state(q.id)
    if state is not None:
        status, ahead = state
        return SearchSummaryResponse(status=status, queue_position=ahead, top_signals=top)

    row = session.get(SearchSummary, q.id)
    if row is None:
        summary_service.enqueue(q.id)
        status, ahead = summary_service.queue_state(q.id) or ("queued", 0)
        return SearchSummaryResponse(status=status, queue_position=ahead, top_signals=top)

    key = [
        SummarySignalOut(signal_id=k["signal_id"], title=by_id[k["signal_id"]].title,
                         score=by_id[k["signal_id"]].score, reason=k.get("reason"))
        for k in row.key_signals if k.get("signal_id") in by_id
    ]
    return SearchSummaryResponse(
        status=row.status, overview=row.overview, key_signals=key, top_signals=top,
        model=row.model, error=row.error,
    )


@router.get("/search/{query_id}/summary", response_model=SearchSummaryResponse)
def get_search_summary(query_id: int, session: Session = Depends(get_session)) -> SearchSummaryResponse:
    """Вывод по ТОП-15. Первое обращение ставит генерацию в очередь —
    фронтенд опрашивает, пока статус не станет done/failed."""
    q = session.get(SearchQuery, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="запрос не найден")
    return _summary_response(q, session)


@router.post("/search/{query_id}/summary/retry", response_model=SearchSummaryResponse)
def retry_search_summary(query_id: int, session: Session = Depends(get_session)) -> SearchSummaryResponse:
    q = session.get(SearchQuery, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="запрос не найден")
    row = session.get(SearchSummary, query_id)
    if row is not None and row.status == "failed":
        session.delete(row)
        session.commit()
    return _summary_response(q, session)


@router.get("/search/{query_id}/status", response_model=SearchStatusResponse)
def get_search_status(query_id: int, session: Session = Depends(get_session)) -> SearchStatusResponse:
    q = session.get(SearchQuery, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="запрос не найден")

    results = None
    excluded = None
    if q.status == "done":
        results = [signal_to_out(s) for s in q.signals if s.status == "included"]
        excluded = [signal_to_out(s) for s in q.signals if s.status == "excluded"]

    return SearchStatusResponse(
        query_id=q.id,
        query_text=q.query_text,
        status=q.status,
        phase=q.phase,
        date_from=q.date_from,
        date_to=q.date_to,
        sources_processed=q.sources_processed,
        candidates_found=q.candidates_found,
        signals_above_75=q.signals_above_75,
        error=q.error,
        results=results,
        excluded=excluded,
    )
