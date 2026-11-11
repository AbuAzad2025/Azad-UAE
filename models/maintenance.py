"""نماذج وحدة الصيانة - Maintenance Models

وحدة الصيانة هي وحدة مالية مستقلة تماماً عن المبيعات:
- أمر الصيانة (Maintenance Order) هو المستند المحوري
- القطع تُستهلك من مستودع الصيانة عبر حركة مخزون (stock movement) من نوع maintenance
- الإيراد يُرحل إلى MAINTENANCE_REVENUE (حساب مستقل عن المبيعات)
- الذمم تُرسند إلى MAINTENANCE_AR (ذمم صيانة مدينة مستقلة)
- المدفوعات تُقبض عبر صندوق الاستقبال فقط
- الكفالات تُدار عبر تدقيق كامل لا يمكن حذفه
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from extensions import db

if TYPE_CHECKING:
    pass


class MaintenanceOrderStatus:
    """حالات أمر الصيانة - آلة الحالات"""

    RECEIVED = "received"  # استلام الجهاز
    DIAGNOSIS = "diagnosis"  # تشخيص
    WAITING_APPROVAL = "waiting_approval"  # انتظار موافقة العميل
    IN_PROGRESS = "in_progress"  # تنفيذ
    WAITING_PARTS = "waiting_parts"  # انتظار قطع
    READY = "ready"  # جاهز للتسليم
    CLOSED = "closed"  # مغلق ومقبوض
    CANCELLED = "cancelled"  # ملغي قبل البدء
    ON_HOLD = "on_hold"  # معلق


class MaintenanceOrderWarrantyStatus:
    """حالة الكفالة للأمر"""

    UNDER_WARRANTY = "under_warranty"  # تحت الكفالة
    EXPIRED = "expired"  # منتهية
    VOID = "void"  # ملغاة
    UNKNOWN = "unknown"  # غير محدد


class MaintenanceDiscountMode:
    """أنواع الخصم"""

    PERCENT = "percent"
    VALUE = "value"


class MaintenancePaymentMode:
    """طرق الدفع"""

    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    E_WALLET = "e_wallet"
    ACCOUNT = "account"  # آجل على حساب العميل/المورد


class MaintenanceOrder(db.Model):
    """أمر الصيانة - المستند المحوري للوحدة"""

    __tablename__ = "maintenance_orders"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "order_number", name="uq_maintenance_orders_tenant_number"),
        db.Index("idx_maintenance_orders_tenant_status", "tenant_id", "status"),
        db.Index("idx_maintenance_orders_tenant_date", "tenant_id", "created_at"),
        db.Index("idx_maintenance_orders_customer", "tenant_id", "customer_id"),
        db.Index("idx_maintenance_orders_engineer", "tenant_id", "engineer_id"),
        db.Index("idx_maintenance_orders_warranty", "tenant_id", "warranty_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    warehouse_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    order_number = db.Column(db.String(50), nullable=False, index=True)
    order_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    # العميل (يمكن أن يكون عميل خارجي، مؤسسة داخلية، أو مجهول للاستهلاك الداخلي)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = db.Column(db.String(200))  # للعميل غير المسجل في قاعدة العملاء
    customer_phone = db.Column(db.String(50))

    # معلومات الجهاز
    device_brand = db.Column(db.String(100))
    device_model = db.Column(db.String(100))
    device_serial_number = db.Column(db.String(100))
    device_imei = db.Column(db.String(100))
    device_plate = db.Column(db.String(50))  # لوحة المركبة
    device_km = db.Column(db.Integer)  # عدد الكيلومترات
    device_fault_description = db.Column(db.Text)  # eschوى العطل

    # بيانات مالية - أسعار البيع (ليست تكلفة)
    subtotal = db.Column(db.Numeric(15, 3), default=0)
    discount_line_total = db.Column(db.Numeric(15, 3), default=0)  # مجموع خصومات السطور
    discount_total_percent = db.Column(db.Numeric(5, 2), default=0)  # خصم إجمالي نسبة مئوية
    discount_total_value = db.Column(db.Numeric(15, 3), default=0)  # خصم إجمالي قيمة صحيحة
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    taxable_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    amount = db.Column(db.Numeric(15, 3), nullable=False, default=0)  # الإجمالي النهائي
    paid_amount = db.Column(db.Numeric(15, 3), default=0)
    balance_due = db.Column(db.Numeric(15, 3), default=0)
    deposit_amount = db.Column(db.Numeric(15, 3), default=0)  # دفعة مقدمة عند الاستلام
    # The amount refunded to the customer after a return left a credit
    # balance. A return credits the maintenance receivable; the refund
    # pays it back out of the maintenance drawer, so the two together
    # settle the credit.
    refunded_amount = db.Column(db.Numeric(15, 3), default=0)  # مبلغ مسترد للعميل

    currency = db.Column(db.String(3), default="AED", nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    base_currency = db.Column(db.String(3), default="AED", nullable=False)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    paid_amount_aed = db.Column(db.Numeric(15, 3), default=0)
    balance_due_aed = db.Column(db.Numeric(15, 3), default=0)

    prices_include_vat = db.Column(db.Boolean, default=False, nullable=False)

    # حالة الأمر
    status = db.Column(db.String(20), default=MaintenanceOrderStatus.RECEIVED, nullable=False, index=True)
    priority = db.Column(db.String(20), default="normal")  # low, normal, high, urgent

    # الكفالة
    warranty_status = db.Column(
        db.String(20),
        default=MaintenanceOrderWarrantyStatus.UNKNOWN,
        nullable=False,
        index=True,
    )
    warranty_checked = db.Column(db.Boolean, default=False, nullable=False)
    warranty_checked_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    warranty_checked_at = db.Column(db.DateTime(timezone=True))
    warranty_notes = db.Column(db.Text)
    warranty_sale_id = db.Column(
        db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"), nullable=True, index=True
    )  # مرتبط بعملية بيع إذا كانت بضمان منتج مباع
    color_tag = db.Column(db.String(7), default="#10b981")  # لون التمييز في الواجهة

    # المستخدمون
    received_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )  # من استلم الجهاز
    engineer_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )  # المهندس المنفذ
    service_advisor_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )  # مستشار الخدمة (اختياري)
    closed_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )  # من أنهى الأمر وقبض المبلغ
    closed_at = db.Column(db.DateTime(timezone=True))

    # ملاحظات وشروط
    notes = db.Column(db.Text)
    terms_and_conditions = db.Column(db.Text)
    customer_signature = db.Column(db.Boolean, default=False)  # قبول العميل خطّياً/شفوياً

    # أرشفة بدلاً من الحذف
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    archived_at = db.Column(db.DateTime(timezone=True))
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Meta
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # العلاقات
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    warehouse = db.relationship("Warehouse", foreign_keys=[warehouse_id])
    customer = db.relationship("Customer", foreign_keys=[customer_id])
    warranty_sale = db.relationship("Sale", foreign_keys=[warranty_sale_id])
    received_by_user = db.relationship("User", foreign_keys=[received_by])
    engineer = db.relationship("User", foreign_keys=[engineer_id])
    service_advisor = db.relationship("User", foreign_keys=[service_advisor_id])
    closed_by_user = db.relationship("User", foreign_keys=[closed_by])
    archived_by_user = db.relationship("User", foreign_keys=[archived_by])

    lines = db.relationship(
        "MaintenanceOrderLine", back_populates="order", cascade="all, delete-orphan", lazy="dynamic"
    )
    services_lines = db.relationship(
        "MaintenanceOrderService", back_populates="order", cascade="all, delete-orphan", lazy="dynamic"
    )
    status_logs = db.relationship(
        "MaintenanceOrderStatusLog",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="MaintenanceOrderStatusLog.created_at.asc()",
    )
    receipts = db.relationship("MaintenanceReceipt", back_populates="order", cascade="all, delete-orphan")
    invoice = db.relationship("MaintenanceInvoice", back_populates="order", uselist=False, cascade="all, delete-orphan")
    returns = db.relationship("MaintenanceReturn", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MaintenanceOrder {self.order_number} {self.status}>"

    @property
    def can_be_converted_to_closed(self):
        return self.status in (MaintenanceOrderStatus.READY,)

    @property
    def net_profit_estimate(self):
        """الربح التقديري = الإجمالي - تكلفة القطع المستهلكة"""
        if not self.invoice or not self.invoice.posted:
            return None
        from utils.currency_utils import convert_and_quantize_aed

        revenue = Decimal(str(self.total_amount or 0)) - Decimal(str(self.tax_amount or 0))
        revenue_base = convert_and_quantize_aed(
            revenue, self.currency, self.exchange_rate, base_currency=self.base_currency
        )
        return revenue_base - self.total_cost_aed

    @property
    def total_cost_aed(self):
        """إجمالي تكلفة القطع المستهلكة (بعملة الأساس)"""
        total = Decimal("0")
        for line in self.lines:
            if line.movement and not line.is_archived:
                total += Decimal(str(line.cost_aed or 0))
        return total

    def to_dict(self):
        return {
            "id": self.id,
            "order_number": self.order_number,
            "status": self.status,
            "priority": self.priority,
            "customer_name": self.customer_name,
            "device_brand": self.device_brand,
            "device_model": self.device_model,
            "device_serial_number": self.device_serial_number,
            "device_imei": self.device_imei,
            "device_plate": self.device_plate,
            "warranty_status": self.warranty_status,
            "warranty_checked": self.warranty_checked,
            "subtotal": float(self.subtotal or 0),
            "discount_total_percent": float(self.discount_total_percent or 0),
            "discount_total_value": float(self.discount_total_value or 0),
            "tax_amount": float(self.tax_amount or 0),
            "total_amount": float(self.total_amount or 0),
            "paid_amount": float(self.paid_amount or 0),
            "balance_due": float(self.balance_due or 0),
            "currency": self.currency,
            "amount_aed": float(self.amount_aed or 0),
            "paid_amount_aed": float(self.paid_amount_aed or 0),
            "balance_due_aed": float(self.balance_due_aed or 0),
            "received_by": self.received_by,
            "engineer_id": self.engineer_id,
            "closed_by": self.closed_by,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MaintenanceOrderLine(db.Model):
    """سطر قطعة غيار في أمر الصيانة"""

    __tablename__ = "maintenance_order_lines"
    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "order_id", "product_id", name="uq_maintenance_order_lines_tenant_order_product"
        ),
        db.Index("idx_maintenance_order_lines_order", "tenant_id", "order_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(15, 3), nullable=False, default=1)
    quantity_returned = db.Column(db.Numeric(15, 3), default=0)  # الكمية المرتجعة من هذه السطر

    unit_price = db.Column(db.Numeric(15, 3), nullable=False, default=0)  # سعر البيع للقطعة
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    discount_value = db.Column(db.Numeric(15, 3), default=0)
    discount_mode = db.Column(db.String(20), default=MaintenanceDiscountMode.PERCENT)  # percent / value
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    line_total = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    warehouse_id = db.Column(
        db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True, index=True
    )  # مستودع الصيانة الذي أُخذت منه القطعة

    # The serial numbers of the individual units consumed, when the product
    # is serial-tracked. Optional: a non-serial product (or a product with
    # no serials registered) leaves an empty list, and the quantity alone
    # describes what was consumed. The list is what lets the workshop trace
    # which physical unit went into which job.
    serial_numbers = db.Column(db.JSON, nullable=True)  # list[str] of consumed serial numbers

    movement_id = db.Column(
        db.Integer, db.ForeignKey("stock_movements.id", ondelete="SET NULL"), nullable=True, index=True
    )  # حركة المخزون المرتبطة

    cost_price = db.Column(db.Numeric(15, 3), default=0)  # تكلفة القطعة وقت الصرف (MWAC)
    cost_aed = db.Column(db.Numeric(15, 3), default=0)  # التكلفة بعملة الأساس

    # The share of the ORDER-level discount that was allocated to this line.
    # The order discount is spread over the lines by the largest-remainder
    # method, so the share is not derivable from the line alone: a return
    # has to reverse exactly what was discounted, and reversing the line
    # total without this share would credit the receivable more than the
    # order ever gave up.
    aggregate_discount = db.Column(db.Numeric(15, 3), default=0)
    # The line's taxable amount after both the line discount and its share
    # of the order discount - the revenue this line actually carried.
    taxable_amount = db.Column(db.Numeric(15, 3), default=0)

    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # العلاقات
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    order = db.relationship("MaintenanceOrder", back_populates="lines", foreign_keys=[order_id])
    product = db.relationship("Product", foreign_keys=[product_id])
    warehouse = db.relationship("Warehouse", foreign_keys=[warehouse_id])
    movement = db.relationship("StockMovement", foreign_keys=[movement_id])

    def __repr__(self):
        return f"<MaintenanceOrderLine {self.product_id} x{self.quantity}>"

    @property
    def net_quantity(self):
        return Decimal(str(self.quantity or 0)) - Decimal(str(self.quantity_returned or 0))

    @property
    def net_line_total(self):
        qty = self.net_quantity
        price = Decimal(str(self.unit_price or 0))
        disc_pct = Decimal(str(self.discount_percent or 0))
        disc_val = Decimal(str(self.discount_value or 0))
        if self.discount_mode == MaintenanceDiscountMode.PERCENT:
            discounted = price * (Decimal("1") - disc_pct / Decimal("100"))
        else:
            discounted = price - disc_val
        return qty * discounted


class MaintenanceOrderService(db.Model):
    """سطر خدمة ثابتة (ميكانيكية/كهربائية/جهد/أخرى) في أمر الصيانة"""

    __tablename__ = "maintenance_order_services"
    __table_args__ = (db.Index("idx_maintenance_order_services_order", "tenant_id", "order_id"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_code = db.Column(db.String(50), nullable=False, index=True)  # رمز الخدمة من maintenance_services
    service_name = db.Column(db.String(200), nullable=False)
    service_name_ar = db.Column(db.String(200))
    service_category = db.Column(db.String(50))  # mechanical, electrical, labor, diagnostic, other
    duration_minutes = db.Column(db.Integer, default=0)

    unit_price = db.Column(db.Numeric(15, 3), nullable=False, default=0)  # سعر ثابت من لوحة المشرف
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    discount_value = db.Column(db.Numeric(15, 3), default=0)
    discount_mode = db.Column(db.String(20), default=MaintenanceDiscountMode.PERCENT)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    line_total = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    engineer_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )  # من نفذ الخدمة

    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    order = db.relationship("MaintenanceOrder", back_populates="services_lines", foreign_keys=[order_id])
    engineer = db.relationship("User", foreign_keys=[engineer_id])

    def __repr__(self):
        return f"<MaintenanceOrderService {self.service_code} x1>"


class MaintenanceOrderStatusLog(db.Model):
    """سجل انتقال الحالات - للتدقيق الكامل"""

    __tablename__ = "maintenance_order_status_logs"
    __table_args__ = (
        db.Index("idx_maintenance_order_status_logs_order", "tenant_id", "order_id"),
        db.Index("idx_maintenance_order_status_logs_created", "tenant_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status = db.Column(db.String(20), nullable=True)
    to_status = db.Column(db.String(20), nullable=False, index=True)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    note = db.Column(db.Text)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    order = db.relationship("MaintenanceOrder", back_populates="status_logs", foreign_keys=[order_id])
    user = db.relationship("User", foreign_keys=[changed_by])

    def __repr__(self):
        return f"<MaintenanceOrderStatusLog {self.order_id} {self.from_status}->{self.to_status}>"


class MaintenanceReceipt(db.Model):
    """سند قبض الصيانة - يصدر من الاستقبال فقط"""

    __tablename__ = "maintenance_receipts"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "receipt_number", name="uq_maintenance_receipts_tenant_number"),
        db.Index("idx_maintenance_receipts_tenant_order", "tenant_id", "order_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receipt_number = db.Column(db.String(50), nullable=False, index=True)
    receipt_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    amount = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    payment_mode = db.Column(db.String(20), nullable=False)  # cash, card, bank_transfer, cheque, e_wallet, account
    reference_number = db.Column(db.String(100))  # رقم الشيك أو رقم التحويل
    cashier_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )  # من استلم المبلغ
    # A deposit is a liability, not a payment against the invoice: it is
    # credited to the maintenance deposit account and applied later.
    is_deposit = db.Column(db.Boolean, default=False, nullable=False, index=True)
    # A refund is a payment the workshop makes to the customer, because a
    # returned part left a credit balance. It is posted in the opposite
    # direction of a receipt: Dr receivable, Cr cash.
    is_refund = db.Column(db.Boolean, default=False, nullable=False, index=True)

    gl_posted = db.Column(db.Boolean, default=False, nullable=False)
    gl_posted_at = db.Column(db.DateTime(timezone=True))
    gl_entry_id = db.Column(
        db.Integer, db.ForeignKey("gl_journal_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )

    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    order = db.relationship("MaintenanceOrder", back_populates="receipts", foreign_keys=[order_id])
    cashier = db.relationship("User", foreign_keys=[cashier_id])
    gl_entry = db.relationship("GLJournalEntry", foreign_keys=[gl_entry_id])

    def __repr__(self):
        return f"<MaintenanceReceipt {self.receipt_number} {self.amount}>"


class MaintenanceInvoice(db.Model):
    """فاتورة الصيانة - منفصلة عن فواتير المبيعات العادية"""

    __tablename__ = "maintenance_invoices"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "invoice_number", name="uq_maintenance_invoices_tenant_number"),
        db.UniqueConstraint("tenant_id", "order_id", name="uq_maintenance_invoices_tenant_order"),
        db.Index("idx_maintenance_invoices_tenant_order", "tenant_id", "order_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_number = db.Column(db.String(50), nullable=False, index=True)
    invoice_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    subtotal = db.Column(db.Numeric(15, 3), default=0)
    discount_total_percent = db.Column(db.Numeric(5, 2), default=0)
    discount_total_value = db.Column(db.Numeric(15, 3), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    taxable_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    amount = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    paid_amount = db.Column(db.Numeric(15, 3), default=0)
    balance_due = db.Column(db.Numeric(15, 3), default=0)

    currency = db.Column(db.String(3), default="AED", nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    base_currency = db.Column(db.String(3), default="AED", nullable=False)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    paid_amount_aed = db.Column(db.Numeric(15, 3), default=0)
    balance_due_aed = db.Column(db.Numeric(15, 3), default=0)

    prices_include_vat = db.Column(db.Boolean, default=False, nullable=False)

    posted = db.Column(db.Boolean, default=False, nullable=False)
    posted_at = db.Column(db.DateTime(timezone=True))
    gl_posted = db.Column(db.Boolean, default=False, nullable=False)
    gl_posted_at = db.Column(db.DateTime(timezone=True))
    gl_entry_id = db.Column(
        db.Integer, db.ForeignKey("gl_journal_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )

    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    order = db.relationship("MaintenanceOrder", back_populates="invoice", foreign_keys=[order_id])
    gl_entry = db.relationship("GLJournalEntry", foreign_keys=[gl_entry_id])

    def __repr__(self):
        return f"<MaintenanceInvoice {self.invoice_number} {self.total_amount}>"


class MaintenanceReturn(db.Model):
    """مرتجع صيانة - إرجاع قطع أو خدمات"""

    __tablename__ = "maintenance_returns"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "return_number", name="uq_maintenance_returns_tenant_number"),
        db.Index("idx_maintenance_returns_tenant_order", "tenant_id", "order_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    return_number = db.Column(db.String(50), nullable=False, index=True)
    return_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    returned_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    reason = db.Column(db.Text)

    total_value = db.Column(db.Numeric(15, 3), default=0)
    total_value_aed = db.Column(db.Numeric(15, 3), default=0)
    # The tax carried by the returned lines and the cost of the parts that
    # went back on the shelf. Both are needed to reverse the invoice leg and
    # the parts-cost leg exactly: reversing the gross alone would leave the
    # tax and the cost of goods sold posted.
    total_value_tax = db.Column(db.Numeric(15, 3), default=0)
    total_value_cost = db.Column(db.Numeric(15, 3), default=0)

    posted = db.Column(db.Boolean, default=False, nullable=False)
    posted_at = db.Column(db.DateTime(timezone=True))
    gl_posted = db.Column(db.Boolean, default=False, nullable=False)

    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    order = db.relationship("MaintenanceOrder", back_populates="returns", foreign_keys=[order_id])
    user = db.relationship("User", foreign_keys=[returned_by])
    lines = db.relationship("MaintenanceReturnLine", back_populates="return_ref")

    def __repr__(self):
        return f"<MaintenanceReturn {self.return_number} {self.total_value}>"


class MaintenanceReturnLine(db.Model):
    """سطر مرتجع الصيانة"""

    __tablename__ = "maintenance_return_lines"
    __table_args__ = (db.Index("idx_maintenance_return_lines_return", "tenant_id", "return_id"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    return_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_returns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_line_id = db.Column(
        db.Integer, db.ForeignKey("maintenance_order_lines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_service_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_order_services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity = db.Column(db.Numeric(15, 3), nullable=False, default=1)
    unit_price = db.Column(db.Numeric(15, 3), default=0)
    line_total = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    line_total_aed = db.Column(db.Numeric(15, 3), default=0)
    # The tax carried by this line and the cost of the parts it returns to the
    # shelf. Both are needed to reverse the invoice leg and the parts-cost leg
    # exactly, not approximately.
    line_total_tax = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    line_total_cost = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    return_ref = db.relationship("MaintenanceReturn", back_populates="lines", foreign_keys=[return_id])
    order_line = db.relationship("MaintenanceOrderLine", foreign_keys=[order_line_id])
    order_service = db.relationship("MaintenanceOrderService", foreign_keys=[order_service_id])

    def __repr__(self):
        return f"<MaintenanceReturnLine qty={self.quantity}>"


class MaintenanceSetting(db.Model):
    """إعدادات وحدة الصيانة لكل تينانت"""

    __tablename__ = "maintenance_settings"
    __table_args__ = (db.UniqueConstraint("tenant_id", name="uq_maintenance_settings_tenant"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    default_warehouse_id = db.Column(
        db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )  # مستودع الصيانة الافتراضي

    # حسابات GL للصيانة
    maintenance_ar_account_id = db.Column(
        db.Integer, db.ForeignKey("gl_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )  # حساب ذمم صيانة مدينة
    maintenance_revenue_account_id = db.Column(
        db.Integer, db.ForeignKey("gl_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )  # حساب إيراد الصيانة
    maintenance_cogs_account_id = db.Column(
        db.Integer, db.ForeignKey("gl_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )  # حساب تكلفة الصيانة

    # حدود الخصم
    max_discount_percent = db.Column(db.Numeric(5, 2), default=15)  # سقف الخصم بنسبة مئوية
    max_discount_value = db.Column(db.Numeric(15, 3), default=0)  # سقف الخصم بقيمة صحيحة
    allow_engineer_discount = db.Column(db.Boolean, default=True, nullable=False)  # هل يمكن للمهندس خصم؟
    require_manager_approval_above_discount = db.Column(db.Boolean, default=True, nullable=False)

    # إعدادات الكفالة
    require_warranty_check = db.Column(db.Boolean, default=True, nullable=False)  # هل يتم فحص الكفالة عند الاستلام؟
    color_warranty = db.Column(db.String(7), default="#10b981")  # لون تحت الكفالة
    color_non_warranty = db.Column(db.String(7), default="#ef4444")  # لون خارج الكفالة
    color_unknown_warranty = db.Column(db.String(7), default="#f59e0b")  # لون غير محدد

    # The rate used to cost the time an engineer spends on a job. The
    # module has no wage table of its own and the HR module has no
    # hourly rate, so the workshop sets one rate for the tenant and the
    # margin report charges every service line's duration against it.
    # A job's true margin is the revenue less the parts cost less the
    # labour cost; without this the report would overstate the margin.
    engineer_hourly_rate = db.Column(db.Numeric(15, 3), default=0)  # سعر ساعة العمل
    allow_engineer_cancel_warranty = db.Column(
        db.Boolean, default=False, nullable=False
    )  # هل يمكن للمهندس إلغاء كفالة؟
    allow_engineer_restore_warranty = db.Column(
        db.Boolean, default=False, nullable=False
    )  # هل يمكن للمهندس إعادة كفالة؟

    # إعدادات الفاتورة
    invoice_prefix = db.Column(db.String(20), default="MINV")  # بادئة فاتورة الصيانة
    receipt_prefix = db.Column(db.String(20), default="PT")  # بادئة سند القبض
    order_prefix = db.Column(db.String(20), default="MN")  # بادئة أمر الصيانة

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    maintenance_ar_account = db.relationship("GLAccount", foreign_keys=[maintenance_ar_account_id])
    maintenance_revenue_account = db.relationship("GLAccount", foreign_keys=[maintenance_revenue_account_id])
    maintenance_cogs_account = db.relationship("GLAccount", foreign_keys=[maintenance_cogs_account_id])
    default_warehouse = db.relationship("Warehouse", foreign_keys=[default_warehouse_id])

    def __repr__(self):
        return f"<MaintenanceSetting tenant_id={self.tenant_id}>"


class MaintenanceServiceTemplate(db.Model):
    """قوالب الخدمات الثابتة السعر - تُضاف من لوحة المشرف"""

    __tablename__ = "maintenance_services"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "service_code", name="uq_maintenance_services_tenant_code"),
        db.Index("idx_maintenance_services_tenant_category", "tenant_id", "service_category"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_code = db.Column(db.String(50), nullable=False, index=True)  # MECH-001, ELEC-001, LABOR-001
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    service_category = db.Column(
        db.String(50), nullable=False, index=True
    )  # mechanical, electrical, labor, diagnostic, other
    fixed_price = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    duration_minutes = db.Column(db.Integer, default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    requires_parts = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=0)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<MaintenanceServiceTemplate {self.service_code} {self.name}>"


class MaintenanceDeviceRegistry(db.Model):
    """سجل الأجهزة - تتبع أجهزة العملاء عبر الصيانات المتكررة"""

    __tablename__ = "maintenance_device_registry"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "serial_number", name="uq_maintenance_device_registry_tenant_serial"),
        db.Index("idx_maintenance_device_registry_tenant_customer", "tenant_id", "customer_id"),
        db.Index("idx_maintenance_device_registry_imei", "tenant_id", "imei"),
        db.Index("idx_maintenance_device_registry_plate", "tenant_id", "plate"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)

    brand = db.Column(db.String(100))
    model = db.Column(db.String(100))
    serial_number = db.Column(db.String(100), index=True)
    imei = db.Column(db.String(100), index=True)
    plate = db.Column(db.String(50), index=True)  # لوحة المركبة

    purchase_date = db.Column(db.DateTime(timezone=True))
    warranty_start_date = db.Column(db.DateTime(timezone=True))
    warranty_end_date = db.Column(db.DateTime(timezone=True))
    warranty_type = db.Column(db.String(50))  # manufacturer, extended, dealer, insurance
    is_under_warranty = db.Column(db.Boolean, default=False, nullable=False, index=True)
    warranty_notes = db.Column(db.Text)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    customer = db.relationship("Customer", foreign_keys=[customer_id])
    product = db.relationship("Product", foreign_keys=[product_id])

    def __repr__(self):
        return f"<MaintenanceDeviceRegistry {self.serial_number or self.imei or self.plate}>"

    @property
    def warranty_status(self):
        if not self.is_active:
            return MaintenanceOrderWarrantyStatus.UNKNOWN
        if not self.is_under_warranty:
            return MaintenanceOrderWarrantyStatus.VOID
        if not self.warranty_end_date:
            return MaintenanceOrderWarrantyStatus.UNKNOWN
        end = self.warranty_end_date
        start = self.warranty_start_date
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        if start and start > now:
            return MaintenanceOrderWarrantyStatus.UNKNOWN
        if now > end:
            return MaintenanceOrderWarrantyStatus.EXPIRED
        return MaintenanceOrderWarrantyStatus.UNDER_WARRANTY


class MaintenanceWarrantyAudit(db.Model):
    """تدقيق الكفالات - كل تغيير على حالة الكفالة يُسجل ولا يُحذف"""

    __tablename__ = "maintenance_warranty_audit"
    __table_args__ = (
        db.Index("idx_maintenance_warranty_audit_tenant_order", "tenant_id", "maintenance_order_id"),
        db.Index("idx_maintenance_warranty_audit_created", "tenant_id", "performed_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    maintenance_order_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_orders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    serial_number = db.Column(db.String(100), index=True)
    imei = db.Column(db.String(100), index=True)

    action = db.Column(db.String(50), nullable=False, index=True)  # checked, cancelled, restored, added
    from_status = db.Column(db.String(50), nullable=True)
    to_status = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text)

    performed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    performed_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    order = db.relationship("MaintenanceOrder", foreign_keys=[maintenance_order_id])
    product = db.relationship("Product", foreign_keys=[product_id])
    user = db.relationship("User", foreign_keys=[performed_by])

    def __repr__(self):
        return f"<MaintenanceWarrantyAudit {self.action} {self.serial_number or self.imei}>"


class MaintenancePurchaseOrderStatus:
    """حالات أمر شراء قطع الصيانة."""

    DRAFT = "draft"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class MaintenancePurchaseOrder(db.Model):
    """أمر شراء قطع الصيانة - مستند توريد قطع إلى مستودع الصيانة.

    The workshop buys its spare parts from suppliers. The document that
    carries that in is this one: it names the supplier and the warehouse,
    and when it is received the stock arrives at the cost the supplier
    charged - which is what the warehouse's moving average is built from
    afterwards.

    The payable is the tenant's own supplier payable (the module's
    ``MAINTENANCE_AP`` concept resolves to it): the counterparty is a
    supplier either way, and a second payable ledger would have to be
    reconciled too.
    """

    __tablename__ = "maintenance_purchase_orders"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "po_number", name="uq_maintenance_purchase_orders_tenant_number"),
        db.Index("idx_maintenance_purchase_orders_tenant_status", "tenant_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)
    warehouse_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_name = db.Column(db.String(200))
    po_number = db.Column(db.String(50), nullable=False, index=True)
    order_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    status = db.Column(
        db.String(20),
        default=MaintenancePurchaseOrderStatus.DRAFT,
        nullable=False,
        index=True,
    )

    subtotal = db.Column(db.Numeric(15, 3), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), default=0)
    # The net amount that goes into the inventory account: the tax is
    # recoverable, so it is posted to the input-tax account and never
    # capitalised into the stock.
    taxable_amount = db.Column(db.Numeric(15, 3), default=0)
    currency = db.Column(db.String(3), default="AED")
    exchange_rate = db.Column(db.Numeric(18, 6), default=1)

    received_at = db.Column(db.DateTime(timezone=True))
    received_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    notes = db.Column(db.Text)

    posted = db.Column(db.Boolean, default=False, nullable=False)
    posted_at = db.Column(db.DateTime(timezone=True))
    gl_posted = db.Column(db.Boolean, default=False, nullable=False)

    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    warehouse = db.relationship("Warehouse", foreign_keys=[warehouse_id])
    supplier = db.relationship("Supplier", foreign_keys=[supplier_id])
    receiver = db.relationship("User", foreign_keys=[received_by])
    lines = db.relationship(
        "MaintenancePurchaseOrderLine",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<MaintenancePurchaseOrder {self.po_number} {self.status} {self.total_amount}>"


class MaintenancePurchaseOrderLine(db.Model):
    """سطر أمر شراء قطع الصيانة"""

    __tablename__ = "maintenance_purchase_order_lines"
    __table_args__ = (db.Index("idx_maintenance_purchase_order_lines_order", "tenant_id", "purchase_order_id"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = db.Column(db.Numeric(15, 3), nullable=False, default=1)
    unit_cost = db.Column(db.Numeric(15, 4), nullable=False, default=0)
    line_total = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    # The stock movement the receipt created, so the line can be traced to
    # the movement that put the goods on the shelf.
    movement_id = db.Column(db.Integer, db.ForeignKey("stock_movements.id", ondelete="SET NULL"), nullable=True)
    received_quantity = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    # Archive-only: a line is never deleted, it is retired.
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    purchase_order = db.relationship("MaintenancePurchaseOrder", back_populates="lines")
    product = db.relationship("Product", foreign_keys=[product_id])
    movement = db.relationship("StockMovement", foreign_keys=[movement_id])

    def __repr__(self):
        return f"<MaintenancePurchaseOrderLine {self.product_id} x{self.quantity}>"
