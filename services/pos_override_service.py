"""POS Phase 3 — supervisor PIN authorization & one-time override tokens.

Flow: the acting cashier calls ``authorize_with_pin`` with a supervisor's
PIN; the service finds an active same-tenant user who (a) holds the
``pos_authorize_override`` permission and (b) matches the PIN, then issues a
short-lived (60s), single-use override token bound to (action, cashier).
Privileged POS endpoints consume the token via
``require_permission_or_override`` — free when the acting user already holds
the action's permission, otherwise the token is validated and burned inside
the caller's ``atomic_transaction``.

Writes here only flush; the route owns the transaction boundary.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from extensions import db
from models import PosOverrideToken, User
from models.enums import PermissionEnum
from services.logging_core import LoggingCore
from utils.pos_security import (
    OVERRIDE_ACTION_PERMISSIONS,
    OVERRIDE_TOKEN_TTL_SECONDS,
    new_override_nonce,
    verify_override_token_signature,
)
from utils.tenanting import get_active_tenant_id, scoped_user_query, tenant_query


class PosOverrideError(Exception):
    """Raised when an override is required/invalid — routes map this to 403."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PosOverrideService:
    @staticmethod
    def _find_supervisor_by_pin(*, pin: str, cashier) -> User | None:
        candidates = scoped_user_query(user=cashier, active_only=True).filter(
            User.supervisor_pin_hash.isnot(None),
            User.id != cashier.id,
        )
        for candidate in candidates.all():
            if not candidate.has_permission(PermissionEnum.POS_AUTHORIZE_OVERRIDE):
                continue
            if candidate.check_supervisor_pin(pin):
                return candidate
        return None

    @staticmethod
    def authorize_with_pin(*, pin: str, action: str, cashier, session=None) -> PosOverrideToken:
        """Validate a supervisor PIN and issue a one-time override token row."""
        if action not in OVERRIDE_ACTION_PERMISSIONS:
            raise ValueError("إجراء التفويض غير معروف.")
        if not pin:
            raise ValueError("الرمز السري للمشرف مطلوب.")
        tenant_id = get_active_tenant_id(cashier)
        if not tenant_id:
            raise ValueError("لا توجد شركة نشطة.")

        supervisor = PosOverrideService._find_supervisor_by_pin(pin=pin, cashier=cashier)
        session_id = getattr(session, "id", None)
        if supervisor is None:
            LoggingCore.log_audit(
                "pos_override_denied",
                "pos",
                session_id,
                {"action": action, "cashier_user_id": cashier.id},
                severity="medium",
            )
            raise PosOverrideError("الرمز السري غير صالح أو ليس لدى المشرف صلاحية التفويض.")

        token_row = PosOverrideToken(
            tenant_id=int(tenant_id),
            action=action,
            cashier_user_id=cashier.id,
            supervisor_user_id=supervisor.id,
            session_id=session_id,
            nonce=new_override_nonce(),
            expires_at=_utcnow() + timedelta(seconds=OVERRIDE_TOKEN_TTL_SECONDS),
        )
        db.session.add(token_row)
        db.session.flush()
        LoggingCore.log_audit(
            "pos_override_granted",
            "pos_override_tokens",
            token_row.id,
            {
                "action": action,
                "cashier_user_id": cashier.id,
                "supervisor_user_id": supervisor.id,
                "session_id": session_id,
            },
            severity="medium",
        )
        return token_row

    @staticmethod
    def consume_override_token(*, token_str: str, action: str, user) -> int:
        """Validate + burn a presented override token. Returns supervisor_user_id."""
        parts = str(token_str or "").split(".")
        if len(parts) != 3 or not parts[0].isdigit():
            raise PosOverrideError("رمز التفويض غير صالح.")
        token_row = (
            tenant_query(PosOverrideToken, user=user)
            .filter(PosOverrideToken.id == int(parts[0]))
            .first()
        )
        if token_row is None or token_row.nonce != parts[1]:
            raise PosOverrideError("رمز التفويض غير صالح.")
        if token_row.action != action or token_row.cashier_user_id != user.id:
            raise PosOverrideError("رمز التفويض لا يطابق هذا الإجراء.")
        if token_row.used_at is not None:
            raise PosOverrideError("تم استخدام رمز التفويض مسبقاً.")
        if token_row.is_expired():
            raise PosOverrideError("انتهت صلاحية رمز التفويض — اطلب تفويضاً جديداً.")
        if not verify_override_token_signature(token_row, token_str):
            raise PosOverrideError("رمز التفويض غير صالح.")
        token_row.used_at = _utcnow()
        db.session.flush()
        return token_row.supervisor_user_id

    @staticmethod
    def require_permission_or_override(*, user, action: str, override_token: str | None = None) -> int | None:
        """Gate a privileged POS action.

        Returns ``None`` when the acting user holds the action's permission;
        otherwise consumes the override token and returns the authorizing
        supervisor's user id. Raises ``PosOverrideError`` (403) when neither
        path succeeds.
        """
        permission = OVERRIDE_ACTION_PERMISSIONS.get(action)
        if permission is None:
            raise ValueError("إجراء التفويض غير معروف.")
        if user.has_permission(permission):
            return None
        if not override_token:
            raise PosOverrideError("يتطلب هذا الإجراء تفويض مشرف.")
        return PosOverrideService.consume_override_token(token_str=override_token, action=action, user=user)
