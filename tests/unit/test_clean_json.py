"""
_clean_json() 단위 테스트

검증 대상:
  - 마크다운 코드펜스 제거 (```json ... ```)
  - 앞뒤 공백 제거
  - 정상 JSON은 그대로 반환
"""
import json
from scraper.receipt_parser import _clean_json


class TestCleanJson:
    def test_plain_json_unchanged(self):
        raw = '{"items": []}'
        assert _clean_json(raw) == '{"items": []}'

    def test_strips_json_fence(self):
        raw = "```json\n{\"items\":[]}\n```"
        result = _clean_json(raw)
        assert result == '{"items":[]}'
        assert "```" not in result

    def test_strips_fence_without_language(self):
        raw = "```\n{\"items\":[]}\n```"
        result = _clean_json(raw)
        assert "```" not in result
        assert json.loads(result)  # 유효한 JSON 이어야 함

    def test_strips_leading_trailing_whitespace(self):
        raw = '  {"items": []}  '
        result = _clean_json(raw)
        assert result == result.strip()

    def test_result_is_valid_json(self):
        """정제 결과가 항상 파싱 가능한 JSON이어야 함"""
        cases = [
            '{"items": [{"name": "원단"}]}',
            "```json\n{\"items\":[{\"name\":\"원단\"}]}\n```",
        ]
        for raw in cases:
            result = _clean_json(raw)
            parsed = json.loads(result)
            assert parsed["items"][0]["name"] == "원단"
