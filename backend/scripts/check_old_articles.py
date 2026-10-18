"""Как обученный классификатор оценивает старые статьи о теперь «зрелых» темах.

Запуск (из корня проекта, в контейнере бэкенда, без правок образа):
    docker compose exec -T backend python - < backend/scripts/check_old_articles.py

Тексты берутся из arXiv API по id (заголовок и аннотация оригинала), плюс
аннотация whitepaper Bitcoin, которой нет на arXiv. Дата публикации в оценке
не участвует: классификатор смотрит только на заголовок и аннотацию.

Контрольная группа (CONTROLS) — короткие СИНТЕТИЧЕСКИЕ новостные тексты в духе
обучающей выборки: «шум» (финотчёт, назначение, суд) и «зрелая технология».
Они написаны для этого теста и не взяты из реальных публикаций.
"""

from __future__ import annotations

import sys
from xml.etree import ElementTree

import httpx

from app.pipeline.classifier import SignalCandidate, TrainedModelClassifier

MODEL_PATH = "app/models/signal_classifier.pkl"
ATOM = {"atom": "http://www.w3.org/2005/Atom"}

# (тема, arXiv id) — год публикации печатается из ответа arXiv
ARXIV_ARTICLES = [
    ("крипта", "1311.0243"),   # Majority is not enough: Bitcoin mining is vulnerable
    ("ИИ", "1207.0580"),       # Improving neural networks by preventing co-adaptation (dropout)
    ("ИИ", "1301.3781"),       # word2vec
    ("ИИ", "1312.5602"),       # Playing Atari with Deep Reinforcement Learning
    ("ИИ", "1406.2661"),       # Generative Adversarial Nets
]

BITCOIN_WHITEPAPER = (
    "крипта",
    "Bitcoin: A Peer-to-Peer Electronic Cash System",
    2008,
    "A purely peer-to-peer version of electronic cash would allow online payments "
    "to be sent directly from one party to another without going through a "
    "financial institution. Digital signatures provide part of the solution, but "
    "the main benefits are lost if a trusted third party is still required to "
    "prevent double-spending. We propose a solution to the double-spending problem "
    "using a peer-to-peer network. The network timestamps transactions by hashing "
    "them into an ongoing chain of hash-based proof-of-work, forming a record that "
    "cannot be changed without redoing the proof-of-work.",
)


# (группа, заголовок, текст) — синтетика, см. docstring
CONTROLS = [
    ("шум", "Acme Corp reports third-quarter earnings above analyst expectations",
     "Acme Corp reported quarterly revenue of 4.2 billion dollars, up 6 percent from a year earlier, "
     "and net income of 610 million dollars. The company raised its full-year earnings guidance and "
     "announced a dividend of 0.45 dollars per share payable to shareholders next month."),
    ("шум", "Globex names new chief financial officer",
     "Globex announced the appointment of a new chief financial officer, effective the first of next "
     "month. She succeeds the retiring executive, who will remain as an adviser to the board through "
     "the end of the year. The board thanked him for his service."),
    ("шум", "Court dismisses shareholder lawsuit against Initech",
     "A federal judge dismissed a shareholder lawsuit against Initech over statements made about its "
     "revenue forecast. The ruling said the plaintiffs failed to show intent to mislead investors. "
     "The plaintiffs may appeal the decision within thirty days."),
    ("зрелая технология", "Relational databases remain the backbone of enterprise software",
     "SQL relational database systems such as PostgreSQL and MySQL have been used in production for "
     "decades. They provide mature transaction support, indexing and replication, and are supported "
     "by every major cloud provider and a large ecosystem of tools."),
    ("зрелая технология", "Wi-Fi 6 routers become standard in home networking",
     "Wi-Fi routers based on a widely deployed wireless standard are now sold by every major "
     "consumer electronics vendor. The technology is well understood, interoperable across devices, "
     "and has been in mass production for years."),
    ("зрелая технология", "Cloud object storage is now a commodity service",
     "Object storage offered by large cloud providers is a mature, widely adopted service with "
     "stable pricing and standard APIs. Enterprises use it routinely for backups, archives and "
     "static website hosting."),
]


def fetch_arxiv(client: httpx.Client, arxiv_id: str) -> tuple[str, int, str] | None:
    resp = client.get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}", follow_redirects=True)
    if resp.status_code != 200:
        return None
    entry = ElementTree.fromstring(resp.content).find("atom:entry", ATOM)
    if entry is None:
        return None
    title = " ".join((entry.findtext("atom:title", "", ATOM)).split())
    summary = " ".join((entry.findtext("atom:summary", "", ATOM)).split())
    year = int(entry.findtext("atom:published", "0000", ATOM)[:4])
    return title, year, summary


def main() -> int:
    classifier = TrainedModelClassifier(MODEL_PATH)
    articles = [("[старая] " + BITCOIN_WHITEPAPER[0], *BITCOIN_WHITEPAPER[1:])]
    with httpx.Client(timeout=20) as client:
        for topic, arxiv_id in ARXIV_ARTICLES:
            got = fetch_arxiv(client, arxiv_id)
            if got is None:
                print(f"! не удалось получить arXiv {arxiv_id}", file=sys.stderr)
                continue
            title, year, summary = got
            articles.append(("[старая] " + topic, title, year, summary))
    articles += [("[контр.] " + group, title, 0, text) for group, title, text in CONTROLS]

    print(f"{'группа':26} {'год':4} {'класс':18} {'P(слаб.)':8}  заголовок / ключевые признаки")
    by_group: dict[str, list[float]] = {}
    for topic, title, year, summary in articles:
        candidate = SignalCandidate(
            feed_item_ids=[0], title=title, summary=summary,
            sources=["test"], trust_levels=["high"], published_at=None, language="EN",
        )
        result = classifier.score(candidate)
        expl = result.explanation
        probs = expl.get("class_probabilities", {})
        by_group.setdefault(topic, []).append(result.confidence)
        print(f"{topic:26} {year or '-':<4} {str(expl.get('predicted_class')):18} {result.confidence:<8}  {title[:70]}")
        print(f"{'':26} {'':4} вероятности: {probs}  признаки: {expl.get('key_predictors')}")

    print("\nсредняя P(слабый сигнал) по группам:")
    for group, values in by_group.items():
        print(f"  {group:26} {sum(values) / len(values):.3f}  (n={len(values)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
