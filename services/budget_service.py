"""
Budget CRUD service — budget creation, approval workflow, line management.
"""

from datetime import UTC, datetime
from decimal import Decimal

from flask_babel import gettext

from extensions import db
from models import Budget, BudgetLine, GLAccount
from utils.helpers import generate_number
from utils.tenanting import get_active_tenant_id, tenant_query


class BudgetService:
    @staticmethod
    def _tid(user):
        return get_active_tenant_id(user)

    @classmethod
    def create_budget(cls, data, user):
        tid = cls._tid(user)
        budget = Budget(
            tenant_id=tid,
            budget_number=generate_number("BUD", Budget, "budget_number"),
            name_ar=data["name_ar"],
            name_en=data.get("name_en"),
            fiscal_year=int(data["fiscal_year"]),
            period_type=data.get("period_type", "annual"),
            period_start=data["period_start"],
            period_end=data["period_end"],
            enforcement=data.get("enforcement", "warn"),
            branch_id=int(data["branch_id"]) if data.get("branch_id") else None,
            notes=data.get("notes"),
            created_by=user.id,
            status="draft",
        )
        db.session.add(budget)
        db.session.flush()

        lines_data = data.get("lines", [])
        for line in lines_data:
            account = GLAccount.query.filter_by(
                tenant_id=tid,
                code=str(line["account_code"]),
            ).first()
            if not account:
                raise ValueError(gettext(f"حساب {line['account_code']} غير موجود."))
            bl = BudgetLine(
                tenant_id=tid,
                budget_id=budget.id,
                account_id=account.id,
                budgeted_amount=Decimal(str(line["budgeted_amount"])),
                notes=line.get("notes"),
            )
            db.session.add(bl)

        cls._recalculate_totals(budget)
        db.session.flush()
        return budget

    @classmethod
    def update_budget(cls, budget, data):
        if budget.status not in ("draft",):
            raise ValueError(gettext("لا يمكن تعديل ميزانية غير مسودة."))

        for field in ("name_ar", "name_en", "notes", "enforcement", "branch_id"):
            if field in data:
                budget[field] = data[field]

        if "lines" in data:
            BudgetLine.query.filter_by(budget_id=budget.id).delete()
            for line in data["lines"]:
                account = GLAccount.query.filter_by(
                    tenant_id=budget.tenant_id,
                    code=str(line["account_code"]),
                ).first()
                if not account:
                    raise ValueError(gettext(f"حساب {line['account_code']} غير موجود."))
                bl = BudgetLine(
                    tenant_id=budget.tenant_id,
                    budget_id=budget.id,
                    account_id=account.id,
                    budgeted_amount=Decimal(str(line["budgeted_amount"])),
                    notes=line.get("notes"),
                )
                db.session.add(bl)

        cls._recalculate_totals(budget)
        db.session.flush()
        return budget

    @classmethod
    def approve_budget(cls, budget, user):
        if budget.status != "draft":
            raise ValueError(gettext("فقط المسودات يمكن الموافقة عليها."))
        budget.status = "approved"
        budget.approved_by = user.id
        budget.approved_at = datetime.now(UTC)
        db.session.flush()
        return budget

    @classmethod
    def submit_budget(cls, budget):
        if budget.status != "draft":
            raise ValueError(gettext("فقط المسودات يمكن إرسالها."))
        budget.status = "active"
        db.session.flush()
        return budget

    @classmethod
    def activate_budget(cls, budget):
        if budget.status not in ("draft", "approved"):
            raise ValueError(gettext("لا يمكن تفعيل ميزانية في حالة غير مسودة أو معتمدة."))
        budget.status = "active"
        db.session.flush()
        return budget

    @classmethod
    def close_budget(cls, budget):
        budget.close()
        db.session.flush()
        return budget

    @classmethod
    def delete_budget(cls, budget):
        if budget.status not in ("draft",):
            raise ValueError(gettext("لا يمكن حذف ميزانية نشطة أو مغلقة."))
        BudgetLine.query.filter_by(budget_id=budget.id).delete()
        db.session.delete(budget)
        db.session.flush()

    @classmethod
    def list_budgets(cls, user, filters=None):
        tid = cls._tid(user)
        query = tenant_query(Budget).filter_by(tenant_id=tid)
        filters = filters or {}
        if filters.get("status"):
            query = query.filter_by(status=filters["status"])
        if filters.get("fiscal_year"):
            query = query.filter_by(fiscal_year=int(filters["fiscal_year"]))
        if filters.get("branch_id"):
            query = query.filter_by(branch_id=int(filters["branch_id"]))
        return query.order_by(Budget.fiscal_year.desc(), Budget.created_at.desc()).all()

    @classmethod
    def get_budget(cls, budget_id, user):
        tid = cls._tid(user)
        budget = Budget.query.filter_by(id=budget_id, tenant_id=tid).first()
        if not budget:
            raise ValueError(gettext("الميزانية غير موجودة."))
        return budget

    @classmethod
    def variance_report(cls, budget_id, user):
        budget = cls.get_budget(budget_id, user)
        budget.update_actuals()
        lines = []
        for line in budget.lines:
            account = line.account
            lines.append(
                {
                    "account_code": account.code if account else "",
                    "account_name": account.name if account else "",
                    "budgeted": float(line.budgeted_amount or 0),
                    "actual": float(line.actual_amount or 0),
                    "variance": float(line.variance or 0),
                    "variance_percentage": float(line.variance_percentage or 0),
                    "variance_status": line.variance_status,
                    "variance_status_ar": line.variance_status_ar,
                }
            )
        return {
            "budget": budget,
            "lines": lines,
            "total_budgeted": float(budget.total_budgeted or 0),
            "total_actual": float(budget.total_actual or 0),
            "total_variance": float(budget.total_variance or 0),
        }

    @classmethod
    def _recalculate_totals(cls, budget):
        total = Decimal("0")
        for line in budget.lines:
            total += line.budgeted_amount or Decimal("0")
        budget.total_budgeted = total
