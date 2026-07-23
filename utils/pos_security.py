"""POS Phase 3 — stateless security primitives.

Session tokens bind a POS session to a cashier + terminal via HMAC-SHA256
over ``pos-session:<session_id>:<user_id>:<terminal_id>`` keyed with the app
``SECRET_KEY``. Override tokens are ``<id>.<nonce>.<hmac>`` strings whose
single-use server-side record lives in ``models/pos_override_token.py``.

All comparisons are constant-time (``hmac.compare_digest``).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from flask import current_app

from models.enums import PermissionEnum, RoleEnum

OVERRIDE_TOKEN_TTL_SECONDS = 60

# Override action -> permission code that lets the ACTING user perform the
# action without a supervisor override token.
OVERRIDE_ACTION_PERMISSIONS: dict[str, PermissionEnum] = {
    "void_line": PermissionEnum.POS_VOID_LINE,
    "discount_override": PermissionEnum.POS_DISCOUNT_OVERRIDE,
    "no_sale_drawer": PermissionEnum.POS_NO_SALE_DRAWER,
    "pay_in": PermissionEnum.POS_PAY_IN_OUT,
    "pay_out": PermissionEnum.POS_PAY_IN_OUT,
}

# Roles that always keep expected-balance (blind-close) visibility.
_EXPECTED_VISIBLE_ROLES = frozenset(
    {
        RoleEnum.OWNER.value,
        RoleEnum.DEVELOPER.value,
        RoleEnum.SUPER_ADMIN.value,
        RoleEnum.MANAGER.value,
        RoleEnum.BRANCH_MANAGER.value,
        RoleEnum.ACCOUNTANT.value,
    }
)


def _secret_key() -> bytes:
    key = current_app.config.get("SECRET_KEY", "")
    return str(key or "").encode("utf-8")


def _hmac_hex(payload: str) -> str:
    return hmac.new(_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_pos_session_token(session_id: int, user_id: int, terminal_id: str) -> str:
    """HMAC token proving possession of the session/terminal binding."""
    return _hmac_hex(f"pos-session:{int(session_id)}:{int(user_id)}:{terminal_id}")


def verify_pos_session_token(session, token) -> bool:
    """Constant-time verification of a presented session token.

    Sessions without a ``terminal_id`` are legacy/unbound — verification
    fails closed for them when a token check is requested explicitly; callers
    decide whether unbound sessions skip the check.
    """
    terminal_id = getattr(session, "terminal_id", None)
    if not terminal_id or not token:
        return False
    expected = issue_pos_session_token(session.id, session.user_id, terminal_id)
    return hmac.compare_digest(expected, str(token))


def new_override_nonce() -> str:
    return secrets.token_hex(16)


def sign_override_token(token_row) -> str:
    """Deterministic signed representation of a PosOverrideToken row."""
    expires = token_row.expires_at
    expires_ts = int(expires.timestamp()) if expires else 0
    payload = (
        f"pos-override:{token_row.id}:{token_row.nonce}:{token_row.action}:"
        f"{token_row.cashier_user_id}:{token_row.supervisor_user_id}:{expires_ts}"
    )
    return f"{token_row.id}.{token_row.nonce}.{_hmac_hex(payload)}"


def verify_override_token_signature(token_row, presented: str) -> bool:
    if not presented:
        return False
    return hmac.compare_digest(sign_override_token(token_row), str(presented))


def can_view_pos_expected(user) -> bool:
    """Blind-close visibility rule for expected balances / tender totals."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_owner", False):
        return True
    if user.has_permission(PermissionEnum.POS_VIEW_EXPECTED):
        return True
    role = getattr(user, "role", None)
    slug = getattr(role, "slug", None)
    return slug in _EXPECTED_VISIBLE_ROLES
