"""Corporate income tax — estimate and accrual.

The estimate is the tenant's accounting profit for the fiscal year
(``FiscalYearService.calculate_pl_balance`` net_income) taxed at the statutory
rate of the tenant's VAT country (``utils/country_tax.py``):

* AE: 0% up to AED 375,000, then 9% on the excess.
* PS 15%, IL 23%, SA 20% (flat).

Tax adjustments (depreciation timing, non-deductibles, loss carryforward
beyond the UAE threshold) are out of scope for the estimate — it is the
accounting-profit provision the Ledger posts as

  Dr INCOME_TAX_EXPENSE (6350)
  Cr INCOME_TAX_PAYABLE (2142)

idempotently per (tenant, fiscal_year). The accrual is a pure service
(flush only); the route owns the transaction boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from extensions import db
from services.gl_posting import post_or_fail
from services.gl_service import FiscalYearService, GLService
from utils.country_tax import compute_corporate_tax
from utils.gl_reference_types import GLRef

__all__ = ["IncomeTaxService"]


class IncomeTaxService:
    @staticmethod
    def _country(tenant_id) -> str:
        from utils.tax_settings import vat_country

        return vat_country(tenant_id)

    @staticmethod
    def estimate(tenant_id, fiscal_year=None, *, taxable_profit=None) -> dict:
        """Estimate corporate tax for a tenant/fiscal year."""
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        country = IncomeTaxService._country(tenant_id)
        pl = None
        if taxable_profit is None:
            if fiscal_year is None:
                raise ValueError("fiscal_year is required when taxable_profit is not supplied")
            pl = FiscalYearService.calculate_pl_balance(tenant_id, fiscal_year)
            taxable_profit = Decimal(str(pl.get("net_income") or 0))
        taxable_profit = Decimal(str(taxable_profit or 0))
        result = compute_corporate_tax(taxable_profit, country)
        result["tenant_id"] = int(tenant_id)
        result["fiscal_year"] = fiscal_year
        result["taxable_profit"] = taxable_profit
        if pl is not None:
            result["total_revenue"] = pl.get("total_revenue")
            result["total_expense"] = pl.get("total_expense")
            result["net_income"] = pl.get("net_income")
        return result

    @staticmethod
    def find_accrual(tenant_id, fiscal_year):
        """Return the posted accrual entry for (tenant, fiscal_year), if any."""
        from models import GLJournalEntry

        return (
            GLJournalEntry.query.filter_by(
                tenant_id=int(tenant_id),
                reference_type=GLRef.INCOME_TAX,
                reference_id=int(fiscal_year),
            )
            .order_by(GLJournalEntry.id.asc())
            .first()
        )

    @staticmethod
    def accrue(
        tenant_id,
        fiscal_year,
        *,
        taxable_profit=None,
        branch_id=None,
        user_id=None,
        date=None,
        allow_closed_period=False,
    ):
        """Post the corporate-tax provision. Idempotent per fiscal year.

        Returns ``{"already_accrued": bool, "tax": Decimal, "entry": ...}``.
        A zero estimate posts nothing (no empty/balanced-zero entry).
        """
        if tenant_id is None or fiscal_year is None:
            raise ValueError("tenant_id and fiscal_year are required")
        existing = IncomeTaxService.find_accrual(tenant_id, fiscal_year)
        if existing is not None:
            return {"already_accrued": True, "tax": None, "entry": existing}

        estimate = IncomeTaxService.estimate(tenant_id, fiscal_year=fiscal_year, taxable_profit=taxable_profit)
        tax = Decimal(str(estimate["tax"]))
        if tax <= Decimal("0"):
            return {"already_accrued": False, "tax": tax, "entry": None}

        if date is None:
            pl = FiscalYearService.calculate_pl_balance(tenant_id, fiscal_year)
            date = pl.get("end_date") or datetime.now(UTC)

        GLService.ensure_core_accounts(tenant_id=int(tenant_id))
        lines = [
            {
                "account": GLService.get_account_code_for_concept(
                    "INCOME_TAX_EXPENSE", branch_id=branch_id, tenant_id=int(tenant_id)
                ),
                "concept_code": "INCOME_TAX_EXPENSE",
                "debit": tax,
                "description": f"ضريبة دخل الشركات ({estimate['country']}) {fiscal_year}",
            },
            {
                "account": GLService.get_account_code_for_concept(
                    "INCOME_TAX_PAYABLE", branch_id=branch_id, tenant_id=int(tenant_id)
                ),
                "concept_code": "INCOME_TAX_PAYABLE",
                "credit": tax,
                "description": f"ضريبة دخل مستحقة ({estimate['country']}) {fiscal_year}",
            },
        ]
        entry = post_or_fail(
            lines,
            description=f"Corporate income tax accrual {fiscal_year} ({estimate['country']})",
            reference_type=GLRef.INCOME_TAX,
            reference_id=int(fiscal_year),
            date=date,
            branch_id=branch_id,
            user_id=user_id,
            tenant_id=int(tenant_id),
            allow_closed_period=allow_closed_period,
        )
        db.session.flush()
        return {"already_accrued": False, "tax": tax, "entry": entry}
