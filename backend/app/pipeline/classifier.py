"""Контракт для ML-модели (Protocol SignalClassifier) — оркестратор не
знает деталей конкретной реализации. Единственная реализация —
TrainedModelClassifier (sklearn TF-IDF -> LogisticRegression, см.
Модель_и_SQL/Методология_и_инструкция.md). Непроверенный вход (не EN /
пустой summary) получает confidence=0.0, а не суррогатную оценку.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class SignalCandidate:
    """Вход в модель — один кандидат в слабый сигнал: одна тема, возможно
    подтверждённая несколькими записями из разных источников.
    """

    feed_item_ids: list[int]
    title: str
    summary: str | None
    sources: list[str]        # source_key каждой подтверждающей записи
    trust_levels: list[str]   # high | medium | low, по одной на sources[i]
    published_at: datetime | None
    language: str = "EN"


@dataclass
class ScoringResult:
    """Выход модели. explanation обязателен — интерпретируемость сигнала
    (какие признаки повлияли на оценку).
    """

    is_weak_signal: bool
    confidence: float          # 0..1
    stage: str | None          
    explanation: dict = field(default_factory=dict)


class SignalClassifier(Protocol):
    """Контракт для модели."""

    model_version: str  # какая модель/версия дала оценку

    def score(self, candidate: SignalCandidate) -> ScoringResult: ...


LABEL_WEAK_SIGNAL = "слабый сигнал"
LABEL_MATURE = "зрелая технология"
LABEL_NOISE = "шум"

MIN_SUMMARY_CHARS = 20
MAX_MODEL_INPUT_CHARS = 14_000

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")


def _clean_model_input(candidate: SignalCandidate) -> str | None:
    """Собрать текст в форме, ожидаемой моделью, либо None, если кандидат не подходит.
    """
    if candidate.language != "EN":
        return None
    if not candidate.summary:
        return None

    summary = _WS_RE.sub(" ", _URL_RE.sub("", _TAG_RE.sub(" ", candidate.summary))).strip()
    if len(summary) < MIN_SUMMARY_CHARS:
        return None

    title = _WS_RE.sub(" ", candidate.title or "").strip()
    text = f"{title}. {summary}" if title else summary
    return text[:MAX_MODEL_INPUT_CHARS]


class TrainedModelClassifier:
    """Обёртка над обученной моделью под Protocol SignalClassifier."""

    model_version = "trained-tfidf-logreg-v1"

    def __init__(self, model_path: str):
        import pickle

        with open(model_path, "rb") as f:
            self._model = pickle.load(f)
        self._classes = list(self._model.classes_)
        if LABEL_WEAK_SIGNAL not in self._classes:
            raise ValueError(
                f"модель не содержит ожидаемый класс {LABEL_WEAK_SIGNAL!r}, "
                f"реальные классы: {self._classes}"
            )
        self._vectorizer, self._clf = self._find_steps()
        log.info("модель загружена: %s, классы: %s", model_path, self._classes)

    def _find_steps(self):
        """Найти TF-IDF векторизатор и классификатор внутри pipeline по
        сигнатуре."""
        vectorizer = clf = None
        for _, step in self._model.steps:
            if hasattr(step, "get_feature_names_out"):
                vectorizer = step
            if hasattr(step, "coef_"):
                clf = step
        if vectorizer is None or clf is None:
            raise ValueError(
                "не удалось найти TF-IDF векторизатор и/или классификатор "
                "внутри загруженного pipeline"
            )
        return vectorizer, clf

    def vectorize(self, texts: list[str]):
        """TF-IDF-векторы для текстов — переиспользуется display_grouping.py
        для косинусной близости между кандидатами."""
        return self._vectorizer.transform(texts)

    def explain_features(self, text: str, predicted_class: str, top_k: int = 4) -> list[str]:
        """Топ-K термов текста, сильнее всего повлиявших на предсказанный
        класс: вес = коэффициент LogisticRegression для класса × вес
        TF-IDF терма в конкретном тексте, берём только термы с ненулевым
        вкладом."""
        try:
            class_idx = list(self._clf.classes_).index(predicted_class)
        except ValueError:
            return []

        x = self._vectorizer.transform([text])
        coef = self._clf.coef_[class_idx if self._clf.coef_.shape[0] > 1 else 0]
        contributions = x.multiply(coef).toarray()[0]
        if not contributions.any():
            return []

        feature_names = self._vectorizer.get_feature_names_out()
        top_indices = contributions.argsort()[::-1][:top_k]
        return [str(feature_names[i]) for i in top_indices if contributions[i] > 0]

    def score(self, candidate: SignalCandidate) -> ScoringResult:
        text = _clean_model_input(candidate)
        if text is None:
            return ScoringResult(
                is_weak_signal=False,
                confidence=0.0,
                stage=None,
                explanation={
                    "predicted_class": None,
                    "rationale": (
                        "Кандидат исключён: не английский язык или недостаточно "
                        "текста в summary — не проверенный моделью вход."
                    ),
                },
            )

        proba = self._model.predict_proba([text])[0]
        by_class = dict(zip(self._classes, proba))
        predicted = self._model.classes_[proba.argmax()]

        return ScoringResult(
            is_weak_signal=predicted == LABEL_WEAK_SIGNAL,
            confidence=round(float(by_class.get(LABEL_WEAK_SIGNAL, 0.0)), 3),
            stage=None,
            explanation={
                "predicted_class": predicted,
                "class_probabilities": {k: round(float(v), 3) for k, v in by_class.items()},
                "key_predictors": self.explain_features(text, predicted),
                "rationale": (
                    f"Обученная модель (TF-IDF + LogisticRegression): класс {predicted!r}, "
                    f"P({LABEL_WEAK_SIGNAL})={by_class.get(LABEL_WEAK_SIGNAL, 0.0):.2f}."
                ),
            },
        )
