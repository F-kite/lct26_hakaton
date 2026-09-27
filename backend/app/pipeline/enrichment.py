"""LLM-обогащение сигналов, прошедших модель: описание, решаемая проблема,
преимущество, кейс-пример. Вызывается только для кандидатов в топ-N — не
тратить инференс на все кандидаты.

Локальная Qwen2.5 через Ollama.
"""

from __future__ import annotations

import json
import logging

import httpx

from ..config import OLLAMA_BASE_URL, OLLAMA_MODEL

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 120.0 

_SYSTEM_PROMPT = (
    "Ты помогаешь анализировать технологические тренды для аналитического сервиса. "
    "На основе ТОЛЬКО предоставленного текста статьи — без использования собственных "
    "общих знаний о предмете — сформулируй четыре коротких пункта на русском языке: "
    "описание технологии (что это), какую проблему она решает (конкретное ограничение "
    "или сложность, которую устраняет технология — должно ОТЛИЧАТЬСЯ от описания, не "
    "повторяй его другими словами), потенциальное преимущество (какую пользу даёт), "
    "кейс-пример (конкретный факт применения из текста — компания, продукт, пилот). "
    "Если в тексте нет данных для какого-то пункта — напиши \"не указано в источнике\" "
    "для этого пункта, не придумывай."
)

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "описание": {"type": "string"},
        "проблема": {"type": "string"},
        "преимущество": {"type": "string"},
        "кейс_пример": {"type": "string"},
    },
    "required": ["описание", "проблема", "преимущество", "кейс_пример"],
}


class EnrichmentResult:
    def __init__(
        self,
        description: str | None,
        problem: str | None,
        potential_advantage: str | None,
        case_example: str | None,
    ):
        self.description = description
        self.problem = problem
        self.potential_advantage = potential_advantage
        self.case_example = case_example


def enrichment_available() -> bool:
    return bool(OLLAMA_BASE_URL and OLLAMA_MODEL)


def _call_ollama_json(
    client: httpx.Client, system_prompt: str, user_content: str, json_schema: dict, *, temperature: float = 0.2,
) -> dict | None:
    """Общий вызов Ollama chat с format=<json-схема> — переиспользуется
    enrich_signal() и translate_query_to_english(). Возвращает None при
    любом сбое (сеть/парсинг) — оба вызывающих места сами решают, как
    деградировать.

    temperature=0.2 по умолчанию (пересказ текста, вариативность не
    вредит); translate_query_to_english передаёт 0 — детерминированный
    перевод, иначе разная формулировка одного запроса между прогонами
    меняет результаты живых API и топ выдачи.
    """
    if not enrichment_available():
        log.info("ollama: OLLAMA_BASE_URL/OLLAMA_MODEL не заданы — пропуск")
        return None

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "format": json_schema,
        "stream": False,
        "options": {"temperature": temperature},
    }

    try:
        resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        raw_text = resp.json()["message"]["content"]
    except Exception as exc:
        log.error("ollama: запрос не удался: %s", exc)
        return None

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        log.error("ollama: ответ не распарсился как JSON несмотря на format-схему: %r", raw_text[:300])
        return None


def enrich_signal(client: httpx.Client, title: str, source_text: str) -> EnrichmentResult | None:
    """Вернуть None, если Ollama недоступна или ответ не разобрать —
    обогащение необязательный шаг, его отсутствие не должно ронять
    сохранение самого сигнала (см. orchestrator.py)."""
    parsed = _call_ollama_json(
        client, _SYSTEM_PROMPT, f"Заголовок: {title}\n\nТекст: {source_text[:6000]}", _JSON_SCHEMA,
    )
    if parsed is None:
        return None

    return EnrichmentResult(
        description=parsed.get("описание"),
        problem=parsed.get("проблема"),
        potential_advantage=parsed.get("преимущество"),
        case_example=parsed.get("кейс_пример"),
    )

_TRANSLATE_SYSTEM_PROMPT = (
    "Ты переводишь пользовательские поисковые запросы о технологических трендах "
    "на английский язык для поиска по научным базам данных (arXiv, Crossref и т.п.). "
    "Переведи запрос точно и по смыслу, сохрани технические термины. "
    "Верни только перевод, без пояснений и кавычек."
)

_TRANSLATE_JSON_SCHEMA = {
    "type": "object",
    "properties": {"translation": {"type": "string"}},
    "required": ["translation"],
}


def translate_query_to_english(client: httpx.Client, query: str) -> str | None:
    """None при недоступности Ollama/сбое разбора — вызывающий код должен
    откатиться на оригинальный query, не блокировать поиск."""
    parsed = _call_ollama_json(client, _TRANSLATE_SYSTEM_PROMPT, query, _TRANSLATE_JSON_SCHEMA, temperature=0)
    if parsed is None:
        return None
    translation = (parsed.get("translation") or "").strip()
    return translation or None
