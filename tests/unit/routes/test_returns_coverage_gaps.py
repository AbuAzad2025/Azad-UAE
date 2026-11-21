"""Idempotency branches of the returns API that the route suites never reached."""

from __future__ import annotations

from contextlib import ExitStack, nullcontext
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def returns_app(app_factory, bypass_permission_auth):
    from routes.returns import returns_bp

    return app_factory(returns_bp)


def _patches():
    stack = ExitStack()
    stack.enter_context(patch("routes.returns.render_template", return_value="ok"))
    stack.enter_context(patch("routes.returns.tenant_get_or_404"))
    stack.enter_context(patch("routes.returns.LoggingCore.log_audit"))
    stack.enter_context(patch("routes.returns.branch_scope_id", return_value=None))
    stack.enter_context(patch("extensions.limiter.limit", return_value=lambda f: f))
    stack.enter_context(patch("routes.returns.atomic_transaction", return_value=nullcontext()))
    return stack


def _result():
    result = MagicMock()
    result.id = 5
    result.return_number = "RET-005"
    result.refund_amount = Decimal("50")
    result.amount_aed = Decimal("50")
    return result


class TestBeginIdempotency:
    def test_fresh_record(self, returns_app):
        from routes.returns import _begin_idem

        record = MagicMock()
        with (
            returns_app.test_request_context("/returns/api/create", method="POST"),
            patch("routes.returns.get_active_tenant_id", return_value=3),
            patch("routes.returns.hash_request_payload", return_value="hash"),
            patch("routes.returns.IdempotencyService.begin", return_value=(record, None)) as begin,
        ):
            got_record, stored, error = _begin_idem({"sale_id": 10}, "key")
        assert got_record is record and stored is None and error is None
        assert begin.call_args.kwargs["tenant_id"] == 3
        assert begin.call_args.kwargs["endpoint"] == "returns.create"

    def test_in_flight_is_409(self, returns_app):
        from routes.returns import _begin_idem
        from services.idempotency_service import IdempotencyInFlightError

        with (
            returns_app.test_request_context("/returns/api/create", method="POST"),
            patch("routes.returns.get_active_tenant_id", return_value=3),
            patch("routes.returns.hash_request_payload", return_value="hash"),
            patch("routes.returns.IdempotencyService.begin", side_effect=IdempotencyInFlightError),
        ):
            record, stored, error = _begin_idem({"sale_id": 10}, "key")
        assert record is None and stored is None
        assert error[1] == 409

    def test_hash_mismatch_is_422(self, returns_app):
        from routes.returns import _begin_idem
        from services.idempotency_service import IdempotencyHashMismatchError

        with (
            returns_app.test_request_context("/returns/api/create", method="POST"),
            patch("routes.returns.get_active_tenant_id", return_value=3),
            patch("routes.returns.hash_request_payload", return_value="hash"),
            patch("routes.returns.IdempotencyService.begin", side_effect=IdempotencyHashMismatchError),
        ):
            record, stored, error = _begin_idem({"sale_id": 10}, "key")
        assert record is None and stored is None
        assert error[1] == 422

    def test_stored_result_is_replayed(self, returns_app):
        from routes.returns import _begin_idem

        body = {"return_number": "RET-1", "success": True}
        with (
            returns_app.test_request_context("/returns/api/create", method="POST"),
            patch("routes.returns.get_active_tenant_id", return_value=3),
            patch("routes.returns.hash_request_payload", return_value="hash"),
            patch("routes.returns.IdempotencyService.begin", return_value=(None, (body, 201))),
        ):
            record, stored, error = _begin_idem({"sale_id": 10}, "key")
        assert record is None and error is None
        assert stored == (body, 201)


class TestApiCreateIdempotency:
    def test_replay_drops_success_flag(self, returns_app):
        client = returns_app.test_client()
        body = {"return_id": 5, "return_number": "RET-1", "refund_amount": 1, "amount_aed": 1, "success": True}
        with (
            _patches(),
            patch(
                "routes.returns.IdempotencyService.begin",
                return_value=(None, (body, 201)),
            ),
        ):
            resp = client.post(
                "/returns/api/create",
                json={"sale_id": 10, "lines": [{"sale_line_id": 1, "quantity": 1}]},
                headers={"Idempotency-Key": "replay-key"},
            )
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["return_number"] == "RET-1"
        assert "success" not in data
        assert resp.get_json()["meta"]["idempotent_replay"] is True

    def test_successful_create_completes_idem_record(self, returns_app):
        client = returns_app.test_client()
        record = MagicMock()
        with (
            _patches(),
            patch("routes.returns.IdempotencyService.begin", return_value=(record, None)),
            patch("routes.returns.ReturnService.create_return", return_value=_result()),
            patch("routes.returns.IdempotencyService.complete") as complete,
        ):
            resp = client.post(
                "/returns/api/create",
                json={"sale_id": 10, "lines": [{"sale_line_id": 1, "quantity": 1}]},
                headers={"Idempotency-Key": "fresh-key"},
            )
        assert resp.status_code == 200
        complete.assert_called_once()
        assert complete.call_args.args[0] is record
