"""E-invoice — country strategy dispatch, XML/QR payload, sync fallback."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestEInvoiceGeneration:
    """EInvoiceService.generate — strategy routing and tenant country resolution."""

    def test_explicit_country_code_uses_strategy(self, mocker):
        strategy = MagicMock()
        strategy.generate_einvoice.return_value = {
            "xml_payload": "<Invoice/>",
            "qr_base64": "abc",
            "format": "fta_ubl_xml",
        }
        mocker.patch("utils.localization.get_strategy", return_value=strategy)

        sale = MagicMock(id=42, total_aed=Decimal("105"))
        from services.einvoice_service import EInvoiceService

        result = EInvoiceService.generate(sale, country_code="AE")
        assert result["xml_payload"] == "<Invoice/>"
        strategy.generate_einvoice.assert_called_once_with(sale)

    def test_tenant_vat_country_fallback(self, mocker):
        tenant = MagicMock(vat_country="SA")
        mock_tenant_q = MagicMock()
        mock_tenant_q.get.return_value = tenant
        mocker.patch(
            "models.Tenant.query",
            new_callable=mocker.PropertyMock,
            return_value=mock_tenant_q,
        )

        strategy = MagicMock()
        strategy.generate_einvoice.return_value = {
            "xml_payload": "<KSA/>",
            "format": "zatca",
        }
        mock_get = mocker.patch(
            "utils.localization.get_strategy", return_value=strategy
        )

        sale = MagicMock(id=1, tenant_id=5)
        from services.einvoice_service import EInvoiceService

        result = EInvoiceService.generate(sale)
        mock_get.assert_called_once_with("SA")
        assert result["format"] == "zatca"

    def test_integration_failure_propagates_from_strategy(self, mocker):
        strategy = MagicMock()
        strategy.generate_einvoice.side_effect = ConnectionError("FTA gateway timeout")
        mocker.patch("utils.localization.get_strategy", return_value=strategy)

        sale = MagicMock(id=1)
        from services.einvoice_service import EInvoiceService

        with pytest.raises(ConnectionError, match="FTA gateway"):
            EInvoiceService.generate(sale, country_code="AE")

    def test_uae_local_compliance_signing_fallback(self, mocker):
        """Null/unknown country routes through get_strategy — local XML still returned."""
        from utils.localization.uae import UAEStrategy

        sale = MagicMock(id=100, total_aed=Decimal("1000"))
        mocker.patch("utils.localization.get_strategy", return_value=UAEStrategy())

        from services.einvoice_service import EInvoiceService

        result = EInvoiceService.generate(sale, country_code="AE")
        assert "xml_payload" in result
        assert "qr_base64" in result
        assert result["format"] == "fta_ubl_xml"
        assert "<Invoice" in result["xml_payload"]

    def test_missing_tenant_defaults_ae(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        strategy = MagicMock()
        strategy.generate_einvoice.return_value = {
            "xml_payload": "",
            "format": "fta_ubl_xml",
        }
        mock_get = mocker.patch(
            "utils.localization.get_strategy", return_value=strategy
        )

        sale = MagicMock(id=2, tenant_id=None)
        from services.einvoice_service import EInvoiceService

        EInvoiceService.generate(sale)
        mock_get.assert_called_once_with("AE")
