from datetime import datetime, timezone
from extensions import db


class Campaign(db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    campaign_type = db.Column(db.String(30), nullable=False)
    discount_value = db.Column(db.Numeric(15, 3), nullable=False)
    max_discount_amount = db.Column(db.Numeric(15, 3))
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    min_order_amount = db.Column(db.Numeric(15, 3), default=0)
    min_quantity = db.Column(db.Numeric(15, 3), default=0)
    applicable_products = db.Column(db.JSON, default=list)
    applicable_categories = db.Column(db.JSON, default=list)
    is_active = db.Column(db.Boolean, default=True, index=True)
    usage_limit = db.Column(db.Integer)
    usage_count = db.Column(db.Integer, default=0)
    coupon_code = db.Column(db.String(50), index=True)

    # Phase 1 — POS promotion engine: campaigns with applies_to_pos=True are
    # evaluated automatically at the register (no coupon required).
    # campaign_type drives the rule kind: bundle / tiered / combo / bogo,
    # with legacy percentage / fixed treated as tiered-style cart rules.
    # rule_config carries the rule-type-specific knobs (see PromotionService).
    applies_to_pos = db.Column(db.Boolean, default=False, index=True)
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    rule_config = db.Column(db.JSON, default=dict)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])

    def __repr__(self):
        return f"<Campaign {self.name} ({self.campaign_type})>"


class SaleCampaign(db.Model):
    __tablename__ = "sale_campaigns"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    discount_amount = db.Column(db.Numeric(15, 3), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    campaign = db.relationship("Campaign", foreign_keys=[campaign_id])
    sale = db.relationship("Sale", foreign_keys=[sale_id])

    def __repr__(self):
        return f"<SaleCampaign S#{self.sale_id} C#{self.campaign_id} disc={self.discount_amount}>"
