"""Живой поиск по внешним API во время запроса — arXiv, Semantic Scholar,
Crossref, OpenAlex, GitHub, Hacker News, NSF, UKRI GtR, CORDIS, Europe PMC.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import CONTACT_EMAIL, GITHUB_TOKEN, OPENALEX_API_KEY, SEMANTIC_SCHOLAR_API_KEY
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
def _day_start_ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _day_end_ts(d: date) -> int:
    return _day_start_ts(d) + 86399


def _in_range(published_at: datetime | None, date_from: date | None, date_to: date | None) -> bool:
    """Страховка поверх фильтров API: источники трактуют даты по-своему
    (и не все умеют фильтровать). Запись без даты при заданном диапазоне
    отбрасывается — проверить её попадание нельзя."""
    if date_from is None and date_to is None:
        return True
    if published_at is None:
        return False
    d = published_at.date()
    return (date_from is None or d >= date_from) and (date_to is None or d <= date_to)


# --------------------------------------------------------------------------
# arXiv
# --------------------------------------------------------------------------

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_arxiv_live(
    client: httpx.Client, query: str, *, max_results: int = 30,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    search_query = f"all:{query}"
    if date_from or date_to:
        # submittedDate требует обе границы — открытую заменяем крайним значением
        lo = (date_from or date(1991, 1, 1)).strftime("%Y%m%d") + "0000"
        hi = (date_to or date(2999, 12, 31)).strftime("%Y%m%d") + "2359"
        search_query += f" AND submittedDate:[{lo} TO {hi}]"
    params = {
        "search_query": search_query,
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


def fetch_semantic_scholar_live(
    client: httpx.Client, query: str, *, limit: int = 30,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    params = {
        "query": query,
        "limit": str(limit),
        "fields": "title,abstract,url,publicationDate,authors,externalIds",
    }
    if date_from or date_to:
        params["publicationDateOrYear"] = f"{date_from or ''}:{date_to or ''}"
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


def search_crossref_live(
    client: httpx.Client, query: str, *, rows: int = 20,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    params = {"query": query, "rows": str(rows)}
    filters = []
    if date_from:
        filters.append(f"from-pub-date:{date_from}")
    if date_to:
        filters.append(f"until-pub-date:{date_to}")
    if filters:
        params["filter"] = ",".join(filters)
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


def openalex_params(params: dict) -> dict:
    """mailto — «вежливый» пул; api_key — бюджет и лимит в 10 раз выше бесплатного."""
    params = {**params, "mailto": CONTACT_EMAIL}
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    return params


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


def fetch_openalex_live(
    client: httpx.Client, query: str, *, per_page: int = 25,
    date_from: date | None = None, date_to: date | None = None, language: str | None = None,
) -> list[LiveItem]:
    params = openalex_params({"search": query, "per-page": str(per_page)})
    filters = [f"language:{language}"] if language else []
    if date_from:
        filters.append(f"from_publication_date:{date_from}")
    if date_to:
        filters.append(f"to_publication_date:{date_to}")
    if filters:
        params["filter"] = ",".join(filters)
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


def fetch_github_live(
    client: httpx.Client, query: str, *, limit: int = 20,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    q = query
    if date_from and date_to:
        q += f" created:{date_from}..{date_to}"
    elif date_from:
        q += f" created:>={date_from}"
    elif date_to:
        q += f" created:<={date_to}"
    params = {"q": q, "per_page": str(limit)}
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


def fetch_hackernews_live(
    client: httpx.Client, query: str, *, limit: int = 20,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    params = {"query": query, "tags": "story", "hitsPerPage": str(limit)}
    numeric = []
    if date_from:
        numeric.append(f"created_at_i>={_day_start_ts(date_from)}")
    if date_to:
        numeric.append(f"created_at_i<={_day_end_ts(date_to)}")
    if numeric:
        params["numericFilters"] = ",".join(numeric)
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


_STOPWORDS = frozenset({"the", "and", "for", "with", "from", "into", "that", "this", "its", "are", "was", "using", "based"})


def _query_tokens(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", query.lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def _relevant(query: str, text: str) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True
    lowered = text.lower()
    return sum(t in lowered for t in tokens) >= max(1, len(tokens) // 2)


NSF_AWARDS_API = "https://www.research.gov/awardapi-service/v1/awards.json"


def fetch_nsf_live(
    client: httpx.Client, query: str, *, limit: int = 20,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    def search(keyword: str) -> list[dict] | None:
        params = {
            "keyword": keyword,
            "rpp": str(limit),
            "printFields": "id,title,abstractText,date,awardeeName,pdPIName,fundProgramName",
        }
        if date_from:
            params["dateStart"] = date_from.strftime("%m/%d/%Y")
        if date_to:
            params["dateEnd"] = date_to.strftime("%m/%d/%Y")
        resp = _get(client, f"{NSF_AWARDS_API}?{urlencode(params)}")
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json().get("response", {}).get("award") or []
        except ValueError:
            log.error("nsf: не удалось разобрать ответ как JSON")
            return None

    awards = search(f'"{query}"')
    if awards is None:
        return []
    if not awards:
        awards = search(query) or []

    items = []
    for award in awards:
        title, award_id = award.get("title"), award.get("id")
        if not title or not award_id:
            continue
        if not _relevant(query, f"{title} {award.get('abstractText') or ''}"):
            continue
        published_at = None
        if award.get("date"):
            try:
                published_at = datetime.strptime(award["date"], "%m/%d/%Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        items.append(LiveItem(
            source_key="nsf",
            url=f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award_id}",
            title=" ".join(title.split()),
            published_at=published_at,
            summary=" ".join((award.get("abstractText") or "").split()) or None,
            author=award.get("awardeeName"),
            raw_categories=award.get("fundProgramName"),
        ))
    return items


UKRI_GTR_API = "https://gtr.ukri.org/gtr/api/projects"


def fetch_ukri_live(
    client: httpx.Client, query: str, *, limit: int = 20,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    params = {"q": query, "s": str(max(limit, 10))}
    resp = _get(
        client, f"{UKRI_GTR_API}?{urlencode(params)}",
        headers={"Accept": "application/vnd.rcuk.gtr.json-v7"},
    )
    if resp is None or resp.status_code != 200:
        return []

    try:
        projects = resp.json().get("project") or []
    except ValueError:
        log.error("ukri: не удалось разобрать ответ как JSON")
        return []

    items = []
    for project in projects:
        title = project.get("title")
        ref = next(
            (i.get("value") for i in (project.get("identifiers") or {}).get("identifier", [])
             if i.get("type") == "RCUK"),
            None,
        )
        if not title or not ref:
            continue
        published_at = None
        if project.get("created"):
            try:
                published_at = datetime.fromtimestamp(project["created"] / 1000, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError, OSError):
                pass
        items.append(LiveItem(
            source_key="ukri",
            url=f"https://gtr.ukri.org/projects?ref={ref}",
            title=" ".join(title.split()),
            published_at=published_at,
            summary=" ".join((project.get("abstractText") or project.get("techAbstractText") or "").split()) or None,
            raw_categories=project.get("leadFunder"),
        ))
    return items


CORDIS_SEARCH_API = "https://cordis.europa.eu/search/en"


def fetch_cordis_live(
    client: httpx.Client, query: str, *, limit: int = 20,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    def search(terms: str) -> list[dict] | None:
        params = {"q": f"contenttype='project' AND {terms}", "format": "json", "num": str(limit)}
        resp = _get(client, f"{CORDIS_SEARCH_API}?{urlencode(params)}")
        if resp is None or resp.status_code != 200:
            return None
        try:
            hits = resp.json().get("hits", {}).get("hit") or []
        except ValueError:
            log.error("cordis: не удалось разобрать ответ как JSON")
            return None
        return [hits] if isinstance(hits, dict) else hits

    tokens = _query_tokens(query)
    if not tokens:
        return []
    hits = search(f"'{' '.join(tokens)}'")
    if hits is None:
        return []
    if not hits and len(tokens) > 1:
        hits = search(" AND ".join(f"'{t}'" for t in tokens)) or []

    items = []
    for hit in hits:
        project = hit.get("project") or {}
        title, project_id = project.get("title"), project.get("id")
        if not title or not project_id:
            continue
        published_at = None
        if project.get("startDate"):
            try:
                published_at = datetime.fromisoformat(project["startDate"]).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        acronym = project.get("acronym")
        title = " ".join(title.split())
        if acronym and not title.lower().startswith(acronym.lower()):
            title = f"{acronym}: {title}"
        items.append(LiveItem(
            source_key="cordis",
            url=f"https://cordis.europa.eu/project/id/{project_id}",
            title=title,
            published_at=published_at,
            summary=" ".join((project.get("objective") or project.get("teaser") or "").split()) or None,
        ))
    return items


def fetch_openalex_ru_live(
    client: httpx.Client, query: str, *, date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    return fetch_openalex_live(client, query, date_from=date_from, date_to=date_to, language="ru")


_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_NOT_ANALYTICS_RE = re.compile(
    r"deliverable|work ?package|\bwp ?\d|progress report|periodic report|final report of|"
    r"annual report|minutes of|thesis|dissertation|data ?set|supplementary",
    re.IGNORECASE,
)
ANALYST_SOURCE_KEYS = {
    "openalex_reports", "mckinsey", "stanford_hai", "hse_expertise", "bis_fsi", "bis_speeches", "fsisac",
}


def fetch_openalex_reports_live(
    client: httpx.Client, query: str, *, per_page: int = 15,
    date_from: date | None = None, date_to: date | None = None, language: str | None = None,
) -> list[LiveItem]:
    filters = ["type:report"]
    if language:
        filters.append(f"language:{language}")
    if date_from:
        filters.append(f"from_publication_date:{date_from}")
    if date_to:
        filters.append(f"to_publication_date:{date_to}")
    params = openalex_params({"search": query, "per-page": str(per_page), "filter": ",".join(filters)})
    resp = _get(client, f"{OPENALEX_API}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        return []
    try:
        works = resp.json().get("results") or []
    except ValueError:
        return []

    items = []
    for work in works:
        title = work.get("title") or work.get("display_name")
        url = work.get("doi") or (work.get("primary_location") or {}).get("landing_page_url") or work.get("id")
        summary = _reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        if not title or not url or not summary or _NOT_ANALYTICS_RE.search(title) or _CJK_RE.search(title):
            continue
        published_at = None
        if work.get("publication_date"):
            try:
                published_at = datetime.fromisoformat(work["publication_date"]).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        publisher = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
        items.append(LiveItem(
            source_key="openalex_reports",
            url=url,
            title=" ".join(title.split()),
            published_at=published_at,
            summary=summary,
            author=publisher,
            raw_categories="report",
        ))
    return items


def fetch_analyst_reports(
    query: str, original_query: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    """Отчёты по запросу — отдельно от кандидатов: они оценивают сигналы, а не конкурируют с ними."""
    jobs = [(query, "en")]
    if original_query and _CYRILLIC_RE.search(original_query):
        jobs.append((original_query, "ru"))
    found: list[LiveItem] = []
    with _client() as client:
        for q, lang in jobs:
            try:
                items = fetch_openalex_reports_live(client, q, date_from=date_from, date_to=date_to, language=lang)
                log.info("[openalex_reports%s] отчётов: %d", f"_{lang}" if lang else "", len(items))
                found += items
            except Exception as exc:
                log.error("[openalex_reports] упал: %s", exc)
    return found


CYBERLENINKA_API = "https://cyberleninka.ru/api/search"


def fetch_cyberleninka_live(
    client: httpx.Client, query: str, *, limit: int = 20,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    try:
        resp = client.post(CYBERLENINKA_API, json={"mode": "articles", "q": query, "size": limit, "from": 0})
    except httpx.HTTPError as exc:
        log.warning("cyberleninka: %s", exc)
        return []
    if resp.status_code != 200:
        return []
    try:
        articles = resp.json().get("articles") or []
    except ValueError:
        log.error("cyberleninka: не удалось разобрать ответ как JSON")
        return []

    items = []
    for a in articles:
        title = re.sub(r"<[^>]+>", "", a.get("name") or "").strip()
        link = a.get("link")
        if not title or not link:
            continue
        published_at = None
        if a.get("year"):
            try:
                published_at = datetime(int(a["year"]), 1, 1, tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
        items.append(LiveItem(
            source_key="cyberleninka",
            url=f"https://cyberleninka.ru{link}",
            title=" ".join(title.split()),
            published_at=published_at,
            summary=" ".join(re.sub(r"<[^>]+>", "", a.get("annotation") or "").split()) or None,
            author=", ".join(a.get("authors") or []) or None,
            raw_categories=a.get("journal"),
        ))
    return items


EUROPEPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def fetch_europepmc_live(
    client: httpx.Client, query: str, *, limit: int = 20,
    date_from: date | None = None, date_to: date | None = None,
) -> list[LiveItem]:
    q = query
    if date_from or date_to:
        q += f" AND FIRST_PDATE:[{date_from or '1900-01-01'} TO {date_to or '2999-12-31'}]"
    params = {"query": q, "resultType": "core", "format": "json", "pageSize": str(limit)}
    resp = _get(client, f"{EUROPEPMC_API}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        return []
    try:
        results = resp.json().get("resultList", {}).get("result") or []
    except ValueError:
        log.error("europepmc: не удалось разобрать ответ как JSON")
        return []

    items = []
    for r in results:
        title = r.get("title")
        if not title:
            continue
        url = (
            f"https://doi.org/{r['doi']}" if r.get("doi")
            else f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"
        )
        published_at = None
        if r.get("firstPublicationDate"):
            try:
                published_at = datetime.fromisoformat(r["firstPublicationDate"]).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        items.append(LiveItem(
            source_key="europepmc",
            url=url,
            title=" ".join(title.split()).rstrip("."),
            published_at=published_at,
            summary=" ".join((r.get("abstractText") or "").split()) or None,
            author=r.get("authorString"),
            raw_categories=r.get("pubType"),
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
    "nsf": dict(
        name="NSF Awards", site_url="https://www.nsf.gov/awardsearch", source_type="grant_database",
        trust_level="high", language="EN", topics="Все",
    ),
    "ukri": dict(
        name="UKRI Gateway to Research", site_url="https://gtr.ukri.org", source_type="grant_database",
        trust_level="high", language="EN", topics="Все",
    ),
    "europepmc": dict(
        name="Europe PMC", site_url="https://europepmc.org", source_type="academic_aggregator",
        trust_level="high", language="EN", topics="Все",
    ),
    "openalex_reports": dict(
        name="OpenAlex — отчёты", site_url="https://openalex.org", source_type="analytical_report",
        trust_level="medium", language="EN", topics="Все",
    ),
    "cyberleninka": dict(
        name="КиберЛенинка", site_url="https://cyberleninka.ru", source_type="academic_aggregator",
        trust_level="medium", language="RU", topics="Все",
    ),
    "cordis": dict(
        name="CORDIS (EU)", site_url="https://cordis.europa.eu", source_type="grant_database",
        trust_level="high", language="EN", topics="Все",
    ),
}


def fetch_all_live(
    query: str, date_from: date | None = None, date_to: date | None = None,
    original_query: str | None = None,
) -> list[LiveItem]:
    """Опросить все живые источники параллельно — они независимы, и время
    фазы определяет самый медленный, а не сумма (retry на 429 у одного
    источника не задерживает остальные). Падение одного не роняет остальные.
    Порядок результатов — как в списке fetchers (httpx.Client потокобезопасен).
    date_from/date_to — необязательный диапазон дат публикации (включительно):
    передаётся в API источника и дополнительно проверяется после ответа.
    """
    fetchers = [
        ("arxiv", fetch_arxiv_live),
        ("semantic_scholar", fetch_semantic_scholar_live),
        ("crossref", search_crossref_live),
        ("openalex", fetch_openalex_live),
        ("github", fetch_github_live),
        ("hackernews", fetch_hackernews_live),
        ("nsf", fetch_nsf_live),
        ("ukri", fetch_ukri_live),
        ("cordis", fetch_cordis_live),
        ("europepmc", fetch_europepmc_live),
    ]
    ru_query = original_query if original_query and _CYRILLIC_RE.search(original_query) else None
    if ru_query:
        fetchers += [
            ("openalex_ru", lambda c, _q, **kw: fetch_openalex_ru_live(c, ru_query, **kw)),
            ("cyberleninka", lambda c, _q, **kw: fetch_cyberleninka_live(c, ru_query, **kw)),
        ]

    with _client() as client:

        def run(entry) -> list[LiveItem]:
            key, fn = entry
            try:
                found = fn(client, query, date_from=date_from, date_to=date_to)
                found = [i for i in found if _in_range(i.published_at, date_from, date_to)]
                log.info("[%s] live-поиск: %d записей", key, len(found))
                return found
            except Exception as exc:
                log.error("[%s] live-поиск упал: %s", key, exc)
                return []

        with ThreadPoolExecutor(max_workers=len(fetchers)) as pool:
            results = list(pool.map(run, fetchers))

    return [item for found in results for item in found]


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
