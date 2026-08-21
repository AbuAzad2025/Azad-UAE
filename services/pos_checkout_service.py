"""POS checkout business logic."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from flask import current_app
from flask_babel import gettext

from extensions import db
from models import Customer, PosOrderType, Product
from models.enums import PermissionEnum
from services.logging_core import LoggingCore
from services.pos_override_service import PosOverrideService
from services.pos_write_service import PosWriteService
from services.promotion_service import PromotionService
from services.sale_service import SaleService
from utils.branching import ensure_warehouse_access, get_active_branch_id
from utils.currency_utils import context_aware_default_currency, convert_and_quantize_aed
from utils.pos_checkout_helpers import (
    _accumulate_session_tender,
    _compute_change_due,
    _parse_split_tenders,
    _pos_standard_price,
    _promotion_evaluation_json,
)
from utils.pos_helpers import POS_QA_MARKER, get_pos_walkin_customer, merge_checkout_lines, safe_decimal
from utils.structured_logging import log_mutation
from utils.tenanting import tenant_get


class PosCheckoutError(Exception):
    """Domain error with a suggested HTTP status and optional JSON payload."""

    def __init__(self, message: str, status_code: int = 400, payload: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


class PosCheckoutService:
    """Encapsulates the POS checkout business transaction."""

    @classmethod
    def checkout(
        cls,
        *,
        payload: dict,
        user,
        session,
        shift,
        tenant_id: int,
        branch_id: int | None,
        promotions_enabled: bool,
        multi_tender_allowed: bool,
    ):
        """Execute the checkout business logic and return ``(response, kds_order)``.

        All DB writes happen inside the caller's transaction; this service
        never commits or rolls back.
        """
        use_quick = bool(payload.get("quick_customer") or payload.get("walkin"))
        customer_id = payload.get("customer_id")

        if use_quick or not customer_id:
            try:
                customer = get_pos_walkin_customer(tenant_id)
            except ValueError:
                raise PosCheckoutError(gettext("بيانات العميل غير صالحة."), 400)
        else:
            customer = tenant_get(Customer, int(customer_id or 0))
            if not customer or not customer.is_active:
                raise PosCheckoutError(gettext("العميل غير صالح أو غير نشط."), 400)

        warehouse_id = payload.get("warehouse_id")
        if warehouse_id:
            try:
                warehouse = ensure_warehouse_access(int(warehouse_id or 0), user=user)
                warehouse_id = warehouse.id
            except ValueError:
                raise PosCheckoutError(gettext("بيانات المستودع غير صالحة."), 400)
        else:
            warehouse_id = None

        currency = (payload.get("currency") or context_aware_default_currency()).strip().upper()
        exchange_rate = payload.get("exchange_rate", 1.0)

        lines = payload.get("lines") or []
        if not isinstance(lines, list) or not lines:
            raise PosCheckoutError(gettext("يرجى إضافة منتجات للسلة."), 400)

        try:
            merged = merge_checkout_lines(lines)
        except ValueError:
            raise PosCheckoutError(gettext("بيانات السلة غير صالحة."), 400)

        discount_requested = False
        try:
            discount_requested = Decimal(str(payload.get("discount_amount") or "0")) > Decimal("0")
        except (InvalidOperation, TypeError, ValueError):
            discount_requested = False
        if not discount_requested:
            discount_requested = any(Decimal(str(row.get("discount_percent") or 0)) > Decimal("0") for row in merged)

        lines_data = []
        product_ids = [int(r["product_id"]) for r in merged]
        if product_ids:
            locked = {
                p.id: p
                for p in db.session.query(Product)
                .filter(Product.id.in_(product_ids), Product.tenant_id == tenant_id)
                .with_for_update()
                .all()
            }
        else:
            locked = {}

        for row in merged:
            product = locked.get(int(row["product_id"]))
            if not product or not product.is_active:
                raise PosCheckoutError(gettext("يوجد منتج غير صالح داخل السلة."), 400)

            if getattr(product, "has_serial_number", False):
                serials = row.get("serials") or payload.get("serials", {}).get(str(product.id)) or []
                clean_serials = [s.strip() for s in serials if s and s.strip()]
                expected_qty = int(row["quantity"])
                if len(clean_serials) != expected_qty:
                    raise PosCheckoutError(
                        gettext(
                            f'⚠️ المنتج "{product.name}" يتطلب {expected_qty} أرقاماً تسلسلية، '
                            f"ولكن تم إدخال {len(clean_serials)} فقط."
                        ),
                        400,
                    )
                row["serials"] = clean_serials

            standard_price = _pos_standard_price(product, customer.customer_type, row["quantity"])
            if row["unit_price"] is not None:
                unit_price = Decimal(str(row["unit_price"])).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            else:
                unit_price = standard_price

            lines_data.append(
                {
                    "product": product,
                    "quantity": row["quantity"],
                    "discount_percent": float(row["discount_percent"]),
                    "unit_price": unit_price,
                    "standard_price": standard_price,
                    "serials": row.get("serials", []),
                }
            )

        for ld in lines_data:
            product = ld["product"]
            standard_price = ld["standard_price"]
            unit_price = Decimal(str(ld["unit_price"]))
            if abs(unit_price - standard_price) > Decimal("0.001"):
                if not user.has_permission(PermissionEnum.OVERRIDE_SALE_PRICE) and not user.is_owner:
                    raise PosCheckoutError(
                        gettext(
                            f'⚠️ ليس لديك صلاحية تغيير سعر المنتج "{product.name}".\n'
                            f"السعر القياسي: {float(standard_price)}"
                        ),
                        403,
                    )
                LoggingCore.log_audit(
                    "price_override",
                    "pos",
                    product.id,
                    {
                        "product": product.name,
                        "standard_price": float(standard_price),
                        "override_price": float(unit_price),
                        "user_id": user.id,
                    },
                )

        promotion_evaluation = None
        if promotions_enabled:
            try:
                promotion_evaluation = PromotionService.evaluate_cart(
                    [
                        {
                            "product_id": ld["product"].id,
                            "quantity": ld["quantity"],
                            "unit_price": ld["unit_price"],
                            "category_id": getattr(ld["product"], "category_id", None),
                        }
                        for ld in lines_data
                    ],
                    tenant_id=tenant_id,
                    branch_id=branch_id or get_active_branch_id(user),
                )
            except Exception:
                current_app.logger.exception("POS promotion evaluation failed")
                promotion_evaluation = None

        payment_method = (payload.get("payment_method") or "").strip()
        paid_amount = payload.get("paid_amount", 0) or 0
        payment_currency = (payload.get("payment_currency") or currency).strip().upper()
        payment_exchange_rate = payload.get("payment_exchange_rate", exchange_rate) or exchange_rate
        reference_number = (payload.get("reference_number") or "").strip() or None

        payment_data = None
        try:
            paid_amount_decimal = Decimal(str(paid_amount))
        except Exception:
            paid_amount_decimal = Decimal("0")

        if paid_amount_decimal > 0:
            if not payment_method:
                raise PosCheckoutError(gettext("يرجى اختيار طريقة الدفع."), 400)
            payment_data = {
                "amount": float(paid_amount_decimal),
                "payment_method": payment_method,
                "currency": payment_currency,
                "exchange_rate": float(payment_exchange_rate),
                "reference_number": reference_number,
            }

        payments_data = None
        if payload.get("payments") is not None:
            payments_data, tenders_error = _parse_split_tenders(
                payload.get("payments"),
                payment_currency,
                payment_exchange_rate,
            )
            if tenders_error:
                raise PosCheckoutError(tenders_error, 400)
            payment_data = None

        if payments_data and len(payments_data) > 1 and not multi_tender_allowed:
            raise PosCheckoutError(
                gettext('ميزة "pos_multi_tender" غير مفعلة لخطة اشتراكك الحالية.'),
                403,
                {"feature": "pos_multi_tender"},
            )

        notes = (payload.get("notes") or "").strip() or None
        if payload.get("qa_marker"):
            tag = f"{POS_QA_MARKER}"
            notes = f"{tag} {notes}".strip() if notes else tag

        override_supervisor_id = None
        if discount_requested:
            override_supervisor_id = PosOverrideService.require_permission_or_override(
                user=user,
                action="discount_override",
                override_token=payload.get("override_token"),
            )

        sale = SaleService.create_sale(
            customer=customer,
            seller=user,
            lines_data=lines_data,
            warehouse_id=warehouse_id,
            currency=currency,
            user_exchange_rate=exchange_rate,
            discount_amount=payload.get("discount_amount", 0) or 0,
            shipping_cost=payload.get("shipping_cost", 0) or 0,
            tax_rate=payload.get("tax_rate", 0) or 0,
            notes=notes,
            payment_data=payment_data,
            payments_data=payments_data,
            promotion_evaluation=promotion_evaluation,
        )

        order_type = (payload.get("order_type") or "").strip()
        ot = PosOrderType.get_by_code(tenant_id, order_type, active_only=True) if order_type else None
        if not ot:
            ot = PosOrderType.default_for_tenant(tenant_id)
            order_type = ot.code if ot else ""
        sale.order_type = order_type

        table_id_raw = payload.get("table_id")
        if table_id_raw:
            try:
                from models import PosTable
                from utils.tenanting import tenant_query

                _table = tenant_query(PosTable).filter_by(id=int(table_id_raw), is_active=True).first()
                sale.table_id = _table.id if _table else None
            except (ValueError, TypeError):
                sale.table_id = None

        sale.pos_session_id = session.id
        db.session.add(sale)
        session.total_sales = Decimal(str(session.total_sales or 0)) + Decimal(str(sale.total_amount or 0))
        if payment_data and payment_data.get("payment_method") == "cash":
            session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + convert_and_quantize_aed(
                payment_data.get("amount", 0),
                payment_currency,
                payment_exchange_rate,
                tenant_id=tenant_id,
            )
        if payments_data:
            for tender_chunk in payments_data:
                _accumulate_session_tender(session, tender_chunk, tenant_id)

        change_due = _compute_change_due(
            sale,
            payments_data,
            payment_data,
            payment_currency,
            payment_exchange_rate,
            tenant_id,
        )
        if change_due > Decimal("0"):
            session.total_change_given = safe_decimal(session.total_change_given) + change_due
            if shift is not None:
                shift.total_change_given = safe_decimal(getattr(shift, "total_change_given", None)) + change_due

        if override_supervisor_id is not None:
            LoggingCore.log_audit(
                "pos_discount_override",
                "pos",
                sale.id,
                {
                    "sale_number": sale.sale_number,
                    "cashier_user_id": user.id,
                    "supervisor_user_id": override_supervisor_id,
                },
                severity="medium",
            )

        db.session.add(session)
        log_mutation(
            "create",
            "Sale",
            sale.id,
            {
                "sale_number": sale.sale_number,
                "source": "pos",
                "amount": float(sale.total_amount or 0),
            },
        )

        kds_order = None
        kds_enabled = bool(ot.kds_enabled) if ot else (order_type in ("dine_in", "takeaway", "delivery"))
        if kds_enabled:
            kds_order = PosWriteService.create_kds_order(
                tenant_id=sale.tenant_id,
                sale_id=sale.id,
                session_id=session.id,
                branch_id=branch_id or get_active_branch_id(user),
                order_number=sale.sale_number,
                items_json=json.dumps(
                    [
                        {
                            "name": getattr(ld["product"], "name_ar", None) or ld["product"].name,
                            "quantity": float(ld["quantity"]),
                            "unit_price": float(ld.get("unit_price") or 0),
                            "notes": ld.get("notes", ""),
                        }
                        for ld in lines_data
                    ]
                ),
            )

        promo_json = _promotion_evaluation_json(promotion_evaluation)
        payment_status = getattr(sale, "payment_status", None)
        response = {
            "success": True,
            "sale_id": sale.id,
            "sale_number": sale.sale_number,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "view_url": f"/sales/{sale.id}",
            "print_url": f"/sales/{sale.id}/print",
            "promotion_discount": promo_json["total_discount"],
            "promotions_applied": promo_json["applied_rules"],
            "upsell_prompts": promo_json["upsell_prompts"],
            "payment_status": payment_status if isinstance(payment_status, str) else None,
            "change_due": float(change_due),
            "order_type": order_type,
            "tenant_id": sale.tenant_id,
        }
        if payments_data:
            response["tenders"] = [
                {
                    "method": tender_chunk["payment_method"],
                    "amount": float(tender_chunk["amount"]),
                    "currency": tender_chunk["currency"],
                }
                for tender_chunk in payments_data
            ]

        return response, kds_order
