from datetime import datetime, timezone
from extensions import db


class EmailList(db.Model):
    __tablename__ = "email_lists"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    subscribers = db.relationship("EmailSubscriber", back_populates="list", cascade="all, delete-orphan")
    campaigns = db.relationship("EmailCampaign", back_populates="list", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<EmailList {self.name}>"


class EmailSubscriber(db.Model):
    __tablename__ = "email_subscribers"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    list_id = db.Column(
        db.Integer,
        db.ForeignKey("email_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(200))
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(20), default="subscribed", index=True)
    unsubscribed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    list = db.relationship("EmailList", back_populates="subscribers", foreign_keys=[list_id])
    customer = db.relationship("Customer", foreign_keys=[customer_id])

    __table_args__ = (db.UniqueConstraint("list_id", "email", name="uq_email_subscriber"),)

    def __repr__(self):
        return f"<EmailSubscriber {self.email}>"


class EmailTemplate(db.Model):
    __tablename__ = "email_templates"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    from_email = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<EmailTemplate {self.name}>"


class EmailCampaign(db.Model):
    __tablename__ = "email_campaigns"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    list_id = db.Column(
        db.Integer,
        db.ForeignKey("email_lists.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("email_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    scheduled_date = db.Column(db.DateTime, nullable=True)
    sent_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="draft", index=True)
    sent_count = db.Column(db.Integer, default=0)
    open_count = db.Column(db.Integer, default=0)
    click_count = db.Column(db.Integer, default=0)
    bounce_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    list = db.relationship("EmailList", back_populates="campaigns", foreign_keys=[list_id])
    template = db.relationship("EmailTemplate", foreign_keys=[template_id])
    logs = db.relationship("CampaignLog", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<EmailCampaign {self.name}>"


class CampaignLog(db.Model):
    __tablename__ = "campaign_logs"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("email_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscriber_id = db.Column(
        db.Integer,
        db.ForeignKey("email_subscribers.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = db.Column(db.String(20), nullable=False, index=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    opened_at = db.Column(db.DateTime, nullable=True)
    clicked_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    campaign = db.relationship("EmailCampaign", back_populates="logs", foreign_keys=[campaign_id])
    subscriber = db.relationship("EmailSubscriber", foreign_keys=[subscriber_id])

    def __repr__(self):
        return f"<CampaignLog C{self.campaign_id} {self.status}>"
