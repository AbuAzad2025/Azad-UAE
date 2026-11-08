"""Zakat accrual — Saudi statutory zakat at 2.5% of the zakat base.

Method (Net Working Capital, المذكور في لائحة الزكاة — the approach ZATCA
publishes for general trade companies):

    zakat_base = max(0, current assets (1100–1179) − current liabilities (2100–2199))

Fixed-asset block (1180–1199) and non-current liabilities (2200+) are
excluded by construction. Amounts are the tenant's base-currency GL balances.
Adjustments for illiquid holdings/investments are out of this first
implementation on purpose — the provision is a yearly accrual, idempotent
per (tenant, fiscal_year), mirroring ``IncomeTaxService``.

Gated by the tenant's ``enable_zakat`` switch (owner Tax Settings page) —
KSA tenants opt in explicitly; the switch, not the country, is the gate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from extensions import db
from services.gl_posting import post_or_fail
from services.gl_service import GLService
from utils.gl_reference_types import GLRef

__all__ = ["ZakatService"]

_ZAKAT_RATE = Decimal("0.025")
# Inclusive code ranges, per the chart-of-accounts layout in
# models/gl_account_registry.py: current assets sit under 1100–1179,
# current liabilities under 2100–2199; fixed assets and non-current
# liabilities live outside both ranges.
_CURRENT_ASSETS = ("1100", "1179")
_CURRENT_LIABILITIES = ("2100", "2199")


def _range_sums(tenant_id: int, low: str, high: str) -> tuple[Decimal, Decimal]:
    """(debits, credits) posted into accounts of a code range (posted entries only)."""
    from sqlalchemy import func

    from models import GLAccount, GLJournalEntry, GLJournalLine

    row = (
        db.session.query(
            func.coalesce(func.sum(GLJournalLine.debit), 0),
            func.coalesce(func.sum(GLJournalLine.credit), 0),
        )
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
        .join(GLAccount, GLAccount.id == GLJournalLine.account_id)
        .filter(
            GLJournalEntry.status == "posted",
            GLJournalEntry.tenant_id == int(tenant_id),
            GLAccount.tenant_id == int(tenant_id),
            GLAccount.is_active.is_(True),
            GLAccount.is_contra.is_(False),
            GLAccount.is_header.is_(False),
            GLAccount.code >= low,
            GLAccount.code <= high,
        )
        .first()
    )
    debits, credits = row or (0, 0)
    return Decimal(str(debits or 0)), Decimal(str(credits or 0))


class ZakatService:
    @staticmethod
    def enabled(tenant_id) -> bool:
        from models import Tenant

        tenant = db.session.get(Tenant, int(tenant_id)) if tenant_id is not None else None
        return bool(getattr(tenant, "enable_zakat", False)) if tenant else False

    @staticmethod
    def estimate(tenant_id, fiscal_year=None) -> dict:
        """Zakat base and amount for a tenant. Zero base ⇒ zero zakat."""
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        tenant_id = int(tenant_id)

        asset_debits, asset_credits = _range_sums(tenant_id, *_CURRENT_ASSETS)
        liab_debits, liab_credits = _range_sums(tenant_id, *_CURRENT_LIABILITIES)
        asset_total = asset_debits - asset_credits
        liability_total = liab_credits - liab_debits

        base = max(Decimal("0"), (asset_total - liability_total)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        zakat = (base * _ZAKAT_RATE).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return {
            "country": None,  # the tenant's enable_zakat switch is the gate; country shown for context
            "fiscal_year": fiscal_year,
            "current_assets": asset_total,
            "current_liabilities": liability_total,
            "zakat_base": base,
            "rate": _ZAKAT_RATE,
            "zakat": zakat,
        }

    @staticmethod
    def find_accrual(tenant_id, fiscal_year):
        from models import GLJournalEntry

        return (
            GLJournalEntry.query.filter_by(
                tenant_id=int(tenant_id),
                reference_type=GLRef.ZAKAT,
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
        branch_id=None,
        user_id=None,
        date=None,
        allow_closed_period=False,
    ):
        """Post the yearly zakat provision. Idempotent per (tenant, fiscal_year)."""
        if tenant_id is None or fiscal_year is None:
            raise ValueError("tenant_id and fiscal_year are required")
        tenant_id = int(tenant_id)
        if not ZakatService.enabled(tenant_id):
            raise ValueError("enable_zakat is off for this tenant — enable it in Tax Settings first.")
        existing = ZakatService.find_accrual(tenant_id, fiscal_year)
        if existing is not None:
            return {"already_accrued": True, "zakat": None, "entry": existing}

        estimate = ZakatService.estimate(tenant_id, fiscal_year=fiscal_year)
        zakat = Decimal(str(estimate["zakat"]))
        if zakat <= Decimal("0"):
            return {"already_accrued": False, "zakat": zakat, "entry": None, "estimate": estimate}

        date = date or datetime.now(UTC)
        GLService.ensure_core_accounts(tenant_id=tenant_id)
        lines = [
            {
                "account": GLService.get_account_code_for_concept(
                    "ZAKAT_EXPENSE", branch_id=branch_id, tenant_id=tenant_id
                ),
                "concept_code": "ZAKAT_EXPENSE",
                "debit": zakat,
                "description": f"زكاة الوعاء الزكوي {fiscal_year} (Zakat accrual — النشاط التجاري)",
            },
            {
                "account": GLService.get_account_code_for_concept(
                    "ZAKAT_PAYABLE", branch_id=branch_id, tenant_id=tenant_id
                ),
                "concept_code": "ZAKAT_PAYABLE",
                "credit": zakat,
                "description": f"زكاة مستحقة {fiscal_year} (Zakat payable)",
            },
        ]
        entry = post_or_fail(
            lines,
            description=f"Zakat accrual {fiscal_year}",
            reference_type=GLRef.ZAKAT,
            reference_id=int(fiscal_year),
            date=date,
            branch_id=branch_id,
            user_id=user_id,
            tenant_id=tenant_id,
            allow_closed_period=allow_closed_period,
        )
        return {"already_accrued": False, "zakat": zakat, "entry": entry, "estimate": estimate}
