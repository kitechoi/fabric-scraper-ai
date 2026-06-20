"""
_is_logo() 단위 테스트

검증 대상:
  - 로고/배너 키워드가 포함된 URL → True
  - 정상 상품 이미지 URL → False
  - 대소문자 무관 처리
"""
from scraper.fetcher import _is_logo


class TestIsLogo:
    def test_logo_keyword(self):
        assert _is_logo("https://example.com/images/logo.png") is True

    def test_banner_keyword(self):
        assert _is_logo("https://example.com/banner_top.jpg") is True

    def test_all_og_prefix(self):
        assert _is_logo("https://example.com/all_og_main.jpg") is True

    def test_og_logo(self):
        assert _is_logo("https://example.com/og_logo.png") is True

    def test_og_image(self):
        assert _is_logo("https://example.com/og_image.jpg") is True

    def test_default_keyword(self):
        assert _is_logo("https://example.com/default.jpg") is True

    def test_noimage_keyword(self):
        assert _is_logo("https://example.com/noimage.gif") is True

    def test_product_image_not_logo(self):
        assert _is_logo("https://img.kohasid.com/photos/goods/2106/abc.jpg") is False

    def test_goods_path_not_logo(self):
        assert _is_logo("https://example.com/goods/product_123.jpg") is False

    def test_cdn_image_not_logo(self):
        assert _is_logo("https://cdn.example.com/items/fabric_blue.png") is False

    def test_uppercase_url_treated_as_logo(self):
        """대소문자 무관하게 감지"""
        assert _is_logo("https://example.com/LOGO.PNG") is True

    def test_mixed_case_banner(self):
        assert _is_logo("https://example.com/Banner_Main.jpg") is True
