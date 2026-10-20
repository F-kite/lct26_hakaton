"""LLM-обогащение сигналов, прошедших модель: описание, решаемая проблема,
преимущество, кейс-пример. Вызывается только для кандидатов в топ-N — не
тратить инференс на все кандидаты.

Описания и перевод запроса — GigaChat 2 Max (при наличии ключа), при его
недоступности автоматически — запасная локальная Qwen2.5 через Ollama.
Какая модель дала ответ, сохраняется вместе с ним (ТЗ: раскрытие модели).
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from ..config import (
    ENRICHMENT_MODEL,
    ENRICHMENT_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    TRANSLATION_MODEL,
)

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
    "для этого пункта, не придумывай. Кейс-пример — только конкретный факт применения "
    "(компания, продукт, пилот, патент, внедрение); общие возможности технологии кейсом "
    "не являются. Отвечай строго на русском языке, даже если текст статьи на английском."
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
        model: str | None = None,
    ):
        self.description = description
        self.problem = problem
        self.potential_advantage = potential_advantage
        self.case_example = case_example
        self.model = model


def ollama_available() -> bool:
    return bool(OLLAMA_BASE_URL and OLLAMA_MODEL)


def _gigachat_ready() -> bool:
    from . import gigachat

    return gigachat.is_available()


def enrichment_available() -> bool:
    return (ENRICHMENT_PROVIDER == "gigachat" and _gigachat_ready()) or ollama_available()


def translation_available() -> bool:
    return _gigachat_ready() or ollama_available()


_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
GIGACHAT_ATTEMPTS = 3


def _call_gigachat_json(user_content: str) -> dict | None:
    from . import gigachat

    content = user_content
    for attempt in range(GIGACHAT_ATTEMPTS):
        try:
            parsed = gigachat.chat_json(_SYSTEM_PROMPT, content, _JSON_SCHEMA, model=ENRICHMENT_MODEL)
        except gigachat.GigaChatError as exc:
            if exc.retryable and attempt < GIGACHAT_ATTEMPTS - 1:
                time.sleep(2 * 2**attempt)
                continue
            log.error("gigachat (описание): %s", exc)
            gigachat.mark_down(str(exc)[:80])
            return None
        except Exception as exc:
            log.error("gigachat (описание): %s", exc)
            gigachat.mark_down(type(exc).__name__)
            return None
        if _CYRILLIC_RE.search(parsed.get("описание") or ""):
            return parsed
        log.warning("gigachat (описание): ответ не на русском, повтор")
        content = "Ответ дай строго на русском языке.\n\n" + user_content
    return None


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
    if not ollama_available():
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
    """Вернуть None, если модель недоступна или ответ не разобрать —
    обогащение необязательный шаг, его отсутствие не должно ронять
    сохранение самого сигнала (см. orchestrator.py)."""
    user_content = f"Заголовок: {title}\n\nТекст: {source_text[:6000]}"
    parsed, model = None, None
    if ENRICHMENT_PROVIDER == "gigachat" and _gigachat_ready():
        parsed, model = _call_gigachat_json(user_content), ENRICHMENT_MODEL
    if parsed is None and ollama_available():
        if ENRICHMENT_PROVIDER == "gigachat":
            log.warning("описание: GigaChat недоступен — запасная модель %s", OLLAMA_MODEL)
        parsed, model = _call_ollama_json(client, _SYSTEM_PROMPT, user_content, _JSON_SCHEMA), OLLAMA_MODEL
    if parsed is None:
        return None

    return EnrichmentResult(
        description=parsed.get("описание"),
        problem=parsed.get("проблема"),
        potential_advantage=parsed.get("преимущество"),
        case_example=parsed.get("кейс_пример"),
        model=model,
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
    parsed = None
    if _gigachat_ready():
        from . import gigachat

        try:
            parsed = gigachat.chat_json(
                _TRANSLATE_SYSTEM_PROMPT, query, _TRANSLATE_JSON_SCHEMA,
                temperature=0.01, model=TRANSLATION_MODEL,
            )
        except Exception as exc:
            log.error("gigachat (перевод): %s", exc)
            gigachat.mark_down(str(exc)[:80])
    if parsed is None and ollama_available():
        log.info("перевод запроса: запасная модель %s", OLLAMA_MODEL)
        parsed = _call_ollama_json(client, _TRANSLATE_SYSTEM_PROMPT, query, _TRANSLATE_JSON_SCHEMA, temperature=0)
    if parsed is None:
        return None
    translation = (parsed.get("translation") or "").strip()
    return translation or None
