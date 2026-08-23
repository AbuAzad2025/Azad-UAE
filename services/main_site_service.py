"""Dashboard, profile and public-site queries extracted from routes/main.py."""

from __future__ import annotations

from decimal import Decimal


class MainSiteService:
    """Read-only query surface for main site routes (behavior-preserving relocation)."""

    @staticmethod
    def count_active_products(tenant_id) -> int:
        from models import Product

        return Product.query.filter_by(is_active=True, tenant_id=tenant_id).count()

    @staticmethod
    def today_sales_totals(tenant_id, today, branch_id=None):
        """(count, sum) of confirmed sales for the given day, tenant-scoped."""
        from sqlalchemy import func

        from extensions import db
        from models import Sale

        query = db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed)).filter(
            func.date(Sale.sale_date) == today,
            Sale.status == "confirmed",
            Sale.tenant_id == tenant_id,
        )
        if branch_id is not None:
            query = query.filter(Sale.branch_id == branch_id)
        return query.first()

    @staticmethod
    def month_sales_totals(tenant_id, month_start, branch_id=None):
        """(count, sum) of confirmed sales since month_start, tenant-scoped."""
        from sqlalchemy import func

        from extensions import db
        from models import Sale

        query = db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed)).filter(
            func.date(Sale.sale_date) >= month_start,
            Sale.status == "confirmed",
            Sale.tenant_id == tenant_id,
        )
        if branch_id is not None:
            query = query.filter(Sale.branch_id == branch_id)
        return query.first()

    @staticmethod
    def month_profit_total(tenant_id, month_start, branch_id=None) -> Decimal:
        """Margin-weighted profit over sale lines since month_start."""
        from sqlalchemy import func

        from extensions import db
        from models import Sale, SaleLine

        profit_expr = func.sum(
            (SaleLine.unit_price - func.coalesce(SaleLine.cost_price, 0))
            * SaleLine.quantity
            * (100 - func.coalesce(SaleLine.discount_percent, 0))
            / 100
        )
        query = (
            db.session.query(profit_expr)
            .select_from(SaleLine)
            .join(Sale, SaleLine.sale_id == Sale.id)
            .filter(
                func.date(Sale.sale_date) >= month_start,
                Sale.status == "confirmed",
                Sale.tenant_id == tenant_id,
            )
        )
        if branch_id is not None:
            query = query.filter(Sale.branch_id == branch_id)
        return query.scalar() or Decimal("0")

    @staticmethod
    def total_receivables(branch_id=None) -> Decimal:
        """Outstanding confirmed-sale balances."""
        from sqlalchemy import func

        from extensions import db
        from models import Sale

        query = db.session.query(func.sum(Sale.amount_aed - Sale.paid_amount_aed)).filter(
            Sale.status == "confirmed",
            Sale.balance_due > 0,
        )
        if branch_id is not None:
            query = query.filter(Sale.branch_id == branch_id)
        return query.scalar() or Decimal("0")

    @staticmethod
    def liquidity_balance(kind, tenant_id, branch_id=None) -> Decimal:
        """Net debit-credit across active non-header liquidity accounts of a kind."""
        from sqlalchemy import func

        from extensions import db
        from models import GLAccount, GLJournalLine

        account_query = GLAccount.query.filter(
            GLAccount.tenant_id == int(tenant_id or 0),
            GLAccount.is_active,
            GLAccount.is_header.is_(False),
            GLAccount.liquidity_kind == kind,
        )
        if branch_id is not None:
            account_query = account_query.filter(GLAccount.branch_id == branch_id)
        account_ids = [acc.id for acc in account_query.all()]
        if not account_ids:
            return Decimal("0")
        debit_query = db.session.query(func.sum(GLJournalLine.debit)).filter(GLJournalLine.account_id.in_(account_ids))
        credit_query = db.session.query(func.sum(GLJournalLine.credit)).filter(
            GLJournalLine.account_id.in_(account_ids)
        )
        if branch_id is not None:
            debit_query = debit_query.join(GLJournalLine.entry).filter_by(branch_id=branch_id)
            credit_query = credit_query.join(GLJournalLine.entry).filter_by(branch_id=branch_id)
        return (debit_query.scalar() or Decimal("0")) - (credit_query.scalar() or Decimal("0"))

    @staticmethod
    def inventory_gl_value(inventory_account, branch_id=None) -> Decimal:
        """Net GL balance of the inventory control account (debit minus credit)."""
        from sqlalchemy import func

        from extensions import db
        from models import GLJournalLine

        inv_debit_query = db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=inventory_account.id)
        inv_credit_query = db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=inventory_account.id)
        if branch_id is not None:
            inv_debit_query = inv_debit_query.join(GLJournalLine.entry).filter_by(branch_id=branch_id)
            inv_credit_query = inv_credit_query.join(GLJournalLine.entry).filter_by(branch_id=branch_id)
        inv_debit = inv_debit_query.scalar() or Decimal("0")
        inv_credit = inv_credit_query.scalar() or Decimal("0")
        return inv_debit - inv_credit

    @staticmethod
    def recent_confirmed_sales(tenant_id, branch_id=None, limit=10):
        """Newest confirmed sales with customer/seller eager-loaded."""
        from sqlalchemy.orm import joinedload

        from models import Sale

        query = Sale.query.options(joinedload(Sale.customer), joinedload(Sale.seller)).filter_by(status="confirmed")
        if tenant_id is not None:
            query = query.filter(Sale.tenant_id == tenant_id)
        if branch_id is not None:
            query = query.filter(Sale.branch_id == branch_id)
        return query.order_by(Sale.sale_date.desc()).limit(limit).all()

    @staticmethod
    def seller_sales_totals(seller_id):
        """(count, sum) of all confirmed sales for a seller."""
        from sqlalchemy import func

        from extensions import db
        from models import Sale

        return (
            db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
            .filter(Sale.seller_id == seller_id, Sale.status == "confirmed")
            .first()
        )

    @staticmethod
    def seller_sales_totals_on(seller_id, day):
        """(count, sum) of a seller's confirmed sales on an exact day."""
        from sqlalchemy import func

        from extensions import db
        from models import Sale

        return (
            db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
            .filter(
                func.date(Sale.sale_date) == day,
                Sale.seller_id == seller_id,
                Sale.status == "confirmed",
            )
            .first()
        )

    @staticmethod
    def seller_sales_totals_since(seller_id, start_day):
        """(count, sum) of a seller's confirmed sales since a start day."""
        from sqlalchemy import func

        from extensions import db
        from models import Sale

        return (
            db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
            .filter(
                Sale.seller_id == seller_id,
                func.date(Sale.sale_date) >= start_day,
                Sale.status == "confirmed",
            )
            .first()
        )

    @staticmethod
    def payment_totals_for_user(user_id):
        """(count, sum) of payments recorded by a user."""
        from sqlalchemy import func

        from extensions import db
        from models import Payment

        return (
            db.session.query(func.count(Payment.id), func.sum(Payment.amount_aed))
            .filter(Payment.user_id == user_id)
            .first()
        )

    @staticmethod
    def recent_sales_for_seller(seller_id, limit=10):
        """A seller's newest confirmed sales."""
        from models import Sale

        return (
            Sale.query.filter_by(seller_id=seller_id, status="confirmed")
            .order_by(Sale.sale_date.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def email_exists(email, exclude_user_id, tenant_id):
        """Return another user holding this email within the tenant, if any."""
        from models import User

        return User.query.filter(
            User.email == email,
            User.id != exclude_user_id,
            User.tenant_id == tenant_id,
        ).first()

    @staticmethod
    def tenant_by_slug(slug):
        """Tenant lookup by public slug (public page — intentionally unscoped)."""
        from models.tenant import Tenant

        return Tenant.query.filter_by(slug=slug).first_or_404()

    @staticmethod
    def active_branches_for_tenant(tenant_id):
        """Active branches of a tenant ordered by name (public profile listing)."""
        from models.branch import Branch

        return Branch.query.filter_by(tenant_id=tenant_id, is_active=True).order_by(Branch.name).all()

    # ─── Dashboard chart datasets ───

    @staticmethod
    def sales_trend_daily(tenant_id, start_day, days=14, branch_id=None):
        """Daily confirmed-sales totals for the window [start_day, start_day+days).

        Returns a dense series (zero-filled days) of {"date", "total_aed"} floats.
        """
        from datetime import timedelta

        from sqlalchemy import func

        from extensions import db
        from models import Sale

        end_day = start_day + timedelta(days=days - 1)
        day_expr = func.date(Sale.sale_date)
        query = db.session.query(day_expr, func.coalesce(func.sum(Sale.amount_aed), 0)).filter(
            Sale.status == "confirmed",
            Sale.tenant_id == tenant_id,
            day_expr >= start_day,
            day_expr <= end_day,
        )
        if branch_id is not None:
            query = query.filter(Sale.branch_id == branch_id)

        totals = {str(row_date): Decimal(str(value or 0)) for row_date, value in query.group_by(day_expr).all()}

        series = []
        for offset in range(days):
            day = start_day + timedelta(days=offset)
            series.append({"date": day.isoformat(), "total_aed": float(totals.get(day.isoformat(), Decimal("0")))})
        return series

    @staticmethod
    def top_customers(tenant_id, start_day=None, limit=5, branch_id=None):
        """Top customers by confirmed-sales revenue since start_day."""
        from sqlalchemy import func

        from extensions import db
        from models import Customer, Sale

        revenue = func.sum(Sale.amount_aed)
        query = (
            db.session.query(Customer.id, Customer.name, func.coalesce(revenue, 0))
            .join(Sale, Sale.customer_id == Customer.id)
            .filter(Sale.status == "confirmed", Sale.tenant_id == tenant_id)
            .group_by(Customer.id, Customer.name)
            .order_by(revenue.desc())
        )
        if start_day is not None:
            query = query.filter(func.date(Sale.sale_date) >= start_day)
        if branch_id is not None:
            query = query.filter(Sale.branch_id == branch_id)

        return [
            {"customer_id": customer_id, "name": name, "total_aed": float(total or 0)}
            for customer_id, name, total in query.limit(limit).all()
        ]

    @staticmethod
    def stock_alert_summary(user, limit=10):
        """Low/out-of-stock product lists and counts for dashboard widgets."""
        from services.stock_service import StockService

        low_stock = StockService.get_low_stock_products(limit=limit, user=user) or []
        out_of_stock = StockService.get_out_of_stock_products(user=user) or []

        def _row(product):
            return {
                "id": product.id,
                "name": getattr(product, "name_ar", None) or product.name,
                "qty": float(getattr(product, "current_stock", None) or 0),
                "min_qty": float(getattr(product, "min_stock_alert", None) or 0),
            }

        return {
            "low_stock": [_row(p) for p in low_stock],
            "out_of_stock": [_row(p) for p in out_of_stock[:limit]],
            "low_stock_count": len(low_stock),
            "out_of_stock_count": len(out_of_stock),
        }
