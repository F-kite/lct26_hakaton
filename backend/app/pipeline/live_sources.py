"""Живой поиск по внешним API во время запроса пользователя — то, чего
не хватало для «в реальном времени, не ограничиваясь датасетом» из ТЗ.

Раньше (candidates.py) поиск смотрел только в уже накопленную БД. Здесь —
пять источников, которые умеют искать по произвольному запросу «на лету»:
arXiv, Semantic Scholar, Crossref (уже были клиенты, только для другого —
см. ниже), USPTO ODP, EPO OPS (патенты, новые).

По решению: код здесь ДУБЛИРУЕТ часть логики RSS-collector/academic.py
(arXiv, Semantic Scholar, Crossref) — сознательно, чтобы backend не зависел
от чужого Docker-образа (тот же принцип, что уже применён к моделям
Source/FeedItem в db.py).

Статус проверки каждого клиента:
- arXiv, Semantic Scholar, Crossref — проверены вручную на реальных
  запросах (тот же способ, что и в RSS-collector).
- USPTO ODP, EPO OPS — ключей нет ни у кого в команде. Написаны по
  документации, БЕЗ проверки вживую. Если что-то в структуре запроса или
  пути эндпоинта успело измениться — не полагаться на них не глядя, сверить
  с официальной документацией в момент получения ключа:
    USPTO ODP: https://data.uspto.gov/apis
    EPO OPS:   https://www.epo.org/en/searching-for-patents/data/web-services/ops

Найденное сохраняется в ту же таблицу feed_items, что заполняет
RSS-collector (обогащение БД, а не разовый ответ на один запрос) —
persist_live_items() дедуплицирует по тому же url_hash, так что повторный
поиск по похожему запросу не задваивает записи.
"""

from __future__ import annotations

import base64
import hashlib
import logging
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
    CONTACT_EMAIL, EPO_OPS_KEY, EPO_OPS_SECRET, SEMANTIC_SCHOLAR_API_KEY, USPTO_ODP_API_KEY,
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
    остальные — тот же принцип изоляции, что в RSS-collector."""
    fetchers = [
        ("arxiv", fetch_arxiv_live),
        ("semantic_scholar", fetch_semantic_scholar_live),
        ("crossref", search_crossref_live),
        ("uspto_odp", fetch_uspto_live),
        ("epo_ops", fetch_epo_ops_live),
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
            language=src.language,
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
