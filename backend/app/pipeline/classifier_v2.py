"""Модель v2 (комплект аналитика, app/models/v2): E5 сравнивает смысл
запроса и статьи, обученный классификатор определяет стадию технологии,
условия запроса («для банков», «чипы»…) проверяются по тексту.

Код аналитика (signals.py, relevance.py) не меняем — используем его функции.
Логика SignalAnalyzer.analyze() повторена здесь, чтобы порог релевантности
брался из настроек, а оценка шла одним батчем по всем кандидатам.
"""

from __future__ import annotations

import logging
import math
import pickle
import re

from ..config import E5_MODEL_DIR, MODEL_V2_PATH, RELEVANCE_THRESHOLD
from .classifier import ScoringResult, SignalCandidate

log = logging.getLogger(__name__)

MIN_WORDS = 60  # правило аналитика: короче — «Недостаточно текста»
E5_MODEL_NAME = "local/multilingual-e5-small-int8"

_TAG_RE = re.compile(r"<[^>]+>")

# короткие теги причины исключения для таблицы «Исключённые»
REASON_TAGS = {
    "short": "Мало текста",
    "conditions": "Не подтверждены условия",
    "review": "Требует проверки",
    "relevance": "Низкая релевантность",
    "stage": None,  # подставляется класс модели
    "uncertain": "Неуверенная стадия",
}


def _load_encoder():
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    if E5_MODEL_NAME not in {m["model"] for m in TextEmbedding.list_supported_models()}:
        TextEmbedding.add_custom_model(
            model=E5_MODEL_NAME, pooling=PoolingType.MEAN, normalization=True,
            sources=ModelSource(hf="intfloat/multilingual-e5-small"), dim=384,
            model_file="onnx/model_qint8_avx512_vnni.onnx", license="mit", size_in_gb=0.118,
        )
    return TextEmbedding(
        E5_MODEL_NAME, specific_model_path=E5_MODEL_DIR, local_files_only=True,
        threads=4, providers=["CPUExecutionProvider"],
    )


class E5SignalClassifier:
    """Модель v2. В отличие от v1 оценивает кандидатов батчем и с учётом
    запроса (score_batch), а не по одному."""

    model_version = "e5-logreg-v2"

    def __init__(self) -> None:
        from ..models.v2 import relevance, signals

        self._signals = signals
        self._relevance = relevance
        with open(MODEL_V2_PATH, "rb") as f:
            artifact = pickle.load(f)  # комплект от аналитика команды — доверенный
        self._clf = artifact["classifier"]
        self._stage_threshold = float(artifact["threshold"])
        self._encoder = _load_encoder()
        log.info(
            "модель v2 загружена: классы %s, порог стадии %.2f, порог релевантности %.2f",
            list(self._clf.classes_), self._stage_threshold, RELEVANCE_THRESHOLD,
        )

    def score(self, candidate: SignalCandidate) -> ScoringResult:
        raise NotImplementedError("модель v2 оценивает с учётом запроса — используйте score_batch")

    def score_batch(self, query: str, candidates: list[SignalCandidate]) -> list[ScoringResult]:
        if not candidates:
            return []
        s = self._signals
        articles = [
            {"title": c.title or "", "text": _TAG_RE.sub(" ", c.summary or "")}
            for c in candidates
        ]
        features, pieces, vectors = s.build_features(articles, self._encoder)
        probabilities = self._clf.predict_proba(features)
        relevance = self._relevance.evaluate_query(
            query, articles, vectors, self._encoder, RELEVANCE_THRESHOLD,
        )

        results = []
        for article, proba, rel, passages in zip(articles, probabilities, relevance, pieces):
            scores = dict(zip(self._clf.classes_, map(float, proba)))
            label = max(scores, key=scores.get)
            weak = scores.get("weak", 0.0)
            enough_text = len(s.clean(article["text"]).split()) >= MIN_WORDS
            accepted = (
                rel["relevant"] and label == "weak" and weak >= self._stage_threshold and enough_text
            )

            # порядок проверок — как в SignalAnalyzer.analyze()
            if not enough_text:
                reason, tag = "Недостаточно текста: нужен текст публикации, не только заголовок.", REASON_TAGS["short"]
            elif rel["missing_conditions"]:
                reason = "Не подтверждены условия запроса: " + rel["missing_conditions"]
                tag = REASON_TAGS["conditions"]
            elif rel["query_needs_review"]:
                reason, tag = "Количественное условие или исключение в запросе требует проверки.", REASON_TAGS["review"]
            elif not rel["relevant"]:
                reason, tag = "Недостаточное смысловое соответствие запросу.", REASON_TAGS["relevance"]
            elif label != "weak":
                reason = f"Модель относит публикацию к классу «{s.LABELS[label]}»."
                tag = s.LABELS[label].capitalize()
            elif weak < self._stage_threshold:
                reason, tag = "Неуверенное различение стадий: требуется проверка.", REASON_TAGS["uncertain"]
            else:
                reason, tag = "Соответствует запросу; модель относит публикацию к слабым сигналам.", None

            # сработавшие текстовые признаки модели; теги-предикторы принятых
            # сигналов собирает оркестратор (нужны источники всей группы)
            fired = s.indicators(f"{article['title']} {article['text']}")
            indicators = [name for name, value in zip(s.PATTERNS, fired) if value > 0]
            relevance_tag = f"Релевантность {math.ceil(rel['relevance'] * 100)}%"
            key_predictors = [] if accepted else [t for t in (tag, relevance_tag) if t]

            results.append(ScoringResult(
                is_weak_signal=accepted,
                confidence=round(weak, 3),
                stage=None,
                explanation={
                    "predicted_class": s.LABELS[label],
                    "class_probabilities": {s.LABELS[k]: round(v, 3) for k, v in scores.items()},
                    "relevance": round(rel["relevance"], 3),
                    "accepted": accepted,
                    "enough_text": enough_text,
                    "reason": reason,
                    "key_predictors": key_predictors,
                    "indicators": indicators,
                    # фрагмент статьи, ближайший к запросу — помогает найти место в источнике
                    "passage_hint": " ".join(passages[rel["best_passage_index"]].split()[:18]),
                    "rationale": (
                        f"Модель v2 (E5 + классификатор стадии): класс «{s.LABELS[label]}», "
                        f"P(слабый сигнал)={weak:.2f}, релевантность запросу {rel['relevance']:.2f}."
                    ),
                },
            ))
        return results
