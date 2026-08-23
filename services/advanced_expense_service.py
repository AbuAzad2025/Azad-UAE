"""Query services for the advanced ledger surfaces (customs taxes, advanced
expense categories/expenses, supplier options and cheque-integration stats).

Read-only helpers — callers own transactions and HTTP concerns."""


class AdvancedExpenseService:
    @staticmethod
    def list_customs_taxes(tenant_id):
        from models.advanced_accounting import CustomsTax

        return CustomsTax.query.filter_by(is_active=True, tenant_id=tenant_id).order_by(CustomsTax.name_ar).all()

    @staticmethod
    def list_expense_categories(tenant_id, ordered=False):
        from models.expense import ExpenseCategory

        query = ExpenseCategory.query.filter_by(is_active=True, tenant_id=tenant_id)
        if ordered:
            query = query.order_by(ExpenseCategory.name)
        return query.all()

    @staticmethod
    def paginate_advanced_expenses(tenant_id, page, per_page):
        from models.advanced_accounting import AdvancedExpense

        return (
            AdvancedExpense.query.filter_by(tenant_id=tenant_id)
            .order_by(AdvancedExpense.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

    @staticmethod
    def list_supplier_options(tenant_id):
        from models import Supplier

        return Supplier.query.filter_by(tenant_id=tenant_id).with_entities(Supplier.id, Supplier.name).all()

    @staticmethod
    def cheque_integration_data(tenant_id):
        """Recent cheques plus tenant-wide status counts and amount total."""
        from extensions import db
        from models import Cheque

        recent_cheques = Cheque.query.filter_by(tenant_id=tenant_id).order_by(Cheque.updated_at.desc()).limit(20).all()

        stats = {
            "total_cheques": Cheque.query.filter_by(tenant_id=tenant_id).count(),
            "pending_cheques": Cheque.query.filter_by(tenant_id=tenant_id, status="pending").count(),
            "cleared_cheques": Cheque.query.filter_by(tenant_id=tenant_id, status="cleared").count(),
            "bounced_cheques": Cheque.query.filter_by(tenant_id=tenant_id, status="bounced").count(),
            "total_amount": db.session.query(db.func.sum(Cheque.amount_aed)).filter_by(tenant_id=tenant_id).scalar()
            or 0,
        }
        return recent_cheques, stats
