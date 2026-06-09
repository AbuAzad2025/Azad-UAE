"""
Verify the form_validation.js maxLength/minLength guard logic.
Pure Python simulation — no JS engine needed.
"""


def _validate_field(val, min_length, max_length):
    """Mirror of validateField logic for the length checks."""
    val = val.strip()
    if min_length > 0 and len(val) < min_length:
        return f"الحد الأدنى {min_length} أحرف"
    if max_length > 0 and len(val) > max_length:
        return f"الحد الأقصى {max_length} حرف"
    return None


def test_negative_maxlength_is_ignored():
    assert _validate_field("hello", -1, -1) is None
    assert _validate_field("", -1, -1) is None


def test_positive_maxlength_enforced():
    assert _validate_field("hello", -1, 3) == "الحد الأقصى 3 حرف"


def test_positive_minlength_enforced():
    assert _validate_field("hi", 3, -1) == "الحد الأدنى 3 أحرف"


def test_zero_limits_are_ignored():
    assert _validate_field("hello", 0, 0) is None
