"""
Step 2: Playwright로 URL의 페이지 HTML을 가져와 Markdown으로 변환해 반환한다.

inner_text 대신 html2text를 사용하는 이유:
- inner_text는 취소선(<del>, <s>), 굵기(<b>, <strong>) 등 가격 구분에 필수적인
  HTML 구조 정보를 모두 날려버린다.
- html2text 변환 후 LLM은 ~~8,200원~~ **4,100원** 처럼
  정가/할인가를 문맥적으로 구분할 수 있다.
"""
import re
import asyncio
from typing import Optional
from playwright.async_api import async_playwright
import html2text as _html2text


def _html_to_markdown(html: str) -> str:
    """HTML을 LLM 친화적 Markdown으로 변환.

    전처리: <del>/<s>/<strike> 태그를 html2text 처리 전에 명시적으로 ~~text~~로 치환.
    (html2text가 버전에 따라 del 처리가 불안정해서 선치환으로 보장)
    """
    # 취소선 태그를 ~~text~~로 선치환.
    # DOTALL 제거: 가격 취소선은 항상 인라인(한 줄)이므로 DOTALL 불필요.
    # DOTALL을 쓰면 <s> 뒤 수천 줄짜리 JSP 템플릿 전체를 하나의 ~~...~~로 삼켜버림.
    html = re.sub(
        r'<(?:del|s|strike)([^>]*)>([^<]{0,200})</(?:del|s|strike)>',
        r'~~\2~~',
        html, flags=re.IGNORECASE,
    )
    h = _html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0          # 줄바꿈 없음
    h.bypass_tables = False   # 테이블 구조 유지 (가격표가 table인 경우 있음)
    h.ignore_emphasis = False # **굵기** 유지
    return h.handle(html)

# og:image가 사이트 로고/배너일 가능성이 높은 패턴
_LOGO_KEYWORDS = ("logo", "banner", "all_og_", "og_logo", "og_image", "default", "noimage")

def _is_logo(url: str) -> bool:
    lower = url.lower()
    return any(kw in lower for kw in _LOGO_KEYWORDS)


# 상품 이미지를 가리키는 CSS 셀렉터 (우선순위 순)
_PRODUCT_IMG_SELECTORS = [
    "img#goods_pic",          # sunquilt
    "img#big_img",
    "img#mainImage",
    "img#prdImg",
    "img#zoom_image",
    ".goods_img img:first-child",
    ".product_img img:first-child",
    ".item_image img:first-child",
    ".goods-img img:first-child",
    ".prd-img img:first-child",
    "img.middle",             # fashionstart
]


async def _get_image_url(page) -> Optional[str]:
    """상품 대표 이미지 URL 추출.

    우선순위:
    1. 상품 이미지 전용 CSS 셀렉터 (id/class 기반)
    2. og:image — 로고/배너 패턴이 아닐 때만
    3. 페이지에서 가장 큰 img (로고 패턴 제외)

    모든 선택자는 query_selector 사용 → 요소 없으면 즉시 None, 타임아웃 없음.
    상대 URL은 브라우저가 .src 프로퍼티로 절대 URL 반환.
    """
    # 1순위: 상품 이미지 전용 셀렉터
    for selector in _PRODUCT_IMG_SELECTORS:
        el = await page.query_selector(selector)
        if not el:
            continue
        # element.src 프로퍼티로 절대 URL 획득 (상대 URL 자동 변환)
        src = await el.evaluate("el => el.src")
        if src and not _is_logo(src):
            print(f"     상품 이미지 발견 [{selector}]: {src}")
            return src

    # 2순위: og:image (로고 패턴 제외)
    el = await page.query_selector('meta[property="og:image"]')
    if el:
        og = await el.get_attribute("content")
        if og and not _is_logo(og):
            print(f"     og:image 발견: {og}")
            return og
        elif og:
            print(f"     og:image 로고로 판단, 건너뜀: {og}")

    # 3순위: 같은 도메인 + DOM 앞쪽 + 최소 크기 200px
    src = await page.evaluate("""() => {
        const LOGO_KW = ["logo", "banner", "all_og_", "og_logo", "og_image", "default", "noimage"];
        const isLogo  = src => LOGO_KW.some(kw => src.toLowerCase().includes(kw));
        const origin  = window.location.origin;

        const isSameOrigin = src => {
            try { return new URL(src).origin === origin; }
            catch { return false; }
        };

        const imgs = Array.from(document.querySelectorAll('img[src]'));
        const candidate = imgs.find(i =>
            isSameOrigin(i.src) &&
            !isLogo(i.src) &&
            (i.naturalWidth >= 200 || i.width >= 200)
        );
        return candidate ? candidate.src : null;
    }""")
    if src:
        print(f"     같은 도메인 첫 번째 img 발견: {src}")
    return src


async def fetch_page(url: str) -> dict:
    """
    Returns:
        {
            "url":        str,
            "text":       str,       # 페이지 전체 텍스트 (innerText)
            "image_url":  str|None,  # 대표 상품 이미지 URL
            "screenshot": bytes,     # 풀페이지 스크린샷 (PNG) — LLM에 전달
        }
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
        except Exception:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        await page.wait_for_timeout(2_000)

        # 본문 영역만 추출 (nav/header/footer 제외) → LLM 노이즈 감소
        # 우선순위 순으로 시도하고, 없으면 전체 페이지 사용
        _CONTENT_SELECTORS = [
            "#goods_detail",          # fashionstart 등 상품 상세 전용 id
            ".goods_detail_area",
            ".goods_info",
            ".product_detail",
            "#product_detail",
            "article",
            "main",
            "#container",
            "#content",
            ".content",
        ]
        html = None
        for sel in _CONTENT_SELECTORS:
            el = await page.query_selector(sel)
            if el:
                html = await el.inner_html()
                print(f"     본문 영역 추출 [{sel}]: {len(html)}자")
                break
        if not html:
            html = await page.content()
            print(f"     본문 영역 없음, 전체 페이지 사용: {len(html)}자")

        text      = _html_to_markdown(html)
        image_url = await _get_image_url(page)
        screenshot = await page.screenshot(full_page=False)  # 뷰포트만 (LLM 미전달)

        await browser.close()

    return {
        "url":        url,
        "text":       text,
        "image_url":  image_url,
        "screenshot": screenshot,
    }


def fetch(url: str) -> dict:
    """동기 래퍼 — main.py·Streamlit에서 편하게 호출."""
    return asyncio.run(fetch_page(url))


# ── 단독 실행 테스트 ─────────────────────────────────────────
if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    result = fetch(target)

    print(f"\n[URL] {result['url']}")
    print(f"[텍스트 길이] {len(result['text'])} 자")
    print(f"[대표 이미지] {result['image_url']}")
    print("\n[텍스트 앞 500자]")
    print(result["text"][:500])
    print("\n[스크린샷] PNG, {:.1f} KB".format(len(result["screenshot"]) / 1024))
