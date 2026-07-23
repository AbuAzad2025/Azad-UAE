"""POS Phase 3 route tests — session pause/resume, HMAC session tokens,
supervisor PIN override endpoint, drawer open, pay-ins/outs, void-line, and
blind-close response gating. Mocked at the route boundary per convention.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.pos_override_service import PosOverrideError
from tests.unit.routes.test_pos_v2_routes import (
    _mock_session,
    _pos_api_patches,
)
from utils.pos_security import issue_pos_session_token


@pytest.fixture
def pos_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


def _bound_session():
    """Terminal-bound session mock — triggers session-token enforcement."""
    session = _mock_session()
    session.terminal_id = "TERM-1"
    return session


def _token_for(client, session, user_id=42):
    with client.application.app_context():
        return issue_pos_session_token(session.id, user_id, session.terminal_id)


def _override_token_row():
    row = MagicMock()
    row.id = 5
    row.nonce = "ab12cd34"
    row.action = "pay_out"
    row.cashier_user_id = 42
    row.supervisor_user_id = 7
    row.expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
    return row


class TestSessionPauseResume:
    def test_pause_success(self, pos_client):
        session = _mock_session()
        with _pos_api_patches(session=session):
            resp = pos_client.post("/pos/api/session/pause", json={})
        assert resp.status_code == 200
        session.pause.assert_called_once()

    def test_pause_without_session_404(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.post("/pos/api/session/pause", json={})
        assert resp.status_code == 404

    def test_pause_blocked_transition_400(self, pos_client):
        session = _mock_session()
        session.pause.side_effect = ValueError("انتقال غير مسموح")
        with _pos_api_patches(session=session):
            resp = pos_client.post("/pos/api/session/pause", json={})
        assert resp.status_code == 400

    def test_pause_requires_token_on_bound_session(self, pos_client):
        with _pos_api_patches(session=_bound_session()):
            resp = pos_client.post("/pos/api/session/pause", json={})
        assert resp.status_code == 403

    def test_resume_success(self, pos_client):
        session = _mock_session()
        session.status = "paused"
        with _pos_api_patches(session=None, paused_session=session):
            resp = pos_client.post("/pos/api/session/resume", json={})
        assert resp.status_code == 200
        session.resume.assert_called_once()

    def test_resume_without_paused_404(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.post("/pos/api/session/resume", json={})
        assert resp.status_code == 404


class TestSessionTokenEnforcement:
    _CHECKOUT_PAYLOAD = {"lines": [{"product_id": 1, "quantity": 1}], "quick_customer": True}

    def test_checkout_without_token_403(self, pos_client):
        with _pos_api_patches(session=_bound_session()):
            resp = pos_client.post("/pos/api/checkout", json=self._CHECKOUT_PAYLOAD)
        assert resp.status_code == 403

    def test_checkout_wrong_token_403(self, pos_client):
        session = _bound_session()
        with _pos_api_patches(session=session):
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._CHECKOUT_PAYLOAD,
                headers={"X-POS-Session-Token": "f" * 64},
            )
        assert resp.status_code == 403

    def test_checkout_token_for_other_terminal_403(self, pos_client):
        session = _bound_session()
        with pos_client.application.app_context():
            foreign = issue_pos_session_token(session.id, 42, "OTHER-TERM")
        with _pos_api_patches(session=session):
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._CHECKOUT_PAYLOAD,
                headers={"X-POS-Session-Token": foreign},
            )
        assert resp.status_code == 403

    def test_checkout_valid_token_passes(self, pos_client):
        session = _bound_session()
        token = _token_for(pos_client, session)
        with _pos_api_patches(session=session):
            resp = pos_client.post(
                "/pos/api/checkout",
                json=self._CHECKOUT_PAYLOAD,
                headers={"X-POS-Session-Token": token},
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_checkout_token_via_body_accepted(self, pos_client):
        session = _bound_session()
        token = _token_for(pos_client, session)
        payload = {**self._CHECKOUT_PAYLOAD, "session_token": token}
        with _pos_api_patches(session=session):
            resp = pos_client.post("/pos/api/checkout", json=payload)
        assert resp.status_code == 200

    def test_close_without_token_403(self, pos_client):
        with _pos_api_patches(session=_bound_session()):
            resp = pos_client.post("/pos/api/session/close", json={"counted_cash": 100})
        assert resp.status_code == 403

    def test_close_with_token_passes(self, pos_client):
        session = _bound_session()
        session.closed_at = MagicMock(isoformat=MagicMock(return_value="2026-06-01T12:00:00"))
        token = _token_for(pos_client, session)
        with _pos_api_patches(session=session):
            resp = pos_client.post(
                "/pos/api/session/close",
                json={"counted_cash": 100},
                headers={"X-POS-Session-Token": token},
            )
        assert resp.status_code == 200

    def test_cart_park_without_token_403(self, pos_client):
        with _pos_api_patches(session=_bound_session()):
            resp = pos_client.post("/pos/api/carts/park", json={"payload": {"lines": []}})
        assert resp.status_code == 403

    def test_unbound_legacy_session_skips_token(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/checkout", json=self._CHECKOUT_PAYLOAD)
        assert resp.status_code == 200


class TestPausedSessionBlocking:
    def test_checkout_blocked_while_paused(self, pos_client):
        with _pos_api_patches(session=None, paused_session=_mock_session()):
            resp = pos_client.post(
                "/pos/api/checkout",
                json={"lines": [{"product_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 409
        assert "موقوفة" in resp.get_json()["error"]

    def test_cart_park_blocked_while_paused(self, pos_client):
        with _pos_api_patches(session=None, paused_session=_mock_session()):
            resp = pos_client.post("/pos/api/carts/park", json={"payload": {"lines": []}})
        assert resp.status_code == 409


class TestBlindCloseRoutes:
    def test_report_hides_expected_from_cashier(self, pos_client, mock_user):
        mock_user.has_permission.return_value = False
        mock_user.role.slug = "cashier"
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/session/report")
        session = resp.get_json()["session"]
        assert "expected_balance" not in session
        assert "total_cash_sales" not in session
        assert "difference" not in session
        assert session["opening_balance"] == 100.0

    def test_report_shows_expected_to_manager(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/session/report")
        session = resp.get_json()["session"]
        assert session["expected_balance"] == 150.0
        assert "total_cash_sales" in session

    def test_session_current_hides_totals_from_cashier(self, pos_client, mock_user):
        mock_user.has_permission.return_value = False
        mock_user.role.slug = "cashier"
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/session/current")
        session = resp.get_json()["session"]
        assert "total_cash_sales" not in session
        assert "total_sales" not in session

    def test_close_requires_counted_cash(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/session/close", json={})
        assert resp.status_code == 400
        assert "counted_cash" in resp.get_json()["error"]

    def test_close_accepts_counted_cash(self, pos_client):
        closed = _mock_session()
        closed.closed_at = MagicMock(isoformat=MagicMock(return_value="2026-06-01T12:00:00"))
        with _pos_api_patches(session=closed) as _:
            resp = pos_client.post("/pos/api/session/close", json={"counted_cash": 120})
        assert resp.get_json()["success"] is True

    def test_shift_current_blind_for_cashier(self, pos_client, mock_user):
        mock_user.has_permission.return_value = False
        mock_user.role.slug = "cashier"
        shift = MagicMock()
        shift.to_dict.return_value = {"id": 3}
        with _pos_api_patches(), patch("routes.pos._get_active_shift", return_value=shift):
            resp = pos_client.get("/pos/api/shift/current")
        assert resp.status_code == 200
        assert shift.to_dict.call_args.kwargs["include_sensitive"] is False

    def test_shift_reconcile_requires_actual_cash(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/shift/reconcile", json={})
        assert resp.status_code == 400
        assert "actual_cash" in resp.get_json()["error"]


class TestAuthorizeOverrideRoute:
    def test_success_returns_signed_token(self, pos_client):
        row = _override_token_row()
        with (
            _pos_api_patches(),
            patch("routes.pos.PosOverrideService.authorize_with_pin", return_value=row),
        ):
            resp = pos_client.post("/pos/api/authorize-override", json={"pin": "7788", "action": "pay_out"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["expires_in"] == 60
        assert data["override_token"].startswith("5.ab12cd34.")

    def test_wrong_pin_403(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosOverrideService.authorize_with_pin",
                side_effect=PosOverrideError("الرمز السري غير صالح"),
            ),
        ):
            resp = pos_client.post("/pos/api/authorize-override", json={"pin": "0000", "action": "pay_out"})
        assert resp.status_code == 403

    def test_unknown_action_400(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosOverrideService.authorize_with_pin",
                side_effect=ValueError("إجراء التفويض غير معروف."),
            ),
        ):
            resp = pos_client.post("/pos/api/authorize-override", json={"pin": "7788", "action": "nuke"})
        assert resp.status_code == 400

    def test_non_json_415(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/authorize-override", data="not-json")
        assert resp.status_code == 415


class TestDrawerOpenRoute:
    def test_denied_without_override(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosOverrideService.require_permission_or_override",
                side_effect=PosOverrideError("يتطلب هذا الإجراء تفويض مشرف."),
            ),
        ):
            resp = pos_client.post("/pos/api/drawer/open", json={})
        assert resp.status_code == 403

    def test_allowed_with_permission_and_audited(self, pos_client, mock_user):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos.requests.post", return_value=MagicMock(status_code=200)),
            patch("routes.pos.LoggingCore.log_audit") as audit,
        ):
            resp = pos_client.post("/pos/api/drawer/open", json={"reason": "تغيير فكة"})
        assert resp.status_code == 200
        assert resp.get_json()["drawer_kicked"] is True
        call = next(c for c in audit.call_args_list if c.args[0] == "pos_no_sale_drawer")
        changes = call.args[3]
        assert changes["cashier_user_id"] == mock_user.id
        assert changes["supervisor_user_id"] is None

    def test_allowed_with_supervisor_override_audit_names_both(self, pos_client, mock_user):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=7),
            patch("routes.pos.requests.post", return_value=MagicMock(status_code=200)),
            patch("routes.pos.LoggingCore.log_audit") as audit,
        ):
            resp = pos_client.post("/pos/api/drawer/open", json={"override_token": "5.ab.sig"})
        assert resp.status_code == 200
        call = next(c for c in audit.call_args_list if c.args[0] == "pos_no_sale_drawer")
        assert call.args[3]["supervisor_user_id"] == 7
        assert call.args[3]["cashier_user_id"] == mock_user.id

    def test_no_session_403(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.post("/pos/api/drawer/open", json={})
        assert resp.status_code == 403

    def test_hardware_failure_still_succeeds(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos.requests.post", side_effect=ConnectionError("down")),
        ):
            resp = pos_client.post("/pos/api/drawer/open", json={})
        assert resp.status_code == 200
        assert resp.get_json()["drawer_kicked"] is False


class TestCashMovementRoutes:
    def test_pay_out_denied_without_override(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosOverrideService.require_permission_or_override",
                side_effect=PosOverrideError("يتطلب هذا الإجراء تفويض مشرف."),
            ),
        ):
            resp = pos_client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_out", "amount": "50", "reason": "مصاريف"},
            )
        assert resp.status_code == 403

    def test_pay_in_denied_without_override(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosOverrideService.require_permission_or_override",
                side_effect=PosOverrideError("يتطلب هذا الإجراء تفويض مشرف."),
            ),
        ):
            resp = pos_client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_in", "amount": "50", "reason": "إيداع"},
            )
        assert resp.status_code == 403

    def test_pay_out_success_201(self, pos_client):
        movement = MagicMock()
        movement.to_dict.return_value = {"id": 9, "movement_type": "pay_out", "amount": 50.0}
        with (
            _pos_api_patches(),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=7),
            patch("routes.pos.PosCashMovementService.create_movement", return_value=movement) as create,
        ):
            resp = pos_client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_out", "amount": "50", "reason": "مصاريف", "override_token": "5.ab.sig"},
            )
        assert resp.status_code == 201
        assert create.call_args.kwargs["authorized_by_user_id"] == 7
        assert create.call_args.kwargs["movement_type"] == "pay_out"

    def test_invalid_type_400(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/cash-movements", json={"type": "sideways", "amount": "5"})
        assert resp.status_code == 400

    def test_invalid_amount_400(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/cash-movements", json={"type": "pay_in", "amount": "abc"})
        assert resp.status_code == 400

    def test_no_session_403(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_in", "amount": "5", "reason": "x"},
            )
        assert resp.status_code == 403

    def test_list_active_session(self, pos_client):
        movement = MagicMock()
        movement.to_dict.return_value = {"id": 1, "movement_type": "pay_in"}
        with (
            _pos_api_patches(),
            patch("routes.pos.PosCashMovementService.list_movements", return_value=[movement]),
        ):
            resp = pos_client.get("/pos/api/cash-movements")
        assert resp.status_code == 200
        assert resp.get_json()["movements"] == [{"id": 1, "movement_type": "pay_in"}]

    def test_list_other_session_forbidden_for_cashier(self, pos_client, mock_user):
        mock_user.has_permission.return_value = False
        mock_user.role.slug = "cashier"
        with _pos_api_patches():
            resp = pos_client.get("/pos/api/cash-movements?session_id=11")
        assert resp.status_code == 403

    def test_list_other_session_allowed_for_manager(self, pos_client):
        session = _mock_session()
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_get", return_value=session),
            patch("routes.pos.PosCashMovementService.list_movements", return_value=[]),
        ):
            resp = pos_client.get("/pos/api/cash-movements?session_id=11")
        assert resp.status_code == 200


class TestVoidLineRoute:
    def test_denied_without_override(self, pos_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosOverrideService.require_permission_or_override",
                side_effect=PosOverrideError("يتطلب هذا الإجراء تفويض مشرف."),
            ),
        ):
            resp = pos_client.post("/pos/api/carts/5/void-line", json={"product_id": 1})
        assert resp.status_code == 403

    def test_success_and_audit(self, pos_client, mock_user):
        cart = MagicMock()
        cart.id = 5
        cart.to_summary_dict.return_value = {"id": 5, "item_count": 1}
        with (
            _pos_api_patches(),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=7),
            patch("routes.pos.PosCartService.void_line", return_value=cart),
            patch("routes.pos.LoggingCore.log_audit") as audit,
        ):
            resp = pos_client.post("/pos/api/carts/5/void-line", json={"product_id": 1})
        assert resp.status_code == 200
        call = next(c for c in audit.call_args_list if c.args[0] == "pos_void_line")
        assert call.args[3]["cashier_user_id"] == mock_user.id
        assert call.args[3]["supervisor_user_id"] == 7

    def test_missing_line_404(self, pos_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos.PosCartService.void_line", side_effect=LookupError("الصنف غير موجود في السلة.")),
        ):
            resp = pos_client.post("/pos/api/carts/5/void-line", json={"product_id": 99})
        assert resp.status_code == 404


class TestSupervisorPinRoute:
    def test_set_pin_success(self, pos_client, mock_user):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/supervisor-pin", json={"pin": "2468"})
        assert resp.status_code == 200
        mock_user.set_supervisor_pin.assert_called_once_with("2468")

    def test_rejects_non_numeric_pin(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/supervisor-pin", json={"pin": "12ab"})
        assert resp.status_code == 400

    def test_rejects_short_pin(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post("/pos/api/supervisor-pin", json={"pin": "12"})
        assert resp.status_code == 400

    def test_non_supervisor_forbidden(self, pos_client, mock_user):
        mock_user.has_permission.return_value = False
        with (
            _pos_api_patches(),
            patch("utils.decorators.is_global_owner_user", return_value=False),
        ):
            resp = pos_client.post("/pos/api/supervisor-pin", json={"pin": "2468"})
        assert resp.status_code == 403
