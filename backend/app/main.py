"""FastAPI-приложение: регистрация роутеров, /health."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from sqlalchemy import text

# До импорта роутеров: они на импорте тянут pipeline.orchestrator, который
# грузит модель и логирует это по INFO — если настроить логирование позже,
# этот лог молча проглатывается дефолтным уровнем root-логгера (WARNING).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

from .db import engine
from .routers import insight, search

app = FastAPI(
    title="ЛЦТ 2026 — Слабые сигналы",
    description="API поиска зарождающихся технологических трендов",
)

app.include_router(search.router)
app.include_router(insight.router)


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
