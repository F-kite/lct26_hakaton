"""Минимальный клиент GigaChat: OAuth-токен (живёт 30 минут) + chat/completions."""

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


DOWN_COOLDOWN_S = 120
_down_until = 0.0


def is_available() -> bool:
    return is_configured() and time.time() >= _down_until


def mark_down(reason: str) -> None:
    global _down_until
    _down_until = time.time() + DOWN_COOLDOWN_S
    log.warning("GigaChat недоступен (%s) — %d с используем запасную модель", reason, DOWN_COOLDOWN_S)


def _verify() -> str | bool:
    if GIGACHAT_CA_FILE and os.path.exists(GIGACHAT_CA_FILE):
        return GIGACHAT_CA_FILE
    log.warning("GigaChat: сертификат %s не найден, используем системные", GIGACHAT_CA_FILE)
    return True


_token: str | None = None
_token_expires_at = 0.0
_token_lock = threading.Lock()
_call_lock = threading.Lock()


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
        _token_expires_at = data["expires_at"] / 1000
        return _token


def chat_json(
    system: str, user: str, schema: dict, *, temperature: float = 0.2, model: str | None = None,
) -> dict:
    timeout = httpx.Timeout(LLM_TIMEOUT_SECONDS, connect=10.0)
    with _call_lock, httpx.Client(verify=_verify(), timeout=timeout) as client:
        token = _get_token(client)
        resp = client.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": model or GIGACHAT_MODEL,
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
            _token = None
        raise GigaChatError(
            f"chat {resp.status_code}: {resp.text[:200]}",
            retryable=resp.status_code in (401, 429) or resp.status_code >= 500,
        )
    data = resp.json()
    log.info("GigaChat: модель %s, токенов %s", data.get("model"), (data.get("usage") or {}).get("total_tokens"))
    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise GigaChatError(f"ответ не JSON: {content[:200]}", retryable=True) from exc
