"""
extract() integration 테스트 — LLM mock

google.genai.Client 를 mock으로 대체해 실제 API 호출 없이
모델 폴백 / 재시도 / JSON 파싱 등 분기 로직을 검증한다.
"""
import pytest
from unittest.mock import patch, MagicMock

SAMPLE_JSON = (
    '{"product_name":"폴리 다후다","material":"폴리 100%",'
    '"size":"148cm","price":"6500원/m","url":"https://example.com"}'
)
SAMPLE_JSON_WITH_SELLER = (
    '{"product_name":"폴리 다후다","material":"폴리 100%",'
    '"size":"148cm","price":"6500원/m","url":"https://example.com","seller":"패션스타트"}'
)
FENCED_JSON = f"```json\n{SAMPLE_JSON}\n```"


def _mock_response(text: str) -> MagicMock:
    m = MagicMock()
    m.text = text
    return m


def _client_error(code: int = 429):
    """ClientError 인스턴스를 최소 인자로 생성."""
    from google.genai.errors import ClientError
    fake_resp = MagicMock()
    fake_resp.status_code = code
    return ClientError(code, {"error": {"code": code, "message": "quota"}}, fake_resp)


def _server_error():
    from google.genai.errors import ServerError
    fake_resp = MagicMock()
    fake_resp.status_code = 503
    return ServerError(503, {"error": {"code": 503, "message": "overload"}}, fake_resp)


@patch("google.genai.Client")
def test_returns_fabric_info(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(SAMPLE_JSON)

    from scraper.extractor import extract
    info = extract("페이지 텍스트", "https://example.com", image_url=None)
    assert info.product_name == "폴리 다후다"
    assert info.material == "폴리 100%"


@patch("google.genai.Client")
def test_injects_image_url(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(SAMPLE_JSON)

    from scraper.extractor import extract
    info = extract("텍스트", "https://example.com", image_url="https://img.com/test.jpg")
    assert info.image_url == "https://img.com/test.jpg"


@patch("google.genai.Client")
def test_strips_seller_from_llm_output(mock_cls):
    """LLM 응답에 seller 가 있어도 None — pipeline에서 주입하는 필드"""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(SAMPLE_JSON_WITH_SELLER)

    from scraper.extractor import extract
    info = extract("텍스트", "https://example.com")
    assert info.seller is None


@patch("google.genai.Client")
def test_strips_markdown_fence(mock_cls):
    """LLM이 ```json ... ``` 형태로 응답해도 파싱 성공"""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(FENCED_JSON)

    from scraper.extractor import extract
    info = extract("텍스트", "https://example.com")
    assert info.product_name == "폴리 다후다"


@patch("google.genai.Client")
@patch("time.sleep")  # 재시도 대기 제거
def test_model_fallback_on_429(mock_sleep, mock_cls):
    """1번째 모델 429 → 2번째 모델 성공"""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _client_error(429),        # 1번째 모델 실패
        _mock_response(SAMPLE_JSON),  # 2번째 모델 성공
    ]

    from scraper.extractor import extract
    info = extract("텍스트", "https://example.com")
    assert info.product_name == "폴리 다후다"
    assert mock_client.models.generate_content.call_count == 2


@patch("google.genai.Client")
@patch("time.sleep")
def test_retry_on_503(mock_sleep, mock_cls):
    """ServerError(503) → 동일 모델 재시도 → 성공"""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _server_error(),            # attempt 0 실패
        _server_error(),            # attempt 1 실패
        _mock_response(SAMPLE_JSON),  # attempt 2 성공
    ]

    from scraper.extractor import extract
    info = extract("텍스트", "https://example.com")
    assert info.product_name == "폴리 다후다"


@patch("google.genai.Client")
@patch("time.sleep")
def test_all_models_exhausted_raises(mock_sleep, mock_cls):
    """모든 모델 429 → RuntimeError"""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = _client_error(429)

    from scraper.extractor import extract
    with pytest.raises(RuntimeError, match="모든 모델"):
        extract("텍스트", "https://example.com")
