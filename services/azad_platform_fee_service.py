"""Azad platform fee accruals for tenant online-store payments."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from flask import current_app

from extensions import db
from utils.db_safety import atomic_transaction
from models import AzadPlatformFee
from models.payment_vault import PaymentVault, PaymentTransaction
from services.gl_posting import post_or_fail
from services.gl_service import GL_ACCOUNTS, GLService
from utils.gl_reference_types import GLRef
from utils.tax_settings import _resolve_main_branch


class AzadPlatformFeeService:
    @staticmethod
    def _get_rate(tenant_id=None):
        """Read platform fee rate from SystemSettings (owner-configurable)."""
        from models import SystemSettings

        settings = SystemSettings.get_current()
        stored = settings.azad_platform_fee_rate
        rate = Decimal(str(stored if stored is not None else 1.00))
        return (rate / Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), rate

    @staticmethod
    def is_online_store_transaction(sale) -> bool:
        if getattr(sale, "source", None) != "online_store":
            return False
        channel = (getattr(sale, "checkout_payment_method", None) or "").strip().lower()
        gateway_ref = (getattr(sale, "checkout_gateway_ref", None) or "").strip()
        return channel == "online_pay" or bool(gateway_ref)

    @staticmethod
    def _base_amount_aed(sale, payment=None) -> Decimal:
        if payment is not None and getattr(payment, "amount_aed", None) is not None:
            amount = Decimal(str(payment.amount_aed or 0))
        else:
            amount = Decimal(str(getattr(sale, "amount_aed", None) or getattr(sale, "total_amount", 0) or 0))
        return amount.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _idempotency_key(sale, payment=None, gateway_reference=None) -> str:
        tenant_id = int(getattr(sale, "tenant_id"))
        sale_id = int(getattr(sale, "id"))
        ref = gateway_reference or getattr(sale, "checkout_gateway_ref", None) or getattr(payment, "id", None) or "sale"
        return f"store-online:{tenant_id}:{sale_id}:{ref}"

    @staticmethod
    def record_store_online_fee(
        sale,
        *,
        payment=None,
        payment_channel=None,
        gateway_name="nowpayments",
        gateway_reference=None,
    ) -> AzadPlatformFee | None:
        """Record and post Azad's 1% share for a confirmed online-store payment."""
        if not AzadPlatformFeeService.is_online_store_transaction(sale):
            return None

        tenant_id = getattr(sale, "tenant_id", None)
        if tenant_id is None:
            raise ValueError("Online store sale is missing tenant_id.")

        key = AzadPlatformFeeService._idempotency_key(sale, payment, gateway_reference)
        existing = AzadPlatformFee.query.filter_by(idempotency_key=key).first()
        if existing:
            return existing

        base_amount = AzadPlatformFeeService._base_amount_aed(sale, payment)
        if base_amount <= Decimal("0"):
            return None

        rate_decimal, rate_percent = AzadPlatformFeeService._get_rate(tenant_id)
        fee_amount = (base_amount * rate_decimal).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if fee_amount <= Decimal("0"):
            return None

        vault = PaymentVault.get_platform_vault()
        if vault is None:
            raise ValueError("Platform vault does not exist — cannot accrue platform fee.")
        fee = AzadPlatformFee(
            idempotency_key=key,
            tenant_id=int(tenant_id or 0),
            sale_id=int(sale.id),
            payment_id=getattr(payment, "id", None),
            vault_id=vault.id,
            rate_percent=rate_percent,
            base_amount_aed=base_amount,
            fee_amount_aed=fee_amount,
            payment_channel=(payment_channel or getattr(sale, "checkout_payment_method", None) or "online_pay")[:50],
            gateway_name=gateway_name,
            gateway_reference=(gateway_reference or getattr(sale, "checkout_gateway_ref", None) or "")[:120],
            status="accrued",
        )
        db.session.add(fee)
        db.session.flush()

        GLService.ensure_core_accounts(tenant_id=int(tenant_id or 0))
        post_or_fail(
            [
                {
                    "account": GL_ACCOUNTS["commission_expense"],
                    "concept_code": "COMMISSION_EXPENSE",
                    "debit": fee_amount,
                    "description": f"Azad online platform fee {rate_percent}% - {sale.sale_number}",
                },
                {
                    "account": GL_ACCOUNTS["azad_platform_payable"],
                    "concept_code": "AZAD_PLATFORM_PAYABLE",
                    "credit": fee_amount,
                    "description": f"Azad payable - online platform fee {sale.sale_number}",
                },
            ],
            description=f"Azad platform fee ({rate_percent}%) {sale.sale_number}",
            reference_type=GLRef.AZAD_PLATFORM_FEE,
            reference_id=fee.id,
            exchange_rate=1.0,
            branch_id=getattr(sale, "branch_id", None),
            tenant_id=int(tenant_id or 0),
        )
        fee.gl_posted = True
        current_app.logger.info("Azad platform fee accrued: sale=%s fee=%s", sale.sale_number, fee_amount)
        return fee

    @staticmethod
    def get_accrued_summary(tenant_id=None):
        """Return total accrued (unapproved) platform fees per tenant."""
        from sqlalchemy import func

        q = db.session.query(
            AzadPlatformFee.tenant_id,
            func.coalesce(func.sum(AzadPlatformFee.fee_amount_aed), 0).label("total"),
        ).filter(AzadPlatformFee.status == "accrued")
        if tenant_id:
            q = q.filter(AzadPlatformFee.tenant_id == tenant_id)
        q = q.group_by(AzadPlatformFee.tenant_id)
        return [
            {
                "tenant_id": row.tenant_id,
                "total_fee_aed": Decimal(str(row.total)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
            }
            for row in q.all()
        ]

    @staticmethod
    def get_settlement_report(tenant_id=None, date_from=None, date_to=None):
        """Return detailed settlement-ready fees."""
        q = AzadPlatformFee.query.filter(AzadPlatformFee.status.in_(["accrued", "settled", "paid"]))
        if tenant_id:
            q = q.filter(AzadPlatformFee.tenant_id == tenant_id)
        if date_from:
            q = q.filter(AzadPlatformFee.created_at >= date_from)
        if date_to:
            q = q.filter(AzadPlatformFee.created_at <= date_to)
        q = q.order_by(AzadPlatformFee.created_at.desc())
        items = q.all()
        total = sum((Decimal(str(f.fee_amount_aed or 0)) for f in items), Decimal("0"))
        return {
            "items": items,
            "total_fee_aed": total.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
            "count": len(items),
        }

    @staticmethod
    def settle_fees(tenant_ids, settlement_date=None, payment_method="bank"):
        """Settle accrued platform fees for a tenant.

        Posts tenant-side GL (azad_platform_payable -> bank) and marks fees as 'settled'.
        This recognises the tenant's payment of accrued fees to the platform
        (accounting settlement).  Use confirm_settlement_paid() for the actual
        platform-side payout confirmation.
        """
        from datetime import datetime, timezone

        settlement_date = settlement_date or datetime.now(timezone.utc)
        if isinstance(tenant_ids, int):
            tenant_ids = [tenant_ids]
        results = []
        for tid in tenant_ids:
            fees = AzadPlatformFee.query.filter_by(tenant_id=tid, status="accrued", gl_posted=True).all()
            if not fees:
                continue
            total = sum(Decimal(str(f.fee_amount_aed or 0)) for f in fees)
            if total <= Decimal("0"):
                continue
            lines = [
                {
                    "account": GL_ACCOUNTS["azad_platform_payable"],
                    "concept_code": "AZAD_PLATFORM_PAYABLE",
                    "debit": total,
                    "description": f"تسوية رسوم منصة أزاد — {len(fees)} سجل",
                },
                {
                    "account": GL_ACCOUNTS[payment_method],
                    "concept_code": "BANK" if payment_method == "bank" else "CASH",
                    "credit": total,
                    "description": f"دفع رسوم منصة أزاد — {total} AED",
                },
            ]
            post_or_fail(
                lines,
                description=f"تسوية رسوم منصة أزاد — Tenant {tid}",
                reference_type=GLRef.AZAD_PLATFORM_FEE,
                reference_id=fees[0].id,
                date=settlement_date,
                exchange_rate=1.0,
                branch_id=_resolve_main_branch(tid),
                tenant_id=tid,
            )
            for fee in fees:
                fee.status = "settled"
            with atomic_transaction("settle_platform_fees"):
                db.session.flush()
            results.append(
                {
                    "tenant_id": tid,
                    "fee_count": len(fees),
                    "total_aed": total.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                }
            )
            current_app.logger.info(
                "Platform fees settled: tenant=%s count=%s total=%s",
                tid,
                len(fees),
                total,
            )
        return results

    @staticmethod
    def confirm_settlement_paid(fee_ids):
        """Mark settled platform fees as paid and record platform-side vault evidence.

        Creates PaymentTransaction records in the platform vault as evidence
        of real-world receipt.  Sets fee.status = 'paid' for each fee.

        Args:
            fee_ids: single fee ID or list of fee IDs.

        Returns:
            dict with transaction_id, count, total_aed.
        """
        from utils.helpers import generate_number

        if isinstance(fee_ids, int):
            fee_ids = [fee_ids]
        fees = AzadPlatformFee.query.filter(
            AzadPlatformFee.id.in_(fee_ids),
            AzadPlatformFee.status == "settled",
        ).all()
        if not fees:
            raise ValueError("No settled fees found for the given IDs.")
        vault = PaymentVault.get_platform_vault()
        if not vault:
            raise ValueError("Platform vault does not exist — cannot record payout.")
        total = sum(Decimal(str(f.fee_amount_aed or 0)) for f in fees)
        if total <= Decimal("0"):
            raise ValueError("Total payout amount is zero.")
        txn_id = f"PLATFORM-SETTLE-{generate_number('SETT', PaymentTransaction, 'transaction_id')}"
        txn = PaymentTransaction(
            transaction_id=txn_id,
            amount_usd=float(total),
            amount_crypto=0,
            crypto_currency="AED",
            payment_status="completed",
            payment_method="bank",
            customer_name="Azad Platform Settlements",
        )
        vault.transactions.append(txn)
        for fee in fees:
            fee.status = "paid"
        with atomic_transaction("confirm_settlement_paid"):
            db.session.flush()
        current_app.logger.info(
            "Platform settlement paid: txn=%s fees=%d total=%s",
            txn_id,
            len(fees),
            total,
        )
        return {
            "transaction_id": txn_id,
            "count": len(fees),
            "total_aed": total.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        }
