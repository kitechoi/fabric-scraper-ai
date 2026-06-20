"""
collect_fabric_data() integration 테스트 — 모든 외부 의존성 mock

pipeline.py 가 import 한 fetch / extract / save / check_exists 를
pipeline 모듈 네임스페이스에서 patch.
실제 네트워크·LLM·DB 호출 없이 파이프라인 분기 전체를 검증한다.
"""
import pytest
from unittest.mock import patch, MagicMock
from scraper.extractor import FabricInfo
from pipeline import collect_fabric_data, DuplicateURLError, LLMQuotaError

TEST_URL = "https://fashionstart.net/goods/goods_view.php?goodsNo=12345"

EXISTING_ROW = {
    "id": 1,
    "product_name": "기존 원단",
    "url": TEST_URL,
    "created_at": "2026-06-01 10:00:00",
}

FAKE_PAGE = {
    "url": TEST_URL,
    "text": "원단 상품 페이지 텍스트",
    "image_url": "https://img.example.com/fabric.jpg",
    "screenshot": b"",
}

FAKE_INFO = FabricInfo(
    product_name="폴리 다후다",
    material="폴리 100%",
    size="148cm",
    price="6500원/m",
    url=TEST_URL,
)


@patch("pipeline.save", return_value=1)
@patch("pipeline.extract", return_value=FAKE_INFO)
@patch("pipeline.fetch", return_value=FAKE_PAGE)
@patch("pipeline.check_exists", return_value=None)
def test_normal_flow(mock_check, mock_fetch, mock_extract, mock_save):
    info, row_id = collect_fabric_data(TEST_URL, seller="패션스타트", purchase_date="2026-06-19")

    assert info.product_name == "폴리 다후다"
    assert row_id == 1
    mock_check.assert_called_once_with(TEST_URL)
    mock_fetch.assert_called_once_with(TEST_URL)
    mock_save.assert_called_once()


@patch("pipeline.fetch")
@patch("pipeline.check_exists", return_value=EXISTING_ROW)
def test_duplicate_raises_without_force(mock_check, mock_fetch):
    """중복 URL + force=False → DuplicateURLError, fetch 미호출"""
    with pytest.raises(DuplicateURLError) as exc_info:
        collect_fabric_data(TEST_URL)

    assert exc_info.value.existing["id"] == 1
    mock_fetch.assert_not_called()  # 페이지 로드 자체를 하지 않음


@patch("pipeline.save", return_value=2)
@patch("pipeline.extract", return_value=FAKE_INFO)
@patch("pipeline.fetch", return_value=FAKE_PAGE)
@patch("pipeline.check_exists", return_value=EXISTING_ROW)
def test_duplicate_skipped_with_force(mock_check, mock_fetch, mock_extract, mock_save):
    """중복 URL + force=True → check_exists 건너뛰고 재수집"""
    info, row_id = collect_fabric_data(TEST_URL, force=True)

    assert info.product_name == "폴리 다후다"
    mock_fetch.assert_called_once()  # 페이지 로드 실행됨


@patch("pipeline.save", return_value=1)
@patch("pipeline.extract", return_value=FAKE_INFO)
@patch("pipeline.fetch", return_value=FAKE_PAGE)
@patch("pipeline.check_exists", return_value=None)
def test_seller_injected_into_info(mock_check, mock_fetch, mock_extract, mock_save):
    """seller, purchase_date 가 info에 주입됨 (LLM 추출 아님)"""
    info, _ = collect_fabric_data(TEST_URL, seller="코튼빌", purchase_date="2026-06-19")

    assert info.seller == "코튼빌"
    assert info.purchase_date == "2026-06-19"


@patch("pipeline.save", return_value=1)
@patch("pipeline.extract", return_value=FAKE_INFO)
@patch("pipeline.fetch", return_value=FAKE_PAGE)
@patch("pipeline.check_exists", return_value=None)
def test_color_override_applied(mock_check, mock_fetch, mock_extract, mock_save):
    """영수증에서 추출한 color가 LLM 추출값보다 우선 적용됨"""
    info, _ = collect_fabric_data(TEST_URL, color="화이트")

    assert info.color == "화이트"


@patch("pipeline.save", return_value=1)
@patch("pipeline.fetch", return_value=FAKE_PAGE)
@patch("pipeline.check_exists", return_value=None)
def test_color_none_keeps_llm_extracted(mock_check, mock_fetch, mock_save):
    """color 파라미터가 None이면 LLM 추출값(info.color)을 그대로 유지"""
    llm_info = FAKE_INFO.model_copy(update={"color": "베이지"})
    with patch("pipeline.extract", return_value=llm_info):
        info, _ = collect_fabric_data(TEST_URL, color=None)

    assert info.color == "베이지"


@patch("pipeline.fetch", return_value=FAKE_PAGE)
@patch("pipeline.check_exists", return_value=None)
def test_llm_quota_error_converted(mock_check, mock_fetch):
    """extract()가 '모든 모델 시도' RuntimeError → LLMQuotaError 변환"""
    with patch("pipeline.extract", side_effect=RuntimeError("Gemini 호출 실패 (모든 모델 시도): ...")):
        with pytest.raises(LLMQuotaError):
            collect_fabric_data(TEST_URL)


@patch("pipeline.fetch", return_value=FAKE_PAGE)
@patch("pipeline.check_exists", return_value=None)
def test_non_quota_runtime_error_propagates(mock_check, mock_fetch):
    """할당량 외 RuntimeError는 그대로 전파 (LLMQuotaError 아님)"""
    with patch("pipeline.extract", side_effect=RuntimeError("예상치 못한 오류")):
        with pytest.raises(RuntimeError, match="예상치 못한 오류"):
            collect_fabric_data(TEST_URL)
