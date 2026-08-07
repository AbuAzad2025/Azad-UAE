from datetime import UTC, datetime

from extensions import db


class Currency(db.Model):
    __tablename__ = "currencies"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(3), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    symbol = db.Column(db.String(10))

    is_base = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True, index=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    exchange_rates = db.relationship("ExchangeRate", back_populates="currency", lazy="dynamic")

    def __repr__(self):
        return f"<Currency {self.code}>"

    def get_display_name(self, lang="ar"):
        if lang == "ar" and self.name_ar:
            return self.name_ar
        return self.name

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "name_ar": self.name_ar,
            "symbol": self.symbol,
            "is_base": self.is_base,
        }


class ExchangeRate(db.Model):
    """LEGACY global exchange-rate table (NOT tenant-scoped).

    .. deprecated::
        The sole system-of-record for multi-tenant exchange rates is
        ``models.exchange_rate_record.ExchangeRateRecord`` (tenant-scoped,
        immutable, effective-dated, manual/api sourced). This legacy table is
        only referenced by initial seeding (``utils/system_init.py``) and must
        NOT be used for transaction or accounting logic — it has no
        ``tenant_id`` and therefore cannot isolate rates per tenant.
    """

    __tablename__ = "exchange_rates"

    id = db.Column(db.Integer, primary_key=True)

    from_currency = db.Column(db.String(3), nullable=False, index=True)
    to_currency = db.Column(db.String(3), nullable=False, index=True)

    currency_id = db.Column(db.Integer, db.ForeignKey("currencies.id", ondelete="RESTRICT"), index=True)

    rate = db.Column(db.Numeric(15, 6), nullable=False)

    source = db.Column(db.String(50))

    is_manual = db.Column(db.Boolean, default=False)

    valid_from = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    valid_until = db.Column(db.DateTime)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)

    currency = db.relationship("Currency", back_populates="exchange_rates")

    def __repr__(self):
        return f"<ExchangeRate {self.currency.code if self.currency else '?'} = {self.rate}>"

    def is_valid(self):
        now = datetime.now(UTC)
        if self.valid_until:
            return self.valid_from <= now <= self.valid_until
        return self.valid_from <= now

    def to_dict(self):
        return {
            "id": self.id,
            "currency_code": self.currency.code if self.currency else None,
            "rate": float(self.rate),
            "source": self.source,
            "is_manual": self.is_manual,
            "valid_from": self.valid_from.isoformat(),
            "is_valid": self.is_valid(),
        }
