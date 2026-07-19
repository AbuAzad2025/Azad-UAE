import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

from flask import current_app

from extensions import db
from models import (
    Sale,
    SaleLine,
    ProductReturn,
    ProductReturnLine,
    Product,
    ProductSerial,
)
from services.stock_service import StockService
from services.gl_service import GLService
from services.gl_posting import post_or_fail
from utils.helpers import generate_number
from utils.gl_reference_types import GLRef
from utils.tax_settings import should_post_vat_gl
from utils.tenanting import get_active_tenant_id, is_platform_owner
from utils.branching import branch_scope_id_for

logger = logging.getLogger(__name__)


class ReturnService:
    GOOD_CONDITIONS = {"good", "sellable", "available"}
    DAMAGED_CONDITIONS = {"damaged", "defective", "bad"}

    @staticmethod
    def _normalize_condition(value):
        condition = (value or "good").strip().lower()
        if condition in ReturnService.GOOD_CONDITIONS:
            return "good"
        if condition in ReturnService.DAMAGED_CONDITIONS:
            return "damaged"
        raise ValueError(f"Unsupported return condition: {value}")

    @staticmethod
    def _optional_money(value, field_name="amount"):
        if value is None or value == "":
            return None
        try:
            amount = Decimal(str(value)).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
        except Exception:
            raise ValueError(f"{field_name} is invalid.")
        if amount < 0:
            raise ValueError(f"{field_name} cannot be negative.")
        return amount

    @staticmethod
    def _validate_sale_access(sale, user=None):
        if not user or not getattr(user, "is_authenticated", False):
            return

        active_tenant_id = get_active_tenant_id(user)
        platform_owner = is_platform_owner(user)

        if platform_owner:
            if active_tenant_id is not None and int(sale.tenant_id) != int(
                active_tenant_id
            ):
                raise ValueError("Sale is outside the active tenant.")
        else:
            if active_tenant_id is None or int(sale.tenant_id) != int(active_tenant_id):
                raise ValueError("Sale is outside your tenant scope.")

        scoped_branch_id = branch_scope_id_for(user)
        if scoped_branch_id is not None and int(sale.branch_id or 0) != int(
            scoped_branch_id
        ):
            raise ValueError("Sale is outside the allowed branch scope.")

        is_seller = getattr(user, "is_seller", None)
        if callable(is_seller) and is_seller() and int(sale.seller_id) != int(user.id):
            raise ValueError("Seller cannot return another seller sale.")

    @staticmethod
    def _serials_from_line_data(line_data):
        from utils.serial_helpers import extract_serials

        return extract_serials(line_data)

    @staticmethod
    def _sale_line_sold_qty(sale_line) -> Decimal:
        return Decimal(str(sale_line.quantity or 0))

    @staticmethod
    def create_return(
        sale_id,
        return_lines_data,
        user=None,
        user_id=None,
        notes=None,
        manual_refund_amount=None,
    ):
        try:
            sale = db.session.get(Sale, sale_id)
            if not sale:
                raise ValueError(f"Sale with ID {sale_id} not found.")

            ReturnService._validate_sale_access(sale, user)

            if sale.status == "cancelled":
                raise ValueError("Cannot create return for a cancelled sale.")
            if sale.status == "pending":
                raise ValueError("Cannot create return for a pending sale.")

            manual_refund_amount = ReturnService._optional_money(
                manual_refund_amount, "manual_refund_amount"
            )

            tenant_id = sale.tenant_id
            processed_by = getattr(user, "id", None) or user_id
            return_number = generate_number(
                "R",
                ProductReturn,
                "return_number",
                branch_id=sale.branch_id,
                tenant_id=tenant_id,
            )

            product_return = ProductReturn(
                tenant_id=tenant_id,
                return_number=return_number,
                sale_id=sale.id,
                customer_id=sale.customer_id,
                branch_id=sale.branch_id,
                currency=sale.currency,
                exchange_rate=sale.exchange_rate,
                notes=notes,
                processed_by=processed_by,
                status="approved",
            )

            product_return.total_amount = Decimal("0")
            product_return.refund_amount = Decimal("0")
            product_return.amount_aed = Decimal("0")

            db.session.add(product_return)
            db.session.flush()

            total_gross_return = Decimal("0")
            total_net_return = Decimal("0")
            revenue_lines = []
            cost_lines = []
            lines_added = 0

            for line_data in return_lines_data:
                sale_line_id = line_data.get("sale_line_id")
                try:
                    quantity = Decimal(str(line_data.get("quantity", 0) or 0))
                except Exception:
                    raise ValueError("Invalid return quantity.")

                if quantity <= 0:
                    continue

                sale_line = db.session.get(SaleLine, sale_line_id)
                if not sale_line:
                    raise ValueError(f"Sale line {sale_line_id} not found.")

                if sale_line.sale_id != sale.id:
                    raise ValueError(
                        f"Sale line {sale_line_id} does not belong to sale {sale.id}."
                    )

                if int(sale_line.tenant_id) != int(tenant_id):
                    raise ValueError("Sale line is outside tenant scope.")

                product = sale_line.product or db.session.get(
                    Product, sale_line.product_id
                )
                if not product:
                    raise ValueError("Returned product was not found.")

                condition = ReturnService._normalize_condition(
                    line_data.get("condition")
                )
                is_good = condition == "good"

                previous_returned = db.session.query(
                    db.func.sum(ProductReturnLine.quantity)
                ).join(ProductReturn).filter(
                    ProductReturnLine.sale_line_id == sale_line.id
                ).filter(ProductReturn.status != "rejected").filter(
                    ProductReturn.tenant_id == tenant_id
                ).scalar() or Decimal("0")

                if (previous_returned + quantity) > sale_line.quantity:
                    raise ValueError(
                        f"Cannot return {quantity} of {product.name}. "
                        f"Already returned: {previous_returned}, Sold: {sale_line.quantity}."
                    )

                if product.has_serial_number:
                    if quantity != quantity.to_integral_value():
                        raise ValueError(
                            f"Product {product.name} requires a whole-number quantity because it uses serial numbers."
                        )

                    serials_to_return = ReturnService._serials_from_line_data(line_data)
                    from utils.serial_helpers import validate_serials

                    validate_serials(serials_to_return, product.name, int(quantity))

                    for serial_number in serials_to_return:
                        serial_obj = ProductSerial.query.filter_by(
                            product_id=sale_line.product_id,
                            serial_number=serial_number,
                            sale_line_id=sale_line.id,
                        ).first()

                        if not serial_obj:
                            raise ValueError(
                                f"Serial {serial_number} is not linked to this sale line."
                            )
                        if serial_obj.status != "sold":
                            raise ValueError(
                                f"Serial {serial_number} is not sold and cannot be returned."
                            )

                        serial_obj.status = "available" if is_good else "defective"
                        serial_obj.sale_line_id = None
                        serial_obj.warranty_start_date = None
                        serial_obj.warranty_end_date = None
                        db.session.add(serial_obj)
                else:
                    unexpected_serials = ReturnService._serials_from_line_data(
                        line_data
                    )
                    if unexpected_serials:
                        raise ValueError(
                            f"Product {product.name} does not use serial numbers."
                        )

                sold_qty = ReturnService._sale_line_sold_qty(sale_line)
                if sold_qty <= 0:
                    raise ValueError("Invalid sale line quantity.")

                effective_unit_price = (
                    Decimal(str(sale_line.line_total or 0)) / sold_qty
                ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                line_total = (effective_unit_price * quantity).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )

                sale_subtotal = Decimal(str(sale.subtotal or 0))
                if sale_subtotal > 0 and sale.discount_amount > 0:
                    discount_share = (
                        line_total / sale_subtotal * Decimal(str(sale.discount_amount))
                    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                    net_line_return = line_total - discount_share
                else:
                    net_line_return = line_total

                if sale_subtotal > 0 and sale.shipping_cost > 0:
                    shipping_share = (
                        line_total / sale_subtotal * Decimal(str(sale.shipping_cost))
                    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                    net_line_return += shipping_share

                if net_line_return < Decimal("0"):
                    net_line_return = Decimal("0")

                total_gross_return += line_total
                total_net_return += net_line_return

                return_line = ProductReturnLine(
                    tenant_id=tenant_id,
                    return_id=product_return.id,
                    sale_line_id=sale_line.id,
                    product_id=sale_line.product_id,
                    quantity=quantity,
                    unit_price=effective_unit_price,
                    line_total=line_total,
                    condition=condition,
                    notes=line_data.get("notes"),
                )
                db.session.add(return_line)
                lines_added += 1

                if is_good:
                    StockService.create_movement(
                        product_id=sale_line.product_id,
                        quantity=quantity,
                        movement_type="return",
                        reference_type=GLRef.PRODUCT_RETURN,
                        reference_id=product_return.id,
                        notes=f"Return for Sale {sale.sale_number}",
                        warehouse_id=sale.warehouse_id,
                    )

                    # استخدام تكلفة COGS الأصلية من سجل التكلفة أولاً، ثم من بند الفاتورة، ثم من المنتج
                    original_cost = Decimal("0")
                    try:
                        from models import ProductCostHistory

                        cost_hist = (
                            ProductCostHistory.query.filter_by(
                                tenant_id=tenant_id,
                                product_id=sale_line.product_id,
                                warehouse_id=sale.warehouse_id,
                                movement_type="sale",
                                reference_type=GLRef.SALE,
                                reference_id=sale.id,
                            )
                            .order_by(ProductCostHistory.id.desc())
                            .first()
                        )
                        if cost_hist and cost_hist.movement_unit_cost:
                            original_cost = abs(
                                Decimal(str(cost_hist.movement_unit_cost))
                            )
                    except Exception:
                        logger.warning(
                            "Failed to fetch cost history for return cost calculation, product %s sale %s",
                            sale_line.product_id,
                            sale.id,
                            exc_info=True,
                        )
                    if original_cost <= Decimal("0"):
                        original_cost = Decimal(str(sale_line.cost_price or 0))
                    if original_cost <= Decimal("0"):
                        original_cost = Decimal(str(product.cost_price or 0))
                    cost_unit = original_cost
                    cost_value = (quantity * cost_unit).quantize(
                        Decimal("0.001"), rounding=ROUND_HALF_UP
                    )

                    if cost_value > 0:
                        cost_lines.append(
                            {
                                "account": GLService.get_account_code_for_concept(
                                    "INVENTORY_ASSET",
                                    branch_id=product_return.branch_id,
                                    tenant_id=tenant_id,
                                    fallback_key="inventory",
                                ),
                                "concept_code": "INVENTORY_ASSET",
                                "debit": cost_value,
                                "credit": 0,
                                "description": f"Inventory Restock - {product.name}",
                            }
                        )
                        cost_lines.append(
                            {
                                "account": GLService.get_account_code_for_concept(
                                    "COGS",
                                    branch_id=product_return.branch_id,
                                    tenant_id=tenant_id,
                                    fallback_key="cogs",
                                ),
                                "concept_code": "COGS_REVERSAL",
                                "debit": 0,
                                "credit": cost_value,
                                "description": f"COGS Reversal - {product.name}",
                            }
                        )

                    mwac_enabled = current_app.config.get("ENABLE_MWAC", False)
                    if mwac_enabled and tenant_id and sale.warehouse_id:
                        try:
                            from models import ProductWarehouseCost

                            query = ProductWarehouseCost.query.filter_by(
                                tenant_id=tenant_id,
                                product_id=sale_line.product_id,
                                warehouse_id=sale.warehouse_id,
                            )
                            from services.stock_service import _safe_for_update

                            pwc = _safe_for_update(
                                query,
                                label=f"PWC(return) p={sale_line.product_id} w={sale.warehouse_id}",
                            )
                            if pwc:
                                qty_decimal = Decimal(str(quantity))
                                old_qty = pwc.total_quantity
                                old_value = pwc.total_value
                                old_avg = pwc.average_cost
                                new_qty, new_value, new_avg = StockService._mwac_calc(
                                    old_qty, old_value, qty_decimal, cost_unit
                                )
                                pwc.total_quantity = new_qty
                                pwc.total_value = new_value
                                pwc.average_cost = new_avg
                                pwc.last_updated = datetime.now(timezone.utc)
                                from models import ProductCostHistory

                                pch = ProductCostHistory(
                                    tenant_id=tenant_id,
                                    product_id=sale_line.product_id,
                                    warehouse_id=sale.warehouse_id,
                                    movement_type="return",
                                    reference_type=GLRef.PRODUCT_RETURN,
                                    reference_id=product_return.id,
                                    old_average_cost=(
                                        old_avg.quantize(Decimal("0.0001"))
                                        if old_avg
                                        else None
                                    ),
                                    new_average_cost=new_avg,
                                    quantity_change=qty_decimal,
                                    old_total_quantity=old_qty,
                                    new_total_quantity=new_qty,
                                    old_total_value=old_value,
                                    new_total_value=new_value,
                                    movement_unit_cost=cost_unit,
                                )
                                db.session.add(pch)
                        except Exception as exc:
                            # Re-raise OperationalError (lock failure) — never silently drop the lock.
                            from sqlalchemy.exc import OperationalError

                            if isinstance(exc, OperationalError):
                                raise
                            current_app.logger.exception(
                                "MWAC update failed during return %s for product %s",
                                getattr(product_return, "id", None),
                                sale_line.product_id,
                            )

            if lines_added == 0:
                raise ValueError("At least one returned item is required.")

            product_return.total_amount = total_gross_return.quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )

            tax_rate = Decimal(str(sale.tax_rate or 0))
            if not should_post_vat_gl(tenant_id):
                tax_rate = Decimal("0")

            auto_net_return_amount = total_net_return.quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
            auto_tax_amount = (
                auto_net_return_amount * (tax_rate / Decimal("100"))
            ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            auto_gross_return_amount = auto_net_return_amount + auto_tax_amount

            final_refund_amount = (
                manual_refund_amount
                if manual_refund_amount is not None
                else auto_gross_return_amount
            )
            if manual_refund_amount is not None:
                if tax_rate > 0:
                    net_return_amount = (
                        final_refund_amount
                        / (Decimal("1") + (tax_rate / Decimal("100")))
                    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                    tax_amount = final_refund_amount - net_return_amount
                else:
                    net_return_amount = final_refund_amount
                    tax_amount = Decimal("0")
            else:
                net_return_amount = auto_net_return_amount
                tax_amount = auto_tax_amount

            product_return.refund_amount = final_refund_amount
            exchange_rate = Decimal(str(product_return.exchange_rate or 1))
            product_return.amount_aed = (final_refund_amount * exchange_rate).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )

            if manual_refund_amount is not None:
                marker = f" | Manual refund override. Auto={auto_gross_return_amount} {product_return.currency}"
                product_return.notes = f"{product_return.notes or ''}{marker}"

            if net_return_amount > 0:
                revenue_lines.append(
                    {
                        "account": GLService.get_account_code_for_concept(
                            "SALES_REVENUE",
                            branch_id=product_return.branch_id,
                            tenant_id=tenant_id,
                            fallback_key="sales_revenue",
                        ),
                        "concept_code": "SALES_RETURNS",
                        "debit": net_return_amount,
                        "credit": 0,
                        "description": f"Sales Return Revenue Reversal {sale.sale_number}",
                    }
                )

            if tax_amount > 0 and should_post_vat_gl(tenant_id):
                revenue_lines.append(
                    {
                        "account": GLService.get_account_code_for_concept(
                            "VAT_OUTPUT",
                            branch_id=product_return.branch_id,
                            tenant_id=tenant_id,
                            fallback_key="tax_payable",
                        ),
                        "concept_code": "VAT_OUTPUT",
                        "debit": tax_amount,
                        "credit": 0,
                        "description": f"Sales Return Tax Reversal {sale.sale_number}",
                    }
                )

            if final_refund_amount > 0:
                revenue_lines.append(
                    {
                        "account": GLService.get_customer_credit_account(
                            sale.customer,
                            branch_id=product_return.branch_id,
                            tenant_id=tenant_id,
                        ),
                        "concept_code": GLService.get_customer_credit_concept(
                            sale.customer
                        ),
                        "debit": 0,
                        "credit": final_refund_amount,
                        "description": f"Credit Customer for Return {sale.sale_number}",
                    }
                )

            if revenue_lines:
                GLService.ensure_core_accounts(tenant_id=tenant_id)
                post_or_fail(
                    lines=revenue_lines,
                    description=f"Sales Return {product_return.return_number} for Sale {sale.sale_number}",
                    reference_type=GLRef.PRODUCT_RETURN,
                    reference_id=product_return.id,
                    currency=product_return.currency,
                    exchange_rate=product_return.exchange_rate,
                    branch_id=product_return.branch_id,
                    user_id=processed_by,
                    tenant_id=tenant_id,
                )
            if cost_lines:
                GLService.ensure_core_accounts(tenant_id=tenant_id)
                post_or_fail(
                    lines=cost_lines,
                    description=f"Sales Return COGS {product_return.return_number} for Sale {sale.sale_number}",
                    reference_type=GLRef.PRODUCT_RETURN,
                    reference_id=product_return.id,
                    exchange_rate=1.0,
                    branch_id=product_return.branch_id,
                    user_id=processed_by,
                    tenant_id=tenant_id,
                )

            if sale.customer:
                sale.customer.apply_return(product_return.amount_aed)

            if hasattr(sale, "recalculate_payment_status"):
                db.session.expire(sale, ["returns"])
                sale.recalculate_payment_status()

            try:
                db.session.flush()
            except Exception:
                raise

            return product_return

        except Exception as e:
            current_app.logger.error(f"Failed to create return: {e}")
            raise
