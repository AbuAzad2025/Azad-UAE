"""Gap coverage for models/pos_cash_movement.py — to_dict branches and repr."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from models.pos_cash_movement import PosCashMovement


def _movement(**kwargs):
    params = {
        "tenant_id": 1,
        "branch_id": 1,
        "user_id": 1,
        "session_id": 1,
        "movement_type": "pay_in",
        "amount": Decimal("50.000"),
        "reason": "Float top-up",
    }
    params.update(kwargs)
    return PosCashMovement(**params)


class TestPosCashMovementDict:
    def test_full_dict(self):
        now = datetime.now(UTC)
        move = _movement(shift_id=9, authorized_by_user_id=4, gl_entry_id=11)
        move.id = 5
        move.created_at = now
        data = move.to_dict()
        assert data["id"] == 5
        assert data["shift_id"] == 9
        assert data["amount"] == 50.0
        assert data["reason"] == "Float top-up"
        assert data["authorized_by_user_id"] == 4
        assert data["gl_entry_id"] == 11
        assert data["created_at"] == now.isoformat()

    def test_none_fallbacks(self):
        move = _movement(amount=None, reason=None)
        move.shift_id = None
        move.authorized_by_user_id = None
        move.gl_entry_id = None
        move.created_at = None
        data = move.to_dict()
        assert data["amount"] == 0
        assert data["reason"] == ""
        assert data["shift_id"] is None
        assert data["created_at"] is None

    def test_repr(self):
        move = _movement(movement_type="pay_out", amount=Decimal("20"))
        move.session_id = 8
        text = repr(move)
        assert "pay_out" in text
        assert "session=8" in text

    def test_type_constants(self):
        assert PosCashMovement.TYPE_PAY_IN == "pay_in"
        assert PosCashMovement.TYPE_PAY_OUT == "pay_out"
        assert set(PosCashMovement.TYPES) == {"pay_in", "pay_out"}

    def test_persist(self, db_session, sample_tenant, sample_user, sample_branch):
        from models.pos_session import PosSession

        session = PosSession(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            user_id=sample_user.id,
            session_number="MOVE-COV3-1",
        )
        db_session.add(session)
        db_session.flush()
        move = PosCashMovement(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            user_id=sample_user.id,
            session_id=session.id,
            movement_type=PosCashMovement.TYPE_PAY_OUT,
            amount=Decimal("15.000"),
            reason="drop",
        )
        db_session.add(move)
        db_session.flush()
        assert move.to_dict()["movement_type"] == "pay_out"
