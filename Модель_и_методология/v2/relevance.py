"""Условия запроса проверяются отдельно от стадии технологии."""
import re
import numpy as np

# Словарь можно расширять без переобучения. Одинаковые понятия на RU/EN.
CONCEPTS = {
 'mcp': r'\bmcp\b|model context protocol',
 'prompt_injection': r'prompt.?injection|tool poison|инъекц\w* промпт|внедрен\w* инструкц|отравлен\w* инструмент',
 'memory': r'\bmemory\b|\brag\b|памят\w*|retrieval.augmented',
 'federated': r'federated|федератив\w*',
 'banking': r'\bbank\w*|бан\w*(?:ов|ах|ами|инг|и|а)\b|financial institution|финансов\w* организац',
 'privacy': r'privacy|private data|confidential|without.{0,30}(sharing|exposing|transferring).{0,20}data|конфиденциал\w*|без передач\w* данн\w*',
 'offline': r'\boffline\b|air.gapped|without (the )?cloud|без (подключени\w* к )?облак\w*|без интернет\w*|автономн\w* режим',
 'edge': r'\bedge\b|on.device|on.chip|локальн\w*|на устройств\w*|периферийн\w*',
 'robot': r'robot\w*|робот\w*|\bcobot\w*',
 'welding': r'weld\w*|свар\w*',
 'photonic': r'photonic\w*|optical (comput\w*|processor\w*|chip\w*)|фотон\w*|оптическ\w* (вычисл\w*|процессор\w*|чип\w*)',
 'in_memory': r'in.memory comput\w*|compute.in.memory|вычислен\w* в памяти',
 'lora': r'\blora\b|low.rank adaptation',
 'mobile': r'\bmobile\b|smartphone\w*|phone\w*|мобильн\w*|смартфон\w*|телефон\w*',
 'fraud': r'fraud\w*|мошеннич\w*|антифрод\w*',
 'quantum': r'quantum|квантов\w*',
 'confidential': r'confidential comput\w*|confidential (ai|inference)|trusted execution|\btee\b|конфиденциальн\w* (вычислен\w*|инференс\w*)|доверенн\w* сред\w* исполнен\w*',
 'reinforcement': r'reinforcement learning|обучен\w* с подкреплен\w*',
 'industrial': r'industr\w*|factor(?:y|ies)|manufactur\w*|промышлен\w*|завод\w*|производств\w*',
 'zk': r'zero.knowledge|\bzkp?\b|нулев\w* разглашен\w*',
 'time_series': r'time.series|временн\w* ряд\w*',
 'plc': r'\bplc\w*\b|programmable logic controller|\bплк\b',
 'formal': r'formal verif\w*|формальн\w* верификац\w*',
 'tactile': r'tactile|haptic|тактильн\w*|осязан\w*',
 'deepfake': r'deepfake\w*|дипфейк\w*',
 'energy': r'energy|power consumption|энерг\w*',
 'cad': r'\bcad\b|\bсапр\b|computer.aided design',
 'lidar': r'\blidar\b|лидар\w*',
 'biomedical': r'biomedical|pacemaker\w*|биомедицин\w*|кардиостимулятор\w*',
 'chip': r'\bchip\w*|microchip\w*|чип\w*|микросхем\w*',
}

# Числа и неизвестные аббревиатуры не заменяются догадкой по общей теме.
def requirements(query):
    q=query.lower()
    required=[name for name,p in CONCEPTS.items() if re.search(p,q)]
    quoted=re.findall(r'[«“"]([^»”"]+)[»”"]',query)
    acronyms=[x.lower() for x in re.findall(r'\b[A-Z][A-Z0-9-]{1,}\b',query)
              if x not in {'AI','ML','LLM','LLMs','RU','EN'} and not any(re.search(p,x.lower()) for p in CONCEPTS.values())]
    numeric=bool(re.search(r'\d+\s*(мс|ms|ватт|w\b|гб|gb|токен|tokens|%)',q))
    return required,quoted+acronyms,numeric

def check_requirements(query,text):
    required,literals,numeric=requirements(query)
    missing=[x for x in required if not re.search(CONCEPTS[x],text.lower())]
    missing.extend(x for x in literals if x.lower() not in text.lower())
    # Broad negation needs human verification unless explicitly modeled as offline/privacy.
    unresolved=bool(re.search(r'\b(кроме|исключая|excluding|except)\b',query.lower()))
    if re.search(r'\bбез\b|\bwithout\b',query.lower()) and not any(x in required for x in ['offline','privacy']):unresolved=True
    return missing,numeric or unresolved

def evaluate_query(query,articles,passage_vectors,encoder,semantic_threshold):
    if not query.strip():raise ValueError('Запрос пустой.')
    qvec=next(iter(encoder.embed(['query: '+query])))
    result=[]
    for a,vec in zip(articles,passage_vectors):
        scores=np.asarray(vec)@qvec
        best=int(np.argmax(scores));score=float(scores[best])
        missing,unresolved=check_requirements(query,a.get('title','')+' '+a.get('text',''))
        result.append({'relevance':score,'missing_conditions':', '.join(missing),
                       'query_needs_review':unresolved,
                       'relevant':not missing and not unresolved and score>=semantic_threshold,
                       'best_passage_index':best})
    return result

def load_reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    from fastembed.common.model_description import ModelSource
    name='local/mmarco-miniLM-int8'
    if name not in {x['model'] for x in TextCrossEncoder.list_supported_models()}:
        TextCrossEncoder.add_custom_model(model=name,
            sources=ModelSource(hf='cross-encoder/mmarco-mMiniLMv2-L12-H384-v1'),
            model_file='onnx/model_qint8_avx512_vnni.onnx', license='apache-2.0', size_in_gb=.118)
    from pathlib import Path
    return TextCrossEncoder(name, specific_model_path=str(Path(__file__).resolve().parent/'reranker'),
                            local_files_only=True, threads=4, providers=['CPUExecutionProvider'])

def rerank_query(query, passages, passage_vectors, encoder, reranker):
    qvec=next(iter(encoder.embed(['query: '+query])))
    pairs=[]; counts=[]
    for ps, vs in zip(passages, passage_vectors):
        best=np.argsort(-(np.asarray(vs) @ qvec))[:2].tolist()
        chosen=list(dict.fromkeys([0]+best))
        pairs.extend((query, ps[i]) for i in chosen); counts.append(len(chosen))
    raw=list(reranker.rerank_pairs(pairs, batch_size=8)); out=[]; offset=0
    for n in counts:
        out.append(float(max(raw[offset:offset+n]))); offset += n
    return out
