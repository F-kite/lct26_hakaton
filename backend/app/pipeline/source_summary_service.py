"""Русскоязычные резюме источников сигнала — лениво, через общую очередь."""

from __future__ import annotations

import logging
import re
import threading
from collections import deque

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import FeedItem, SessionLocal, SourceSummary
from .enrichment import summarize_source_ru

log = logging.getLogger(__name__)

MIN_TEXT_WORDS = 15
ORIGINAL_CHARS = 400

_TAG_RE = re.compile(r"<[^>]+>")

_queue: deque[int] = deque()
_queued: set[int] = set()
_cond = threading.Condition()
_worker: threading.Thread | None = None


def clean_text(text: str | None) -> str:
    return " ".join(_TAG_RE.sub(" ", text or "").split())


def source_summary(item: FeedItem, cached: SourceSummary | None) -> dict:
    """Резюме для карточки источника и его статус: ready | pending | original | none."""
    text = clean_text(item.summary)
    if item.language == "RU":
        if not text:
            return {"summary": None, "summary_model": None, "summary_status": "none"}
        short = text if len(text) <= ORIGINAL_CHARS else text[:ORIGINAL_CHARS].rsplit(" ", 1)[0] + "…"
        return {"summary": short, "summary_model": None, "summary_status": "original"}
    if cached is not None:
        return {"summary": cached.summary, "summary_model": cached.model, "summary_status": "ready"}
    if len(text.split()) < MIN_TEXT_WORDS:
        return {"summary": None, "summary_model": None, "summary_status": "none"}
    enqueue(item.id)
    return {"summary": None, "summary_model": None, "summary_status": "pending"}


def enqueue(feed_item_id: int) -> None:
    global _worker
    with _cond:
        if feed_item_id in _queued:
            return
        _queued.add(feed_item_id)
        _queue.append(feed_item_id)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work_loop, name="source-summary", daemon=True)
            _worker.start()
        _cond.notify()


def _work_loop() -> None:
    while True:
        with _cond:
            while not _queue:
                _cond.wait()
            feed_item_id = _queue.popleft()
        try:
            _process(feed_item_id)
        except Exception:
            log.exception("резюме источника %s: необработанная ошибка", feed_item_id)
        finally:
            with _cond:
                _queued.discard(feed_item_id)


def _process(feed_item_id: int) -> None:
    with SessionLocal() as session:
        if session.get(SourceSummary, feed_item_id) is not None:
            return
        item = session.get(FeedItem, feed_item_id)
        if item is None:
            return
        title, text = item.title, clean_text(item.summary)

    with httpx.Client() as client:
        result = summarize_source_ru(client, title, text)
    if result is None:
        return
    summary, model = result
    stmt = pg_insert(SourceSummary).values(feed_item_id=feed_item_id, model=model, summary=summary)
    stmt = stmt.on_conflict_do_update(
        index_elements=[SourceSummary.feed_item_id], set_={"model": model, "summary": summary},
    )
    with SessionLocal() as session:
        session.execute(stmt)
        session.commit()
