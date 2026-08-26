from datetime import UTC, datetime
from decimal import Decimal

from flask_babel import gettext

from extensions import db
from models import Quotation, QuotationLine
from utils.helpers import generate_number


class QuotationService:
    @staticmethod
    def _tid(user):
        from utils.tenanting import get_active_tenant_id

        return get_active_tenant_id(user)

    @classmethod
    def create_quotation(cls, data, user):
        tid = cls._tid(user)
        q = Quotation(
            tenant_id=tid,
            quotation_number=generate_number("QT", Quotation, "quotation_number"),
            customer_id=int(data["customer_id"]),
            branch_id=data.get("branch_id"),
            warehouse_id=data.get("warehouse_id"),
            quotation_date=datetime.now(UTC).date(),
            expiry_date=data.get("expiry_date"),
            status="draft",
            notes=data.get("notes"),
            terms=data.get("terms"),
            currency=data.get("currency", "AED"),
            exchange_rate=Decimal(str(data.get("exchange_rate", 1))),
            base_currency=data.get("base_currency", "AED"),
            prices_include_vat=bool(data.get("prices_include_vat")),
            created_by=user.id,
        )
        db.session.add(q)
        db.session.flush()

        for line_data in data.get("lines", []):
            qty = Decimal(str(line_data.get("quantity", 1)))
            price = Decimal(str(line_data.get("unit_price", 0)))
            disc = Decimal(str(line_data.get("discount_percent", 0)))
            tax = Decimal(str(line_data.get("tax_rate", 0)))
            line_total = qty * price * (1 - disc / 100)
            tax_amt = line_total * tax / 100
            line = QuotationLine(
                tenant_id=tid,
                quotation_id=q.id,
                product_id=int(line_data["product_id"]),
                description=line_data.get("description", ""),
                quantity=qty,
                unit_price=price,
                discount_percent=disc,
                tax_rate=tax,
                line_total=line_total + tax_amt,
                sort_order=line_data.get("sort_order", 0),
            )
            db.session.add(line)

        db.session.flush()
        cls._recalculate_totals(q)
        return q

    @classmethod
    def update_quotation(cls, quotation, data):
        if quotation.status not in ("draft",):
            raise ValueError(gettext("فقط المسودات يمكن تعديلها."))

        for field in (
            "customer_id",
            "branch_id",
            "warehouse_id",
            "notes",
            "terms",
            "currency",
            "exchange_rate",
            "base_currency",
            "prices_include_vat",
            "expiry_date",
        ):
            if field in data:
                if field in ("customer_id", "branch_id", "warehouse_id"):
                    val = data.get(field)
                    setattr(quotation, field, int(val) if val else None)
                elif field in ("exchange_rate",):
                    setattr(quotation, field, Decimal(str(data.get(field, 1))))
                elif field == "prices_include_vat":
                    setattr(quotation, field, bool(data.get(field)))
                else:
                    setattr(quotation, field, data.get(field))

        if "lines" in data:
            for line in list(quotation.lines):
                quotation.lines.remove(line)
            db.session.flush()

            for line_data in data.get("lines", []):
                qty = Decimal(str(line_data.get("quantity", 1)))
                price = Decimal(str(line_data.get("unit_price", 0)))
                disc = Decimal(str(line_data.get("discount_percent", 0)))
                tax = Decimal(str(line_data.get("tax_rate", 0)))
                line_total = qty * price * (1 - disc / 100)
                tax_amt = line_total * tax / 100
                line = QuotationLine(
                    tenant_id=quotation.tenant_id,
                    quotation_id=quotation.id,
                    product_id=int(line_data["product_id"]),
                    description=line_data.get("description", ""),
                    quantity=qty,
                    unit_price=price,
                    discount_percent=disc,
                    tax_rate=tax,
                    line_total=line_total + tax_amt,
                    sort_order=line_data.get("sort_order", 0),
                )
                quotation.lines.append(line)
                db.session.add(line)

        db.session.flush()
        cls._recalculate_totals(quotation)
        return quotation

    @classmethod
    def send_quotation(cls, quotation):
        if quotation.status != "draft":
            raise ValueError(gettext("فقط المسودات يمكن إرسالها."))
        quotation.status = "sent"
        db.session.flush()
        return quotation

    @classmethod
    def accept_quotation(cls, quotation):
        if quotation.status != "sent":
            raise ValueError(gettext("عرض الأسعار يجب أن يكون مرسلاً للقبول."))
        if quotation.is_expired:
            raise ValueError(gettext("عرض الأسعار منتهي الصلاحية."))
        quotation.status = "accepted"
        db.session.flush()
        return quotation

    @classmethod
    def reject_quotation(cls, quotation):
        if quotation.status not in ("sent",):
            raise ValueError(gettext("عرض الأسعار يجب أن يكون مرسلاً للرفض."))
        quotation.status = "rejected"
        db.session.flush()
        return quotation

    @classmethod
    def convert_to_sale(cls, quotation, user):
        if quotation.status != "accepted":
            raise ValueError(gettext("فقط عروض الأسعار المقبولة يمكن تحويلها."))
        if quotation.sale_id:
            raise ValueError(gettext("تم تحويل هذا العرض مسبقاً."))

        from models import Sale, SaleLine

        sale = Sale(
            tenant_id=quotation.tenant_id,
            sale_number=generate_number("SALE", Sale, "sale_number"),
            customer_id=quotation.customer_id,
            seller_id=user.id,
            warehouse_id=quotation.warehouse_id,
            branch_id=quotation.branch_id,
            sale_date=datetime.now(UTC),
            subtotal=quotation.subtotal,
            discount_amount=quotation.discount_amount,
            tax_rate=quotation.tax_rate,
            tax_amount=quotation.tax_amount,
            total_amount=quotation.total_amount,
            amount=quotation.total_amount,
            currency=quotation.currency,
            exchange_rate=quotation.exchange_rate,
            base_currency=quotation.base_currency,
            amount_aed=quotation.amount_aed,
            prices_include_vat=quotation.prices_include_vat,
            notes=quotation.notes,
            status="draft",
        )
        db.session.add(sale)
        db.session.flush()

        for q_line in quotation.lines:
            s_line = SaleLine(
                tenant_id=quotation.tenant_id,
                sale_id=sale.id,
                product_id=q_line.product_id,
                quantity=q_line.quantity,
                unit_price=q_line.unit_price,
                discount_percent=q_line.discount_percent,
                line_total=q_line.line_total,
            )
            db.session.add(s_line)

        quotation.status = "converted_to_sale"
        quotation.sale_id = sale.id
        db.session.flush()
        return sale

    @classmethod
    def duplicate_quotation(cls, quotation, user):
        data = {
            "customer_id": quotation.customer_id,
            "branch_id": quotation.branch_id,
            "warehouse_id": quotation.warehouse_id,
            "notes": quotation.notes,
            "terms": quotation.terms,
            "currency": quotation.currency,
            "exchange_rate": float(quotation.exchange_rate or 1),
            "base_currency": quotation.base_currency,
            "prices_include_vat": quotation.prices_include_vat,
            "lines": [
                {
                    "product_id": line.product_id,
                    "description": line.description,
                    "quantity": float(line.quantity),
                    "unit_price": float(line.unit_price),
                    "discount_percent": float(line.discount_percent or 0),
                    "tax_rate": float(line.tax_rate or 0),
                    "sort_order": line.sort_order,
                }
                for line in quotation.lines
            ],
        }
        return cls.create_quotation(data, user)

    @classmethod
    def get_quotation(cls, quotation_id, tenant_id=None):
        q = db.session.get(Quotation, quotation_id)
        if not q:
            raise ValueError(gettext("عرض الأسعار غير موجود."))
        if tenant_id and q.tenant_id != tenant_id:
            raise ValueError(gettext("غير مصرح."))
        return q

    @classmethod
    def list_quotations(cls, tenant_id, filters=None):
        q = Quotation.query.filter_by(tenant_id=tenant_id)
        if filters:
            if filters.get("status"):
                q = q.filter_by(status=filters["status"])
            if filters.get("customer_id"):
                q = q.filter_by(customer_id=int(filters["customer_id"]))
        return q.order_by(Quotation.created_at.desc()).all()

    @classmethod
    def _recalculate_totals(cls, quotation):
        subtotal = Decimal("0")
        total_tax = Decimal("0")
        total_discount = Decimal("0")
        for line in quotation.lines:
            base = line.quantity * line.unit_price
            disc_amt = base * line.discount_percent / 100
            total_discount += disc_amt
            taxable = base - disc_amt
            tax = taxable * line.tax_rate / 100
            total_tax += tax
            subtotal += base
        quotation.subtotal = subtotal
        quotation.discount_amount = total_discount
        quotation.tax_amount = total_tax
        quotation.total_amount = subtotal - total_discount + total_tax
        quotation.amount_aed = quotation.total_amount
        db.session.flush()
