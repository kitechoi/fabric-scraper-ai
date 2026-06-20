# 원단 정보 수집기

Playwright + Gemini LLM 기반 원단 쇼핑몰 스크래퍼.  
영수증 이미지에서 상품명을 추출하고, 판매처 사이트에서 URL을 탐색해 정보를 수집·저장한다.

---

## 요구사항

- Python 3.10+
- Gemini API 키 ([Google AI Studio](https://aistudio.google.com))

---

## 설치

```bash
cd fabric-scraper

# 1. 가상환경 생성 + 의존성 설치 (pytest 포함)
make install

# 2. Playwright 브라우저 설치
.venv/bin/playwright install chromium

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일에 GEMINI_API_KEY=your_key_here 입력
```

---

## 실행

```bash
make dev
```

내부 동작: **unit + integration 테스트 통과 후** Streamlit 앱 시작.  
테스트가 하나라도 실패하면 앱이 뜨지 않는다.

> `streamlit run ui/app.py` 를 직접 치지 말 것.

---

## 테스트

```bash
make test        # unit + integration (빠름, ~10초)
make test-e2e    # 실제 네트워크 + LLM 호출 (느림)
```

### 특정 테스트만

```bash
.venv/bin/pytest tests/unit/test_db_crud.py -v
.venv/bin/pytest -k "fallback" -v
```

---

## 테스트 구조

```
tests/
  unit/           # 외부 호출 없음 — make test에 포함
    test_url_finder_query.py    # 상품코드 추출 로직
    test_fetcher_utils.py       # 로고 이미지 감지
    test_clean_json.py          # LLM 응답 JSON 정제
    test_db_crud.py             # SQLite CRUD 전체
    test_fabric_info_model.py   # Pydantic 모델 검증
    test_exceptions.py          # 커스텀 예외 클래스
  integration/    # LLM·Playwright mock — make test에 포함
    test_extractor_mock.py      # LLM 추출 + 모델 폴백
    test_receipt_parser_mock.py # 영수증 파싱 + 모델 폴백
    test_url_finder_mock.py     # URL 탐색 + LLM 선택
    test_pipeline_mock.py       # 파이프라인 전체 분기
  e2e/            # 실제 사이트/LLM — make test-e2e로만 실행
  fixtures/       # 테스트용 이미지 등 (수동 추가)
```

---

## 명령어 요약

| 명령어 | 설명 |
|--------|------|
| `make install` | venv 생성 + 전체 의존성 설치 |
| `make dev` | **테스트 통과 후** Streamlit 시작 (기본 진입점) |
| `make test` | unit + integration 테스트만 실행 |
| `make test-e2e` | 실제 사이트/LLM E2E 테스트 |

---

## 프로젝트 구조

```
fabric-scraper/
  config.py          # API 키, DB 경로, Gemini 모델 목록
  pipeline.py        # 수집 파이프라인 단일 진입점
  main.py            # CLI (개발·테스트용)
  scraper/
    fetcher.py       # Playwright 페이지 렌더링 + 이미지 추출
    extractor.py     # LLM 원단 정보 추출
    receipt_parser.py# LLM Vision 영수증 상품명 추출
    url_finder.py    # Playwright 검색 + LLM URL 탐색
  db/
    database.py      # SQLite CRUD
  ui/
    app.py           # Streamlit UI
  tests/             # 테스트 (위 구조 참고)
```
