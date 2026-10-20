"""Минимальный клиент GigaChat: OAuth-токен (живёт 30 минут) + chat/completions
с ответом строго по JSON-схеме. Параллельность здесь не ограничивается —
этим занимается очередь в summary_service.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid

import httpx

from ..config import (
    GIGACHAT_AUTH_KEY,
    GIGACHAT_CA_FILE,
    GIGACHAT_MODEL,
    GIGACHAT_SCOPE,
    LLM_TIMEOUT_SECONDS,
)

log = logging.getLogger(__name__)

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://api.giga.chat/v1/chat/completions"
TOKEN_REFRESH_MARGIN_S = 60


class GigaChatError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def is_configured() -> bool:
    return bool(GIGACHAT_AUTH_KEY)


def _verify() -> str | bool:
    # без сертификата Минцифры TLS-проверка не пройдёт — лучше явная ошибка,
    # чем молча отключённая проверка
    if GIGACHAT_CA_FILE and os.path.exists(GIGACHAT_CA_FILE):
        return GIGACHAT_CA_FILE
    log.warning("GigaChat: сертификат %s не найден, используем системные", GIGACHAT_CA_FILE)
    return True


_token: str | None = None
_token_expires_at = 0.0  # unix-время в секундах
_token_lock = threading.Lock()


def _get_token(client: httpx.Client) -> str:
    global _token, _token_expires_at
    with _token_lock:
        if _token and time.time() < _token_expires_at - TOKEN_REFRESH_MARGIN_S:
            return _token
        resp = client.post(
            OAUTH_URL,
            headers={
                "Authorization": f"Basic {GIGACHAT_AUTH_KEY}",
                "RqUID": str(uuid.uuid4()),
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"scope": GIGACHAT_SCOPE},
        )
        if resp.status_code != 200:
            raise GigaChatError(f"OAuth {resp.status_code}: {resp.text[:200]}", retryable=resp.status_code >= 500)
        data = resp.json()
        _token = data["access_token"]
        _token_expires_at = data["expires_at"] / 1000  # API отдаёт миллисекунды
        return _token


def chat_json(system: str, user: str, schema: dict, *, temperature: float = 0.2) -> dict:
    """Один запрос к модели; ответ — dict по схеме. 429/5xx — retryable."""
    with httpx.Client(verify=_verify(), timeout=LLM_TIMEOUT_SECONDS) as client:
        token = _get_token(client)
        resp = client.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": GIGACHAT_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_schema", "schema": schema, "strict": True},
                "temperature": temperature,
            },
        )
    if resp.status_code != 200:
        if resp.status_code == 401:
            global _token
            _token = None  # токен отозван раньше срока — следующая попытка возьмёт новый
        raise GigaChatError(
            f"chat {resp.status_code}: {resp.text[:200]}",
            retryable=resp.status_code in (401, 429) or resp.status_code >= 500,
        )
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise GigaChatError(f"ответ не JSON: {content[:200]}", retryable=True) from exc
