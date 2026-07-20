from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

import logging

from sqlalchemy import func
from extensions import db

logger = logging.getLogger(__name__)


class PartnerService:
    # ── Period aggregation ──────────────────────────────────────

    @staticmethod
    def get_scope_revenue(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = "company",
        scope_id: Optional[int] = None,
    ) -> Decimal:
        from models import Sale

        if scope_type == "warehouse" and scope_id:
            from models import SaleLine

            q = (
                db.session.query(func.sum(SaleLine.line_total * func.coalesce(Sale.exchange_rate, 1)))
                .select_from(SaleLine)
                .join(Sale, SaleLine.sale_id == Sale.id)
                .filter(
                    Sale.tenant_id == tenant_id,
                    Sale.status == "confirmed",
                    func.date(Sale.sale_date) >= period_start,
                    func.date(Sale.sale_date) <= period_end,
                    Sale.warehouse_id == scope_id,
                )
            )
            return q.scalar() or Decimal("0")

        q = db.session.query(func.sum(Sale.amount_aed)).filter(
            Sale.tenant_id == tenant_id,
            Sale.status == "confirmed",
            func.date(Sale.sale_date) >= period_start,
            func.date(Sale.sale_date) <= period_end,
        )
        if scope_type == "branch" and scope_id:
            q = q.filter(Sale.branch_id == scope_id)
        result = q.scalar() or Decimal("0")
        return result

    @staticmethod
    def get_scope_cogs(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = "company",
        scope_id: Optional[int] = None,
    ) -> Decimal:
        from models import SaleLine, Sale

        q = (
            db.session.query(func.sum(SaleLine.quantity * func.coalesce(SaleLine.cost_price, 0)))
            .join(Sale, SaleLine.sale_id == Sale.id)
            .filter(
                SaleLine.tenant_id == tenant_id,
                Sale.status == "confirmed",
                func.date(Sale.sale_date) >= period_start,
                func.date(Sale.sale_date) <= period_end,
            )
        )
        if scope_type == "branch" and scope_id:
            q = q.filter(Sale.branch_id == scope_id)
        elif scope_type == "warehouse" and scope_id:
            q = q.filter(Sale.warehouse_id == scope_id)
        result = q.scalar() or Decimal("0")
        return result

    @staticmethod
    def get_scope_expenses(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = "company",
        scope_id: Optional[int] = None,
    ) -> Decimal:
        from models import Expense

        if scope_type == "warehouse":
            return Decimal("0")

        q = db.session.query(func.sum(Expense.amount_aed)).filter(
            Expense.tenant_id == tenant_id,
            Expense.is_reversed.is_(False),
            func.date(Expense.expense_date) >= period_start,
            func.date(Expense.expense_date) <= period_end,
        )
        if scope_type == "branch" and scope_id:
            q = q.filter(Expense.branch_id == scope_id)
        result = q.scalar() or Decimal("0")
        return result

    @staticmethod
    def calculate_scope_profit(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = "company",
        scope_id: Optional[int] = None,
    ) -> dict:
        """Return full P&L for a scope."""
        revenue = PartnerService.get_scope_revenue(tenant_id, period_start, period_end, scope_type, scope_id)
        cogs = PartnerService.get_scope_cogs(tenant_id, period_start, period_end, scope_type, scope_id)
        expenses = PartnerService.get_scope_expenses(tenant_id, period_start, period_end, scope_type, scope_id)
        gross_profit = revenue - cogs
        net_profit = gross_profit - expenses
        return {
            "revenue": float(revenue),
            "cogs": float(cogs),
            "expenses": float(expenses),
            "gross_profit": float(gross_profit),
            "net_profit": float(net_profit),
        }

    # ── Distribution creation ───────────────────────────────────

    @staticmethod
    def create_distributions(
        tenant_id: int,
        period_start: date,
        period_end: date,
        created_by: Optional[int] = None,
    ) -> List[int]:
        """Create draft distributions for ALL active partners for the period.

        Validates:
        - Total profit-share percentages across partners ≤ 100 %
        - Loss-sharing percentages are set when net profit < 0
        - Each partner's scope P&L can be resolved
        """
        from models import Partner, PartnerProfitDistribution

        partners = Partner.query.filter_by(
            tenant_id=tenant_id,
            is_active=True,
        ).all()

        if not partners:
            return []

        total_share_pct = sum(Decimal(str(p.share_percentage or 0)) for p in partners)
        if total_share_pct > Decimal("100"):
            raise ValueError(f"إجمالي نسب الأرباح ({total_share_pct}%) يتجاوز 100%")

        distribution_ids = []
        for partner in partners:
            # Skip if already exists for this period
            existing = PartnerProfitDistribution.query.filter_by(
                partner_id=partner.id,
                period_start=period_start,
                period_end=period_end,
            ).first()
            if existing:
                continue

            # Get scope P&L
            try:
                pnl = PartnerService.calculate_scope_profit(
                    tenant_id,
                    period_start,
                    period_end,
                    partner.scope_type,
                    partner.scope_id,
                )
            except Exception as exc:
                raise ValueError(
                    f"فشل حساب أرباح النطاق للشريك {partner.id} ({partner.scope_type}/{partner.scope_id}): {exc}"
                ) from exc

            net_profit = Decimal(str(pnl["net_profit"]))
            total_expenses_dec = Decimal(str(pnl["expenses"]))

            share_pct = Decimal(str(partner.share_percentage or 0))
            expense_pct = Decimal(str(partner.expense_share_percentage or 0))
            loss_pct = Decimal(str(partner.loss_share_percentage or 0))
            fixed = Decimal(str(partner.fixed_monthly_amount or 0))
            threshold = Decimal(str(partner.min_profit_threshold or 0))

            share_amount = Decimal("0")
            expense_share = Decimal("0")
            loss_share = Decimal("0")

            if net_profit > 0:
                if net_profit >= threshold:
                    share_amount = (net_profit * share_pct / 100).quantize(Decimal("0.001"))
                expense_share = (total_expenses_dec * expense_pct / 100).quantize(Decimal("0.001"))
            elif net_profit < 0:
                if loss_pct <= Decimal("0"):
                    raise ValueError(
                        f"الشريك {partner.id} ليس لديه نسبة تحمل خسارة بينما صافي الربح سالب ({net_profit})"
                    )
                loss_share = (abs(net_profit) * loss_pct / 100).quantize(Decimal("0.001"))
                expense_share = (total_expenses_dec * expense_pct / 100).quantize(Decimal("0.001"))

            net_due = share_amount - expense_share - loss_share + fixed

            dist = PartnerProfitDistribution(
                tenant_id=tenant_id,
                partner_id=partner.id,
                period_start=period_start,
                period_end=period_end,
                scope_type=partner.scope_type,
                scope_id=partner.scope_id,
                total_revenue=pnl["revenue"],
                total_cogs=pnl["cogs"],
                total_expenses=pnl["expenses"],
                net_profit=pnl["net_profit"],
                share_percentage=share_pct,
                share_amount=share_amount,
                expense_share_percentage=expense_pct,
                expense_share_amount=expense_share,
                loss_share_percentage=loss_pct,
                loss_share_amount=loss_share,
                fixed_amount=fixed,
                net_due=net_due,
                status="draft",
                created_by=created_by,
            )
            db.session.add(dist)
            db.session.flush()
            distribution_ids.append(dist.id)

        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush partner profit distributions")
            raise

        return distribution_ids

    # ── Distribution lifecycle ──────────────────────────────────

    @staticmethod
    def approve_distribution(dist_id: int, approved_by: int, tenant_id: Optional[int] = None) -> bool:
        from models import PartnerProfitDistribution, PartnerTransaction, Partner

        dist = db.session.get(PartnerProfitDistribution, dist_id)
        if not dist or dist.status != "draft":
            return False
        if tenant_id is not None and dist.tenant_id != tenant_id:
            return False

        dist.status = "approved"
        dist.approved_by = approved_by
        dist.approved_at = datetime.now(timezone.utc)
        net = float(dist.net_due)
        if net != 0:
            tx_type = "profit_share" if net > 0 else "loss_share"
            tx = PartnerTransaction(
                tenant_id=dist.tenant_id,
                partner_id=dist.partner_id,
                distribution_id=dist.id,
                transaction_type=tx_type,
                amount=abs(net) if net > 0 else -abs(net),
                amount_base=abs(net) if net > 0 else -abs(net),
                transaction_date=dist.period_end,
                notes=f"توزيع فترة {dist.period_start} – {dist.period_end}",
            )
            db.session.add(tx)
            partner = db.session.get(Partner, dist.partner_id)
            if partner:
                old_bal = Decimal(str(partner.current_balance or 0))
                new_bal = old_bal + Decimal(str(tx.amount))
                partner.current_balance = new_bal
                partner.total_profit_received = Decimal(str(partner.total_profit_received or 0)) + (
                    Decimal(str(tx.amount)) if net > 0 else Decimal("0")
                )
                partner.total_loss_borne = Decimal(str(partner.total_loss_borne or 0)) + (
                    abs(Decimal(str(tx.amount))) if net < 0 else Decimal("0")
                )
                tx.balance_after = new_bal

        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush partner distribution approval")
            raise

        return True

    @staticmethod
    def pay_distribution(dist_id: int, tenant_id: Optional[int] = None) -> bool:
        from models import PartnerProfitDistribution
        from services.gl_service import GLService, GL_ACCOUNTS
        from services.gl_posting import post_or_fail
        from utils.gl_reference_types import GLRef

        dist = db.session.get(PartnerProfitDistribution, dist_id)
        if not dist or dist.status != "approved":
            return False
        if tenant_id is not None and dist.tenant_id != tenant_id:
            return False

        dist.status = "paid"
        net = float(dist.net_due)
        if net != 0:
            amount = abs(net)
            from utils.tax_settings import _resolve_main_branch

            branch_id = _resolve_main_branch(dist.tenant_id)
            try:
                partner_account = GLService.get_account_code_for_concept(
                    "PARTNER_CURRENT_ACCOUNT", tenant_id=dist.tenant_id
                )
            except Exception:
                partner_account = "2150"
            try:
                bank_account = GLService.get_default_liquidity_account("bank", tenant_id=dist.tenant_id)
            except Exception:
                bank_account = GL_ACCOUNTS.get("bank", "1120")
            lines = [
                {
                    "account": partner_account,
                    "concept_code": "PARTNER_CURRENT_ACCOUNT",
                    "debit": amount,
                    "description": f"دفع مستحق شريك - توزيع {dist.id}",
                },
                {
                    "account": bank_account,
                    "concept_code": "BANK",
                    "credit": amount,
                    "description": f"دفع مستحق شريك - توزيع {dist.id}",
                },
            ]
            post_or_fail(
                lines,
                description=f"دفع توزيع شريك #{dist.id}",
                reference_type=GLRef.PARTNER_DISTRIBUTION,
                reference_id=dist.id,
                tenant_id=dist.tenant_id,
                branch_id=branch_id,
            )
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush partner distribution payment")
            raise

        return True

    # ── Manual transactions ───────────────────────────────────

    @staticmethod
    def add_transaction(
        partner_id: int,
        transaction_type: str,
        amount: Decimal,
        currency: str | None = None,
        exchange_rate: Decimal = Decimal("1"),
        notes: str = "",
        created_by: Optional[int] = None,
        reference_number: str = "",
        tenant_id: Optional[int] = None,
    ) -> Optional[int]:
        from models import Partner, PartnerTransaction
        from utils.currency_utils import get_system_default_currency

        if not currency:
            currency = get_system_default_currency()
        partner = db.session.get(Partner, partner_id)
        if not partner:
            return None
        if tenant_id is not None and partner.tenant_id != tenant_id:
            return None

        amount_base = (amount * exchange_rate).quantize(Decimal("0.001"))
        old_bal = Decimal(str(partner.current_balance or 0))
        new_bal = old_bal + amount_base

        tx = PartnerTransaction(
            tenant_id=partner.tenant_id,
            partner_id=partner_id,
            transaction_type=transaction_type,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
            amount_base=amount_base,
            balance_after=new_bal,
            notes=notes,
            created_by=created_by,
            reference_number=reference_number,
        )
        db.session.add(tx)
        db.session.flush()
        partner.current_balance = new_bal
        if transaction_type == "withdrawal":
            partner.total_withdrawals = Decimal(str(partner.total_withdrawals or 0)) + abs(amount_base)
        elif transaction_type == "additional_investment":
            partner.total_additional_investment = Decimal(str(partner.total_additional_investment or 0)) + amount_base
        if amount_base != 0:
            from services.gl_service import GLService, GL_ACCOUNTS
            from services.gl_posting import post_or_fail
            from utils.gl_reference_types import GLRef
            from utils.tax_settings import _resolve_main_branch

            branch_id = _resolve_main_branch(partner.tenant_id)
            try:
                partner_account = GLService.get_account_code_for_concept(
                    "PARTNER_CURRENT_ACCOUNT", tenant_id=partner.tenant_id
                )
            except Exception:
                partner_account = "2150"
            try:
                bank_account = GLService.get_default_liquidity_account("bank", tenant_id=partner.tenant_id)
            except Exception:
                bank_account = GL_ACCOUNTS.get("bank", "1120")
            amt = float(abs(amount_base))
            if amount_base > 0:
                lines = [
                    {
                        "account": bank_account,
                        "concept_code": "BANK",
                        "debit": amt,
                        "description": notes or f"{transaction_type} - شريك {partner_id}",
                    },
                    {
                        "account": partner_account,
                        "concept_code": "PARTNER_CURRENT_ACCOUNT",
                        "credit": amt,
                        "description": notes or f"{transaction_type} - شريك {partner_id}",
                    },
                ]
            else:
                lines = [
                    {
                        "account": partner_account,
                        "concept_code": "PARTNER_CURRENT_ACCOUNT",
                        "debit": amt,
                        "description": notes or f"{transaction_type} - شريك {partner_id}",
                    },
                    {
                        "account": bank_account,
                        "concept_code": "BANK",
                        "credit": amt,
                        "description": notes or f"{transaction_type} - شريك {partner_id}",
                    },
                ]
            post_or_fail(
                lines,
                description=f"حركة شريك - {transaction_type} #{tx.id}",
                reference_type=GLRef.PARTNER_TRANSACTION,
                reference_id=tx.id,
                tenant_id=partner.tenant_id,
                branch_id=branch_id,
            )
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush partner manual transaction")
            raise

        return tx.id

    # ── Reports ─────────────────────────────────────────────────

    @staticmethod
    def get_partner_statement(partner_id: int, start_date: date, end_date: date) -> dict:
        """Full statement for a partner in a date range."""
        from models import Partner, PartnerTransaction

        partner = db.session.get(Partner, partner_id)
        if not partner:
            return {}

        txs = (
            PartnerTransaction.query.filter(
                PartnerTransaction.partner_id == partner_id,
                PartnerTransaction.transaction_date >= start_date,
                PartnerTransaction.transaction_date <= end_date,
            )
            .order_by(PartnerTransaction.transaction_date, PartnerTransaction.id)
            .all()
        )

        total_credit = sum(float(t.amount_base) for t in txs if float(t.amount_base) > 0)
        total_debit = sum(abs(float(t.amount_base)) for t in txs if float(t.amount_base) < 0)

        return {
            "partner": partner,
            "transactions": txs,
            "total_credit": total_credit,
            "total_debit": total_debit,
            "net_movement": total_credit - total_debit,
            "opening_balance": (float(txs[0].balance_after) - float(txs[0].amount_base) if txs else 0),
            "closing_balance": (float(txs[-1].balance_after) if txs else float(partner.current_balance or 0)),
        }
