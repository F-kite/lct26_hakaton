"""Pydantic-схемы API.

Имена полей — английские (стандарт REST), содержимое — русское (ТЗ:
"вся аналитическая выдача и интерфейс — на русском языке").
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class SearchCreatedResponse(BaseModel):
    query_id: int
    status: str


class SignalSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feed_item_id: int
    title: str
    url: str
    source_key: str
    source_name: str
    trust_level: str
    published_at: datetime | None


class SignalOut(BaseModel):
    # protected_namespaces=() — иначе pydantic ругается на поле model_version
    # (по умолчанию резервирует префикс "model_" для своих внутренних методов)
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    title: str
    area: str | None
    description: str | None
    potential_advantage: str | None
    case_example: str | None
    stage: str | None
    mention_trend: str | None
    score: float
    is_mainstream: bool
    explanation: dict
    model_version: str
    created_at: datetime
    sources: list[SignalSourceOut]


class SearchStatusResponse(BaseModel):
    query_id: int
    query_text: str
    status: str
    sources_processed: int
    candidates_found: int
    signals_above_75: int
    error: str | None
    results: list[SignalOut] | None = None
