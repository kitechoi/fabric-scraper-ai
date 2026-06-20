"""
영수증/주문내역 이미지 → 상품 리스트 추출 (LLM Vision).
반환 형식: [{"name": str, "color": Optional[str]}, ...]
"""
import json
from typing import Optional
import config

RECEIPT_PROMPT = """이 이미지는 원단 쇼핑몰의 주문내역, 영수증, 또는 거래명세서 캡처본이다.
이미지에서 구매한 상품 목록을 추출해서 아래 JSON 형식으로만 반환해라.
마크다운 코드블록 없이 순수 JSON만 출력할 것.

{
  "items": [
    {"name": "상품명 (색상/옵션 제외한 순수 상품명)", "color": "색상 또는 옵션 (없으면 null)"},
    ...
  ]
}

주의:
- 추출 대상은 name과 color 두 필드뿐 — 가격, 수량, 날짜 등 다른 정보는 절대 추출하지 말 것
  (가격은 영수증의 정가가 아닌 실구매가를 별도로 수집해야 하므로 이 단계에서 불필요)
- 카테고리·브랜드 헤더, 배송비, 할인 등 상품이 아닌 항목은 제외
- 색상·옵션이 상품명에 붙어있으면 name에서 분리해 color에 넣을 것
  예) "보드레 스판 공단_화이트" → name: "보드레 스판 공단", color: "화이트"
- 동일 상품이라도 색상이 다르면 별개 항목으로 출력할 것"""


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _parse_gemini(image_bytes: bytes, mime_type: str) -> list[dict]:
    import time
    from google import genai
    from google.genai import types
    from google.genai.errors import ServerError, ClientError

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    contents = [
        RECEIPT_PROMPT,
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
    ]

    last_err = None
    for model in config.GEMINI_MODELS:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(model=model, contents=contents)
                data = json.loads(_clean_json(resp.text))
                return _items_to_dicts(data.get("items", []))
            except ServerError as e:
                last_err = e
                wait = 2 ** attempt
                print(f"     [{model}] 서버 오류, {wait}초 후 재시도...")
                time.sleep(wait)
            except ClientError as e:
                last_err = e
                print(f"     [{model}] 할당량 초과(429), 다음 모델로 전환...")
                break
            except Exception as e:
                raise

    raise RuntimeError(f"Gemini 호출 실패 (모든 모델 시도): {last_err}")


def _parse_openai(image_bytes: bytes, mime_type: str) -> list[dict]:
    import base64
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    b64 = base64.b64encode(image_bytes).decode()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": RECEIPT_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime_type};base64,{b64}",
                    "detail": "high",
                }},
            ],
        }],
        temperature=0,
    )
    data = json.loads(_clean_json(resp.choices[0].message.content))
    return _items_to_dicts(data.get("items", []))


def _items_to_dicts(items: list) -> list[dict]:
    """LLM 응답 items → [{"name": str, "color": Optional[str]}, ...] 정규화."""
    result = []
    for item in items:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        color = item.get("color") or None
        if color:
            color = color.strip() or None
        result.append({"name": name, "color": color})
    return result


def parse_receipt(image_bytes: bytes, mime_type: str = "image/jpeg") -> list[dict]:
    """
    영수증/주문내역 이미지에서 상품 리스트를 추출한다.

    Args:
        image_bytes: 이미지 바이너리
        mime_type:   "image/jpeg" | "image/png" | "image/webp" 등

    Returns:
        [{"name": str, "color": Optional[str]}, ...] 리스트
    """
    if config.LLM_PROVIDER == "gemini":
        return _parse_gemini(image_bytes, mime_type)
    return _parse_openai(image_bytes, mime_type)
