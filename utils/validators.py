"""
Unified Input Validation Layer
Centralized validation to ensure data integrity across all endpoints.
"""

import re
from datetime import datetime


class ValidationError(ValueError):
    """Raised when input validation fails.

    Subclasses ValueError deliberately: callers of helpers.save_uploaded_file
    already catch ValueError to turn a rejected upload into a 400, and an
    unrelated exception type here would escape as a 500.
    """


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


def validate_required_string(value: str | None, field_name: str, max_length: int = 255) -> str:
    """Validate a required string field."""
    if not value or not str(value).strip():
        raise ValidationError(f"{field_name} is required")
    text = str(value).strip()
    if len(text) > max_length:
        raise ValidationError(f"{field_name} exceeds maximum length of {max_length} characters")
    # Prevent control characters
    if any(ord(c) < 32 and c not in "\t\n\r" for c in text):
        raise ValidationError(f"{field_name} contains invalid characters")
    return text


def validate_email(value: str | None) -> str | None:
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


def validate_phone(value: str | None) -> str | None:
    """Validate phone number format if provided."""
    if not value:
        return None
    phone = re.sub(r"[^\d+]", "", str(value))
    if len(phone) < 7 or len(phone) > 20:
        raise ValidationError("Phone number must be 7-20 digits")
    return phone


# ==================== Date Validators ====================


def validate_date_range(date_from: str | None, date_to: str | None) -> tuple[datetime | None, datetime | None]:
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


def validate_optional_id(value, field_name: str = "id") -> int | None:
    """Validate an optional database ID."""
    if value is None or value == "":
        return None
    return validate_id(value, field_name)


# ==================== Collection Validators ====================


def validate_pagination(page: int, per_page: int, max_per_page: int = 100) -> tuple[int, int]:
    """Validate and normalize pagination parameters."""
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 20
    if per_page > max_per_page:
        per_page = max_per_page
    return page, per_page


# ==================== File Upload Content Validation ====================
# An extension allowlist alone is a filename check, not a content check: the
# server decides how to serve whatever arrives, so a .png that is really HTML
# becomes stored XSS the moment that file is requested. save_uploaded_file only
# rejected two executable formats, which left every other type unchecked.
#
# Each extension maps to the alternatives that are valid for it. An
# alternative is a tuple of (offset, bytes) that must ALL match - webp needs
# both RIFF and the WEBP tag at offset 8, since WAV and AVI share the
# container. Alternatives are tried in turn: GIF has GIF87a or GIF89a.
_FILE_SIGNATURES: dict[str, tuple[tuple[tuple[int, bytes], ...], ...]] = {
    "png": (((0, b"\x89PNG\r\n\x1a\n"),),),
    "jpg": (((0, b"\xff\xd8\xff"),),),
    "jpeg": (((0, b"\xff\xd8\xff"),),),
    "gif": (((0, b"GIF87a"),), ((0, b"GIF89a"),)),
    "webp": (((0, b"RIFF"), (8, b"WEBP")),),
    "pdf": (((0, b"%PDF-"),),),
    "zip": (((0, b"PK\x03\x04"),),),
    "xlsx": (((0, b"PK\x03\x04"),),),
    "xls": (((0, b"\xd0\xcf\x11\xe0"),),),
    "doc": (((0, b"\xd0\xcf\x11\xe0"),),),
    "docx": (((0, b"PK\x03\x04"),),),
}

# Formats with no reliable signature. These are text or container formats where
# any prefix is plausible; they are accepted on the extension allowlist alone,
# and callers should treat them as untrusted input.
_UNSIGNED_EXTENSIONS = frozenset({"csv", "txt", "xml", "json"})


def validate_file_signature(filename: str, header: bytes) -> None:
    """Reject an upload whose bytes contradict its extension.

    Args:
        filename: the client-supplied name; only its extension is read.
        header: the first bytes of the uploaded file.

    Raises:
        ValidationError: if the extension is unknown, or the content does not
            match the signature for that extension.
    """
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if not ext or ext in _UNSIGNED_EXTENSIONS:
        return
    alternatives = _FILE_SIGNATURES.get(ext)
    if alternatives is None:
        raise ValidationError(f"Unsupported file type: .{ext}")
    for required in alternatives:
        if all(header[o : o + len(m)] == m for o, m in required):
            return
    raise ValidationError(f"File content does not match a .{ext} file")
