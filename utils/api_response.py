"""
Unified API Response Envelope
Ensures all API endpoints return a consistent format.

Standard envelope:
{
    "success": bool,
    "data": Any | null,
    "message": str | null,
    "errors": list[str] | null,
    "meta": dict | null  # pagination, timestamps, etc.
}
"""

from typing import Any
from flask import jsonify


def success_response(
    data: Any = None,
    message: str | None = None,
    meta: dict | None = None,
    status_code: int = 200,
):
    """Return a standardized success API response."""
    response = {
        "success": True,
        "data": data,
        "message": message,
        "errors": None,
        "meta": meta,
    }
    return jsonify(response), status_code


def error_response(
    message: str,
    errors: list | None = None,
    status_code: int = 400,
    meta: dict | None = None,
):
    """Return a standardized error API response."""
    response = {
        "success": False,
        "data": None,
        "message": message,
        "errors": errors or [],
        "meta": meta,
    }
    return jsonify(response), status_code


def paginated_response(
    items: list, page: int, per_page: int, total: int, message: str | None = None
):
    """Return a paginated success response with metadata."""
    return success_response(
        data=items,
        message=message,
        meta={
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
                "has_next": page * per_page < total,
                "has_prev": page > 1,
            }
        },
    )
