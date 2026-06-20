"""
Step 3: 페이지 텍스트(+옵션: 스크린샷)를 LLM에 넘겨 원단 정보를 JSON으로 추출한다.
"""
import json
from typing import Optional
from pydantic import BaseModel, Field
import config


# ── 추출 스키마 ────────────────────────────────────────────────
class FabricInfo(BaseModel):
    product_name: str = Field(description="상품명")
    material: Optional[str] = Field(None, description="소재/혼용률 (예: 면 60%, 폴리 40%)")
    size: Optional[str] = Field(None, description="원단 규격 (폭*길이, 예: 148*90, 150cm)")
    price: Optional[str] = Field(None, description="가격 (예: 8500원/yard)")
    color: Optional[str] = Field(None, description="색상/옵션 (예: 화이트, 베이지)")
    seller: Optional[str] = Field(None, description="판매처 (사용자 입력)")
    purchase_date: Optional[str] = Field(None, description="구입일 (사용자 입력, YYYY-MM-DD)")
    memo: Optional[str] = Field(None, description="메모 (사용자 입력)")
    image_url: Optional[str] = Field(None, description="대표 이미지 URL")
    url: str = Field(description="상품 URL")


# ── 공통 프롬프트 ──────────────────────────────────────────────
SYSTEM_PROMPT = """너는 원단 쇼핑몰 상품 페이지에서 정보를 추출하는 전문가야.
주어진 텍스트(마크다운 형식)에서 아래 필드를 추출해서 반드시 JSON만 반환해.
설명이나 마크다운 코드블록 없이 순수 JSON만 출력할 것.
페이지 텍스트에 없는 정보는 절대 만들어 내지 말고 null로 반환할 것.

## 가격(price) 판단 — 반드시 이 순서로 추론

1. ~~숫자~~ 형태(취소선)는 정가. 무시.
2. "정가", "소비자가", "원가"로 레이블된 금액은 정가. 무시.
3. "판매가", "할인가", "특가", "세일가"로 레이블된 금액이 있으면 그것이 실제 결제가.
4. 레이블 없이 두 금액이 나란히 있으면 더 낮은 금액이 할인가.
5. 단위(/m, /yard 등)가 있으면 반드시 함께 기록.

## 필드

- product_name: 상품명 전체. 상품코드(예: AB-123), 특가태그(예: [반값]) 모두 포함.
  색상·옵션 정보만 제외. 페이지 텍스트에서 찾은 실제 상품명만 기입.
- material: 소재/혼용률. 없으면 null
- size: 원단 규격. 폭+길이면 "148*90", 폭만이면 "148cm". 없으면 null
- price: 위 추론 순서에 따라 결정한 실제 결제 금액. 없으면 null
- color: 색상 또는 옵션. 상품명에 색상이 포함되면 분리해서 추출. 없으면 null
- url: 상품 URL"""

def _build_user_message(text: str, url: str) -> str:
    # Markdown은 HTML보다 compact하므로 10000자로 확장
    truncated = text[:10000]
    # 디버그: 실제 LLM에 전달되는 마크다운 앞부분 확인
    preview = truncated[:500].replace('\n', '↵')
    print(f"     [LLM 입력 미리보기] {len(truncated)}자: {preview}")
    return f"상품 URL: {url}\n\n페이지 마크다운:\n{truncated}"


# ── Gemini ────────────────────────────────────────────────────
def _extract_gemini(text: str, url: str, screenshot: Optional[bytes]) -> dict:
    import time
    from google import genai
    from google.genai import types
    from google.genai.errors import ServerError, ClientError

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    contents: list = [SYSTEM_PROMPT + "\n\n" + _build_user_message(text, url)]
    if screenshot:
        contents.append(types.Part.from_bytes(data=screenshot, mime_type="image/png"))

    last_err = None
    for model in config.GEMINI_MODELS:
        for attempt in range(3):  # 모델별 최대 3회 재시도
            try:
                response = client.models.generate_content(model=model, contents=contents)
                raw = response.text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                return json.loads(raw.strip())
            except ServerError as e:
                # 503: 서버 과부하 → 잠시 후 재시도
                last_err = e
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f"     [{model}] 서버 오류, {wait}초 후 재시도... ({e})")
                time.sleep(wait)
            except ClientError as e:
                # 429: 할당량 초과 → 같은 모델 재시도 무의미, 다음 모델로 즉시 전환
                last_err = e
                print(f"     [{model}] 할당량 초과(429), 다음 모델로 전환...")
                break  # inner loop 탈출 → 다음 model로
            except Exception as e:
                raise  # 그 외 에러는 즉시 전파

    raise RuntimeError(f"Gemini 호출 실패 (모든 모델 시도): {last_err}")


# ── OpenAI ───────────────────────────────────────────────────
def _extract_openai(text: str, url: str, screenshot: Optional[bytes]) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    user_content: list = [{"type": "text", "text": _build_user_message(text, url)}]
    if screenshot:
        b64 = base64.b64encode(screenshot).decode()
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"},
        })

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


# ── 공개 인터페이스 ───────────────────────────────────────────
def extract(
    text: str,
    url: str,
    image_url: Optional[str] = None,
    screenshot: Optional[bytes] = None,
) -> FabricInfo:
    """
    페이지 텍스트를 LLM으로 파싱해 FabricInfo를 반환한다.
    image_url: fetcher가 추출한 대표 이미지 URL (LLM이 아닌 DOM에서 직접 추출).
    screenshot: 텍스트에 정보가 없을 때 LLM에 함께 전달.
    """
    if config.LLM_PROVIDER == "gemini":
        raw = _extract_gemini(text, url, screenshot)
    else:
        raw = _extract_openai(text, url, screenshot)

    raw["url"] = url
    raw["image_url"] = image_url
    # pipeline에서 주입하는 필드 — LLM 결과가 있더라도 제거 (pipeline이 덮어씀)
    raw.pop("seller", None)
    raw.pop("purchase_date", None)
    raw.pop("memo", None)      # 메모는 항상 사용자가 직접 입력
    # color는 유지 (LLM이 페이지에서 추출, 영수증 색상이 있으면 pipeline에서 override)

    # product_name은 필수 필드 — LLM이 null 반환하면 URL에서 fallback
    if not raw.get("product_name"):
        raw["product_name"] = url.split("?")[-1]  # 쿼리스트링을 임시 이름으로
        print(f"     ⚠ product_name null → fallback 사용: {raw['product_name']}")

    return FabricInfo(**raw)


# ── 단독 실행 테스트 ─────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from scraper.fetcher import fetch

    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    print(f"[extractor test] {target}")

    page = fetch(target)
    info = extract(page["text"], target)  # 텍스트만으로 먼저 시도

    print(info.model_dump_json(indent=2))
