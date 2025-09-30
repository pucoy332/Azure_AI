

# ===== 정상 구조로 전체 재정리 =====

import json
import faiss
import numpy as np
import openai
import os
from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from azure.storage.blob import BlobServiceClient
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv

# SuppressStderr 클래스를 파일 상단에 정의
import sys
class SuppressStderr:
    def __enter__(self):
        self._original_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr.close()
        sys.stderr = self._original_stderr

load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') or os.getenv('AZURE_OPENAI_KEY')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE') or os.getenv('AZURE_OPENAI_ENDPOINT')
EMBED_MODEL = os.getenv('EMBED_MODEL') or os.getenv('EMBED_DEPLOYMENT')
openai.api_key = OPENAI_API_KEY
openai.api_base = OPENAI_API_BASE

app = FastAPI(title='문서 유사도 검색 API', description='요구사항 텍스트를 입력하면 유사한 기존 산출물을 찾아드립니다.')

# 파일 다운로드 API (Blob Storage)
@app.get('/download')
async def download_file(filename: str = Query(..., description="다운로드할 파일명")):
    try:
        from urllib.parse import unquote
        filename_decoded = unquote(filename)
        conn_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
        container = os.getenv('AZURE_STORAGE_CONTAINER')
        if not conn_str or not container:
            return JSONResponse({"error": "Azure Storage 연결 정보가 없습니다."}, status_code=400)
        from azure.storage.blob import BlobServiceClient
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        # 파일명 완전 일치하는 blob 찾기 (한글/공백/특수문자 대응)
        container_client = blob_service.get_container_client(container)
        blob_name = None
        for blob in container_client.list_blobs():
            if blob.name == filename_decoded:
                blob_name = blob.name
                break
        if not blob_name:
            return JSONResponse({"error": f"파일({filename_decoded})이 Blob Storage에 존재하지 않습니다."}, status_code=404)
        blob_client = blob_service.get_blob_client(container=container, blob=blob_name)
        stream = blob_client.download_blob()
        file_data = stream.readall()
        # 파일 확장자 추출
        ext = blob_name.lower().split('.')[-1]
        content_type = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }.get(ext, 'application/octet-stream')
        from urllib.parse import quote
        return StreamingResponse(
            iter([file_data]),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(blob_name)}"
            }
        )
    except Exception as e:
        print(f"[다운로드 오류] {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
BASE_DIR = Path(__file__).parent
app.mount('/static', StaticFiles(directory=BASE_DIR / 'static'), name='static')

@app.post('/upload')
async def upload_file(file: UploadFile = File(...), overwrite: str = Form('0')):
    try:
        conn_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
        container = os.getenv('AZURE_STORAGE_CONTAINER')
        if not conn_str or not container:
            return {"error": "Azure Storage 연결 정보가 없습니다."}
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        blob_client = blob_service.get_blob_client(container=container, blob=file.filename)
        if blob_client.exists() and overwrite != '1':
            return {"error": f"동일한 이름의 파일({file.filename})이 이미 존재합니다."}
        content = await file.read()
        blob_client.upload_blob(content, overwrite=(overwrite=='1'))

        # 파일 본문(text) 추출 (txt, docx, pdf 지원)
        text_content = None
        try:
            ext = file.filename.lower().split('.')[-1]
            if ext == 'txt':
                text_content = content.decode('utf-8', errors='ignore')
            elif ext == 'docx':
                from io import BytesIO
                from docx import Document
                docx_file = BytesIO(content)
                doc = Document(docx_file)
                text_content = '\n'.join([p.text for p in doc.paragraphs])
            elif ext == 'pdf':
                from io import BytesIO
                pdf_file = BytesIO(content)
                text_content = ''
                with SuppressStderr():
                    # 1차: PyPDF2
                    try:
                        from PyPDF2 import PdfReader
                        reader = PdfReader(pdf_file)
                        text_content = '\n'.join([page.extract_text() or '' for page in reader.pages])
                    except Exception as e1:
                        print(f'PyPDF2 추출 실패: {e1}')
                    # 2차: pdfplumber
                    if not text_content.strip():
                        try:
                            import pdfplumber
                            pdf_file.seek(0)
                            with pdfplumber.open(pdf_file) as pdf:
                                text_content = '\n'.join([page.extract_text() or '' for page in pdf.pages])
                        except Exception as e2:
                            print(f'pdfplumber 추출 실패: {e2}')
                    # 3차: PyMuPDF(fitz)
                    if not text_content.strip():
                        try:
                            import fitz  # PyMuPDF
                            pdf_file.seek(0)
                            doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
                            text_content = '\n'.join([page.get_text() for page in doc])
                        except Exception as e3:
                            print(f'PyMuPDF 추출 실패: {e3}')
                    # 4차: OCR (이미지 기반 PDF, pytesseract 필요)
                    if not text_content.strip():
                        try:
                            import pdfplumber
                            import pytesseract
                            pdf_file.seek(0)
                            with pdfplumber.open(pdf_file) as pdf:
                                ocr_texts = []
                                for page in pdf.pages:
                                    img = page.to_image(resolution=300)
                                    ocr_text = pytesseract.image_to_string(img.original)
                                    ocr_texts.append(ocr_text)
                                text_content = '\n'.join(ocr_texts)
                        except Exception as e4:
                            print(f'OCR 추출 실패: {e4}')
            else:
                text_content = ''
        except Exception as e:
            print(f'본문 추출 오류: {e}')
            text_content = ''

        # Azure Cognitive Search 인덱스 자동 추가
        try:
            search_endpoint = os.getenv('AZURE_SEARCH_ENDPOINT')
            search_api_key = os.getenv('AZURE_SEARCH_API_KEY')
            search_index = os.getenv('AZURE_SEARCH_INDEX')
            if search_endpoint and search_api_key and search_index:
                import requests
                from datetime import datetime
                import base64
                safe_path = base64.urlsafe_b64encode(file.filename.encode('utf-8')).decode('ascii')
                doc = {
                    "@search.action": "mergeOrUpload",
                    "content": text_content if text_content else "",
                    "metadata_storage_name": file.filename,
                    "metadata_storage_path": safe_path,
                    "metadata_storage_content_type": file.content_type,
                    "metadata_storage_size": len(content),
                    "metadata_storage_last_modified": datetime.utcnow().isoformat() + 'Z',
                    "metadata_storage_file_extension": f'.{ext}'
                }
                url = f"{search_endpoint}/indexes/{search_index}/docs/index?api-version=2025-09-01"
                headers = {
                    "Content-Type": "application/json",
                    "api-key": search_api_key
                }
                payload = {"value": [doc]}
                resp = requests.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    search_result = resp.json()
                else:
                    search_result = {"error": f"Search 인덱스 추가 실패: {resp.text}"}
            else:
                search_result = {"error": "Search 인덱스 정보 누락"}
        except Exception as se:
            search_result = {"error": f"Search 인덱스 추가 오류: {str(se)}"}

        # meta.json에 새 파일 정보 추가 (중복시 덮어쓰기)
        try:
            meta_path = BASE_DIR / 'meta.json'
            meta = []
            if meta_path.exists():
                with open(meta_path, encoding='utf-8') as f:
                    meta = json.load(f)
            # 파일명 중복시 기존 항목 제거
            meta = [item for item in meta if item.get('source') != file.filename]
            # 새 항목 추가
            meta.append({
                'source': file.filename,
                'text': text_content if text_content else '',
                'content_type': file.content_type,
                'size': len(content)
            })
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as me:
            print(f"meta.json 갱신 오류: {me}")

        # 업로드 성공 후 ingest.py 자동 실행 (FAISS 인덱스 갱신)
        try:
            import subprocess, sys
            python_exe = sys.executable  # 현재 FastAPI가 실행 중인 파이썬 경로
            subprocess.Popen([python_exe, 'ingest.py'], cwd=str(BASE_DIR))
        except Exception as ie:
            print(f"ingest.py 자동 실행 오류: {ie}")

        return {"message": "Azure Storage 업로드 성공", "filename": file.filename, "search_index": search_result}
    except Exception as e:
        return {"error": str(e)}

@app.post('/summarize')
async def summarize(request: Request):
    try:
        data = await request.json()
        text = data.get("text", "")
        query = data.get('query', '')
        doc_title = data.get('source', '문서명없음')
        # text가 없으면 meta.json에서 source로 본문 찾아서 사용
        if not text:
            meta_path = BASE_DIR / 'meta.json'
            if meta_path.exists():
                with open(meta_path, encoding='utf-8') as f:
                    meta = json.load(f)
                for item in meta:
                    if item.get('source') == doc_title:
                        text = item.get('text', '')
                        break
        print(f"[요약 요청] text 길이: {len(text)}, 내용: {text[:100]}")  # 앞 100자만 출력
        print(f"[요약 요청] query: {query}")
        max_length = 4000
        if text and len(text) > max_length:
            # 앞 2000자 + 뒤 2000자 합침
            text = text[:2000] + '\n...\n' + text[-2000:]
        if not text:
            return JSONResponse({"error": "본문이 없습니다."})
        prompt = (
            f"아래는 문서의 본문입니다. 문서명: {doc_title}\n"
            f"본문을 충분히 읽고, 요구사항과 관련된 핵심 키워드 5개와 요약문을 각각 한글로 작성해줘.\n"
            f"[요구사항]\n{query}\n[문서 본문]\n{text}\n---\n"
            f"출력 형식:\n키워드: 키워드1, 키워드2, 키워드3, 키워드4, 키워드5\n요약: (2~3문장)"
        )
        gpt_deployment = os.getenv('GPT_DEPLOYMENT') or 'gpt-3.5-turbo'
        completion = openai.chat.completions.create(
            model=gpt_deployment,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=1.0
        )
        output = completion.choices[0].message.content
        import re
        kw_match = re.search(r'키워드\s*[:：]\s*(.+)', output)
        summary_match = re.search(r'요약\s*[:：]\s*(.+)', output)
        keywords = kw_match.group(1).strip() if kw_match else ''
        summary = summary_match.group(1).strip() if summary_match else output.strip()
        return JSONResponse({"keywords": keywords, "summary": summary})
    except Exception as e:
        return JSONResponse({"error": str(e)})
    try:
        import re
        data = await request.json()
        text = data.get("text", "")
        query = data.get('query', '')
        doc_title = data.get('source', '문서명없음')
        # text가 없으면 meta.json에서 source로 본문 찾아서 사용
        if not text:
            meta_path = BASE_DIR / 'meta.json'
            if meta_path.exists():
                with open(meta_path, encoding='utf-8') as f:
                    meta = json.load(f)
                found = False
                for item in meta:
                    # 공백 제거 후 비교
                    if item.get('source', '').strip() == doc_title.strip():
                        text = item.get('text', '')
                        print(f"[매칭된 문서명] {doc_title} -> [본문 길이] {len(text)}")
                        found = True
                        break
                if not found:
                    print(f"[매칭 실패] 요청 문서명: {doc_title}, meta.json 내 source 목록: {[item.get('source') for item in meta]}")
                    return JSONResponse({"error": "본문이 없습니다. (문서명 매칭 실패)"})
                if not text or not text.strip():
                    print(f"[본문 없음] 문서명: {doc_title}, 실제 본문: '{text}'")
                    return JSONResponse({"error": "본문이 없습니다. (text 필드 비어있음)"})
        print(f"[요약 요청] text 길이: {len(text)}, 내용: {text[:100]}")  # 앞 100자만 출력
        print(f"[요약 요청] query: {query}")
        max_length = 4000
        if text and len(text) > max_length:
            # 앞 2000자 + 뒤 2000자 합침
            text = text[:2000] + '\n...\n' + text[-2000:]
        prompt = (
            f"아래는 문서의 본문입니다. 문서명: {doc_title}\n"
            f"본문을 충분히 읽고, 요구사항과 관련된 핵심 키워드 5개와 요약문을 각각 한글로 작성해줘.\n"
            f"[요구사항]\n{query}\n[문서 본문]\n{text}\n---\n"
            f"출력 형식:\n키워드: 키워드1, 키워드2, 키워드3, 키워드4, 키워드5\n요약: (2~3문장)"
        )
        gpt_deployment = os.getenv('GPT_DEPLOYMENT') or 'gpt-3.5-turbo'
        completion = openai.chat.completions.create(
            model=gpt_deployment,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=1.0
        )
        output = completion.choices[0].message.content
        kw_match = re.search(r'키워드\s*[:：]\s*(.+)', output)
        summary_match = re.search(r'요약\s*[:：]\s*(.+)', output)
        keywords = kw_match.group(1).strip() if kw_match else ''
        summary = summary_match.group(1).strip() if summary_match else output.strip()
        return JSONResponse({"keywords": keywords, "summary": summary})
    except Exception as e:
        return JSONResponse({"error": str(e)})

FAISS_INDEX_PATH = BASE_DIR / 'faiss_index.bin'
META_PATH = BASE_DIR / 'meta.json'
faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
with open(META_PATH, encoding='utf-8') as f:
    meta = json.load(f)

def get_openai_embedding(text):
    response = openai.embeddings.create(
        input=[text],
        model=EMBED_MODEL
    )
    return np.array(response.data[0].embedding, dtype=np.float32).reshape(1, -1)

def vector_search(query, top_k=5):
    query_vec = get_openai_embedding(query)
    D, I = faiss_index.search(query_vec, top_k)
    results = []
    for idx, score in zip(I[0], D[0]):
        if idx < 0 or idx >= len(meta):
            continue
        item = meta[idx]
        similarity = 1 / (1 + float(score))
        results.append({
            '문서명': item.get('source', '제목없음'),
            '유사도': similarity
        })
    results = sorted(results, key=lambda x: -x['유사도'])
    return results

# 검색 API 추가
from fastapi import Query
@app.get('/search')
async def search(q: str = Query(..., description="검색 질의"), top_k: int = Query(5, description="결과 수")):
    try:
        results = vector_search(q, top_k)
        if not results:
            return {"질의": q, "결과": [], "메시지": "검색 결과가 없습니다."}
        return {"질의": q, "결과": results}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

