"""GL posting for completed Azad donations — owner vault integration."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from flask import current_app
from flask_babel import gettext

from extensions import db
from models import GLAccount
from models.donation import Donation
from models.payment_vault import PaymentTransaction, PaymentVault
from services.exchange_rate_service import ExchangeRateService
from services.gl_posting import post_or_fail
from services.gl_service import GLService
from utils.db_safety import atomic_transaction
from utils.gl_reference_types import GLRef


class DonationGLService:
    @staticmethod
    def _vault_accounts(vault: PaymentVault | None, tenant_id: int) -> tuple[str, str]:
        debit = (getattr(vault, "donation_debit_account", None) or "1120").strip()
        credit = (getattr(vault, "donation_credit_account", None) or "4200").strip()
        debit_account = GLAccount.query.filter_by(code=debit, tenant_id=tenant_id).order_by(GLAccount.id.asc()).first()
        if debit in ("1110", "1120") or getattr(debit_account, "is_header", False):
            liquidity_kind = "cash" if debit == "1110" else "bank"
            debit = GLService.get_default_liquidity_account(liquidity_kind, tenant_id=tenant_id)
        return debit, credit

    @staticmethod
    def post_completed_donation(donation: Donation) -> bool:
        if getattr(donation, "gl_posted", False):
            return True
        if donation.status != "completed":
            return False

        amount_usd = Decimal(str(donation.amount_usd or 0))
        if amount_usd <= 0:
            return False

        tenant_id = getattr(donation, "tenant_id", None)
        if tenant_id is None:
            current_app.logger.info(
                "Skipping tenant GL posting for Azad/platform donation #%s; platform ledger is not tenant-scoped.",
                getattr(donation, "id", None),
            )
            return False

        vault = PaymentVault.get_tenant_vault(tenant_id) or PaymentVault.get_platform_vault()
        debit_acct, credit_acct = DonationGLService._vault_accounts(vault, int(tenant_id or 0))

        try:
            rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", "AED")
            rate = Decimal(str(rate_info["rate"]))
        except Exception:
            rate = Decimal("3.67")
        from utils.currency_utils import convert_and_quantize_aed

        amount_aed = convert_and_quantize_aed(amount_usd, "USD", rate, tenant_id=tenant_id)

        method_label = donation.payment_method or "donation"
        donor = donation.donor_name or donation.customer_name or gettext("متبرع")
        desc = gettext(f"تبرع Azad #{donation.id} — {donor} ({method_label})")

        lines = [
            {
                "account": debit_acct,
                "concept_code": "BANK",
                "debit": amount_aed,
                "description": desc,
            },
            {
                "account": credit_acct,
                "concept_code": "DONATION_REVENUE",
                "credit": amount_aed,
                "description": desc,
            },
        ]

        try:
            post_or_fail(
                lines,
                description=desc,
                reference_type=GLRef.DONATION,
                reference_id=donation.id,
                exchange_rate=1,
                tenant_id=tenant_id,
            )
            donation.gl_posted = True
            db.session.flush()
            current_app.logger.info(f"Donation GL posted: #{donation.id} AED {amount_aed}")
            return True
        except Exception as exc:
            current_app.logger.error(f"Donation GL failed #{donation.id}: {exc}")
            raise

    @staticmethod
    def record_platform_receipt(donation: Donation) -> bool:
        """Record a platform (tenant-less) donation in the platform vault ledger.

        The platform vault is the treasury for Azad platform money. Approving
        a platform donation means the owner confirms real-world receipt, so a
        completed PaymentTransaction is written as evidence. Idempotent: a
        second call for the same donation is a no-op.
        """
        if getattr(donation, "tenant_id", None) is not None:
            return False
        if getattr(donation, "status", None) != "completed":
            return False
        from utils.tenanting import without_tenant_scope

        # All vault reads/writes below are tenant-less: bypass ORM scoping
        # or the active-tenant filter/stamp would hide/mis-tag platform rows.
        with without_tenant_scope():
            vault = PaymentVault.get_platform_vault()
            if vault is None:
                raise ValueError("Platform vault does not exist — cannot record receipt.")
            receipt_id = f"DONATION-{donation.id}"
            existing = PaymentTransaction.query.filter_by(transaction_id=receipt_id).first()
            if existing is not None:
                return True
        amount = Decimal(str(donation.amount_usd or 0))
        if amount <= 0:
            return False
        method = (getattr(donation, "payment_method", None) or "donation")[:50]
        currency = (getattr(donation, "crypto_type", None) or method or "USD")[:10].upper()
        txn = PaymentTransaction(
            tenant_id=None,
            transaction_id=receipt_id,
            amount_usd=amount.quantize(Decimal("0.01")),
            amount_crypto=Decimal(str(donation.amount_crypto or 0)),
            crypto_currency=currency,
            payment_address=getattr(donation, "final_wallet_address", None)
            or getattr(donation, "wallet_address", None),
            payment_status="completed",
            payment_method=method,
            customer_name=getattr(donation, "donor_name", None) or getattr(donation, "customer_name", None),
            customer_email=getattr(donation, "donor_email", None) or getattr(donation, "customer_email", None),
            ip_address=getattr(donation, "ip_address", None),
            user_agent=(getattr(donation, "user_agent", None) or "")[:500] or None,
            is_verified=True,
            completed_at=datetime.now(UTC),
        )
        vault.transactions.append(txn)
        # The vault receipt is tenant-less: bypass the ORM auto-stamp or
        # the row would inherit the session's active tenant.
        with without_tenant_scope(), atomic_transaction("donation_platform_receipt"):
            db.session.flush()
        current_app.logger.info(f"Platform donation receipt recorded: #{donation.id} {receipt_id}")
        return True
