Бэкенд-сервис: API + пайплайн + задел под ML-модель
Контекст
RSS-collector (готов) закрывает п.5.1 моей зоны ответственности («сырые данные источников») — 11 источников, ~7400 записей в feed_items/sources в Postgres signals. Не хватает остального из раздела 5 контекста: API-слоя, оркестрации пайплайна и места, куда аналитик воткнёт свою NLP/скоринг-модель. Это и есть предмет этого плана — «бэкенд для сервиса» целиком, вторая половина моей роли после сбора данных.

Разделение труда (уже зафиксировано в CONTEXT_LCT2026.md §5): я строю фундамент — оркестрацию, контракт вход/выход для модели, персистентность, API. Сама модель (веса, критерии скоринга, что считать зрелым трендом) — не моя часть; здесь я даю чёткий интерфейс, за которым аналитик её включит.

Попутно нашёл в getDataset/ параллельный проект аналитика — bulk-загрузка arXiv-датасета с Kaggle (3-4 млн статей → parquet) для офлайн-анализа трендов. Это его пайплайн подготовки данных для обучения, к бэкенду напрямую не подключается — но подтверждает, что модель обучается отдельно от сервиса, а сервис только вызывает готовую модель на инференсе.

Формат датасета 100_слабых_технологических_сигналов...xlsx (проверил вручную через zipfile+ElementTree) даёт точную форму того, что должен возвращать /search и /insight/{id}: № | Технология | Область | Компании | Почему это слабый сигнал | Стадия развития | Тренд упоминаний | Балл (стадия+тренд) | Источники (markdown-ссылки). Именно эту форму использую как основу для схемы signals.

Архитектура
Новая директория backend/ (соседняя с RSS-collector/), собственный Dockerfile, подключается как ещё один сервис в существующий RSS-collector/docker-compose.yml (не отдельный compose-стек — незачем поднимать вторую сеть/БД ради одного Postgres). Использует ту же БД signals через db (уже поднят, уже содержит feed_items/sources). Ставка на «чёткое разделение парсинг/инференс/интерфейс» (ТЗ, раздел 3) реализуется как разделение по сервисам в одном compose, а не по трём разным compose-стекам — collector остаётся собственно парсингом, backend — интерфейсом+оркестрацией, инференс — pluggable-интерфейс внутри backend (заглушка сейчас, реальная модель аналитика — потом, без смены контракта).

Backend читает feed_items/sources напрямую (та же БД), но определяет свои SQLAlchemy-модели для них независимо от collector/db.py — два отдельных Docker-образа, кросс-импорт Python-модулей между ними не делаю (стандартный подход для независимо разворачиваемых сервисов).

backend/
  Dockerfile
  requirements.txt
  app/
    __init__.py
    config.py          # DATABASE_URL и т.п. из окружения — как в collector/db.py
    db.py               # engine/SessionLocal + ORM: FeedItem/Source (read-only
                         # зеркало схемы collector) + Signal/SignalSource/SearchQuery (новые)
    init_db.py           # create_all() для новых таблиц — как collector.main init
    schemas.py           # Pydantic-модели запросов/ответов API
    main.py               # FastAPI app, регистрация роутеров, /health
    routers/
      search.py            # POST /search, GET /search/{id}/status
      insight.py            # GET /insight/{id}
    pipeline/
      __init__.py
      candidates.py          # шаг 1: кандидаты — поиск по feed_items (ILIKE по
                              # заголовку/summary + свежесть), с точкой расширения
                              # под live fetch (arXiv/Semantic Scholar) позже
      classifier.py           # ЗАДЕЛ ПОД ML: Protocol SignalClassifier + рабочая
                               # эвристика-заглушка (явно помечена, не настоящая модель)
      orchestrator.py           # run_search(): кандидаты -> classifier.score() каждому
                                 # -> фильтр по порогу -> топ-15 -> запись в signals
Схема БД — новые таблицы (та же Postgres signals)
search_queries (
  id, query_text, status,           -- pending|running|done|failed
  sources_processed, candidates_found, signals_above_75,  -- бонусные счётчики ТЗ
  error, created_at, finished_at
)

signals (
  id, query_id NULL REFERENCES search_queries,  -- NULL = накопленный сигнал вне
                                                  -- конкретного запроса пользователя
  title, area, description, case_example, stage,
  mention_trend, score, is_mainstream,
  explanation JSONB,     -- интерпретируемость: признаки/обоснование (ТЗ §2, §8.3)
  model_version,         -- какая модель/эвристика дала оценку — ТЗ требует логировать
  created_at
)

signal_sources (
  signal_id REFERENCES signals,
  feed_item_id REFERENCES feed_items,   -- кросс-источниковое подтверждение,
  PRIMARY KEY (signal_id, feed_item_id)  -- один сигнал может ссылаться на N записей
)
API
POST /search {query: str} — создаёт search_queries строку, запускает пайплайн в BackgroundTasks (без новой инфраструктуры — Redis/Celery не нужны на этом этапе, ТЗ явно допускает «на промежуточном этапе достаточно ... API-ответа»), возвращает {query_id} сразу
GET /search/{query_id}/status — статус + счётчики (стриминг прогресса через поллинг, не WebSocket — тот же принцип «просто и без лишней инфраструктуры»); когда status=done — тут же отдаёт топ-15 сигналов
GET /insight/{signal_id} — полная карточка сигнала + связанные источники (join через signal_sources → feed_items → sources, с trust_level каждого — ТЗ требует показывать доверие источника в выдаче)
GET /health — для docker-compose healthcheck
Задел под ML-модель (ядро задачи)
class SignalCandidate:  # вход в модель
    feed_item_ids: list[int]
    title: str
    summary: str | None
    sources: list[str]       # source_key каждого подтверждающего item
    trust_levels: list[str]
    published_at: datetime

class ScoringResult:     # выход из модели
    is_weak_signal: bool
    confidence: float        # 0..1
    stage: str | None
    explanation: dict        # признаки/обоснование — обязательная интерпретируемость

class SignalClassifier(Protocol):
    def score(self, candidate: SignalCandidate) -> ScoringResult: ...
Сейчас — HeuristicStubClassifier: простая эвристика на основе trust_level/числа подтверждающих источников/свежести, не настоящая классификация, явно так помеченная в docstring. Даёт пайплайну реально работать и отдавать правдоподобные ответы уже сегодня. Аналитик подключает реальную модель, реализовав тот же Protocol — оркестратор не меняется.

Осознанно упрощено на этом проходе (проговорить с тобой)
Кандидаты берутся из уже накопленной БД (feed_items), не через живой fan-out по внешним API в момент запроса — хотя ТЗ говорит «в реальном времени, не ограничиваясь датасетом». Наш feed_items — не закрытый датасет, а собственный растущий корпус (7400+ записей, 11 источников, обновляется каждые 30 мин), так что это ближе к духу требования, чем кажется — но живой fan-out по arXiv/Semantic Scholar с пользовательским запросом (уже есть в academic.py) — это следующий шаг, не в этом проходе.
BackgroundTasks вместо очереди (Celery/RQ+Redis). Проще, без новых контейнеров, достаточно для промежуточного этапа. Если нагрузка/объём вырастет — заменить на реальную очередь, не меняя API-контракт.
classifier.py — эвristика, не модель. Основная работа аналитика ещё впереди; моя часть — контракт и работающая заглушка за ним.
Проверка
docker compose up -d --build — поднимаются db + collector + adminer + backend вместе
docker compose exec backend python -m app.init_db (или в CMD автоматически) — создаёт новые таблицы, \dt в adminer покажет signals/signal_sources/search_queries рядом с уже существующими feed_items/sources
curl -X POST localhost:8000/search -d '{"query": "агентный ИИ"}' → получить query_id, опросить /search/{id}/status до done, убедиться что в ответе реальные записи из уже собранного корпуса (например, что-то из недавно добавленных arXiv/techcrunch записей)
curl localhost:8000/insight/{signal_id} — проверить, что источники и trust_level в ответе корректны
python -m py_compile по всем новым файлам перед докер-сборкой (как делал для RSS-collector) — ловить синтаксические ошибки до билда