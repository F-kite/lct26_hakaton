import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://signals:signals@localhost:5432/signals",
)

# сколько кандидатов максимум разбирает пайплайн за один поиск
SEARCH_CANDIDATE_LIMIT = int(os.getenv("SEARCH_CANDIDATE_LIMIT", "1000"))
# сколько сигналов отдаём в ответе (ТЗ: ТОП-15)
SEARCH_TOP_N = int(os.getenv("SEARCH_TOP_N", "15"))
# порог уверенности, ниже которого кандидат не считается сигналом
SIGNAL_SCORE_THRESHOLD = float(os.getenv("SIGNAL_SCORE_THRESHOLD", "0.5"))
# сколько отклонённых кандидатов сохраняем для вкладки "Исключённые"
SEARCH_EXCLUDED_LIMIT = int(os.getenv("SEARCH_EXCLUDED_LIMIT", "15"))

# --- CORS ---
FRONTEND_ORIGINS = [
    o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]

# --- live-поиск по внешним API во время запроса ---

# Контактный email для polite pool arXiv/Crossref.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "team@example.com")

SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# --- обученная модель ---
MODEL_PATH = os.getenv("MODEL_PATH", "app/models/signal_classifier.pkl")

# --- LLM-обогащение сигналов (описание/преимущество/кейс-пример, ТЗ) ---

# Локальная модель (Qwen2.5 Ollama)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# --- GigaChat: итоговый вывод по ТОП-15 поиска ---
# без ключа вывод отключён, остальной сервис работает как раньше
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY", "").strip()
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-3-Ultra")
# корневой сертификат НУЦ Минцифры — API GigaChat работает на нём
GIGACHAT_CA_FILE = os.getenv("GIGACHAT_CA_FILE", "../certs/russian_trusted_root_ca.pem")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "240"))
