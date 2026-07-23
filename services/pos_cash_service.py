"""POS Phase 3 — pay-ins / pay-outs against the session cash drawer.

Every movement posts an immediate balanced GL journal via ``post_or_fail``:
  - pay_out: Dr MISC_EXPENSE (petty-cash / misc, fallback 6500) / Cr cash
  - pay_in : Dr cash / Cr MISC_EXPENSE (exact reverse)

Amounts are tenant base currency, strict ``Decimal`` quantized to 0.001.
Movement totals are folded into the session (and active shift) expected
drawer via ``total_pay_ins`` / ``total_pay_outs``.

Writes here only flush; the route owns the transaction boundary.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models import PosCashMovement
from services.gl_posting import post_or_fail
from services.gl_service import GLService
from services.logging_core import LoggingCore
from utils.gl_reference_types import GLRef
from utils.pos_helpers import resolve_pos_cash_account_code
from utils.tenanting import get_active_tenant_id, tenant_query

_AED_QUANTUM = Decimal("0.001")


class PosCashMovementService:
    @staticmethod
    def _post_gl(movement: PosCashMovement, session, user):
        tenant_id = movement.tenant_id
        amount = Decimal(str(movement.amount))
        cash_code = resolve_pos_cash_account_code(tenant_id, session.branch_id)
        misc_code = GLService.get_account_code_for_concept(
            "MISC_EXPENSE",
            tenant_id=tenant_id,
            branch_id=session.branch_id,
            fallback_key="misc_expense",
        )
        label = "إيداع نقدي" if movement.movement_type == PosCashMovement.TYPE_PAY_IN else "سحب نقدي"
        description = f"{label} POS — جلسة {session.session_number}: {movement.reason}"
        if movement.movement_type == PosCashMovement.TYPE_PAY_OUT:
            lines = [
                {
                    "account": misc_code,
                    "concept_code": "MISC_EXPENSE",
                    "debit": amount,
                    "credit": 0,
                    "description": description,
                },
                {
                    "account": cash_code,
                    "concept_code": "CASH",
                    "debit": 0,
                    "credit": amount,
                    "description": description,
                },
            ]
        else:
            lines = [
                {
                    "account": cash_code,
                    "concept_code": "CASH",
                    "debit": amount,
                    "credit": 0,
                    "description": description,
                },
                {
                    "account": misc_code,
                    "concept_code": "MISC_EXPENSE",
                    "debit": 0,
                    "credit": amount,
                    "description": description,
                },
            ]
        return post_or_fail(
            lines,
            description=description,
            reference_type=GLRef.POS_CASH_MOVEMENT,
            reference_id=movement.id,
            branch_id=session.branch_id,
            user_id=user.id,
            tenant_id=tenant_id,
        )

    @staticmethod
    def create_movement(
        *,
        user,
        session,
        shift=None,
        movement_type: str,
        amount,
        reason: str,
        authorized_by_user_id: int | None = None,
    ) -> PosCashMovement:
        if movement_type not in PosCashMovement.TYPES:
            raise ValueError("نوع الحركة النقدية غير صالح.")
        amt = Decimal(str(amount or "0")).quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP)
        if amt <= Decimal("0"):
            raise ValueError("مبلغ الحركة يجب أن يكون أكبر من صفر.")
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("سبب الحركة النقدية مطلوب.")

        tenant_id = get_active_tenant_id(user) or session.tenant_id
        movement = PosCashMovement(
            tenant_id=int(tenant_id),
            branch_id=session.branch_id,
            user_id=user.id,
            session_id=session.id,
            shift_id=getattr(shift, "id", None),
            authorized_by_user_id=authorized_by_user_id,
            movement_type=movement_type,
            amount=amt,
            reason=reason[:255],
        )
        db.session.add(movement)
        db.session.flush()

        entry = PosCashMovementService._post_gl(movement, session, user)
        movement.gl_entry_id = entry.id if entry is not None else None

        field = "total_pay_ins" if movement_type == PosCashMovement.TYPE_PAY_IN else "total_pay_outs"
        session_total = Decimal(str(getattr(session, field, None) or 0)) + amt
        setattr(session, field, session_total)
        if shift is not None and getattr(shift, "id", None):
            shift_total = Decimal(str(getattr(shift, field, None) or 0)) + amt
            setattr(shift, field, shift_total)
        db.session.flush()

        LoggingCore.log_audit(
            f"pos_{movement_type}",
            "pos_cash_movements",
            movement.id,
            {
                "session_id": session.id,
                "shift_id": movement.shift_id,
                "amount": float(amt),
                "reason": movement.reason,
                "cashier_user_id": user.id,
                "supervisor_user_id": authorized_by_user_id,
            },
            severity="medium",
        )
        return movement

    @staticmethod
    def list_movements(*, user, session, limit: int = 100) -> list[PosCashMovement]:
        if not session:
            return []
        limit = max(1, min(int(limit or 100), 200))
        return (
            tenant_query(PosCashMovement, user=user)
            .filter(PosCashMovement.session_id == session.id)
            .order_by(PosCashMovement.id.desc())
            .limit(limit)
            .all()
        )
