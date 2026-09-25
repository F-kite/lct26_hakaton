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

# --- live-поиск по внешним API во время запроса (pipeline/live_sources.py) ---

# Контактный email для polite pool arXiv/Crossref. НЕ хардкодить личный
# email — тот же принцип, что в RSS-collector/collector/academic.py.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "team@example.com")

# Ключ формально "рекомендован", не обязателен — без него безключевой пул
# Semantic Scholar может быть перегружен (см. RSS-collector, где это уже
# проверено вручную).
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

# USPTO ODP и EPO OPS — ключей пока нет, клиенты написаны заранее и
# аккуратно пропускают себя, если ключ не задан (см. live_sources.py).
USPTO_ODP_API_KEY = os.getenv("USPTO_ODP_API_KEY")
EPO_OPS_KEY = os.getenv("EPO_OPS_KEY")
EPO_OPS_SECRET = os.getenv("EPO_OPS_SECRET")

# --- обученная модель (Этап 1 ТЗ) ---

# sklearn.Pipeline (TF-IDF -> LogisticRegression), обучена аналитиком на
# 172 размеченных публикациях, 3 класса: слабый сигнал / зрелая технология /
# шум. Требует ИМЕННО scikit-learn==1.9.1 — на 1.7.2 predict_proba ломается
# (проверено вручную: AttributeError на LogisticRegression.multi_class),
# несовместимость форматов между минорными версиями sklearn.
MODEL_PATH = os.getenv("MODEL_PATH", "app/models/signal_classifier.pkl")

# --- LLM-обогащение сигналов (описание/преимущество/кейс-пример, ТЗ) ---

# YandexGPT из разрешённого ТЗ списка облачных моделей. Ключа пока нет у
# команды — enrichment.py аккуратно пропускает себя без ключа/folder_id,
# тот же принцип, что у USPTO ODP/EPO OPS в live_sources.py. Не проверено
# вживую — структура запроса по документации Yandex Cloud Foundation Models,
# сверить при получении ключа: https://yandex.cloud/ru/docs/foundation-models/
YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY")
YANDEX_GPT_FOLDER_ID = os.getenv("YANDEX_GPT_FOLDER_ID")
YANDEX_GPT_MODEL = os.getenv("YANDEX_GPT_MODEL", "yandexgpt-lite")
