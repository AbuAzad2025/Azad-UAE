from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from flask_babel import gettext
from sqlalchemy import case as sa_case
from sqlalchemy import func

from extensions import db

logger = logging.getLogger(__name__)


class PartnerService:
    # ── Period aggregation ──────────────────────────────────────

    @staticmethod
    def _months_in_period(period_start: date, period_end: date) -> int:
        """Calendar months touched by an inclusive period (minimum 1)."""
        if period_end < period_start:
            return 1
        return max((period_end.year - period_start.year) * 12 + (period_end.month - period_start.month) + 1, 1)

    @staticmethod
    def get_scope_revenue(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = "company",
        scope_id: int | None = None,
    ) -> Decimal:
        """Net revenue (VAT excluded) in base currency for a scope.

        VAT is a liability, never revenue, so it is stripped per row:
        ``amount_aed - tax_amount * exchange_rate`` (same linear conversion
        the sale used to compute ``amount_aed``). Discounts are already
        netted in ``amount_aed`` at sale time.
        """
        from models import Sale

        if scope_type == "warehouse" and scope_id:
            from models import SaleLine

            # Net of VAT: prices already including VAT are spread back with
            # the sale's own statutory rate; otherwise the tax was extra.
            q = (
                db.session.query(
                    func.sum(
                        (SaleLine.line_total * func.coalesce(Sale.exchange_rate, 1))
                        / sa_case(
                            (
                                Sale.prices_include_vat.is_(True),
                                1 + func.coalesce(Sale.tax_rate, 0) / 100,
                            ),
                            else_=1,
                        )
                    )
                )
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

        net_amount = Sale.amount_aed - Sale.tax_amount * func.coalesce(Sale.exchange_rate, 1)
        q = db.session.query(func.sum(net_amount)).filter(
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
        scope_id: int | None = None,
    ) -> Decimal:
        from models import Sale, SaleLine

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
        scope_id: int | None = None,
    ) -> Decimal:
        from models import Expense

        q = db.session.query(func.sum(Expense.amount_aed)).filter(
            Expense.tenant_id == tenant_id,
            Expense.is_reversed.is_(False),
            func.date(Expense.expense_date) >= period_start,
            func.date(Expense.expense_date) <= period_end,
        )
        if scope_type == "branch" and scope_id:
            q = q.filter(Expense.branch_id == scope_id)
        elif scope_type == "warehouse" and scope_id:
            q = q.filter(Expense.warehouse_id == scope_id)
        result = q.scalar() or Decimal("0")
        return result

    @staticmethod
    def get_scope_commissions(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = "company",
        scope_id: int | None = None,
    ) -> Decimal:
        """Product commissions accrued for a scope in a period, net of returns.

        Product commissions are a real cost of the sale (Dr COMMISSION_EXPENSE
        at order time), so a company-level distribution must not allocate a
        profit that this leg already took. Return reversals that landed in the
        same period reduce the figure by the same proportion the return
        journal used.
        """
        from models import PartnerCommissionEntry, Sale

        q = (
            db.session.query(func.coalesce(func.sum(PartnerCommissionEntry.commission_amount_aed), Decimal("0")))
            .join(Sale, PartnerCommissionEntry.sale_id == Sale.id)
            .filter(
                PartnerCommissionEntry.tenant_id == tenant_id,
                Sale.status == "confirmed",
                func.date(Sale.sale_date) >= period_start,
                func.date(Sale.sale_date) <= period_end,
            )
        )
        if scope_type == "branch" and scope_id:
            q = q.filter(Sale.branch_id == scope_id)
        elif scope_type == "warehouse" and scope_id:
            q = q.filter(Sale.warehouse_id == scope_id)
        gross = q.scalar() or Decimal("0")

        from models import ProductReturn, ProductReturnLine, SaleLine

        # Returns in the same period claw back their proportional share.
        return_rows = (
            db.session.query(
                ProductReturnLine.quantity, SaleLine.quantity, PartnerCommissionEntry.commission_amount_aed
            )
            .join(ProductReturn, ProductReturn.id == ProductReturnLine.return_id)
            .join(SaleLine, SaleLine.id == ProductReturnLine.sale_line_id)
            .join(
                PartnerCommissionEntry,
                PartnerCommissionEntry.sale_line_id == SaleLine.id,
            )
            .filter(
                ProductReturn.tenant_id == tenant_id,
                ProductReturn.status != "rejected",
                func.date(ProductReturn.return_date) >= period_start,
                func.date(ProductReturn.return_date) <= period_end,
            )
        )
        reversed_total = Decimal("0")
        for ret_qty, sold_qty, commission in return_rows.all():
            sold = Decimal(str(sold_qty or 0))
            returned = Decimal(str(ret_qty or 0))
            if sold <= Decimal("0") or returned <= Decimal("0"):
                continue
            ratio = returned / sold
            if ratio > Decimal("1"):
                ratio = Decimal("1")
            reversed_total += Decimal(str(commission or 0)) * ratio
        net = gross - reversed_total.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return net if net > Decimal("0") else Decimal("0")

    @staticmethod
    def calculate_scope_profit(
        tenant_id: int,
        period_start: date,
        period_end: date,
        scope_type: str = "company",
        scope_id: int | None = None,
    ) -> dict:
        """Return full P&L for a scope."""
        revenue = PartnerService.get_scope_revenue(tenant_id, period_start, period_end, scope_type, scope_id)
        cogs = PartnerService.get_scope_cogs(tenant_id, period_start, period_end, scope_type, scope_id)
        expenses = PartnerService.get_scope_expenses(tenant_id, period_start, period_end, scope_type, scope_id)
        commissions = PartnerService.get_scope_commissions(tenant_id, period_start, period_end, scope_type, scope_id)
        gross_profit = revenue - cogs
        net_profit = gross_profit - expenses - commissions
        return {
            "revenue": float(revenue),
            "cogs": float(cogs),
            "expenses": float(expenses),
            "commissions": float(commissions),
            "gross_profit": float(gross_profit),
            "net_profit": float(net_profit),
        }

    # ── Distribution creation ───────────────────────────────────

    @staticmethod
    def create_distributions(
        tenant_id: int,
        period_start: date,
        period_end: date,
        created_by: int | None = None,
    ) -> list[int]:
        """Create draft distributions for ALL active partners for the period.

        Validates:
        - Total profit-share percentages per scope ≤ 100 %
          (a scope is ``(scope_type, scope_id)`` — a company-level 100%
          partner and a branch-level 100% partner hold different scopes
          and must not block each other)
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

        scope_totals: dict[tuple[str, int | None], Decimal] = {}
        for p in partners:
            key = (getattr(p, "scope_type", "company") or "company", getattr(p, "scope_id", None))
            scope_totals[key] = scope_totals.get(key, Decimal("0")) + Decimal(
                str(getattr(p, "share_percentage", 0) or 0)
            )
        for (scope_type, scope_id), total_share_pct in scope_totals.items():
            if total_share_pct > Decimal("100"):
                scope_label = f"{scope_type}/{scope_id}"
                raise ValueError(
                    gettext(f"إجمالي نسب الأرباح في النطاق ({scope_label}) يتجاوز 100%: {total_share_pct}%")
                )

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
                    gettext(
                        f"فشل حساب أرباح النطاق للشريك {partner.id} ({partner.scope_type}/{partner.scope_id}): {exc}"
                    )
                ) from exc

            net_profit = Decimal(str(pnl["net_profit"]))
            total_expenses_dec = Decimal(str(pnl["expenses"]))
            total_commissions_dec = Decimal(str(pnl.get("commissions", 0) or 0))

            share_pct = Decimal(str(partner.share_percentage or 0))
            expense_pct = Decimal(str(partner.expense_share_percentage or 0))
            loss_pct = Decimal(str(partner.loss_share_percentage or 0))
            # The fixed amount is monthly: scale it by the number of months
            # the distribution period spans so a quarter pays three months.
            fixed = Decimal(str(partner.fixed_monthly_amount or 0)) * Decimal(
                PartnerService._months_in_period(period_start, period_end)
            )
            threshold = Decimal(str(partner.min_profit_threshold or 0))

            share_amount = Decimal("0")
            expense_share = Decimal("0")
            loss_share = Decimal("0")

            if net_profit > 0:
                if net_profit >= threshold:
                    share_amount = (net_profit * share_pct / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                expense_share = (total_expenses_dec * expense_pct / 100).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )
            elif net_profit < 0:
                if loss_pct <= Decimal("0"):
                    raise ValueError(
                        gettext(f"الشريك {partner.id} ليس لديه نسبة تحمل خسارة بينما صافي الربح سالب ({net_profit})")
                    )
                loss_share = (abs(net_profit) * loss_pct / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                expense_share = (total_expenses_dec * expense_pct / 100).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )

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
                total_commissions=total_commissions_dec,
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
    def _distribution_branch(tenant_id) -> int | None:
        from utils.tax_settings import _resolve_main_branch

        return _resolve_main_branch(tenant_id)

    @staticmethod
    def approve_distribution(dist_id: int, approved_by: int, tenant_id: int | None = None) -> bool:
        from models import Partner, PartnerProfitDistribution, PartnerTransaction

        dist = db.session.get(PartnerProfitDistribution, dist_id)
        if not dist or dist.status != "draft":
            return False
        if tenant_id is not None and dist.tenant_id != tenant_id:
            return False

        dist.status = "approved"
        dist.approved_by = approved_by
        dist.approved_at = datetime.now(UTC)
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
                notes=gettext(f"توزيع فترة {dist.period_start} – {dist.period_end}"),
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

            # Gl accrual: credit the partner's current account so the GL and
            # the partner ledger agree, instead of only debiting at payment
            # time (which left the GL partner account permanently short).
            # Positive entitlements accrue a commission expense; a loss share
            # nets against the same expense (the partner funds the loss).
            from services.gl_posting import post_or_fail
            from services.gl_service import GLService
            from utils.gl_reference_types import GLRef

            amt = Decimal(str(abs(net))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            try:
                branch_id = PartnerService._distribution_branch(dist.tenant_id)
            except Exception:
                branch_id = None
            partner_account = GLService.get_account_code_for_concept(
                "PARTNER_CURRENT_ACCOUNT", tenant_id=dist.tenant_id, branch_id=branch_id
            )
            commission_account = GLService.get_account_code_for_concept(
                "COMMISSION_EXPENSE", tenant_id=dist.tenant_id, branch_id=branch_id
            )
            if net > 0:
                lines = [
                    {
                        "account": commission_account,
                        "concept_code": "COMMISSION_EXPENSE",
                        "debit": amt,
                        "description": gettext(f"استحقاق توزيع شريك #{dist.id}"),
                    },
                    {
                        "account": partner_account,
                        "concept_code": "PARTNER_CURRENT_ACCOUNT",
                        "credit": amt,
                        "description": gettext(f"استحقاق توزيع شريك #{dist.id}"),
                    },
                ]
            else:
                lines = [
                    {
                        "account": partner_account,
                        "concept_code": "PARTNER_CURRENT_ACCOUNT",
                        "debit": amt,
                        "description": gettext(f"تحميل خسارة شريك #{dist.id}"),
                    },
                    {
                        "account": commission_account,
                        "concept_code": "COMMISSION_EXPENSE",
                        "credit": amt,
                        "description": gettext(f"تحميل خسارة شريك #{dist.id}"),
                    },
                ]
            post_or_fail(
                lines,
                description=gettext(f"استحقاق توزيع شريك #{dist.id}"),
                reference_type=GLRef.PARTNER_DISTRIBUTION,
                reference_id=dist.id,
                tenant_id=dist.tenant_id,
                branch_id=branch_id,
            )

        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush partner distribution approval")
            raise

        return True

    @staticmethod
    def pay_distribution(dist_id: int, tenant_id: int | None = None) -> bool:
        from models import PartnerProfitDistribution
        from services.gl_posting import post_or_fail
        from services.gl_service import GLService
        from utils.gl_reference_types import GLRef

        dist = db.session.get(PartnerProfitDistribution, dist_id)
        if not dist or dist.status != "approved":
            return False
        if tenant_id is not None and dist.tenant_id != tenant_id:
            return False

        dist.status = "paid"
        net = float(dist.net_due)
        if net > 0:
            amount = abs(net)
            branch_id = PartnerService._distribution_branch(dist.tenant_id)
            try:
                partner_account = GLService.get_account_code_for_concept(
                    "PARTNER_CURRENT_ACCOUNT", tenant_id=dist.tenant_id, branch_id=branch_id
                )
            except Exception:
                partner_account = "2150"
            try:
                bank_account = GLService.get_default_liquidity_account(
                    "bank", tenant_id=dist.tenant_id, branch_id=branch_id
                )
            except Exception:
                bank_account = "1120"
            lines = [
                {
                    "account": partner_account,
                    "concept_code": "PARTNER_CURRENT_ACCOUNT",
                    "debit": amount,
                    "description": gettext(f"دفع مستحق شريك - توزيع {dist.id}"),
                },
                {
                    "account": bank_account,
                    "concept_code": "BANK",
                    "credit": amount,
                    "description": gettext(f"دفع مستحق شريك - توزيع {dist.id}"),
                },
            ]
            post_or_fail(
                lines,
                description=gettext(f"دفع توزيع شريك #{dist.id}"),
                reference_type=GLRef.PARTNER_DISTRIBUTION,
                reference_id=dist.id,
                tenant_id=dist.tenant_id,
                branch_id=branch_id,
            )
            # Settle the partner ledger: payment reduces the accrued balance
            # and is written to the statement so current_balance, the
            # transaction ledger and the GL all agree.
            from models import Partner, PartnerTransaction

            partner = db.session.get(Partner, dist.partner_id)
            if partner:
                amt = Decimal(str(amount)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                new_bal = Decimal(str(partner.current_balance or 0)) - amt
                tx = PartnerTransaction(
                    tenant_id=dist.tenant_id,
                    partner_id=dist.partner_id,
                    distribution_id=dist.id,
                    transaction_type="withdrawal",
                    amount=-amt,
                    amount_base=-amt,
                    balance_after=new_bal,
                    transaction_date=datetime.now(UTC).date(),
                    notes=gettext(f"دفع توزيع {dist.period_start} – {dist.period_end}"),
                )
                db.session.add(tx)
                partner.current_balance = new_bal
                partner.total_withdrawals = Decimal(str(partner.total_withdrawals or 0)) + amt
        # A negative (loss) entitlement is absorbed at accrual time — there
        # is no cash leg, so marking it paid only closes the lifecycle.
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
        created_by: int | None = None,
        reference_number: str = "",
        tenant_id: int | None = None,
    ) -> int | None:
        from models import Partner, PartnerTransaction
        from utils.currency_utils import get_system_default_currency

        if not currency:
            currency = get_system_default_currency()
        partner = db.session.get(Partner, partner_id)
        if not partner:
            return None
        if tenant_id is not None and partner.tenant_id != tenant_id:
            return None

        amount_base = (amount * exchange_rate).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
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
            from services.gl_posting import post_or_fail
            from services.gl_service import GLService
            from utils.gl_reference_types import GLRef
            from utils.tax_settings import _resolve_main_branch

            branch_id = _resolve_main_branch(partner.tenant_id)
            try:
                partner_account = GLService.get_account_code_for_concept(
                    "PARTNER_CURRENT_ACCOUNT", tenant_id=partner.tenant_id, branch_id=branch_id
                )
            except Exception:
                partner_account = "2150"
            try:
                bank_account = GLService.get_default_liquidity_account(
                    "bank", tenant_id=partner.tenant_id, branch_id=branch_id
                )
            except Exception:
                bank_account = "1120"
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
                description=gettext(f"حركة شريك - {transaction_type} #{tx.id}"),
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
                PartnerTransaction.tenant_id == partner.tenant_id,
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

    @staticmethod
    def get_partner_activity(partner_id, tid):
        """Latest distributions (12) and transactions (20), tenant-scoped."""
        from models import PartnerProfitDistribution, PartnerTransaction

        dists_q = PartnerProfitDistribution.query.filter_by(partner_id=partner_id)
        if tid is not None:
            dists_q = dists_q.filter(PartnerProfitDistribution.tenant_id == tid)
        latest_dists = dists_q.order_by(PartnerProfitDistribution.period_end.desc()).limit(12).all()

        txs_q = PartnerTransaction.query.filter_by(partner_id=partner_id)
        if tid is not None:
            txs_q = txs_q.filter(PartnerTransaction.tenant_id == tid)
        latest_txs = txs_q.order_by(PartnerTransaction.transaction_date.desc()).limit(20).all()

        return latest_dists, latest_txs

    @staticmethod
    def link_product_partner(partner_id: int, customer_id: int, tenant_id: int | None = None) -> bool:
        """Link a product-level partner (Customer) to a company-level Partner.

        The same human can hold both roles; this records that fact so the
        unified statement can report both earnings streams together. The link
        is tenant-scoped: a customer from another tenant can never attach.
        """
        from models import Customer, Partner

        partner = db.session.get(Partner, partner_id)
        customer = db.session.get(Customer, customer_id)
        if not partner or not customer:
            return False
        if tenant_id is not None and partner.tenant_id != tenant_id:
            return False
        if customer.tenant_id != partner.tenant_id:
            return False
        if customer.customer_type not in ("partner", "merchant"):
            return False
        customer.partner_id = partner.id
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush product-partner link")
            raise
        return True

    @staticmethod
    def unlink_product_partner(customer_id: int, tenant_id: int | None = None) -> bool:
        from models import Customer

        customer = db.session.get(Customer, customer_id)
        if not customer:
            return False
        if tenant_id is not None and customer.tenant_id != tenant_id:
            return False
        customer.partner_id = None
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush product-partner unlink")
            raise
        return True

    @staticmethod
    def get_unified_statement(partner_id: int, tenant_id: int | None = None) -> dict:
        """One-person view mixing both roles.

        Company-level earnings (distributions + current balance) plus
        product-level earnings (per-line commissions of every linked
        customer), tenant-scoped. Returns amounts in base currency; a partner
        with no linked customer still returns their company figures alone.
        """
        from models import Customer, Partner, PartnerCommissionEntry, PartnerProfitDistribution

        partner = db.session.get(Partner, partner_id)
        if not partner:
            return {}
        if tenant_id is not None and partner.tenant_id != tenant_id:
            return {}

        dists = (
            PartnerProfitDistribution.query.filter_by(partner_id=partner.id, tenant_id=partner.tenant_id)
            .order_by(PartnerProfitDistribution.period_start.desc())
            .all()
        )
        linked_customers = Customer.query.filter_by(partner_id=partner.id, tenant_id=partner.tenant_id).all()
        customer_ids = [c.id for c in linked_customers]
        product_commissions = Decimal("0")
        if customer_ids:
            product_commissions = db.session.query(
                func.coalesce(func.sum(PartnerCommissionEntry.commission_amount_aed), Decimal("0"))
            ).filter(
                PartnerCommissionEntry.tenant_id == partner.tenant_id,
                PartnerCommissionEntry.partner_customer_id.in_(customer_ids),
            ).scalar() or Decimal("0")
        company_total = sum((Decimal(str(d.share_amount or 0)) for d in dists), Decimal("0"))
        return {
            "partner": partner,
            "distributions": dists,
            "linked_customers": [
                {"id": c.id, "name": c.name, "customer_type": c.customer_type} for c in linked_customers
            ],
            "company_total": float(company_total),
            "current_balance": float(partner.current_balance or 0),
            "product_commissions_total": float(product_commissions),
            # Lifetime earned across both roles (entitlements, not cash).
            "combined_total": float(company_total + product_commissions),
        }

    @staticmethod
    def list_distributions(tid, status=""):
        """Tenant-scoped distribution history (latest 200)."""
        from models import PartnerProfitDistribution

        q = PartnerProfitDistribution.query.filter_by(tenant_id=tid)
        if status:
            q = q.filter_by(status=status)
        return q.order_by(PartnerProfitDistribution.period_end.desc()).limit(200).all()
