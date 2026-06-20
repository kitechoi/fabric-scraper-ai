"""
FabricInfo Pydantic 모델 단위 테스트

검증 대상:
  - 필수 필드(product_name, url) 누락 시 ValidationError
  - 선택 필드 기본값 None
  - model_dump() 결과가 JSON 직렬화 가능
"""
import json
import pytest
from pydantic import ValidationError
from scraper.extractor import FabricInfo


class TestFabricInfoValid:
    def test_full_fields(self):
        info = FabricInfo(
            product_name="폴리 다후다",
            material="폴리 100%",
            size="148cm",
            price="6500원/m",
            seller="패션스타트",
            purchase_date="2026-06-19",
            image_url="https://img.example.com/a.jpg",
            url="https://fashionstart.net/goods/goods_view.php?goodsNo=1",
        )
        assert info.product_name == "폴리 다후다"
        assert info.seller == "패션스타트"

    def test_optional_fields_default_none(self):
        info = FabricInfo(
            product_name="원단",
            url="https://example.com/item",
        )
        assert info.material is None
        assert info.size is None
        assert info.price is None
        assert info.color is None
        assert info.seller is None
        assert info.purchase_date is None
        assert info.memo is None
        assert info.image_url is None

    def test_color_and_memo_fields(self):
        info = FabricInfo(
            product_name="보드레 스판 공단",
            url="https://fashionstart.net/goods/goods_view.php?goodsNo=1",
            color="화이트",
            memo="2026 봄 컬렉션용",
        )
        assert info.color == "화이트"
        assert info.memo == "2026 봄 컬렉션용"

    def test_model_dump_json_serializable(self):
        info = FabricInfo(product_name="원단", url="https://example.com/item")
        dumped = json.dumps(info.model_dump(), ensure_ascii=False)
        assert "원단" in dumped

    def test_model_copy_with_update(self):
        info = FabricInfo(product_name="원단", url="https://example.com/item")
        updated = info.model_copy(update={"product_name": "수정 원단"})
        assert updated.product_name == "수정 원단"
        assert updated.url == info.url


class TestFabricInfoInvalid:
    def test_missing_product_name_raises(self):
        with pytest.raises(ValidationError):
            FabricInfo(url="https://example.com/item")

    def test_missing_url_raises(self):
        with pytest.raises(ValidationError):
            FabricInfo(product_name="원단")

    def test_empty_args_raises(self):
        with pytest.raises(ValidationError):
            FabricInfo()
