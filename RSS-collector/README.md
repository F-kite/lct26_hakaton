# RSS-коллектор слабых сигналов

Фоновый слой сбора для сервиса слабых сигналов (кейс Газпромбанк Тех, ЛЦТ 2026).
Каждые 30 минут обходит RSS-ленты и HTML-источники и пишет записи в общую
PostgreSQL-базу (`feed_items`), из которой backend берёт кандидатов при поиске.
Live-поиск по внешним API во время запроса пользователя делает уже backend —
коллектор от него не зависит и копит историю заранее.

## Источники (26 лент, `collector/feeds.py`)

| Тип | Источники | Доверие |
|---|---|---|
| Научные публикации | arXiv, Semantic Scholar | высокое |
| Университеты и лаборатории | MIT News, Stanford HAI, Berkeley AI Research, НИУ ВШЭ («Наука», «Экспертиза»), МФТИ | среднее / высокое |
| Международные организации | BIS — Financial Stability Institute, BIS — речи центробанкиров | высокое |
| Отраслевые ассоциации и аналитика | McKinsey, FS-ISAC, A3 (Association for Advancing Automation) | среднее |
| Профессиональные медиа | IEEE Spectrum, The Record, Dark Reading, SecurityWeek | среднее / высокое |
| Компании-разработчики | OpenAI, NVIDIA Technical Blog, AWS Machine Learning Blog | среднее |
| Научные медиа (RU) | N + 1, Naked Science, Indicator.Ru | среднее |
| Технологические медиа | TechCrunch, SiliconANGLE | пониженное |
| Блог-платформа (RU) | Хабр | пониженное, только индикатор |

Уровни доверия выставлены по критериям ТЗ: научные публикации, университеты,
регуляторы и профессиональные медиа — доверенные; агрегаторы, блоги и
пресс-релизы — пониженная доверенность (`is_indicator_only`), такие сведения
должны подтверждаться независимыми источниками.

Stanford HAI, МФТИ и A3 не отдают RSS — для них HTML-парсеры
(`html_sources.py`). arXiv и Semantic Scholar в фоне не опрашиваются: по
запросу пользователя их ищет live-поиск backend, а в коллекторе они доступны
разовыми командами `arxiv` / `semantic-scholar` (`academic.py`).

## Запуск

Коллектор поднимается вместе со всем стеком из корня репозитория:

```bash
docker compose up -d collector       # init + сбор каждые 30 минут
docker compose logs -f collector
docker compose exec collector python -m collector.main stats   # что накопилось
```

Локально, без Docker:

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://signals:signals@localhost:5432/signals"

python -m collector.main init                    # создать таблицы
python -m collector.main collect [ключи…]        # однократный сбор (все или выбранные ленты)
python -m collector.main loop --interval 1800    # непрерывный сбор
python -m collector.main stats                   # записи, глубина истории, сбои по лентам
python -m collector.main discover [ключи…]       # найти URL ленты, если сайт её сменил
```

Разовые команды:

```bash
python -m collector.main archive <ключ> --from 2026-01-01 [--to …] [--save]  # архивная догрузка
python -m collector.main arxiv "cat:cs.AI AND abs:agentic" --save             # поиск в arXiv
python -m collector.main semantic-scholar "neuromorphic chips" --save          # поиск в Semantic Scholar
python -m collector.main verify-doi 10.1038/nature12373                        # проверка DOI через Crossref
```

## Отказоустойчивость

Отдельный критерий оценки (п. 8.2 ТЗ):

| Механизм | Где |
|---|---|
| Изоляция лент — падение одной не роняет прогон | `core.collect_all` |
| Ретраи с экспоненциальной задержкой на 429/5xx, учёт `Retry-After` | `core._fetch` |
| Условный GET по `ETag` / `Last-Modified` | `core.collect_one` |
| Дедупликация по `UNIQUE(url_hash)` на уровне БД, не в памяти | `db.FeedItem` |
| Счётчик `consecutive_failures` и `last_error` на источнике | `db.Source` |
| Явные DNS-серверы контейнера (1.1.1.1, 8.8.8.8) | `docker-compose.yml` |

## Соблюдение условий источников

У TechCrunch отдельные RSS Terms: атрибуция, ссылка на оригинал, контент не
изменять, полный текст не копировать. Поэтому коллектор сохраняет только то,
что отдаёт лента — заголовок, summary, ссылку, дату, автора; полные статьи не
выкачиваются. Флаг `store_summary=False` в `feeds.py` отключает сохранение
текста для источника, если его условия окажутся жёстче.

## Поля под требования ТЗ

ТЗ требует показывать для каждого источника наименование, ссылку, дату
публикации, тип источника, язык оригинала и уровень доверенности. Всё это
пишется в `feed_items` сразу при сборе, денормализованно — чтобы выдача
строилась одним запросом без джойнов.

## Структура

```
collector/
  feeds.py         реестр лент + метаданные доверия, типа и языка
  db.py            SQLAlchemy-модели Source и FeedItem
  core.py          сбор RSS, ретраи, дедупликация
  html_sources.py  HTML-парсеры для источников без RSS
  academic.py      arXiv, Semantic Scholar, проверка DOI через Crossref
  archive.py       разовая архивная догрузка за период
  discover.py      автодискавери лент (link rel=alternate + типовые пути)
  main.py          CLI
```

## Добавить источник

Новая RSS-лента — одна запись `Feed(...)` в `collector/feeds.py` (ключ, название,
URL, тип, уровень доверия, язык). Источник без RSS — запись с
`rss_pollable=False` и функция-парсер в `html_sources.py`.
