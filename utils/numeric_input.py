"""Strict parsing of the numbers that arrive from a form or a JSON body.

A malformed number must never become a zero.

The failure mode this exists to prevent: a tax rate typed as ``16%`` is
parsed by a lenient helper into ``0.0``, the service reads that as an
EXPLICIT rate of zero (which the statutory fallback respects), and the
invoice that looks perfectly reasonable on screen is tax-free in the ledger.
The same shape turns a purchase line's unit cost into zero and a customs
duty into the statutory default instead of the operator's figure.

So the contract is:

* ``None`` or an empty string -> *default* (the field was not supplied)
* a number -> the number
* anything else -> ``ValueError`` naming the field

The caller decides what to do with the error; for a form that means telling
the operator, for an API that means a 400.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_decimal_field(
    value,
    *,
    default=None,
    field: str = "value",
    allow_negative: bool = True,
) -> Decimal | None:
    """Parse *value* as a Decimal, strictly.

    Raises ``ValueError`` when the field was supplied but is not a number.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, Decimal):
        candidate = value
    else:
        try:
            candidate = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"{field} must be a number") from None
    if not candidate.is_finite():
        raise ValueError(f"{field} must be a number")
    if not allow_negative and candidate < 0:
        raise ValueError(f"{field} cannot be negative")
    return candidate


def parse_float_field(value, *, default=None, field: str = "value", allow_negative: bool = True):
    """Same contract as :func:`parse_decimal_field`, with a float result."""
    parsed = parse_decimal_field(value, default=default, field=field, allow_negative=allow_negative)
    if parsed is None:
        return None
    return float(parsed)


def parse_int_field(value, *, default=None, field: str = "value", minimum: int | None = None):
    """Parse *value* as an int, strictly.

    An unparseable value becomes ``ValueError`` rather than a 500, and
    *minimum* rejects a negative or zero id.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        parsed = int(str(value).strip())
    except (ValueError, TypeError):
        raise ValueError(f"{field} must be a whole number") from None
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return parsed
