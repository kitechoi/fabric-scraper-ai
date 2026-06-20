"""
find_product_url() integration 테스트 — Playwright + LLM mock

_search_and_extract() 를 AsyncMock으로 대체해 Playwright 없이 후보 처리 로직 검증.
_pick_best_url() 의 LLM 호출은 google.genai.Client mock으로 대체.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

CANDIDATE_A = {
    "name": "48-222 폴리 다후다 안감",
    "url": "https://fashionstart.net/goods/goods_view.php?goodsNo=12345",
}
CANDIDATE_B = {
    "name": "48-222 다후다 (화이트)",
    "url": "https://fashionstart.net/goods/goods_view.php?goodsNo=12346",
}

LLM_PICK_A = '{"url": "' + CANDIDATE_A["url"] + '", "reason": "코드 일치"}'


def _mock_llm_response(text: str) -> MagicMock:
    m = MagicMock()
    m.text = text
    return m


def _client_error(code: int = 429):
    from google.genai.errors import ClientError
    fake_resp = MagicMock()
    fake_resp.status_code = code
    return ClientError(code, {"error": {"code": code, "message": "quota"}}, fake_resp)


@patch("scraper.url_finder._search_and_extract", new_callable=AsyncMock)
def test_single_candidate_returned_directly(mock_search):
    """후보 1건 → LLM 없이 바로 반환"""
    mock_search.return_value = [CANDIDATE_A]

    from scraper.url_finder import find_product_url
    result = find_product_url("48-222 원단", "https://fashionstart.net")
    assert result == CANDIDATE_A["url"]


@patch("scraper.url_finder._search_and_extract", new_callable=AsyncMock)
def test_no_candidates_returns_none(mock_search):
    mock_search.return_value = []

    from scraper.url_finder import find_product_url
    result = find_product_url("없는상품", "https://fashionstart.net")
    assert result is None


@patch("google.genai.Client")
@patch("scraper.url_finder._search_and_extract", new_callable=AsyncMock)
def test_multi_candidates_llm_picks(mock_search, mock_cls):
    """후보 2건 → LLM이 선택"""
    mock_search.return_value = [CANDIDATE_A, CANDIDATE_B]
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_llm_response(LLM_PICK_A)

    from scraper.url_finder import find_product_url
    result = find_product_url("48-222 {Basic} 폴리 다후다 안감 15종", "https://fashionstart.net")
    assert result == CANDIDATE_A["url"]


@patch("google.genai.Client")
@patch("scraper.url_finder._search_and_extract", new_callable=AsyncMock)
def test_llm_fail_fallback_to_first_candidate(mock_search, mock_cls):
    """LLM 실패해도 후보의 첫 번째 항목을 fallback으로 반환"""
    mock_search.return_value = [CANDIDATE_A, CANDIDATE_B]
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = _client_error(429)

    from scraper.url_finder import find_product_url
    result = find_product_url("48-222 원단", "https://fashionstart.net")
    assert result == CANDIDATE_A["url"]  # 첫 번째 후보 fallback


@patch("scraper.url_finder._search_and_extract", new_callable=AsyncMock)
def test_search_query_uses_product_code(mock_search):
    """Playwright 검색 시 상품명 전체가 아닌 코드만 사용하는지 확인"""
    mock_search.return_value = [CANDIDATE_A]

    from scraper.url_finder import find_product_url
    find_product_url("48-222 {Basic} 폴리 다후다 안감 15종", "https://fashionstart.net")

    # _search_and_extract 첫 번째 인자가 상품명, 두 번째가 seller_url
    call_args = mock_search.call_args
    # find_product_url 내부에서 _make_search_query 적용 후 전달됨
    # asyncio.run(_search_and_extract(product_name, seller_url)) 로 호출되므로
    # 첫 번째 positional arg 확인
    passed_query = call_args.args[0]
    assert passed_query == "48-222"  # 코드만 추출됨
    assert "{Basic}" not in passed_query
