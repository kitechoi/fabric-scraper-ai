"""
DB CRUD 단위 테스트

- tmp_db fixture로 테스트별 격리 SQLite 사용
- sample_fabric_info.image_url=None → _download_image() 미호출 (네트워크 차단)
- save()는 ON CONFLICT upsert 동작 (같은 URL → 덮어쓰기)
"""
import pytest
from db.database import save, list_all, check_exists, delete, update


class TestSave:
    def test_returns_int_id(self, tmp_db, sample_fabric_info):
        row_id = save(sample_fabric_info)
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_saved_row_retrievable(self, tmp_db, sample_fabric_info):
        save(sample_fabric_info)
        rows = list_all()
        assert len(rows) == 1
        assert rows[0]["product_name"] == "테스트 원단"

    def test_upsert_on_duplicate_url(self, tmp_db, sample_fabric_info):
        """같은 URL 재저장 → 덮어쓰기 (오류 아님)"""
        save(sample_fabric_info)
        updated = sample_fabric_info.model_copy(update={"product_name": "수정된 원단"})
        save(updated)

        rows = list_all()
        assert len(rows) == 1  # 새 행이 추가되지 않음
        assert rows[0]["product_name"] == "수정된 원단"

    def test_multiple_items_saved(self, tmp_db, sample_fabric_info):
        save(sample_fabric_info)
        second = sample_fabric_info.model_copy(update={
            "url": "https://fashionstart.net/goods/goods_view.php?goodsNo=88888",
            "product_name": "두 번째 원단",
        })
        save(second)
        assert len(list_all()) == 2


class TestListAll:
    def test_empty_db(self, tmp_db):
        assert list_all() == []

    def test_returns_dicts(self, tmp_db, sample_fabric_info):
        save(sample_fabric_info)
        rows = list_all()
        assert isinstance(rows[0], dict)
        assert "id" in rows[0]
        assert "product_name" in rows[0]
        assert "created_at" in rows[0]


class TestCheckExists:
    def test_found(self, tmp_db, sample_fabric_info):
        save(sample_fabric_info)
        row = check_exists(sample_fabric_info.url)
        assert row is not None
        assert row["product_name"] == "테스트 원단"

    def test_not_found(self, tmp_db):
        result = check_exists("https://notexist.example.com/item")
        assert result is None

    def test_returns_dict_with_id(self, tmp_db, sample_fabric_info):
        save(sample_fabric_info)
        row = check_exists(sample_fabric_info.url)
        assert "id" in row
        assert isinstance(row["id"], int)


class TestDelete:
    def test_removes_row(self, tmp_db, sample_fabric_info):
        row_id = save(sample_fabric_info)
        delete(row_id)
        assert list_all() == []

    def test_nonexistent_id_is_noop(self, tmp_db):
        """존재하지 않는 id 삭제 → 오류 없이 통과"""
        delete(9999)

    def test_deletes_correct_row(self, tmp_db, sample_fabric_info):
        """2건 중 1건만 삭제"""
        id1 = save(sample_fabric_info)
        second = sample_fabric_info.model_copy(update={
            "url": "https://fashionstart.net/goods/goods_view.php?goodsNo=77777",
            "product_name": "삭제 안 할 원단",
        })
        save(second)

        delete(id1)
        rows = list_all()
        assert len(rows) == 1
        assert rows[0]["product_name"] == "삭제 안 할 원단"


class TestUpdate:
    def test_updates_product_name(self, tmp_db, sample_fabric_info):
        row_id = save(sample_fabric_info)
        update(row_id, {"product_name": "수정 원단"})
        assert list_all()[0]["product_name"] == "수정 원단"

    def test_updates_seller(self, tmp_db, sample_fabric_info):
        row_id = save(sample_fabric_info)
        update(row_id, {"seller": "코튼빌"})
        assert list_all()[0]["seller"] == "코튼빌"

    def test_updates_multiple_fields(self, tmp_db, sample_fabric_info):
        row_id = save(sample_fabric_info)
        update(row_id, {"material": "폴리 100%", "size": "148cm", "price": "6500원/m"})
        row = list_all()[0]
        assert row["material"] == "폴리 100%"
        assert row["size"] == "148cm"
        assert row["price"] == "6500원/m"

    def test_disallowed_field_url_is_ignored(self, tmp_db, sample_fabric_info):
        """url 필드 수정 시도 → 무시됨, 원래 URL로 여전히 조회 가능"""
        row_id = save(sample_fabric_info)
        original_url = sample_fabric_info.url
        update(row_id, {"url": "https://hacked.example.com"})
        assert check_exists(original_url) is not None

    def test_empty_dict_is_noop(self, tmp_db, sample_fabric_info):
        row_id = save(sample_fabric_info)
        update(row_id, {})
        assert list_all()[0]["product_name"] == "테스트 원단"

    def test_only_disallowed_fields_is_noop(self, tmp_db, sample_fabric_info):
        row_id = save(sample_fabric_info)
        update(row_id, {"url": "https://hack.com", "id": 999, "image_path": "/evil"})
        assert list_all()[0]["product_name"] == "테스트 원단"
