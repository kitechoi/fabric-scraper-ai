"""
_make_search_query / _make_search_queries 단위 테스트

전략 변경 (2024):
  - 1차 쿼리: 상품명 그대로 (괄호·수량 제거 안 함)
  - 2차 쿼리: 괄호+내용 제거 (비전 오인식 대비)
  - 3차↓: 앞 단어 축소
  - 상품 코드가 있으면 코드만 단일 반환
"""
from scraper.url_finder import _make_search_query, _make_search_queries


class TestProductCodeExtraction:
    def test_numeric_code(self):
        assert _make_search_query("48-222 {Basic} 폴리 다후다 안감 15종") == "48-222"

    def test_another_numeric_code(self):
        assert _make_search_query("60-419 {반값세일} 로즈스킨 새틴") == "60-419"

    def test_three_digit_suffix_code(self):
        assert _make_search_query("70-087 {한정특가} 보드레 스판 공단 안감_화이트") == "70-087"

    def test_alpha_prefix_code(self):
        assert _make_search_query("A12-345 테스트 원단") == "A12-345"

    def test_code_takes_priority_over_keywords(self):
        """코드와 키워드가 함께 있으면 코드만 반환"""
        result = _make_search_query("48-222 폴리 다후다 안감")
        assert result == "48-222"
        assert "폴리" not in result

    def test_code_returns_single_query(self):
        """코드가 있으면 쿼리 목록도 1개"""
        assert _make_search_queries("70-157 [반값ST] 원단") == ["70-157"]


class TestKeywordFallback:
    def test_first_query_is_raw(self):
        """1차 쿼리는 괄호·수량 포함 원본 그대로"""
        queries = _make_search_queries("(Basic) 폴리 다후다 안감 15종")
        assert queries[0] == "(Basic) 폴리 다후다 안감 15종"

    def test_second_query_strips_brackets_and_content(self):
        """2차 쿼리는 괄호+내용 통째로 제거"""
        queries = _make_search_queries("(Basic) 폴리 다후다 안감 15종")
        assert len(queries) >= 2
        assert "(" not in queries[1]
        assert "Basic" not in queries[1]
        assert "폴리" in queries[1]

    def test_curly_braces_stripped_in_fallback(self):
        """중괄호+내용이 2차 쿼리에서 제거됨"""
        queries = _make_search_queries("폴리 다후다 안감 {베이지}")
        assert any("{" not in q for q in queries[1:])

    def test_square_brackets_stripped_in_fallback(self):
        """대괄호+내용이 2차 쿼리에서 제거됨"""
        queries = _make_search_queries("[한정특가] 코튼 원단")
        assert any("[" not in q for q in queries[1:])

    def test_quantity_suffix_in_raw_query(self):
        """1차 쿼리는 수량 표기 그대로 유지"""
        queries = _make_search_queries("폴리 안감 15종")
        assert "15종" in queries[0]

    def test_collapses_whitespace(self):
        """공백이 여러 개면 단일 공백으로"""
        queries = _make_search_queries("폴리  다후다   안감")
        assert "  " not in queries[0]

    def test_strips_leading_trailing_whitespace(self):
        """앞뒤 공백 제거"""
        queries = _make_search_queries("  코튼 원단  ")
        assert queries[0] == queries[0].strip()

    def test_fallback_shorter_queries(self):
        """단어가 4개 이상이면 3단어·2단어 축소 쿼리가 추가됨"""
        queries = _make_search_queries("한정특가 보드레 스판 공단 안감")
        words_per_query = [len(q.split()) for q in queries]
        assert 3 in words_per_query or 2 in words_per_query
