"""Unit tests for EInvoiceService guard branches."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.einvoice_service import EInvoiceService


class TestGuardBranches:
    def test_mock_sale_without_int_id_skips(self):
        sale = SimpleNamespace(id="not-an-int", tenant_id=1)
        assert EInvoiceService.generate_for_sale(sale) is None

    def test_missing_tenant_id_falls_back(self, mocker):
        sale = SimpleNamespace(id=7, tenant_id=None)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        mocker.patch.object(EInvoiceService, "_tenant", return_value=None)
        assert EInvoiceService.generate_for_sale(sale) is None

    def test_disabled_einvoice_skips(self, mocker):
        sale = SimpleNamespace(id=7, tenant_id=1)
        tenant = SimpleNamespace(enable_einvoice=False)
        mocker.patch.object(EInvoiceService, "_tenant", return_value=tenant)
        assert EInvoiceService.generate_for_sale(sale) is None

    def test_no_profile_jurisdiction_skips(self, mocker):
        sale = SimpleNamespace(id=7, tenant_id=1)
        tenant = SimpleNamespace(enable_einvoice=True, vat_country=None)
        mocker.patch.object(EInvoiceService, "_tenant", return_value=tenant)
        mocker.patch.object(EInvoiceService, "_build_document", return_value=None)
        assert EInvoiceService.generate_for_sale(sale) is None

    def test_return_missing_tenant(self, mocker):
        mocker.patch.object(EInvoiceService, "_tenant", return_value=None)
        product_return = MagicMock(tenant_id=1, sale=MagicMock())
        assert EInvoiceService.generate_for_return(product_return) is None

    def test_return_credit_notes_disabled(self, mocker):
        tenant = SimpleNamespace(enable_einvoice=True, enable_einvoice_credit_notes=False)
        mocker.patch.object(EInvoiceService, "_tenant", return_value=tenant)
        product_return = MagicMock(tenant_id=1, sale=MagicMock())
        assert EInvoiceService.generate_for_return(product_return) is None

    def test_return_zero_total_falls_back(self, mocker):
        sale = MagicMock(tax_rate=0)
        line = SimpleNamespace(
            quantity=Decimal("1"),
            unit_price=Decimal("10"),
            line_total=Decimal("10"),
            product=None,
            product_id=2,
        )
        product_return = MagicMock(
            tenant_id=1,
            sale=sale,
            return_number="R-1",
            refund_amount=Decimal("0"),
            total_amount=Decimal("10"),
            currency="AED",
            exchange_rate=Decimal("1"),
            created_at=datetime(2026, 1, 1),
            lines=[line],
        )
        tenant = SimpleNamespace(enable_einvoice=True, enable_einvoice_credit_notes=True)
        mocker.patch.object(EInvoiceService, "_tenant", return_value=tenant)
        mocker.patch.object(EInvoiceService, "_build_document", return_value=None)
        assert EInvoiceService.generate_for_return(product_return) is None

    def test_get_for_sale(self, mocker):
        query = MagicMock()
        query.first.return_value = "row"
        query.filter_by.return_value = query
        einvoice_model = mocker.patch("models.EInvoice")
        einvoice_model.query.filter_by.return_value = query
        assert EInvoiceService.get_for_sale(1) == "row"
        assert EInvoiceService.get_for_sale(1, tenant_id=2) == "row"

    def test_get_for_return(self, mocker):
        query = MagicMock()
        query.first.return_value = "row"
        query.filter_by.return_value = query
        einvoice_model = mocker.patch("models.EInvoice")
        einvoice_model.query.filter_by.return_value = query
        assert EInvoiceService.get_for_return(1) == "row"
        assert EInvoiceService.get_for_return(1, tenant_id=2) == "row"


class TestClassicPhase0:
    def test_phase2_without_secrets_raises(self, mocker):
        tenant = SimpleNamespace(id=1, enable_einvoice=True, vat_country="SA", zatca_phase2_enabled=True)
        sale = SimpleNamespace(id=7, tenant_id=1, currency="SAR")
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value=None)
        with pytest.raises(ValueError, match="private key"):
            EInvoiceService._build_document(tenant, sale, doc_type="invoice", billing_reference=None)

    def test_sa_classic_document(self, mocker):
        tenant = SimpleNamespace(id=1, enable_einvoice=True, vat_country="SA", zatca_phase2_enabled=False)
        sale = SimpleNamespace(id=7, tenant_id=1, currency="SAR")
        mocker.patch(
            "utils.einvoice_document.zatca_document",
            return_value={"xml_payload": "<x/>", "qr_base64": "q", "invoice_hash": "h", "format": "z"},
        )
        mocker.patch("utils.tax_settings.vat_country", return_value="SA")
        doc = EInvoiceService._build_document(tenant, sale, doc_type="invoice", billing_reference=None)
        assert doc["format"] == "z"
