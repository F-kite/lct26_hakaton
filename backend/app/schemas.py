"""Pydantic-схемы API.

Имена полей — английские (стандарт REST), содержимое — русское (ТЗ:
"вся аналитическая выдача и интерфейс — на русском языке").
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    # диапазон дат публикации, включительно; None — без границы с этой стороны
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "SearchRequest":
        if self.date_to is not None and self.date_to > date.today():
            self.date_to = date.today()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from не может быть позже date_to")
        return self


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
    source_type: str
    trust_level: str
    language: str
    published_at: datetime | None
    is_primary: bool
    relation: str | None = None


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    title: str
    area: str | None
    description: str | None
    problem: str | None
    potential_advantage: str | None
    case_example: str | None
    stage: str | None
    mention_trend: str | None
    score: float
    is_mainstream: bool
    status: str  # included | excluded — вкладка "Слабые сигналы"/"Исключённые"
    explanation: dict
    model_version: str
    created_at: datetime
    sources: list[SignalSourceOut]


class SearchStatusResponse(BaseModel):
    query_id: int
    query_text: str
    status: str
    phase: str | None  # collecting|scoring|ranking|done — шаги модалки прогресса
    date_from: date | None = None
    date_to: date | None = None
    sources_processed: int
    candidates_found: int
    signals_above_75: int
    error: str | None
    results: list[SignalOut] | None = None
    excluded: list[SignalOut] | None = None


class SummarySignalOut(BaseModel):
    signal_id: int
    title: str
    score: float
    reason: str | None = None


class SearchSummaryResponse(BaseModel):
    status: str
    queue_position: int | None = None
    overview: str | None = None
    key_signals: list[SummarySignalOut] = Field(default_factory=list)
    top_signals: list[SummarySignalOut] = Field(default_factory=list)
    model: str | None = None
    error: str | None = None
