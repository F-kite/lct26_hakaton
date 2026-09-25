"""Научно-патентные источники: поисковые API, а не статичные ленты.

В отличие от RSS (core.py) и архивных HTML/sitemap-обходов (archive.py), у
arXiv и Semantic Scholar нет фиксированного URL для поллинга — это поисковые
API: каждый прогон ищет по теме/запросу, а не скачивает один и тот же адрес.
Поэтому отдельный модуль. Персистентность и денормализация переиспользуют
archive.ArchiveItem / archive.persist_items — те уже умеют писать в feed_items
той же схемой, что и живой RSS-сбор.

Разделение источников этого файла:

arXiv (fetch_arxiv)
    Atom API (export.arxiv.org/api/query), без ключа. Проверено вручную:
    жёсткий rate-limit на общий (не привязанный к ключу) пул — первый же
    "холодный" запрос без паузы поймал 429. Обязателен identifying
    User-Agent с контактным email и пауза между запросами (см. ARXIV_MIN_INTERVAL).
    source_type="preprint" — без peer review, это НЕ то же самое по весу
    доказательства, что журнальная публикация.

Semantic Scholar (fetch_semantic_scholar)
    Academic Graph API, ключ формально "рекомендован", не обязателен.
    Проверено вручную: безключевой пул сейчас стабильно отдаёт 429 на
    каждую попытку (это общий инфраструктурный лимит Semantic Scholar,
    не бага здесь) — код рабочий и корректный, но для реальной эксплуатации
    нужен SEMANTIC_SCHOLAR_API_KEY. Без ключа функция просто вернёт мало
    или ничего — это ожидаемо, не повод считать модуль сломанным.

Crossref (verify_doi)
    НЕ источник кандидатов — по своей роли в таблице источников это
    верификация и дедупликация: подтверждение, что DOI, найденный в другом
    источнике (arXiv/Semantic Scholar/упоминание в новости), существует,
    и получение его канонических метаданных. Поэтому это не "коллектор",
    возвращающий список ArchiveItem, а точечная lookup-функция.

Ничего не подключено к loop — как и archive.py, отдельные команды в main.py.
Что искать (конкретные search_query) — решение аналитика/скоринга, не
зашито здесь: эта часть отвечает только за механику запроса и сохранения.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx

from .archive import ArchiveItem, REQUEST_TIMEOUT, _get, persist_items

log = logging.getLogger(__name__)

# Контактный email для polite pool (arXiv/Crossref вежливо просят себя
# идентифицировать). НЕ хардкодить личный email — берётся из окружения,
# чтобы не утекать в закоммиченный код репозитория, который может стать
# публичным (SourceCraft).
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "team@example.com")
USER_AGENT = f"LCT2026-WeakSignals/0.1 (hackathon research collector; mailto:{CONTACT_EMAIL})"


def _client(extra_headers: dict[str, str] | None = None) -> httpx.Client:
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    return httpx.Client(follow_redirects=True, timeout=REQUEST_TIMEOUT, headers=headers)


# --------------------------------------------------------------------------
# arXiv
# --------------------------------------------------------------------------

ARXIV_API = "http://export.arxiv.org/api/query"
# arXiv просит не чаще 1 запроса/3с на их общий пул. fetch_arxiv() делает один
# запрос за вызов — паузу между запросами держит вызывающий код, если он
# опрашивает несколько тем подряд (например, будущий цикл по seed-темам).

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _clean_ws(text: str | None) -> str | None:
    """Атом-фиды arXiv переносят title/summary по строкам с отступами."""
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip() or None


def _parse_arxiv_feed(xml_bytes: bytes) -> list[ArchiveItem]:
    root = ElementTree.fromstring(xml_bytes)
    items: list[ArchiveItem] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = _clean_ws(entry.findtext("atom:title", namespaces=ATOM_NS))
        if not title:
            continue

        url = None
        for link in entry.findall("atom:link", ATOM_NS):
            if link.get("rel") == "alternate":
                url = link.get("href")
                break
        if not url:
            url = entry.findtext("atom:id", namespaces=ATOM_NS)
        if not url:
            continue

        published_raw = entry.findtext("atom:published", namespaces=ATOM_NS)
        published_at = None
        if published_raw:
            try:
                published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        authors = [
            a.findtext("atom:name", namespaces=ATOM_NS)
            for a in entry.findall("atom:author", ATOM_NS)
        ]
        categories = [
            c.get("term") for c in entry.findall("atom:category", ATOM_NS) if c.get("term")
        ]

        items.append(ArchiveItem(
            source_key="arxiv",
            url=url,
            title=title,
            published_at=published_at,
            summary=_clean_ws(entry.findtext("atom:summary", namespaces=ATOM_NS)),
            author=", ".join(a for a in authors if a) or None,
            raw_categories=", ".join(categories) if categories else None,
        ))
    return items


def fetch_arxiv(
    client: httpx.Client, search_query: str, *, max_results: int = 100,
) -> list[ArchiveItem]:
    """Поиск в arXiv. search_query — синтаксис arXiv: 'cat:cs.AI AND abs:agentic'.

    arXiv не фильтрует по датам на уровне query-параметра (только сортировка) —
    для диапазона фильтровать результат после парсинга по published_at.
    """
    params = {
        "search_query": search_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
    }
    resp = _get(client, f"{ARXIV_API}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        log.error("arxiv: запрос не удался (query=%r)", search_query)
        return []
    try:
        return _parse_arxiv_feed(resp.content)
    except ElementTree.ParseError as exc:
        log.error("arxiv: не удалось разобрать ответ: %s", exc)
        return []


# --------------------------------------------------------------------------
# Semantic Scholar
# --------------------------------------------------------------------------

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = "title,abstract,url,publicationDate,authors,externalIds,venue"


def fetch_semantic_scholar(
    client: httpx.Client, query: str, *, limit: int = 50, api_key: str | None = None,
) -> list[ArchiveItem]:
    """Поиск в Semantic Scholar. Без api_key безключевой пул может быть
    перегружен (проверено вручную, 429 на каждой попытке) — не значит,
    что код сломан, значит, что для продакшена нужен ключ.
    """
    params = {
        "query": query,
        "sort": "publicationDate:desc",
        "limit": str(limit),
        "fields": SEMANTIC_SCHOLAR_FIELDS,
    }
    headers = {"x-api-key": api_key} if api_key else None
    resp = _get(client, f"{SEMANTIC_SCHOLAR_API}?{urlencode(params)}", headers=headers)
    if resp is None or resp.status_code != 200:
        log.error("semantic_scholar: запрос не удался (query=%r) — без ключа пул может "
                   "быть перегружен, см. SEMANTIC_SCHOLAR_API_KEY", query)
        return []

    data = resp.json()
    items: list[ArchiveItem] = []
    for paper in data.get("data", []):
        title = paper.get("title")
        url = paper.get("url")
        if not title or not url:
            continue

        published_at = None
        pub_date = paper.get("publicationDate")
        if pub_date:
            try:
                published_at = datetime.fromisoformat(pub_date).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        authors = [a.get("name") for a in (paper.get("authors") or [])]
        ext_ids = paper.get("externalIds") or {}
        doi = ext_ids.get("DOI")

        items.append(ArchiveItem(
            source_key="semantic_scholar",
            url=url,
            title=title,
            published_at=published_at,
            summary=paper.get("abstract"),
            author=", ".join(a for a in authors if a) or None,
            raw_categories=f"doi:{doi}" if doi else (paper.get("venue") or None),
        ))
    return items


# --------------------------------------------------------------------------
# Crossref — верификация DOI, не источник кандидатов
# --------------------------------------------------------------------------

CROSSREF_API = "https://api.crossref.org/works"


@dataclass
class CrossrefWork:
    doi: str
    title: str | None
    type: str | None
    published: str | None  # YYYY, YYYY-MM или YYYY-MM-DD — по точности исходных данных
    is_referenced_by_count: int | None


def verify_doi(client: httpx.Client, doi: str) -> CrossrefWork | None:
    """Подтвердить существование DOI и получить канонические метаданные.

    Роль по ТЗ: верификация и дедупликация публикаций, найденных в других
    источниках (arXiv/Semantic Scholar/упоминание в новости) — не discovery
    новых кандидатов, поэтому нет fetch_crossref() в духе fetch_arxiv().
    """
    doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    resp = _get(client, f"{CROSSREF_API}/{doi}")
    if resp is None or resp.status_code != 200:
        return None

    msg = resp.json().get("message", {})
    date_parts = None
    for key in ("published", "published-print", "published-online"):
        if msg.get(key, {}).get("date-parts"):
            date_parts = msg[key]["date-parts"][0]
            break
    published = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(date_parts)) if date_parts else None

    titles = msg.get("title") or []
    return CrossrefWork(
        doi=msg.get("DOI", doi),
        title=titles[0] if titles else None,
        type=msg.get("type"),
        published=published,
        is_referenced_by_count=msg.get("is-referenced-by-count"),
    )


# --------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------

def run_arxiv(search_query: str, *, max_results: int = 100, save: bool = False) -> list[ArchiveItem]:
    with _client() as client:
        items = fetch_arxiv(client, search_query, max_results=max_results)
    if save and items:
        n = persist_items(items)
        log.info("[arxiv] сохранено новых: %d/%d", n, len(items))
    return items


def run_semantic_scholar(
    query: str, *, limit: int = 50, save: bool = False, api_key: str | None = None,
) -> list[ArchiveItem]:
    api_key = api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    with _client() as client:
        items = fetch_semantic_scholar(client, query, limit=limit, api_key=api_key)
    if save and items:
        n = persist_items(items)
        log.info("[semantic_scholar] сохранено новых: %d/%d", n, len(items))
    return items


def run_verify_doi(doi: str) -> CrossrefWork | None:
    with _client() as client:
        return verify_doi(client, doi)


def main() -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(
        prog="python -m collector.academic",
        description="Поиск по научным API (arXiv, Semantic Scholar) и верификация DOI (Crossref).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("arxiv")
    a.add_argument("query", help="arXiv search_query, напр. 'cat:cs.AI AND abs:agentic'")
    a.add_argument("--max-results", type=int, default=100)
    a.add_argument("--save", action="store_true")

    s = sub.add_parser("semantic-scholar")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--save", action="store_true")

    v = sub.add_parser("verify-doi")
    v.add_argument("doi")

    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")

    if args.cmd == "arxiv":
        items = run_arxiv(args.query, max_results=args.max_results, save=args.save)
        print(f"\n[arxiv] найдено: {len(items)}")
        for it in items[:20]:
            print(f"  {it.published_at} | {it.title[:90]!r}")
        return 0

    if args.cmd == "semantic-scholar":
        items = run_semantic_scholar(args.query, limit=args.limit, save=args.save)
        print(f"\n[semantic_scholar] найдено: {len(items)}")
        for it in items[:20]:
            print(f"  {it.published_at} | {it.title[:90]!r}")
        return 0

    if args.cmd == "verify-doi":
        with _client() as client:
            work = verify_doi(client, args.doi)
        if work is None:
            print(f"DOI не найден или Crossref недоступен: {args.doi}")
            return 1
        print(f"DOI:        {work.doi}")
        print(f"title:      {work.title}")
        print(f"type:       {work.type}")
        print(f"published:  {work.published}")
        print(f"cited by:   {work.is_referenced_by_count}")
        return 0

    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
