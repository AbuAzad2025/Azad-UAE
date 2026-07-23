"""POS Phase 3 service tests — session tokens, supervisor PIN overrides,
blind-close expected-balance math, mixed-currency conversion, and pay-in/out
GL posting. Real ``db_session`` + ``sample_*`` fixtures per convention.

NOTE: db-backed tests must NOT wrap calls in a nested ``app.app_context()`` —
Flask-SQLAlchemy scopes the session per app context, so a nested context
would hide uncommitted fixture rows. The ``db_session`` fixture already
provides the app context.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.pos_session import PosSession
from services.pos_cash_service import PosCashMovementService
from services.pos_override_service import PosOverrideError, PosOverrideService
from utils.pos_helpers import close_pos_session
from utils.pos_security import (
    OVERRIDE_TOKEN_TTL_SECONDS,
    can_view_pos_expected,
    issue_pos_session_token,
    sign_override_token,
    verify_override_token_signature,
    verify_pos_session_token,
)


# ─── Session tokens ───


class TestSessionToken:
    @staticmethod
    def _session(terminal_id="TERM-1", user_id=7, session_id=11):
        return SimpleNamespace(id=session_id, user_id=user_id, terminal_id=terminal_id)

    def test_valid_token_passes(self, app):
        with app.app_context():
            session = self._session()
            token = issue_pos_session_token(session.id, session.user_id, session.terminal_id)
            assert verify_pos_session_token(session, token) is True

    def test_wrong_terminal_rejected(self, app):
        with app.app_context():
            session = self._session()
            token = issue_pos_session_token(session.id, session.user_id, "OTHER-TERM")
            assert verify_pos_session_token(session, token) is False

    def test_wrong_user_rejected(self, app):
        with app.app_context():
            session = self._session()
            token = issue_pos_session_token(session.id, 999, session.terminal_id)
            assert verify_pos_session_token(session, token) is False

    def test_tampered_token_rejected(self, app):
        with app.app_context():
            session = self._session()
            token = issue_pos_session_token(session.id, session.user_id, session.terminal_id)
            tampered = token[:-2] + ("00" if not token.endswith("00") else "ff")
            assert verify_pos_session_token(session, tampered) is False

    def test_missing_token_or_terminal_rejected(self, app):
        with app.app_context():
            assert verify_pos_session_token(self._session(), None) is False
            assert verify_pos_session_token(self._session(terminal_id=None), "abc") is False


# ─── Supervisor PIN on User ───


class TestSupervisorPin:
    def test_pin_roundtrip(self, db_session, sample_user):
        sample_user.set_supervisor_pin("4321")
        db_session.flush()
        assert sample_user.check_supervisor_pin("4321") is True
        assert sample_user.check_supervisor_pin("1234") is False

    def test_unset_pin_never_matches(self, db_session, sample_user):
        sample_user.supervisor_pin_hash = None
        assert sample_user.check_supervisor_pin("4321") is False
        assert sample_user.check_supervisor_pin(None) is False


# ─── Override service lifecycle ───


def _make_supervisor(db_session, sample_tenant, *, with_permission=True, pin="7788"):
    import uuid

    from models import Permission, Role, User

    unique = str(uuid.uuid4())[:8]
    role = Role(name=f"Sup {unique}", slug=f"sup-{unique}", is_active=True)
    if with_permission:
        perm = db_session.query(Permission).filter_by(code="pos_authorize_override").first()
        if perm is None:
            perm = Permission(
                code="pos_authorize_override",
                name="pos_authorize_override",
                name_ar="pos_authorize_override",
                category="pos",
            )
            db_session.add(perm)
            db_session.flush()
        role.permissions.append(perm)
    db_session.add(role)
    db_session.flush()
    supervisor = User(
        username=f"sup-{unique}",
        email=f"sup-{unique}@example.com",
        full_name="Supervisor",
        tenant_id=sample_tenant.id,
        role_id=role.id,
    )
    supervisor.set_password("password123")
    supervisor.set_supervisor_pin(pin)
    db_session.add(supervisor)
    db_session.flush()
    return supervisor


class TestAuthorizeWithPin:
    def test_valid_pin_with_permission_issues_token(self, db_session, sample_tenant, sample_user, mocker):
        supervisor = _make_supervisor(db_session, sample_tenant)
        audit = mocker.patch("services.pos_override_service.LoggingCore.log_audit")
        token_row = PosOverrideService.authorize_with_pin(pin="7788", action="pay_out", cashier=sample_user)
        assert token_row.id is not None
        assert token_row.supervisor_user_id == supervisor.id
        assert token_row.cashier_user_id == sample_user.id
        assert token_row.used_at is None
        # Audit trail names BOTH actors.
        grant = [c for c in audit.call_args_list if c.args[0] == "pos_override_granted"]
        assert grant, "expected pos_override_granted audit row"
        changes = grant[0].args[3]
        assert changes["cashier_user_id"] == sample_user.id
        assert changes["supervisor_user_id"] == supervisor.id

    def test_signed_token_roundtrip(self, db_session, sample_tenant, sample_user):
        _make_supervisor(db_session, sample_tenant)
        token_row = PosOverrideService.authorize_with_pin(pin="7788", action="void_line", cashier=sample_user)
        token = sign_override_token(token_row)
        assert verify_override_token_signature(token_row, token) is True
        assert verify_override_token_signature(token_row, token[:-2] + "00") is False

    def test_wrong_pin_denied_and_audited(self, db_session, sample_tenant, sample_user, mocker):
        _make_supervisor(db_session, sample_tenant)
        audit = mocker.patch("services.pos_override_service.LoggingCore.log_audit")
        with pytest.raises(PosOverrideError):
            PosOverrideService.authorize_with_pin(pin="0000", action="pay_out", cashier=sample_user)
        assert any(c.args[0] == "pos_override_denied" for c in audit.call_args_list)

    def test_pin_from_user_without_permission_rejected(self, db_session, sample_tenant, sample_user):
        _make_supervisor(db_session, sample_tenant, with_permission=False, pin="6655")
        with pytest.raises(PosOverrideError):
            PosOverrideService.authorize_with_pin(pin="6655", action="pay_out", cashier=sample_user)

    def test_unknown_action_rejected(self, db_session, sample_user):
        with pytest.raises(ValueError):
            PosOverrideService.authorize_with_pin(pin="7788", action="nuke", cashier=sample_user)

    def test_self_authorization_impossible(self, db_session, sample_tenant):
        """A supervisor cannot authorize their OWN action with their own PIN."""
        supervisor = _make_supervisor(db_session, sample_tenant)
        with pytest.raises(PosOverrideError):
            PosOverrideService.authorize_with_pin(pin="7788", action="pay_out", cashier=supervisor)


class TestConsumeOverrideToken:
    def _issue(self, db_session, sample_tenant, cashier, action="pay_out"):
        supervisor = _make_supervisor(db_session, sample_tenant)
        token_row = PosOverrideService.authorize_with_pin(pin="7788", action=action, cashier=cashier)
        return token_row, sign_override_token(token_row), supervisor

    def test_valid_token_consumed_once(self, db_session, sample_tenant, sample_user):
        token_row, token, supervisor = self._issue(db_session, sample_tenant, sample_user)
        supervisor_id = PosOverrideService.consume_override_token(
            token_str=token, action="pay_out", user=sample_user
        )
        assert supervisor_id == supervisor.id
        assert token_row.used_at is not None
        # Single-use: second consumption rejected.
        with pytest.raises(PosOverrideError, match="مسبقاً"):
            PosOverrideService.consume_override_token(token_str=token, action="pay_out", user=sample_user)

    def test_expired_token_rejected(self, db_session, sample_tenant, sample_user):
        token_row, token, _ = self._issue(db_session, sample_tenant, sample_user)
        token_row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.flush()
        with pytest.raises(PosOverrideError, match="صلاحية"):
            PosOverrideService.consume_override_token(token_str=token, action="pay_out", user=sample_user)

    def test_wrong_action_rejected(self, db_session, sample_tenant, sample_user):
        _, token, _ = self._issue(db_session, sample_tenant, sample_user, action="pay_out")
        with pytest.raises(PosOverrideError):
            PosOverrideService.consume_override_token(token_str=token, action="void_line", user=sample_user)

    def test_wrong_cashier_rejected(self, db_session, sample_tenant, sample_user):
        _, token, _ = self._issue(db_session, sample_tenant, sample_user)
        other = _make_supervisor(db_session, sample_tenant, pin="1122")
        with pytest.raises(PosOverrideError):
            PosOverrideService.consume_override_token(token_str=token, action="pay_out", user=other)

    def test_cross_tenant_token_invisible(self, db_session, sample_tenant, sample_user):
        """A token from tenant A cannot be consumed while scoped to tenant B."""
        import uuid

        from models import Tenant

        _, token, _ = self._issue(db_session, sample_tenant, sample_user)
        unique = str(uuid.uuid4())[:8]
        other_tenant = Tenant(
            name=f"Other Co {unique}",
            name_ar="شركة أخرى",
            slug=f"other-co-{unique}",
            email=f"other-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(other_tenant)
        db_session.flush()
        other_tenant_supervisor = _make_supervisor(db_session, sample_tenant, pin="9090")
        other_tenant_supervisor.tenant_id = other_tenant.id
        db_session.flush()
        with pytest.raises(PosOverrideError):
            PosOverrideService.consume_override_token(
                token_str=token, action="pay_out", user=other_tenant_supervisor
            )


class TestRequirePermissionOrOverride:
    def test_user_with_permission_needs_no_token(self, db_session, sample_tenant):
        from models import Permission

        supervisor = _make_supervisor(db_session, sample_tenant)
        # The action permission is separate from pos_authorize_override; grant
        # it here for the permission-pass case.
        perm = db_session.query(Permission).filter_by(code="pos_pay_in_out").first()
        if perm is None:
            perm = Permission(code="pos_pay_in_out", name="p", name_ar="p", category="pos")
            db_session.add(perm)
            db_session.flush()
        supervisor.role.permissions.append(perm)
        db_session.flush()
        assert PosOverrideService.require_permission_or_override(user=supervisor, action="pay_out") is None

    def test_without_permission_and_token_denied(self, db_session, sample_user):
        with pytest.raises(PosOverrideError, match="تفويض"):
            PosOverrideService.require_permission_or_override(user=sample_user, action="pay_out")

    def test_ttl_constant_is_sixty_seconds(self):
        assert OVERRIDE_TOKEN_TTL_SECONDS == 60


# ─── Blind-close visibility rule ───


class TestBlindVisibility:
    def test_cashier_hidden_manager_visible(self):
        cashier = SimpleNamespace(
            is_authenticated=True,
            is_owner=False,
            has_permission=lambda code: False,
            role=SimpleNamespace(slug="cashier"),
        )
        manager = SimpleNamespace(
            is_authenticated=True,
            is_owner=False,
            has_permission=lambda code: False,
            role=SimpleNamespace(slug="manager"),
        )
        privileged = SimpleNamespace(
            is_authenticated=True,
            is_owner=False,
            has_permission=lambda code: code == "pos_view_expected",
            role=SimpleNamespace(slug="cashier"),
        )
        assert can_view_pos_expected(cashier) is False
        assert can_view_pos_expected(manager) is True
        assert can_view_pos_expected(privileged) is True


# ─── Expected balance: conversion + change/pay-in/out folding ───


class TestClosePosSessionPhase3:
    @staticmethod
    def _session(**overrides):
        session = MagicMock()
        session.id = 10
        session.tenant_id = 1
        session.branch_id = 2
        session.session_number = "POS-1"
        session.user_id = 5
        session.difference = Decimal("0")
        session.total_change_given = Decimal("0")
        session.total_pay_ins = Decimal("0")
        session.total_pay_outs = Decimal("0")
        session.close = MagicMock()
        for key, value in overrides.items():
            setattr(session, key, value)
        return session

    def test_mixed_currency_cash_tender_converted(self, mocker):
        """USD cash tender is converted to base currency with its own rate."""
        session = self._session()
        usd_cash = MagicMock(
            payment_method="cash",
            amount=Decimal("10"),
            currency="USD",
            exchange_rate=Decimal("3.6725"),
        )
        aed_cash = MagicMock(
            payment_method="cash",
            amount=Decimal("50"),
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        sale = MagicMock(total_amount=Decimal("86.725"), payments=[usd_cash, aed_cash])
        sale_q = MagicMock()
        sale_q.filter.return_value.all.return_value = [sale]
        mocker.patch("models.Sale.query", sale_q)
        close_pos_session(session, Decimal("150"))
        # 10 USD × 3.6725 = 36.725 AED, + 50 AED = 86.725 gross (no change).
        assert session.total_cash_sales == Decimal("86.725")

    def test_change_given_folds_into_gross(self, mocker):
        session = self._session(total_change_given=Decimal("50"))
        cash = MagicMock(payment_method="cash", amount=Decimal("50"), currency="AED", exchange_rate=Decimal("1"))
        sale = MagicMock(total_amount=Decimal("50"), payments=[cash])
        sale_q = MagicMock()
        sale_q.filter.return_value.all.return_value = [sale]
        mocker.patch("models.Sale.query", sale_q)
        close_pos_session(session, Decimal("150"))
        # Net payment rows (50) + change handed back (50) = gross tender 100.
        assert session.total_cash_sales == Decimal("100")

    def test_full_formula_with_real_session(
        self, db_session, sample_tenant, sample_branch, sample_user, mocker
    ):
        """expected = opening + tender − change + pay-ins − pay-outs (Decimal-exact)."""
        session = PosSession(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            user_id=sample_user.id,
            session_number="POS-SES-P3",
            opening_balance_cash=Decimal("100"),
            status=PosSession.STATUS_OPEN,
            total_change_given=Decimal("50"),
            total_pay_ins=Decimal("25"),
            total_pay_outs=Decimal("10"),
        )
        db_session.add(session)
        db_session.flush()
        cash = MagicMock(payment_method="cash", amount=Decimal("150"), currency="AED", exchange_rate=Decimal("1"))
        sale = MagicMock(total_amount=Decimal("150"), payments=[cash])
        sale_q = MagicMock()
        sale_q.filter.return_value.all.return_value = [sale]
        mocker.patch("models.Sale.query", sale_q)
        close_pos_session(session, Decimal("315"))
        # gross = 150 net + 50 change = 200; expected = 100 + 200 − 50 + 25 − 10 = 265
        assert session.total_cash_sales == Decimal("200")
        assert session.expected_balance == Decimal("265.000")
        # counted 315 vs expected 265 → overage +50 (difference != 0 → GL would
        # post; here it runs against the real DB with no sales-period blocks).
        assert session.difference == Decimal("50.000")
        assert session.status == PosSession.STATUS_CLOSED

    def test_difference_gl_lines_balanced_correct_sign(self, mocker):
        """Shortage posts Dr difference / Cr cash with equal amounts."""
        session = self._session()
        session.closed_at = datetime.now(timezone.utc)

        def _close(closing, notes):
            session.difference = Decimal("-7.500")

        session.close.side_effect = _close
        sale_q = MagicMock()
        sale_q.filter.return_value.all.return_value = []
        mocker.patch("models.Sale.query", sale_q)
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder._branch_account_code",
            return_value="1110",
        )
        mocker.patch("services.gl_helpers.get_account", return_value=MagicMock(is_header=False))
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            side_effect=["6500"],
        )
        create_je = mocker.patch("services.gl_service.GLService.create_journal_entry")
        close_pos_session(session, Decimal("92.500"))
        lines = create_je.call_args.kwargs["lines"]
        assert sum(line["debit"] for line in lines) == sum(line["credit"] for line in lines) == Decimal("7.500")
        assert lines[0]["account"] == "6500" and lines[0]["debit"] == Decimal("7.500")
        assert lines[1]["account"] == "1110" and lines[1]["credit"] == Decimal("7.500")


# ─── Pay-ins / pay-outs with real GL ───


def _open_session(db_session, sample_tenant, sample_branch, sample_user):
    import uuid

    session = PosSession(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        user_id=sample_user.id,
        session_number=f"POS-SES-CM-{str(uuid.uuid4())[:8]}",
        opening_balance_cash=Decimal("100"),
        status=PosSession.STATUS_OPEN,
    )
    db_session.add(session)
    db_session.flush()
    return session


class TestCashMovements:
    def test_pay_out_posts_balanced_gl_and_updates_totals(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts, mocker
    ):
        from models import GLJournalEntry, GLJournalLine

        session = _open_session(db_session, sample_tenant, sample_branch, sample_user)
        supervisor = _make_supervisor(db_session, sample_tenant)
        audit = mocker.patch("services.pos_cash_service.LoggingCore.log_audit")
        movement = PosCashMovementService.create_movement(
            user=sample_user,
            session=session,
            movement_type="pay_out",
            amount=Decimal("40.500"),
            reason="Petty cash for supplies",
            authorized_by_user_id=supervisor.id,
        )
        db_session.flush()
        assert movement.gl_entry_id is not None
        entry = db_session.get(GLJournalEntry, movement.gl_entry_id)
        assert entry is not None
        assert entry.total_debit == entry.total_credit == Decimal("40.500")
        lines = db_session.query(GLJournalLine).filter_by(entry_id=entry.id).all()
        assert len(lines) == 2
        debit_line = next(line for line in lines if line.debit > 0)
        credit_line = next(line for line in lines if line.credit > 0)
        # Dr expense / Cr cash (exact double-entry).
        assert debit_line.account_id != credit_line.account_id
        assert Decimal(str(session.total_pay_outs)) == Decimal("40.500")
        assert Decimal(str(session.total_pay_ins)) == Decimal("0")
        # Audit names BOTH actors.
        changes = audit.call_args.args[3]
        assert changes["cashier_user_id"] == sample_user.id
        assert changes["supervisor_user_id"] == supervisor.id

    def test_pay_in_posts_reverse_gl(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        from models import GLJournalLine

        session = _open_session(db_session, sample_tenant, sample_branch, sample_user)
        movement = PosCashMovementService.create_movement(
            user=sample_user,
            session=session,
            movement_type="pay_in",
            amount=Decimal("60"),
            reason="Owner float top-up",
        )
        db_session.flush()
        lines = db_session.query(GLJournalLine).filter_by(entry_id=movement.gl_entry_id).all()
        assert sum(Decimal(str(line.debit)) for line in lines) == Decimal("60.000")
        assert sum(Decimal(str(line.credit)) for line in lines) == Decimal("60.000")
        assert Decimal(str(session.total_pay_ins)) == Decimal("60.000")

    def test_validation_rejects_bad_input(self, db_session, sample_tenant, sample_branch, sample_user):
        session = _open_session(db_session, sample_tenant, sample_branch, sample_user)
        with pytest.raises(ValueError):
            PosCashMovementService.create_movement(
                user=sample_user, session=session, movement_type="sideways", amount=Decimal("5"), reason="x"
            )
        with pytest.raises(ValueError):
            PosCashMovementService.create_movement(
                user=sample_user, session=session, movement_type="pay_in", amount=Decimal("0"), reason="x"
            )
        with pytest.raises(ValueError):
            PosCashMovementService.create_movement(
                user=sample_user, session=session, movement_type="pay_in", amount=Decimal("5"), reason=" "
            )

    def test_list_scoped_to_session_and_tenant(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        session = _open_session(db_session, sample_tenant, sample_branch, sample_user)
        other_session = _open_session(db_session, sample_tenant, sample_branch, sample_user)
        PosCashMovementService.create_movement(
            user=sample_user, session=session, movement_type="pay_in", amount=Decimal("10"), reason="a"
        )
        PosCashMovementService.create_movement(
            user=sample_user, session=other_session, movement_type="pay_out", amount=Decimal("5"), reason="b"
        )
        listed = PosCashMovementService.list_movements(user=sample_user, session=session)
        assert len(listed) == 1
        assert listed[0].session_id == session.id
        assert listed[0].movement_type == "pay_in"
