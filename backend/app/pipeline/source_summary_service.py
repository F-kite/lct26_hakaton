"""Русскоязычные резюме источников, оценки аналитиков и сводная оценка — лениво, через общую очередь."""

from __future__ import annotations

import logging
import re
import threading
from collections import deque
from typing import Callable

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import ENRICHMENT_MODEL
from ..db import AnalystAssessment, FeedItem, SessionLocal, Signal, SourceSummary
from .enrichment import assess_report_ru, gigachat_ready, summarize_reports_ru, summarize_source_ru

log = logging.getLogger(__name__)

MIN_TEXT_WORDS = 15
ORIGINAL_CHARS = 400

_TAG_RE = re.compile(r"<[^>]+>")

_queue: deque[tuple[str, Callable[[], None]]] = deque()
_queued: set[str] = set()
_cond = threading.Condition()
_worker: threading.Thread | None = None


def clean_text(text: str | None) -> str:
    return " ".join(_TAG_RE.sub(" ", text or "").split())


def _enqueue(key: str, task: Callable[[], None]) -> None:
    global _worker
    with _cond:
        if key in _queued:
            return
        _queued.add(key)
        _queue.append((key, task))
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work_loop, name="ai-texts", daemon=True)
            _worker.start()
        _cond.notify()


def is_queued(key: str) -> bool:
    with _cond:
        return key in _queued


def _work_loop() -> None:
    while True:
        with _cond:
            while not _queue:
                _cond.wait()
            key, task = _queue.popleft()
        try:
            task()
        except Exception:
            log.exception("%s: необработанная ошибка", key)
        finally:
            with _cond:
                _queued.discard(key)


def _upsert(model_cls, feed_item_id: int, values: dict) -> None:
    stmt = pg_insert(model_cls).values(feed_item_id=feed_item_id, **values)
    stmt = stmt.on_conflict_do_update(index_elements=[model_cls.feed_item_id], set_=values)
    with SessionLocal() as session:
        session.execute(stmt)
        session.commit()


def _stale(model: str | None) -> bool:
    """Ответ запасной модели пересоздаём, когда основная снова доступна."""
    return model != ENRICHMENT_MODEL and gigachat_ready()


def _load_item(feed_item_id: int) -> tuple[str, str] | None:
    with SessionLocal() as session:
        item = session.get(FeedItem, feed_item_id)
        return (item.title, clean_text(item.summary)) if item else None


# ---------- резюме источника ----------

def source_summary(item: FeedItem, cached: SourceSummary | None) -> dict:
    """Резюме для карточки источника и его статус: ready | pending | original | none."""
    text = clean_text(item.summary)
    if item.language == "RU":
        if not text:
            return {"summary": None, "summary_model": None, "summary_status": "none"}
        short = text if len(text) <= ORIGINAL_CHARS else text[:ORIGINAL_CHARS].rsplit(" ", 1)[0] + "…"
        return {"summary": short, "summary_model": None, "summary_status": "original"}
    if cached is not None:
        if _stale(cached.model):
            fid = item.id
            _enqueue(f"summary:{fid}", lambda: _make_summary(fid))
        return {"summary": cached.summary, "summary_model": cached.model, "summary_status": "ready"}
    if len(text.split()) < MIN_TEXT_WORDS:
        return {"summary": None, "summary_model": None, "summary_status": "none"}
    fid = item.id
    _enqueue(f"summary:{fid}", lambda: _make_summary(fid))
    return {"summary": None, "summary_model": None, "summary_status": "pending"}


def _make_summary(feed_item_id: int) -> None:
    loaded = _load_item(feed_item_id)
    if loaded is None:
        return
    with httpx.Client() as client:
        result = summarize_source_ru(client, *loaded)
    if result:
        _upsert(SourceSummary, feed_item_id, {"summary": result[0], "model": result[1]})


# ---------- оценка аналитиков по отчёту ----------

def analyst_assessment(item: FeedItem, cached: AnalystAssessment | None) -> dict:
    if cached is not None:
        if _stale(cached.model):
            fid = item.id
            _enqueue(f"assessment:{fid}", lambda: _make_assessment(fid))
        return {"summary": cached.assessment, "summary_model": cached.model, "summary_status": "ready"}
    if len(clean_text(item.summary).split()) < MIN_TEXT_WORDS:
        return {"summary": None, "summary_model": None, "summary_status": "none"}
    fid = item.id
    _enqueue(f"assessment:{fid}", lambda: _make_assessment(fid))
    return {"summary": None, "summary_model": None, "summary_status": "pending"}


def _make_assessment(feed_item_id: int) -> None:
    loaded = _load_item(feed_item_id)
    if loaded is None:
        return
    with httpx.Client() as client:
        result = assess_report_ru(client, *loaded)
    if result:
        _upsert(AnalystAssessment, feed_item_id, {"assessment": result[0], "model": result[1]})


# ---------- сводная оценка по отчётам сигнала ----------

def reports_summary(signal: Signal, report_ids: list[int]) -> dict:
    """status: ready | pending | none; при ready — stage/first_applications/mass_adoption + model."""
    if not report_ids:
        return {"status": "none"}
    cached = signal.analyst_summary or {}
    signal_id, ids = signal.id, sorted(report_ids)
    key = f"reports:{signal_id}"
    if cached.get("report_ids") == ids:
        if _stale(cached.get("model")) and not is_queued(key):
            _enqueue(key, lambda: _make_reports_summary(signal_id, ids))
        return {"status": "ready", **{k: cached[k] for k in ("stage", "first_applications", "mass_adoption", "model")}}
    if not is_queued(key):
        _enqueue(key, lambda: _make_reports_summary(signal_id, ids))
    return {"status": "pending"}


def _make_reports_summary(signal_id: int, report_ids: list[int]) -> None:
    with SessionLocal() as session:
        signal = session.get(Signal, signal_id)
        items = [session.get(FeedItem, i) for i in report_ids]
        technology = signal.title if signal else ""
        reports = [(i.title, clean_text(i.summary)) for i in items if i]
    with httpx.Client() as client:
        result = summarize_reports_ru(client, technology, reports)
    if result is None:
        return
    summary, model = result
    with SessionLocal() as session:
        signal = session.get(Signal, signal_id)
        if signal is not None:
            signal.analyst_summary = {**summary, "model": model, "report_ids": report_ids}
            session.commit()
