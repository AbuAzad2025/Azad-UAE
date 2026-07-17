from datetime import datetime, timezone
from extensions import db
from utils.currency_utils import context_aware_default_currency
from utils.constants import normalize_payment_method_code


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "payment_number", name="uq_payments_tenant_payment_number"
        ),
    )

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
    direction = db.Column(
        db.String(10), default="outgoing", index=True
    )  # incoming, outgoing

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True)

    # معلومات المورد (لسندات الصرف)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), index=True)
    supplier_name = db.Column(db.String(200))
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"), index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), index=True)

    amount = db.Column(db.Numeric(15, 3), nullable=False)
    currency = db.Column(
        db.String(3), default=context_aware_default_currency, nullable=False
    )  # TODO: use Config.DEFAULT_CURRENCY
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)

    # Alias for unified currency handling
    @property
    def base_amount(self):
        return self.amount_aed

    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value

    payment_method = db.Column(db.String(20), nullable=False)

    reference_number = db.Column(db.String(100))

    # معلومات الشيك (قديمة - للتوافق)
    cheque_number = db.Column(db.String(50))
    cheque_date = db.Column(db.Date)
    bank_name = db.Column(db.String(100))

    # ربط مع نموذج الشيك (جديد - للمحاسبة الدقيقة)
    cheque_id = db.Column(db.Integer, db.ForeignKey("cheques.id"), index=True)

    # حالة الدفعة - للشيكات فقط
    # confirmed: مؤكدة (الشيك صُرف)
    # pending: معلقة (الشيك لم يُصرف بعد)
    payment_confirmed = db.Column(
        db.Boolean, default=True, index=True
    )  # True للنقد/بطاقة، False للشيكات المعلقة
    confirmation_date = db.Column(db.DateTime)  # تاريخ التأكيد
    rejection_reason = db.Column(db.String(500))  # سبب الرفض

    payment_date = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    notes = db.Column(db.Text)

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    sale = db.relationship("Sale", back_populates="payments")
    purchase = db.relationship("Purchase", foreign_keys=[purchase_id])
    customer = db.relationship("Customer")
    supplier = db.relationship("Supplier", foreign_keys=[supplier_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    user = db.relationship("User", foreign_keys=[user_id])
    cheque = db.relationship(
        "Cheque", backref="payment_record", foreign_keys=[cheque_id]
    )
    tenant = db.relationship("Tenant", backref="payments", foreign_keys=[tenant_id])

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
            self.confirmation_date = datetime.now(timezone.utc)

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


class Receipt(db.Model):
    __tablename__ = "receipts"
    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "receipt_number", name="uq_receipts_tenant_receipt_number"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receipt_number = db.Column(db.String(50), nullable=False, index=True)

    # تصنيف مصدر السند
    source_type = db.Column(
        db.String(20), default="sale", index=True
    )  # sale, manual, refund, etc.
    source_id = db.Column(db.Integer, index=True)  # ID of the source (sale_id, etc.)

    # اتجاه المدفوعات
    direction = db.Column(
        db.String(10), default="incoming", index=True
    )  # incoming, outgoing

    customer_id = db.Column(
        db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True
    )

    amount = db.Column(db.Numeric(15, 3), nullable=False)
    currency = db.Column(
        db.String(3), default=context_aware_default_currency, nullable=False
    )  # TODO: use Config.DEFAULT_CURRENCY
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)

    # Alias for unified currency handling
    @property
    def base_amount(self):
        return self.amount_aed

    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value

    payment_method = db.Column(db.String(20), nullable=False)

    reference_number = db.Column(db.String(100))

    # معلومات الشيك (قديمة - للتوافق)
    cheque_number = db.Column(db.String(50))
    cheque_date = db.Column(db.Date)
    bank_name = db.Column(db.String(100))

    # ربط مع نموذج الشيك (جديد - للمحاسبة الدقيقة)
    cheque_id = db.Column(db.Integer, db.ForeignKey("cheques.id"), index=True)

    # حالة السند - للشيكات فقط
    payment_confirmed = db.Column(db.Boolean, default=True, index=True)
    confirmation_date = db.Column(db.DateTime)
    rejection_reason = db.Column(db.String(500))
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), index=True)

    receipt_date = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    notes = db.Column(db.Text)

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    customer = db.relationship("Customer", back_populates="receipts")
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    user = db.relationship("User", foreign_keys=[user_id])
    cheque = db.relationship(
        "Cheque", backref="receipt_record", foreign_keys=[cheque_id]
    )
    tenant = db.relationship("Tenant", backref="receipts", foreign_keys=[tenant_id])

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
            self.confirmation_date = datetime.now(timezone.utc)

    def reject_receipt(self, reason):
        """رفض السند (شيك مرتد) - يعكس التوزيع على فواتير البيع"""
        if self.payment_confirmed:
            self.payment_confirmed = False

        self.rejection_reason = reason

        # عكس الدفعات المرتبطة بالسند (التوزيع على فواتير البيع)
        linked_payments = Payment.query.filter(
            db.or_(
                Payment.cheque_id == self.cheque_id,
                Payment.reference_number == self.receipt_number,
            ),
            Payment.payment_type == "sale_payment",
            Payment.payment_confirmed,
        ).all()
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
