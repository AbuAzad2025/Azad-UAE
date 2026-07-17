from __future__ import annotations

from datetime import datetime

import pytest

from utils.validators import (
    ValidationError,
    validate_date_range,
    validate_email,
    validate_id,
    validate_optional_id,
    validate_pagination,
    validate_percentage,
    validate_phone,
    validate_positive_amount,
    validate_quantity,
    validate_required_string,
)


class TestValidatePositiveAmount:
    def test_accepts_zero_and_positive(self):
        assert validate_positive_amount(0) == 0.0
        assert validate_positive_amount("42.5") == 42.5

    def test_rejects_invalid_number(self):
        with pytest.raises(ValidationError, match="amount must be a valid number"):
            validate_positive_amount("abc")

    def test_rejects_negative(self):
        with pytest.raises(ValidationError, match="cannot be negative"):
            validate_positive_amount(-1)

    def test_rejects_excessive_value(self):
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_positive_amount(1_000_000_000_000)

    def test_custom_field_name(self):
        with pytest.raises(ValidationError, match="total must be a valid number"):
            validate_positive_amount(None, field_name="total")


class TestValidateQuantity:
    def test_accepts_zero_and_within_limit(self):
        assert validate_quantity(0) == 0.0
        assert validate_quantity(1_000_000) == 1_000_000.0

    def test_rejects_invalid_and_negative(self):
        with pytest.raises(ValidationError, match="quantity must be a valid number"):
            validate_quantity({})
        with pytest.raises(ValidationError, match="cannot be negative"):
            validate_quantity(-0.01)

    def test_rejects_excessive_quantity(self):
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_quantity(1_000_001)


class TestValidatePercentage:
    def test_accepts_boundaries(self):
        assert validate_percentage(0) == 0.0
        assert validate_percentage(100) == 100.0
        assert validate_percentage("50.5") == 50.5

    def test_rejects_out_of_range(self):
        with pytest.raises(ValidationError, match="between 0 and 100"):
            validate_percentage(100.1)
        with pytest.raises(ValidationError, match="between 0 and 100"):
            validate_percentage(-1)

    def test_rejects_non_numeric(self):
        with pytest.raises(ValidationError, match="percentage must be a valid number"):
            validate_percentage("half")


class TestValidateRequiredString:
    def test_returns_stripped_text(self):
        assert validate_required_string("  hello  ", "name") == "hello"

    def test_rejects_empty_and_whitespace(self):
        with pytest.raises(ValidationError, match="title is required"):
            validate_required_string("", "title")
        with pytest.raises(ValidationError, match="title is required"):
            validate_required_string("   ", "title")
        with pytest.raises(ValidationError, match="title is required"):
            validate_required_string(None, "title")

    def test_rejects_excessive_length(self):
        with pytest.raises(ValidationError, match="maximum length of 3"):
            validate_required_string("abcd", "code", max_length=3)

    def test_rejects_control_characters(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_required_string("bad\x01value", "field")

    def test_allows_tab_newline_carriage_return(self):
        assert validate_required_string("a\tb\nc\r", "field") == "a\tb\nc"


class TestValidateEmail:
    def test_returns_none_for_empty(self):
        assert validate_email(None) is None
        assert validate_email("") is None

    def test_normalizes_valid_email(self):
        assert validate_email("  User@Example.COM  ") == "user@example.com"

    def test_rejects_invalid_and_oversized(self):
        with pytest.raises(ValidationError, match="Invalid email format"):
            validate_email("not-an-email")
        with pytest.raises(ValidationError, match="maximum length"):
            validate_email("a" * 250 + "@b.co")


class TestValidatePhone:
    def test_returns_none_for_empty(self):
        assert validate_phone(None) is None

    def test_strips_non_digits_and_validates_length(self):
        assert validate_phone("+971 50-123 4567") == "+971501234567"

    def test_rejects_too_short_or_long(self):
        with pytest.raises(ValidationError, match="7-20 digits"):
            validate_phone("123456")
        with pytest.raises(ValidationError, match="7-20 digits"):
            validate_phone("1" * 21)


class TestValidateDateRange:
    def test_parses_valid_range(self):
        start, end = validate_date_range("2024-01-01", "2024-12-31")
        assert start == datetime(2024, 1, 1)
        assert end == datetime(2024, 12, 31)

    def test_allows_single_sided_dates(self):
        start, end = validate_date_range("2024-06-15", None)
        assert start == datetime(2024, 6, 15)
        assert end is None
        start, end = validate_date_range(None, "2024-06-15")
        assert start is None
        assert end == datetime(2024, 6, 15)

    def test_rejects_invalid_formats(self):
        with pytest.raises(ValidationError, match="Invalid from_date"):
            validate_date_range("01-01-2024", None)
        with pytest.raises(ValidationError, match="Invalid to_date"):
            validate_date_range(None, "31/12/2024")

    def test_rejects_inverted_range(self):
        with pytest.raises(ValidationError, match="From date cannot be after"):
            validate_date_range("2024-12-01", "2024-01-01")


class TestValidateId:
    def test_accepts_positive_integers(self):
        assert validate_id("42") == 42
        assert validate_id(1) == 1

    def test_rejects_invalid_non_positive_and_overflow(self):
        with pytest.raises(ValidationError, match="id must be a valid integer"):
            validate_id("x")
        with pytest.raises(ValidationError, match="positive integer"):
            validate_id(0)
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_id(2_147_483_648)


class TestValidateOptionalId:
    def test_returns_none_for_missing(self):
        assert validate_optional_id(None) is None
        assert validate_optional_id("") is None

    def test_delegates_to_validate_id(self):
        assert validate_optional_id("7") == 7


class TestValidatePagination:
    def test_normalizes_invalid_and_caps_per_page(self):
        assert validate_pagination(0, 0) == (1, 20)
        assert validate_pagination(2, 500, max_per_page=100) == (2, 100)

    def test_preserves_valid_values(self):
        assert validate_pagination(3, 50, max_per_page=100) == (3, 50)
