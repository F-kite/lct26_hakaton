"""Сбор лент.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import FeedItem, SessionLocal, Source
from .feeds import FEEDS, Feed

log = logging.getLogger(__name__)

USER_AGENT = "LCT2026-WeakSignals/0.1 (hackathon research collector)"
MAX_RETRIES = 3
BACKOFF_BASE = 2.0
REQUEST_TIMEOUT = 20.0


@dataclass
class CollectResult:
    key: str
    ok: bool
    new_items: int = 0
    not_modified: bool = False
    error: str | None = None


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        tm = getattr(entry, attr, None)
        if tm:
            return datetime(*tm[:6], tzinfo=timezone.utc)
    return None


def upsert_source(session, feed: Feed) -> Source:
    src = session.scalar(select(Source).where(Source.key == feed.key))
    if src is None:
        src = Source(key=feed.key)
        session.add(src)
    src.name = feed.source_name
    src.feed_url = feed.url
    src.site_url = feed.site_url
    src.source_type = feed.source_type
    src.trust_level = feed.trust_level
    src.language = feed.language
    src.topics = ", ".join(feed.topics)
    src.is_indicator_only = feed.is_indicator_only
    src.sponsored_possible = feed.sponsored_possible
    src.attribution_required = feed.attribution_required
    src.notes = feed.notes
    session.flush()
    return src


def _fetch(client: httpx.Client, url: str, etag: str | None, last_modified: str | None):
    """Условный GET с ретраями. Возвращает httpx.Response."""
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, headers=headers)
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = BACKOFF_BASE ** attempt
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = max(wait, float(retry_after))
                log.warning("%s -> %s, повтор через %.1fs", url, resp.status_code, wait)
                time.sleep(wait)
                continue
            return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            wait = BACKOFF_BASE ** attempt
            log.warning("%s -> %s, повтор через %.1fs", url, exc, wait)
            time.sleep(wait)
    raise last_exc or RuntimeError(f"не удалось получить {url}")


def collect_one(feed: Feed) -> CollectResult:
    """Собрать одну ленту. Исключения наружу не выбрасывает."""
    if not feed.rss_pollable:
        return CollectResult(feed.key, ok=False,
                             error="не RSS-источник (поисковый API) — используйте collector.academic")
    if not feed.url:
        return CollectResult(feed.key, ok=False,
                             error="URL ленты не задан — запустите discover")

    session = SessionLocal()
    try:
        src = upsert_source(session, feed)
        session.commit()

        with httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = _fetch(client, feed.url, src.etag, src.last_modified)

        src.last_polled_at = datetime.now(timezone.utc)

        if resp.status_code == 304:
            src.last_ok_at = src.last_polled_at
            src.consecutive_failures = 0
            src.last_error = None
            session.commit()
            return CollectResult(feed.key, ok=True, not_modified=True)

        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)

        if parsed.bozo and not parsed.entries:
            raise ValueError(f"лента не распарсилась: {parsed.bozo_exception}")

        new_count = 0
        for entry in parsed.entries:
            link = getattr(entry, "link", None)
            if not link:
                continue
            h = url_hash(link)

            exists = session.scalar(select(FeedItem.id).where(FeedItem.url_hash == h))
            if exists:
                continue

            summary = None
            if feed.store_summary:
                summary = getattr(entry, "summary", None)

            cats = getattr(entry, "tags", None)
            raw_categories = (
                ", ".join(t.get("term", "") for t in cats if t.get("term")) if cats else None
            )

            item = FeedItem(
                source_id=src.id,
                url=link,
                url_hash=h,
                title=getattr(entry, "title", "") or "",
                summary=summary,
                author=getattr(entry, "author", None),
                published_at=_parse_date(entry),
                raw_categories=raw_categories,
                trust_level=feed.trust_level,
                source_type=feed.source_type,
                language=feed.language,
                is_indicator_only=feed.is_indicator_only,
                sponsored=False,
                is_translated=False,
            )
            session.add(item)
            try:
                session.flush()
                new_count += 1
            except IntegrityError:
                session.rollback()
                continue

        src.etag = resp.headers.get("ETag") or src.etag
        src.last_modified = resp.headers.get("Last-Modified") or src.last_modified
        src.last_ok_at = datetime.now(timezone.utc)
        src.consecutive_failures = 0
        src.last_error = None
        session.commit()

        return CollectResult(feed.key, ok=True, new_items=new_count)

    except Exception as exc:
        session.rollback()
        try:
            src = session.scalar(select(Source).where(Source.key == feed.key))
            if src:
                src.last_polled_at = datetime.now(timezone.utc)
                src.consecutive_failures = (src.consecutive_failures or 0) + 1
                src.last_error = str(exc)[:1000]
                session.commit()
        except Exception:
            session.rollback()
        log.error("[%s] ошибка сбора: %s", feed.key, exc)
        return CollectResult(feed.key, ok=False, error=str(exc))
    finally:
        session.close()


def collect_all(keys: list[str] | None = None) -> list[CollectResult]:
    """Собрать все ленты. Одна упавшая лента не мешает остальным."""
    feeds = [f for f in FEEDS if not keys or f.key in keys]
    results = []
    for feed in feeds:
        res = collect_one(feed)
        results.append(res)
        if res.ok:
            state = "без изменений" if res.not_modified else f"+{res.new_items}"
            log.info("[%s] ok, %s", res.key, state)
        else:
            log.warning("[%s] fail: %s", res.key, res.error)
    return results
