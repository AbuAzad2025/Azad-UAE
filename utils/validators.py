"""
Unified Input Validation Layer
Centralized validation to ensure data integrity across all endpoints.
"""

from typing import Optional, Tuple
from datetime import datetime
import re


class ValidationError(Exception):
    """Raised when input validation fails."""


# ==================== Numeric Validators ====================


def validate_positive_amount(value, field_name: str = "amount") -> float:
    """Validate that a value is a positive number."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a valid number")
    if num < 0:
        raise ValidationError(f"{field_name} cannot be negative")
    if num > 999_999_999_999:  # 999 billion max
        raise ValidationError(f"{field_name} exceeds maximum allowed value")
    return num


def validate_quantity(value, field_name: str = "quantity") -> float:
    """Validate product quantity (can be zero but not negative)."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a valid number")
    if num < 0:
        raise ValidationError(f"{field_name} cannot be negative")
    if num > 1_000_000:  # 1 million max
        raise ValidationError(f"{field_name} exceeds maximum allowed value")
    return num


def validate_percentage(value, field_name: str = "percentage") -> float:
    """Validate percentage (0-100)."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a valid number")
    if not (0 <= num <= 100):
        raise ValidationError(f"{field_name} must be between 0 and 100")
    return num


# ==================== String Validators ====================


def validate_required_string(
    value: Optional[str], field_name: str, max_length: int = 255
) -> str:
    """Validate a required string field."""
    if not value or not str(value).strip():
        raise ValidationError(f"{field_name} is required")
    text = str(value).strip()
    if len(text) > max_length:
        raise ValidationError(
            f"{field_name} exceeds maximum length of {max_length} characters"
        )
    # Prevent control characters
    if any(ord(c) < 32 and c not in "\t\n\r" for c in text):
        raise ValidationError(f"{field_name} contains invalid characters")
    return text


def validate_email(value: Optional[str]) -> Optional[str]:
    """Validate email format if provided."""
    if not value:
        return None
    email = str(value).strip().lower()
    if len(email) > 254:
        raise ValidationError("Email exceeds maximum length")
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        raise ValidationError("Invalid email format")
    return email


def validate_phone(value: Optional[str]) -> Optional[str]:
    """Validate phone number format if provided."""
    if not value:
        return None
    phone = re.sub(r"[^\d+]", "", str(value))
    if len(phone) < 7 or len(phone) > 20:
        raise ValidationError("Phone number must be 7-20 digits")
    return phone


# ==================== Date Validators ====================


def validate_date_range(
    date_from: Optional[str], date_to: Optional[str]
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Validate a date range."""
    from_date = None
    to_date = None

    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise ValidationError("Invalid from_date format. Use YYYY-MM-DD")

    if date_to:
        try:
            to_date = datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            raise ValidationError("Invalid to_date format. Use YYYY-MM-DD")

    if from_date and to_date and from_date > to_date:
        raise ValidationError("From date cannot be after to date")

    return from_date, to_date


# ==================== ID Validators ====================


def validate_id(value, field_name: str = "id") -> int:
    """Validate a database ID."""
    try:
        id_val = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a valid integer")
    if id_val <= 0:
        raise ValidationError(f"{field_name} must be a positive integer")
    if id_val > 2_147_483_647:  # Max int32
        raise ValidationError(f"{field_name} exceeds maximum allowed value")
    return id_val


def validate_optional_id(value, field_name: str = "id") -> Optional[int]:
    """Validate an optional database ID."""
    if value is None or value == "":
        return None
    return validate_id(value, field_name)


# ==================== Collection Validators ====================


def validate_pagination(
    page: int, per_page: int, max_per_page: int = 100
) -> Tuple[int, int]:
    """Validate and normalize pagination parameters."""
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 20
    if per_page > max_per_page:
        per_page = max_per_page
    return page, per_page
