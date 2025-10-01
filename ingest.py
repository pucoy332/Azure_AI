

import json
import faiss
import numpy as np
from openai import AzureOpenAI
from packaging import version
import os
from dotenv import load_dotenv
# 파일 락을 위한 filelock 라이브러리 사용
from filelock import FileLock, Timeout

# 로그 파일 핸들러
import sys
class TeeLogger:
    def __init__(self, *files):
        self.files = files
    def write(self, msg):
        for f in self.files:
            f.write(msg)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

logfile = open('ingest.log', 'a', encoding='utf-8')
logger = TeeLogger(sys.stdout, logfile)
def logprint(*args, **kwargs):
    print(*args, **kwargs, file=logger)



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


# 단일 실행 진입점: ingest.py는 명시적으로 한 번만 실행(여러 파일 업로드 후 수동 또는 별도 트리거)
lock_path = 'meta.json.lock'
lock = FileLock(lock_path, timeout=60)
try:
    logprint('[ingest.py] 파일 락 획득 시도...')
    with lock:
        logprint('[ingest.py] 파일 락 획득!')
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
            if not text or len(text.strip()) < 20:
                logprint(f"[ingest.py] 제외: '{item.get('source')}' (텍스트 20자 미만 또는 없음)")
                continue
            if text.strip().lower().startswith(('http://', 'https://')):
                logprint(f"[ingest.py] 제외: '{item.get('source')}' (http/https로 시작)")
                continue
            logprint(f"[ingest.py] 임베딩 시도: '{item.get('source')}' (텍스트 길이: {len(text)})")
            try:
                emb = get_openai_embedding(text)
                logprint(f"[ingest.py] 임베딩 성공: '{item.get('source')}', shape: {emb.shape}")
                embeddings.append(emb)
                filtered_meta.append(item)
            except Exception as e:
                logprint(f"[ingest.py] 임베딩 실패: '{item.get('source')}', 에러: {e}")

        if embeddings:
            embeddings = np.vstack(embeddings)
            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(embeddings)
            faiss.write_index(index, 'faiss_index.bin')
            # faiss_index.bin flush/close 보장
            try:
                with open('faiss_index.bin', 'rb+') as fidx:
                    fidx.flush()
                    os.fsync(fidx.fileno())
            except Exception as e:
                print(f'[flush] faiss_index.bin flush error: {e}')
            # meta.json도 인덱싱된 항목만 따로 저장(선택)
            with open('meta.json', 'w', encoding='utf-8') as f:
                json.dump(filtered_meta, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            logprint('FAISS 인덱스 재생성 완료! (flush/close 완료)')
        else:
            logprint('인덱싱할 유효한 텍스트가 없습니다.')
except Timeout:
    logprint('[ingest.py] 파일 락 획득 실패: 다른 ingest.py가 실행 중입니다. 종료합니다.')

