"""Tests for ambiguity module."""

from cc_spec.core.ambiguity import (
    AMBIGUITY_KEYWORDS,
    AmbiguityMatch,
    AmbiguityType,
    detect,
    filter_false_positives,
    get_context,
    is_in_code_block,
)
from cc_spec.core.ambiguity.detector import (
    get_all_keywords,
    get_keywords_by_type,
    get_type_description,
)


class TestAmbiguityType:
    """Tests for AmbiguityType enum."""

    def test_has_nine_types(self) -> None:
        """Test that enum has exactly 9 types."""
        assert len(AmbiguityType) == 9

    def test_scope_type(self) -> None:
        """Test SCOPE type exists and has correct value."""
        assert AmbiguityType.SCOPE.value == "scope"

    def test_data_structure_type(self) -> None:
        """Test DATA_STRUCTURE type exists and has correct value."""
        assert AmbiguityType.DATA_STRUCTURE.value == "data_structure"

    def test_interface_type(self) -> None:
        """Test INTERFACE type exists and has correct value."""
        assert AmbiguityType.INTERFACE.value == "interface"

    def test_validation_type(self) -> None:
        """Test VALIDATION type exists and has correct value."""
        assert AmbiguityType.VALIDATION.value == "validation"

    def test_error_handling_type(self) -> None:
        """Test ERROR_HANDLING type exists and has correct value."""
        assert AmbiguityType.ERROR_HANDLING.value == "error_handling"

    def test_performance_type(self) -> None:
        """Test PERFORMANCE type exists and has correct value."""
        assert AmbiguityType.PERFORMANCE.value == "performance"

    def test_security_type(self) -> None:
        """Test SECURITY type exists and has correct value."""
        assert AmbiguityType.SECURITY.value == "security"

    def test_dependency_type(self) -> None:
        """Test DEPENDENCY type exists and has correct value."""
        assert AmbiguityType.DEPENDENCY.value == "dependency"

    def test_ux_type(self) -> None:
        """Test UX type exists and has correct value."""
        assert AmbiguityType.UX.value == "ux"

    def test_all_types_unique(self) -> None:
        """Test that all type values are unique."""
        values = [t.value for t in AmbiguityType]
        assert len(values) == len(set(values))


class TestAmbiguityKeywords:
    """Tests for AMBIGUITY_KEYWORDS mapping."""

    def test_has_keywords_for_all_types(self) -> None:
        """Test that keywords are defined for all 9 types."""
        assert len(AMBIGUITY_KEYWORDS) == 9
        for ambiguity_type in AmbiguityType:
            assert ambiguity_type in AMBIGUITY_KEYWORDS

    def test_each_type_has_minimum_keywords(self) -> None:
        """Test that each type has at least 5 keywords."""
        for ambiguity_type, keywords in AMBIGUITY_KEYWORDS.items():
            assert len(keywords) >= 5, f"{ambiguity_type} has only {len(keywords)} keywords"

    def test_scope_keywords_include_chinese(self) -> None:
        """Test that SCOPE keywords include Chinese terms."""
        keywords = AMBIGUITY_KEYWORDS[AmbiguityType.SCOPE]
        chinese_keywords = ["可能", "或许", "大概"]
        for kw in chinese_keywords:
            assert kw in keywords, f"Missing Chinese keyword: {kw}"

    def test_scope_keywords_include_english(self) -> None:
        """Test that SCOPE keywords include English terms."""
        keywords = AMBIGUITY_KEYWORDS[AmbiguityType.SCOPE]
        english_keywords = ["maybe", "perhaps", "possibly"]
        for kw in english_keywords:
            assert kw in keywords, f"Missing English keyword: {kw}"

    def test_data_structure_keywords(self) -> None:
        """Test DATA_STRUCTURE keywords."""
        keywords = AMBIGUITY_KEYWORDS[AmbiguityType.DATA_STRUCTURE]
        assert "待定" in keywords
        assert "tbd" in keywords

    def test_error_handling_keywords(self) -> None:
        """Test ERROR_HANDLING keywords."""
        keywords = AMBIGUITY_KEYWORDS[AmbiguityType.ERROR_HANDLING]
        assert "重试" in keywords
        assert "retry" in keywords
        assert "timeout" in keywords

    def test_security_keywords(self) -> None:
        """Test SECURITY keywords."""
        keywords = AMBIGUITY_KEYWORDS[AmbiguityType.SECURITY]
        assert "权限" in keywords
        assert "security" in keywords
        assert "token" in keywords

    def test_keywords_are_lowercase(self) -> None:
        """Test that English keywords are lowercase."""
        for keywords in AMBIGUITY_KEYWORDS.values():
            for kw in keywords:
                # Skip Chinese characters
                if any(ord(c) > 127 for c in kw):
                    continue
                assert kw == kw.lower(), f"Keyword '{kw}' should be lowercase"


class TestAmbiguityMatch:
    """Tests for AmbiguityMatch data class."""

    def test_basic_creation(self) -> None:
        """Test basic AmbiguityMatch creation."""
        match = AmbiguityMatch(
            type=AmbiguityType.SCOPE,
            keyword="maybe",
            line_number=10,
            context="line 9\nmaybe this is unclear\nline 11",
        )
        assert match.type == AmbiguityType.SCOPE
        assert match.keyword == "maybe"
        assert match.line_number == 10
        assert "maybe this is unclear" in match.context

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        match = AmbiguityMatch(
            type=AmbiguityType.VALIDATION,
            keyword="校验",
            line_number=5,
            context="some context",
        )
        assert match.original_line == ""
        assert match.confidence == 1.0

    def test_with_original_line(self) -> None:
        """Test AmbiguityMatch with original_line field."""
        match = AmbiguityMatch(
            type=AmbiguityType.INTERFACE,
            keyword="api",
            line_number=20,
            context="context here",
            original_line="We need to call the api endpoint",
        )
        assert match.original_line == "We need to call the api endpoint"

    def test_with_confidence(self) -> None:
        """Test AmbiguityMatch with custom confidence."""
        match = AmbiguityMatch(
            type=AmbiguityType.PERFORMANCE,
            keyword="fast",
            line_number=15,
            context="context",
            confidence=0.8,
        )
        assert match.confidence == 0.8

    def test_str_representation(self) -> None:
        """Test string representation."""
        match = AmbiguityMatch(
            type=AmbiguityType.SECURITY,
            keyword="权限",
            line_number=25,
            context="context",
            original_line="  需要检查权限  ",
        )
        result = str(match)
        assert "[security]" in result
        assert "Line 25" in result
        assert "权限" in result
        assert "需要检查权限" in result

    def test_to_dict(self) -> None:
        """Test to_dict conversion."""
        match = AmbiguityMatch(
            type=AmbiguityType.DEPENDENCY,
            keyword="version",
            line_number=30,
            context="version context",
            original_line="check the version",
            confidence=0.9,
        )
        result = match.to_dict()
        assert result["type"] == "dependency"
        assert result["keyword"] == "version"
        assert result["line_number"] == 30
        assert result["context"] == "version context"
        assert result["original_line"] == "check the version"
        assert result["confidence"] == 0.9


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_type_description_scope(self) -> None:
        """Test get_type_description for SCOPE."""
        desc = get_type_description(AmbiguityType.SCOPE)
        assert "范围歧义" in desc
        assert "功能边界" in desc

    def test_get_type_description_all_types(self) -> None:
        """Test get_type_description returns non-empty for all types."""
        for ambiguity_type in AmbiguityType:
            desc = get_type_description(ambiguity_type)
            assert len(desc) > 0
            assert "歧义" in desc or ambiguity_type.value in desc

    def test_get_all_keywords(self) -> None:
        """Test get_all_keywords returns flattened list."""
        all_keywords = get_all_keywords()
        assert isinstance(all_keywords, list)
        assert len(all_keywords) > 50  # Should have many keywords
        assert "maybe" in all_keywords
        assert "可能" in all_keywords

    def test_get_keywords_by_type(self) -> None:
        """Test get_keywords_by_type returns correct list."""
        keywords = get_keywords_by_type(AmbiguityType.SCOPE)
        assert "maybe" in keywords
        assert "可能" in keywords

    def test_get_keywords_by_type_all_types(self) -> None:
        """Test get_keywords_by_type works for all types."""
        for ambiguity_type in AmbiguityType:
            keywords = get_keywords_by_type(ambiguity_type)
            assert len(keywords) >= 5


class TestAmbiguityTypeUsability:
    """Tests for practical usage of ambiguity types."""

    def test_type_iteration(self) -> None:
        """Test that all types can be iterated."""
        types_list = list(AmbiguityType)
        assert len(types_list) == 9

    def test_type_from_string(self) -> None:
        """Test creating type from string value."""
        for ambiguity_type in AmbiguityType:
            # Can get type by value
            found = None
            for t in AmbiguityType:
                if t.value == ambiguity_type.value:
                    found = t
                    break
            assert found == ambiguity_type

    def test_type_comparison(self) -> None:
        """Test type comparison."""
        assert AmbiguityType.SCOPE == AmbiguityType.SCOPE
        assert AmbiguityType.SCOPE != AmbiguityType.UX


class TestGetContext:
    """Tests for get_context function."""

    def test_basic_context(self) -> None:
        """Test basic context extraction."""
        lines = ["line1", "line2", "line3", "line4", "line5"]
        context = get_context(lines, 2, context_lines=2)
        assert "line1" in context
        assert "line2" in context
        assert "line3" in context
        assert "line4" in context
        assert "line5" in context

    def test_context_at_start(self) -> None:
        """Test context extraction at start of file."""
        lines = ["line1", "line2", "line3", "line4", "line5"]
        context = get_context(lines, 0, context_lines=2)
        assert "line1" in context
        assert "line2" in context
        assert "line3" in context

    def test_context_at_end(self) -> None:
        """Test context extraction at end of file."""
        lines = ["line1", "line2", "line3", "line4", "line5"]
        context = get_context(lines, 4, context_lines=2)
        assert "line3" in context
        assert "line4" in context
        assert "line5" in context

    def test_context_custom_lines(self) -> None:
        """Test context with custom number of lines."""
        lines = ["a", "b", "c", "d", "e", "f", "g"]
        context = get_context(lines, 3, context_lines=1)
        assert "c" in context
        assert "d" in context
        assert "e" in context
        assert "a" not in context


class TestIsInCodeBlock:
    """Tests for is_in_code_block function."""

    def test_not_in_code_block(self) -> None:
        """Test line not in code block."""
        lines = ["normal line", "another line"]
        assert is_in_code_block(lines, 0) is False
        assert is_in_code_block(lines, 1) is False

    def test_in_code_block(self) -> None:
        """Test line inside code block."""
        lines = ["text", "```python", "code here", "```", "more text"]
        assert is_in_code_block(lines, 0) is False
        assert is_in_code_block(lines, 2) is True  # Inside code block
        assert is_in_code_block(lines, 4) is False

    def test_multiple_code_blocks(self) -> None:
        """Test multiple code blocks."""
        lines = [
            "text",
            "```",
            "block1",
            "```",
            "text",
            "```",
            "block2",
            "```",
            "final text",
        ]
        assert is_in_code_block(lines, 0) is False
        assert is_in_code_block(lines, 2) is True
        assert is_in_code_block(lines, 4) is False
        assert is_in_code_block(lines, 6) is True
        assert is_in_code_block(lines, 8) is False


class TestFilterFalsePositives:
    """Tests for filter_false_positives function."""

    def test_normal_line_kept(self) -> None:
        """Test normal line with keyword is kept."""
        match = AmbiguityMatch(
            type=AmbiguityType.SCOPE,
            keyword="maybe",
            line_number=1,
            context="",
            original_line="This maybe needs clarification",
        )
        assert filter_false_positives(match, "This maybe needs clarification") is True

    def test_header_filtered(self) -> None:
        """Test markdown header is filtered."""
        match = AmbiguityMatch(
            type=AmbiguityType.SCOPE,
            keyword="maybe",
            line_number=1,
            context="",
            original_line="# Maybe Section",
        )
        assert filter_false_positives(match, "# Maybe Section") is False

    def test_negation_filtered(self) -> None:
        """Test line with negation word is filtered."""
        match = AmbiguityMatch(
            type=AmbiguityType.DATA_STRUCTURE,
            keyword="待定",
            line_number=1,
            context="",
            original_line="这个字段已定义，不是待定",
        )
        assert filter_false_positives(match, "这个字段已定义，不是待定") is False

    def test_english_negation_filtered(self) -> None:
        """Test line with English negation is filtered."""
        match = AmbiguityMatch(
            type=AmbiguityType.SCOPE,
            keyword="perhaps",
            line_number=1,
            context="",
            original_line="The API is already defined, perhaps not ambiguous",
        )
        line = "The API is already defined, perhaps not ambiguous"
        assert filter_false_positives(match, line) is False

    def test_url_filtered(self) -> None:
        """Test keyword in URL is filtered."""
        match = AmbiguityMatch(
            type=AmbiguityType.INTERFACE,
            keyword="api",
            line_number=1,
            context="",
            original_line="See https://api.example.com/docs for details",
        )
        line = "See https://api.example.com/docs for details"
        assert filter_false_positives(match, line) is False

    def test_inline_code_filtered(self) -> None:
        """Test keyword in inline code is filtered."""
        match = AmbiguityMatch(
            type=AmbiguityType.VALIDATION,
            keyword="validate",
            line_number=1,
            context="",
            original_line="Use the `validate()` function",
        )
        assert filter_false_positives(match, "Use the `validate()` function") is False


class TestDetect:
    """Tests for detect function."""

    def test_detect_empty_content(self) -> None:
        """Test detect with empty content."""
        matches = detect("")
        assert matches == []

    def test_detect_no_ambiguity(self) -> None:
        """Test detect with unambiguous content."""
        content = """# Clear Specification

This is a clear and precise document.
The requirements are exact and specific.
"""
        matches = detect(content)
        # Should have no matches or very few
        assert len(matches) < 5

    def test_detect_scope_ambiguity_chinese(self) -> None:
        """Test detect finds Chinese scope keywords."""
        content = """# 需求文档

这个功能可能需要调整。
或许我们应该考虑其他方案。
"""
        matches = detect(content)
        scope_matches = [m for m in matches if m.type == AmbiguityType.SCOPE]
        assert len(scope_matches) > 0
        keywords_found = {m.keyword for m in scope_matches}
        assert "可能" in keywords_found or "或许" in keywords_found

    def test_detect_scope_ambiguity_english(self) -> None:
        """Test detect finds English scope keywords."""
        content = """# Requirements

This feature maybe needs adjustment.
Perhaps we should consider alternatives.
"""
        matches = detect(content)
        scope_matches = [m for m in matches if m.type == AmbiguityType.SCOPE]
        assert len(scope_matches) > 0

    def test_detect_skips_code_blocks(self) -> None:
        """Test detect skips content in code blocks."""
        content = """# Document

```python
# This maybe should be skipped
result = maybe_function()
```

This maybe is not in code block.
"""
        matches = detect(content)
        # Only the line outside code block should match
        for match in matches:
            if match.keyword == "maybe":
                assert match.line_number == 8  # Line after code block

    def test_detect_returns_correct_line_numbers(self) -> None:
        """Test detect returns correct line numbers (1-indexed)."""
        content = """Line 1
Line 2
Maybe this line 3
Line 4
"""
        matches = detect(content)
        maybe_matches = [m for m in matches if m.keyword == "maybe"]
        if maybe_matches:
            assert maybe_matches[0].line_number == 3

    def test_detect_includes_context(self) -> None:
        """Test detect includes context in matches."""
        content = """Context line 1
Context line 2
This maybe needs work
Context line 4
Context line 5
"""
        matches = detect(content)
        maybe_matches = [m for m in matches if m.keyword == "maybe"]
        if maybe_matches:
            context = maybe_matches[0].context
            assert "Context line" in context

    def test_detect_multiple_types(self) -> None:
        """Test detect finds multiple ambiguity types."""
        content = """# Mixed Ambiguities

Maybe we need to handle errors with retry logic.
The security permissions might be dynamic.
Performance should be optimized, possibly with cache.
"""
        matches = detect(content)
        types_found = {m.type for m in matches}
        # Should find multiple different types
        assert len(types_found) >= 2

    def test_detect_filters_negations(self) -> None:
        """Test detect filters lines with negation words."""
        content = """# Document

The format is already defined and confirmed.
This maybe needs clarification.
"""
        matches = detect(content)
        # The first line should be filtered due to "defined"
        defined_line_matches = [
            m for m in matches
            if m.line_number == 3 and m.keyword == "format"
        ]
        assert len(defined_line_matches) == 0

    def test_detect_case_insensitive(self) -> None:
        """Test detect is case insensitive for English keywords."""
        content = """# Document

MAYBE this needs work.
Maybe this too.
maybe lowercase.
"""
        matches = detect(content)
        maybe_matches = [m for m in matches if m.keyword.lower() == "maybe"]
        assert len(maybe_matches) >= 3
