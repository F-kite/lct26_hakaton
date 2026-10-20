"""FastAPI-приложение: регистрация роутеров, /health."""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

_log_dir = os.getenv("LOG_DIR")
if _log_dir:
    os.makedirs(_log_dir, exist_ok=True)
    _file_handler = TimedRotatingFileHandler(
        os.path.join(_log_dir, "backend.log"), when="midnight", backupCount=30, encoding="utf-8",
    )
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    ))
    for _name in ("", "uvicorn"):
        logging.getLogger(_name).addHandler(_file_handler)

from .config import FRONTEND_ORIGINS
from .db import engine
from .routers import insight, search

app = FastAPI(
    title="ЛЦТ 2026 — Слабые сигналы",
    description="API поиска зарождающихся технологических трендов",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(insight.router)


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
