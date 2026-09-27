"""Живой поиск по внешним API во время запроса — arXiv, Semantic Scholar,
Crossref, OpenAlex, GitHub, Hacker News.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import CONTACT_EMAIL, GITHUB_TOKEN, SEMANTIC_SCHOLAR_API_KEY
from ..db import FeedItem, Source

log = logging.getLogger(__name__)

USER_AGENT = f"LCT2026-WeakSignals-backend/0.1 (live search; mailto:{CONTACT_EMAIL})"
REQUEST_TIMEOUT = 20.0
MAX_RETRIES = 3
BACKOFF_BASE = 2.0


def url_hash(url: str) -> str:
    """Тот же алгоритм, что в RSS-collector/collector/core.py — иначе
    дедуп по UNIQUE(url_hash) в БД не сработает между двумя сервисами."""
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


@dataclass
class LiveItem:
    source_key: str
    url: str
    title: str
    published_at: datetime | None
    summary: str | None = None
    author: str | None = None
    raw_categories: str | None = None


def _client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})


def _get(
    client: httpx.Client, url: str, *, headers: dict[str, str] | None = None,
) -> httpx.Response | None:
    """GET с ретраями — тот же паттерн, что в RSS-collector/archive.py."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            wait = BACKOFF_BASE**attempt
            log.warning("%s -> %s, повтор через %.1fs", url, exc, wait)
            time.sleep(wait)
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = BACKOFF_BASE**attempt
            log.warning("%s -> %s, повтор через %.1fs", url, resp.status_code, wait)
            time.sleep(wait)
            continue
        return resp
    log.error("не удалось получить %s после %d попыток", url, MAX_RETRIES)
    return None


# --------------------------------------------------------------------------
# arXiv
# --------------------------------------------------------------------------

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_arxiv_live(client: httpx.Client, query: str, *, max_results: int = 30) -> list[LiveItem]:
    params = {
        "search_query": f"all:{query}",
        "sortBy": "relevance",
        "max_results": str(max_results),
    }
    resp = _get(client, f"{ARXIV_API}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        return []
    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as exc:
        log.error("arxiv: не удалось разобрать ответ: %s", exc)
        return []

    items = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = (entry.findtext("atom:title", namespaces=ATOM_NS) or "").strip()
        if not title:
            continue
        url = next(
            (l.get("href") for l in entry.findall("atom:link", ATOM_NS) if l.get("rel") == "alternate"),
            entry.findtext("atom:id", namespaces=ATOM_NS),
        )
        if not url:
            continue
        published_raw = entry.findtext("atom:published", namespaces=ATOM_NS)
        published_at = None
        if published_raw:
            try:
                published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        authors = [a.findtext("atom:name", namespaces=ATOM_NS) for a in entry.findall("atom:author", ATOM_NS)]
        items.append(LiveItem(
            source_key="arxiv",
            url=url,
            title=" ".join(title.split()),
            published_at=published_at,
            summary=" ".join((entry.findtext("atom:summary", namespaces=ATOM_NS) or "").split()) or None,
            author=", ".join(a for a in authors if a) or None,
        ))
    return items


# --------------------------------------------------------------------------
# Semantic Scholar — ключ рекомендован, не обязателен
# --------------------------------------------------------------------------

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"


def fetch_semantic_scholar_live(client: httpx.Client, query: str, *, limit: int = 30) -> list[LiveItem]:
    params = {
        "query": query,
        "limit": str(limit),
        "fields": "title,abstract,url,publicationDate,authors,externalIds",
    }
    headers = {"x-api-key": SEMANTIC_SCHOLAR_API_KEY} if SEMANTIC_SCHOLAR_API_KEY else None
    resp = _get(client, f"{SEMANTIC_SCHOLAR_API}?{urlencode(params)}", headers=headers)
    if resp is None or resp.status_code != 200:
        return []

    items = []
    for paper in resp.json().get("data", []):
        title, url = paper.get("title"), paper.get("url")
        if not title or not url:
            continue
        published_at = None
        if paper.get("publicationDate"):
            try:
                published_at = datetime.fromisoformat(paper["publicationDate"]).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        authors = [a.get("name") for a in (paper.get("authors") or [])]
        items.append(LiveItem(
            source_key="semantic_scholar",
            url=url,
            title=title,
            published_at=published_at,
            summary=paper.get("abstract"),
            author=", ".join(a for a in authors if a) or None,
        ))
    return items


# --------------------------------------------------------------------------
# Crossref — REST API уже используется для verify_doi в RSS-collector,
# здесь то же API, но режим поиска по ключевым словам, не lookup по DOI
# --------------------------------------------------------------------------

CROSSREF_SEARCH_API = "https://api.crossref.org/works"


def search_crossref_live(client: httpx.Client, query: str, *, rows: int = 20) -> list[LiveItem]:
    params = {"query": query, "rows": str(rows)}
    resp = _get(client, f"{CROSSREF_SEARCH_API}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        return []

    items = []
    for work in resp.json().get("message", {}).get("items", []):
        titles = work.get("title") or []
        doi = work.get("DOI")
        if not titles or not doi:
            continue
        date_parts = None
        for key in ("published", "published-print", "published-online"):
            if work.get(key, {}).get("date-parts"):
                date_parts = work[key]["date-parts"][0]
                break
        published_at = None
        if date_parts:
            y = date_parts[0]
            m = date_parts[1] if len(date_parts) > 1 else 1
            d = date_parts[2] if len(date_parts) > 2 else 1
            try:
                published_at = datetime(y, m, d, tzinfo=timezone.utc)
            except ValueError:
                pass
        authors = [
            " ".join(filter(None, [a.get("given"), a.get("family")])) for a in (work.get("author") or [])
        ]
        items.append(LiveItem(
            source_key="crossref",
            url=f"https://doi.org/{doi}",
            title=titles[0],
            published_at=published_at,
            # abstract у Crossref — JATS-размеченный XML (<jats:p>...</jats:p>),
            # не HTML, но classifier._clean_model_input снимает любые теги
            # generic-regex'ом (<[^>]+>), так что чистить здесь не нужно
            summary=work.get("abstract"),
            author=", ".join(a for a in authors if a) or None,
            raw_categories=work.get("type"),
        ))
    return items


# --------------------------------------------------------------------------
# OpenAlex
# --------------------------------------------------------------------------

OPENALEX_API = "https://api.openalex.org/works"


def _reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex не отдаёт abstract текстом (авторское право) — только
    inverted index: слово -> список позиций в тексте. Собираем обратно."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def fetch_openalex_live(client: httpx.Client, query: str, *, per_page: int = 25) -> list[LiveItem]:
    params = {"search": query, "per-page": str(per_page), "mailto": CONTACT_EMAIL}
    resp = _get(client, f"{OPENALEX_API}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        return []

    try:
        data = resp.json()
    except ValueError:
        log.error("openalex: не удалось разобрать ответ как JSON")
        return []

    items = []
    for work in data.get("results", []):
        title = work.get("title") or work.get("display_name")
        if not title:
            continue
        url = work.get("doi") or (work.get("primary_location") or {}).get("landing_page_url") or work.get("id")
        if not url:
            continue
        published_at = None
        pub_date = work.get("publication_date")
        if pub_date:
            try:
                published_at = datetime.fromisoformat(pub_date).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        authors = [(a.get("author") or {}).get("display_name") for a in (work.get("authorships") or [])]
        items.append(LiveItem(
            source_key="openalex",
            url=url,
            title=title,
            published_at=published_at,
            summary=_reconstruct_openalex_abstract(work.get("abstract_inverted_index")),
            author=", ".join(a for a in authors if a) or None,
            raw_categories=work.get("type"),
        ))
    return items


# --------------------------------------------------------------------------
# GitHub — без токена работает (60 запросов/час на IP), с токеном —
# 5000/час
# --------------------------------------------------------------------------

GITHUB_SEARCH_API = "https://api.github.com/search/repositories"


def fetch_github_live(client: httpx.Client, query: str, *, limit: int = 20) -> list[LiveItem]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    params = {"q": query, "per_page": str(limit)}
    resp = _get(client, f"{GITHUB_SEARCH_API}?{urlencode(params)}", headers=headers)
    if resp is None or resp.status_code != 200:
        return []

    try:
        data = resp.json()
    except ValueError:
        log.error("github: не удалось разобрать ответ как JSON")
        return []

    items = []
    for repo in data.get("items", []):
        full_name = repo.get("full_name")
        url = repo.get("html_url")
        if not full_name or not url:
            continue
        created_at = None
        if repo.get("created_at"):
            try:
                created_at = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass
        items.append(LiveItem(
            source_key="github",
            url=url,
            title=full_name,
            published_at=created_at,
            summary=repo.get("description"),
            author=(repo.get("owner") or {}).get("login"),
            raw_categories=repo.get("language"),
        ))
    return items


# --------------------------------------------------------------------------
# Hacker News — через Algolia HN Search (публичный, ключ не нужен)
# --------------------------------------------------------------------------

HACKERNEWS_SEARCH_API = "https://hn.algolia.com/api/v1/search"


def fetch_hackernews_live(client: httpx.Client, query: str, *, limit: int = 20) -> list[LiveItem]:
    params = {"query": query, "tags": "story", "hitsPerPage": str(limit)}
    resp = _get(client, f"{HACKERNEWS_SEARCH_API}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        return []

    try:
        data = resp.json()
    except ValueError:
        log.error("hackernews: не удалось разобрать ответ как JSON")
        return []

    items = []
    for hit in data.get("hits", []):
        title = hit.get("title")
        object_id = hit.get("objectID")
        if not title or not object_id:
            continue
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
        created_at = None
        if hit.get("created_at"):
            try:
                created_at = datetime.fromisoformat(hit["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass
        items.append(LiveItem(
            source_key="hackernews",
            url=url,
            title=title,
            published_at=created_at,
            summary=hit.get("story_text"),
            author=hit.get("author"),
        ))
    return items


# --------------------------------------------------------------------------
# Сводный вызов + персистентность (обогащение БД)
# --------------------------------------------------------------------------

LIVE_SOURCE_META: dict[str, dict[str, str]] = {
    "arxiv": dict(
        name="arXiv", site_url="https://arxiv.org", source_type="preprint",
        trust_level="high", language="EN", topics="Все",
    ),
    "semantic_scholar": dict(
        name="Semantic Scholar", site_url="https://www.semanticscholar.org/product/api",
        source_type="academic_aggregator", trust_level="high", language="EN", topics="Все",
    ),
    "crossref": dict(
        name="Crossref", site_url="https://www.crossref.org", source_type="doi_registry",
        trust_level="high", language="EN", topics="Все",
    ),
    "openalex": dict(
        name="OpenAlex", site_url="https://openalex.org", source_type="academic_aggregator",
        trust_level="high", language="EN", topics="Все",
    ),
    "github": dict(
        name="GitHub", site_url="https://github.com", source_type="code_repository",
        trust_level="medium", language="EN", topics="Все",  # первичная активность
    ),
    "hackernews": dict(
        name="Hacker News", site_url="https://news.ycombinator.com", source_type="community_forum",
        trust_level="medium", language="EN", topics="Все",
    ),
}


def fetch_all_live(query: str) -> list[LiveItem]:
    """Опросить все живые источники. Падение одного не должно ронять остальные."""
    fetchers = [
        ("arxiv", fetch_arxiv_live),
        ("semantic_scholar", fetch_semantic_scholar_live),
        ("crossref", search_crossref_live),
        ("openalex", fetch_openalex_live),
        ("github", fetch_github_live),
        ("hackernews", fetch_hackernews_live),
    ]
    items: list[LiveItem] = []
    with _client() as client:
        for key, fn in fetchers:
            try:
                found = fn(client, query)
                items.extend(found)
                log.info("[%s] live-поиск: %d записей", key, len(found))
            except Exception as exc:
                log.error("[%s] live-поиск упал: %s", key, exc)
    return items


_CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")


def _detect_language(text: str) -> str:
    """LIVE_SOURCE_META['language'] — язык интерфейса источника, не язык
    конкретной работы.
    """
    return "RU" if _CYRILLIC_RE.search(text) else "EN"


def _upsert_source(session: Session, source_key: str) -> Source:
    meta = LIVE_SOURCE_META[source_key]
    src = session.scalar(select(Source).where(Source.key == source_key))
    if src is None:
        src = Source(key=source_key)
        session.add(src)
    src.name = meta["name"]
    src.site_url = meta["site_url"]
    src.source_type = meta["source_type"]
    src.trust_level = meta["trust_level"]
    src.language = meta["language"]
    src.topics = meta["topics"]
    session.flush()
    return src


def persist_live_items(session: Session, items: list[LiveItem]) -> list[FeedItem]:
    """Записать найденное в feed_items — ту же таблицу, что заполняет
    RSS-collector, тем же алгоритмом дедупа (UNIQUE(url_hash)). Обогащает
    БД для будущих поисков, а не только отвечает на текущий запрос.
    Возвращает и новые, и уже существовавшие (по дедупу) FeedItem — их
    сразу можно использовать как кандидатов в этом же поиске.
    """
    source_cache: dict[str, Source] = {}
    result: list[FeedItem] = []

    for item in items:
        if not item.title or not item.url or item.source_key not in LIVE_SOURCE_META:
            continue

        src = source_cache.get(item.source_key)
        if src is None:
            src = _upsert_source(session, item.source_key)
            source_cache[item.source_key] = src

        h = url_hash(item.url)
        existing = session.scalar(select(FeedItem).where(FeedItem.url_hash == h))
        if existing is not None:
            result.append(existing)
            continue

        author = item.author[:255] if item.author else item.author

        row = FeedItem(
            source_id=src.id,
            url=item.url,
            url_hash=h,
            title=item.title,
            summary=item.summary,
            author=author,
            published_at=item.published_at,
            raw_categories=item.raw_categories,
            trust_level=src.trust_level,
            source_type=src.source_type,
            language=_detect_language(f"{item.title} {item.summary or ''}"),
        )
        session.add(row)
        try:
            session.flush()
            result.append(row)
        except IntegrityError:
            session.rollback()
            existing = session.scalar(select(FeedItem).where(FeedItem.url_hash == h))
            if existing is not None:
                result.append(existing)

    session.commit()
    return result
