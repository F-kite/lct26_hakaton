"""Контракт для ML-модели: что она получает на вход и что обязана вернуть.

Оркестратор (orchestrator.py) работает с Protocol SignalClassifier, не
с конкретной реализацией — подключить другую модель означает написать
класс, реализующий .score(), и передать его экземпляр в run_search().
Остальной пайплайн не меняется.

Единственная реализация — TrainedModelClassifier, обёртка над обученной
моделью аналитика (sklearn: TF-IDF -> LogisticRegression, см.
Модель_и_SQL/Методология_и_инструкция.md). Эвристика-заглушка, которая
была здесь раньше, убрана: она давала кандидатам без валидного текста
(не EN / пустой summary) оценку, несопоставимую по шкале с реальной
моделью, и эти "эвристические" результаты систематически вытесняли из
топ-15 честные оценки модели (эвристика легко давала 0.7-0.95 на свежих
записях с высоким доверием, модель — более взвешенные 0.3-0.6 даже на
явных слабых сигналах). Теперь кандидат, для которого нет проверенного
входа, просто не получает шанс попасть в выдачу (confidence=0.0), а не
угадывается по суррогатным признакам.
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
    language: str = "EN"      # модель обучена и проверена только на EN


@dataclass
class ScoringResult:
    """Выход модели. explanation обязателен — интерпретируемость требует
    ТЗ (раздел 2: "показывать, по каким признакам..."; критерий 8.3).
    """

    is_weak_signal: bool
    confidence: float          # 0..1
    stage: str | None          # модель стадию не определяет — см. TrainedModelClassifier
    explanation: dict = field(default_factory=dict)


class SignalClassifier(Protocol):
    """Контракт для модели. model_version — ТЗ требует явно логировать,
    какая модель дала оценку (особенно при выборе из нескольких).
    """

    model_version: str

    def score(self, candidate: SignalCandidate) -> ScoringResult: ...


# --------------------------------------------------------------------------
# Обученная модель (Этап 1 ТЗ) — sklearn.Pipeline (TF-IDF -> LogisticRegression),
# см. Методология_и_инструкция.md от аналитика. 172 обучающих публикации,
# проверка: 72/76 (94.7%), топ-15 на контрольной выборке — 15/15.
# --------------------------------------------------------------------------

LABEL_WEAK_SIGNAL = "слабый сигнал"
LABEL_MATURE = "зрелая технология"
LABEL_NOISE = "шум"

# Модель проверена только на английском тексте содержательной публикации
# (заголовок+описание+очищенный текст, без URL, до ~14000 символов) — не на
# заголовке без текста и не на русском. Ниже этого порога по символам в
# summary — не "проверенный вход" по формулировке методологии, кандидат
# исключается из оценки (см. score()), а не угадывается суррогатно.
MIN_SUMMARY_CHARS = 20
MAX_MODEL_INPUT_CHARS = 14_000

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")


def _clean_model_input(candidate: SignalCandidate) -> str | None:
    """Собрать текст в форме, ожидаемой моделью, либо None, если кандидат
    не подходит (см. MIN_SUMMARY_CHARS) — методология прямо предупреждает
    не подавать модели заголовок без текста, HTML или русский язык.
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
    """Обёртка над обученной моделью аналитика под Protocol SignalClassifier."""

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
        сигнатуре, а не по жёстко зашитым именам шагов — устойчивее к тому,
        как именно аналитик назвал шаги при обучении."""
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
        """TF-IDF векторы уже обученного векторизатора — переиспользуется
        display_grouping.py для похожести кандидатов (не для скоринга)."""
        return self._vectorizer.transform(texts)

    def explain_features(self, text: str, predicted_class: str, top_k: int = 4) -> list[str]:
        """Топ-K термов текста, сильнее всего повлиявших на предсказанный
        класс — настоящая word-level интерпретируемость (ТЗ раздел 2:
        "показывать, по каким признакам..."; критерий 8.3), не хардкод
        категорий: вес = коэффициент LogisticRegression для класса × вес
        TF-IDF терма в КОНКРЕТНОМ тексте, берём только термы, реально
        присутствующие в тексте (ненулевой вклад)."""
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
            # Не EN или недостаточно текста — не проверенный моделью вход
            # (см. Методология_и_инструкция.md). confidence=0.0 естественно
            # не проходит порог SIGNAL_SCORE_THRESHOLD в orchestrator.py —
            # кандидат просто не попадёт в выдачу, без суррогатной оценки.
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
            stage=None,  # модель не определяет стадию — только 3 класса, см. методологию
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
