"""Unit tests for delta module."""

import pytest

from cc_spec.core.delta import (
    DeltaItem,
    DeltaOperation,
    DeltaSpec,
    generate_merge_preview,
    merge_delta,
    parse_delta,
    validate_delta,
)


class TestDeltaOperation:
    """Tests for DeltaOperation enum."""

    def test_enum_values(self) -> None:
        """Test DeltaOperation enum values."""
        assert DeltaOperation.ADDED.value == "added"
        assert DeltaOperation.MODIFIED.value == "modified"
        assert DeltaOperation.REMOVED.value == "removed"
        assert DeltaOperation.RENAMED.value == "renamed"


class TestDeltaItem:
    """Tests for DeltaItem dataclass."""

    def test_added_item(self) -> None:
        """Test creating ADDED DeltaItem."""
        item = DeltaItem(
            operation=DeltaOperation.ADDED,
            requirement_name="New Feature",
            content="The system SHALL support new feature.",
        )
        assert item.operation == DeltaOperation.ADDED
        assert item.requirement_name == "New Feature"
        assert item.content == "The system SHALL support new feature."
        assert item.reason is None
        assert item.migration is None
        assert item.old_name is None
        assert item.new_name is None

    def test_modified_item(self) -> None:
        """Test creating MODIFIED DeltaItem."""
        item = DeltaItem(
            operation=DeltaOperation.MODIFIED,
            requirement_name="Existing Feature",
            content="Updated content.",
        )
        assert item.operation == DeltaOperation.MODIFIED
        assert item.requirement_name == "Existing Feature"
        assert item.content == "Updated content."

    def test_removed_item(self) -> None:
        """Test creating REMOVED DeltaItem."""
        item = DeltaItem(
            operation=DeltaOperation.REMOVED,
            requirement_name="Old Feature",
            reason="Deprecated",
            migration="Use new feature instead",
        )
        assert item.operation == DeltaOperation.REMOVED
        assert item.requirement_name == "Old Feature"
        assert item.reason == "Deprecated"
        assert item.migration == "Use new feature instead"

    def test_renamed_item(self) -> None:
        """Test creating RENAMED DeltaItem."""
        item = DeltaItem(
            operation=DeltaOperation.RENAMED,
            requirement_name="New Name",
            old_name="Old Name",
            new_name="New Name",
        )
        assert item.operation == DeltaOperation.RENAMED
        assert item.requirement_name == "New Name"
        assert item.old_name == "Old Name"
        assert item.new_name == "New Name"


class TestDeltaSpec:
    """Tests for DeltaSpec dataclass."""

    def test_delta_spec_creation(self) -> None:
        """Test creating DeltaSpec."""
        items = [
            DeltaItem(
                operation=DeltaOperation.ADDED,
                requirement_name="Feature A",
                content="Content A",
            ),
            DeltaItem(
                operation=DeltaOperation.MODIFIED,
                requirement_name="Feature B",
                content="Content B",
            ),
        ]
        delta = DeltaSpec(capability="user-auth", items=items)

        assert delta.capability == "user-auth"
        assert len(delta.items) == 2
        assert delta.items[0].operation == DeltaOperation.ADDED
        assert delta.items[1].operation == DeltaOperation.MODIFIED


class TestParseDelta:
    """Tests for parse_delta function."""

    def test_parse_simple_delta(self) -> None:
        """Test parsing a simple delta spec."""
        content = """# Delta: user-auth

## ADDED Requirements

### Requirement: OAuth2 Support
The system SHALL support OAuth2 authentication.

## MODIFIED Requirements

### Requirement: Session Management
Updated session timeout to 24 hours.

## REMOVED Requirements

### Requirement: Basic Auth
**Reason**: Replaced by OAuth2
**Migration**: Link OAuth account

## RENAMED Requirements

- FROM: `### Requirement: Login Flow`
- TO: `### Requirement: Authentication Flow`
"""
        delta = parse_delta(content)

        assert delta.capability == "user-auth"
        assert len(delta.items) == 4

        # Check ADDED
        added = [item for item in delta.items if item.operation == DeltaOperation.ADDED]
        assert len(added) == 1
        assert added[0].requirement_name == "OAuth2 Support"
        assert "OAuth2 authentication" in added[0].content

        # Check MODIFIED
        modified = [
            item for item in delta.items if item.operation == DeltaOperation.MODIFIED
        ]
        assert len(modified) == 1
        assert modified[0].requirement_name == "Session Management"
        assert "24 hours" in modified[0].content

        # Check REMOVED
        removed = [
            item for item in delta.items if item.operation == DeltaOperation.REMOVED
        ]
        assert len(removed) == 1
        assert removed[0].requirement_name == "Basic Auth"
        assert removed[0].reason == "Replaced by OAuth2"
        assert removed[0].migration == "Link OAuth account"

        # Check RENAMED
        renamed = [
            item for item in delta.items if item.operation == DeltaOperation.RENAMED
        ]
        assert len(renamed) == 1
        assert renamed[0].old_name == "Login Flow"
        assert renamed[0].new_name == "Authentication Flow"

    def test_parse_delta_missing_title(self) -> None:
        """Test parsing delta without proper title."""
        content = """## ADDED Requirements

### Requirement: New Feature
Content here.
"""
        with pytest.raises(ValueError, match="(must have a title|必须有标题|标题)"):
            parse_delta(content)

    def test_parse_delta_multiple_added(self) -> None:
        """Test parsing delta with multiple ADDED requirements."""
        content = """# Delta: payment

## ADDED Requirements

### Requirement: Credit Card Payment
Support credit card payments.

### Requirement: PayPal Payment
Support PayPal payments.

### Requirement: Apple Pay
Support Apple Pay.
"""
        delta = parse_delta(content)

        assert delta.capability == "payment"
        assert len(delta.items) == 3
        assert all(item.operation == DeltaOperation.ADDED for item in delta.items)
        names = [item.requirement_name for item in delta.items]
        assert "Credit Card Payment" in names
        assert "PayPal Payment" in names
        assert "Apple Pay" in names

    def test_parse_delta_multiple_renamed(self) -> None:
        """Test parsing delta with multiple RENAMED requirements."""
        content = """# Delta: api

## RENAMED Requirements

- FROM: `### Requirement: Old API v1`
- TO: `### Requirement: New API v1`

- FROM: `### Requirement: Old API v2`
- TO: `### Requirement: New API v2`
"""
        delta = parse_delta(content)

        assert delta.capability == "api"
        assert len(delta.items) == 2
        assert all(item.operation == DeltaOperation.RENAMED for item in delta.items)
        assert delta.items[0].old_name == "Old API v1"
        assert delta.items[0].new_name == "New API v1"
        assert delta.items[1].old_name == "Old API v2"
        assert delta.items[1].new_name == "New API v2"

    def test_parse_delta_empty_sections(self) -> None:
        """Test parsing delta with empty sections."""
        content = """# Delta: empty-test

## ADDED Requirements

## MODIFIED Requirements

## REMOVED Requirements

## RENAMED Requirements
"""
        delta = parse_delta(content)

        assert delta.capability == "empty-test"
        assert len(delta.items) == 0


class TestValidateDelta:
    """Tests for validate_delta function."""

    def test_validate_valid_delta(self) -> None:
        """Test validating a valid delta spec."""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="OAuth2",
                    content="OAuth2 support",
                ),
                DeltaItem(
                    operation=DeltaOperation.REMOVED,
                    requirement_name="Basic Auth",
                    reason="Deprecated",
                ),
                DeltaItem(
                    operation=DeltaOperation.RENAMED,
                    requirement_name="New Name",
                    old_name="Old Name",
                    new_name="New Name",
                ),
            ],
        )

        is_valid, errors = validate_delta(delta)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_missing_capability(self) -> None:
        """Test validating delta without capability name."""
        delta = DeltaSpec(
            capability="",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="Feature",
                    content="Content",
                )
            ],
        )

        is_valid, errors = validate_delta(delta)

        assert is_valid is False
        assert any("capability" in error.lower() for error in errors)

    def test_validate_no_items(self) -> None:
        """Test validating delta with no items."""
        delta = DeltaSpec(capability="test", items=[])

        is_valid, errors = validate_delta(delta)

        assert is_valid is False
        assert any("至少" in error or "at least" in error.lower() for error in errors)

    def test_validate_added_without_content(self) -> None:
        """Test validating ADDED item without content."""
        delta = DeltaSpec(
            capability="test",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="Feature",
                    content="",
                )
            ],
        )

        is_valid, errors = validate_delta(delta)

        assert is_valid is False
        assert any("content" in error.lower() for error in errors)

    def test_validate_modified_without_content(self) -> None:
        """Test validating MODIFIED item without content."""
        delta = DeltaSpec(
            capability="test",
            items=[
                DeltaItem(
                    operation=DeltaOperation.MODIFIED,
                    requirement_name="Feature",
                    content="",
                )
            ],
        )

        is_valid, errors = validate_delta(delta)

        assert is_valid is False
        assert any("content" in error.lower() for error in errors)

    def test_validate_removed_without_reason(self) -> None:
        """Test validating REMOVED item without reason."""
        delta = DeltaSpec(
            capability="test",
            items=[
                DeltaItem(
                    operation=DeltaOperation.REMOVED,
                    requirement_name="Feature",
                    reason=None,
                )
            ],
        )

        is_valid, errors = validate_delta(delta)

        assert is_valid is False
        assert any("reason" in error.lower() for error in errors)

    def test_validate_renamed_without_names(self) -> None:
        """Test validating RENAMED item without old/new names."""
        delta = DeltaSpec(
            capability="test",
            items=[
                DeltaItem(
                    operation=DeltaOperation.RENAMED,
                    requirement_name="Feature",
                    old_name=None,
                    new_name=None,
                )
            ],
        )

        is_valid, errors = validate_delta(delta)

        assert is_valid is False
        assert any("old_name" in error for error in errors)
        assert any("new_name" in error for error in errors)

    def test_validate_missing_requirement_name(self) -> None:
        """Test validating item without requirement_name."""
        delta = DeltaSpec(
            capability="test",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED, requirement_name="", content="Test"
                )
            ],
        )

        is_valid, errors = validate_delta(delta)

        assert is_valid is False
        assert any("requirement_name" in error for error in errors)


class TestMergeDelta:
    """Tests for merge_delta function."""

    def test_merge_added(self) -> None:
        """Test merging ADDED requirement."""
        base_content = """# Spec: User Auth

### Requirement: Login
User can log in.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="OAuth2",
                    content="The system SHALL support OAuth2.",
                )
            ],
        )

        result = merge_delta(base_content, delta)

        assert "### Requirement: OAuth2" in result
        assert "The system SHALL support OAuth2." in result
        assert "### Requirement: Login" in result  # Original preserved

    def test_merge_modified(self) -> None:
        """Test merging MODIFIED requirement."""
        base_content = """# Spec: User Auth

### Requirement: Session Timeout
Sessions expire after 1 hour.

### Requirement: Login
User can log in.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.MODIFIED,
                    requirement_name="Session Timeout",
                    content="Sessions expire after 24 hours.",
                )
            ],
        )

        result = merge_delta(base_content, delta)

        assert "Sessions expire after 24 hours." in result
        assert "Sessions expire after 1 hour." not in result
        assert "### Requirement: Login" in result  # Other requirement preserved

    def test_merge_removed(self) -> None:
        """Test merging REMOVED requirement."""
        base_content = """# Spec: User Auth

### Requirement: Basic Auth
Support basic authentication.

### Requirement: OAuth2
Support OAuth2 authentication.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.REMOVED,
                    requirement_name="Basic Auth",
                    reason="Deprecated",
                )
            ],
        )

        result = merge_delta(base_content, delta)

        assert "### Requirement: Basic Auth" not in result
        assert "Support basic authentication." not in result
        assert "### Requirement: OAuth2" in result  # Other requirement preserved

    def test_merge_renamed(self) -> None:
        """Test merging RENAMED requirement."""
        base_content = """# Spec: User Auth

### Requirement: Login Flow
User authentication process.

Some detailed content here.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.RENAMED,
                    requirement_name="Authentication Flow",
                    old_name="Login Flow",
                    new_name="Authentication Flow",
                )
            ],
        )

        result = merge_delta(base_content, delta)

        assert "### Requirement: Authentication Flow" in result
        assert "### Requirement: Login Flow" not in result
        assert "User authentication process." in result  # Content preserved
        assert "Some detailed content here." in result  # Content preserved

    def test_merge_multiple_operations(self) -> None:
        """Test merging multiple operations at once."""
        base_content = """# Spec: User Auth

### Requirement: Login
Basic login.

### Requirement: Old Feature
To be removed.

### Requirement: To Rename
Should be renamed.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="OAuth2",
                    content="OAuth2 support.",
                ),
                DeltaItem(
                    operation=DeltaOperation.MODIFIED,
                    requirement_name="Login",
                    content="Enhanced login with MFA.",
                ),
                DeltaItem(
                    operation=DeltaOperation.REMOVED,
                    requirement_name="Old Feature",
                    reason="Deprecated",
                ),
                DeltaItem(
                    operation=DeltaOperation.RENAMED,
                    requirement_name="New Name",
                    old_name="To Rename",
                    new_name="New Name",
                ),
            ],
        )

        result = merge_delta(base_content, delta)

        # Check all changes applied
        assert "### Requirement: OAuth2" in result
        assert "Enhanced login with MFA." in result
        assert "### Requirement: Old Feature" not in result
        assert "### Requirement: New Name" in result
        assert "### Requirement: To Rename" not in result

    def test_merge_modified_not_found(self) -> None:
        """Test merging MODIFIED when requirement not found."""
        base_content = """# Spec: User Auth

### Requirement: Login
Basic login.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.MODIFIED,
                    requirement_name="Nonexistent",
                    content="Should fail.",
                )
            ],
        )

        with pytest.raises(ValueError, match="(not found|未找到)"):
            merge_delta(base_content, delta)

    def test_merge_removed_not_found(self) -> None:
        """Test merging REMOVED when requirement not found."""
        base_content = """# Spec: User Auth

### Requirement: Login
Basic login.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.REMOVED,
                    requirement_name="Nonexistent",
                    reason="Test",
                )
            ],
        )

        with pytest.raises(ValueError, match="(not found|未找到)"):
            merge_delta(base_content, delta)

    def test_merge_renamed_not_found(self) -> None:
        """Test merging RENAMED when old name not found."""
        base_content = """# Spec: User Auth

### Requirement: Login
Basic login.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.RENAMED,
                    requirement_name="New Name",
                    old_name="Nonexistent",
                    new_name="New Name",
                )
            ],
        )

        with pytest.raises(ValueError, match="(not found|未找到)"):
            merge_delta(base_content, delta)


class TestGenerateMergePreview:
    """Tests for generate_merge_preview function."""

    def test_preview_all_operations(self) -> None:
        """Test generating preview with all operation types."""
        base_content = """# Spec: User Auth

### Requirement: Login
Basic login.

### Requirement: Old Feature
To be removed.

### Requirement: To Rename
Should be renamed.
"""
        delta = DeltaSpec(
            capability="user-auth",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="OAuth2",
                    content="OAuth2 support.",
                ),
                DeltaItem(
                    operation=DeltaOperation.MODIFIED,
                    requirement_name="Login",
                    content="Enhanced login.",
                ),
                DeltaItem(
                    operation=DeltaOperation.REMOVED,
                    requirement_name="Old Feature",
                    reason="Deprecated",
                    migration="Use new feature",
                ),
                DeltaItem(
                    operation=DeltaOperation.RENAMED,
                    requirement_name="New Name",
                    old_name="To Rename",
                    new_name="New Name",
                ),
            ],
        )

        preview = generate_merge_preview(base_content, delta)

        assert "user-auth" in preview
        assert "4" in preview  # Total changes count
        assert "+" in preview and "OAuth2" in preview  # Added
        assert "~" in preview and "Login" in preview  # Modified
        assert "-" in preview and "Old Feature" in preview  # Removed
        assert "→" in preview  # Renamed arrow
        assert "Deprecated" in preview  # Reason
        assert "✓" in preview  # Validation passed

    def test_preview_validation_errors(self) -> None:
        """Test preview with validation errors."""
        base_content = ""
        delta = DeltaSpec(
            capability="",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="Feature",
                    content="",  # Missing content
                )
            ],
        )

        preview = generate_merge_preview(base_content, delta)

        assert "✗" in preview  # Validation error indicator
        assert "capability" in preview.lower()
        assert "content" in preview.lower()

    def test_preview_empty_delta(self) -> None:
        """Test preview with no changes."""
        base_content = "# Spec"
        delta = DeltaSpec(capability="test", items=[])

        preview = generate_merge_preview(base_content, delta)

        assert "0" in preview  # No changes
        assert "至少" in preview or "at least" in preview.lower()

    def test_preview_only_added(self) -> None:
        """Test preview with only ADDED operations."""
        base_content = "# Spec"
        delta = DeltaSpec(
            capability="test",
            items=[
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="Feature A",
                    content="Content A",
                ),
                DeltaItem(
                    operation=DeltaOperation.ADDED,
                    requirement_name="Feature B",
                    content="Content B",
                ),
            ],
        )

        preview = generate_merge_preview(base_content, delta)

        assert "2" in preview  # 2 additions
        assert "+ Feature A" in preview or "Feature A" in preview
        assert "+ Feature B" in preview or "Feature B" in preview
