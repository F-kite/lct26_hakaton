"""Конфигурация из окружения — тот же принцип, что в collector/db.py:
переменные, а не хардкод, с разумным дефолтом для локального docker-compose.
"""

import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://signals:signals@localhost:5432/signals",
)

# сколько кандидатов максимум разбирает пайплайн за один поиск
SEARCH_CANDIDATE_LIMIT = int(os.getenv("SEARCH_CANDIDATE_LIMIT", "500"))
# сколько сигналов отдаём в ответе (ТЗ: ТОП-15)
SEARCH_TOP_N = int(os.getenv("SEARCH_TOP_N", "15"))
# порог уверенности, ниже которого кандидат не считается сигналом
SIGNAL_SCORE_THRESHOLD = float(os.getenv("SIGNAL_SCORE_THRESHOLD", "0.5"))
# сколько отклонённых кандидатов сохраняем для вкладки "Исключённые" —
# небольшой лимит: каждый отклонённый тоже проходит LLM-обогащение
# (см. orchestrator.py), а Ollama на CPU медленная, раздувать без нужды
# не стоит
SEARCH_EXCLUDED_LIMIT = int(os.getenv("SEARCH_EXCLUDED_LIMIT", "5"))

# --- CORS ---
FRONTEND_ORIGINS = [
    o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]

# --- live-поиск по внешним API во время запроса (pipeline/live_sources.py) ---

# Контактный email для polite pool arXiv/Crossref. НЕ хардкодить личный
# email — тот же принцип, что в RSS-collector/collector/academic.py.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "team@example.com")

# Ключ формально "рекомендован", не обязателен — без него безключевой пул
# Semantic Scholar может быть перегружен (см. RSS-collector, где это уже
# проверено вручную).
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

# USPTO ODP и EPO OPS — ключей не будет (решение по проекту), клиенты
# написаны, но не подключены к рабочему циклу (см. live_sources.py).
USPTO_ODP_API_KEY = os.getenv("USPTO_ODP_API_KEY")
EPO_OPS_KEY = os.getenv("EPO_OPS_KEY")
EPO_OPS_SECRET = os.getenv("EPO_OPS_SECRET")

# GitHub — без токена тоже работает (60 запросов/час на IP), токен просто
# поднимает лимит до 5000/час; получается самостоятельно и мгновенно
# (github.com/settings/tokens), без формы одобрения.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# PatentsView (search.patentsview.org) — НЕ ПРОВЕРЕНО ВЖИВУЮ. У API
# патентного офиса США была миграция на новый эндпоинт с обязательным
# бесплатным ключом (в отличие от старого api.patentsview.org) — на момент
# написания неизвестно, актуален ли ключ ещё нужен для этого конкретного
# запроса; ключ опционален в коде на случай, если для search всё же не
# требуется. Сверить с документацией при использовании:
# https://search.patentsview.org/docs/
PATENTSVIEW_API_KEY = os.getenv("PATENTSVIEW_API_KEY")

# --- обученная модель (Этап 1 ТЗ) ---

# sklearn.Pipeline (TF-IDF -> LogisticRegression), обучена аналитиком на
# 172 размеченных публикациях, 3 класса: слабый сигнал / зрелая технология /
# шум. Требует ИМЕННО scikit-learn==1.9.1 — на 1.7.2 predict_proba ломается
# (проверено вручную: AttributeError на LogisticRegression.multi_class),
# несовместимость форматов между минорными версиями sklearn.
MODEL_PATH = os.getenv("MODEL_PATH", "app/models/signal_classifier.pkl")

# --- LLM-обогащение сигналов (описание/преимущество/кейс-пример, ТЗ) ---

# Локальная модель вместо облачной (YandexGPT требовал ключ, которого нет,
# и внешнюю зависимость) — Qwen2.5, разрешена ТЗ как модель с Hugging Face,
# без согласования. Крутится отдельным сервисом Ollama в том же
# docker-compose (см. RSS-collector/docker-compose.yml), backend стучится
# по HTTP внутри docker-сети — тот же принцип, что был бы с YandexGPT,
# просто локальный адрес вместо облачного.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
