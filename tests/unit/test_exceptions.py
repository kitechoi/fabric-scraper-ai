"""
커스텀 예외 클래스 단위 테스트

검증 대상:
  - DuplicateURLError: .existing 속성, 메시지에 id 포함
  - LLMQuotaError: Exception 서브클래스, 메시지 보존
"""
from pipeline import DuplicateURLError, LLMQuotaError


class TestDuplicateURLError:
    def test_existing_attribute(self):
        existing = {"id": 1, "product_name": "원단", "created_at": "2026-06-19"}
        err = DuplicateURLError(existing)
        assert err.existing == existing

    def test_message_contains_id(self):
        err = DuplicateURLError({"id": 42, "product_name": "원단", "created_at": ""})
        assert "42" in str(err)

    def test_is_exception(self):
        err = DuplicateURLError({"id": 1, "product_name": "", "created_at": ""})
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self):
        import pytest
        with pytest.raises(DuplicateURLError) as exc_info:
            raise DuplicateURLError({"id": 99, "product_name": "원단", "created_at": ""})
        assert exc_info.value.existing["id"] == 99


class TestLLMQuotaError:
    def test_is_exception(self):
        err = LLMQuotaError("한도 초과")
        assert isinstance(err, Exception)

    def test_message_preserved(self):
        err = LLMQuotaError("gemini 모든 모델 할당량 초과")
        assert "할당량" in str(err)

    def test_can_be_raised_and_caught(self):
        import pytest
        with pytest.raises(LLMQuotaError):
            raise LLMQuotaError("한도")
