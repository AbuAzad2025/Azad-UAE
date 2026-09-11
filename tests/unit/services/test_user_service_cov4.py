"""Coverage-4 for services.user_service — fallback/else arcs (real paths)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.user_service import UserService


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield
        db_session.rollback()


class TestSimpleLookups:
    def test_get_tenant_none(self):
        assert UserService.get_tenant(None) is None
        assert UserService.get_tenant(0) is None

    def test_get_role_zero_is_none(self):
        assert UserService.get_role(0) is None

    def test_two_factor_required_none(self):
        assert UserService.two_factor_required(None) is False

    def test_two_factor_required_non_true_flag(self):
        assert UserService.two_factor_required(MagicMock(two_factor_enabled=1)) is False
        assert UserService.two_factor_required(MagicMock(two_factor_enabled=True)) is True

    def test_totp_uri_none_when_no_secret(self):
        assert UserService.totp_provisioning_uri(MagicMock(totp_secret=None)) is None

    def test_qr_none_when_no_uri(self, mocker):
        mocker.patch.object(UserService, "totp_provisioning_uri", return_value=None)
        assert UserService.two_factor_qr_data_uri(MagicMock()) is None

    def test_verify_totp_rejects(self):
        assert UserService.verify_totp(None, "123456") is False
        assert UserService.verify_totp(MagicMock(totp_secret=None), "123456") is False
        assert UserService.verify_totp(MagicMock(totp_secret="ABC"), "12 34") is False
        assert UserService.verify_totp(MagicMock(totp_secret="ABC"), "abcdef") is False

    def test_verify_totp_exception_returns_false(self, mocker):
        import pyotp

        user = MagicMock(totp_secret="JBSWY3DPEHPK3PXP")
        mocker.patch.object(pyotp.TOTP, "verify", side_effect=RuntimeError("boom"))
        assert UserService.verify_totp(user, "123456") is False

    def test_totp_roundtrip_and_qr(self, mocker):
        import pyotp

        user = MagicMock(totp_secret="JBSWY3DPEHPK3PXP", username="u1", email="")
        uri = UserService.totp_provisioning_uri(user)
        assert uri.startswith("otpauth://")
        code = pyotp.TOTP("JBSWY3DPEHPK3PXP").now()
        assert UserService.verify_totp(user, code) is True
        data_uri = UserService.two_factor_qr_data_uri(user)
        assert data_uri.startswith("data:image/png;base64,")

    def test_generate_and_toggle_two_factor(self, db_session, sample_role):
        from models import User

        user = User(
            username="cov4_2fa_user", full_name="Cov4", email="c4@example.com", phone="",
            role_id=sample_role.id,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()
        secret = UserService.generate_totp_secret(user)
        assert secret
        UserService.enable_two_factor(user)
        assert user.two_factor_enabled is True
        assert UserService.two_factor_required(user) is True
        UserService.disable_two_factor(user)
        assert user.two_factor_enabled is False
        assert user.totp_secret is None


class TestBranchAndTenantHelpers:
    def test_available_branches_no_tenant_no_scope(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.branching.branch_scope_id_for", return_value=None)
        from models import Branch

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = ["b"]
        mocker.patch.object(Branch, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert UserService.available_branches(MagicMock()) == ["b"]

    def test_count_sales_no_tenant(self, mocker):
        from models import Sale

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 4
        mocker.patch.object(Sale, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert UserService.count_sales_for_seller(1, None) == 4

    def test_create_user_minimal(self):
        user = UserService.create_user("cov4_min_user", "Min User")
        assert user.username == "cov4_min_user"
        assert user.tenant_id is None

    def test_tenant_branches_without_tid(self, mocker):
        from models import Branch

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = ["x"]
        mocker.patch.object(Branch, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert UserService.tenant_branches(None) == ["x"]

    def test_profile_context_without_tid(self, db_session, sample_role):
        from models import User

        user = User(
            username="cov4_prof_user", full_name="Prof", email="p@example.com", phone="",
            role_id=sample_role.id,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()
        ctx = UserService.user_profile_context(user.id, None)
        assert ctx["stats"]["sales_count"] == 0
        assert ctx["stats"]["payments_count"] == 0
        assert ctx["recent_sales"] == []
