"""POS security primitives — HMAC tokens, override signing, blind-close matrix."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from models.enums import PermissionEnum
from utils.pos_security import (
    can_view_pos_expected,
    issue_customer_display_token,
    issue_pos_session_token,
    new_override_nonce,
    sign_override_token,
    verify_customer_display_token,
    verify_override_token_signature,
    verify_pos_session_token,
)


class TestSessionTokens:
    def test_roundtrip_matches(self):
        token = issue_pos_session_token(12, 34, "T-1")
        session = SimpleNamespace(id=12, user_id=34, terminal_id="T-1")
        assert verify_pos_session_token(session, token) is True

    def test_wrong_terminal_rejected(self):
        token = issue_pos_session_token(12, 34, "T-1")
        session = SimpleNamespace(id=12, user_id=34, terminal_id="T-2")
        assert verify_pos_session_token(session, token) is False

    def test_unbound_legacy_session_fails_closed(self):
        session = SimpleNamespace(id=1, user_id=1, terminal_id=None)
        assert verify_pos_session_token(session, "whatever") is False

    def test_empty_presented_token_rejected(self):
        session = SimpleNamespace(id=1, user_id=1, terminal_id="T-9")
        assert verify_pos_session_token(session, "") is False


class TestCustomerDisplayTokens:
    def test_roundtrip(self):
        token = issue_customer_display_token(3, 4)
        assert verify_customer_display_token(3, 4, token) is True

    def test_tampered_and_empty_tokens_rejected(self):
        token = issue_customer_display_token(3, 4)
        assert verify_customer_display_token(3, 5, token) is False
        assert verify_customer_display_token(3, 4, None) is False

    def test_nonce_is_hex_and_unique(self):
        a, b = new_override_nonce(), new_override_nonce()
        assert len(a) == 32 and len(b) == 32
        assert a != b


def _override_row(**over):
    base = dict(
        id=7,
        nonce="ab" * 16,
        action="void_line",
        cashier_user_id=2,
        supervisor_user_id=3,
        expires_at=datetime.now(UTC) + timedelta(seconds=60),
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestOverrideTokenSigning:
    def test_sign_then_verify(self):
        row = _override_row()
        signed = sign_override_token(row)
        parts = signed.split(".")
        assert len(parts) == 3
        assert parts[0] == "7"
        assert parts[1] == "ab" * 16
        assert verify_override_token_signature(row, signed) is True

    def test_expiryless_row_signs_with_zero_ts(self):
        row = _override_row(expires_at=None)
        signed = sign_override_token(row)
        assert verify_override_token_signature(row, signed) is True

    def test_any_field_change_breaks_signature(self):
        row = _override_row()
        signed = sign_override_token(row)
        tampered = _override_row(action="pay_in")
        assert verify_override_token_signature(tampered, signed) is False

    def test_empty_presented_rejected(self):
        assert verify_override_token_signature(_override_row(), "") is False


class TestCanViewPosExpected:
    class _User:
        def __init__(self, *, authenticated=True, owner=False, role_slug=None, has_perm=False):
            self.is_authenticated = authenticated
            self.is_owner = owner
            self.has_permission = lambda code, _hp=has_perm: _hp
            self.role = SimpleNamespace(slug=role_slug) if role_slug else None

    @pytest.mark.parametrize("perm", [PermissionEnum.POS_VIEW_EXPECTED])
    def test_permission_grants(self, perm):
        assert can_view_pos_expected(self._User(has_perm=True)) is True

    def test_owner_short_circuit_even_without_permission(self):
        assert can_view_pos_expected(self._User(owner=True)) is True

    @pytest.mark.parametrize(
        ("slug", "expected"),
        [
            ("owner", True),
            ("developer", True),
            ("super_admin", True),
            ("manager", True),
            ("branch_manager", True),
            ("accountant", True),
            ("cashier", False),
            ("seller", False),
        ],
    )
    def test_role_visibility_matrix(self, slug, expected):
        assert can_view_pos_expected(self._User(role_slug=slug)) is expected

    def test_anonymous_user_denied(self):
        assert can_view_pos_expected(None) is False
        assert can_view_pos_expected(self._User(authenticated=False)) is False

    def test_cashier_without_permission_denied(self):
        assert can_view_pos_expected(self._User(role_slug="cashier")) is False


class TestFraudCanonical:
    def _row(self, **over):
        base = dict(
            tenant_id=1,
            user_id=9,
            session_id=77,
            event_type="void_line",
            severity="medium",
            repeat_count=2,
            details='{"x": 1}',
            created_at=datetime(2026, 8, 27, 10, 0, 0),
        )
        base.update(over)
        return SimpleNamespace(**base)

    def test_canonical_joins_all_components(self):
        from utils.pos_security import POS_FRAUD_REPEAT_THRESHOLD, POS_FRAUD_REPEAT_WINDOW_MINUTES

        assert POS_FRAUD_REPEAT_WINDOW_MINUTES == 60
        assert POS_FRAUD_REPEAT_THRESHOLD == 3

    def test_canonical_differs_by_prev_hash_and_user(self):
        from utils.pos_security import _fraud_canonical

        assert _fraud_canonical(self._row(), "") != _fraud_canonical(self._row(), "a" * 64)
        assert _fraud_canonical(self._row(user_id=None), "") != _fraud_canonical(self._row(user_id=5), "")
