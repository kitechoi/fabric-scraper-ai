"""
상품명 + 판매처 base URL → 상품 URL 탐색.

흐름:
  1. 상품명에서 검색 쿼리 추출 (상품 코드 우선 → 키워드 fallback)
  2. Playwright로 판매처 사이트에서 검색
  3. 결과 페이지에서 상품 링크 후보 추출
  4. LLM이 가장 유사한 링크 선택
"""
import asyncio
import json
import re
from typing import Optional
from playwright.async_api import async_playwright
import config


# 상품 코드 패턴: 숫자-숫자 (예: 48-222, 70-087, A12-345)
_PRODUCT_CODE_RE = re.compile(r'\b[A-Za-z]?\d{2,4}-\d{3,5}\b')


def _make_search_query(product_name: str) -> str:
    """단일 쿼리 반환 (하위 호환·테스트용). 실제 탐색은 _make_search_queries 사용."""
    return _make_search_queries(product_name)[0]


def _make_search_queries(product_name: str) -> list[str]:
    """
    검색에 시도할 쿼리 목록을 우선순위 순으로 반환한다.

    1. 상품 코드가 있으면 [코드] 만 반환 (가장 정확)
    2. 없으면:
       - 1차: 원본 그대로 (수량 표기만 제거). 괄호 포함.
              "(Basic) 폴리 다후다 안감 15종" → "(Basic) 폴리 다후다 안감"
       - 2차: 괄호 문자 제거 (비전이 괄호 종류를 잘못 인식했을 경우 대비)
              "(Basic) 폴리 다후다 안감" → "Basic 폴리 다후다 안감"
       - 3차↓: 앞 단어를 줄여가며 재시도
    """
    # 1순위: 상품 코드
    m = _PRODUCT_CODE_RE.search(product_name)
    if m:
        return [m.group()]

    def clean(s: str) -> str:
        return re.sub(r'\s+', ' ', s).strip()

    # 1차: 인식된 상품명 그대로
    q1 = clean(product_name)
    queries: list[str] = [q1]

    # 2차: 괄호+내용 통째로 제거 — 비전이 괄호 종류를 오인식했을 경우 대비
    #   "(Basic) 폴리 다후다 안감 15종" → "폴리 다후다 안감 15종"
    q2 = clean(re.sub(r'[\(\[\{【「『<][^\)\]\}】」』>]*[\)\]\}】」』>]', ' ', product_name))
    if q2 and q2 != q1:
        queries.append(q2)

    # 3차↓: q1 기준 앞 단어 축소
    words = q1.split()
    if len(words) > 3:
        queries.append(' '.join(words[:3]))
    if len(words) > 2:
        queries.append(' '.join(words[:2]))

    return queries

# 판매처 홈페이지에서 검색 입력창을 찾기 위한 셀렉터 (우선순위 순)
_SEARCH_INPUT_SELECTORS = [
    'input[name="keyword"]',
    'input[name="search"]',
    'input[name="q"]',
    'input[name="keywords"]',
    'input[type="search"]',
    '#keyword',
    '#search',
    '#searchInput',
    '.search_input input',
    '.search-input input',
]

# 상품 상세 URL 패턴 (각 쇼핑몰 프레임워크별)
_PRODUCT_URL_PATTERNS = [
    "goodsNo=", "branduid=", "gdno=",
    "goods_view", "shopdetail", "shop_goods",
    "itemNo=", "productNo=", "product_id=",
]


def _is_product_url(href: str) -> bool:
    return any(p in href for p in _PRODUCT_URL_PATTERNS)


async def _search_and_extract(query: str, seller_url: str) -> list[dict]:
    """
    판매처 사이트에서 query로 검색 후 후보 상품 목록 반환.
    query는 호출 전에 _make_search_query()로 이미 최적화된 검색어.
    Returns: [{"name": str, "url": str}, ...]
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
            await page.goto(seller_url, wait_until="networkidle", timeout=20_000)
        except Exception:
            await page.goto(seller_url, wait_until="domcontentloaded", timeout=20_000)

        # 검색창 찾기
        search_el = None
        matched_sel = None
        for selector in _SEARCH_INPUT_SELECTORS:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                search_el = el
                matched_sel = selector
                break

        if not search_el:
            print(f"     ✗ 검색창 셀렉터 매칭 실패 (시도: {_SEARCH_INPUT_SELECTORS})")
            await browser.close()
            return []

        # 검색 실행
        print(f"     검색 쿼리: '{query}' (셀렉터: {matched_sel})")
        await search_el.fill(query)
        await search_el.press("Enter")

        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            await page.wait_for_load_state("domcontentloaded", timeout=10_000)

        # AJAX 렌더링 대기: 상품 링크 패턴이 DOM에 나타날 때까지 최대 5초 폴링
        _product_selector = ", ".join(
            f'a[href*="{p}"]' for p in _PRODUCT_URL_PATTERNS
        )
        try:
            await page.wait_for_selector(_product_selector, timeout=5_000)
            print(f"     상품 링크 DOM 등장 확인")
        except Exception:
            # 타임아웃 — AJAX가 느리거나 패턴이 없는 경우, 1초 추가 대기 후 진행
            await page.wait_for_timeout(1_000)
            print(f"     상품 링크 대기 타임아웃, 현재 DOM으로 진행")

        print(f"     검색 후 URL: {page.url}")

        # 상품 링크 후보 추출 — 메인 프레임 + 모든 iframe 탐색
        js_extract = """(patterns) => {
            const seen = new Set();
            const results = [];
            const links = Array.from(document.querySelectorAll('a[href]'));
            for (const a of links) {
                const href = a.href;
                const text = a.innerText.trim().replace(/\\s+/g, ' ');
                if (!text || text.length < 2) continue;
                if (!patterns.some(p => href.includes(p))) continue;
                if (seen.has(href)) continue;
                seen.add(href);
                results.push({ name: text, url: href });
                if (results.length >= 15) break;
            }
            return results;
        }"""

        candidates = await page.evaluate(js_extract, _PRODUCT_URL_PATTERNS)

        # 메인 프레임에서 못 찾으면 iframe 전부 탐색
        if not candidates:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    frame_candidates = await frame.evaluate(js_extract, _PRODUCT_URL_PATTERNS)
                    if frame_candidates:
                        print(f"     iframe({frame.url[:60]})에서 {len(frame_candidates)}건 발견")
                        candidates = frame_candidates
                        break
                except Exception:
                    continue

        if not candidates:
            # 진단: 패턴 불일치인지 확인용 샘플 출력
            sample = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .slice(0, 5).map(a => a.href);
            }""")
            print(f"     ✗ 패턴 미매칭. 샘플 링크: {sample}")

        await browser.close()
        return candidates


def _pick_best_url(product_name: str, candidates: list[dict]) -> Optional[str]:
    """LLM에게 후보 목록 중 가장 유사한 URL을 선택하게 한다.
    LLM 실패 시 후보가 있으면 첫 번째 항목을 반환 (best-effort fallback).
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["url"]

    candidate_text = "\n".join(
        f"{i+1}. 상품명: {c['name'][:80]}\n   URL: {c['url']}"
        for i, c in enumerate(candidates)
    )

    prompt = f"""다음은 쇼핑몰 검색 결과 상품 목록이다.
찾는 상품명: "{product_name}"

후보 목록:
{candidate_text}

위 목록 중 찾는 상품과 가장 유사한 항목의 URL을 반환해라.
반드시 아래 JSON 형식으로만 출력할 것 (다른 텍스트 없이):
{{"url": "선택한 URL", "reason": "선택 이유 한 줄"}}

확실히 일치하는 항목이 없으면: {{"url": null, "reason": "없음"}}"""

    try:
        if config.LLM_PROVIDER == "gemini":
            import time
            from google import genai
            from google.genai.errors import ServerError, ClientError
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            _MODELS = config.GEMINI_MODELS
            raw = None
            for model in _MODELS:
                for attempt in range(3):
                    try:
                        resp = client.models.generate_content(
                            model=model, contents=[prompt]
                        )
                        raw = resp.text.strip()
                        break
                    except ServerError:
                        time.sleep(2 ** attempt)
                    except ClientError:
                        # 429: 할당량 초과 → 다음 모델로
                        print(f"     [{model}] 429 할당량 초과, 다음 모델로...")
                        break
                if raw:
                    break
            if not raw:
                raise RuntimeError("모든 Gemini 모델 할당량 초과")
        else:
            from openai import OpenAI
            client = OpenAI(api_key=config.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw = resp.choices[0].message.content

        # JSON 정제
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        url = result.get("url")
        reason = result.get("reason", "")
        if url:
            print(f"     LLM 선택: {url} ({reason})")
        return url
    except Exception as e:
        print(f"     LLM 매칭 실패: {e}")
        # LLM 실패해도 후보가 있으면 첫 번째 항목 반환 (best-effort)
        fallback = candidates[0]["url"]
        print(f"     fallback → 첫 번째 후보 사용: {fallback}")
        return fallback


def find_product_url(product_name: str, seller_url: str) -> Optional[str]:
    """
    판매처 사이트에서 product_name을 검색해 가장 유사한 상품 URL을 반환한다.

    후보가 0건이면 다음 쿼리로 재시도 (쿼리를 점진적으로 줄여가며 탐색).

    Args:
        product_name: 영수증에서 추출한 상품명
        seller_url:   판매처 base URL (예: "https://fashionstart.net")

    Returns:
        상품 URL 문자열, 또는 찾지 못하면 None
    """
    print(f"  [URL 탐색] '{product_name}' @ {seller_url}")
    queries = _make_search_queries(product_name)

    for query in queries:
        candidates = asyncio.run(_search_and_extract(query, seller_url))
        print(f"     후보 {len(candidates)}건 발견")
        if candidates:
            return _pick_best_url(product_name, candidates)
        if len(queries) > 1:
            print(f"     0건 → 다음 쿼리 시도")

    print(f"     모든 쿼리 소진, URL 탐색 실패")
    return None
