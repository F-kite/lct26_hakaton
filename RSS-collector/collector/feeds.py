"""Реестр лент.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Feed:
    key: str                     # уникальный идентификатор ленты
    source_name: str             # человекочитаемое имя источника
    url: str | None              # URL ленты; None
    site_url: str                # корень сайта
    source_type: str             # tech_media | university | industry_report | ...
    trust_level: str             # high | medium | low
    language: str                # EN | RU
    topics: tuple[str, ...]      # темы покрытия
    is_indicator_only: bool = False   # требует кросс-подтверждения
    sponsored_possible: bool = False  # возможны рекламные материалы
    store_summary: bool = True        # можно ли хранить summary из ленты
    attribution_required: bool = False
    notes: str = ""
    rss_pollable: bool = True


FEEDS: list[Feed] = [
    Feed(
        key="techcrunch",
        source_name="TechCrunch",
        url="https://techcrunch.com/feed/",
        site_url="https://techcrunch.com",
        source_type="tech_media",
        trust_level="low",
        language="EN",
        topics=("Финтех", "Роботы", "ИИ-инфра"),
        is_indicator_only=True,
        store_summary=True,
        attribution_required=True,
        notes="Отдельные RSS Terms: атрибуция + ссылка на оригинал, "
              "контент не изменять, полный текст не копировать.",
    ),
    Feed(
        key="siliconangle",
        source_name="SiliconANGLE",
        url="https://siliconangle.com/feed/",
        site_url="https://siliconangle.com",
        source_type="tech_media",
        trust_level="low",
        language="EN",
        topics=("ИИ-инфра", "Защита ИИ", "Edge"),
        is_indicator_only=True,
        sponsored_possible=True,
        notes="Возможны sponsored-материалы и медиапартнёрство theCUBE.",
    ),
    Feed(
        key="mit_news",
        source_name="MIT News",
        url="https://news.mit.edu/rss/feed",
        site_url="https://news.mit.edu",
        source_type="university",
        trust_level="medium",
        language="EN",
        topics=("Все",),
        notes="Пресс-служба, не журнал. Есть тематические ленты — см. discover.",
    ),
    Feed(
        key="mckinsey",
        source_name="McKinsey",
        url="https://www.mckinsey.com/insights/rss",
        site_url="https://www.mckinsey.com",
        source_type="industry_report",
        trust_level="medium",
        language="EN",
        topics=("Финтех", "Инд.ИИ"),
        is_indicator_only=True,
        notes="Консалтинговая аналитика. Только RSS + метаданные, без скрапинга.",
    ),
    Feed(
        key="hse_science",
        source_name="НИУ ВШЭ",
        url="https://www.hse.ru/rss/rss_news_science.rss",
        site_url="https://www.hse.ru/news/science/",
        source_type="university",
        trust_level="medium",
        language="RU",
        topics=("Все",),
        notes="Раздел «Наука». Основная лента ВШЭ для технологических сигналов.",
    ),
    Feed(
        key="hse_expertise",
        source_name="НИУ ВШЭ",
        url="https://www.hse.ru/rss/rss_news_expertise.rss",
        site_url="https://www.hse.ru/news/expertise/",
        source_type="university",
        trust_level="medium",
        language="RU",
        topics=("Все",),
        notes="Раздел «Экспертиза» — комментарии учёных. Много не-технических тем, "
              "фильтровать на стороне скоринга.",
    ),
    # Поисковые API (academic.py), url справочный.
    Feed(
        key="arxiv",
        source_name="arXiv",
        url="http://export.arxiv.org/api/query",
        site_url="https://arxiv.org",
        source_type="preprint",
        trust_level="high",
        language="EN",
        topics=("Все",),
        is_indicator_only=False,
        rss_pollable=False,
        notes="Препринты без peer review. Atom API, без ключа, но строгий "
              "rate-limit (общий пул) — обязателен mailto в User-Agent и пауза "
              "между запросами. OAI-PMH для массовой синхронизации не реализован, "
              "используется только search API.",
    ),
    Feed(
        key="semantic_scholar",
        source_name="Semantic Scholar",
        url="https://api.semanticscholar.org/graph/v1/paper/search",
        site_url="https://www.semanticscholar.org/product/api",
        source_type="academic_aggregator",
        trust_level="high",
        language="EN",
        topics=("Все",),
        is_indicator_only=True,
        rss_pollable=False,
        notes="Не единственное подтверждение существования публикации — сверять "
              "DOI через Crossref. Ключ рекомендован: проверено вручную — "
              "безключевой пул сейчас стабильно отдаёт 429, для реальной "
              "эксплуатации нужен SEMANTIC_SCHOLAR_API_KEY.",
    ),
    Feed(
        key="fsisac",
        source_name="FS-ISAC",
        url="https://www.fsisac.com/newsroom/rss.xml",
        site_url="https://www.fsisac.com/newsroom",
        source_type="industry_association",
        trust_level="medium",
        language="EN",
        topics=("Защита ИИ", "Финтех"),
        is_indicator_only=True,
        notes="Проверено вручную — настоящий RSS 2.0, обычная лента. Публичная "
              "лента ≠ весь корпус, основная часть контента только для членов "
              "организации.",
    ),
    Feed(
        key="stanford_hai",
        source_name="Stanford HAI",
        url="https://hai.stanford.edu/sitemap.xml",
        site_url="https://hai.stanford.edu/news",
        source_type="university",
        trust_level="medium",
        language="EN",
        topics=("ИИ-инфра", "Защита ИИ"),
        rss_pollable=False,
        notes="Проверено вручную — RSS нет (листинг рендерится Next.js RSC "
              "на клиенте, HTML не парсится). Собирается через sitemap.xml "
              "(~1000 /news/ URL с lastmod) + og:title со страницы статьи. "
              "og:description/JSON-LD/дата в мете отсутствуют — summary нет, "
              "это ограничение источника, не баг парсера.",
    ),
    Feed(
        key="mipt",
        source_name="МФТИ",
        url="https://mipt.ru/api/v1/?action=news.getItemsShort&lang=ru",
        site_url="https://mipt.ru/news",
        source_type="university",
        trust_level="medium",
        language="RU",
        topics=("Все",),
        rss_pollable=False,
        notes="Проверено вручную — публичного RSS/API нет (Angular SPA), "
              "но найден незадокументированный внутренний JSON-эндпоинт "
              "(тот же, что использует сам сайт). Отдаёт все новости одним "
              "ответом, без пагинации; параметр tag игнорируется сервером — "
              "фильтрация по темам (science/ai/innovation/people/top-ii) "
              "не реализована, берём общий поток. Детального эндпоинта с "
              "текстом статьи не нашли — только title+дата+url, без summary.",
    ),
    Feed(
        key="a3_automate",
        source_name="A3 / Association for Advancing Automation",
        url="https://www.automate.org/a3/press-center",
        site_url="https://www.automate.org/a3/press-center",
        source_type="industry_association",
        trust_level="medium",
        language="EN",
        topics=("Роботы", "Инд.ИИ"),
        is_indicator_only=True,
        rss_pollable=False,
        notes="Проверено вручную — RSS/sitemap нет, обычный серверный HTML "
              "(не SPA). Позитивное смещение в пользу отрасли — не может быть "
              "единственным основанием. Тема источника зашита в CSS-классы "
              "карточки (tc-ai, tc-robotics, tc-vision, tc-motionControl) — "
              "сохраняем как raw_categories.",
    ),
]

BY_KEY = {f.key: f for f in FEEDS}
