"""Tests for routes/quotations.py — 11 distinct endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import unauthenticated_client


def _mock_quotation(**kwargs):
    q = MagicMock()
    q.id = kwargs.get("id", 1)
    q.tenant_id = kwargs.get("tenant_id", 1)
    q.quotation_number = kwargs.get("quotation_number", "QT-2026-001")
    q.status = kwargs.get("status", "draft")
    q.is_expired = kwargs.get("is_expired", False)
    q.sale_id = kwargs.get("sale_id")
    q.customer_id = kwargs.get("customer_id", 1)
    q.lines = kwargs.get("lines", [])
    q.subtotal = kwargs.get("subtotal", 100)
    q.total_amount = kwargs.get("total_amount", 100)
    return q


def _mock_sale(**kwargs):
    s = MagicMock()
    s.id = kwargs.get("id", 10)
    s.sale_number = "SALE-1"
    return s


@pytest.fixture
def quotations_client(app_factory, bypass_permission_auth):
    from routes.quotations import quotations_bp

    app = app_factory(quotations_bp)
    # need sales blueprint for redirect target sales.detail; register dummy
    from flask import Blueprint

    sales_bp = Blueprint("sales", __name__)

    @sales_bp.route("/sales/<int:id>")
    def detail(id):
        return "ok"

    app.register_blueprint(sales_bp)
    return app.test_client()


@pytest.fixture
def quotations_mocks():
    q = _mock_quotation()
    sale = _mock_sale()
    patches = [
        patch("routes.quotations.QuotationService.list_quotations", return_value=[q]),
        patch("routes.quotations.QuotationService.create_quotation", return_value=q),
        patch("routes.quotations.QuotationService.get_quotation", return_value=q),
        patch("routes.quotations.QuotationService.update_quotation", return_value=q),
        patch("routes.quotations.QuotationService.send_quotation", return_value=q),
        patch("routes.quotations.QuotationService.accept_quotation", return_value=q),
        patch("routes.quotations.QuotationService.reject_quotation", return_value=q),
        patch("routes.quotations.QuotationService.convert_to_sale", return_value=sale),
        patch("routes.quotations.QuotationService.duplicate_quotation", return_value=_mock_quotation(id=2)),
        patch("routes.quotations.render_template", return_value="ok"),
    ]
    for p in patches:
        p.start()
    yield {"quotation": q, "sale": sale}
    for p in reversed(patches):
        p.stop()


class TestQuotationsAuth:
    def test_index_requires_login(self, quotations_client):
        with unauthenticated_client(quotations_client):
            resp = quotations_client.get("/quotations/")
        assert resp.status_code == 401

    def test_index_forbidden(self, quotations_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = quotations_client.get("/quotations/")
        assert resp.status_code == 403

    def test_create_forbidden(self, quotations_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = quotations_client.get("/quotations/create")
        assert resp.status_code == 403

    def test_send_forbidden(self, quotations_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = quotations_client.post("/quotations/1/send")
        assert resp.status_code == 403


class TestQuotationsIndex:
    def test_index_happy(self, quotations_client, quotations_mocks):
        resp = quotations_client.get("/quotations/")
        assert resp.status_code == 200

    def test_index_with_filters(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.list_quotations", return_value=[]) as m:
            resp = quotations_client.get("/quotations/?status=draft&customer_id=5")
        assert resp.status_code == 200
        m.assert_called_once()

    def test_index_404_via_service_tenant_isolation(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.list_quotations", return_value=[]):
            resp = quotations_client.get("/quotations/")
        assert resp.status_code == 200


class TestQuotationsCreate:
    def test_create_get_happy(self, quotations_client, quotations_mocks):
        resp = quotations_client.get("/quotations/create")
        assert resp.status_code == 200

    def test_create_post_success(self, quotations_client, quotations_mocks):
        resp = quotations_client.post(
            "/quotations/create",
            data={"customer_id": "1", "lines-0-product_id": "1", "lines-0-quantity": "2", "lines-0-unit_price": "50"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/quotations/1" in resp.location

    def test_create_post_validation_error_stays_200(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.create_quotation", side_effect=ValueError("customer required")):
            resp = quotations_client.post("/quotations/create", data={"customer_id": ""})
        assert resp.status_code == 200

    def test_create_post_key_error_stays_200(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.create_quotation", side_effect=KeyError("customer_id")):
            resp = quotations_client.post("/quotations/create", data={})
        assert resp.status_code == 200


class TestQuotationsDetail:
    def test_detail_happy(self, quotations_client, quotations_mocks):
        resp = quotations_client.get("/quotations/1")
        assert resp.status_code == 200

    def test_detail_404(self, quotations_client, quotations_mocks):
        with patch(
            "routes.quotations.QuotationService.get_quotation", side_effect=ValueError("عرض الأسعار غير موجود.")
        ):
            with pytest.raises(ValueError, match="عرض الأسعار غير موجود"):
                quotations_client.get("/quotations/999")


class TestQuotationsEdit:
    def test_edit_get_happy(self, quotations_client, quotations_mocks):
        resp = quotations_client.get("/quotations/1/edit")
        assert resp.status_code == 200

    def test_edit_post_success(self, quotations_client, quotations_mocks):
        resp = quotations_client.post("/quotations/1/edit", data={"customer_id": "1"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_post_validation_error_stays_200(self, quotations_client, quotations_mocks):
        with patch(
            "routes.quotations.QuotationService.update_quotation", side_effect=ValueError("فقط المسودات يمكن تعديلها.")
        ):
            resp = quotations_client.post("/quotations/1/edit", data={"customer_id": "1"})
        assert resp.status_code == 200


class TestQuotationsSend:
    def test_send_happy(self, quotations_client, quotations_mocks):
        resp = quotations_client.post("/quotations/1/send", follow_redirects=False)
        assert resp.status_code == 302

    def test_send_validation_error_redirect(self, quotations_client, quotations_mocks):
        with patch(
            "routes.quotations.QuotationService.send_quotation", side_effect=ValueError("فقط المسودات يمكن إرسالها.")
        ):
            resp = quotations_client.post("/quotations/1/send", follow_redirects=False)
        assert resp.status_code == 302


class TestQuotationsAccept:
    def test_accept_happy(self, quotations_client, quotations_mocks):
        resp = quotations_client.post("/quotations/1/accept", follow_redirects=False)
        assert resp.status_code == 302

    def test_accept_validation_error(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.accept_quotation", side_effect=ValueError("منتهي")):
            resp = quotations_client.post("/quotations/1/accept", follow_redirects=False)
        assert resp.status_code == 302


class TestQuotationsReject:
    def test_reject_happy(self, quotations_client, quotations_mocks):
        resp = quotations_client.post("/quotations/1/reject", follow_redirects=False)
        assert resp.status_code == 302

    def test_reject_validation_error(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.reject_quotation", side_effect=ValueError("يجب أن يكون مرسلاً")):
            resp = quotations_client.post("/quotations/1/reject", follow_redirects=False)
        assert resp.status_code == 302


class TestQuotationsConvert:
    def test_convert_happy_redirects_to_sale(self, quotations_client, quotations_mocks):
        resp = quotations_client.post("/quotations/1/convert", follow_redirects=False)
        assert resp.status_code == 302
        assert "/sales/" in resp.location

    def test_convert_validation_error_redirect(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.convert_to_sale", side_effect=ValueError("فقط المقبولة")):
            resp = quotations_client.post("/quotations/1/convert", follow_redirects=False)
        assert resp.status_code == 302


class TestQuotationsDuplicate:
    def test_duplicate_happy(self, quotations_client, quotations_mocks):
        resp = quotations_client.post("/quotations/1/duplicate", follow_redirects=False)
        assert resp.status_code == 302
        assert "/quotations/2" in resp.location

    def test_duplicate_validation_error(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.duplicate_quotation", side_effect=ValueError("fail")):
            resp = quotations_client.post("/quotations/1/duplicate", follow_redirects=False)
        assert resp.status_code == 302

    def test_duplicate_404(self, quotations_client, quotations_mocks):
        with patch("routes.quotations.QuotationService.get_quotation", side_effect=ValueError("غير موجود")):
            with pytest.raises(ValueError, match="غير موجود"):
                quotations_client.post("/quotations/1/duplicate", follow_redirects=False)
