"""Итоговый вывод по ТОП-15 поиска через GigaChat."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from typing import Literal

from sqlalchemy import select

from ..config import GIGACHAT_MODEL
from ..db import SearchQuery, SearchSummary, SessionLocal, Signal
from . import gigachat

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 3.0
KEY_SIGNALS_MAX = 3
DESCRIPTION_CHARS = 1500

QueueState = tuple[Literal["queued", "running"], int] | None

_queue: deque[int] = deque()
_running: int | None = None
_cond = threading.Condition()
_worker: threading.Thread | None = None


def enqueue(query_id: int) -> None:
    global _worker
    with _cond:
        if query_id == _running or query_id in _queue:
            return
        _queue.append(query_id)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work_loop, name="gigachat-summary", daemon=True)
            _worker.start()
        _cond.notify()


def queue_state(query_id: int) -> QueueState:
    with _cond:
        if query_id == _running:
            return ("running", 0)
        if query_id in _queue:
            ahead = list(_queue).index(query_id) + (1 if _running is not None else 0)
            return ("queued", ahead)
        return None


def _work_loop() -> None:
    global _running
    while True:
        with _cond:
            while not _queue:
                _cond.wait()
            _running = _queue.popleft()
        query_id = _running
        try:
            _process(query_id)
        except Exception:
            log.exception("summary: необработанная ошибка для запроса %s", query_id)
        finally:
            with _cond:
                _running = None


SYSTEM_PROMPT = (
    "Ты — аналитик технологической разведки банка. Тебе дают ТОП слабых сигналов — "
    "зарождающихся технологий, найденных сервисом по запросу пользователя. "
    "Пиши по-русски, деловым языком, без воды и без выдумок: опирайся только на "
    "переданные описания, не добавляй фактов, компаний и цифр, которых в них нет."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {
            "type": "string",
            "description": "3–4 предложения: какие направления и общие темы прослеживаются в найденных сигналах",
        },
        "key_signals": {
            "type": "array",
            "description": "2–3 самых значимых для запроса пользователя сигнала",
            "items": {
                "type": "object",
                "properties": {
                    "signal_id": {"type": "integer", "description": "id сигнала из списка"},
                    "reason": {"type": "string", "description": "одно предложение — почему он ключевой"},
                },
                "required": ["signal_id", "reason"],
            },
        },
    },
    "required": ["overview", "key_signals"],
}


_TAG_RE = re.compile(r"<[^>]+>")


def _signal_text(signal: Signal) -> str:
    primary = next((s for s in signal.sources if s.is_primary), signal.sources[0] if signal.sources else None)
    text = (primary.feed_item.summary if primary else None) or signal.description or ""
    text = " ".join(_TAG_RE.sub(" ", text).split())
    return text[:DESCRIPTION_CHARS]


def _build_prompt(query_text: str, signals: list[Signal]) -> str:
    lines = [f"Запрос пользователя: «{query_text}»", "", "Сигналы (id | уверенность модели | название | описание):"]
    for s in signals:
        lines.append(f"- {s.id} | {round(s.score * 100)}% | {s.title} | {_signal_text(s)}")
    lines += [
        "",
        "Задачи:",
        "1. overview — кратко обобщи, что найдено по запросу: какие направления и общие темы "
        "прослеживаются, чем они интересны как ранние сигналы.",
        f"2. key_signals — выбери 2–{KEY_SIGNALS_MAX} сигнала, наиболее значимых именно для этого запроса, "
        "и в одном предложении объясни выбор. Используй только id из списка выше.",
        "",
        "id — служебные номера, пользователь их не видит: не упоминай id и номера сигналов в тексте "
        "overview и reason. В reason сразу пиши суть, без «Сигнал значим, потому что…».",
    ]
    return "\n".join(lines)


def _store(query_id: int, *, status: str, overview: str | None = None,
           key_signals: list | None = None, error: str | None = None) -> None:
    with SessionLocal() as session:
        row = session.get(SearchSummary, query_id) or SearchSummary(query_id=query_id)
        row.status = status
        row.overview = overview
        row.key_signals = key_signals or []
        row.model = GIGACHAT_MODEL
        row.error = error
        session.add(row)
        session.commit()


def _process(query_id: int) -> None:
    with SessionLocal() as session:
        q = session.get(SearchQuery, query_id)
        if q is None:
            return
        signals = sorted(
            session.scalars(select(Signal).where(Signal.query_id == query_id, Signal.status == "included")),
            key=lambda s: s.score, reverse=True,
        )
        if not signals:
            return
        prompt = _build_prompt(q.query_text, signals)
        valid_ids = {s.id for s in signals}

    for attempt in range(MAX_ATTEMPTS):
        try:
            t0 = time.time()
            data = gigachat.chat_json(SYSTEM_PROMPT, prompt, SCHEMA)
            break
        except gigachat.GigaChatError as exc:
            if exc.retryable and attempt < MAX_ATTEMPTS - 1:
                wait = BACKOFF_BASE_S * 2**attempt
                log.warning("summary %s: %s, повтор через %.0fs", query_id, exc, wait)
                time.sleep(wait)
                continue
            log.error("summary %s: %s", query_id, exc)
            _store(query_id, status="failed", error=str(exc)[:500])
            return
        except Exception as exc:
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(BACKOFF_BASE_S * 2**attempt)
                continue
            log.error("summary %s: %s", query_id, exc)
            _store(query_id, status="failed", error=str(exc)[:500])
            return

    key_signals, seen = [], set()
    for item in data.get("key_signals") or []:
        sid = item.get("signal_id")
        if sid in valid_ids and sid not in seen and item.get("reason"):
            seen.add(sid)
            key_signals.append({"signal_id": sid, "reason": item["reason"].strip()})
    key_signals = key_signals[:KEY_SIGNALS_MAX]

    overview = (data.get("overview") or "").strip()
    if not overview:
        _store(query_id, status="failed", error="модель вернула пустой вывод")
        return
    _store(query_id, status="done", overview=overview, key_signals=key_signals)
    log.info("summary %s: готово за %.1fs, ключевых сигналов %d", query_id, time.time() - t0, len(key_signals))
