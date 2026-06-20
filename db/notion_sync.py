"""
Notion 동기화 모듈 — 🗄️ DB 내 원단/부자재 창고 연동.

SQLite 저장 이후 보조 저장소로 호출된다.
NOTION_API_KEY가 없으면 조용히 skip.

기존 DB 필드 매핑:
  이름        ← product_name (title)
  품번        ← product_name에서 정규식으로 추출한 상품코드
  소재        ← material
  사이즈      ← size
  색상        ← color
  판매처      ← seller (SELECT 옵션과 정확히 일치해야 함)
  구매일      ← purchase_date
  메모        ← memo
  상품URL     ← url  (새로 추가된 필드)
  판매가      ← price (텍스트, 단위 포함)  (새로 추가된 필드)
  이미지URL   ← image_url  (새로 추가된 필드)
  자재 유형   ← 항상 ["원단"] (스크래퍼는 원단만 수집)
"""
from __future__ import annotations
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from scraper.extractor import FabricInfo

# 기존 DB의 판매처 SELECT 옵션 — 정확히 일치해야 한다
_VALID_SELLERS = {"패션스타트", "체크앤플라워", "리본리본", "코튼빌", "썬퀼트", "천가게"}

# 상품명에서 품번 추출 (예: "48-222", "70-157", "A12-345")
_PRODUCT_CODE_RE = re.compile(r'\b[A-Za-z]?\d{2,4}-\d{3,5}\b')


def _extract_code(product_name: str) -> Optional[str]:
    m = _PRODUCT_CODE_RE.search(product_name)
    return m.group() if m else None


def _seller_option(seller: Optional[str]) -> Optional[str]:
    if not seller:
        return None
    return seller if seller in _VALID_SELLERS else None  # 없는 옵션은 null


def save_to_notion(info: "FabricInfo", sqlite_id: int) -> Optional[str]:
    """
    FabricInfo를 Notion 원단/부자재 창고 DB에 저장한다.

    Returns:
        생성된 Notion 페이지 URL (성공), 또는 None (API 키 없음 / 실패)

    절대 raise하지 않음 — 실패 시 경고 출력 후 None 반환.
    """
    import config
    if not config.NOTION_API_KEY:
        return None

    try:
        from notion_client import Client
        notion = Client(auth=config.NOTION_API_KEY)

        properties: dict = {
            "이름": {
                "title": [{"text": {"content": info.product_name or ""}}]
            },
            # 스크래퍼는 원단만 수집
            "자재 유형": {
                "multi_select": [{"name": "원단"}]
            },
        }

        # 품번 — 상품명에서 자동 추출
        code = _extract_code(info.product_name or "")
        if code:
            properties["품번"] = {"rich_text": [{"text": {"content": code}}]}

        if info.material:
            properties["소재"] = {"rich_text": [{"text": {"content": info.material}}]}
        if info.size:
            properties["사이즈"] = {"rich_text": [{"text": {"content": info.size}}]}
        if info.color:
            properties["색상"] = {"rich_text": [{"text": {"content": info.color}}]}
        if info.memo:
            properties["메모"] = {"rich_text": [{"text": {"content": info.memo}}]}
        if info.url:
            properties["상품URL"] = {"url": info.url}
        if info.image_url:
            properties["이미지URL"] = {"url": info.image_url}
        if info.price:
            properties["판매가"] = {"rich_text": [{"text": {"content": info.price}}]}
        if info.purchase_date:
            properties["구매일"] = {"date": {"start": info.purchase_date}}

        seller_opt = _seller_option(info.seller)
        if seller_opt:
            properties["판매처"] = {"select": {"name": seller_opt}}

        page_body: dict = {
            "parent": {"database_id": config.NOTION_DATABASE_ID},
            "properties": properties,
        }
        if info.image_url:
            page_body["cover"] = {"type": "external", "external": {"url": info.image_url}}

        response = notion.pages.create(**page_body)
        page_url = response.get("url", "")
        print(f"     Notion 저장 완료: {page_url}")
        return page_url

    except Exception as e:
        print(f"     ⚠ Notion 저장 실패 (SQLite는 정상 저장됨): {e}")
        return None
