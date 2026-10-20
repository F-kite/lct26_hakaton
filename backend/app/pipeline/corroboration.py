"""Подтверждения для сигналов ТОП-15 (ТЗ: сведения должны подтверждаться."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from urllib.parse import urlencode

import numpy as np
from sqlalchemy.orm import Session

from ..config import RELEVANCE_THRESHOLD
from .candidates import find_candidates
from .classifier import SignalCandidate
from .display_grouping import DisplayGroup
from .live_sources import (
    ANALYST_SOURCE_KEYS,
    OPENALEX_API,
    LiveItem,
    _client,
    _get,
    _reconstruct_openalex_abstract,
    openalex_params,
    persist_live_items,
)

log = logging.getLogger(__name__)

SIMILAR_MIN = 0.90
SIMILAR_PERCENTILE = 99
MAX_SIMILAR = 4
MAX_CITING = 3
TARGETED_DB_LIMIT = 30
TEXT_WORDS = 150

_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_STOP = {
    "the", "and", "for", "with", "from", "into", "that", "this", "its", "are", "using", "based",
    "via", "new", "toward", "towards", "study", "analysis", "approach", "system", "systems",
}


@dataclass
class Corroboration:
    sources: list[tuple[int, str]] = field(default_factory=list)
    citation_growth: bool = False


def publication_key(title: str | None) -> str:
    return re.sub(r"\W+", " ", (title or "").lower()).strip()


def _text(candidate: SignalCandidate) -> str:
    summary = " ".join(_TAG_RE.sub(" ", candidate.summary or "").split()[:TEXT_WORDS])
    return f"query: {candidate.title}. {summary}"


def _title_terms(title: str, n: int = 3) -> str:
    words = [w for w in _WORD_RE.findall(title.lower()) if len(w) > 3 and w not in _STOP]
    return " ".join(sorted(set(words), key=len, reverse=True)[:n])


def _similar_works(
    session: Session, encoder, groups: list[DisplayGroup], pool: list[SignalCandidate],
    taken: set[str],
) -> tuple[list[list[tuple[int, str]]], float | None]:
    by_key: dict[str, SignalCandidate] = {}
    for c in pool:
        by_key.setdefault(publication_key(c.title), c)
    for g in groups:
        terms = _title_terms(g.representative.title or "")
        if terms:
            for c in find_candidates(session, terms, limit=TARGETED_DB_LIMIT, date_from=date(2000, 1, 1)):
                by_key.setdefault(publication_key(c.title), c)
    for key in taken:
        by_key.pop(key, None)
    candidates = [c for c in by_key.values() if c.title]
    if not candidates:
        return [[] for _ in groups], None

    pool_vecs = np.asarray(list(encoder.embed([_text(c) for c in candidates], batch_size=32)))
    rep_vecs = np.asarray(list(encoder.embed([_text(g.representative) for g in groups])))

    sample = pool_vecs[:500]
    pairwise = (sample @ sample.T)[np.triu_indices(len(sample), 1)]
    threshold = max(SIMILAR_MIN, float(np.percentile(pairwise, SIMILAR_PERCENTILE))) if len(pairwise) else SIMILAR_MIN
    median = float(np.median(pairwise)) if len(pairwise) else None
    log.info("подтверждения: пул %d записей, порог близости %.3f, медиана темы %s",
             len(candidates), threshold, f"{median:.3f}" if median else "—")

    result = []
    sims = pool_vecs @ rep_vecs.T
    for gi in range(len(groups)):
        order = np.argsort(-sims[:, gi])
        picked = [
            (candidates[i].feed_item_ids[0], "similar")
            for i in order[:MAX_SIMILAR * 3] if sims[i, gi] >= threshold
        ][:MAX_SIMILAR]
        result.append(picked)
    return result, median


_DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)
_OPENALEX_ID_RE = re.compile(r"openalex\.org/(W\d+)", re.IGNORECASE)
WORK_FIELDS = "id,doi,title,publication_date,abstract_inverted_index,counts_by_year,related_works"


def _openalex_get(client, path: str, params: dict) -> dict | None:
    params = openalex_params(params)
    resp = _get(client, f"{OPENALEX_API}{path}?{urlencode(params)}")
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _resolve_work(client, url: str, title: str) -> dict | None:
    if m := _OPENALEX_ID_RE.search(url or ""):
        return _openalex_get(client, f"/{m.group(1)}", {"select": WORK_FIELDS})
    doi = None
    if m := _DOI_RE.search(url or ""):
        doi = m.group(0).rstrip(".")
    elif m := _ARXIV_RE.search(url or ""):
        doi = f"10.48550/arxiv.{m.group(1)}"
    if doi:
        data = _openalex_get(client, "", {"filter": f"doi:{doi}", "select": WORK_FIELDS})
        if data and data.get("results"):
            return data["results"][0]
    if title:
        clean_title = re.sub(r"[,:|]", " ", title)[:200]
        data = _openalex_get(client, "", {
            "filter": f"title.search:{clean_title}", "per-page": "3", "select": WORK_FIELDS,
        })
        for work in (data or {}).get("results", []):
            if publication_key(work.get("title")) == publication_key(title):
                return work
    return None


def _to_live_item(work: dict) -> LiveItem | None:
    title = work.get("title")
    url = work.get("doi") or work.get("id")
    if not title or not url:
        return None
    published_at = None
    if work.get("publication_date"):
        try:
            published_at = datetime.fromisoformat(work["publication_date"]).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return LiveItem(
        source_key="openalex", url=url, title=title, published_at=published_at,
        summary=_reconstruct_openalex_abstract(work.get("abstract_inverted_index")),
    )


def _citation_growth(work: dict) -> bool:
    counts = {c["year"]: c.get("cited_by_count", 0) for c in work.get("counts_by_year") or []}
    last = datetime.now(timezone.utc).year - 1
    return counts.get(last, 0) >= 2 and counts.get(last, 0) > counts.get(last - 1, 0)


def _openalex_links(client, group: DisplayGroup, url: str) -> tuple[list[tuple[LiveItem, str]], bool]:
    work = _resolve_work(client, url, group.representative.title or "")
    if not work:
        return [], False
    links: list[tuple[LiveItem, str]] = []
    work_id = work["id"].rsplit("/", 1)[-1]
    citing = _openalex_get(client, "", {
        "filter": f"cites:{work_id}", "sort": "publication_date:desc",
        "per-page": str(MAX_CITING), "select": WORK_FIELDS,
    })
    for w in (citing or {}).get("results", []):
        if item := _to_live_item(w):
            links.append((item, "cites"))
    return links, _citation_growth(work)


def _filter_links_by_meaning(encoder, groups, links, threshold: float):
    flat = [(gi, item, rel) for gi, (items, _) in enumerate(links) for item, rel in items]
    if not flat:
        return links
    texts = [f"query: {item.title}. {' '.join((item.summary or '').split()[:TEXT_WORDS])}" for _, item, _ in flat]
    link_vecs = np.asarray(list(encoder.embed(texts, batch_size=32)))
    rep_vecs = np.asarray(list(encoder.embed([_text(g.representative) for g in groups])))
    kept: list[list[tuple[LiveItem, str]]] = [[] for _ in groups]
    dropped = 0
    for (gi, item, rel), vec in zip(flat, link_vecs):
        if float(vec @ rep_vecs[gi]) >= threshold:
            kept[gi].append((item, rel))
        else:
            dropped += 1
    log.info("подтверждения OpenAlex: оставлено %d, отброшено по смыслу %d (порог %.3f)",
             len(flat) - dropped, dropped, threshold)
    return [(kept[gi], growth) for gi, (_, growth) in enumerate(links)]


MAX_ASSESSMENTS = 3
ASSESSMENT_DB_LIMIT = 1000


def _analyst_pool(session: Session, reports: list[SignalCandidate], queries: list[str]) -> list[SignalCandidate]:
    by_key: dict[str, SignalCandidate] = {}
    for c in reports:
        by_key.setdefault(publication_key(c.title), c)
    for q in queries:
        for c in find_candidates(session, q, limit=ASSESSMENT_DB_LIMIT, date_from=date(2015, 1, 1)):
            if c.sources and c.sources[0] in ANALYST_SOURCE_KEYS:
                by_key.setdefault(publication_key(c.title), c)
    return [c for c in by_key.values() if c.title and c.summary]


def _analyst_assessments(
    encoder, groups: list[DisplayGroup], pool: list[SignalCandidate], query: str,
    signal_threshold: float, taken: set[str],
) -> list[list[tuple[int, str]]]:
    """Отчёты, близкие к сигналу (assessment); если таких нет — по теме запроса (assessment_topic)."""
    pool = [c for c in pool if publication_key(c.title) not in taken]
    if not pool:
        return [[] for _ in groups]
    pool_vecs = np.asarray(list(encoder.embed([_text(c) for c in pool], batch_size=32)))
    rep_vecs = np.asarray(list(encoder.embed([_text(g.representative) for g in groups])))
    passage_vecs = np.asarray(list(encoder.embed(
        [f"passage: {c.title}. {' '.join((c.summary or '').split()[:TEXT_WORDS])}" for c in pool], batch_size=32,
    )))
    query_vec = np.asarray(next(iter(encoder.embed([f"query: {query}"]))))
    by_query = passage_vecs @ query_vec
    topic = [
        (pool[i].feed_item_ids[0], "assessment_topic")
        for i in np.argsort(-by_query)[:MAX_ASSESSMENTS] if by_query[i] >= RELEVANCE_THRESHOLD
    ]

    sims = pool_vecs @ rep_vecs.T
    result = []
    for gi in range(len(groups)):
        order = np.argsort(-sims[:, gi])
        own = [
            (pool[i].feed_item_ids[0], "assessment")
            for i in order[:MAX_ASSESSMENTS] if sims[i, gi] >= signal_threshold
        ]
        result.append(own or topic)
    log.info("оценки аналитиков: пул %d отчётов, по теме запроса %d, сигналов со своими отчётами %d",
             len(pool), len(topic), sum(1 for r in result if r and r[0][1] == "assessment"))
    return result


def corroborate(
    session: Session, encoder, groups: list[DisplayGroup], pool: list[SignalCandidate],
    primary_urls: list[str], *, reports: list[SignalCandidate] = (), queries: list[str] = (),
) -> list[Corroboration]:
    if not groups:
        return []
    taken = {publication_key(m.title) for g in groups for m in g.members}
    result = [Corroboration() for _ in groups]

    topic_median = None
    if encoder is not None:
        try:
            similar_by_group, topic_median = _similar_works(session, encoder, groups, pool, taken)
            for gi, similar in enumerate(similar_by_group):
                result[gi].sources.extend(similar)
        except Exception as exc:
            log.error("подтверждения (близкие работы) упали: %s", exc)
        try:
            analyst_pool = _analyst_pool(session, list(reports), list(queries))
            assessments = _analyst_assessments(
                encoder, groups, analyst_pool, queries[0] if queries else "",
                topic_median or SIMILAR_MIN, taken,
            )
            for gi, items in enumerate(assessments):
                result[gi].sources.extend(items)
        except Exception as exc:
            log.error("оценки аналитиков упали: %s", exc)

    try:
        with _client() as client, ThreadPoolExecutor(max_workers=3) as executor:
            links = list(executor.map(lambda a: _openalex_links(client, *a), zip(groups, primary_urls)))
    except Exception as exc:
        log.error("подтверждения (OpenAlex) упали: %s", exc)
        links = [([], False) for _ in groups]

    if encoder is not None and topic_median is not None:
        links = _filter_links_by_meaning(encoder, groups, links, topic_median)

    for gi, (items, growth) in enumerate(links):
        result[gi].citation_growth = growth
        fresh = [(i, rel) for i, rel in items if publication_key(i.title) not in taken]
        if not fresh:
            continue
        stored = persist_live_items(session, [i for i, _ in fresh])
        by_key = {publication_key(fi.title): fi.id for fi in stored}
        seen = {fid for fid, _ in result[gi].sources}
        for item, relation in fresh:
            fid = by_key.get(publication_key(item.title))
            if fid is not None and fid not in seen:
                seen.add(fid)
                result[gi].sources.append((fid, relation))
    return result
