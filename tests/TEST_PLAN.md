# 테스트 계획서

## 구조

```
tests/
  conftest.py               # 공통 fixture
  unit/
    test_url_finder_query.py
    test_fetcher_utils.py
    test_clean_json.py
    test_db_crud.py
    test_fabric_info_model.py
    test_exceptions.py
  integration/
    test_extractor_mock.py
    test_receipt_parser_mock.py
    test_url_finder_mock.py
    test_pipeline_mock.py
  e2e/
    test_sites_fetch.py
    test_sites_url_finder.py
    test_pipeline_full.py
    test_receipt_full.py
  fixtures/
    sample_receipt.jpg        # 실제 주문내역 캡처 이미지 (수동 추가 필요)
    fashionstart_page.txt     # 저장해둔 상품 페이지 텍스트 (extractor 단위용)
```

실행 방법:
```bash
pytest tests/unit tests/integration          # 빠른 테스트만 (항상)
pytest tests/e2e -m e2e                      # 느린 테스트 (수동/CI)
pytest tests/ -v --tb=short                  # 전체
```

---

## 공통 설정

### conftest.py

```python
import pytest, os, config

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """테스트용 임시 DB — 테스트 종료 후 자동 삭제."""
    db_file = str(tmp_path / "test_fabric.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    from db import database
    database.init_db()          # 테이블 생성
    yield db_file

@pytest.fixture
def sample_fabric_info():
    from scraper.extractor import FabricInfo
    return FabricInfo(
        product_name="테스트 원단",
        material="면 100%",
        size="150cm",
        price="8500원/m",
        seller="패션스타트",
        purchase_date="2026-06-19",
        image_url="https://example.com/img.jpg",
        url="https://fashionstart.net/goods/goods_view.php?goodsNo=99999",
    )

@pytest.fixture
def fixture_dir():
    return os.path.join(os.path.dirname(__file__), "fixtures")
```

### pytest.ini (또는 pyproject.toml)

```ini
[pytest]
markers =
    e2e: 실제 네트워크/LLM 호출 (느림)
```

---

## 1. Unit 테스트

외부 의존성 없음. 전체 수백 ms 이내 완료.

---

### test_url_finder_query.py

**대상**: `scraper/url_finder.py` — `_make_search_query()`

| 테스트명 | 입력 | 기대 출력 | 검증 |
|---------|------|---------|------|
| `test_extracts_product_code_numeric` | `'48-222 {Basic} 폴리 다후다 안감 15종'` | `'48-222'` | `==` |
| `test_extracts_product_code_leading_alpha` | `'A1-234 원단명'` | `'A1-234'` | `==` |
| `test_code_takes_priority_over_keywords` | `'70-087 {한정특가} 보드레 스판 공단'` | `'70-087'` | `==` |
| `test_fallback_strips_braces` | `'폴리 다후다 안감 {베이지}'` | `'폴리 다후다 안감 베이지'` | `==` |
| `test_fallback_strips_brackets` | `'[한정특가] 코튼 원단'` | `'한정특가 코튼 원단'` | `in result` (괄호 없음) |
| `test_fallback_strips_quantity` | `'폴리 안감 15종'` | 결과에 `'15종'` 없음 | `not in` |
| `test_fallback_collapses_whitespace` | `'폴리  다후다   안감'` | 연속 공백 없음 | `'  ' not in` |

구현 방식:
```python
from scraper.url_finder import _make_search_query

def test_extracts_product_code_numeric():
    assert _make_search_query("48-222 {Basic} 폴리 다후다 안감 15종") == "48-222"
```

---

### test_fetcher_utils.py

**대상**: `scraper/fetcher.py` — `_is_logo()`

| 테스트명 | 입력 URL | 기대 결과 |
|---------|---------|---------|
| `test_logo_keyword` | `.../logo.png` | `True` |
| `test_banner_keyword` | `.../banner_top.jpg` | `True` |
| `test_all_og_prefix` | `.../all_og_main.jpg` | `True` |
| `test_og_logo` | `.../og_logo.png` | `True` |
| `test_noimage` | `.../noimage.gif` | `True` |
| `test_product_image` | `.../goods/product_123.jpg` | `False` |
| `test_cdn_image` | `https://img.kohasid.com/photos/goods/2106/abc.jpg` | `False` |
| `test_uppercase_url` | `.../LOGO.PNG` | `True` (대소문자 무관) |

---

### test_clean_json.py

**대상**: `scraper/receipt_parser.py` — `_clean_json()`

| 테스트명 | 입력 | 기대 출력 |
|---------|------|---------|
| `test_plain_json` | `'{"items": []}'` | `'{"items": []}'` |
| `test_strips_markdown_fence` | ` ```json\n{"items":[]}\n``` ` | `'{"items":[]}'` |
| `test_strips_fence_without_lang` | ` ```\n{"items":[]}\n``` ` | `'{"items":[]}'` |
| `test_strips_leading_whitespace` | `'  {"items": []}  '` | `'{"items": []}'` |

---

### test_db_crud.py

**대상**: `db/database.py` — `save / list_all / check_exists / delete / update`

각 테스트는 `tmp_db` fixture 사용 (격리된 임시 DB).

| 테스트명 | 시나리오 | 검증 |
|---------|---------|------|
| `test_save_returns_int_id` | FabricInfo 저장 | 반환값이 `int` |
| `test_save_and_list` | 2건 저장 후 `list_all()` | 길이 2, 순서 최신순 |
| `test_check_exists_found` | 저장 후 같은 URL로 조회 | `dict` 반환, `id` 포함 |
| `test_check_exists_not_found` | 저장하지 않은 URL 조회 | `None` 반환 |
| `test_duplicate_url_raises` | 같은 URL 두 번 `save()` | `sqlite3.IntegrityError` 또는 upsert 동작 확인 |
| `test_delete_removes_row` | 저장 후 `delete(id)` | `list_all()` 빈 리스트 |
| `test_delete_nonexistent_is_noop` | 없는 id `delete(999)` | 오류 없이 통과 |
| `test_update_allowed_fields` | `product_name`, `seller` 수정 | `list_all()[0]` 값 변경 확인 |
| `test_update_disallowed_field` | `url` 수정 시도 | 무시되거나 `ValueError` |

---

### test_fabric_info_model.py

**대상**: `scraper/extractor.py` — `FabricInfo` Pydantic 모델

| 테스트명 | 시나리오 | 검증 |
|---------|---------|------|
| `test_valid_full` | 모든 필드 입력 | 인스턴스 생성 성공 |
| `test_optional_fields_default_none` | `product_name`, `url`만 입력 | 나머지 필드 `None` |
| `test_missing_required_product_name` | `url`만 입력, `product_name` 누락 | `ValidationError` |
| `test_missing_required_url` | `product_name`만 입력, `url` 누락 | `ValidationError` |
| `test_model_dump_serializable` | `model_dump()` 후 `json.dumps()` | 오류 없이 JSON 직렬화 |

---

### test_exceptions.py

**대상**: `pipeline.py` — `DuplicateURLError`, `LLMQuotaError`

| 테스트명 | 검증 |
|---------|------|
| `test_duplicate_error_has_existing` | `.existing` 속성이 전달한 dict와 동일 |
| `test_duplicate_error_message` | `str(e)`에 id 포함 |
| `test_quota_error_is_exception` | `LLMQuotaError`가 `Exception` 서브클래스 |

---

## 2. Integration 테스트 (Mock)

LLM API와 Playwright를 mock으로 대체. 네트워크 호출 없음.

---

### test_extractor_mock.py

**대상**: `scraper/extractor.py` — `extract()` + `_extract_gemini()`

Mock 대상: `google.genai.Client.models.generate_content`

**픽스처**:
```python
SAMPLE_LLM_RESPONSE = '{"product_name":"폴리 다후다","material":"폴리 100%","size":"148cm","price":"6500원/m","url":"https://..."}'
```

| 테스트명 | mock 설정 | 검증 |
|---------|---------|------|
| `test_extract_returns_fabric_info` | 1회 호출 → 정상 JSON 반환 | `FabricInfo` 인스턴스, `product_name` 일치 |
| `test_extract_injects_image_url` | 정상 응답 | `info.image_url` == 전달한 값 |
| `test_extract_strips_seller_from_llm` | LLM 응답에 `seller` 포함 | `info.seller == None` (pipeline에서 주입) |
| `test_extract_model_fallback_on_429` | 1번째 호출 → `ClientError(429)`, 2번째 → 정상 | `FabricInfo` 반환, 2번 호출됨 확인 |
| `test_extract_retry_on_503` | 1,2번째 → `ServerError(503)`, 3번째 → 정상 | 3회 호출 후 성공 |
| `test_extract_all_models_fail_raises` | 모든 호출 → `ClientError(429)` | `RuntimeError` 발생 |
| `test_extract_strips_markdown_fence` | LLM이 ` ```json{...}``` ` 반환 | 파싱 성공 |

---

### test_receipt_parser_mock.py

**대상**: `scraper/receipt_parser.py` — `parse_receipt()`

Mock 대상: `google.genai.Client.models.generate_content`

**픽스처**:
```python
SAMPLE_RECEIPT_RESPONSE = '{"items":[{"name":"48-222 폴리 다후다"},{"name":"70-087 보드레 스판"}]}'
EMPTY_RECEIPT_RESPONSE  = '{"items":[]}'
```

| 테스트명 | mock 설정 | 검증 |
|---------|---------|------|
| `test_parse_returns_name_list` | 정상 응답 | `list[str]` 길이 2, 상품명 일치 |
| `test_parse_empty_items` | `items: []` | 빈 리스트 반환 |
| `test_parse_model_fallback_on_429` | 1번째 → 429, 2번째 → 정상 | 이름 리스트 반환 |
| `test_parse_ignores_missing_name_key` | `items`에 `{}` 포함 | 해당 항목 제외하고 나머지 반환 |

---

### test_url_finder_mock.py

**대상**: `scraper/url_finder.py` — `find_product_url()`

Mock 대상: `playwright.async_api.async_playwright` (AsyncMock), LLM

**픽스처**:
```python
CANDIDATE_1 = [{"name": "48-222 폴리 다후다 안감", "url": "https://fashionstart.net/goods/goods_view.php?goodsNo=12345"}]
CANDIDATE_2 = CANDIDATE_1 + [{"name": "48-222 다후다 (화이트)", "url": "https://fashionstart.net/goods/goods_view.php?goodsNo=12346"}]
```

| 테스트명 | mock 설정 | 검증 |
|---------|---------|------|
| `test_single_candidate_no_llm` | Playwright → 후보 1건 | URL 반환, LLM 미호출 |
| `test_multi_candidate_llm_picks` | Playwright → 후보 2건, LLM → 첫 번째 URL | 첫 번째 URL 반환 |
| `test_no_candidates_returns_none` | Playwright → 후보 0건 | `None` 반환 |
| `test_no_search_input_returns_none` | 검색창 없음 | `None` 반환 |
| `test_llm_fail_fallback_to_first` | 후보 2건, LLM → 예외 | 첫 번째 URL fallback 반환 |
| `test_query_uses_product_code` | 상품명 `'48-222 원단'` | `search_el.fill()` 호출 인자 `'48-222'` 확인 |

---

### test_pipeline_mock.py

**대상**: `pipeline.py` — `collect_fabric_data()`

Mock 대상: `pipeline.fetch`, `pipeline.extract`, `pipeline.save`, `pipeline.check_exists`

| 테스트명 | mock 설정 | 검증 |
|---------|---------|------|
| `test_normal_flow` | `check_exists→None`, `fetch→페이지dict`, `extract→FabricInfo`, `save→1` | `(FabricInfo, 1)` 반환 |
| `test_duplicate_raises_without_force` | `check_exists→기존row dict` | `DuplicateURLError` 발생, `fetch` 미호출 |
| `test_duplicate_skipped_with_force` | `check_exists→기존row dict`, `force=True` | 정상 수집, `fetch` 호출됨 |
| `test_seller_injected` | `seller='패션스타트'` 전달 | `info.seller == '패션스타트'` |
| `test_purchase_date_injected` | `purchase_date='2026-06-19'` 전달 | `info.purchase_date == '2026-06-19'` |
| `test_quota_error_propagates` | `extract` → `RuntimeError('모든 모델 시도')` | `LLMQuotaError` 변환되어 발생 |

---

## 3. E2E 테스트 (실제 네트워크 + LLM)

`@pytest.mark.e2e` 마크. `pytest -m e2e`로만 실행.  
각 테스트는 `tmp_db` fixture로 테스트 DB 격리.  
실패 허용 기준: 사이트 구조 변경 시 재검토.

---

### test_sites_fetch.py

**대상**: `scraper/fetcher.py` — 각 쇼핑몰 이미지 추출

각 사이트의 검증용 고정 URL을 `conftest.py` 또는 상수로 정의.

| 테스트명 | URL | 검증 |
|---------|-----|------|
| `test_fashionstart_image` | 패션스타트 특정 상품 | `image_url`이 `img.kohasid.com` 포함 |
| `test_1000gage_image` | 천가게 특정 상품 | `image_url` not None, not logo |
| `test_sunquilt_image` | 썬퀼트 특정 상품 | `image_url` not None (`#goods_pic` selector) |
| `test_cottonvill_image` | 코튼빌 특정 상품 | `image_url`이 동일 도메인, not logo |
| `test_fetch_returns_text` | 패션스타트 임의 상품 | `text` 길이 > 100 |

구현 방식:
```python
@pytest.mark.e2e
def test_fashionstart_image():
    from scraper.fetcher import fetch
    result = fetch("https://fashionstart.net/goods/goods_view.php?goodsNo=XXXXX")
    assert result["image_url"] is not None
    assert "kohasid.com" in result["image_url"]
    assert not _is_logo(result["image_url"])
```

---

### test_sites_url_finder.py

**대상**: `scraper/url_finder.py` — 사이트별 URL 탐색

| 테스트명 | 상품코드 | 사이트 | 검증 |
|---------|---------|-------|------|
| `test_fashionstart_url_finder` | `'48-222'` | fashionstart.net | `goodsNo=` 포함 URL 반환 |
| `test_1000gage_url_finder` | 샘플 코드 | 1000gage.co.kr | `branduid=` 포함 URL 반환 |
| `test_sunquilt_url_finder` | 샘플 코드 | sunquilt.com | URL not None |
| `test_cottonvill_url_finder` | 샘플 코드 | cottonvill.com | URL not None |
| `test_url_finder_no_match` | `'XXXXX-없는코드'` | fashionstart.net | `None` 반환 또는 fallback |

---

### test_pipeline_full.py

**대상**: `pipeline.py` — 실제 수집 → DB 저장

| 테스트명 | 시나리오 | 검증 |
|---------|---------|------|
| `test_collect_fashionstart` | 패션스타트 URL 1개 | `product_name` not empty, DB에 저장됨 |
| `test_collect_1000gage` | 천가게 URL 1개 | 동일 |
| `test_collect_sunquilt` | 썬퀼트 URL 1개 | 동일 |
| `test_collect_cottonvill` | 코튼빌 URL 1개 | 동일 |
| `test_collect_with_seller_date` | URL + seller + date | DB 저장 row에 seller, purchase_date 일치 |
| `test_collect_duplicate_raises` | 같은 URL 두 번 | 두 번째 호출에서 `DuplicateURLError` |
| `test_collect_batch_3urls` | URL 3개 루프 | 3건 모두 DB 저장, `list_all()` 길이 3 |
| `test_collect_batch_with_duplicate` | URL 3개 중 1개 중복 | 중복은 `DuplicateURLError`, 나머지 2건 저장 |

---

### test_receipt_full.py

**대상**: `receipt_parser.py` → `url_finder.py` 연계

전제: `fixtures/sample_receipt.jpg` 존재 (테스트 실행 전 수동 추가 필요)

| 테스트명 | 시나리오 | 검증 |
|---------|---------|------|
| `test_parse_receipt_returns_names` | 영수증 이미지 → `parse_receipt()` | `list[str]`, 길이 > 0 |
| `test_parsed_names_are_nonempty` | 추출된 상품명 각 항목 | `len(name) > 2` |
| `test_find_url_from_parsed_name` | 추출된 첫 번째 상품명 → `find_product_url()` | URL not None 또는 None (사이트 구조 의존) |

---

## 구현 우선순위

| 순위 | 대상 | 이유 |
|------|------|------|
| 1 | `unit/test_db_crud.py` | 데이터 무결성 핵심, 구현 쉬움 |
| 2 | `unit/test_url_finder_query.py` | 버그 재현 경험 있음, 순수 함수 |
| 3 | `integration/test_pipeline_mock.py` | 파이프라인 분기 전체 커버 |
| 4 | `integration/test_extractor_mock.py` | LLM 폴백 로직 검증 |
| 5 | `e2e/test_pipeline_full.py` | 실제 사이트 회귀 테스트 |
| 6 | 나머지 unit, integration | 순서 무관 |
| 7 | `e2e/test_receipt_full.py` | fixture 이미지 필요 |
