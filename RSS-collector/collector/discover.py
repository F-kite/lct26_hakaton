"""Автодискавери RSS-лент.

Две стратегии:
1. <link rel="alternate" type="application/rss+xml"> в <head> страницы — канонический способ.
2. Перебор типовых путей (/feed, /rss, /feed.xml, ...) — fallback.

Нужен, когда точный URL ленты неизвестен (например, ВШЭ) или когда сайт
сменил адрес фида: вместо правки константы запускаем discover.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from selectolax.parser import HTMLParser

log = logging.getLogger(__name__)

USER_AGENT = "LCT2026-WeakSignals/0.1 (hackathon research collector)"

COMMON_PATHS = [
    "/feed", "/feed/", "/rss", "/rss/", "/feed.xml", "/rss.xml",
    "/index.xml", "/atom.xml", "/news/rss", "/blog/feed",
]


def _looks_like_feed(content: bytes) -> bool:
    """Лента считается валидной, если парсер нашёл хотя бы одну запись."""
    parsed = feedparser.parse(content)
    return bool(parsed.entries)


def discover(site_url: str, timeout: float = 15.0) -> list[str]:
    """Вернуть список найденных URL лент, самый вероятный — первым."""
    found: list[str] = []
    headers = {"User-Agent": USER_AGENT}

    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        # --- стратегия 1: <link rel="alternate">
        try:
            resp = client.get(site_url)
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            for node in tree.css('link[rel="alternate"]'):
                mime = (node.attributes.get("type") or "").lower()
                href = node.attributes.get("href")
                if not href:
                    continue
                if "rss" in mime or "atom" in mime or "xml" in mime:
                    found.append(urljoin(str(resp.url), href))
        except Exception as exc:
            log.warning("discover: не удалось разобрать %s: %s", site_url, exc)

        # --- стратегия 2: типовые пути от корня домена
        parsed = urlparse(site_url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        for path in COMMON_PATHS:
            candidate = urljoin(root, path)
            if candidate in found:
                continue
            try:
                r = client.get(candidate)
                if r.status_code == 200 and _looks_like_feed(r.content):
                    found.append(candidate)
            except Exception:
                continue

    # дедуп с сохранением порядка
    seen: set[str] = set()
    ordered = []
    for u in found:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered
