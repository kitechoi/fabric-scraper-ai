"""
Step 4: SQLite에 원단 정보를 저장한다. 이미지는 로컬 폴더에 다운로드한다.
"""
import sqlite3
import urllib.request
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List

import config

if TYPE_CHECKING:
    from scraper.extractor import FabricInfo

# 이미지 저장 폴더 (DB와 같은 위치 기준)
IMAGES_DIR = Path("images")


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fabrics (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name  TEXT NOT NULL,
            material      TEXT,
            size          TEXT,
            price         TEXT,
            color         TEXT,
            seller        TEXT,
            purchase_date TEXT,
            memo          TEXT,
            url           TEXT UNIQUE NOT NULL,
            image_url     TEXT,
            image_path    TEXT,
            created_at    DATETIME DEFAULT (datetime('now', 'localtime'))
        )
    """)
    # 기존 DB에 컬럼이 없으면 추가 (마이그레이션)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(fabrics)")}
    for col, typedef in [
        ("seller", "TEXT"),
        ("purchase_date", "TEXT"),
        ("color", "TEXT"),
        ("memo", "TEXT"),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE fabrics ADD COLUMN {col} {typedef}")
    conn.commit()


def _download_image(image_url: str) -> Optional[str]:
    """이미지를 IMAGES_DIR에 저장하고 상대 경로를 반환한다."""
    if not image_url:
        return None

    IMAGES_DIR.mkdir(exist_ok=True)

    # URL 해시로 파일명 생성 (확장자 유지)
    ext = image_url.split("?")[0].rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        ext = "jpg"
    filename = hashlib.md5(image_url.encode()).hexdigest()[:12] + f".{ext}"
    filepath = IMAGES_DIR / filename

    if filepath.exists():
        return str(filepath)  # 이미 다운로드됨

    try:
        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            filepath.write_bytes(resp.read())
        return str(filepath)
    except Exception as e:
        print(f"  [이미지 다운로드 실패] {e}")
        return None


def save(info: "FabricInfo") -> int:
    """
    FabricInfo를 DB에 저장한다.
    - 같은 URL이 이미 있으면 UPDATE (upsert).
    - 이미지를 로컬에 다운로드한 뒤 경로를 함께 저장.
    Returns: 저장된 row id
    """
    image_path = None
    if info.image_url:
        print(f"  [이미지 다운로드 중] {info.image_url}")
        image_path = _download_image(info.image_url)
        if image_path:
            print(f"  [이미지 저장 완료] {image_path}")

    with sqlite3.connect(config.DB_PATH) as conn:
        _init_db(conn)
        cursor = conn.execute("""
            INSERT INTO fabrics
                (product_name, material, size, price, color, seller, purchase_date, memo,
                 url, image_url, image_path)
            VALUES
                (:product_name, :material, :size, :price, :color, :seller, :purchase_date, :memo,
                 :url, :image_url, :image_path)
            ON CONFLICT(url) DO UPDATE SET
                product_name  = excluded.product_name,
                material      = excluded.material,
                size          = excluded.size,
                price         = excluded.price,
                color         = excluded.color,
                seller        = excluded.seller,
                purchase_date = excluded.purchase_date,
                memo          = excluded.memo,
                image_url     = excluded.image_url,
                image_path    = excluded.image_path
        """, {
            "product_name":  info.product_name,
            "material":      info.material,
            "size":          info.size,
            "price":         info.price,
            "color":         info.color,
            "seller":        info.seller,
            "purchase_date": info.purchase_date,
            "memo":          info.memo,
            "url":           info.url,
            "image_url":     info.image_url,
            "image_path":    image_path,
        })
        conn.commit()
        return cursor.lastrowid


def list_all() -> List[dict]:
    """저장된 전체 원단 목록을 반환한다."""
    with sqlite3.connect(config.DB_PATH) as conn:
        _init_db(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM fabrics ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def check_exists(url: str) -> Optional[dict]:
    """URL이 이미 DB에 있으면 해당 행을 반환, 없으면 None."""
    with sqlite3.connect(config.DB_PATH) as conn:
        _init_db(conn)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM fabrics WHERE url = ?", (url,)
        ).fetchone()
        return dict(row) if row else None


def delete(row_id: int) -> None:
    """id로 행을 삭제한다."""
    with sqlite3.connect(config.DB_PATH) as conn:
        _init_db(conn)
        conn.execute("DELETE FROM fabrics WHERE id = ?", (row_id,))
        conn.commit()


def update(row_id: int, fields: dict) -> None:
    """
    id로 지정한 행의 필드를 수정한다.
    fields: {"product_name": ..., "material": ..., "size": ..., "price": ...} 중 일부.
    """
    allowed = {"product_name", "material", "size", "price", "color", "seller", "purchase_date", "memo"}
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return
    set_clause = ", ".join(f"{k} = :{k}" for k in filtered)
    filtered["_id"] = row_id
    with sqlite3.connect(config.DB_PATH) as conn:
        _init_db(conn)
        conn.execute(
            f"UPDATE fabrics SET {set_clause} WHERE id = :_id", filtered
        )
        conn.commit()
