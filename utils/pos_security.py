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


def issue_customer_display_token(session_id: int, tenant_id: int) -> str:
    """HMAC token authorizing the public customer-display page/stream."""
    return _hmac_hex(f"pos-display:{int(session_id)}:{int(tenant_id)}")


def verify_customer_display_token(session_id: int, tenant_id: int, token) -> bool:
    """Constant-time verification of a customer-display link token."""
    if not token:
        return False
    expected = issue_customer_display_token(session_id, tenant_id)
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


# ─── Insert-only fraud signal log (hash-chained per tenant) ───

POS_FRAUD_REPEAT_WINDOW_MINUTES = 60
POS_FRAUD_REPEAT_THRESHOLD = 3

_FRAUD_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def _fraud_canonical(row, prev_hash: str) -> str:
    return "|".join(
        [
            prev_hash,
            str(int(row.tenant_id)),
            str(row.user_id or ""),
            str(row.session_id or ""),
            str(row.event_type),
            str(row.severity),
            str(row.repeat_count),
            row.details or "{}",
            row.created_at.strftime(_FRAUD_TS_FORMAT),
        ]
    )


def log_pos_fraud_signal(
    event_type: str,
    *,
    user_id=None,
    session_id=None,
    branch_id=None,
    details=None,
    severity: str = "medium",
    tenant_id=None,
):
    """Append one insert-only fraud signal with per-tenant hash chaining.

    Repeat aggregation: the same ``(event_type, user_id)`` recurring within
    ``POS_FRAUD_REPEAT_WINDOW_MINUTES`` increments ``repeat_count``; reaching
    ``POS_FRAUD_REPEAT_THRESHOLD`` escalates severity to ``high``. Never
    raises on missing tenant context (returns ``None`` instead).
    """
    import json
    from datetime import datetime, timedelta, timezone

    from extensions import db
    from models import PosFraudSignal
    from utils.tenanting import get_active_tenant_id

    tid = tenant_id or get_active_tenant_id()
    if tid is None:
        return None
    try:
        tid = int(tid)
    except (TypeError, ValueError):
        return None
    # Naive UTC wall time — the exact value hashed is the value stored.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window_start = now - timedelta(minutes=POS_FRAUD_REPEAT_WINDOW_MINUTES)
    repeat_count = (
        PosFraudSignal.query.filter(
            PosFraudSignal.tenant_id == int(tid),
            PosFraudSignal.event_type == event_type,
            PosFraudSignal.user_id == user_id,
            PosFraudSignal.created_at >= window_start,
        ).count()
        + 1
    )
    if repeat_count >= POS_FRAUD_REPEAT_THRESHOLD:
        severity = "high"
    prev = PosFraudSignal.query.filter(PosFraudSignal.tenant_id == int(tid)).order_by(PosFraudSignal.id.desc()).first()
    prev_hash = prev.entry_hash if prev else ""
    details_json = json.dumps(details or {}, ensure_ascii=False, sort_keys=True, default=str)
    row = PosFraudSignal(
        tenant_id=int(tid),
        branch_id=branch_id,
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        severity=severity,
        repeat_count=repeat_count,
        details=details_json,
        prev_hash=prev_hash,
        created_at=now,
    )
    row.entry_hash = hashlib.sha256(_fraud_canonical(row, prev_hash).encode("utf-8")).hexdigest()
    db.session.add(row)
    db.session.flush()
    return row


def verify_pos_fraud_chain(tenant_id: int) -> bool:
    """Recompute the per-tenant hash chain; ``False`` on any tamper or gap."""
    from models import PosFraudSignal

    rows = (
        PosFraudSignal.query.filter(PosFraudSignal.tenant_id == int(tenant_id)).order_by(PosFraudSignal.id.asc()).all()
    )
    prev_hash = ""
    for row in rows:
        if row.prev_hash != prev_hash:
            return False
        expected = hashlib.sha256(_fraud_canonical(row, prev_hash).encode("utf-8")).hexdigest()
        if row.entry_hash != expected:
            return False
        prev_hash = row.entry_hash
    return True
