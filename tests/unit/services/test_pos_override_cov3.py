"""Coverage boost for services/pos_override_service.py.

Targets: authorize pin-empty / no-tenant / session-none, consume malformed /
nonce-mismatch / missing-row / bad-signature, require unknown-action /
token-success path. Real service calls; supervisor rows are real DB rows.
"""

from __future__ import annotations

import uuid

import pytest

from services.pos_override_service import PosOverrideError, PosOverrideService


def _make_supervisor(db_session, sample_tenant, *, with_permission=True, pin="7788"):
    from models import Permission, Role, User

    unique = uuid.uuid4().hex[:8]
    role = Role(name=f"SupC3 {unique}", slug=f"supc3-{unique}", is_active=True)
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
    sup = User(
        username=f"supc3-{unique}",
        email=f"supc3-{unique}@example.com",
        full_name="Sup",
        tenant_id=sample_tenant.id,
        role_id=role.id,
    )
    sup.set_password("password123")
    sup.set_supervisor_pin(pin)
    db_session.add(sup)
    db_session.flush()
    return sup


class TestAuthorizeEdgePaths:
    def test_empty_pin_rejected(self, db_session, sample_user):
        with pytest.raises(ValueError):
            PosOverrideService.authorize_with_pin(pin="", action="pay_out", cashier=sample_user)

    def test_no_active_tenant_rejected(self, db_session, sample_user, mocker):
        mocker.patch("services.pos_override_service.get_active_tenant_id", return_value=None)
        with pytest.raises(ValueError):
            PosOverrideService.authorize_with_pin(pin="1234", action="pay_out", cashier=sample_user)

    def test_session_none_stored_as_none(self, db_session, sample_tenant, sample_user):
        _make_supervisor(db_session, sample_tenant)
        row = PosOverrideService.authorize_with_pin(pin="7788", action="pay_out", cashier=sample_user, session=None)
        assert row.session_id is None

    def test_unknown_action_rejected(self, db_session, sample_user):
        with pytest.raises(ValueError):
            PosOverrideService.authorize_with_pin(pin="x", action="nope", cashier=sample_user)


class TestConsumeEdgePaths:
    def _issue(self, db_session, sample_tenant, cashier, action="pay_out"):
        from utils.pos_security import sign_override_token

        sup = _make_supervisor(db_session, sample_tenant)
        row = PosOverrideService.authorize_with_pin(pin="7788", action=action, cashier=cashier)
        return row, sign_override_token(row), sup

    def test_malformed_tokens_rejected(self, db_session, sample_user):
        for bad in ("", "abc", "1.2", "x.y.z", "notanint.nonce.sig"):
            with pytest.raises(PosOverrideError):
                PosOverrideService.consume_override_token(token_str=bad, action="pay_out", user=sample_user)

    def test_missing_row_rejected(self, db_session, sample_tenant, sample_user):
        _make_supervisor(db_session, sample_tenant)
        with pytest.raises(PosOverrideError):
            PosOverrideService.consume_override_token(
                token_str="99999999.deadbeef.deadbeef", action="pay_out", user=sample_user
            )

    def test_nonce_mismatch_rejected(self, db_session, sample_tenant, sample_user):
        from utils.pos_security import sign_override_token

        row, token, _ = self._issue(db_session, sample_tenant, sample_user)
        parts = token.split(".")
        tampered = f"{parts[0]}.wrongnonce.{parts[2]}"
        assert row.nonce != "wrongnonce"
        with pytest.raises(PosOverrideError):
            PosOverrideService.consume_override_token(token_str=tampered, action="pay_out", user=sample_user)
        assert sign_override_token(row) == token

    def test_bad_signature_rejected(self, db_session, sample_tenant, sample_user):
        row, token, _ = self._issue(db_session, sample_tenant, sample_user)
        parts = token.split(".")
        bad_sig = parts[2][:-2] + ("00" if not parts[2].endswith("00") else "ff")
        with pytest.raises(PosOverrideError):
            PosOverrideService.consume_override_token(
                token_str=f"{parts[0]}.{parts[1]}.{bad_sig}", action="pay_out", user=sample_user
            )


class TestRequirePermissionOrOverride:
    def test_unknown_action_raises_value_error(self, db_session, sample_user):
        with pytest.raises(ValueError):
            PosOverrideService.require_permission_or_override(user=sample_user, action="nope")

    def test_token_success_returns_supervisor(self, db_session, sample_tenant, sample_user):
        from utils.pos_security import sign_override_token

        sup = _make_supervisor(db_session, sample_tenant)
        row = PosOverrideService.authorize_with_pin(pin="7788", action="pay_out", cashier=sample_user)
        token = sign_override_token(row)
        sample_user.has_permission = lambda code: False
        # force permission miss regardless of seeded role perms
        from unittest.mock import MagicMock

        sample_user.has_permission = MagicMock(return_value=False)
        got = PosOverrideService.require_permission_or_override(
            user=sample_user, action="pay_out", override_token=token
        )
        assert got == sup.id
