import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # "openai" 또는 "gemini"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Notion 연동 (선택 — 없으면 Notion 저장 건너뜀)
NOTION_API_KEY     = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

DB_PATH = "fabric.db"

# Gemini 모델 우선순위 — 앞에서부터 순서대로 시도, 429/503 발생 시 다음으로 폴백
GEMINI_MODELS: list[str] = [
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash",
    "gemini-2.5-flash",
]

# 자주 사용하는 판매처 — 영수증 수집 기능에서 검색 대상으로 사용
SELLER_SITES: dict[str, str] = {
    "패션스타트": "https://fashionstart.net",
    "천가게":  "https://1000gage.co.kr",
    "썬퀼트":     "https://www.sunquilt.com",
    "코튼빌":     "http://www.cottonvill.com",
}
