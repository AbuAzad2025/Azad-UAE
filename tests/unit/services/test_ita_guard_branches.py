"""Unit tests for ITA allocation guard/data-variant branches."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.ita_allocation_service import ItaAllocationError, ItaAllocationService


def _tenant(**kwargs):
    tenant = MagicMock(
        enable_ita_allocation=True,
        ita_allocation_threshold=Decimal("0"),
        ita_environment="sandbox",
        tax_number="512345678",
        id=11,
    )
    for key, value in kwargs.items():
        setattr(tenant, key, value)
    return tenant


def _sale(**kwargs):
    sale = MagicMock(
        tenant_id=11,
        total_amount=Decimal("500"),
        taxable_amount=Decimal("400"),
        tax_amount=Decimal("100"),
        sale_number="S-1",
    )
    sale.customer = None
    sale.sale_date = None
    for key, value in kwargs.items():
        setattr(sale, key, value)
    return sale


def _stored_invoice(mocker, number=None):
    query = MagicMock()
    row = MagicMock(ita_allocation_number=number)
    query.filter_by.return_value.with_for_update.return_value.first.return_value = row
    mocker.patch("utils.tenanting.tenant_query", return_value=query)
    return row


class TestEligible:
    def test_above_threshold(self):
        assert ItaAllocationService.eligible(_tenant(), _sale()) is True

    def test_below_threshold(self):
        tenant = _tenant(ita_allocation_threshold=Decimal("900"))
        assert ItaAllocationService.eligible(tenant, _sale()) is False

    def test_disabled(self):
        assert ItaAllocationService.eligible(_tenant(enable_ita_allocation=False), _sale()) is False


class TestGuards:
    def test_missing_tenant(self, mocker):
        mock_db = mocker.patch("services.ita_allocation_service.db")
        mock_db.session.get.return_value = None
        with pytest.raises(ItaAllocationError, match="Tenant not found"):
            ItaAllocationService.request_allocation_number(_sale())

    def test_buyer_bad_digits(self, mocker):
        mock_db = mocker.patch("services.ita_allocation_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="tok")
        sale = _sale(customer=MagicMock(tax_number="123"))
        with pytest.raises(ItaAllocationError, match="customer"):
            ItaAllocationService.request_allocation_number(sale)

    def test_json_value_error_body_is_empty(self, mocker):
        mock_db = mocker.patch("services.ita_allocation_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="tok")
        _stored_invoice(mocker)
        response = MagicMock(status_code=200)
        response.json.side_effect = ValueError("not json")
        mocker.patch("services.ita_allocation_service.requests.post", return_value=response)
        with pytest.raises(ItaAllocationError, match="did not approve"):
            ItaAllocationService.request_allocation_number(_sale())

    def test_nested_data_picked(self, mocker):
        mock_db = mocker.patch("services.ita_allocation_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="tok")
        _stored_invoice(mocker)
        response = MagicMock(status_code=200)
        response.json.return_value = {"data": {"confirmation_number": "A-1"}}
        mocker.patch("services.ita_allocation_service.requests.post", return_value=response)
        result = ItaAllocationService.request_allocation_number(_sale())
        assert result["allocation_number"] == "A-1"

    def test_success_sets_number_on_existing_einvoice(self, mocker):
        mock_db = mocker.patch("services.ita_allocation_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="tok")
        row = _stored_invoice(mocker)
        response = MagicMock(status_code=200)
        response.json.return_value = {"confirmation_number": "N-9"}
        mocker.patch("services.ita_allocation_service.requests.post", return_value=response)
        result = ItaAllocationService.request_allocation_number(_sale())
        assert result["allocation_number"] == "N-9"
        assert row.ita_allocation_number == "N-9"

    @pytest.mark.parametrize(
        ("status_code", "body"),
        [
            (500, {"approved": True, "confirmation_number": "123"}),
            (200, {"approved": True}),
            (200, {"status": 200, "approved": False, "confirmation_number": "123"}),
            (200, {"status": 400, "approved": True, "confirmation_number": "123"}),
            (200, {"approved": True, "confirmation_number": "0"}),
            (200, {"approved": True, "confirmation_number": "000"}),
            (200, {"approved": True, "confirmation_number": " "}),
            (200, {"approved": True, "confirmation_number": "None"}),
            (200, []),
        ],
    )
    def test_contradictory_or_missing_confirmation_is_rejected(self, mocker, status_code, body):
        mock_db = mocker.patch("services.ita_allocation_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="tok")
        row = _stored_invoice(mocker)
        response = MagicMock(status_code=status_code)
        response.json.return_value = body
        mocker.patch("services.ita_allocation_service.requests.post", return_value=response)
        with pytest.raises(ItaAllocationError, match="did not approve"):
            ItaAllocationService.request_allocation_number(_sale())
        assert row.ita_allocation_number is None

    def test_existing_number_is_not_sent_again(self, mocker):
        mock_db = mocker.patch("services.ita_allocation_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="tok")
        _stored_invoice(mocker, number="123")
        post = mocker.patch("services.ita_allocation_service.requests.post")
        with pytest.raises(ItaAllocationError, match="already recorded"):
            ItaAllocationService.request_allocation_number(_sale())
        post.assert_not_called()

    def test_missing_invoice_artifact_is_refused_before_network(self, mocker):
        mock_db = mocker.patch("services.ita_allocation_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="tok")
        query = MagicMock()
        query.filter_by.return_value.with_for_update.return_value.first.return_value = None
        mocker.patch("utils.tenanting.tenant_query", return_value=query)
        post = mocker.patch("services.ita_allocation_service.requests.post")
        with pytest.raises(ItaAllocationError, match="artifact"):
            ItaAllocationService.request_allocation_number(_sale())
        post.assert_not_called()
