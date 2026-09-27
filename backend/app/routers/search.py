"""POST /search — открытый запрос → пайплайн → ТОП-15.
GET /search/{id}/status
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import SearchQuery, SessionLocal
from ..deps import get_session
from ..pipeline.orchestrator import run_search
from ..presenters import signal_to_out
from ..schemas import SearchCreatedResponse, SearchRequest, SearchStatusResponse

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
    q = SearchQuery(query_text=body.query, status="pending")
    session.add(q)
    session.commit()
    session.refresh(q)

    background_tasks.add_task(_run_search_job, q.id)
    return SearchCreatedResponse(query_id=q.id, status=q.status)


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
        sources_processed=q.sources_processed,
        candidates_found=q.candidates_found,
        signals_above_75=q.signals_above_75,
        error=q.error,
        results=results,
        excluded=excluded,
    )
