"""ITA allocation number client — payload, response parsing, storage."""

from decimal import Decimal

import pytest

from models import EInvoice
from services.ita_allocation_service import ItaAllocationError, ItaAllocationService


def _make_sale(db_session, sample_tenant, sample_branch, sample_user, *, total=Decimal("6000")):
    from models import Customer, Sale

    customer = Customer(tenant_id=sample_tenant.id, name="Buyer", tax_number="123456789")
    db_session.add(customer)
    db_session.flush()
    sale = Sale(
        tenant_id=sample_tenant.id,
        customer_id=customer.id,
        seller_id=sample_user.id,
        sale_number="S-ITA-1",
        branch_id=sample_branch.id,
        currency="ILS",
        base_currency="ILS",
        amount=total,
        amount_aed=total,
        subtotal=total - Decimal("100"),
        tax_rate=Decimal("18"),
        tax_amount=Decimal("100"),
        taxable_amount=total - Decimal("100"),
        total_amount=total,
    )
    db_session.add(sale)
    db_session.flush()
    return sale


class TestItaAllocationService:
    def test_disabled_raises(self, db_session, sample_tenant, sample_branch, sample_user):
        tenant = sample_tenant
        tenant.enable_ita_allocation = False
        db_session.commit()
        sale = _make_sale(db_session, tenant, sample_branch, sample_user)
        with pytest.raises(ItaAllocationError, match="disabled"):
            ItaAllocationService.request_allocation_number(sale)

    def test_no_token_raises(self, db_session, sample_tenant, sample_branch, sample_user):
        tenant = sample_tenant
        tenant.enable_ita_allocation = True
        tenant.vat_country = "IL"
        tenant.tax_number = "123456789"
        db_session.commit()
        sale = _make_sale(db_session, tenant, sample_branch, sample_user)
        with pytest.raises(ItaAllocationError, match="token"):
            ItaAllocationService.request_allocation_number(sale)

    def test_below_threshold_raises(self, db_session, sample_tenant, sample_branch, sample_user):
        tenant = sample_tenant
        tenant.enable_ita_allocation = True
        tenant.vat_country = "IL"
        tenant.tax_number = "123456789"
        tenant.ita_allocation_threshold = Decimal("10000")
        db_session.commit()
        from services.tenant_secrets_service import TenantSecretsService

        TenantSecretsService.set(tenant.id, "ita_oauth_token", "tok-123", user_id=sample_user.id)
        sale = _make_sale(db_session, tenant, sample_branch, sample_user, total=Decimal("6000"))
        with pytest.raises(ItaAllocationError, match="below the allocation threshold"):
            ItaAllocationService.request_allocation_number(sale)

    def test_bad_seller_trn_raises(self, db_session, sample_tenant, sample_branch, sample_user):
        tenant = sample_tenant
        tenant.enable_ita_allocation = True
        tenant.vat_country = "IL"
        tenant.tax_number = "12345"
        db_session.commit()
        from services.tenant_secrets_service import TenantSecretsService

        TenantSecretsService.set(tenant.id, "ita_oauth_token", "tok-123", user_id=sample_user.id)
        sale = _make_sale(db_session, tenant, sample_branch, sample_user)

        with pytest.raises(ItaAllocationError, match="9 digits"):
            ItaAllocationService.request_allocation_number(sale)

    def test_approved_response_stores_number(self, db_session, sample_tenant, sample_branch, sample_user, mocker):
        tenant = sample_tenant
        tenant.enable_ita_allocation = True
        tenant.vat_country = "IL"
        tenant.tax_number = "123456789"
        db_session.commit()
        from services.tenant_secrets_service import TenantSecretsService

        TenantSecretsService.set(tenant.id, "ita_oauth_token", "tok-123", user_id=sample_user.id)
        sale = _make_sale(db_session, tenant, sample_branch, sample_user)

        # Create the invoice artifact row first so the service has somewhere
        # to store the allocation number.
        from services.einvoice_service import EInvoiceService

        row = EInvoiceService.generate_for_sale(sale)
        assert row is not None
        db_session.commit()

        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Status": 200,
            "Message": "Invoice approved",
            "Confirmation_Number": "20240704061109183186068226",
        }
        mocker.patch("services.ita_allocation_service.requests.post", return_value=mock_resp)

        result = ItaAllocationService.request_allocation_number(sale)
        assert result["allocation_number"] == "20240704061109183186068226"
        assert result["approved"] is True
        refreshed = EInvoice.query.filter_by(tenant_id=tenant.id, sale_id=sale.id, doc_type="invoice").first()
        assert refreshed.ita_allocation_number == "20240704061109183186068226"

    def test_rejected_response_raises(self, db_session, sample_tenant, sample_branch, sample_user, mocker):
        tenant = sample_tenant
        tenant.enable_ita_allocation = True
        tenant.vat_country = "IL"
        tenant.tax_number = "123456789"
        db_session.commit()
        from services.tenant_secrets_service import TenantSecretsService

        TenantSecretsService.set(tenant.id, "ita_oauth_token", "tok-123", user_id=sample_user.id)
        sale = _make_sale(db_session, tenant, sample_branch, sample_user)

        from services.einvoice_service import EInvoiceService

        assert EInvoiceService.generate_for_sale(sale) is not None

        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Status": 400,
            "Message": "Invoice not approved",
            "Confirmation_Number": "0",
        }
        mocker.patch("services.ita_allocation_service.requests.post", return_value=mock_resp)

        with pytest.raises(ItaAllocationError, match="did not approve"):
            ItaAllocationService.request_allocation_number(sale)

    def test_network_error_raises(self, db_session, sample_tenant, sample_branch, sample_user, mocker):
        tenant = sample_tenant
        tenant.enable_ita_allocation = True
        tenant.vat_country = "IL"
        tenant.tax_number = "123456789"
        db_session.commit()
        from services.tenant_secrets_service import TenantSecretsService

        TenantSecretsService.set(tenant.id, "ita_oauth_token", "tok-123", user_id=sample_user.id)
        sale = _make_sale(db_session, tenant, sample_branch, sample_user)

        from services.einvoice_service import EInvoiceService

        assert EInvoiceService.generate_for_sale(sale) is not None

        import requests

        mocker.patch("services.ita_allocation_service.requests.post", side_effect=requests.ConnectionError("boom"))

        with pytest.raises(ItaAllocationError, match="Could not reach"):
            ItaAllocationService.request_allocation_number(sale)
