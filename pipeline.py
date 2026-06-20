"""
파이프라인 레이어 — UI / CLI가 호출하는 단일 진입점.
중복 체크, fetch, extract, save를 순서대로 조율한다.
"""
from typing import Optional
from scraper.fetcher import fetch
from scraper.extractor import extract, FabricInfo
from db.database import check_exists, save
from db.notion_sync import save_to_notion


class DuplicateURLError(Exception):
    """이미 DB에 존재하는 URL을 재수집하려 할 때 발생."""
    def __init__(self, existing: dict):
        self.existing = existing
        super().__init__(f"이미 저장된 URL입니다 (id={existing['id']})")


class LLMQuotaError(Exception):
    """모든 LLM 모델의 할당량이 소진됐을 때 발생."""
    pass


def collect_fabric_data(
    url: str,
    seller: Optional[str] = None,
    purchase_date: Optional[str] = None,
    color: Optional[str] = None,
    force: bool = False,
) -> tuple[FabricInfo, int]:
    """
    전체 파이프라인 실행.

    Args:
        url:           수집할 상품 URL
        seller:        판매처 (사용자 입력)
        purchase_date: 구입일 YYYY-MM-DD (사용자 입력)
        color:         색상/옵션 (영수증 파싱 결과. 제공 시 LLM 추출값보다 우선 적용)
        force:         True이면 중복 체크 건너뛰고 재수집

    Returns:
        (FabricInfo, row_id)

    Raises:
        DuplicateURLError: force=False이고 URL이 이미 DB에 있을 때
    """
    if not force:
        existing = check_exists(url)
        if existing:
            raise DuplicateURLError(existing)

    page = fetch(url)
    try:
        info = extract(page["text"], url, image_url=page["image_url"])
    except RuntimeError as e:
        if "할당량" in str(e) or "모든 모델" in str(e):
            raise LLMQuotaError(str(e)) from e
        raise

    # 사용자/영수증 입력값 주입
    info.seller = seller
    info.purchase_date = purchase_date
    if color is not None:           # 영수증 색상이 LLM 페이지 추출보다 우선
        info.color = color
    # memo는 항상 null (사용자가 편집 화면에서 직접 입력)

    # 1순위: SQLite 저장 (실패하면 즉시 에러 전파)
    row_id = save(info)

    # 2순위: Notion 저장 (실패해도 SQLite는 유지 — 경고만 출력)
    save_to_notion(info, sqlite_id=row_id)

    return info, row_id
