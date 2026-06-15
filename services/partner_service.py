"""
Partner Service — Profit/Loss Calculation & Distribution

Handles:
  • Period revenue/expense aggregation per scope (company / branch / warehouse)
  • Profit/loss share calculation per partner
  • Distribution creation (draft → approved → paid)
  • Running balance updates
  • GL journal generation (optional)
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from extensions import db


class PartnerService:
    """Core business logic for partner profit/loss distribution."""

    # ── Period aggregation ──────────────────────────────────────

    @staticmethod
    def get_scope_revenue(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = 'company',
        scope_id: Optional[int] = None,
    ) -> Decimal:
        """Total confirmed sales revenue for the scope in the period (base currency)."""
        from models import Sale

        # Warehouse scope is line-based: a single sale may contain lines from
        # several warehouses, so summing Sale.amount_aed over a SaleLine join
        # would multiply the sale total by its line count. Sum line revenue
        # (converted to base currency) attributable to this warehouse instead.
        if scope_type == 'warehouse' and scope_id:
            from models import SaleLine
            q = db.session.query(
                func.sum(SaleLine.line_total * func.coalesce(Sale.exchange_rate, 1))
            ).join(SaleLine, SaleLine.sale_id == Sale.id).filter(
                Sale.tenant_id == tenant_id,
                Sale.status == 'confirmed',
                func.date(Sale.sale_date) >= period_start,
                func.date(Sale.sale_date) <= period_end,
                SaleLine.warehouse_id == scope_id,
            )
            return q.scalar() or Decimal('0')

        q = db.session.query(func.sum(Sale.amount_aed)).filter(
            Sale.tenant_id == tenant_id,
            Sale.status == 'confirmed',
            func.date(Sale.sale_date) >= period_start,
            func.date(Sale.sale_date) <= period_end,
        )
        if scope_type == 'branch' and scope_id:
            q = q.filter(Sale.branch_id == scope_id)
        result = q.scalar() or Decimal('0')
        return result

    @staticmethod
    def get_scope_cogs(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = 'company',
        scope_id: Optional[int] = None,
    ) -> Decimal:
        """Cost of goods sold using the historical cost captured on each sale line.

        Uses SaleLine.cost_price (cost at time of sale) rather than the product's
        current cost, and aligns the period filter with the sale date and
        confirmed status so revenue and COGS cover the same transactions.
        """
        from models import SaleLine, Sale
        q = db.session.query(
            func.sum(SaleLine.quantity * func.coalesce(SaleLine.cost_price, 0))
        ).join(Sale, SaleLine.sale_id == Sale.id).filter(
            SaleLine.tenant_id == tenant_id,
            Sale.status == 'confirmed',
            func.date(Sale.sale_date) >= period_start,
            func.date(Sale.sale_date) <= period_end,
        )
        if scope_type == 'branch' and scope_id:
            q = q.filter(Sale.branch_id == scope_id)
        elif scope_type == 'warehouse' and scope_id:
            q = q.filter(SaleLine.warehouse_id == scope_id)
        result = q.scalar() or Decimal('0')
        return result

    @staticmethod
    def get_scope_expenses(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = 'company',
        scope_id: Optional[int] = None,
    ) -> Decimal:
        """Total confirmed expenses for the scope.

        Expenses are only tracked at company/branch granularity (the Expense
        model has no warehouse dimension). Warehouse-scoped partners therefore
        share gross profit (revenue - COGS) and are not charged company-wide
        operating expenses, which previously inflated their loss share.
        """
        from models import Expense

        if scope_type == 'warehouse':
            return Decimal('0')

        q = db.session.query(func.sum(Expense.amount_aed)).filter(
            Expense.tenant_id == tenant_id,
            Expense.is_reversed == False,
            func.date(Expense.expense_date) >= period_start,
            func.date(Expense.expense_date) <= period_end,
        )
        if scope_type == 'branch' and scope_id:
            q = q.filter(Expense.branch_id == scope_id)
        result = q.scalar() or Decimal('0')
        return result

    @staticmethod
    def calculate_scope_profit(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = 'company',
        scope_id: Optional[int] = None,
    ) -> dict:
        """Return full P&L for a scope."""
        revenue = PartnerService.get_scope_revenue(tenant_id, period_start, period_end, scope_type, scope_id)
        cogs = PartnerService.get_scope_cogs(tenant_id, period_start, period_end, scope_type, scope_id)
        expenses = PartnerService.get_scope_expenses(tenant_id, period_start, period_end, scope_type, scope_id)
        gross_profit = revenue - cogs
        net_profit = gross_profit - expenses
        return {
            'revenue': float(revenue),
            'cogs': float(cogs),
            'expenses': float(expenses),
            'gross_profit': float(gross_profit),
            'net_profit': float(net_profit),
        }

    # ── Distribution creation ───────────────────────────────────

    @staticmethod
    def create_distributions(
        tenant_id: int,
        period_start: date,
        period_end: date,
        created_by: Optional[int] = None,
    ) -> List[int]:
        """Create draft distributions for ALL active partners for the period."""
        from models import Partner, PartnerProfitDistribution

        partners = Partner.query.filter_by(
            tenant_id=tenant_id,
            is_active=True,
        ).all()

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
            pnl = PartnerService.calculate_scope_profit(
                tenant_id, period_start, period_end,
                partner.scope_type, partner.scope_id,
            )

            net_profit = Decimal(str(pnl['net_profit']))

            # Calculate shares
            share_pct = Decimal(str(partner.share_percentage or 0))
            expense_pct = Decimal(str(partner.expense_share_percentage or 0))
            loss_pct = Decimal(str(partner.loss_share_percentage or 0))
            fixed = Decimal(str(partner.fixed_monthly_amount or 0))
            threshold = Decimal(str(partner.min_profit_threshold or 0))

            share_amount = Decimal('0')
            expense_share = Decimal('0')
            loss_share = Decimal('0')

            if net_profit > 0:
                # Profit: apply share percentage, check threshold
                if net_profit >= threshold:
                    share_amount = (net_profit * share_pct / 100).quantize(Decimal('0.001'))
                expense_share = (Decimal(str(pnl['expenses'])) * expense_pct / 100).quantize(Decimal('0.001'))
            elif net_profit < 0:
                # Loss: partner bears loss share
                loss_share = (abs(net_profit) * loss_pct / 100).quantize(Decimal('0.001'))
                expense_share = (Decimal(str(pnl['expenses'])) * expense_pct / 100).quantize(Decimal('0.001'))

            net_due = share_amount - expense_share - loss_share + fixed

            dist = PartnerProfitDistribution(
                tenant_id=tenant_id,
                partner_id=partner.id,
                period_start=period_start,
                period_end=period_end,
                scope_type=partner.scope_type,
                scope_id=partner.scope_id,
                total_revenue=pnl['revenue'],
                total_cogs=pnl['cogs'],
                total_expenses=pnl['expenses'],
                net_profit=pnl['net_profit'],
                share_percentage=share_pct,
                share_amount=share_amount,
                expense_share_percentage=expense_pct,
                expense_share_amount=expense_share,
                loss_share_percentage=loss_pct,
                loss_share_amount=loss_share,
                fixed_amount=fixed,
                net_due=net_due,
                status='draft',
                created_by=created_by,
            )
            db.session.add(dist)
            db.session.flush()
            distribution_ids.append(dist.id)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return distribution_ids

    # ── Distribution lifecycle ──────────────────────────────────

    @staticmethod
    def approve_distribution(dist_id: int, approved_by: int, tenant_id: Optional[int] = None) -> bool:
        """Approve a draft distribution and create profit_share transaction.

        When tenant_id is provided the distribution must belong to it, preventing
        cross-tenant access via a guessed id.
        """
        from models import PartnerProfitDistribution, PartnerTransaction, Partner

        dist = PartnerProfitDistribution.query.get(dist_id)
        if not dist or dist.status != 'draft':
            return False
        if tenant_id is not None and dist.tenant_id != tenant_id:
            return False

        dist.status = 'approved'
        dist.approved_by = approved_by
        dist.approved_at = datetime.now(timezone.utc)

        # Create transaction
        net = float(dist.net_due)
        if net != 0:
            tx_type = 'profit_share' if net > 0 else 'loss_share'
            tx = PartnerTransaction(
                tenant_id=dist.tenant_id,
                partner_id=dist.partner_id,
                distribution_id=dist.id,
                transaction_type=tx_type,
                amount=abs(net) if net > 0 else -abs(net),
                amount_base=abs(net) if net > 0 else -abs(net),
                transaction_date=dist.period_end,
                notes=f'توزيع فترة {dist.period_start} – {dist.period_end}',
            )
            db.session.add(tx)

            # Update partner balance
            partner = Partner.query.get(dist.partner_id)
            if partner:
                old_bal = Decimal(str(partner.current_balance or 0))
                new_bal = old_bal + Decimal(str(tx.amount))
                partner.current_balance = new_bal
                partner.total_profit_received = (Decimal(str(partner.total_profit_received or 0))
                                                  + (Decimal(str(tx.amount)) if net > 0 else Decimal('0')))
                partner.total_loss_borne = (Decimal(str(partner.total_loss_borne or 0))
                                             + (abs(Decimal(str(tx.amount))) if net < 0 else Decimal('0')))
                tx.balance_after = new_bal

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return True

    @staticmethod
    def pay_distribution(dist_id: int, tenant_id: Optional[int] = None) -> bool:
        """Mark distribution as paid (tenant-scoped when tenant_id is given)."""
        from models import PartnerProfitDistribution

        dist = PartnerProfitDistribution.query.get(dist_id)
        if not dist or dist.status != 'approved':
            return False
        if tenant_id is not None and dist.tenant_id != tenant_id:
            return False

        dist.status = 'paid'
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return True

    # ── Manual transactions ───────────────────────────────────

    @staticmethod
    def add_transaction(
        partner_id: int,
        transaction_type: str,
        amount: Decimal,
        currency: str = None,
        exchange_rate: Decimal = Decimal('1'),
        notes: str = '',
        created_by: Optional[int] = None,
        reference_number: str = '',
        tenant_id: Optional[int] = None,
    ) -> Optional[int]:
        """Record a manual transaction and update partner balance.

        When tenant_id is provided the partner must belong to it, preventing
        cross-tenant manipulation via a guessed id.
        """
        from models import Partner, PartnerTransaction
        from utils.currency_utils import get_system_default_currency

        if not currency:
            currency = get_system_default_currency()
        partner = Partner.query.get(partner_id)
        if not partner:
            return None
        if tenant_id is not None and partner.tenant_id != tenant_id:
            return None

        amount_base = (amount * exchange_rate).quantize(Decimal('0.001'))
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

        # Update partner aggregates
        partner.current_balance = new_bal
        if transaction_type == 'withdrawal':
            partner.total_withdrawals = (Decimal(str(partner.total_withdrawals or 0)) + abs(amount_base))
        elif transaction_type == 'additional_investment':
            partner.total_additional_investment = (Decimal(str(partner.total_additional_investment or 0)) + amount_base)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return tx.id

    # ── Reports ─────────────────────────────────────────────────

    @staticmethod
    def get_partner_statement(partner_id: int, start_date: date, end_date: date) -> dict:
        """Full statement for a partner in a date range."""
        from models import Partner, PartnerTransaction

        partner = Partner.query.get(partner_id)
        if not partner:
            return {}

        txs = PartnerTransaction.query.filter(
            PartnerTransaction.partner_id == partner_id,
            PartnerTransaction.transaction_date >= start_date,
            PartnerTransaction.transaction_date <= end_date,
        ).order_by(PartnerTransaction.transaction_date, PartnerTransaction.id).all()

        total_credit = sum(float(t.amount_base) for t in txs if float(t.amount_base) > 0)
        total_debit = sum(abs(float(t.amount_base)) for t in txs if float(t.amount_base) < 0)

        return {
            'partner': partner,
            'transactions': txs,
            'total_credit': total_credit,
            'total_debit': total_debit,
            'net_movement': total_credit - total_debit,
            'opening_balance': float(txs[0].balance_after) - float(txs[0].amount_base) if txs else 0,
            'closing_balance': float(txs[-1].balance_after) if txs else float(partner.current_balance or 0),
        }
