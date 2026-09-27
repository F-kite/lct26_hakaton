"""Архивная догрузка исторических записей
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .core import upsert_source, url_hash
from .db import FeedItem, SessionLocal
from .feeds import BY_KEY

log = logging.getLogger(__name__)

USER_AGENT = "LCT2026-WeakSignals/0.1 (hackathon research collector; archive backfill)"
REQUEST_TIMEOUT = 20.0
REQUEST_DELAY = 1.0
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

TECHCRUNCH_CATEGORIES = {
    "artificial-intelligence", "robotics", "hardware", "security",
    "fintech", "enterprise", "biotech-health", "climate", "space",
}

EXCLUDED_SOURCES = {
    "mckinsey": "sitemap.xml и robots.txt не отвечают (похоже на бот-защиту); "
                "архива нет, глубина ограничена RSS — см. заметку в feeds.py",
}


@dataclass
class ArchiveItem:
    """Запись из архива. Поля соответствуют смыслу FeedItem (db.py)."""

    source_key: str
    url: str
    title: str
    published_at: datetime | None
    summary: str | None = None
    author: str | None = None
    raw_categories: str | None = None


def _client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )


def _daterange(date_from: date, date_to: date):
    d = date_from
    while d <= date_to:
        yield d
        d += timedelta(days=1)


MAX_RETRIES = 3
BACKOFF_BASE = 2.0


def _get(
    client: httpx.Client, url: str, *, headers: dict[str, str] | None = None,
) -> httpx.Response | None:
    """GET с ретраями на сетевые сбои и 429/5xx.
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            wait = BACKOFF_BASE ** attempt
            log.warning("%s -> %s, повтор через %.1fs", url, exc, wait)
            time.sleep(wait)
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = BACKOFF_BASE ** attempt
            log.warning("%s -> %s, повтор через %.1fs", url, resp.status_code, wait)
            time.sleep(wait)
            continue
        return resp
    log.error("не удалось получить %s после %d попыток — пропуск", url, MAX_RETRIES)
    return None


# --------------------------------------------------------------------------
# Способ 1: day_archive — ВШЭ, TechCrunch
# --------------------------------------------------------------------------

def fetch_hse_day(
    client: httpx.Client, source_key: str, section: str, day: date,
) -> list[ArchiveItem]:
    """Один день архива ВШЭ. section: 'science' | 'expertise'.

    Дата берётся из URL архива, а не из карточки (там она без времени).
    """
    url = f"https://www.hse.ru/news/archive/{section}/{day:%Y/%m/%d}/"
    resp = _get(client, url)
    if resp is None:
        return []
    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        log.warning("%s -> %s, день пропущен", url, resp.status_code)
        return []

    tree = HTMLParser(resp.text)
    items: list[ArchiveItem] = []
    for post in tree.css("div.post"):
        link = post.css_first("h2.first_child a")
        if link is None:
            continue
        href = link.attributes.get("href")
        if not href:
            continue
        full_url = href if href.startswith("http") else f"https://www.hse.ru{href}"
        title = link.text(strip=True)

        text_node = post.css_first(".post__text")
        summary = text_node.text(strip=True) if text_node else None

        rubric_node = post.css_first(".tag-set a.rubric span")
        tag_node = post.css_first(".tag-set a.tag")
        cats = [n.text(strip=True) for n in (rubric_node, tag_node) if n]

        items.append(ArchiveItem(
            source_key=source_key,
            url=full_url,
            title=title,
            published_at=datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            summary=summary,
            raw_categories=", ".join(cats) if cats else None,
        ))
    return items


def fetch_techcrunch_day(
    client: httpx.Client, day: date, categories: set[str] | None = TECHCRUNCH_CATEGORIES,
) -> list[ArchiveItem]:
    """Один день архива TechCrunch. categories=None -> без фильтрации по теме.
    """
    url = f"https://techcrunch.com/{day:%Y/%m/%d}/"
    resp = _get(client, url)
    if resp is None:
        return []
    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        log.warning("%s -> %s, день пропущен", url, resp.status_code)
        return []

    tree = HTMLParser(resp.text)
    items: list[ArchiveItem] = []
    for post in tree.css("li.wp-block-post"):
        classes = post.attributes.get("class", "") or ""
        post_cats = {c.removeprefix("category-") for c in classes.split() if c.startswith("category-")}
        if categories is not None and not (post_cats & categories):
            continue

        link = post.css_first("a.loop-card__title-link")
        if link is None:
            continue
        href = link.attributes.get("href")
        if not href:
            continue
        title = link.text(strip=True)

        published_at = None
        time_node = post.css_first("time.loop-card__time")
        if time_node is not None:
            dt_raw = time_node.attributes.get("datetime")
            if dt_raw:
                try:
                    published_at = datetime.fromisoformat(dt_raw).astimezone(timezone.utc)
                except ValueError:
                    pass

        author_node = post.css_first("a.loop-card__author")

        items.append(ArchiveItem(
            source_key="techcrunch",
            url=href,
            title=title,
            published_at=published_at,
            author=author_node.text(strip=True) if author_node else None,
            raw_categories=", ".join(sorted(post_cats)) if post_cats else None,
        ))
    return items


DAY_ARCHIVE_SOURCES = {
    "hse_science": lambda client, day: fetch_hse_day(client, "hse_science", "science", day),
    "hse_expertise": lambda client, day: fetch_hse_day(client, "hse_expertise", "expertise", day),
    "techcrunch": fetch_techcrunch_day,
}


# --------------------------------------------------------------------------
# Способ 2: sitemap — SiliconANGLE, MIT News
# --------------------------------------------------------------------------

def _parse_sitemap(xml_bytes: bytes) -> list[tuple[str, str | None]]:
    """Вернуть [(loc, lastmod), ...] из sitemap-файла (index или urlset)."""
    root = ElementTree.fromstring(xml_bytes)
    nodes = root.findall("sm:url", SITEMAP_NS) or root.findall("sm:sitemap", SITEMAP_NS)
    return [
        (node.findtext("sm:loc", namespaces=SITEMAP_NS), node.findtext("sm:lastmod", namespaces=SITEMAP_NS))
        for node in nodes
        if node.findtext("sm:loc", namespaces=SITEMAP_NS)
    ]


_SILICONANGLE_DATE_RE = re.compile(r"siliconangle\.com/(\d{4})/(\d{2})/(\d{2})/")


def list_siliconangle_urls(
    client: httpx.Client, date_from: date, date_to: date,
) -> list[tuple[str, datetime]]:
    """Обойти sitemap-индекс SiliconANGLE, дата — из пути URL (надёжнее lastmod:
    lastmod иногда на день-два позже фактической публикации)."""
    resp = _get(client, "https://siliconangle.com/sitemap.xml")
    if resp is None or resp.status_code != 200:
        log.error("не удалось получить индекс sitemap siliconangle")
        return []
    sub_sitemaps = [loc for loc, _ in _parse_sitemap(resp.content) if "post-sitemap" in loc]

    matched: list[tuple[str, datetime]] = []
    for sm_url in sub_sitemaps:
        resp = _get(client, sm_url)
        if resp is None or resp.status_code != 200:
            continue
        for loc, _lastmod in _parse_sitemap(resp.content):
            m = _SILICONANGLE_DATE_RE.search(loc)
            if not m:
                continue
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if date_from <= d <= date_to:
                matched.append((loc, datetime(d.year, d.month, d.day, tzinfo=timezone.utc)))
        time.sleep(REQUEST_DELAY)
    return matched


def list_mit_news_urls(
    client: httpx.Client, date_from: date, date_to: date,
) -> list[tuple[str, datetime]]:
    """Обойти постраничный sitemap-индекс MIT News, дата — из <lastmod>."""
    resp = _get(client, "https://news.mit.edu/sitemap.xml")
    if resp is None or resp.status_code != 200:
        log.error("не удалось получить индекс sitemap mit_news")
        return []
    pages = [loc for loc, _ in _parse_sitemap(resp.content)]

    matched: list[tuple[str, datetime]] = []
    for page_url in pages:
        resp = _get(client, page_url)
        if resp is None or resp.status_code != 200:
            continue
        for loc, lastmod in _parse_sitemap(resp.content):
            if not lastmod:
                continue
            try:
                dt = datetime.fromisoformat(lastmod).astimezone(timezone.utc)
            except ValueError:
                continue
            if date_from <= dt.date() <= date_to:
                matched.append((loc, dt))
        time.sleep(REQUEST_DELAY)
    return matched


SITEMAP_SOURCES = {
    "siliconangle": list_siliconangle_urls,
    "mit_news": list_mit_news_urls,
}


def enrich_from_opengraph(
    client: httpx.Client, source_key: str, url: str, published_at: datetime,
) -> ArchiveItem | None:
    """Добрать title/summary/author со страницы статьи через OpenGraph-мету.

    Общий метод, не завязан на конкретную вёрстку сайта.
    """
    resp = _get(client, url)
    if resp is None or resp.status_code != 200:
        return None
    tree = HTMLParser(resp.text)

    def meta(prop: str) -> str | None:
        node = tree.css_first(f'meta[property="{prop}"]') or tree.css_first(f'meta[name="{prop}"]')
        return node.attributes.get("content") if node else None

    title = meta("og:title")
    if not title:
        return None

    published_time = meta("article:published_time")
    if published_time:
        try:
            published_at = datetime.fromisoformat(published_time).astimezone(timezone.utc)
        except ValueError:
            pass

    return ArchiveItem(
        source_key=source_key,
        url=url,
        title=title,
        published_at=published_at,
        summary=meta("og:description"),
        author=meta("og:author") or meta("author"),
    )


# --------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------

FLUSH_EVERY = 25  # раз в сколько новых записей промежуточно писать в БД при save=True


def fetch_archive(
    source_key: str, date_from: date, date_to: date, *, enrich: bool = False, save: bool = False,
) -> list[ArchiveItem]:
    """Собрать архив одного источника за период.
    """
    if source_key in EXCLUDED_SOURCES:
        raise ValueError(f"{source_key}: архив недоступен — {EXCLUDED_SOURCES[source_key]}")

    collected: list[ArchiveItem] = []
    pending: list[ArchiveItem] = []

    def _maybe_flush(force: bool = False) -> None:
        if not save or not pending or not (force or len(pending) >= FLUSH_EVERY):
            return
        n = persist_items(pending)
        log.info("[%s] промежуточно сохранено %d/%d новых", source_key, n, len(pending))
        pending.clear()

    with _client() as client:
        if source_key in DAY_ARCHIVE_SOURCES:
            fetch_day = DAY_ARCHIVE_SOURCES[source_key]
            for day in _daterange(date_from, date_to):
                try:
                    day_items = fetch_day(client, day)
                except Exception as exc:
                    log.error("[%s] сбой на дне %s, пропуск: %s", source_key, day, exc)
                    day_items = []
                collected.extend(day_items)
                pending.extend(day_items)
                _maybe_flush()
                time.sleep(REQUEST_DELAY)
            _maybe_flush(force=True)
            return collected

        if source_key in SITEMAP_SOURCES:
            pairs = SITEMAP_SOURCES[source_key](client, date_from, date_to)
            if not enrich:
                collected = [
                    ArchiveItem(source_key=source_key, url=u, title="", published_at=dt)
                    for u, dt in pairs
                ]
                return collected

            for u, dt in pairs:
                try:
                    item = enrich_from_opengraph(client, source_key, u, dt)
                except Exception as exc:
                    log.error("[%s] сбой на %s, пропуск: %s", source_key, u, exc)
                    item = None
                if item:
                    collected.append(item)
                    pending.append(item)
                    _maybe_flush()
                time.sleep(REQUEST_DELAY)
            _maybe_flush(force=True)
            return collected

    raise ValueError(f"неизвестный источник: {source_key}")


def persist_items(items: list[ArchiveItem]) -> int:
    """Записать архивные записи в feed_items — той же схемой, что core.collect_one.
    """
    session = SessionLocal()
    new_count = 0
    source_cache: dict[str, object] = {}
    try:
        for item in items:
            if not item.title:
                log.warning("пропуск без title (нужен --enrich для sitemap-источников): %s", item.url)
                continue

            feed = BY_KEY.get(item.source_key)
            if feed is None:
                log.warning("неизвестный source_key: %s", item.source_key)
                continue

            src = source_cache.get(item.source_key)
            if src is None:
                src = upsert_source(session, feed)
                session.commit()
                source_cache[item.source_key] = src

            h = url_hash(item.url)
            if session.scalar(select(FeedItem.id).where(FeedItem.url_hash == h)):
                continue

            author = item.author[:255] if item.author else item.author

            session.add(FeedItem(
                source_id=src.id,
                url=item.url,
                url_hash=h,
                title=item.title,
                summary=item.summary,
                author=author,
                published_at=item.published_at,
                raw_categories=item.raw_categories,
                trust_level=feed.trust_level,
                source_type=feed.source_type,
                language=feed.language,
                is_indicator_only=feed.is_indicator_only,
                sponsored=False,
                is_translated=False,
            ))
            try:
                session.flush()
                new_count += 1
            except IntegrityError:
                session.rollback()
                continue

        session.commit()
        return new_count
    finally:
        session.close()


def main() -> int:
    import argparse
    import sys

    all_keys = sorted(set(DAY_ARCHIVE_SOURCES) | set(SITEMAP_SOURCES))
    p = argparse.ArgumentParser(
        prog="python -m collector.archive",
        description="Архивная догрузка за период (то же самое, что "
                     "`python -m collector.main archive`, для точечного запуска модуля).",
    )
    p.add_argument("source_key", choices=all_keys)
    p.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD, по умолчанию — сегодня")
    p.add_argument("--enrich", action="store_true",
                    help="для sitemap-источников: добрать title/summary со страницы статьи "
                         "(на порядок больше запросов)")
    p.add_argument("--save", action="store_true",
                    help="записать найденное в БД (требует DATABASE_URL); без флага — только печать")
    args = p.parse_args()

    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to) if args.date_to else date.today()
   
    enrich = args.enrich or (args.save and args.source_key in SITEMAP_SOURCES)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")

    items = fetch_archive(args.source_key, date_from, date_to, enrich=enrich, save=args.save)
    print(f"\n[{args.source_key}] найдено записей: {len(items)}")
    for it in items[:20]:
        print(f"  {it.published_at} | {it.title[:80]!r} | {it.url}")
    if len(items) > 20:
        print(f"  ... и ещё {len(items) - 20}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
