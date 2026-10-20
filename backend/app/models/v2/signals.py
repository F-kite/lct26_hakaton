"""Локальная модель. Никакого сервера, ключей или запросов в интернет."""
from pathlib import Path
import re
import pickle
import numpy as np
from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

ROOT = Path(__file__).resolve().parent
MODEL_NAME = 'local/multilingual-e5-small-int8'
LABELS = {'weak': 'слабый сигнал', 'mature': 'зрелая технология', 'noise': 'шум'}

# Это признаки текста, а не готовые ответы. Веса учатся на размеченных примерах.
PATTERNS = {
    'research': r'\b(researchers?|experiment\w*|laboratory|proof.of.concept|prototype\w*|feasibility study|new method|novel approach)\b|исследован\w*|эксперимент\w*|прототип\w*',
    'early': r'\b(could someday|could enable|not yet|pilot project|pilot program|early.stage|first.of.its.kind|pre.commercial|limited deployment)\b|пилотн\w*|впервые|опытн\w+ образ\w*',
    'adoption': r'\b(widely (used|adopted)|million.{0,20}(users|customers|devices)|billion.{0,20}(users|transactions)|in production|deployed (at|across)|production workloads|years of.{0,20}(experience|development)|commercially available)\b|массов\w* внедр\w*|промышленн\w* эксплуатац\w*',
    'documentation': r'\b(documentation|installation|user guide|configuration|getting started|supported versions|reference manual)\b|документац\w*|руководство пользователя',
    'business_news': r'\b(quarterly (results|revenue|earnings)|earnings per share|stock.{0,15}(rose|fell|jump)|layoffs?|lawsuit|sues?|net income|fiscal (year|quarter)|conference.{0,20}(held|event))\b|выручк\w*|судебн\w* иск\w*|увольнен\w*',
    'funding': r'\b(funding round|raised.{0,25}(million|billion)|seed funding|series [abcde])\b|раунд финансирован\w*',
}
BOILERPLATE = re.compile(r'disclosure:|subscribe to|sign up for|all rights reserved|cookie (policy|consent)|your vote of support|thank you for reading|thecube.{0,80}(interview|coverage)', re.I)
BRANDS = re.compile(r'\b(MIT News|Massachusetts Institute of Technology|MIT|SiliconANGLE|theCUBE|TechCrunch)\b', re.I)

def clean(text):
    lines = [x for x in str(text or '').splitlines() if not BOILERPLATE.search(x)]
    text = re.sub(r'https?://\S+', ' ', '\n'.join(lines))
    text = BRANDS.sub(' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def chunks(title, text):
    """Читаем начало и части статьи; длинный текст не обрезается до заголовка."""
    title, text = clean(title), clean(text)
    words = text.split()
    if not words:
        return [title]
    starts = list(range(0, len(words), 150))
    if len(starts) > 8:
        starts = [starts[i] for i in np.linspace(0, len(starts)-1, 8, dtype=int)]
    return [(title + '. ' + ' '.join(words[s:s+190])).strip() for s in starts]

def indicators(text):
    text = clean(text).lower()
    return np.array([min(len(re.findall(p, text)), 8)/8 for p in PATTERNS.values()], dtype=np.float32)

def load_encoder():
    if MODEL_NAME not in {x['model'] for x in TextEmbedding.list_supported_models()}:
        TextEmbedding.add_custom_model(model=MODEL_NAME, pooling=PoolingType.MEAN,
            normalization=True, sources=ModelSource(hf='intfloat/multilingual-e5-small'),
            dim=384, model_file='onnx/model_qint8_avx512_vnni.onnx', license='mit', size_in_gb=.118)
    return TextEmbedding(MODEL_NAME, specific_model_path=str(ROOT/'encoder'),
                         local_files_only=True, threads=4, providers=['CPUExecutionProvider'])

def build_features(articles, encoder=None):
    """Одна строка = смысл начала + смысл всей статьи + шесть признаков."""
    encoder = encoder or load_encoder()
    pieces = [chunks(a.get('title',''), a.get('text','')) for a in articles]
    encoded = list(encoder.embed(['passage: '+p for ps in pieces for p in ps], batch_size=16))
    features, document_vectors, offset = [], [], 0
    for a, ps in zip(articles, pieces):
        vectors = np.asarray(encoded[offset:offset+len(ps)])
        offset += len(ps)
        mean = vectors.mean(axis=0); mean /= max(np.linalg.norm(mean), 1e-9)
        features.append(np.r_[vectors[0], mean, indicators(a.get('title','')+' '+a.get('text',''))])
        document_vectors.append(vectors)
    return np.asarray(features), pieces, document_vectors

class SignalAnalyzer:
    def __init__(self, model_path=None):
        # Загружайте pickle только из доверенного комплекта.
        with open(model_path or ROOT/'Модель.pkl', 'rb') as f:
            artifact = pickle.load(f)
        self.classifier = artifact['classifier']
        self.threshold = artifact['threshold']
        self.encoder = load_encoder()

    def classify(self, articles):
        """articles: список словарей title, text, url. Возвращает три оценки и флаг проверки."""
        if not articles:
            return []
        X, _, _ = build_features(articles, self.encoder)
        probabilities = self.classifier.predict_proba(X)
        results = []
        for a, p in zip(articles, probabilities):
            scores = dict(zip(self.classifier.classes_, map(float,p)))
            label = max(scores, key=scores.get)
            short = len(clean(a.get('text','')).split()) < 60
            results.append(dict(id=a.get('id'), url=a.get('url',''), label=label,
                class_name=LABELS[label], scores=scores,
                needs_review=short or scores[label] < self.threshold,
                reason='Недостаточно текста' if short else 'Оценка обученной модели; не процент достоверности источника'))
        return results

    def analyze(self, query, articles):
        """Аудит всех кандидатов. Стадия, релевантность и причина исключения раздельны."""
        import pandas as pd
        try:
            from .relevance import evaluate_query
        except ImportError:
            from relevance import evaluate_query
        if not articles:
            return pd.DataFrame(columns=['title','url','label','confidence','relevance','accepted','reason'])
        X, pieces, vectors = build_features(articles, self.encoder)
        probabilities = self.classifier.predict_proba(X)
        similarity_threshold = float((ROOT/'Порог_релевантности.txt').read_text().strip())
        relevance = evaluate_query(query, articles, vectors, self.encoder, similarity_threshold)
        results=[]
        for a,p,r,ps in zip(articles,probabilities,relevance,pieces):
            scores=dict(zip(self.classifier.classes_,map(float,p)));label=max(scores,key=scores.get)
            enough_text=len(clean(a.get('text','')).split())>=60
            accepted=r['relevant'] and label=='weak' and scores['weak']>=self.threshold and enough_text
            if not enough_text:reason='Недостаточно текста: нужен текст публикации, не только заголовок.'
            elif r['missing_conditions']:reason='Не подтверждены условия: '+r['missing_conditions']
            elif r['query_needs_review']:reason='Количественное условие или исключение требует проверки.'
            elif not r['relevant']:reason='Недостаточное смысловое соответствие запросу.'
            elif label!='weak':reason='Класс: '+LABELS[label]
            elif scores['weak']<self.threshold:reason='Неуверенное различение стадий: требуется проверка.'
            else:reason='Соответствует запросу; модель относит публикацию к слабым сигналам.'
            results.append(dict(id=a.get('id'),technology_key=a.get('technology_key',''),title=a.get('title',''),
                url=a.get('url',''),label=label,confidence=scores[label],weak_score=scores['weak'],
                relevance=r['relevance'],accepted=accepted,reason=reason,
                # Короткая выдержка помогает найти фрагмент в исходной статье; не является объяснением класса.
                passage_hint=' '.join(ps[r['best_passage_index']].split()[:18])))
        return pd.DataFrame(results)

    def rank(self, query, articles, limit=15):
        """До 15 подходящих технологий. Недостаток результатов не заполняется мусором."""
        if limit<1:raise ValueError('limit должен быть положительным.')
        audit=self.analyze(query,articles)
        if audit.empty:return audit
        selected=audit[audit.accepted].sort_values(['relevance','weak_score'],ascending=False)
        seen=set();kept=[]
        for i,row in selected.iterrows():
            # При наличии ключа группируем именно технологии, а не страницы об одной технологии.
            key=row.technology_key or re.sub(r'\W+',' ',row.title.lower()).strip()
            if key in seen:continue
            seen.add(key);kept.append(i)
            if len(kept)>=limit:break
        return selected.loc[kept].reset_index(drop=True)
