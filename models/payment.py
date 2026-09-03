"""Payment model - tracks outgoing/incoming payments."""

from datetime import UTC, datetime

from sqlalchemy.orm import validates

from extensions import db
from utils.currency_utils import context_aware_default_currency
from utils.payment_utils import normalize_payment_method_code


def payment_affects_balance(model):
    """Unified balance-impact condition for Payment/Receipt.

    A record affects balances when it is confirmed, or when it is a pending
    (non-rejected) cheque: issuing an outgoing cheque reduces AP immediately and
    receiving an incoming cheque reduces AR immediately (GL: Dr CUC / Cr AR),
    with the effect reversed only on bounce/cancellation (which sets a
    rejection_reason). Non-cheque unconfirmed records have no effect.
    """
    return db.or_(
        model.payment_confirmed,
        db.and_(model.payment_method == "cheque", model.rejection_reason.is_(None)),
    )


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (db.UniqueConstraint("tenant_id", "payment_number", name="uq_payments_tenant_payment_number"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_number = db.Column(db.String(50), nullable=False, index=True)

    payment_type = db.Column(db.String(20), nullable=False, index=True)

    # اتجاه المدفوعات
    direction = db.Column(db.String(10), default="outgoing", index=True)  # incoming, outgoing

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="RESTRICT"), index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), index=True)

    # معلومات المورد (لسندات الصرف)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    supplier_name = db.Column(db.String(200))
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id", ondelete="RESTRICT"), index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), index=True)

    amount = db.Column(db.Numeric(15, 3), nullable=False)
    currency = db.Column(
        db.String(3), default=context_aware_default_currency, nullable=False
    )  # TODO: use Config.DEFAULT_CURRENCY
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    base_currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)

    # Alias for unified currency handling
    @property
    def base_amount(self):
        return self.amount_aed

    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value

    @property
    def base_currency_display(self):
        """Alias for templates."""
        return self.base_currency

    payment_method = db.Column(db.String(20), nullable=False)

    reference_number = db.Column(db.String(100))

    # رقم الشيك (شخصي - بنكي/شخصي)
    cheque_number = db.Column(db.String(50))
    cheque_date = db.Column(db.Date)
    bank_name = db.Column(db.String(100))

    # ربط مع نموذج الشيك (جديد - للمحاسبة الدقيقة)
    cheque_id = db.Column(db.Integer, db.ForeignKey("cheques.id", ondelete="RESTRICT"), index=True)

    # حالة الدفعة - للشيكات فقط
    # confirmed: مؤكدة (الشيك صُرف)
    # pending: معلقة (الشيك لم يُصرف بعد)
    payment_confirmed = db.Column(db.Boolean, default=True, index=True)  # True للنقد/بطاقة، False للشيكات المعلقة
    confirmation_date = db.Column(db.DateTime(timezone=True))  # تاريخ التأكيد
    rejection_reason = db.Column(db.String(500))  # سبب الرفض

    payment_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    notes = db.Column(db.Text)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    sale = db.relationship("Sale", back_populates="payments")
    purchase = db.relationship("Purchase", foreign_keys=[purchase_id])
    customer = db.relationship("Customer")
    supplier = db.relationship("Supplier", foreign_keys=[supplier_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    user = db.relationship("User", foreign_keys=[user_id])
    cheque = db.relationship("Cheque", backref="payment_record", foreign_keys=[cheque_id])
    tenant = db.relationship("Tenant", backref="payments", foreign_keys=[tenant_id])

    _SOURCE_FIELDS = ("sale_id", "purchase_id")

    @validates("sale_id", "purchase_id")
    def _validate_payment_direction(self, key, value):
        """Invariant: Payment.direction must match the source-document type.

        - sale_id   → must be incoming (customer paying us for a sale)
        - purchase_id → must be outgoing (us paying supplier for a purchase)
        Also enforces at-most-one source FK.
        """
        if value is not None:
            others = [f for f in self._SOURCE_FIELDS if f != key and getattr(self, f, None) is not None]
            if others:
                raise ValueError(f"Payment can reference at most one source document, {key} vs {others}")
            direction = getattr(self, "direction", None)
            if key == "sale_id" and direction == "outgoing":
                raise ValueError(
                    f"Payment.sale_id cannot be set on an outgoing payment "
                    f"(direction='{direction}'). Use purchase_id for outgoing."
                )
            if key == "purchase_id" and direction == "incoming":
                raise ValueError(
                    f"Payment.purchase_id cannot be set on an incoming payment "
                    f"(direction='{direction}'). Use sale_id for incoming."
                )
        return value

    def __repr__(self):
        return f"<Payment {self.payment_number}>"

    def get_method_display(self, lang="ar"):
        methods = {
            "cash": {"ar": "نقدي", "en": "Cash"},
            "card": {"ar": "بطاقة", "en": "Card"},
            "bank_transfer": {"ar": "تحويل بنكي", "en": "Bank Transfer"},
            "cheque": {"ar": "شيك", "en": "Cheque"},
            "e_wallet": {"ar": "محفظة إلكترونية", "en": "E-Wallet"},
        }
        canonical = normalize_payment_method_code(self.payment_method)
        return methods.get(canonical, {}).get(lang, self.payment_method)

    def confirm_payment(self):
        """تأكيد الدفعة (بعد صرف الشيك)"""
        if not self.payment_confirmed:
            self.payment_confirmed = True
            self.confirmation_date = datetime.now(UTC)

            # تحديث حالة الفاتورة
            if self.sale:
                self.sale.recalculate_payment_status()

    def reject_payment(self, reason):
        """رفض الدفعة (شيك مرتد) - يعكس التوزيع على فاتورة البيع"""
        if self.payment_confirmed:
            self.payment_confirmed = False

        self.rejection_reason = reason

        # تحديث حالة الفاتورة (recalculate يستثني الدفعات غير المؤكدة)
        if self.sale:
            self.sale.recalculate_payment_status()

    @property
    def is_pending(self):
        """هل الدفعة معلقة (شيك لم يُصرف)"""
        return not self.payment_confirmed

    @property
    def status_ar(self):
        """حالة الدفعة بالعربي"""
        if self.payment_confirmed:
            return "مؤكدة"
        else:
            return "معلقة" if not self.rejection_reason else "مرفوضة"

    @property
    def direction_ar(self):
        """اتجاه المدفوعة بالعربي"""
        directions = {"incoming": "وارد", "outgoing": "صادر"}
        return directions.get(self.direction, "غير محدد")

    def to_dict(self):
        return {
            "id": self.id,
            "payment_number": self.payment_number,
            "payment_type": self.payment_type,
            "amount": float(self.amount),
            "currency": self.currency,
            "payment_method": self.payment_method,
            "payment_date": self.payment_date.isoformat(),
            "payment_confirmed": self.payment_confirmed,
            "status_ar": self.status_ar,
            "cheque_id": self.cheque_id,
        }
