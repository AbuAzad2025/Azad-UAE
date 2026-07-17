"""
نموذج مراكز التكلفة - Cost Centers Model
"""

from datetime import datetime, timezone
from extensions import db


class CostCenter(db.Model):
    """
    مراكز التكلفة - لتتبع الأرباح والمصاريف حسب الفرع/القسم/المشروع
    """

    __tablename__ = "cost_centers"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "code", name="uq_cost_centers_tenant_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code = db.Column(db.String(20), nullable=False, index=True)
    name_ar = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200))

    # التسلسل الهرمي
    parent_id = db.Column(db.Integer, db.ForeignKey("cost_centers.id"), index=True)
    level = db.Column(db.Integer, default=0)

    # النوع
    center_type = db.Column(
        db.String(30), default="department"
    )  # department, branch, project, product_line

    # المسؤول
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

    # الموازنة
    budget_amount = db.Column(db.Numeric(18, 3), default=0)

    # الحالة
    is_active = db.Column(db.Boolean, default=True, index=True)

    description = db.Column(db.Text)

    # Meta
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    parent = db.relationship("CostCenter", remote_side=[id], backref="children")
    manager = db.relationship("User", foreign_keys=[manager_id])
    tenant = db.relationship("Tenant", backref="cost_centers", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<CostCenter {self.code} - {self.name_ar}>"

    @property
    def full_name(self):
        """الاسم الكامل مع الكود"""
        return f"{self.code} - {self.name_ar or self.name_en}"

    @property
    def center_type_ar(self):
        """نوع المركز بالعربي"""
        types = {
            "department": "قسم",
            "branch": "فرع",
            "project": "مشروع",
            "product_line": "خط إنتاج",
        }
        return types.get(self.center_type, self.center_type)

    def get_performance(self, period_start=None, period_end=None):
        """
        حساب أداء مركز التكلفة
        """
        from sqlalchemy import func
        from models import GLJournalLine, GLJournalEntry

        # الإيرادات
        revenue_query = (
            db.session.query(func.sum(GLJournalLine.credit))
            .join(GLJournalEntry)
            .filter(
                GLJournalLine.cost_center_id == self.id,
                GLJournalLine.account.has(type="revenue"),
            )
        )

        if period_start and period_end:
            revenue_query = revenue_query.filter(
                func.date(GLJournalEntry.entry_date).between(period_start, period_end)
            )

        revenues = revenue_query.scalar() or 0

        # المصروفات
        expense_query = (
            db.session.query(func.sum(GLJournalLine.debit))
            .join(GLJournalEntry)
            .filter(
                GLJournalLine.cost_center_id == self.id,
                GLJournalLine.account.has(type="expense"),
            )
        )

        if period_start and period_end:
            expense_query = expense_query.filter(
                func.date(GLJournalEntry.entry_date).between(period_start, period_end)
            )

        expenses = expense_query.scalar() or 0

        profit = revenues - expenses
        margin = (profit / revenues * 100) if revenues > 0 else 0

        return {
            "revenues": float(revenues),
            "expenses": float(expenses),
            "profit": float(profit),
            "margin": float(margin),
        }
