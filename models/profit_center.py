"""
نموذج مراكز الربح - Profit Centers Model
"""

from datetime import datetime, timezone
from extensions import db


class ProfitCenter(db.Model):
    """
    مراكز الربح - لتتبع الأرباح والأداء حسب وحدة الأعمال
    """

    __tablename__ = "profit_centers"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "code", name="uq_profit_centers_tenant_code"),
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
    parent_id = db.Column(db.Integer, db.ForeignKey("profit_centers.id"), index=True)
    level = db.Column(db.Integer, default=0)

    # المسؤول
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

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

    parent = db.relationship("ProfitCenter", remote_side=[id], backref="children")
    manager = db.relationship("User", foreign_keys=[manager_id])
    tenant = db.relationship(
        "Tenant", backref="profit_centers", foreign_keys=[tenant_id]
    )

    def __repr__(self):
        return f"<ProfitCenter {self.code} - {self.name_ar}>"

    @property
    def full_name(self):
        """الاسم الكامل مع الكود"""
        return f"{self.code} - {self.name_ar or self.name_en}"
