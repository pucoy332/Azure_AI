간단 PoC: 로컬 텍스트 문서를 OpenAI 임베딩으로 변환하여 FAISS로 인덱스 후 FastAPI로 검색 제공

준비
- Python 3.10+ 설치
- 가상환경 생성 및 활성화
- 의존성 설치: pip install -r requirements.txt
- .env에 OPENAI_API_KEY 설정

사용법
1. 색인 생성
   python poC_ingest.py
2. 서버 실행
   uvicorn app:app --reload
3. 검색
   GET /search?q=검색어

참고: 이 PoC는 교육용이며, 프로덕션 전에는 보안/성능/에러처리 강화 필요
