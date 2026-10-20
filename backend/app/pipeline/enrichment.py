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
    "Ты помогаешь аналитикам банка разбирать ранние технологические сигналы. Работай ТОЛЬКО "
    "по предоставленному тексту публикации, без собственных общих знаний. Отвечай строго на "
    "русском языке, даже если текст на английском.\n"
    "описание — 1–2 предложения о том, что именно предлагает или исследует эта публикация: "
    "конкретный метод, устройство, материал или подход и его суть. Опирайся на заголовок. "
    "Не давай общего определения области (не начинай с «X — это область…»).\n"
    "проблема — конкретное ограничение, которое устраняет предложенный подход; не повторяй описание.\n"
    "преимущество — какую пользу даёт подход по тексту.\n"
    "критерии — 2–4 признака того, что технология на ранней стадии (слабый сигнал), каждый с "
    "фактом из текста: исследование или прототип, пилот или опытная эксплуатация, грант или "
    "раннее финансирование, первая демонстрация или новизна подхода, нерешённые ограничения, "
    "отсутствие массового рынка. Указывай только то, что подтверждается текстом.\n"
    "проявления — конкретные факты, где технология уже проявилась: компания, продукт, пилот, "
    "эксперимент, патент, испытание. Каждое проявление — одно законченное предложение с конкретикой (кто, что и где сделал). Если в тексте названы конкретные системы, продукты или проекты — назови их и то, что о них сказано. Общие возможности технологии проявлением не являются. "
    "Если таких фактов нет — пустой список.\n"
    "Если исполнитель не назван в тексте (например, «we»), пиши «авторы проекта» или «исследователи»; "
    "не используй шаблонные подстановки вида {{company}}.\n"
    "Если для текстового пункта нет данных — напиши \"не указано в источнике\", не придумывай."
)

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "описание": {"type": "string"},
        "проблема": {"type": "string"},
        "преимущество": {"type": "string"},
        "критерии": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"критерий": {"type": "string"}, "факт": {"type": "string"}},
                "required": ["критерий", "факт"],
            },
        },
        "проявления": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["описание", "проблема", "преимущество", "критерии", "проявления"],
}

NOT_SPECIFIED = "не указано в источнике"

_LEADING_JUNK_RE = re.compile(r"^[\s!•\-–—*·.,:;]+")


_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]*\}\}")


def clean_item(text: str) -> str:
    """Убирает мусор в начале пункта («!Loihi», «- …») и делает первую букву заглавной.
    Пункт с шаблонной заглушкой модели («{{company}}») отбрасывается."""
    text = _LEADING_JUNK_RE.sub("", text or "").strip()
    if _PLACEHOLDER_RE.search(text):
        return ""
    return text[:1].upper() + text[1:]


def clean_criteria(items: list | None) -> list[dict]:
    cleaned = [
        {"criterion": clean_item(c.get("criterion", "")), "fact": clean_item(c.get("fact", ""))}
        for c in items or [] if isinstance(c, dict) and c.get("criterion") and c.get("fact")
    ]
    return [c for c in cleaned if c["criterion"] and c["fact"]]


def clean_text(text: str | None) -> str | None:
    return _PLACEHOLDER_RE.sub("авторы проекта", text) if text else text


_EMPTY_ITEM_RE = re.compile(r"^(не )?указан\w* в (тексте|источнике)\.?$", re.IGNORECASE)


def _as_text(item) -> str:
    """Запасная qwen иногда возвращает объект вместо предложения — берём из него текст."""
    if isinstance(item, dict):
        values = [v for v in item.values() if isinstance(v, str) and len(v.split()) > 2]
        return max(values, key=len) if values else ""
    if isinstance(item, str) and item.strip().startswith("{"):
        try:
            return _as_text(json.loads(item.replace("«", '"').replace("»", '"')))
        except ValueError:
            return ""
    return item if isinstance(item, str) else ""


def clean_manifestations(items: list | None) -> list[str]:
    cleaned = [clean_item(_as_text(m)) for m in items or []]
    return [m for m in cleaned if m and not _EMPTY_ITEM_RE.match(m) and NOT_SPECIFIED not in m.lower()]


class EnrichmentResult:
    def __init__(
        self,
        description: str | None,
        problem: str | None,
        potential_advantage: str | None,
        case_example: str | None,
        model: str | None = None,
        weak_criteria: list[dict] | None = None,
        manifestations: list[str] | None = None,
    ):
        self.description = description
        self.problem = problem
        self.potential_advantage = potential_advantage
        self.case_example = case_example
        self.model = model
        self.weak_criteria = weak_criteria
        self.manifestations = manifestations


def ollama_available() -> bool:
    return bool(OLLAMA_BASE_URL and OLLAMA_MODEL)


def _gigachat_ready() -> bool:
    from . import gigachat

    return gigachat.is_available()


def gigachat_ready() -> bool:
    return ENRICHMENT_PROVIDER == "gigachat" and _gigachat_ready()


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
        if not _CYRILLIC_RE.search(parsed.get("описание") or ""):
            log.warning("gigachat (описание): ответ не на русском, повтор")
            content = "Ответ дай строго на русском языке.\n\n" + user_content
            continue
        if _PLACEHOLDER_RE.search(json.dumps(parsed, ensure_ascii=False)) and attempt < GIGACHAT_ATTEMPTS - 1:
            log.warning("gigachat (описание): шаблонная заглушка в ответе, повтор")
            content = (
                "Не используй шаблонные подстановки вида {{...}}. Если исполнитель не назван в тексте, "
                "пиши «авторы проекта» или «исследователи».\n\n" + user_content
            )
            continue
        return parsed
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

    criteria = clean_criteria([
        {"criterion": c.get("критерий"), "fact": c.get("факт")}
        for c in parsed.get("критерии") or [] if isinstance(c, dict)
    ])
    manifestations = clean_manifestations(parsed.get("проявления"))
    return EnrichmentResult(
        description=clean_text(parsed.get("описание")),
        problem=clean_text(parsed.get("проблема")),
        potential_advantage=clean_text(parsed.get("преимущество")),
        case_example=manifestations[0] if manifestations else NOT_SPECIFIED,
        model=model,
        weak_criteria=criteria,
        manifestations=manifestations,
    )

_SOURCE_SUMMARY_PROMPT = (
    "Кратко перескажи на русском языке, о чём эта публикация: 1–2 предложения, "
    "что предлагается или исследуется и главный результат. Только по тексту, "
    "без собственных знаний и без оценок. Отвечай строго на русском языке."
)
_SOURCE_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"резюме": {"type": "string"}},
    "required": ["резюме"],
}


def summarize_source_ru(client: httpx.Client, title: str, text: str) -> tuple[str, str] | None:
    """(резюме, модель): GigaChat, при недоступности — qwen."""
    user_content = f"Заголовок: {title}\n\nТекст: {text[:4000]}"
    if _gigachat_ready():
        from . import gigachat

        try:
            parsed = gigachat.chat_json(
                _SOURCE_SUMMARY_PROMPT, user_content, _SOURCE_SUMMARY_SCHEMA, model=ENRICHMENT_MODEL,
            )
            summary = (parsed.get("резюме") or "").strip()
            if _CYRILLIC_RE.search(summary):
                return summary, ENRICHMENT_MODEL
        except Exception as exc:
            log.error("gigachat (резюме источника): %s", exc)
            gigachat.mark_down(str(exc)[:80])
    if ollama_available():
        parsed = _call_ollama_json(client, _SOURCE_SUMMARY_PROMPT, user_content, _SOURCE_SUMMARY_SCHEMA)
        summary = ((parsed or {}).get("резюме") or "").strip()
        if summary:
            return summary, OLLAMA_MODEL
    return None


def _llm_json(client: httpx.Client, system: str, user: str, schema: dict, check_key: str) -> tuple[dict, str] | None:
    """(ответ, модель): GigaChat, при недоступности — qwen. check_key — поле, которое должно быть на русском."""
    if _gigachat_ready():
        from . import gigachat

        try:
            parsed = gigachat.chat_json(system, user, schema, model=ENRICHMENT_MODEL)
            if _CYRILLIC_RE.search(json.dumps(parsed.get(check_key), ensure_ascii=False)):
                return parsed, ENRICHMENT_MODEL
        except Exception as exc:
            log.error("gigachat (%s): %s", check_key, exc)
            gigachat.mark_down(str(exc)[:80])
    if ollama_available():
        parsed = _call_ollama_json(client, system, user, schema)
        if parsed:
            return parsed, OLLAMA_MODEL
    return None


_ASSESSMENT_PROMPT = (
    "Ты помогаешь аналитикам банка. По тексту аналитического отчёта кратко (1–2 предложения) "
    "на русском языке изложи, как авторы оценивают технологию: её зрелость, перспективы, риски "
    "или применение. Только по тексту, без собственных знаний. Если оценки в тексте нет — "
    "кратко перескажи, о чём отчёт. Не используй шаблонные подстановки вида {{...}}."
)
_ASSESSMENT_SCHEMA = {
    "type": "object",
    "properties": {"оценка": {"type": "string"}},
    "required": ["оценка"],
}


def assess_report_ru(client: httpx.Client, title: str, text: str) -> tuple[str, str] | None:
    result = _llm_json(
        client, _ASSESSMENT_PROMPT, f"Заголовок: {title}\n\nТекст: {text[:4000]}", _ASSESSMENT_SCHEMA, "оценка",
    )
    if result is None:
        return None
    text_ru = clean_item(clean_text((result[0].get("оценка") or "").strip()) or "")
    return (text_ru, result[1]) if text_ru else None


STAGE_VALUES = ["Исследования", "Ранняя стадия", "Пилотные внедрения", "Рост", "Зрелость", "Нет данных"]
FIRST_USE_VALUES = ["Есть пилотные кейсы", "Есть внедрения", "Не подтверждено"]
MASS_ADOPTION_VALUES = ["Подтверждено", "Не подтверждено"]

_REPORTS_SUMMARY_PROMPT = (
    "Ты помогаешь аналитикам банка. По фрагментам аналитических отчётов составь сводную оценку "
    "технологии: стадия развития, первые применения, массовое внедрение. Выбирай значение строго "
    "из допустимых и в основании одним предложением на русском укажи, на что опираешься в "
    "отчётах. Только по текстам отчётов, без собственных знаний; если данных нет — выбирай "
    "«Нет данных» или «Не подтверждено»."
)


def _assessment_field(values: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"значение": {"type": "string", "enum": values}, "основание": {"type": "string"}},
        "required": ["значение", "основание"],
    }


_REPORTS_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "стадия": _assessment_field(STAGE_VALUES),
        "первые_применения": _assessment_field(FIRST_USE_VALUES),
        "массовое_внедрение": _assessment_field(MASS_ADOPTION_VALUES),
    },
    "required": ["стадия", "первые_применения", "массовое_внедрение"],
}


def summarize_reports_ru(
    client: httpx.Client, technology: str, reports: list[tuple[str, str]],
) -> tuple[dict, str] | None:
    """Сводная оценка по отчётам: {stage, first_applications, mass_adoption: {value, basis}}."""
    parts = [f"Технология: {technology}", ""]
    for i, (title, text) in enumerate(reports, 1):
        parts.append(f"Отчёт {i}: {title}\n{text[:1500]}\n")
    result = _llm_json(client, _REPORTS_SUMMARY_PROMPT, "\n".join(parts), _REPORTS_SUMMARY_SCHEMA, "стадия")
    if result is None:
        return None
    parsed, model = result
    allowed = {
        "stage": ("стадия", STAGE_VALUES, "Нет данных"),
        "first_applications": ("первые_применения", FIRST_USE_VALUES, "Не подтверждено"),
        "mass_adoption": ("массовое_внедрение", MASS_ADOPTION_VALUES, "Не подтверждено"),
    }
    summary = {}
    for key, (ru_key, values, fallback) in allowed.items():
        field = parsed.get(ru_key) or {}
        value = field.get("значение") if field.get("значение") in values else fallback
        summary[key] = {"value": value, "basis": clean_item(clean_text((field.get("основание") or "").strip()) or "") or None}
    return summary, model


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
