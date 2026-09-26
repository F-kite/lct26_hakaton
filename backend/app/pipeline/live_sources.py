"""Живой поиск по внешним API во время запроса пользователя — то, чего
не хватало для «в реальном времени, не ограничиваясь датасетом» из ТЗ.

Раньше (candidates.py) поиск смотрел только в уже накопленную БД. Здесь —
источники, которые умеют искать по произвольному запросу «на лету»:
arXiv, Semantic Scholar, Crossref, OpenAlex (академические/патентные),
GitHub, Hacker News, Reddit (не-академические сигналы — ранний рост
активности вокруг темы, а не публикации), плюс USPTO ODP/EPO ODP/
PatentsView для патентов.

По решению: код здесь ДУБЛИРУЕТ часть логики RSS-collector/academic.py
(arXiv, Semantic Scholar, Crossref) — сознательно, чтобы backend не зависел
от чужого Docker-образа (тот же принцип, что уже применён к моделям
Source/FeedItem в db.py).

Статус проверки каждого клиента:
- arXiv, Semantic Scholar, Crossref — проверены вручную на реальных
  запросах (тот же способ, что и в RSS-collector).
- OpenAlex, GitHub, Hacker News, Reddit — написаны по документации
  публичных keyless-эндпоинтов, БЕЗ проверки вживую (нет доступа для
  ручного теста на момент написания) — сверить с реальным ответом API
  при первом реальном запуске.
- USPTO ODP, EPO OPS, PatentsView — ключей нет ни у кого в команде (или
  не будут получены — решение по проекту для USPTO/EPO). Написаны по
  документации, БЕЗ проверки вживую. Если что-то в структуре запроса или
  пути эндпоинта успело измениться — не полагаться на них не глядя, сверить
  с официальной документацией в момент получения ключа:
    USPTO ODP:   https://data.uspto.gov/apis
    EPO OPS:     https://www.epo.org/en/searching-for-patents/data/web-services/ops
    PatentsView: https://search.patentsview.org/docs/

Найденное сохраняется в ту же таблицу feed_items, что заполняет
RSS-collector (обогащение БД, а не разовый ответ на один запрос) —
persist_live_items() дедуплицирует по тому же url_hash, так что повторный
поиск по похожему запросу не задваивает записи.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlencode
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import (
    CONTACT_EMAIL,
    EPO_OPS_KEY,
    EPO_OPS_SECRET,
    GITHUB_TOKEN,
    PATENTSVIEW_API_KEY,
    SEMANTIC_SCHOLAR_API_KEY,
    USPTO_ODP_API_KEY,
)
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
# arXiv — проверено вручную
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
# Semantic Scholar — проверено вручную (ключ рекомендован, не обязателен)
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
# OpenAlex — НЕ ПРОВЕРЕНО ВЖИВУЮ. Ключ не нужен вообще (mailto= в query —
# тот же принцип вежливого пула, что уже используется для arXiv/Crossref
# через User-Agent). Огромное покрытие (~250М+ работ) — реальная замена
# главному узкому месту "мало платформ реально отвечают".
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
# GitHub — НЕ ПРОВЕРЕНО ВЖИВУЮ. Без токена работает (60 запросов/час на IP),
# с токеном — 5000/час. Другой тип сигнала, чем академические источники:
# ранний рост open-source активности вокруг темы, до появления публикаций.
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
# Hacker News (через Algolia HN Search — стандартный публичный API для
# поиска по HN, ключ не нужен). НЕ ПРОВЕРЕНО ВЖИВУЮ. Важная оговорка: у
# обычных ссылочных постов на HN нет своего текста (story_text есть только
# у Ask/Show HN) — без summary такие кандидаты не пройдут
# classifier._clean_model_input (MIN_SUMMARY_CHARS) и не попадут в модель,
# это ожидаемо, не баг.
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
# Reddit — ПРОВЕРЕНО, И ПРОВЕРКА ПОКАЗАЛА ОТКАЗ: публичный keyless-путь
# (www.reddit.com/search.json) без OAuth возвращает 403 — анти-бот
# HTML-страница вместо JSON, не изредка, а стабильно с датацентровского IP.
# Рабочий путь есть — OAuth через client_credentials (тот же паттерн, что
# EPO OPS выше), но это ровно та регистрация приложения, которой этот заход
# сознательно избегал (решение по проекту). НЕ включено в fetch_all_live().
# Низкий trust_level в LIVE_SOURCE_META оставлен осознанно на случай, если
# OAuth всё же будет подключён позже — соцсеть, ТЗ требует не считать такие
# источники единственным основанием для сигнала.
# --------------------------------------------------------------------------

REDDIT_SEARCH_API = "https://www.reddit.com/search.json"


def fetch_reddit_live(client: httpx.Client, query: str, *, limit: int = 20) -> list[LiveItem]:
    params = {"q": query, "sort": "relevance", "limit": str(limit)}
    resp = _get(client, f"{REDDIT_SEARCH_API}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        return []

    try:
        data = resp.json()
    except ValueError:
        log.error("reddit: не удалось разобрать ответ как JSON")
        return []

    items = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        title = post.get("title")
        permalink = post.get("permalink")
        if not title or not permalink:
            continue
        created_at = None
        if post.get("created_utc"):
            try:
                created_at = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                pass
        items.append(LiveItem(
            source_key="reddit",
            url=f"https://www.reddit.com{permalink}",
            title=title,
            published_at=created_at,
            summary=post.get("selftext") or None,
            author=post.get("author"),
            raw_categories=post.get("subreddit"),
        ))
    return items


# --------------------------------------------------------------------------
# PatentsView — ПРОВЕРЕНО, И ПРОВЕРКА ПОКАЗАЛА ПРОБЛЕМУ: search.patentsview.org
# не резолвится (NXDOMAIN), а офиц. сайт patentsview.org/apis/purpose теперь
# 301-редиректит на data.uspto.gov/support/transition-guide/patentsview —
# PatentsView слился с USPTO ODP в единую платформу. Это НЕ независимая
# keyless-альтернатива патентному пробелу, как предполагалось изначально:
# тот же заблокированный ключ, что и у USPTO ODP (см. fetch_uspto_live).
# Оставлено в файле нерабочим по той же причине — как задел, если ключ
# ODP всё же появится. НЕ включено в fetch_all_live().
# --------------------------------------------------------------------------

PATENTSVIEW_API = "https://api.patentsview.org/patents/query"


def fetch_patentsview_live(client: httpx.Client, query: str, *, limit: int = 20) -> list[LiveItem]:
    headers = {"X-Api-Key": PATENTSVIEW_API_KEY} if PATENTSVIEW_API_KEY else None
    params = {
        "q": json.dumps({"_text_any": {"patent_title": query}}),
        "f": json.dumps(["patent_id", "patent_title", "patent_date", "patent_abstract"]),
        "o": json.dumps({"size": limit}),
    }
    resp = _get(client, f"{PATENTSVIEW_API}?{urlencode(params)}", headers=headers)
    if resp is None or resp.status_code != 200:
        return []

    try:
        data = resp.json()
    except ValueError:
        log.error("patentsview: не удалось разобрать ответ как JSON")
        return []

    items = []
    for patent in data.get("patents", []):
        title = patent.get("patent_title")
        patent_id = patent.get("patent_id")
        if not title or not patent_id:
            continue
        published_at = None
        if patent.get("patent_date"):
            try:
                published_at = datetime.fromisoformat(patent["patent_date"]).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        items.append(LiveItem(
            source_key="patentsview",
            url=f"https://patents.google.com/patent/US{patent_id}",
            title=title,
            published_at=published_at,
            summary=patent.get("patent_abstract"),
            raw_categories="patent_grant",
        ))
    return items


# --------------------------------------------------------------------------
# USPTO ODP — ключ есть в схеме, но не у нас. НЕ ПРОВЕРЕНО ВЖИВУЮ.
# Путь эндпоинта и форма запроса — по документации Open Data Portal,
# сверить перед реальным использованием: https://data.uspto.gov/apis
# --------------------------------------------------------------------------

USPTO_ODP_SEARCH_API = "https://api.uspto.gov/api/v1/patent/applications/search"


def fetch_uspto_live(client: httpx.Client, query: str, *, limit: int = 20) -> list[LiveItem]:
    if not USPTO_ODP_API_KEY:
        log.info("uspto_odp: USPTO_ODP_API_KEY не задан — пропуск")
        return []

    headers = {"X-API-KEY": USPTO_ODP_API_KEY, "Accept": "application/json"}
    params = {"q": query, "limit": str(limit)}
    resp = _get(client, f"{USPTO_ODP_SEARCH_API}?{urlencode(params)}", headers=headers)
    if resp is None or resp.status_code != 200:
        return []

    try:
        data = resp.json()
    except ValueError:
        log.error("uspto_odp: не удалось разобрать ответ как JSON")
        return []

    items = []
    for entry in data.get("patentFileWrapperDataBag", data.get("results", [])):
        title = entry.get("inventionTitle") or entry.get("title")
        app_number = entry.get("applicationNumberText") or entry.get("applicationNumber")
        if not title or not app_number:
            continue
        filing_date = entry.get("filingDate")
        published_at = None
        if filing_date:
            try:
                published_at = datetime.fromisoformat(filing_date).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        items.append(LiveItem(
            source_key="uspto_odp",
            url=f"https://ppubs.uspto.gov/pubwebapp/application-file/{app_number}",
            title=title,
            published_at=published_at,
            raw_categories="patent_application",
        ))
    return items


# --------------------------------------------------------------------------
# EPO OPS — ключей нет. НЕ ПРОВЕРЕНО ВЖИВУЮ. OAuth2 client_credentials,
# путь и параметры — по документации, сверить перед использованием:
# https://www.epo.org/en/searching-for-patents/data/web-services/ops
# --------------------------------------------------------------------------

EPO_OPS_TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
EPO_OPS_SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search"


def _epo_ops_token(client: httpx.Client) -> str | None:
    """OAuth2 client_credentials — POST, не GET, поэтому не через общий
    _get() (тот ретраит GET-запросы). Ретраев здесь нет намеренно: клиент
    не проверен вживую, лишняя магия усложнит отладку, когда ключ появится.
    """
    if not EPO_OPS_KEY or not EPO_OPS_SECRET:
        return None
    basic = base64.b64encode(f"{EPO_OPS_KEY}:{EPO_OPS_SECRET}".encode()).decode()
    try:
        resp = client.post(
            EPO_OPS_TOKEN_URL,
            headers={"Authorization": f"Basic {basic}"},
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as exc:
        log.error("epo_ops: не удалось получить токен: %s", exc)
        return None


def fetch_epo_ops_live(client: httpx.Client, query: str) -> list[LiveItem]:
    if not EPO_OPS_KEY or not EPO_OPS_SECRET:
        log.info("epo_ops: EPO_OPS_KEY/EPO_OPS_SECRET не заданы — пропуск")
        return []

    token = _epo_ops_token(client)
    if not token:
        return []

    cql = f'ti="{query}"'
    resp = _get(
        client,
        f"{EPO_OPS_SEARCH_URL}?q={quote(cql)}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp is None or resp.status_code != 200:
        return []

    try:
        data = resp.json()
        docs = (
            data.get("ops:world-patent-data", {})
            .get("ops:biblio-search", {})
            .get("ops:search-result", {})
            .get("ops:publication-reference", [])
        )
        if isinstance(docs, dict):
            docs = [docs]
    except (ValueError, AttributeError) as exc:
        log.error("epo_ops: неожиданная форма ответа: %s", exc)
        return []

    items = []
    for doc in docs:
        try:
            doc_id = doc["document-id"]
            pub_number = doc_id["doc-number"]["$"]
            country = doc_id.get("country", {}).get("$", "")
        except (KeyError, TypeError):
            continue
        items.append(LiveItem(
            source_key="epo_ops",
            url=f"https://worldwide.espacenet.com/patent/search/family/publication/{country}{pub_number}",
            title=f"{country}{pub_number}",
            published_at=None,
            raw_categories="patent_publication",
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
    "patentsview": dict(
        name="PatentsView", site_url="https://patentsview.org", source_type="patent_office",
        trust_level="high", language="EN", topics="Патенты США",
    ),
    "github": dict(
        name="GitHub", site_url="https://github.com", source_type="code_repository",
        # Первичная активность (код), не мнение — выше соцсетей, но не
        # институциональный источник вроде arXiv/USPTO
        trust_level="medium", language="EN", topics="Все",
    ),
    "hackernews": dict(
        name="Hacker News", site_url="https://news.ycombinator.com", source_type="community_forum",
        trust_level="medium", language="EN", topics="Все",
    ),
    "reddit": dict(
        name="Reddit", site_url="https://reddit.com", source_type="social_media",
        # ТЗ: соцсети не могут быть единственным основанием для сигнала
        trust_level="low", language="EN", topics="Все",
    ),
    "uspto_odp": dict(
        name="USPTO ODP", site_url="https://www.uspto.gov", source_type="patent_office",
        trust_level="high", language="EN", topics="Все (сильнее Роботы, Edge, ИИ-инфра)",
    ),
    "epo_ops": dict(
        name="EPO OPS", site_url="https://www.epo.org/en/searching-for-patents/data/web-services/ops",
        source_type="patent_office", trust_level="high", language="EN", topics="Все",
    ),
}


def fetch_all_live(query: str) -> list[LiveItem]:
    """Опросить все живые источники. Падение одного не должно ронять
    остальные — тот же принцип изоляции, что в RSS-collector.

    USPTO ODP и EPO OPS сюда сознательно не включены: ключи не будут
    получены (решение по проекту), а без ключа fetch_uspto_live()/
    fetch_epo_ops_live() и так всегда возвращали пусто — незачем на каждый
    поиск дёргать заведомо пустой вызов и писать в лог "пропуск". Сами
    функции и записи в LIVE_SOURCE_META оставлены в файле нетронутыми —
    написаны по документации, в дело не введены; если ключ всё же появится,
    достаточно вернуть две строчки в список ниже.

    PatentsView сюда НЕ включён — проверка показала, что он слился с
    USPTO ODP (см. комментарий у fetch_patentsview_live) и требует тот же
    недоступный ключ. Патентный пробел остаётся открытым, честно.

    Reddit сюда тоже НЕ включён — проверка показала стабильный 403 на
    keyless-путь без OAuth (см. комментарий у fetch_reddit_live); OAuth
    сознательно решили не подключать (та же регистрация, которой этот
    заход избегал).
    """
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
    """LIVE_SOURCE_META['language'] — язык ИНТЕРФЕЙСА источника (сайты
    arXiv/Crossref/USPTO/EPO — все английские), не язык конкретной работы.
    Crossref, например, индексирует и русскоязычные журналы — если слепо
    наследовать язык источника на каждую запись (как было раньше), такая
    статья получает ложную метку EN и уходит в classifier.py как валидный
    английский вход; модель обучена и проверена только на английском (см.
    classifier.py) и на русском тексте выдаёт мусорную классификацию —
    поймано вручную: набор русскоязычных Crossref-статей про нейроморфные
    чипы классифицировался как "шум" с предикторами из русских стоп-слов
    ("из", "это", "на", "для"). Грубая эвристика вместо детектора языка:
    для двуязычного EN/RU корпуса наличия кириллицы достаточно, без новой
    ML-зависимости.
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

        # author — VARCHAR(255) в реальной схеме; у научных статей бывает
        # 15+ соавторов через запятую, легко превышает лимит (поймано на
        # реальной arXiv-статье с 18 авторами) — усекаем на границе записи,
        # а не в каждом fetcher'е отдельно
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
