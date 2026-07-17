"""Azad subscription fee billing and GL posting for tenants."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app

from extensions import db
from models import AzadSubscriptionFee
from models.system_settings import SystemSettings
from services.gl_posting import post_or_fail
from services.gl_service import GL_ACCOUNTS, GLService
from utils.gl_reference_types import GLRef


class AzadSubscriptionFeeService:
    @staticmethod
    def _settings_amount(fee_type: str) -> Decimal | None:
        """Read subscription fee amount from SystemSettings (owner-configurable)."""
        settings = SystemSettings.get_current()
        mapping = {
            "monthly": settings.subscription_monthly_fee_aed,
            "yearly": settings.subscription_yearly_fee_aed,
            "perpetual": settings.subscription_perpetual_fee_aed,
        }
        val = mapping.get(fee_type)
        if val is None:
            return None
        return Decimal(str(val)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _period_dates(fee_type: str, billing_date=None):
        """Return (start, end) for the subscription period."""
        start = billing_date or datetime.now(timezone.utc).date()
        if fee_type == "monthly":
            end = start + timedelta(days=30)
        elif fee_type == "yearly":
            end = start + timedelta(days=365)
        elif fee_type == "perpetual":
            end = None
        else:
            end = start + timedelta(days=30)
        return start, end

    @classmethod
    def create_subscription_fee(
        cls,
        tenant_id: int,
        fee_type: str = "monthly",
        *,
        amount_aed: Decimal | None = None,
        billing_date=None,
        notes: str | None = None,
    ) -> AzadSubscriptionFee | None:
        """Create a subscription fee record and post GL entry (accrued)."""
        fee_type = (fee_type or "monthly").strip().lower()
        if fee_type not in ("monthly", "yearly", "perpetual"):
            raise ValueError(f"Invalid subscription fee_type: {fee_type}")

        amount = amount_aed
        if amount is None:
            amount = cls._settings_amount(fee_type)
        if amount is None or amount <= Decimal("0"):
            current_app.logger.info(
                "Subscription fee skipped: no amount configured for %s", fee_type
            )
            return None

        amount = Decimal(str(amount)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        period_start, period_end = cls._period_dates(fee_type, billing_date)

        fee = AzadSubscriptionFee(
            tenant_id=int(tenant_id),
            fee_type=fee_type,
            amount_aed=amount,
            billing_period_start=period_start,
            billing_period_end=period_end,
            status="accrued",
            notes=notes or f"Subscription fee ({fee_type})",
        )
        db.session.add(fee)
        db.session.flush()

        # Post GL: Dr Subscription Expense, Cr Azad Platform Payable
        GLService.ensure_core_accounts(tenant_id=int(tenant_id))
        from utils.tax_settings import _resolve_main_branch

        branch_id = _resolve_main_branch(tenant_id)
        post_or_fail(
            [
                {
                    "account": GL_ACCOUNTS["azad_subscription_expense"],
                    "concept_code": "AZAD_SUBSCRIPTION_EXPENSE",
                    "debit": amount,
                    "description": f"Subscription fee ({fee_type}) - Tenant {tenant_id}",
                },
                {
                    "account": GL_ACCOUNTS["azad_platform_payable"],
                    "concept_code": "AZAD_PLATFORM_PAYABLE",
                    "credit": amount,
                    "description": f"Azad payable - subscription ({fee_type}) Tenant {tenant_id}",
                },
            ],
            description=f"Subscription fee ({fee_type}) - Tenant {tenant_id}",
            reference_type=GLRef.AZAD_SUBSCRIPTION_FEE,
            reference_id=fee.id,
            exchange_rate=1.0,
            branch_id=branch_id,
            tenant_id=int(tenant_id),
        )
        fee.gl_posted = True
        fee.gl_posted_at = datetime.now(timezone.utc)
        current_app.logger.info(
            "Subscription fee accrued: tenant=%s type=%s amount=%s",
            tenant_id,
            fee_type,
            amount,
        )
        return fee

    @classmethod
    def record_payment(
        cls,
        fee_id: int,
        *,
        payment_method: str = "bank_transfer",
        payment_reference: str | None = None,
        paid_amount_aed: Decimal | None = None,
        tenant_id: int | None = None,
    ) -> AzadSubscriptionFee:
        """Record tenant payment for a subscription fee (accrued -> paid)."""
        fee = db.session.get(AzadSubscriptionFee, fee_id)
        if not fee:
            raise ValueError(f"Subscription fee {fee_id} not found")
        if fee.status != "accrued":
            raise ValueError(
                f"Subscription fee must be accrued before payment (current: {fee.status})"
            )

        amount = paid_amount_aed
        if amount is None:
            amount = fee.amount_aed
        amount = Decimal(str(amount)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        tid = tenant_id or fee.tenant_id

        # Post GL: Dr Azad Platform Payable, Cr Cash/Bank
        debit_account = GL_ACCOUNTS["azad_platform_payable"]
        credit_concept = GLService.get_payment_credit_concept(payment_method)
        if credit_concept:
            credit_account = GLService._resolve_journal_line_account(
                GLService.posting_line(credit_concept.lower().replace("_", "")),
                tenant_id=tid,
                missing_ok=True,
            )
            credit_code = (
                credit_account.code if credit_account else GL_ACCOUNTS.get("cash")
            )
        else:
            credit_code = GL_ACCOUNTS.get("cash")

        GLService.ensure_core_accounts(tenant_id=int(tid))
        from utils.tax_settings import _resolve_main_branch

        branch_id = _resolve_main_branch(tid)
        post_or_fail(
            [
                {
                    "account": debit_account,
                    "concept_code": "AZAD_PLATFORM_PAYABLE",
                    "debit": amount,
                    "description": f"Subscription fee payment - {fee.fee_type}",
                },
                {
                    "account": credit_code,
                    "concept_code": credit_concept or "CASH",
                    "credit": amount,
                    "description": f"Paid subscription fee via {payment_method}",
                },
            ],
            description=f"Subscription fee paid ({fee.fee_type}) - Tenant {tid}",
            reference_type=GLRef.AZAD_SUBSCRIPTION_FEE,
            reference_id=fee.id,
            exchange_rate=1.0,
            branch_id=branch_id,
            tenant_id=int(tid),
        )

        fee.status = "paid"
        fee.paid_at = datetime.now(timezone.utc)
        fee.paid_amount_aed = amount
        fee.payment_method = payment_method
        fee.payment_reference = payment_reference
        current_app.logger.info(
            "Subscription fee paid: fee_id=%s amount=%s method=%s",
            fee_id,
            amount,
            payment_method,
        )
        return fee

    @classmethod
    def waive_fee(
        cls, fee_id: int, *, notes: str | None = None, tenant_id: int | None = None
    ) -> AzadSubscriptionFee:
        """Waive / cancel a subscription fee and reverse its GL entry."""
        fee = db.session.get(AzadSubscriptionFee, fee_id)
        if not fee:
            raise ValueError(f"Subscription fee {fee_id} not found")
        if fee.status == "cancelled":
            return fee

        tid = tenant_id or fee.tenant_id

        if fee.gl_posted and fee.status == "accrued":
            # Reverse the original accrued entry
            GLService.reverse_entry(
                reference_type=GLRef.AZAD_SUBSCRIPTION_FEE,
                reference_id=fee.id,
                description=f"Waived subscription fee ({fee.fee_type}) - Tenant {tid}",
                tenant_id=int(tid),
            )

        fee.status = "cancelled"
        fee.notes = (fee.notes or "") + f"\nWaived: {notes or 'No reason given'}"
        current_app.logger.info("Subscription fee waived: fee_id=%s", fee_id)
        return fee
