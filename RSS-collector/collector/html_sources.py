"""HTML/API-источники без нормального RSS: Stanford HAI, МФТИ, A3/Automate.

В отличие от archive.py (одноразовая историческая догрузка по диапазону дат)
и academic.py (поисковые API по явному запросу), эти три источника — как раз
"текущий список последних материалов", концептуально то же самое, что и RSS:
опрашиваются периодически, каждый раз отдают последние N записей, дедуп по
url_hash решает остальное. Поэтому они ДОЛЖНЫ быть частью обычного цикла
сбора (см. main.py: cmd_collect/cmd_loop зовут collect_html_sources()
следом за collect_all()) — в отличие от archive.py/academic.py.

Разметка проверена вручную (curl) на реальных страницах:

Stanford HAI (fetch_stanford_hai)
    Next.js RSC — листинг /news рендерится клиентским JS, парсить его HTML
    нереально (сериализованное дерево React, не обычная разметка). Обходной
    путь: sitemap.xml содержит ~1000 URL вида /news/{slug} с <lastmod>.
    На самой странице статьи нет ни og:description, ни JSON-LD, ни даты —
    только og:title (с суффиксом " | Stanford HAI", отрезается). Итог:
    title + published_at (из lastmod) + url, БЕЗ summary — это не баг,
    у источника действительно нет доступных метаданных богаче этого.

МФТИ (fetch_mipt)
    Angular SPA (<app-root>), HTML пустой. Но есть внутренний JSON API,
    найденный по preload-хинтам в шаблоне: /api/v1/?action=news.getItemsShort
    — отдаёт ВСЕ ~3400 новостей одним ответом, без пагинации и без
    подтверждённого серверного фильтра по тегу (параметр tag игнорируется,
    проверено). Детальный эндпоинт с текстом статьи не найден (перебор
    очевидных имён action ни к чему не привёл, страницы статей — тоже
    пустой SPA-шелл без OG-меты) — тоже title + published_at + url, без
    summary. Фильтрация по теме (science/ai/innovation/people/top-ii из
    исходной таблицы источников) не реализована: сырые tag id в ответе
    без расшифровки в человекочитаемые имена, а отдельного tags-эндпоинта
    не нашлось — берём общий поток, как и remaining topics=("Все",).

A3 / Automate (fetch_a3)
    Обычный серверный HTML (не SPA) — https://www.automate.org/a3/press-center
    отдаёт ~96 карточек прямо в разметке. Тема — в CSS-классах контейнера
    (tc-ai, tc-robotics, tc-vision, tc-motionControl), дата — текстом
    "MM/DD/YYYY | Источник". Пагинации/архива глубже этой страницы не
    нашлось — это просто "текущий срез", как одна RSS-лента.

Все три источника кладут ArchiveItem (та же денормализация, что в archive.py
и academic.py) через archive.persist_items(). lookback_days отсекает старое
до попытки вставки — иначе на каждый 30-минутный прогон loop пришлось бы
перебирать/дёргать сотни-тысячи уже известных URL просто чтобы схлопнуться
в 0 новых через дедуп в БД.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

import httpx
from selectolax.parser import HTMLParser

from .archive import ArchiveItem, _client, _get, _parse_sitemap, persist_items

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 14


# --------------------------------------------------------------------------
# Stanford HAI — sitemap + минимальный og:title (без summary/даты в мете)
# --------------------------------------------------------------------------

STANFORD_HAI_SITEMAP = "https://hai.stanford.edu/sitemap.xml"
STANFORD_HAI_TITLE_SUFFIX = re.compile(r"\s*\|\s*Stanford HAI\s*$")


def fetch_stanford_hai(
    client: httpx.Client, *, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[ArchiveItem]:
    resp = _get(client, STANFORD_HAI_SITEMAP)
    if resp is None or resp.status_code != 200:
        log.error("stanford_hai: sitemap недоступен")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    candidates: list[tuple[str, datetime]] = []
    for loc, lastmod in _parse_sitemap(resp.content):
        if "/news/" not in loc or not lastmod:
            continue
        try:
            dt = datetime.fromisoformat(lastmod).astimezone(timezone.utc)
        except ValueError:
            continue
        if dt >= cutoff:
            candidates.append((loc, dt))

    items: list[ArchiveItem] = []
    for url, published_at in candidates:
        art = _get(client, url)
        if art is None or art.status_code != 200:
            continue
        tree = HTMLParser(art.text)
        node = tree.css_first('meta[property="og:title"]')
        title = node.attributes.get("content") if node else None
        if not title:
            continue
        title = STANFORD_HAI_TITLE_SUFFIX.sub("", title).strip()
        items.append(ArchiveItem(
            source_key="stanford_hai",
            url=url,
            title=title,
            published_at=published_at,
        ))
    return items


# --------------------------------------------------------------------------
# МФТИ — внутренний JSON API (не RSS, не задокументирован публично)
# --------------------------------------------------------------------------

MIPT_API = "https://mipt.ru/api/v1/"


def fetch_mipt(
    client: httpx.Client, *, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[ArchiveItem]:
    resp = _get(client, f"{MIPT_API}?action=news.getItemsShort&lang=ru")
    if resp is None or resp.status_code != 200:
        log.error("mipt: API недоступен")
        return []

    try:
        data = resp.json()
    except ValueError:
        log.error("mipt: не удалось разобрать JSON-ответ")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    items: list[ArchiveItem] = []
    for entry in data:
        code = entry.get("code")
        name = entry.get("name")
        active = entry.get("activeDate") or [None]
        ts = active[0]
        if not code or not name or not ts:
            continue
        published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
        if published_at < cutoff:
            continue
        items.append(ArchiveItem(
            source_key="mipt",
            url=f"https://mipt.ru/news/{code}",
            title=re.sub(r"&nbsp;", " ", name).strip(),
            published_at=published_at,
        ))
    return items


# --------------------------------------------------------------------------
# A3 / Automate — обычный серверный HTML, одна страница "текущий срез"
# --------------------------------------------------------------------------

A3_PRESS_CENTER = "https://www.automate.org/a3/press-center"
_A3_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def fetch_a3(
    client: httpx.Client, *, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[ArchiveItem]:
    resp = _get(client, A3_PRESS_CENTER)
    if resp is None or resp.status_code != 200:
        log.error("a3: страница недоступна")
        return []

    cutoff = date.today() - timedelta(days=lookback_days)
    tree = HTMLParser(resp.text)
    items: list[ArchiveItem] = []
    for card in tree.css("div.item.informational"):
        link = card.css_first("h3 a")
        if link is None:
            continue
        href = link.attributes.get("href")
        title = link.text(strip=True)
        if not href or not title:
            continue

        meta_node = card.css_first("p.memberCompanyName")
        meta_text = meta_node.text(strip=True) if meta_node else ""
        m = _A3_DATE_RE.search(meta_text)
        if not m:
            continue
        published_date = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if published_date < cutoff:
            continue
        published_at = datetime(
            published_date.year, published_date.month, published_date.day, tzinfo=timezone.utc,
        )

        classes = card.attributes.get("class", "") or ""
        topics = [c.removeprefix("tc-") for c in classes.split() if c.startswith("tc-")]

        items.append(ArchiveItem(
            source_key="a3_automate",
            url=href,
            title=title,
            published_at=published_at,
            raw_categories=", ".join(topics) if topics else None,
        ))
    return items


# --------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------

FETCHERS = {
    "stanford_hai": fetch_stanford_hai,
    "mipt": fetch_mipt,
    "a3_automate": fetch_a3,
}


def collect_html_sources(keys: list[str] | None = None) -> dict[str, int]:
    """Опросить все (или выбранные) HTML/API-источники и сохранить найденное.

    Вызывается из cmd_collect/cmd_loop наравне с RSS-сбором — эти источники
    концептуально такие же "текущие ленты", просто без формата RSS.
    """
    fetchers = {k: v for k, v in FETCHERS.items() if not keys or k in keys}
    saved: dict[str, int] = {}
    with _client() as client:
        for key, fetch_fn in fetchers.items():
            try:
                found = fetch_fn(client)
            except Exception as exc:
                log.error("[%s] сбой сбора: %s", key, exc)
                saved[key] = 0
                continue
            n = persist_items(found) if found else 0
            saved[key] = n
            log.info("[%s] ok, +%d (из %d кандидатов)", key, n, len(found))
    return saved


def main() -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(prog="python -m collector.html_sources")
    p.add_argument("keys", nargs="*", help=f"по умолчанию — все: {', '.join(FETCHERS)}")
    args = p.parse_args()

    unknown = [k for k in args.keys if k not in FETCHERS]
    if unknown:
        p.error(f"неизвестные ключи: {', '.join(unknown)} (доступны: {', '.join(FETCHERS)})")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
    saved = collect_html_sources(args.keys or None)
    total = sum(saved.values())
    print(f"\nНовых записей: {total}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
