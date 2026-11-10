"""VAT reconciliation — the filed return must equal the journal, not invoices.

Posts the VAT legs a sale, a purchase and a return would post, then checks
that both the GL VAT report and the filed return agree to the cent.
"""

from datetime import UTC, datetime
from decimal import Decimal

from services.gl_posting import post_or_fail
from services.gl_service import GLService
from services.tax_service import TaxService
from utils.gl_reference_types import GLRef

JAN = ("2026-01-01", "2026-01-31")


def _post_vat(db_session, tenant, debit_concept, credit_concept, amount, reference_type):
    out_acc = GLService.get_account_code_for_concept(debit_concept, tenant_id=tenant.id, branch_id=None)
    in_acc = GLService.get_account_code_for_concept(credit_concept, tenant_id=tenant.id, branch_id=None)
    lines = [
        {"account": out_acc, "concept_code": debit_concept, "debit": Decimal(str(amount))},
        {"account": in_acc, "concept_code": credit_concept, "credit": Decimal(str(amount))},
    ]
    post_or_fail(
        lines,
        description=f"VAT scenario {reference_type}",
        reference_type=reference_type,
        date=datetime(2026, 1, 15, tzinfo=UTC),
        tenant_id=tenant.id,
    )
    db_session.flush()


class TestVatReturnReconcilesToJournal:
    def test_output_input_and_return_reversal(self, db_session, sample_tenant):
        # Sale: output VAT 160 (1000 @ 16%).
        _post_vat(db_session, sample_tenant, "SALES_REVENUE", "VAT_OUTPUT", "160", GLRef.SALE)
        # Purchase: input VAT 80 (500 @ 16%).
        _post_vat(db_session, sample_tenant, "VAT_INPUT", "INVENTORY_ASSET", "80", GLRef.PURCHASE)
        # Return: output VAT reversed 16.
        _post_vat(db_session, sample_tenant, "VAT_OUTPUT", "SALES_REVENUE", "16", GLRef.PRODUCT_RETURN)

        report = GLService.get_vat_report(*JAN, tenant_id=sample_tenant.id)
        assert Decimal(str(report["vat_output"])) == Decimal("144.000")
        assert Decimal(str(report["vat_input"])) == Decimal("80.000")
        assert Decimal(str(report["net_vat"])) == Decimal("64.000")

        filed = TaxService.get_vat_return(*JAN, tenant_id=sample_tenant.id)
        assert filed["source"] == "gl"
        assert Decimal(str(filed["output_vat"])) == Decimal("144.000")
        assert Decimal(str(filed["input_vat"])) == Decimal("80.000")
        assert filed["category_totals"] is None

    def test_other_tenant_vat_is_isolated(self, db_session, sample_tenant):
        _post_vat(db_session, sample_tenant, "SALES_REVENUE", "VAT_OUTPUT", "160", GLRef.SALE)
        other = GLService.get_vat_report(*JAN, tenant_id=sample_tenant.id + 999999)
        assert Decimal(str(other["vat_output"])) == Decimal("0")
        assert Decimal(str(other["vat_input"])) == Decimal("0")
