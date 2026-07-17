from extensions import db
from datetime import datetime, timezone


class PayrollSettings(db.Model):
    __tablename__ = "payroll_settings"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    # Jurisdiction/Policy
    payroll_jurisdiction = db.Column(
        db.String(50), default="default"
    )  # Palestine, UAE, GCC, Custom
    country_code = db.Column(db.String(3), default="PS")  # PS, AE, etc.

    # Leave Policy Parameters
    annual_leave_days = db.Column(db.Integer, default=30)

    # End of Service/Gratuity Policy
    eos_calculation_method = db.Column(
        db.String(50), default="standard"
    )  # standard, custom

    rounding_policy = db.Column(db.String(20), default="round_half_up")

    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<PayrollSettings tenant={self.tenant_id}>"
