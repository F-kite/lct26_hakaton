"""CLI коллектора.

    python -m collector.main init                 # создать таблицы
    python -m collector.main discover hse         # найти URL ленты
    python -m collector.main collect              # собрать все ленты
    python -m collector.main collect techcrunch   # собрать выбранные
    python -m collector.main loop --interval 1800 # непрерывный сбор
    python -m collector.main stats                # что накопилось
    python -m collector.main archive hse_science --from 2025-01-01 --save
                                                    # архивная догрузка за период
                                                    # (разовая, НЕ часть loop)
    python -m collector.main arxiv "cat:cs.AI AND abs:agentic" --save
    python -m collector.main semantic-scholar "agentic AI safety" --save
    python -m collector.main verify-doi 10.1038/s41586-021-03819-2
                                                    # поисковые API — тоже НЕ часть loop,
                                                    # search_query задаётся явно при каждом вызове
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date

from sqlalchemy import func, select

from .academic import run_arxiv, run_semantic_scholar, run_verify_doi
from .archive import DAY_ARCHIVE_SOURCES, SITEMAP_SOURCES, fetch_archive
from .core import collect_all
from .db import FeedItem, SessionLocal, Source, init_db
from .discover import discover
from .feeds import BY_KEY, FEEDS
from .html_sources import FETCHERS as HTML_FETCHERS, collect_html_sources


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_init(_args) -> int:
    init_db()
    print("Таблицы созданы.")
    return 0


def cmd_discover(args) -> int:
    keys = args.keys or [f.key for f in FEEDS if f.rss_pollable]
    for key in keys:
        feed = BY_KEY.get(key)
        if not feed:
            print(f"[{key}] неизвестный ключ")
            continue
        print(f"\n[{key}] {feed.site_url}")
        urls = discover(feed.site_url)
        if not urls:
            print("  лент не найдено — источник уходит в HTML-парсер")
            continue
        for u in urls:
            print(f"  {u}")
        print(f"  -> пропишите url='{urls[0]}' в collector/feeds.py")
    return 0


def _split_collect_keys(keys: list[str] | None) -> tuple[list[str], list[str]]:
    """Явные keys могут смешивать RSS- и HTML/API-источники в одном вызове
    (collect stanford_hai techcrunch) — разводим по нужному механизму сбора.
    Без явных keys — все RSS-ленты (rss_pollable) + все HTML/API-источники;
    поисковые API (arxiv/semantic_scholar) вслепую не опрашиваются, для них
    нужен конкретный search_query — только через collector.academic.
    """
    rss_keys = [k for k in (keys or [f.key for f in FEEDS if f.rss_pollable]) if k not in HTML_FETCHERS]
    html_keys = [k for k in (keys or list(HTML_FETCHERS)) if k in HTML_FETCHERS]
    return rss_keys, html_keys


def cmd_collect(args) -> int:
    rss_keys, html_keys = _split_collect_keys(args.keys or None)

    results = collect_all(rss_keys) if rss_keys else []
    html_saved = collect_html_sources(html_keys) if html_keys else {}

    total = sum(r.new_items for r in results) + sum(html_saved.values())
    failed = [r.key for r in results if not r.ok]
    print(f"\nНовых записей: {total}")
    if failed:
        print(f"Не удалось собрать: {', '.join(failed)}")
    # ненулевой код только если упало вообще всё (и RSS, и HTML)
    return 1 if failed and len(failed) == len(results) and not html_saved else 0


def cmd_loop(args) -> int:
    log = logging.getLogger("loop")
    rss_keys, html_keys = _split_collect_keys(args.keys or None)
    while True:
        try:
            if rss_keys:
                collect_all(rss_keys)
            if html_keys:
                collect_html_sources(html_keys)
        except Exception as exc:
            log.error("прогон упал целиком: %s", exc)
        log.info("следующий прогон через %d с", args.interval)
        time.sleep(args.interval)


def cmd_stats(_args) -> int:
    session = SessionLocal()
    try:
        rows = session.execute(
            select(
                Source.key,
                Source.name,
                Source.trust_level,
                func.count(FeedItem.id),
                func.min(FeedItem.published_at),
                func.max(FeedItem.published_at),
                Source.consecutive_failures,
            )
            .outerjoin(FeedItem, FeedItem.source_id == Source.id)
            .group_by(Source.id)
            .order_by(Source.key)
        ).all()

        if not rows:
            print("Пусто. Запустите `collect`.")
            return 0

        key_width = max(17, max(len(key) for key, *_ in rows) + 1)
        print(f"{'ключ':<{key_width}}{'доверие':<9}{'записей':>8}  {'глубина истории':<34}{'сбоев'}")
        print("-" * (key_width + 64))
        for key, _name, trust, cnt, dmin, dmax, fails in rows:
            span = "—"
            if dmin and dmax:
                span = f"{dmin:%Y-%m-%d} .. {dmax:%Y-%m-%d}"
            print(f"{key:<{key_width}}{trust:<9}{cnt:>8}  {span:<34}{fails or 0}")

        total = session.scalar(select(func.count(FeedItem.id)))
        print(f"\nВсего записей: {total}")
        return 0
    finally:
        session.close()


def cmd_archive(args) -> int:
    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to) if args.date_to else date.today()
    # без title запись в БД бессмысленна — для sitemap-источников enrich обязателен при --save
    enrich = args.enrich or (args.save and args.key in SITEMAP_SOURCES)

    # save=True -> персистентность пачками по ходу сбора (см. archive.fetch_archive):
    # один сетевой сбой на середине многочасового прогона больше не теряет всё найденное
    items = fetch_archive(args.key, date_from, date_to, enrich=enrich, save=args.save)
    print(f"[{args.key}] получено за {date_from}..{date_to}: {len(items)}")
    return 0


def cmd_arxiv(args) -> int:
    items = run_arxiv(args.query, max_results=args.max_results, save=args.save)
    print(f"[arxiv] найдено: {len(items)}")
    return 0


def cmd_semantic_scholar(args) -> int:
    items = run_semantic_scholar(args.query, limit=args.limit, save=args.save)
    print(f"[semantic_scholar] найдено: {len(items)}")
    return 0


def cmd_verify_doi(args) -> int:
    work = run_verify_doi(args.doi)
    if work is None:
        print(f"DOI не найден или Crossref недоступен: {args.doi}")
        return 1
    print(f"title: {work.title}\ntype: {work.type}\npublished: {work.published}\n"
          f"cited by: {work.is_referenced_by_count}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="collector", description="RSS-коллектор слабых сигналов")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="создать таблицы").set_defaults(fn=cmd_init)

    d = sub.add_parser("discover", help="найти URL лент")
    d.add_argument("keys", nargs="*")
    d.set_defaults(fn=cmd_discover)

    c = sub.add_parser("collect", help="однократный сбор")
    c.add_argument("keys", nargs="*")
    c.set_defaults(fn=cmd_collect)

    l = sub.add_parser("loop", help="непрерывный сбор")
    l.add_argument("keys", nargs="*")
    l.add_argument("--interval", type=int, default=1800, help="секунд между прогонами")
    l.set_defaults(fn=cmd_loop)

    sub.add_parser("stats", help="статистика накопленного").set_defaults(fn=cmd_stats)

    ar = sub.add_parser("archive", help="архивная догрузка за период (разовая, не часть loop)")
    ar.add_argument("key", choices=sorted(set(DAY_ARCHIVE_SOURCES) | set(SITEMAP_SOURCES)))
    ar.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    ar.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD, по умолчанию — сегодня")
    ar.add_argument("--enrich", action="store_true",
                     help="для sitemap-источников: добрать title/summary со страницы статьи")
    ar.add_argument("--save", action="store_true", help="записать найденное в БД")
    ar.set_defaults(fn=cmd_archive)

    ax = sub.add_parser("arxiv", help="поиск в arXiv (search API, без ключа)")
    ax.add_argument("query", help="arXiv search_query, напр. 'cat:cs.AI AND abs:agentic'")
    ax.add_argument("--max-results", type=int, default=100)
    ax.add_argument("--save", action="store_true")
    ax.set_defaults(fn=cmd_arxiv)

    ss = sub.add_parser("semantic-scholar", help="поиск в Semantic Scholar (ключ рекомендован)")
    ss.add_argument("query")
    ss.add_argument("--limit", type=int, default=50)
    ss.add_argument("--save", action="store_true")
    ss.set_defaults(fn=cmd_semantic_scholar)

    vd = sub.add_parser("verify-doi", help="проверить DOI и получить метаданные через Crossref")
    vd.add_argument("doi")
    vd.set_defaults(fn=cmd_verify_doi)

    args = p.parse_args()
    setup_logging(args.verbose)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
