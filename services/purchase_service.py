from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from flask import current_app
from extensions import db
from models import (
    Purchase,
    PurchaseLine,
    PurchaseReturn,
    PurchaseReturnLine,
    Product,
    Supplier,
)
from services.stock_service import StockService, _safe_for_update
from services.exchange_rate_service import ExchangeRateService
from services.gl_service import GLService, GL_ACCOUNTS
from services.gl_posting import post_or_fail
from utils.gl_reference_types import GLRef
from utils.branching import ensure_warehouse_access
from utils.helpers import generate_number
from services.logging_core import LoggingCore
from utils.tenanting import get_active_tenant_id
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from utils.field_validators import validate_currency_code
from utils.tax_settings import normalize_tax_rate, should_post_vat_gl


class PurchaseService:
    @staticmethod
    def create_purchase(
        user,
        supplier_data,
        lines_data,
        warehouse_id=None,
        currency=None,
        user_exchange_rate=None,
        discount_amount=0,
        tax_rate=0,
        notes=None,
        freight=0,
        insurance=0,
        customs_duty=0,
        other_landed_cost=0,
    ):
        """
        Create a new purchase invoice with stock update and GL entries.

        Args:
            user: Current user object (creator)
            supplier_data: Dict containing supplier_id or name/phone/email
            lines_data: List of dicts [{'product_id': int, 'quantity': float, 'unit_cost': float, 'discount_percent': float}]
            warehouse_id: ID of the warehouse to add stock to
            currency: Currency code (default 'AED')
            user_exchange_rate: Optional manual exchange rate
            discount_amount: Total discount amount
            tax_rate: Tax percentage
            notes: Optional notes
            freight: Freight/shipping cost (in purchase currency)
            insurance: Insurance cost (in purchase currency)
            customs_duty: Customs/duty cost (in purchase currency)
            other_landed_cost: Other landed costs (in purchase currency)

        Returns:
            Purchase object
        """
        if not currency:
            try:
                from models import Tenant

                currency = resolve_default_currency(Tenant.get_current())
            except Exception:
                currency = get_system_default_currency()
        currency = (currency or "").strip() or get_system_default_currency()
        currency = validate_currency_code(currency)
        # Validate Warehouse
        if not warehouse_id:
            raise ValueError("⚠️ يجب اختيار المستودع الذي ستُضاف إليه البضاعة.")

        warehouse = ensure_warehouse_access(warehouse_id, user=user)

        # Validate Supplier
        supplier_id = supplier_data.get("supplier_id")
        supplier_name = supplier_data.get("supplier_name")

        supplier = None
        if supplier_id:
            # Validate supplier belongs to the same tenant as the warehouse
            supplier = Supplier.query.filter_by(
                id=supplier_id, tenant_id=warehouse.tenant_id
            ).first()
            if not supplier:
                raise ValueError("⚠️ المورد المحدد غير موجود أو لا ينتمي لنفس الشركة.")
            supplier_name = supplier.name
            supplier_data["phone"] = supplier.phone or ""
            supplier_data["email"] = supplier.email or ""

        if not supplier_name:
            raise ValueError("⚠️ يجب إدخال اسم المورد.")

        if not lines_data:
            raise ValueError("⚠️ يجب إضافة منتج واحد على الأقل للفاتورة.")

        has_valid_line = False
        for line_data in lines_data:
            product_id = line_data.get("product_id")
            quantity = Decimal(str(line_data.get("quantity") or 0))
            unit_cost = Decimal(str(line_data.get("unit_cost") or 0))
            if product_id and quantity > 0 and unit_cost >= 0:
                has_valid_line = True
                break
        if not has_valid_line:
            raise ValueError("⚠️ يجب إضافة منتج واحد على الأقل للفاتورة.")

        # Resolve tenant from warehouse (validated above) or active context
        tenant_id = (
            get_active_tenant_id(user)
            or getattr(user, "tenant_id", None)
            or getattr(warehouse, "tenant_id", None)
        )

        # Generate Number
        purchase_branch_id = warehouse.branch_id or user.branch_id
        purchase_number = generate_number(
            "P",
            Purchase,
            "purchase_number",
            branch_id=purchase_branch_id,
            tenant_id=tenant_id,
        )

        from utils.tax_settings import get_prices_include_vat

        prices_include_vat = get_prices_include_vat(
            tenant_id=tenant_id, branch_id=purchase_branch_id
        )

        from utils.currency_utils import resolve_tenant_base_currency

        base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)
        rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
            currency,
            base_currency,
            user_rate=user_exchange_rate,
            tenant_id=tenant_id,
        )
        if rate_info.get("rate_mode") == "needs_input":
            raise ValueError(
                "⚠️ سعر الصرف غير متوفر.\n"
                "💡 اذهب إلى إعدادات المالك ← أسعار الصرف ← أدخل سعر يدوي، "
                'أو أدخل سعراً في حقل "سعر الصرف".'
            )
        exchange_rate = Decimal(str(rate_info["rate"]))

        # Create Purchase Header
        effective_tax_rate = normalize_tax_rate(tax_rate, tenant_id)
        purchase = Purchase(
            tenant_id=tenant_id,
            purchase_number=purchase_number,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            branch_id=purchase_branch_id,
            supplier_name=supplier_name,
            supplier_phone=supplier_data.get("phone"),
            supplier_email=supplier_data.get("email"),
            currency=currency,
            exchange_rate=exchange_rate,
            discount_amount=Decimal(str(discount_amount or 0)),
            tax_rate=effective_tax_rate,
            prices_include_vat=prices_include_vat,
            notes=notes,
            user_id=user.id,
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            freight=Decimal(str(freight or 0)),
            insurance=Decimal(str(insurance or 0)),
            customs_duty=Decimal(str(customs_duty or 0)),
            other_landed_cost=Decimal(str(other_landed_cost or 0)),
        )

        db.session.add(purchase)
        db.session.flush()

        subtotal = Decimal("0")
        lines_added = 0

        for line_data in lines_data:
            product_id = line_data.get("product_id")
            quantity = Decimal(str(line_data.get("quantity") or 0))
            unit_cost = Decimal(str(line_data.get("unit_cost") or 0))
            discount_percent = Decimal(str(line_data.get("discount_percent") or 0))

            if product_id and quantity > 0 and unit_cost >= 0:
                product = db.session.get(Product, product_id)
                if product:
                    line = PurchaseLine(
                        tenant_id=tenant_id,
                        purchase_id=purchase.id,
                        product_id=product_id,
                        quantity=quantity,
                        unit_cost=unit_cost,
                        discount_percent=discount_percent,
                    )

                    # Calculate line totals
                    line_subtotal = quantity * unit_cost
                    line_discount = line_subtotal * (discount_percent / Decimal("100"))
                    line_total = line_subtotal - line_discount

                    line.line_total = line_total
                    db.session.add(line)
                    db.session.flush()
                    subtotal += line_total
                    lines_added += 1
                    if getattr(product, "has_serial_number", False):
                        from utils.serial_helpers import (
                            extract_serials,
                            validate_serials,
                        )

                        clean_serials = extract_serials(line_data)
                        validate_serials(
                            clean_serials,
                            product.name,
                            int(Decimal(str(line_data.get("quantity", 0)))),
                        )

                        from models.product_serial import ProductSerial

                        existing_serials = ProductSerial.query.filter(
                            ProductSerial.tenant_id == tenant_id,
                            ProductSerial.serial_number.in_(clean_serials),
                        ).count()
                        if existing_serials > 0:
                            raise ValueError(
                                f'⚠️ بعض الأرقام التسلسلية موجودة مسبقاً للمنتج "{product.name}".'
                            )

                        for sn in clean_serials:
                            serial_obj = ProductSerial(
                                tenant_id=tenant_id,
                                product_id=product_id,
                                serial_number=sn,
                                status="available",
                                warehouse_id=warehouse_id,
                                purchase_line_id=line.id,
                            )
                            if getattr(product, "warranty_days", 0) > 0:
                                from datetime import datetime, timedelta

                                serial_obj.warranty_start_date = datetime.now()
                                serial_obj.warranty_end_date = (
                                    datetime.now()
                                    + timedelta(days=int(product.warranty_days))
                                )
                            db.session.add(serial_obj)

        if lines_added == 0:
            current_app.logger.warning(
                "Purchase creation rolled back: no lines added for purchase %s",
                purchase.purchase_number,
            )
            raise ValueError("⚠️ يجب إضافة منتج واحد على الأقل للفاتورة.")

        purchase.subtotal = subtotal
        purchase.calculate_totals()

        total_landed = purchase.total_landed_cost
        if total_landed > 0 and purchase.subtotal > 0:
            for line in purchase.lines:
                if line.line_total and line.line_total > 0:
                    ratio = line.line_total / purchase.subtotal
                    line.landed_cost = (total_landed * ratio).quantize(
                        Decimal("0.001"), rounding=ROUND_HALF_UP
                    )

        db.session.flush()

        # Stock Update (uses landed_unit_cost for WAC when MWAC is enabled)
        StockService.process_purchase_lines(purchase, warehouse_id)

        # GL Entries
        GLService.ensure_core_accounts(tenant_id=tenant_id)

        capitalize_landed = current_app.config.get(
            "ENABLE_LANDED_COST_CAPITALIZATION", True
        )

        # Inventory debit should be VAT-exclusive (taxable_amount) plus landed costs if capitalized
        inventory_debit = purchase.taxable_amount or Decimal("0")
        if capitalize_landed:
            inventory_debit += total_landed
        if inventory_debit < Decimal("0"):
            inventory_debit = Decimal("0")

        total_payable = purchase.total_amount

        lines = [
            {
                "account": GL_ACCOUNTS["inventory"],
                "concept_code": "INVENTORY_ASSET",
                "debit": inventory_debit,
                "description": f"شراء بضاعة {purchase.purchase_number}",
            },
            {
                "account": GL_ACCOUNTS["payable"],
                "concept_code": "AP",
                "credit": total_payable,
                "description": f"ذمم دائنة - مورد: {purchase.supplier_name}",
            },
        ]

        # إذا كانت التكاليف الإضافية لا تُرسمل، فترحيلها إلى حساباتها المناسبة
        if not capitalize_landed and total_landed > 0:
            if purchase.freight > 0:
                lines.append(
                    {
                        "account": GL_ACCOUNTS.get("freight_in", "5301"),
                        "concept_code": "FREIGHT_IN",
                        "debit": purchase.freight,
                        "description": f"أجور شحن - {purchase.purchase_number}",
                    }
                )
            if purchase.customs_duty > 0:
                lines.append(
                    {
                        "account": GL_ACCOUNTS.get("customs_duty", "5302"),
                        "concept_code": "CUSTOMS_DUTY",
                        "debit": purchase.customs_duty,
                        "description": f"رسوم جمركية - {purchase.purchase_number}",
                    }
                )
            if purchase.insurance > 0:
                lines.append(
                    {
                        "account": GL_ACCOUNTS.get("insurance_in", "5303"),
                        "explicit_account_allowed": True,
                        "debit": purchase.insurance,
                        "description": f"تأمين شحن - {purchase.purchase_number}",
                    }
                )
            if purchase.other_landed_cost > 0:
                lines.append(
                    {
                        "account": GL_ACCOUNTS.get("misc_expense", "6500"),
                        "explicit_account_allowed": True,
                        "debit": purchase.other_landed_cost,
                        "description": f"تكاليف إضافية أخرى - {purchase.purchase_number}",
                    }
                )

        if purchase.tax_amount > 0 and should_post_vat_gl(tenant_id):
            lines.append(
                {
                    "account": GL_ACCOUNTS["vat_input"],
                    "concept_code": "VAT_INPUT",
                    "debit": purchase.tax_amount,
                    "description": f"ضريبة مدخلات (شراء) {purchase.purchase_number}",
                }
            )

        post_or_fail(
            lines,
            description=f"Purchase {purchase.purchase_number}",
            reference_type=GLRef.PURCHASE,
            reference_id=purchase.id,
            currency=purchase.currency,
            exchange_rate=purchase.exchange_rate,
            branch_id=purchase.branch_id,
            tenant_id=tenant_id,
        )

        if supplier:
            try:
                from decimal import Decimal as _D

                supplier.apply_purchase(_D(str(purchase.amount_aed or 0)))
            except Exception as e:
                current_app.logger.warning(f"Supplier stats update failed: {e}")

        db.session.flush()
        LoggingCore.log_audit("create", "purchases", purchase.id)

        return purchase

    @staticmethod
    def cancel_purchase(purchase):
        """إلغاء فاتورة شراء - عكس القيد المحاسبي والمخزون ورصيد المورد."""
        if purchase.status == "cancelled":
            raise ValueError("فاتورة الشراء ملغاة بالفعل")

        from models import Payment

        direct_paid = (
            db.session.query(db.func.sum(Payment.amount_aed))
            .filter(
                Payment.purchase_id == purchase.id,
                Payment.tenant_id == purchase.tenant_id,
                Payment.direction == "outgoing",
                Payment.payment_confirmed,
            )
            .scalar()
        )
        if direct_paid and Decimal(str(direct_paid)) > 0:
            raise ValueError(
                "لا يمكن إلغاء فاتورة شراء لها مدفوعات مؤكدة. قم بإلغاء المدفوعات أولاً."
            )

        supplier = purchase.supplier
        amount_aed = Decimal(str(purchase.amount_aed or 0))

        if supplier:
            supplier.total_purchases_aed = max(
                (supplier.total_purchases_aed or Decimal("0")) - amount_aed,
                Decimal("0"),
            )

        from models.warehouse import StockMovement

        has_stock = (
            StockMovement.query.filter_by(
                reference_type=GLRef.PURCHASE,
                reference_id=purchase.id,
            ).first()
            is not None
        )

        if has_stock:
            StockService.reverse_purchase(purchase)

            GLService.reverse_entry(
                reference_type=GLRef.PURCHASE,
                reference_id=purchase.id,
                description=f"Reverse Purchase {purchase.purchase_number} (Cancelled)",
                tenant_id=getattr(purchase, "tenant_id", None),
            )

        purchase.status = "cancelled"

        try:
            db.session.flush()
        except Exception:
            current_app.logger.exception(
                "Purchase cancel flush failed for %s", purchase.purchase_number
            )
            raise

        LoggingCore.log_audit("cancel", "purchases", purchase.id)

    @staticmethod
    def create_purchase_return(purchase, user, lines_data, reason=None, notes=None):
        """إنشاء مرتجع مشتريات - عكس المخزون والقيد المحاسبي ورصيد المورد."""
        from models.product_serial import ProductSerial
        from decimal import Decimal as _D

        if purchase.status == "cancelled":
            raise ValueError("لا يمكن عمل مرتجع لفاتورة شراء ملغاة")

        if not lines_data:
            raise ValueError("يجب إرجاع منتج واحد على الأقل")

        tenant_id = getattr(purchase, "tenant_id", None)
        warehouse_id = getattr(purchase, "warehouse_id", None)
        branch_id = getattr(purchase, "branch_id", None)

        capitalized = current_app.config.get("ENABLE_LANDED_COST_CAPITALIZATION", True)
        mwac = current_app.config.get("ENABLE_MWAC", False)

        return_number = generate_number(
            "PR",
            PurchaseReturn,
            "return_number",
            branch_id=branch_id,
            tenant_id=tenant_id,
        )

        purchase_return = PurchaseReturn(
            tenant_id=tenant_id,
            return_number=return_number,
            purchase_id=purchase.id,
            supplier_id=purchase.supplier_id,
            warehouse_id=warehouse_id,
            branch_id=branch_id,
            currency=purchase.currency,
            exchange_rate=purchase.exchange_rate,
            reason=reason,
            notes=notes,
            processed_by=user.id,
        )
        db.session.add(purchase_return)
        db.session.flush()

        subtotal = _D("0")
        tax_amount = _D("0")

        for line_data in lines_data:
            purchase_line_id = line_data.get("purchase_line_id")
            product_id = line_data.get("product_id")
            quantity = _D(str(line_data.get("quantity") or 0))
            unit_cost = _D(str(line_data.get("unit_cost") or 0))
            return_reason = line_data.get("reason", "")

            if quantity <= 0:
                continue

            line_total = (quantity * unit_cost).quantize(
                _D("0.001"), rounding=ROUND_HALF_UP
            )
            subtotal += line_total

            return_line = PurchaseReturnLine(
                tenant_id=tenant_id,
                return_id=purchase_return.id,
                purchase_line_id=purchase_line_id,
                product_id=product_id,
                quantity=quantity,
                unit_cost=unit_cost,
                line_total=line_total,
                reason=return_reason,
            )
            db.session.add(return_line)
            db.session.flush()

            # إعادة تعيين الأرقام التسلسلية إذا كانت موجودة
            serials = (
                ProductSerial.query.filter_by(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    purchase_line_id=purchase_line_id,
                    status="available",
                )
                .limit(int(quantity))
                .all()
            )
            for serial in serials:
                serial.status = "returned"

            # إزالة المخزون (إرجاع للمورد)
            StockService.remove_stock(
                product_id=product_id,
                quantity=quantity,
                reference_type=GLRef.PURCHASE,
                reference_id=purchase_return.id,
                notes=f"مرتجع مشتريات: {return_number}",
                warehouse_id=warehouse_id,
            )

            # عكس MWAC
            if mwac and tenant_id and warehouse_id:
                from models.product_warehouse_cost import ProductWarehouseCost
                from models.product_cost_history import ProductCostHistory

                pwc = _safe_for_update(
                    ProductWarehouseCost.query.filter_by(
                        tenant_id=tenant_id,
                        product_id=product_id,
                        warehouse_id=warehouse_id,
                    ),
                    label=f"purchase_return_PWC_{product_id}_{warehouse_id}",
                )
                if pwc and pwc.total_quantity > 0:
                    cost_history = (
                        ProductCostHistory.query.filter_by(
                            tenant_id=tenant_id,
                            product_id=product_id,
                            warehouse_id=warehouse_id,
                            movement_type="purchase",
                            reference_type=GLRef.PURCHASE,
                            reference_id=purchase.id,
                        )
                        .order_by(ProductCostHistory.id.desc())
                        .first()
                    )
                    original_unit_cost = (
                        abs(_D(str(cost_history.movement_unit_cost)))
                        if cost_history
                        else unit_cost
                    )
                    quantity * original_unit_cost

                    old_qty = pwc.total_quantity
                    old_value = pwc.total_value
                    old_avg = pwc.average_cost

                    new_qty, new_value, new_avg = StockService._mwac_calc(
                        old_qty, old_value, -quantity, original_unit_cost
                    )

                    pwc.total_quantity = new_qty if new_qty >= 0 else _D("0")
                    pwc.total_value = new_value if new_value >= 0 else _D("0")
                    pwc.average_cost = (
                        new_avg.quantize(_D("0.0001")) if new_qty > 0 else _D("0")
                    )
                    pwc.last_updated = datetime.now(timezone.utc)

                    pch = ProductCostHistory(
                        tenant_id=tenant_id,
                        product_id=product_id,
                        warehouse_id=warehouse_id,
                        movement_type="purchase_reversal",
                        reference_type=GLRef.PURCHASE,
                        reference_id=purchase_return.id,
                        old_average_cost=(
                            old_avg.quantize(_D("0.0001")) if old_avg else None
                        ),
                        new_average_cost=pwc.average_cost,
                        quantity_change=-quantity,
                        old_total_quantity=old_qty,
                        new_total_quantity=pwc.total_quantity,
                        old_total_value=old_value,
                        new_total_value=pwc.total_value,
                        movement_unit_cost=original_unit_cost.quantize(_D("0.0001")),
                    )
                    db.session.add(pch)

        if subtotal <= 0:
            current_app.logger.warning(
                "Purchase return rolled back: no lines for return %s",
                getattr(purchase_return, "return_number", None),
            )
            raise ValueError("يجب إرجاع منتج واحد على الأقل")

        # حساب الضريبة التناسبية
        if purchase.tax_amount and purchase.subtotal and purchase.subtotal > 0:
            tax_ratio = subtotal / _D(str(purchase.subtotal))
            tax_amount = (_D(str(purchase.tax_amount)) * tax_ratio).quantize(
                _D("0.01"), rounding=ROUND_HALF_UP
            )

        purchase_return.subtotal = subtotal
        purchase_return.tax_amount = tax_amount

        # حساب رصيد المخزون شامل التكاليف الجمركية المرسملة (VAT-exclusive إذا كانت الأسعار شاملة)
        inventory_credit = subtotal
        if purchase.prices_include_vat:
            _tr = purchase.tax_rate
            try:
                tax_rate = Decimal(str(_tr)) if _tr is not None else Decimal("0")
            except Exception:
                tax_rate = Decimal("0")
            if tax_rate > 0:
                inventory_credit = (
                    subtotal / (Decimal("1") + (tax_rate / Decimal("100")))
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if capitalized:
            for return_line in purchase_return.lines:
                if return_line.purchase_line_id:
                    pl = next(
                        (
                            l
                            for l in purchase.lines
                            if l.id == return_line.purchase_line_id
                        ),
                        None,
                    )
                    if pl and pl.landed_cost and pl.landed_cost > 0:
                        landed_ratio = (
                            _D(str(pl.landed_cost)) / _D(str(pl.line_total))
                            if pl.line_total > 0
                            else _D("0")
                        )
                        inventory_credit += (
                            _D(str(return_line.line_total)) * landed_ratio
                        ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

        purchase_return.total_amount = inventory_credit + tax_amount
        purchase_return.calculate_totals()
        db.session.flush()

        # GL posting
        GLService.ensure_core_accounts(tenant_id=tenant_id)

        gl_lines = [
            {
                "account": GL_ACCOUNTS["payable"],
                "concept_code": "AP",
                "debit": purchase_return.total_amount,
                "description": f"مرتجع مشتريات {return_number}",
            },
            {
                "account": GL_ACCOUNTS["inventory"],
                "concept_code": "INVENTORY_ASSET",
                "credit": inventory_credit,
                "description": f"إرجاع بضاعة للمورد {return_number}",
            },
        ]

        if tax_amount > 0 and should_post_vat_gl(tenant_id):
            gl_lines.append(
                {
                    "account": GL_ACCOUNTS["vat_input"],
                    "concept_code": "VAT_INPUT",
                    "credit": tax_amount,
                    "description": f"عكس ضريبة مدخلات {return_number}",
                }
            )

        post_or_fail(
            gl_lines,
            description=f"Purchase Return {return_number}",
            reference_type=GLRef.PURCHASE,
            reference_id=purchase_return.id,
            currency=purchase_return.currency,
            exchange_rate=purchase_return.exchange_rate,
            branch_id=branch_id,
            tenant_id=tenant_id,
        )

        if purchase.supplier:
            supplier = purchase.supplier
            supplier.total_purchases_aed = max(
                (supplier.total_purchases_aed or _D("0"))
                - _D(str(purchase_return.amount_aed or 0)),
                _D("0"),
            )

        try:
            db.session.flush()
        except Exception:
            current_app.logger.exception(
                "Purchase return flush failed for %s",
                getattr(purchase_return, "return_number", None),
            )
            raise

        LoggingCore.log_audit("create", "purchase_returns", purchase_return.id)
        return purchase_return
