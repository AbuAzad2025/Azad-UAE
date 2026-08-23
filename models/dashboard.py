from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import JSONB

from extensions import db


class DashboardWidget(db.Model):
    """
    Registry of available dashboard widgets
    """

    __tablename__ = "dashboard_widgets"

    id = db.Column(db.Integer, primary_key=True)
    widget_key = db.Column(db.String(50), unique=True, nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    required_permission = db.Column(db.String(50))
    data_source = db.Column(db.String(100))  # Service/method to call
    default_size = db.Column(db.String(20), default="medium")
    allowed_roles = db.Column(db.String(255))  # Comma-separated roles
    is_enabled = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<DashboardWidget {self.widget_key}>"


class UserDashboardLayout(db.Model):
    """
    Customizable layout storage per user
    """

    __tablename__ = "user_dashboard_layouts"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    layout_json = db.Column(JSONB, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (db.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user_layout"),)

    def __repr__(self):
        return f"<UserDashboardLayout user={self.user_id}>"
