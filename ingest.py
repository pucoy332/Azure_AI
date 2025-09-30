import json
import faiss
import numpy as np
from openai import AzureOpenAI
from packaging import version
import os
from dotenv import load_dotenv


load_dotenv()
# Azure OpenAI 환경변수 명확화
AZURE_OPENAI_KEY = os.getenv('OPENAI_API_KEY') or os.getenv('AZURE_OPENAI_KEY')
AZURE_OPENAI_ENDPOINT = os.getenv('OPENAI_API_BASE') or os.getenv('AZURE_OPENAI_ENDPOINT')
AZURE_OPENAI_VERSION = os.getenv('OPENAI_API_VERSION') or "2023-05-15"
EMBED_DEPLOYMENT = os.getenv('EMBED_DEPLOYMENT') or os.getenv('EMBED_MODEL')

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

with open('meta.json', encoding='utf-8') as f:
    meta = json.load(f)

def get_openai_embedding(text):
    # 최대 8000자까지만 임베딩
    max_length = 8000
    if text and len(text) > max_length:
        text = text[:max_length]
    response = client.embeddings.create(
        input=[text],
        model=EMBED_DEPLOYMENT
    )
    embedding = response.data[0].embedding
    return np.array(embedding, dtype=np.float32)

embeddings = []
filtered_meta = []
for item in meta:
    text = item.get('text', '')
    # 의미 없는 텍스트(빈 문자열, 20자 미만, http/https로 시작) 제외
    if not text or len(text.strip()) < 20 or text.strip().lower().startswith(('http://', 'https://')):
        continue
    emb = get_openai_embedding(text)
    embeddings.append(emb)
    filtered_meta.append(item)

if embeddings:
    embeddings = np.vstack(embeddings)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    faiss.write_index(index, 'faiss_index.bin')
    # meta.json도 인덱싱된 항목만 따로 저장(선택)
    with open('meta.json', 'w', encoding='utf-8') as f:
        json.dump(filtered_meta, f, ensure_ascii=False, indent=2)
    print('FAISS 인덱스 재생성 완료!')
else:
    print('인덱싱할 유효한 텍스트가 없습니다.')
