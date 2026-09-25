"""LLM-обогащение прошедших модель сигналов — закрывает требование ТЗ:

    "Для каждого тренда должны быть представлены: описание технологии,
    потенциальное преимущество, кейс-пример, источник или источники и
    объяснение отнесения технологии к зарождающемуся тренду."

Источники и объяснение классификации уже закрыты (SignalSource, поле
explanation с вероятностями классов из classifier.py). Здесь — три
оставшихся поля: описание, преимущество, кейс-пример.

Вызывается ТОЛЬКО для кандидатов, уже прошедших классификатор и попавших
в топ-N (см. orchestrator.py) — не для всех сотен кандидатов, чтобы не
жечь запросы к LLM впустую.

Модель — YandexGPT (из разрешённого ТЗ списка облачных моделей). Промпт
жёстко ограничивает модель ТОЛЬКО текстом источника, без общих знаний —
иначе это будет нарушением требования ТЗ "запрещено формировать выдачу
слабых сигналов только на знаниях LLM без подтверждённого поиска": здесь
источник уже найден и подтверждён пайплайном, LLM только пересказывает/
структурирует конкретный текст, не сочиняет из общих знаний.

НЕ ПРОВЕРЕНО ВЖИВУЮ — ключа/folder_id у команды пока нет. Структура запроса
по документации Yandex Cloud Foundation Models Completion API, сверить при
получении доступа: https://yandex.cloud/ru/docs/foundation-models/concepts/
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from ..config import YANDEX_GPT_API_KEY, YANDEX_GPT_FOLDER_ID, YANDEX_GPT_MODEL

log = logging.getLogger(__name__)

YANDEX_GPT_API = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
REQUEST_TIMEOUT = 30.0

_SYSTEM_PROMPT = (
    "Ты помогаешь анализировать технологические тренды для аналитического сервиса. "
    "На основе ТОЛЬКО предоставленного текста статьи — без использования собственных "
    "общих знаний о предмете — сформулируй три коротких пункта на русском языке: "
    "описание технологии (что это), потенциальное преимущество (какую пользу даёт), "
    "кейс-пример (конкретный факт применения из текста — компания, продукт, пилот). "
    "Если в тексте нет данных для какого-то пункта — напиши \"не указано в источнике\" "
    "для этого пункта, не придумывай. Ответь строго в формате JSON без пояснений: "
    '{"описание": "...", "преимущество": "...", "кейс_пример": "..."}'
)


class EnrichmentResult:
    def __init__(self, description: str | None, potential_advantage: str | None, case_example: str | None):
        self.description = description
        self.potential_advantage = potential_advantage
        self.case_example = case_example


def enrichment_available() -> bool:
    return bool(YANDEX_GPT_API_KEY and YANDEX_GPT_FOLDER_ID)


def _extract_json(text: str) -> dict | None:
    """Модель просили ответить чистым JSON, но LLM иногда оборачивает ответ
    в markdown-блок ```json ... ``` или добавляет пояснение вокруг — вырезаем
    первый похожий на объект фрагмент и пробуем распарсить."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def enrich_signal(client: httpx.Client, title: str, source_text: str) -> EnrichmentResult | None:
    """Вернуть None, если ключ не настроен, запрос не удался или ответ
    не разобрать — обогащение необязательный шаг, его отсутствие не должно
    ронять сохранение самого сигнала (см. orchestrator.py)."""
    if not enrichment_available():
        log.info("yandexgpt: YANDEX_GPT_API_KEY/YANDEX_GPT_FOLDER_ID не заданы — пропуск обогащения")
        return None

    payload = {
        "modelUri": f"gpt://{YANDEX_GPT_FOLDER_ID}/{YANDEX_GPT_MODEL}/latest",
        "completionOptions": {"stream": False, "temperature": 0.2, "maxTokens": 500},
        "messages": [
            {"role": "system", "text": _SYSTEM_PROMPT},
            {"role": "user", "text": f"Заголовок: {title}\n\nТекст: {source_text[:6000]}"},
        ],
    }
    headers = {
        "Authorization": f"Api-Key {YANDEX_GPT_API_KEY}",
        "x-folder-id": YANDEX_GPT_FOLDER_ID,
    }

    try:
        resp = client.post(YANDEX_GPT_API, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["result"]["alternatives"][0]["message"]["text"]
    except Exception as exc:
        log.error("yandexgpt: запрос не удался: %s", exc)
        return None

    parsed = _extract_json(raw_text)
    if parsed is None:
        log.error("yandexgpt: не удалось разобрать ответ как JSON: %r", raw_text[:300])
        return None

    return EnrichmentResult(
        description=parsed.get("описание"),
        potential_advantage=parsed.get("преимущество"),
        case_example=parsed.get("кейс_пример"),
    )
