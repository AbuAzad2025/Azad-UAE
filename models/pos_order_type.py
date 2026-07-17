from extensions import db


class PosOrderType(db.Model):
    """Configurable, industry-neutral POS order types (per tenant).

    Replaces the previously hard-coded restaurant-only set
    (dine_in / takeaway / delivery) so the POS can serve any business.
    """

    __tablename__ = "pos_order_types"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True
    )
    code = db.Column(db.String(40), nullable=False)
    name_ar = db.Column(db.String(120), nullable=False)
    name_en = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    kds_enabled = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "code", name="uq_pos_order_type_tenant_code"),
    )

    @property
    def display_name(self):
        return self.name_ar or self.name_en or self.code

    @classmethod
    def for_tenant(cls, tenant_id, active_only=True):
        q = cls.query.filter_by(tenant_id=tenant_id)
        if active_only:
            q = q.filter_by(is_active=True)
        return q.order_by(cls.sort_order, cls.id).all()

    @classmethod
    def get_by_code(cls, tenant_id, code, active_only=False):
        q = cls.query.filter_by(tenant_id=tenant_id, code=code)
        if active_only:
            q = q.filter_by(is_active=True)
        return q.first()

    @classmethod
    def default_for_tenant(cls, tenant_id):
        ot = cls.query.filter_by(
            tenant_id=tenant_id, is_default=True, is_active=True
        ).first()
        if not ot:
            ot = (
                cls.query.filter_by(tenant_id=tenant_id, is_active=True)
                .order_by(cls.sort_order, cls.id)
                .first()
            )
        return ot

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name_ar": self.name_ar,
            "name_en": self.name_en,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "is_default": self.is_default,
            "kds_enabled": self.kds_enabled,
        }


# Generic, industry-neutral defaults seeded for every new company.
DEFAULT_POS_ORDER_TYPES = [
    ("in_store", "في المتجر", "In-store", True, 10, False),
    ("pickup", "استلام من المتجر", "Pickup", False, 20, False),
    ("delivery", "توصيل", "Delivery", False, 30, False),
    ("online", "عبر الإنترنت", "Online", False, 40, False),
    ("phone", "طلب هاتفي", "Phone order", False, 50, False),
    ("walk_in", "عميل نقدي", "Walk-in", False, 60, False),
]


def ensure_default_pos_order_types(tenant_id):
    """Seed generic order types for a tenant if it has none configured yet."""
    existing = PosOrderType.query.filter_by(tenant_id=tenant_id).first()
    if existing:
        return
    for (
        code,
        name_ar,
        name_en,
        is_default,
        sort_order,
        kds_enabled,
    ) in DEFAULT_POS_ORDER_TYPES:
        db.session.add(
            PosOrderType(
                tenant_id=tenant_id,
                code=code,
                name_ar=name_ar,
                name_en=name_en,
                is_active=True,
                sort_order=sort_order,
                is_default=is_default,
                kds_enabled=kds_enabled,
            )
        )
    db.session.flush()
