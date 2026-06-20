"""
공통 pytest fixture
- sys.path: 프로젝트 루트(fabric-scraper/)를 자동 추가
- tmp_db:   테스트별 격리 SQLite DB (테스트 후 자동 삭제)
- sample_fabric_info: 이미지 다운로드 없는 FabricInfo 인스턴스
"""
import sys
import os
import pytest

# fabric-scraper/ 를 import 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config  # noqa: E402 (경로 설정 후 import)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """
    테스트용 임시 DB.
    config.DB_PATH를 tmp_path 내 파일로 교체 → 테스트 종료 후 자동 삭제.
    """
    db_file = str(tmp_path / "test_fabric.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    yield db_file


@pytest.fixture
def sample_fabric_info():
    """
    기본 테스트용 FabricInfo.
    image_url=None 으로 설정해 _download_image() 호출을 방지.
    """
    from scraper.extractor import FabricInfo
    return FabricInfo(
        product_name="테스트 원단",
        material="면 100%",
        size="150cm",
        price="8500원/m",
        seller="패션스타트",
        purchase_date="2026-06-19",
        image_url=None,
        url="https://fashionstart.net/goods/goods_view.php?goodsNo=99999",
    )


@pytest.fixture
def fixture_dir():
    """fixtures/ 디렉터리 절대 경로."""
    return os.path.join(os.path.dirname(__file__), "fixtures")
