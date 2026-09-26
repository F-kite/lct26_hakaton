"""LLM-обогащение прошедших модель сигналов — закрывает требование ТЗ:

    "Для каждого тренда должны быть представлены: описание технологии,
    потенциальное преимущество, кейс-пример, источник или источники и
    объяснение отнесения технологии к зарождающемуся тренду."

Источники и объяснение классификации уже закрыты (SignalSource, поле
explanation с вероятностями классов из classifier.py). Здесь — три
оставшихся поля: описание, преимущество, кейс-пример.

Вызывается ТОЛЬКО для кандидатов, уже прошедших классификатор и попавших
в топ-N (см. orchestrator.py) — не для всех сотен кандидатов, чтобы не
тратить инференс впустую.

Модель — локальная Qwen2.5 через Ollama (разрешена ТЗ: "любая с Hugging
Face" без согласования, в отличие от облачных). Крутится отдельным
сервисом в docker-compose, backend стучится к ней по HTTP внутри
docker-сети (см. OLLAMA_BASE_URL в config.py). Сначала пробовали YandexGPT
(облачный, из разрешённого списка) — отказались: нужен был ключ, которого
не было, и внешняя зависимость от доступности сервиса. У локальной модели
такого риска нет ценой более скромного качества генерации.

Промпт жёстко ограничивает модель ТОЛЬКО текстом источника, без общих
знаний — иначе это нарушало бы требование ТЗ "запрещено формировать выдачу
слабых сигналов только на знаниях LLM без подтверждённого поиска": здесь
источник уже найден и подтверждён пайплайном, LLM только пересказывает/
структурирует конкретный текст, не сочиняет из общих знаний.

Ollama поддерживает format="json" — режим, который ограничивает сэмплинг
токенов только валидным JSON на уровне грамматики, а не полагается на то,
что модель "договорится" следовать инструкции. Для 7B-модели это заметно
надёжнее, чем просить JSON в тексте промпта и парсить с расчётом на удачу.
"""

from __future__ import annotations

import json
import logging

import httpx

from ..config import OLLAMA_BASE_URL, OLLAMA_MODEL

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 120.0  # 7B на CPU может генерировать десятки секунд

_SYSTEM_PROMPT = (
    "Ты помогаешь анализировать технологические тренды для аналитического сервиса. "
    "На основе ТОЛЬКО предоставленного текста статьи — без использования собственных "
    "общих знаний о предмете — сформулируй три коротких пункта на русском языке: "
    "описание технологии (что это), потенциальное преимущество (какую пользу даёт), "
    "кейс-пример (конкретный факт применения из текста — компания, продукт, пилот). "
    "Если в тексте нет данных для какого-то пункта — напиши \"не указано в источнике\" "
    "для этого пункта, не придумывай."
)

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "описание": {"type": "string"},
        "преимущество": {"type": "string"},
        "кейс_пример": {"type": "string"},
    },
    "required": ["описание", "преимущество", "кейс_пример"],
}


class EnrichmentResult:
    def __init__(self, description: str | None, potential_advantage: str | None, case_example: str | None):
        self.description = description
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
    деградировать (пропустить обогащение / оставить запрос как есть).

    temperature по умолчанию 0.2 — для enrich_signal (пересказ текста,
    немного вариативности не вредит). translate_query_to_english передаёт
    0 явно: перевод — не творческая задача, разная формулировка одного и
    того же запроса между прогонами меняет результаты живых API (arXiv/
    Crossref/OpenAlex) и, следовательно, топ выдачи — детерминированный
    перевод убирает этот источник расхождений между одинаковыми запросами.
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
        potential_advantage=parsed.get("преимущество"),
        case_example=parsed.get("кейс_пример"),
    )


# --------------------------------------------------------------------------
# Перевод запроса пользователя на английский перед поиском кандидатов.
#
# Модель обучена и проверена только на английском (classifier.py), а поиск
# по накопленной БД (candidates.py) ищет буквальное вхождение слов запроса
# в заголовок/summary — русский запрос почти никогда не совпадает с
# англоязычными заголовками, и даже когда живые источники (OpenAlex) всё же
# находят русскоязычный материал по теме, он всё равно отсеивается моделью
# на входе (см. orchestrator.py). Перевод запроса к единому языку — не
# перевод контента, а нормализация ЗАПРОСА перед поиском: оригинальный
# query_text как ввёл пользователь остаётся в БД и в выдаче без изменений,
# переведённая версия используется только для find_candidates/fetch_all_live.
# --------------------------------------------------------------------------

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
