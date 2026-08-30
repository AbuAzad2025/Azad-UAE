"""Receipt model - payment receipts for incoming/outgoing funds.

ARCHITECTURE NOTE: RECEIPT SOURCE IDENTITY PATTERN
================================================
Receipt uses a polymorphic source pattern (source_type + source_id) rather
than separate nullable FKs. This design was chosen to support multiple
source document types (sale, manual, refund, adjustment, etc.) without
adding a nullable FK column per source type.

Trade-offs vs. separate FK columns:
  PRO: Clean schema — only two columns for N source types.
  CON: No DB-level referential integrity on source_id.
  CON: Application must validate source_type/source_id consistency.

For new development, prefer separate nullable FK columns per source type
(e.g., sale_id, purchase_id, expense_id) with a UNIQUE CHECK constraint
ensuring exactly one is non-NULL. This provides both referential integrity
and explicit domain semantics.

Existing code pattern:
  source_type = "sale" → source_id = sale.id
  source_type = "manual" → source_id = None (no FK target)
  source_type = "refund" → source_id = sale.id

If adding new source types, update the VALID_SOURCE_TYPES set below.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import validates

from extensions import db
from utils.currency_utils import context_aware_default_currency
from utils.payment_utils import normalize_payment_method_code


class Receipt(db.Model):
    __tablename__ = "receipts"
    __table_args__ = (db.UniqueConstraint("tenant_id", "receipt_number", name="uq_receipts_tenant_receipt_number"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receipt_number = db.Column(db.String(50), nullable=False, index=True)

    # تصنيف مصدر السند
    # NOTE: see module docstring for the polymorphic source pattern trade-offs.
    # For referential integrity in new code, prefer separate nullable FK columns.
    VALID_SOURCE_TYPES = frozenset({"sale", "manual", "refund", "adjustment", "other"})
    source_type = db.Column(db.String(20), default="sale", index=True)  # sale, manual, refund, etc.
    source_id = db.Column(db.Integer, index=True)  # LEGACY polymorphic FK — retained for backward compat
    # Explicit FKs (F-01 remediation) — nullable, SET NULL on delete, with DB-level FK
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"), index=True, nullable=True)

    # اتجاه المدفوعات
    direction = db.Column(db.String(10), default="incoming", index=True)  # incoming, outgoing

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)

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

    # معلومات الشيك (قديمة - للتوافق)
    cheque_number = db.Column(db.String(50))
    cheque_date = db.Column(db.Date)
    bank_name = db.Column(db.String(100))

    # ربط مع نموذج الشيك (جديد - للمحاسبة الدقيقة)
    cheque_id = db.Column(db.Integer, db.ForeignKey("cheques.id", ondelete="RESTRICT"), index=True)

    # حالة السند - للشيكات فقط
    payment_confirmed = db.Column(db.Boolean, default=True, index=True)
    confirmation_date = db.Column(db.DateTime(timezone=True))
    rejection_reason = db.Column(db.String(500))
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), index=True)

    receipt_date = db.Column(
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

    customer = db.relationship("Customer", back_populates="receipts")
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    user = db.relationship("User", foreign_keys=[user_id])
    cheque = db.relationship("Cheque", backref="receipt_record", foreign_keys=[cheque_id])
    tenant = db.relationship("Tenant", backref="receipts", foreign_keys=[tenant_id])
    sale = db.relationship("Sale", foreign_keys=[sale_id])

    @validates("sale_id")
    def _validate_sale_id(self, key, value):
        """F-01: explicit FK must be consistent with polymorphic source fields.

        If sale_id is set, source_type must be sale-like and source_id (if set)
        must match sale_id. Allows gradual migration: legacy rows keep
        source_id only, new rows set both.
        """
        if value is not None:
            if self.source_type not in ("sale", "refund", "adjustment"):
                raise ValueError(
                    f"Receipt.sale_id requires source_type in sale/refund/adjustment, got {self.source_type}"
                )
            if self.source_id is not None and self.source_id != value:
                raise ValueError(f"Receipt.sale_id ({value}) must match source_id ({self.source_id}) when both are set")
        return value

    @validates("source_type")
    def _validate_source_type(self, key, value):
        if value not in self.VALID_SOURCE_TYPES:
            raise ValueError(f"Invalid source_type {value!r}, must be one of {sorted(self.VALID_SOURCE_TYPES)}")
        return value

    def __repr__(self):
        return f"<Receipt {self.receipt_number}>"

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

    def confirm_receipt(self):
        """تأكيد السند (بعد صرف الشيك)"""
        if not self.payment_confirmed:
            self.payment_confirmed = True
            self.confirmation_date = datetime.now(UTC)

    def reject_receipt(self, reason):
        """رفض السند (شيك مرتد) - يعكس التوزيع على فواتير البيع"""
        if self.payment_confirmed:
            self.payment_confirmed = False

        self.rejection_reason = reason

        # عكس الدفعات المرتبطة بالسند (التوزيع على فواتير البيع)
        from models import Payment

        link_conditions = [Payment.reference_number == self.receipt_number]
        if self.cheque_id:
            link_conditions.append(Payment.cheque_id == self.cheque_id)
        linked_payments_query = Payment.query.filter(
            db.or_(*link_conditions),
            Payment.payment_type == "sale_payment",
            Payment.payment_confirmed,
        )
        tenant_id = getattr(self, "tenant_id", None)
        if tenant_id is not None:
            linked_payments_query = linked_payments_query.filter(Payment.tenant_id == tenant_id)
        linked_payments = linked_payments_query.all()
        for pmt in linked_payments:
            pmt.payment_confirmed = False
            pmt.rejection_reason = reason
            if pmt.sale_id and pmt.sale:
                pmt.sale.recalculate_payment_status()

    @property
    def is_pending(self):
        """هل السند معلق (شيك لم يُصرف)"""
        return not self.payment_confirmed

    @property
    def status_ar(self):
        """حالة السند بالعربي"""
        if self.payment_confirmed:
            return "مؤكد"
        else:
            return "معلق" if not self.rejection_reason else "مرفوض"

    @property
    def source_type_ar(self):
        """نوع المصدر بالعربي"""
        source_types = {
            "sale": "مبيعات",
            "manual": "يدوي",
            "refund": "استرداد",
            "adjustment": "تسوية",
            "other": "أخرى",
        }
        return source_types.get(self.source_type, "غير محدد")

    @property
    def direction_ar(self):
        """اتجاه المدفوعة بالعربي"""
        directions = {"incoming": "وارد", "outgoing": "صادر"}
        return directions.get(self.direction, "غير محدد")

    def get_source_info(self):
        """معلومات المصدر"""
        if self.source_type == "sale" and self.source_id:
            from models import Sale

            sale = db.session.get(Sale, self.source_id)
            if sale:
                return {
                    "type": "فاتورة بيع",
                    "number": sale.sale_number,
                    "date": sale.sale_date.strftime("%Y-%m-%d"),
                    "amount": float(sale.total_amount),
                }
        return None

    def to_dict(self):
        return {
            "id": self.id,
            "receipt_number": self.receipt_number,
            "customer": self.customer.name if self.customer else None,
            "amount": float(self.amount),
            "currency": self.currency,
            "payment_method": self.payment_method,
            "receipt_date": self.receipt_date.isoformat(),
            "payment_confirmed": self.payment_confirmed,
            "status_ar": self.status_ar,
            "cheque_id": self.cheque_id,
        }
