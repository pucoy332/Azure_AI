**MS AI 개발역량 향상과정 MVP**

프로젝트 : 문서 유사도 검색 서비스

내용 : Azure OpenAI 기반으로 요구사항을 입력하면 유사한 기존 산출물을 빠르게 추천하고 문서 업로드 및 검색 기능을 제공

최종 업로드 사이트 링크:  
https://ms-azure-yeo-bebvbqevg5gzctdy.koreacentral-01.azurewebsites.net/static/index.html

---

## 1. 주요 기능 및 구조

- **문서 유사도 검색 API 제공**  
  FastAPI 기반 REST API 서버(app.py)  
  사용자가 텍스트 질의 또는 파일 업로드로 유사 문서 검색 가능

- **임베딩 및 벡터 인덱스 구축**  
  ingest.py에서 meta.json(문서 메타데이터) 파일을 읽어,  
  OpenAI(Azure OpenAI) 임베딩 모델로 각 문서의 임베딩 벡터 생성  
  FAISS를 이용해 벡터 인덱스(faiss_index.bin) 생성 및 저장

- **유사도 검색**  
  사용자가 입력한 텍스트를 임베딩 후, FAISS 인덱스에서 가장 유사한 문서 검색  
  검색 결과로 관련 문서 정보(meta.json에서 추출) 반환

- **Azure Blob Storage 연동**  
  파일 다운로드 API: Blob Storage에서 파일을 찾아 반환  
  환경변수(.env)로 연결 정보 관리

- **웹 프론트엔드**  
  static 폴더 내 index.html, app.js, style.css 등 웹 프론트엔드 제공

---

## 2. 기술 스택

- **Backend**: FastAPI, Python
- **AI/임베딩**: Azure OpenAI (gpt-4.1-mini, text-embedding-3-large)
- **벡터 검색**: FAISS
- **Storage**: Azure Blob Storage
- **Frontend**: HTML/JS/CSS (static 폴더)
- **배포**: Azure Web App

---

## 3. 동작 플로우

1. **문서 임베딩 및 인덱스 구축**  
   ingest.py 실행 → meta.json의 각 문서 임베딩 → faiss_index.bin 생성

2. **API 서버 실행**  
   app.py 실행 → FastAPI 서버 구동

3. **유사도 검색**  
   사용자가 텍스트 입력 → 임베딩 변환 → FAISS로 유사 문서 검색 → 결과 반환

4. **파일 다운로드**  
   Blob Storage에서 파일 다운로드 API 제공

5. **웹 프론트엔드**  
   index.html 등에서 API 호출 및 결과 표시
