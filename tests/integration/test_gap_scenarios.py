"""Gap-closure scenarios — real DB, independently computed expectations.

1. Approved returns reduce scope revenue/COGS in the return period.
2. The unified statement reports net payable (approved only, reversals netted).
3. ITA allocation payload carries every mandatory Approval field.
4. ZATCA submission sends the stored signed-artifact XML verbatim.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from models import (
    Partner,
    PartnerCommissionEntry,
    PartnerProfitDistribution,
    ProductReturn,
    ProductReturnLine,
    Sale,
    SaleLine,
)
from services.partner_service import PartnerService

JAN = (date(2026, 1, 1), date(2026, 1, 31))
FEB = (date(2026, 2, 1), date(2026, 2, 28))


def _sale(db_session, tenant, warehouse, user, customer, product, number, *, status="confirmed"):
    sale = Sale(
        tenant_id=tenant.id,
        sale_number=number,
        customer_id=customer.id,
        seller_id=user.id,
        branch_id=warehouse.branch_id,
        warehouse_id=warehouse.id,
        sale_date=datetime(2026, 1, 10, tzinfo=UTC),
        status=status,
        subtotal=Decimal("200"),
        total_amount=Decimal("200"),
        amount=Decimal("200"),
        amount_aed=Decimal("200"),
        tax_amount=Decimal("0"),
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(
        tenant_id=tenant.id,
        sale_id=sale.id,
        product_id=product.id,
        quantity=Decimal("2"),
        unit_price=Decimal("100"),
        line_total=Decimal("200"),
        cost_price=Decimal("50"),
    )
    db_session.add(line)
    db_session.flush()
    return sale, line


def _return(db_session, tenant, sale, customer, line, product, number, *, status="approved", qty=1):
    ret = ProductReturn(
        tenant_id=tenant.id,
        return_number=number,
        sale_id=sale.id,
        customer_id=customer.id,
        branch_id=sale.branch_id,
        return_date=datetime(2026, 2, 10, tzinfo=UTC),
        status=status,
        total_amount=Decimal("100"),
        refund_amount=Decimal("100"),
        amount_aed=Decimal("100"),
        currency="AED",
    )
    db_session.add(ret)
    db_session.flush()
    db_session.add(
        ProductReturnLine(
            tenant_id=tenant.id,
            return_id=ret.id,
            sale_line_id=line.id,
            product_id=product.id,
            quantity=Decimal(str(qty)),
            unit_price=Decimal("100"),
            line_total=Decimal("100"),
        )
    )
    db_session.flush()
    return ret


class TestReturnsReduceScopeProfit:
    def test_approved_return_reduces_return_period_revenue_and_cogs(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        sale, line = _sale(
            db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product, "RET-1"
        )
        _return(db_session, sample_tenant, sale, sample_customer, line, sample_product, "RET-1-R")
        # February: no new sales; half the January sale returned.
        # Revenue −100 (half of 200), COGS −50 (1 × 50 cost) → net −50.
        assert PartnerService.get_scope_revenue(sample_tenant.id, *FEB, "company") == Decimal("-100")
        assert PartnerService.get_scope_cogs(sample_tenant.id, *FEB, "company") == Decimal("-50")
        pnl = PartnerService.calculate_scope_profit(sample_tenant.id, *FEB, "company")
        assert Decimal(str(pnl["net_profit"])) == Decimal("-50")
        # Warehouse scope mirrors on line totals: same −100/−50 here.
        assert PartnerService.get_scope_revenue(sample_tenant.id, *FEB, "warehouse", sample_warehouse.id) == Decimal(
            "-100"
        )
        assert PartnerService.get_scope_cogs(sample_tenant.id, *FEB, "warehouse", sample_warehouse.id) == Decimal("-50")
        # January is untouched by a February return.
        assert PartnerService.get_scope_revenue(sample_tenant.id, *JAN, "company") == Decimal("200")

    def test_rejected_return_does_not_reduce(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        sale, line = _sale(
            db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product, "RET-2"
        )
        _return(db_session, sample_tenant, sale, sample_customer, line, sample_product, "RET-2-R", status="rejected")
        assert PartnerService.get_scope_revenue(sample_tenant.id, *FEB, "company") == Decimal("0")
        assert PartnerService.get_scope_cogs(sample_tenant.id, *FEB, "company") == Decimal("0")


class TestUnifiedStatementNetPayable:
    def test_drafts_excluded_and_reversals_netted(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        sale, line = _sale(
            db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product, "UNI-1"
        )
        partner = Partner(tenant_id=sample_tenant.id, name="Dual", scope_type="company", share_percentage=Decimal("50"))
        db_session.add(partner)
        db_session.flush()
        sample_customer.partner_id = partner.id
        db_session.flush()
        db_session.add_all(
            [
                PartnerProfitDistribution(
                    tenant_id=sample_tenant.id,
                    partner_id=partner.id,
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                    scope_type="company",
                    net_profit=100,
                    share_amount=100,
                    net_due=100,
                    status="draft",
                ),
                PartnerProfitDistribution(
                    tenant_id=sample_tenant.id,
                    partner_id=partner.id,
                    period_start=date(2026, 2, 1),
                    period_end=date(2026, 2, 28),
                    scope_type="company",
                    net_profit=120,
                    share_amount=60,
                    net_due=60,
                    status="approved",
                ),
                PartnerCommissionEntry(
                    tenant_id=sample_tenant.id,
                    sale_id=sale.id,
                    sale_line_id=line.id,
                    partner_customer_id=sample_customer.id,
                    percentage=Decimal("20"),
                    base_amount_aed=Decimal("200"),
                    commission_amount_aed=Decimal("40"),
                ),
            ]
        )
        db_session.flush()
        _return(db_session, sample_tenant, sale, sample_customer, line, sample_product, "UNI-1-R")

        out = PartnerService.get_unified_statement(partner.id, sample_tenant.id)
        # Approved net due only; the draft stays out of the payable.
        assert out["company_total"] == 60.0
        assert out["draft_total"] == 100.0
        # Gross 40 on a 2-unit line; returning 1 unit reverses 20.
        assert out["product_commissions_gross"] == 40.0
        assert out["product_commissions_reversed"] == 20.0
        assert out["product_commissions_total"] == 20.0
        assert out["combined_total"] == 80.0


class TestAuthorityRequestShapes:
    def test_ita_payload_has_every_mandatory_field(self):
        from services.ita_allocation_service import ItaAllocationService

        tenant = MagicMock(id=7)
        sale = MagicMock(
            sale_number="S-9",
            taxable_amount=Decimal("1000"),
            tax_amount=Decimal("180"),
            total_amount=Decimal("1180"),
            discount_amount=Decimal("50"),
            subtotal=Decimal("1050"),
            sale_date=datetime(2026, 3, 3, tzinfo=UTC),
        )
        payload = ItaAllocationService._build_payload(tenant, sale, "123456789", "987654321")
        mandatory = {
            "Invoice_ID",
            "Invoice_Type",
            "Vat_Number",
            "Invoice_Date",
            "Invoice_Issuance_Date",
            "Amount_Before_Discount",
            "Discount",
            "Payment_Amount",
            "VAT_Amount",
            "Payment_Amount_Including_VAT",
        }
        assert mandatory <= set(payload)
        assert payload["Amount_Before_Discount"] == "1050.00"
        assert payload["Discount"] == "50.00"
        assert payload["Payment_Amount"] == "1000.00"
        assert payload["VAT_Amount"] == "180.00"
        assert payload["Payment_Amount_Including_VAT"] == "1180.00"
        assert payload["Invoice_Type"] == "305"

    def test_zatca_sends_stored_xml_verbatim(self, auth_client, db_session, sample_tenant, sample_sale, mocker):
        from models import EInvoice

        sample_tenant.vat_country = "SA"
        sample_tenant.zatca_phase2_enabled = True
        row = EInvoice(
            tenant_id=sample_tenant.id,
            sale_id=sample_sale.id,
            country="SA",
            doc_type="invoice",
            format="test",
            xml_payload="<Invoice><Signature>sig</Signature></Invoice>",
            invoice_hash="a" * 64,
            status="generated",
        )
        db_session.add(row)
        db_session.commit()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="credential")
        response = MagicMock(status_code=200)
        response.json.return_value = {"reportingStatus": "REPORTED"}
        post = mocker.patch("services.zatca_submission_service.requests.post", return_value=response)

        assert auth_client.post(f"/sales/{sample_sale.id}/submit-to-zatca").status_code == 302
        post.assert_called_once()
        _args, kwargs = post.call_args
        assert kwargs["data"] == b"<Invoice><Signature>sig</Signature></Invoice>"
        assert kwargs["headers"]["Authorization"] == "Bearer credential"
        assert post.call_args.args[0].endswith("/invoices/reporting/single")
