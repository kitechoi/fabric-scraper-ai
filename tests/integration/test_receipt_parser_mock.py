"""
parse_receipt() integration 테스트 — LLM mock

parse_receipt() 반환 타입: list[dict{"name": str, "color": Optional[str]}]
"""
import pytest
from unittest.mock import patch, MagicMock

# 새 프롬프트에 맞는 color 포함 응답
SAMPLE_RESPONSE = (
    '{"items":['
    '{"name":"48-222 폴리 다후다 안감","color":null},'
    '{"name":"보드레 스판 공단 안감","color":"화이트"}'
    ']}'
)
EMPTY_RESPONSE = '{"items":[]}'
MISSING_NAME_RESPONSE = '{"items":[{"name":"정상 상품","color":"블랙"},{"other":"값"}]}'

FAKE_IMAGE = b"\xff\xd8\xff"  # 최소 JPEG 헤더


def _mock_response(text: str) -> MagicMock:
    m = MagicMock()
    m.text = text
    return m


def _client_error(code: int = 429):
    from google.genai.errors import ClientError
    fake_resp = MagicMock()
    fake_resp.status_code = code
    return ClientError(code, {"error": {"code": code, "message": "quota"}}, fake_resp)


@patch("google.genai.Client")
def test_returns_dict_list(mock_cls):
    """parse_receipt → list[dict{name, color}] 반환"""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(SAMPLE_RESPONSE)

    from scraper.receipt_parser import parse_receipt
    items = parse_receipt(FAKE_IMAGE, mime_type="image/jpeg")
    assert isinstance(items, list)
    assert len(items) == 2
    assert items[0]["name"] == "48-222 폴리 다후다 안감"
    assert items[0]["color"] is None
    assert items[1]["name"] == "보드레 스판 공단 안감"
    assert items[1]["color"] == "화이트"


@patch("google.genai.Client")
def test_empty_items_returns_empty_list(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(EMPTY_RESPONSE)

    from scraper.receipt_parser import parse_receipt
    assert parse_receipt(FAKE_IMAGE) == []


@patch("google.genai.Client")
def test_missing_name_key_skipped(mock_cls):
    """items 내 name 키가 없는 항목은 제외"""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(MISSING_NAME_RESPONSE)

    from scraper.receipt_parser import parse_receipt
    items = parse_receipt(FAKE_IMAGE)
    assert len(items) == 1
    assert items[0]["name"] == "정상 상품"
    assert items[0]["color"] == "블랙"


@patch("google.genai.Client")
@patch("time.sleep")
def test_model_fallback_on_429(mock_sleep, mock_cls):
    """1번째 모델 429 → 2번째 모델 성공"""
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _client_error(429),
        _mock_response(SAMPLE_RESPONSE),
    ]

    from scraper.receipt_parser import parse_receipt
    items = parse_receipt(FAKE_IMAGE)
    assert len(items) == 2
    assert mock_client.models.generate_content.call_count == 2


@patch("google.genai.Client")
@patch("time.sleep")
def test_all_models_fail_raises(mock_sleep, mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = _client_error(429)

    from scraper.receipt_parser import parse_receipt
    with pytest.raises(RuntimeError, match="모든 모델"):
        parse_receipt(FAKE_IMAGE)
