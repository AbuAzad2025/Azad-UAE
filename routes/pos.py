from flask_babel import gettext
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    current_app,
    redirect,
    url_for,
    flash,
    abort,
)
from flask_login import current_user, login_required
from extensions import db
from models import Customer, PosSession, Product, PosOrderType
from models.enums import PermissionEnum
from models.pos_shift import PosShift
from models.system_settings import SystemSettings
from models.tenant import Tenant
from services.pos_cash_service import PosCashMovementService
from services.pos_override_service import PosOverrideError, PosOverrideService
from services.pos_rma_service import PosRmaService
from services.idempotency_service import (
    IdempotencyHashMismatchError,
    IdempotencyInFlightError,
    IdempotencyService,
    hash_request_payload,
)
from services.pricing_service import PricingService
from services.promotion_service import PromotionService
from services.pos_cart_service import PosCartConflictError, PosCartService
from services.sale_service import SaleService
from utils.branching import (
    ensure_warehouse_access,
    get_accessible_warehouses,
    get_active_branch_id,
)
from utils.decorators import permission_required
from utils.db_safety import atomic_transaction
from utils.helpers import generate_number
import queue as _queue
import os as _os
import requests
from utils.pos_helpers import (
    POS_QA_MARKER,
    compute_fast_cash_options,
    create_pos_session,
    close_pos_session,
    get_active_session,
    get_paused_session,
    get_pos_walkin_customer,
    lookup_pos_product_exact,
    merge_checkout_lines,
    payment_amount_base,
    require_active_session,
    safe_decimal,
    search_pos_products,
    serialize_pos_product,
)
from utils.pos_security import (
    OVERRIDE_TOKEN_TTL_SECONDS,
    can_view_pos_expected,
    issue_pos_session_token,
    sign_override_token,
    verify_pos_session_token,
)
from utils.pos_features import pos_feature_enabled
from sqlalchemy.exc import IntegrityError
from utils.structured_logging import log_mutation
from services.logging_core import LoggingCore
from utils.tenanting import tenant_get, tenant_query, get_active_tenant_id
from utils.currency_utils import context_aware_default_currency, convert_and_quantize_aed

pos_bp = Blueprint("pos", __name__, url_prefix="/pos")


def _pos_standard_price(product, customer_type, quantity):
    """Tier-aware standard POS price via PricingService, quantized to 0.001."""
    price = PricingService.get_price(product, customer_type, quantity)
    return Decimal(str(price)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _promotion_evaluation_json(evaluation):
    """Serialize PromotionService.evaluate_cart output for JSON responses."""
    if not evaluation:
        return {
            "lines": [],
            "subtotal_before": 0.0,
            "total_discount": 0.0,
            "subtotal_after": 0.0,
            "applied_rules": [],
            "upsell_prompts": [],
        }
    return {
        "lines": [
            {
                "product_id": line["product_id"],
                "quantity": float(line["quantity"]),
                "unit_price": float(line["unit_price"]),
                "original_total": float(line["original_total"]),
                "discount_amount": float(line["discount_amount"]),
                "adjusted_total": float(line["adjusted_total"]),
            }
            for line in evaluation["lines"]
        ],
        "subtotal_before": float(evaluation["subtotal_before"]),
        "total_discount": float(evaluation["total_discount"]),
        "subtotal_after": float(evaluation["subtotal_after"]),
        "applied_rules": [
            {
                "campaign_id": rule["campaign_id"],
                "name": rule["name"],
                "campaign_type": rule["campaign_type"],
                "discount_amount": float(rule["discount_amount"]),
            }
            for rule in evaluation["applied_rules"]
        ],
        "upsell_prompts": evaluation["upsell_prompts"],
    }


_TENDER_CASH_METHOD = "cash"
_TENDER_CARD_METHODS = ("card", "bank_transfer", "e_wallet")


def _parse_split_tenders(raw_payments, default_currency, default_rate):
    """Validate the Phase 2 ``payments`` array into tender chunk dicts.

    Returns ``(chunks, error_message)`` — exactly one of the two is set.
    Amounts stay ``Decimal``; conversion happens per chunk in SaleService.
    """
    if not isinstance(raw_payments, list) or not raw_payments:
        return None, gettext("قائمة الدفعات غير صالحة.")
    chunks = []
    for chunk in raw_payments:
        if not isinstance(chunk, dict):
            return None, gettext("بيانات الدفعة غير صالحة.")
        try:
            amount = Decimal(str(chunk.get("amount") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            return None, gettext("مبلغ الدفعة غير صالح.")
        if amount <= Decimal("0"):
            return None, gettext("مبلغ الدفعة يجب أن يكون أكبر من صفر.")
        method = (chunk.get("payment_method") or chunk.get("method") or "").strip()
        if not method:
            return None, gettext("يرجى اختيار طريقة الدفع لكل دفعة.")
        try:
            rate = Decimal(str(chunk.get("exchange_rate") or default_rate or "1"))
        except (InvalidOperation, TypeError, ValueError):
            return None, gettext("سعر الصرف غير صالح.")
        chunks.append(
            {
                "amount": amount,
                "payment_method": method,
                "currency": (chunk.get("currency") or default_currency).strip().upper(),
                "exchange_rate": rate,
                "reference_number": (chunk.get("reference_number") or "").strip() or None,
                "cheque_number": chunk.get("cheque_number"),
                "cheque_date": chunk.get("cheque_date"),
                "bank_name": chunk.get("bank_name"),
                "notes": chunk.get("notes"),
            }
        )
    return chunks, None


def _tender_chunk_aed(chunk, tenant_id):
    """Exact base-currency amount of a parsed tender chunk."""
    return convert_and_quantize_aed(
        chunk["amount"],
        chunk["currency"],
        chunk["exchange_rate"],
        tenant_id=tenant_id,
    )


def _accumulate_session_tender(session, chunk, tenant_id):
    """Accumulate per-tender session totals for a split-tender chunk."""
    method = chunk.get("payment_method")
    chunk_aed = _tender_chunk_aed(chunk, tenant_id)
    if method == _TENDER_CASH_METHOD:
        session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + chunk_aed
    elif method in _TENDER_CARD_METHODS:
        session.total_card_sales = Decimal(str(session.total_card_sales or 0)) + chunk_aed


def _compute_change_due(sale, payments_data, payment_data, payment_currency, payment_exchange_rate, tenant_id):
    """Cash change owed when the tender exceeds the invoice total.

    Reporting metadata only — the overpayment itself is still booked as
    customer prepayment credit by SaleService (unchanged behavior).
    """
    sale_total_aed = getattr(sale, "amount_aed", None)
    if not isinstance(sale_total_aed, Decimal):
        return Decimal("0")
    tendered_aed = Decimal("0")
    cash_tendered = False
    if payments_data:
        for chunk in payments_data:
            tendered_aed += _tender_chunk_aed(chunk, tenant_id)
            if chunk.get("payment_method") == _TENDER_CASH_METHOD:
                cash_tendered = True
    elif payment_data and payment_data.get("payment_method") == _TENDER_CASH_METHOD:
        cash_tendered = True
        tendered_aed = convert_and_quantize_aed(
            payment_data.get("amount", 0),
            payment_currency,
            payment_exchange_rate,
            tenant_id=tenant_id,
        )
    if not cash_tendered:
        return Decimal("0")
    return max(tendered_aed - sale_total_aed, Decimal("0"))


# ─── Phase 3 — session tokens, blind-close visibility, override plumbing ───


def _extract_session_token(payload=None):
    token = request.headers.get("X-POS-Session-Token")
    if not token and isinstance(payload, dict):
        token = payload.get("session_token")
    if not token:
        token = request.args.get("session_token")
    return token


def _require_session_token(session, payload=None):
    """403 when a terminal-bound session is mutated without its HMAC token.

    Sessions without a ``terminal_id`` are legacy/unbound and skip the check.
    """
    if not getattr(session, "terminal_id", None):
        return None
    token = _extract_session_token(payload)
    if not token or not verify_pos_session_token(session, token):
        return (
            jsonify({"success": False, "error": gettext("رمز أمان الجلسة غير صالح أو مفقود.")}),
            403,
        )
    return None


def _can_view_expected() -> bool:
    return can_view_pos_expected(current_user)


# ─── Phase 4 — SaaS sub-feature gating + offline-first idempotency ───


def _current_tenant():
    tid = get_active_tenant_id(current_user)
    if not tid:
        return None
    return db.session.get(Tenant, int(tid))


def _pos_feature_denied(feature: str):
    """Clean JSON 403 when the active tenant lacks a POS sub-feature.

    Resolution: explicit per-tenant column first; NULL inherits the plan
    default (basic = core checkout only, pro/enterprise = full POS surface).
    """
    tenant = _current_tenant()
    if tenant is None:
        return None
    if pos_feature_enabled(tenant, feature):
        return None
    return (
        jsonify(
            {
                "success": False,
                "error": gettext(f'ميزة "{feature}" غير مفعلة لخطة اشتراكك الحالية.'),
                "feature": feature,
            }
        ),
        403,
    )


def _extract_idempotency_key(payload=None):
    key = request.headers.get("Idempotency-Key")
    if not key and isinstance(payload, dict):
        key = payload.get("idempotency_key")
    return (key or "").strip() or None


def _idempotent_begin(endpoint: str, payload, key):
    """Begin an idempotent execution inside the caller's transaction.

    Returns ``(record, stored, error)`` — exactly one of the three is set:
    ``record`` to complete after the business write, ``stored`` as a replayed
    ``(body, status)`` response, or ``error`` as a ready ``(response, code)``.
    """
    tid = get_active_tenant_id(current_user)
    request_hash = hash_request_payload(
        {k: v for k, v in (payload or {}).items() if k != "idempotency_key"}
    )
    try:
        record, stored = IdempotencyService.begin(
            tenant_id=int(tid or 0),
            endpoint=endpoint,
            key=key,
            user_id=getattr(current_user, "id", None),
            request_hash=request_hash,
        )
    except IdempotencyInFlightError:
        return None, None, (
            jsonify({"success": False, "error": gettext("طلب مكرر قيد المعالجة حالياً. أعد المحاولة بعد لحظات.")}),
            409,
        )
    except IdempotencyHashMismatchError:
        return None, None, (
            jsonify({"success": False, "error": gettext("مفتاح عدم التكرار استُخدم مع بيانات مختلفة.")}),
            422,
        )
    if stored is not None:
        body, status = stored
        return None, ({**body, "idempotent_replay": True}, status), None
    return record, None, None


def _idempotency_conflict_response():
    return (
        jsonify({"success": False, "error": gettext("طلب مكرر قيد المعالجة حالياً. أعد المحاولة بعد لحظات.")}),
        409,
    )


def _session_report_payload(session, include_sensitive: bool):
    """Blind-close serialization: expected/difference/tender totals are only
    present for roles with expected-balance visibility."""
    data = {
        "id": session.id,
        "number": session.session_number,
        "user_id": session.user_id,
        "branch_id": session.branch_id,
        "opened_at": session.opened_at.isoformat() if session.opened_at else None,
        "closed_at": (session.closed_at.isoformat() if session.closed_at else None),
        "opening_balance": float(session.opening_balance_cash or 0),
        "closing_balance": (
            float(session.closing_balance_cash or 0) if session.closing_balance_cash is not None else None
        ),
        "duration_minutes": session.duration_minutes,
        "status": session.status,
        "terminal_id": session.terminal_id,
        "notes": session.notes or "",
    }
    if include_sensitive:
        data.update(
            {
                "expected_balance": (
                    float(session.expected_balance or 0) if session.expected_balance is not None else None
                ),
                "difference": (float(session.difference or 0) if session.difference is not None else None),
                "total_sales": float(session.total_sales or 0),
                "total_cash_sales": float(session.total_cash_sales or 0),
                "total_card_sales": float(session.total_card_sales or 0),
                "total_change_given": float(session.total_change_given or 0),
                "total_cash_refunds": float(getattr(session, "total_cash_refunds", None) or 0),
                "total_pay_ins": float(session.total_pay_ins or 0),
                "total_pay_outs": float(session.total_pay_outs or 0),
            }
        )
    return data


def _get_closable_session(user):
    """Open session, falling back to the user's paused session (both closable)."""
    try:
        return require_active_session(user)
    except ValueError:
        return get_paused_session(user)


def _paused_session_error_response():
    return (
        jsonify(
            {
                "success": False,
                "error": gettext("الجلسة موقوفة مؤقتاً. يرجى استئناف الجلسة قبل المتابعة."),
            }
        ),
        409,
    )


def _pos_register_context():
    from utils.tax_settings import get_prices_include_vat
    from utils.currency_utils import resolve_default_currency
    from services.industry_service import get_pos_profile

    warehouses = [
        w for w in get_accessible_warehouses(current_user) if w.is_active and w.warehouse_type != w.TYPE_ONLINE
    ]
    tenant = Tenant.get_current()
    tenant_default_currency = resolve_default_currency(tenant) if tenant else "AED"
    branch_id = get_active_branch_id()
    return {
        "warehouses": warehouses,
        "tenant_default_currency": tenant_default_currency,
        "currency_symbol": tenant_default_currency or "AED",
        "prices_include_vat": get_prices_include_vat(
            tenant_id=get_active_tenant_id(current_user),
            branch_id=branch_id,
        ),
        "pos_config": (
            get_pos_profile(tenant)
            if tenant
            else {
                "business_type": "general",
                "mode": "retail",
                "enable_tables": False,
                "enable_hold": True,
                "enable_kds": True,
            }
        ),
    }


@pos_bp.before_request
def _require_pos_enabled():
    global_setting = SystemSettings.query.order_by(SystemSettings.id.desc()).first()
    if global_setting and not global_setting.enable_pos:
        if request.is_json or request.path.startswith("/pos/api/"):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": gettext("POS غير مفعل على مستوى النظام."),
                    }
                ),
                403,
            )
        return render_template("pos/disabled.html", reason="system"), 403
    tid = get_active_tenant_id(current_user)
    if tid:
        tenant = db.session.get(Tenant, tid)
        if tenant and not tenant.enable_pos:
            if request.is_json or request.path.startswith("/pos/api/"):
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": gettext("POS غير مفعل لهذه الشركة."),
                        }
                    ),
                    403,
                )
            return render_template("pos/disabled.html", reason="tenant"), 403
    return None


@pos_bp.route("/")
@login_required
@permission_required("manage_sales")
def index():
    return render_template("pos/index.html", **_pos_register_context())


@pos_bp.route("/grid")
@login_required
@permission_required("manage_sales")
def grid():
    return render_template("pos/grid.html", **_pos_register_context())


@pos_bp.route("/api/order-types")
@login_required
@permission_required("manage_sales")
def api_order_types():
    """Return the tenant's configured, active POS order types."""
    tid = get_active_tenant_id(current_user)
    if not tid:
        return jsonify({"success": False, "error": gettext("لا يوجد فرع/شركة نشطة")}), 400
    types = PosOrderType.for_tenant(tid, active_only=True)
    default = PosOrderType.default_for_tenant(tid)
    return jsonify(
        {
            "success": True,
            "order_types": [t.to_dict() for t in types],
            "default_code": default.code if default else None,
        }
    )


@pos_bp.route("/settings/order-types", methods=["GET", "POST"])
@login_required
@permission_required("manage_sales")
def order_type_settings():
    """Per-company configuration of POS order types (replaces hard-coded restaurant types)."""
    tid = get_active_tenant_id(current_user)
    if not tid:
        flash(gettext("لا يوجد فرع/شركة نشطة."), "warning")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        action = request.form.get("action") or ""
        try:
            with atomic_transaction("pos_order_type_settings"):
                if action == "create":
                    code = (request.form.get("code") or "").strip()
                    if not code:
                        raise ValueError(gettext("يرجى إدخال رمز النوع (code)."))
                    if PosOrderType.get_by_code(tid, code):
                        raise ValueError(gettext("رمز النوع موجود مسبقاً."))
                    db.session.add(
                        PosOrderType(
                            tenant_id=tid,
                            code=code,
                            name_ar=(request.form.get("name_ar") or "").strip() or code,
                            name_en=(request.form.get("name_en") or "").strip() or None,
                            is_active=request.form.get("is_active") == "on",
                            sort_order=int(request.form.get("sort_order") or 0),
                            is_default=request.form.get("is_default") == "on",
                            kds_enabled=request.form.get("kds_enabled") == "on",
                        )
                    )
                    flash(gettext("تمت إضافة نوع الطلب."), "success")
                elif action == "edit":
                    ot = db.session.get(PosOrderType, int(request.form.get("ot_id") or 0))
                    if not ot or ot.tenant_id != tid:
                        raise ValueError(gettext("نوع الطلب غير موجود."))
                    ot.name_ar = (request.form.get("name_ar") or "").strip() or ot.code
                    ot.name_en = (request.form.get("name_en") or "").strip() or None
                    ot.is_active = request.form.get("is_active") == "on"
                    ot.sort_order = int(request.form.get("sort_order") or 0)
                    ot.kds_enabled = request.form.get("kds_enabled") == "on"
                    ot.is_default = request.form.get("is_default") == "on"
                    flash(gettext("تم تحديث نوع الطلب."), "success")
                elif action == "toggle":
                    ot = db.session.get(PosOrderType, int(request.form.get("ot_id") or 0))
                    if not ot or ot.tenant_id != tid:
                        raise ValueError(gettext("نوع الطلب غير موجود."))
                    ot.is_active = not ot.is_active
                    flash(gettext("تم تحديث حالة نوع الطلب."), "success")
                elif action == "set_default":
                    ot = db.session.get(PosOrderType, int(request.form.get("ot_id") or 0))
                    if not ot or ot.tenant_id != tid:
                        raise ValueError(gettext("نوع الطلب غير موجود."))
                    for o in PosOrderType.for_tenant(tid, active_only=False):
                        o.is_default = o.id == ot.id
                    flash(gettext("تم تعيين النوع الافتراضي."), "success")
                elif action == "delete":
                    ot = db.session.get(PosOrderType, int(request.form.get("ot_id") or 0))
                    if not ot or ot.tenant_id != tid:
                        raise ValueError(gettext("نوع الطلب غير موجود."))
                    if ot.is_default:
                        raise ValueError(gettext("لا يمكن حذف النوع الافتراضي."))
                    db.session.delete(ot)
                    flash(gettext("تم حذف نوع الطلب."), "success")
                else:
                    raise ValueError(gettext("إجراء غير معروف."))
        except ValueError as exc:
            flash(str(exc), "warning")
        except Exception as exc:
            flash(gettext(f"خطأ: {exc}"), "danger")
        return redirect(url_for("pos.order_type_settings"))

    types = PosOrderType.for_tenant(tid, active_only=False)
    return render_template("pos/order_types.html", types=types)


@pos_bp.route("/api/categories")
@login_required
@permission_required("manage_sales")
def api_categories():
    from models import ProductCategory

    query = tenant_query(ProductCategory).filter_by(is_active=True)
    cats = query.order_by(ProductCategory.sort_order, ProductCategory.name).all()
    return jsonify([{"id": c.id, "name": c.name, "name_ar": c.name_ar} for c in cats])


@pos_bp.route("/api/products")
@login_required
@permission_required("manage_sales")
def api_products():
    q = (request.args.get("q") or "").strip()
    per_page = request.args.get("per_page", 20, type=int)
    warehouse_id = request.args.get("warehouse_id", type=int)
    category_id = request.args.get("category_id", type=int)

    products, stock_map, _ = search_pos_products(
        q,
        user=current_user,
        warehouse_id=warehouse_id,
        per_page=per_page,
        category_id=category_id,
    )
    results = [serialize_pos_product(p, stock_map, warehouse_id=warehouse_id) for p in products]
    return jsonify(results)


@pos_bp.route("/api/product")
@login_required
@permission_required("manage_sales")
def api_product_lookup():
    """Exact barcode/SKU lookup — JSON 404 when not found."""
    code = (request.args.get("code") or request.args.get("barcode") or "").strip()
    if not code:
        return jsonify({"success": False, "error": gettext("رمز المنتج مطلوب.")}), 400

    warehouse_id = request.args.get("warehouse_id", type=int)
    product, stock_map = lookup_pos_product_exact(
        code,
        user=current_user,
        warehouse_id=warehouse_id,
    )
    if not product:
        return jsonify({"success": False, "error": gettext("المنتج غير موجود.")}), 404

    payload = serialize_pos_product(product, stock_map, warehouse_id=warehouse_id)
    payload["success"] = True
    if not product.is_active:
        payload["warning"] = gettext("المنتج غير نشط.")
    elif payload.get("is_out_of_stock"):
        payload["warning"] = gettext("لا يوجد مخزون في المستودع المحدد.")
    return jsonify(payload)


@pos_bp.route("/api/customers")
@login_required
@permission_required("manage_sales")
def api_customers():
    q = (request.args.get("q") or "").strip()
    per_page = request.args.get("per_page", 20, type=int)
    per_page = max(1, min(per_page, 50))

    query = tenant_query(Customer).filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Customer.name.ilike(like),
                Customer.name_ar.ilike(like),
                Customer.phone.ilike(like),
            )
        )

    customers = query.order_by(Customer.name).limit(per_page).all()
    results = []
    for c in customers:
        phone = (c.phone or "").strip()
        label = c.name
        if phone:
            label = f"{label} - {phone}"
        results.append(
            {
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "customer_type": c.customer_type,
                "text": label,
            }
        )
    return jsonify(results)


@pos_bp.route("/api/walkin-customer")
@login_required
@permission_required("manage_sales")
def api_walkin_customer():
    """Quick / walk-in customer for POS (tenant-scoped)."""
    try:
        with atomic_transaction("pos_walkin_customer"):
            customer = get_pos_walkin_customer()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify(
        {
            "success": True,
            "id": customer.id,
            "name": customer.name,
            "text": customer.name,
            "customer_type": customer.customer_type,
            "is_walkin": True,
        }
    )


@pos_bp.route("/api/checkout", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_checkout():
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True) or {}

    session = get_active_session(current_user)
    if not session:
        if get_paused_session(current_user):
            return _paused_session_error_response()
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً."),
                }
            ),
            403,
        )

    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error

    idempotency_key = _extract_idempotency_key(payload)

    shift = _get_active_shift(current_user)
    # Phase 4 — shifts are a pro-tier sub-feature. On the basic tier the POS
    # runs shiftless: core checkout stays available without an open shift.
    if not shift and _pos_feature_denied("pos_shifts") is None:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("لا توجد وردية مفتوحة. يرجى فتح وردية أولاً."),
                }
            ),
            403,
        )

    use_quick = bool(payload.get("quick_customer") or payload.get("walkin"))
    customer_id = payload.get("customer_id")

    if use_quick or not customer_id:
        try:
            customer = get_pos_walkin_customer()
        except ValueError:
            return jsonify({"success": False, "error": gettext("بيانات العميل غير صالحة.")}), 400
    else:
        customer = tenant_get(Customer, int(customer_id or 0))
        if not customer or not customer.is_active:
            return (
                jsonify({"success": False, "error": gettext("العميل غير صالح أو غير نشط.")}),
                400,
            )

    warehouse_id = payload.get("warehouse_id")
    if warehouse_id:
        try:
            warehouse = ensure_warehouse_access(int(warehouse_id or 0), user=current_user)
            warehouse_id = warehouse.id
        except ValueError:
            return (
                jsonify({"success": False, "error": gettext("بيانات المستودع غير صالحة.")}),
                400,
            )
    else:
        warehouse_id = None

    currency = (payload.get("currency") or context_aware_default_currency()).strip().upper()
    exchange_rate = payload.get("exchange_rate", 1.0)

    lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines:
        return jsonify({"success": False, "error": gettext("يرجى إضافة منتجات للسلة.")}), 400

    try:
        merged = merge_checkout_lines(lines)
    except ValueError:
        return jsonify({"success": False, "error": gettext("بيانات السلة غير صالحة.")}), 400

    # Phase 3 — manual discounts (header discount_amount or any line
    # discount_percent) are gated: the acting cashier needs
    # pos_discount_override or a one-time supervisor override token.
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
        tid = get_active_tenant_id(current_user)
        locked = {
            p.id: p
            for p in db.session.query(Product)
            .filter(Product.id.in_(product_ids), Product.tenant_id == tid)
            .with_for_update()
            .all()
        }
    else:
        locked = {}

    for row in merged:
        product = locked.get(int(row["product_id"]))
        if not product or not product.is_active:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": gettext("يوجد منتج غير صالح داخل السلة."),
                    }
                ),
                400,
            )

        if getattr(product, "has_serial_number", False):
            serials = row.get("serials") or payload.get("serials", {}).get(str(product.id)) or []
            clean_serials = [s.strip() for s in serials if s and s.strip()]
            expected_qty = int(row["quantity"])
            if len(clean_serials) != expected_qty:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": gettext(
                                f'⚠️ المنتج "{product.name}" يتطلب {expected_qty} أرقاماً تسلسلية، ولكن تم إدخال {len(clean_serials)} فقط.'
                            ),
                        }
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
            if not current_user.has_permission(PermissionEnum.OVERRIDE_SALE_PRICE) and not current_user.is_owner:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": gettext(
                                f'⚠️ ليس لديك صلاحية تغيير سعر المنتج "{product.name}".\nالسعر القياسي: {float(standard_price)}'
                            ),
                        }
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
                    "user_id": current_user.id,
                },
            )

    # Phase 1 — evaluate automatic promotions on the merged, tier-priced cart.
    # A promotion engine failure must never block a sale; log and continue.
    # Phase 4 — promotions are a pro-tier sub-feature; on the basic tier the
    # cart checks out at tier prices with no automatic discounts.
    promotion_evaluation = None
    if _pos_feature_denied("pos_promotions") is None:
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
                tenant_id=get_active_tenant_id(current_user),
                branch_id=get_active_branch_id(current_user),
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
            return jsonify({"success": False, "error": gettext("يرجى اختيار طريقة الدفع.")}), 400
        payment_data = {
            "amount": float(paid_amount_decimal),
            "payment_method": payment_method,
            "currency": payment_currency,
            "exchange_rate": float(payment_exchange_rate),
            "reference_number": reference_number,
        }

    # Phase 2 — split tenders. A non-null `payments` array takes precedence
    # over the legacy single-payment fields and replaces them entirely.
    payments_data = None
    if payload.get("payments") is not None:
        payments_data, tenders_error = _parse_split_tenders(
            payload.get("payments"),
            payment_currency,
            payment_exchange_rate,
        )
        if tenders_error:
            return jsonify({"success": False, "error": tenders_error}), 400
        payment_data = None

    # Phase 4 — true split tenders (more than one chunk) are a pro-tier
    # sub-feature. A single-chunk payments array is just a typed single
    # payment and stays available on the basic tier.
    if payments_data and len(payments_data) > 1:
        multi_tender_denied = _pos_feature_denied("pos_multi_tender")
        if multi_tender_denied:
            return multi_tender_denied

    notes = (payload.get("notes") or "").strip() or None
    if payload.get("qa_marker"):
        tag = f"{POS_QA_MARKER}"
        notes = f"{tag} {notes}".strip() if notes else tag

    change_due = Decimal("0")
    response = None
    try:
        with atomic_transaction("pos_checkout_flow"):
            # Phase 4 — offline-first idempotency. The ledger row is created
            # inside THIS transaction: a rollback (any failure below) removes
            # it, so only a committed sale completes the key.
            idem_record = None
            if idempotency_key:
                idem_record, idem_stored, idem_error = _idempotent_begin(
                    "pos.checkout", payload, idempotency_key
                )
                if idem_error:
                    return idem_error
                if idem_stored is not None:
                    stored_body, stored_status = idem_stored
                    return jsonify(stored_body), stored_status

            override_supervisor_id = None
            if discount_requested:
                override_supervisor_id = PosOverrideService.require_permission_or_override(
                    user=current_user,
                    action="discount_override",
                    override_token=payload.get("override_token"),
                )
            sale = SaleService.create_sale(
                customer=customer,
                seller=current_user,
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
            # Resolve the configured order type (legacy fallback preserved).
            tid = get_active_tenant_id(current_user)
            order_type = (payload.get("order_type") or "").strip()
            ot = PosOrderType.get_by_code(tid, order_type, active_only=True) if order_type else None
            if not ot:
                ot = PosOrderType.default_for_tenant(tid)
                order_type = ot.code if ot else ""
            sale.order_type = order_type
            sale.pos_session_id = session.id
            db.session.add(sale)
            session.total_sales = Decimal(str(session.total_sales or 0)) + Decimal(str(sale.total_amount or 0))
            if payment_data and payment_data.get("payment_method") == "cash":
                session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + convert_and_quantize_aed(
                    payment_data.get("amount", 0),
                    payment_currency,
                    payment_exchange_rate,
                    tenant_id=tid,
                )
            if payments_data:
                for tender_chunk in payments_data:
                    _accumulate_session_tender(session, tender_chunk, tid)
            change_due = _compute_change_due(
                sale,
                payments_data,
                payment_data,
                payment_currency,
                payment_exchange_rate,
                tid,
            )
            if change_due > Decimal("0"):
                # Drawer math: gross tender is booked above; the change handed
                # back is tracked so expected = tender − change.
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
                        "cashier_user_id": current_user.id,
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

            kds_enabled = bool(ot.kds_enabled) if ot else (order_type in ("dine_in", "takeaway", "delivery"))
            if kds_enabled:
                from models import PosKdsOrder

                kds_order = PosKdsOrder(
                    tenant_id=sale.tenant_id,
                    sale_id=sale.id,
                    session_id=session.id,
                    branch_id=get_active_branch_id(),
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
                    status="pending",
                )
                db.session.add(kds_order)

            # Build the response INSIDE the transaction so the idempotency
            # ledger stores exactly what the client received for this sale.
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
            if idem_record is not None:
                IdempotencyService.complete(idem_record, response, 200)
    except PosOverrideError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except IntegrityError:
        # Concurrent duplicate: the unique (tenant, endpoint, key) constraint
        # rejected our in-flight insert — the other request owns the key.
        if idempotency_key:
            return _idempotency_conflict_response()
        current_app.logger.error("POS checkout integrity error", exc_info=True)
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("فشل إنشاء الفاتورة. تحقق من البيانات وحاول مرة أخرى."),
                }
            ),
            500,
        )
    except Exception as exc:
        current_app.logger.error(f"POS checkout error: {exc}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("فشل إنشاء الفاتورة. تحقق من البيانات وحاول مرة أخرى."),
                }
            ),
            500,
        )

    if order_type in ("dine_in", "takeaway", "delivery"):
        _notify_kds(
            {
                "type": "new_order",
                "order_id": kds_order.id,
                "order_number": kds_order.order_number,
                "tenant_id": sale.tenant_id,
            },
            tenant_id=sale.tenant_id,
        )

    return jsonify(response)


@pos_bp.route("/api/promotions/evaluate", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_promotions_evaluate():
    """Preview automatic promotions for a cart (no sale is created).

    Returns the tier-priced cart with promotional discounts applied, the
    rules that fired, and upsell prompt metadata for the register UI.
    """
    promotions_denied = _pos_feature_denied("pos_promotions")
    if promotions_denied:
        return promotions_denied
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"success": False, "error": gettext("بيانات غير صالحة.")}), 400

    lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines:
        return jsonify({"success": False, "error": gettext("يرجى إضافة منتجات للسلة.")}), 400

    try:
        merged = merge_checkout_lines(lines)
    except ValueError:
        return jsonify({"success": False, "error": gettext("بيانات السلة غير صالحة.")}), 400

    customer_type = "regular"
    customer_id = payload.get("customer_id")
    if customer_id:
        customer = tenant_get(Customer, int(customer_id or 0), or_404=False)
        if customer and customer.is_active:
            customer_type = customer.customer_type or "regular"

    tid = get_active_tenant_id(current_user)
    product_ids = [int(r["product_id"]) for r in merged]
    products = {
        p.id: p
        for p in db.session.query(Product)
        .filter(Product.id.in_(product_ids), Product.tenant_id == tid)
        .all()
    }

    cart = []
    for row in merged:
        product = products.get(int(row["product_id"]))
        if not product or not product.is_active:
            return (
                jsonify({"success": False, "error": gettext("يوجد منتج غير صالح داخل السلة.")}),
                400,
            )
        if row["unit_price"] is not None:
            unit_price = Decimal(str(row["unit_price"])).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        else:
            unit_price = _pos_standard_price(product, customer_type, row["quantity"])
        cart.append(
            {
                "product_id": product.id,
                "quantity": row["quantity"],
                "unit_price": unit_price,
                "category_id": getattr(product, "category_id", None),
            }
        )

    try:
        evaluation = PromotionService.evaluate_cart(
            cart,
            tenant_id=tid,
            branch_id=get_active_branch_id(current_user),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, **_promotion_evaluation_json(evaluation)})


@pos_bp.route("/api/carts")
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_carts_list():
    """Lightweight parked-cart list for the cashier's open session.

    Summaries only (id/label/totals/item-count) — no payload bloat.
    """
    session = get_active_session(current_user)
    limit = request.args.get("limit", 25, type=int)
    carts = PosCartService.list_carts(user=current_user, session=session, limit=limit)
    return jsonify({"success": True, "carts": [c.to_summary_dict() for c in carts]})


@pos_bp.route("/api/carts/park", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_carts_park():
    """Park (create) or re-park (update) a server-side cart tab."""
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"success": False, "error": gettext("بيانات غير صالحة.")}), 400

    session = get_active_session(current_user)
    if not session:
        if get_paused_session(current_user):
            return _paused_session_error_response()
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً."),
                }
            ),
            403,
        )

    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error

    try:
        with atomic_transaction("pos_cart_park"):
            cart = PosCartService.park_cart(
                user=current_user,
                session=session,
                payload=payload.get("payload"),
                label=payload.get("label"),
                cart_id=payload.get("cart_id"),
            )
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "cart": cart.to_summary_dict()}), 201


@pos_bp.route("/api/carts/<int:cart_id>")
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_cart_retrieve(cart_id):
    """Resume a parked cart — atomic single-resume semantics (409 on double-resume)."""
    try:
        with atomic_transaction("pos_cart_resume"):
            cart = PosCartService.resume_cart(user=current_user, cart_id=cart_id)
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except PosCartConflictError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409

    return jsonify({"success": True, "cart": cart.to_detail_dict()})


@pos_bp.route("/api/carts/<int:cart_id>", methods=["DELETE"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_cart_delete(cart_id):
    try:
        with atomic_transaction("pos_cart_delete"):
            PosCartService.delete_cart(user=current_user, cart_id=cart_id)
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({"success": True})


@pos_bp.route("/api/fast-cash")
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_fast_cash():
    """Dynamic fast-cash keys for a cart total + precomputed change per key."""
    total_raw = (request.args.get("total") or "").strip()
    if not total_raw:
        return jsonify({"success": False, "error": gettext("الإجمالي مطلوب.")}), 400
    try:
        total = Decimal(total_raw)
    except InvalidOperation:
        return jsonify({"success": False, "error": gettext("الإجمالي غير صالح.")}), 400
    if total < 0:
        return jsonify({"success": False, "error": gettext("الإجمالي لا يمكن أن يكون سالباً.")}), 400

    currency = (request.args.get("currency") or "").strip().upper()
    if not currency:
        from utils.currency_utils import get_tenant_base_currency

        currency = get_tenant_base_currency(get_active_tenant_id(current_user))

    options = compute_fast_cash_options(total, currency=currency)
    return jsonify(
        {
            "success": True,
            "total": float(total),
            "currency": currency,
            "options": [
                {
                    "amount": float(option["amount"]),
                    "change": float(option["change"]),
                    "is_exact": option["is_exact"],
                }
                for option in options
            ],
        }
    )


@pos_bp.route("/api/session/current")
@login_required
@permission_required("manage_sales")
def api_session_current():
    session = get_active_session(current_user)
    if not session:
        return jsonify({"success": False, "session": None}), 200
    payload = {
        "id": session.id,
        "number": session.session_number,
        "opened_at": session.opened_at.isoformat(),
        "duration_minutes": session.duration_minutes,
        "opening_balance": float(session.opening_balance_cash or 0),
        "status": session.status,
        "terminal_id": session.terminal_id,
    }
    if _can_view_expected():
        payload.update(
            {
                "total_sales": float(session.total_sales or 0),
                "total_cash_sales": float(session.total_cash_sales or 0),
                "total_card_sales": float(session.total_card_sales or 0),
            }
        )
    return jsonify({"success": True, "session": payload})


@pos_bp.route("/api/session/open", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_session_open():
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True) or {}
    opening_balance = Decimal(payload.get("opening_balance", 0) or 0)
    notes = (payload.get("notes") or "").strip() or None
    terminal_id = (payload.get("terminal_id") or "").strip() or None

    existing = get_active_session(current_user)
    if existing:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext(f"توجد جلسة مفتوحة بالفعل: {existing.session_number}. يرجى إغلاقها أولاً."),
                }
            ),
            409,
        )

    branch_id = get_active_branch_id(current_user)
    if not branch_id:
        return (
            jsonify({"success": False, "error": gettext("لا يوجد فرع نشط. يرجى تحديد فرع.")}),
            400,
        )

    idempotency_key = _extract_idempotency_key(payload)
    try:
        with atomic_transaction("pos_session_open"):
            # Phase 4 — offline retry safety: replay the original open instead
            # of erroring on a duplicate key, 409 on an in-flight duplicate.
            idem_record = None
            if idempotency_key:
                idem_record, idem_stored, idem_error = _idempotent_begin(
                    "pos.session_open", payload, idempotency_key
                )
                if idem_error:
                    return idem_error
                if idem_stored is not None:
                    stored_body, stored_status = idem_stored
                    return jsonify(stored_body), stored_status
            session = create_pos_session(current_user, branch_id, opening_balance, notes, terminal_id=terminal_id)

            session_token = None
            if session.terminal_id:
                session_token = issue_pos_session_token(session.id, session.user_id, session.terminal_id)
            response = {
                "success": True,
                "session": {
                    "id": session.id,
                    "number": session.session_number,
                    "opened_at": session.opened_at.isoformat(),
                    "opening_balance": float(session.opening_balance_cash or 0),
                    "status": session.status,
                    "terminal_id": session.terminal_id,
                },
                "session_token": session_token,
            }
            if idem_record is not None:
                IdempotencyService.complete(idem_record, response, 201)
    except IntegrityError:
        if idempotency_key:
            return _idempotency_conflict_response()
        return jsonify({"success": False, "error": gettext("تعذر فتح الجلسة. حاول مرة أخرى.")}), 500
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify(response), 201


@pos_bp.route("/api/session/pause", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_session_pause():
    payload = request.get_json(silent=True) or {}
    session = get_active_session(current_user)
    if not session:
        return jsonify({"success": False, "error": gettext("لا توجد جلسة مفتوحة لإيقافها.")}), 404
    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error
    try:
        with atomic_transaction("pos_session_pause"):
            session.pause()
            db.session.flush()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, "session": {"id": session.id, "status": session.status}})


@pos_bp.route("/api/session/resume", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_session_resume():
    payload = request.get_json(silent=True) or {}
    session = get_paused_session(current_user)
    if not session:
        return jsonify({"success": False, "error": gettext("لا توجد جلسة موقوفة لاستئنافها.")}), 404
    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error
    try:
        with atomic_transaction("pos_session_resume"):
            session.resume()
            db.session.flush()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    session_token = None
    if session.terminal_id:
        session_token = issue_pos_session_token(session.id, session.user_id, session.terminal_id)
    return jsonify(
        {
            "success": True,
            "session": {"id": session.id, "status": session.status},
            "session_token": session_token,
        }
    )


@pos_bp.route("/api/session/close", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_session_close():
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True) or {}
    # Blind close: the cashier's physical count is mandatory. The legacy
    # ``closing_balance`` key is still accepted as an alias.
    counted_raw = payload.get("counted_cash", payload.get("closing_balance"))
    if counted_raw is None:
        return (
            jsonify({"success": False, "error": gettext("المبلغ المعدود (counted_cash) مطلوب لإغلاق الجلسة.")}),
            400,
        )
    try:
        closing_cash = Decimal(str(counted_raw or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"success": False, "error": gettext("المبلغ المعدود غير صالح.")}), 400
    notes = (payload.get("notes") or "").strip() or None

    session = _get_closable_session(current_user)
    if not session:
        return (
            jsonify({"success": False, "error": gettext("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً.")}),
            404,
        )

    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error

    idempotency_key = _extract_idempotency_key(payload)
    try:
        with atomic_transaction("pos_session_close"):
            idem_record = None
            if idempotency_key:
                idem_record, idem_stored, idem_error = _idempotent_begin(
                    "pos.session_close", payload, idempotency_key
                )
                if idem_error:
                    return idem_error
                if idem_stored is not None:
                    stored_body, stored_status = idem_stored
                    return jsonify(stored_body), stored_status
            close_pos_session(session, closing_cash, notes)
            response = {"success": True, "session": _session_report_payload(session, _can_view_expected())}
            if idem_record is not None:
                IdempotencyService.complete(idem_record, response, 200)
    except IntegrityError:
        if idempotency_key:
            return _idempotency_conflict_response()
        return jsonify({"success": False, "error": gettext("تعذر إغلاق الجلسة. حاول مرة أخرى.")}), 500
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify(response)


@pos_bp.route("/api/session/report")
@login_required
@permission_required("manage_sales")
def api_session_report():
    session_id = request.args.get("session_id", type=int)
    if session_id:
        session = tenant_get(PosSession, session_id)
        if not session:
            return jsonify({"success": False, "error": gettext("الجلسة غير موجودة.")}), 404
    else:
        session = get_active_session(current_user) or get_paused_session(current_user)
        if not session:
            return (
                jsonify(
                    {
                        "success": False,
                        "session": None,
                        "error": gettext("لا توجد جلسة مفتوحة."),
                    }
                ),
                200,
            )

    return jsonify({"success": True, "session": _session_report_payload(session, _can_view_expected())})


def _get_active_shift(user=None) -> PosShift | None:
    from utils.tenanting import get_active_tenant_id

    tid = get_active_tenant_id(current_user)
    if not tid:
        return None
    session = get_active_session(current_user)
    if not session:
        return None
    return (
        PosShift.query.filter(
            PosShift.tenant_id == int(tid),
            PosShift.session_id == session.id,
            PosShift.user_id == current_user.id,
            PosShift.status == PosShift.SHIFT_OPEN,
        )
        .order_by(PosShift.id.desc())
        .first()
    )


@pos_bp.route("/api/shift/current")
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_shift_current():
    shifts_denied = _pos_feature_denied("pos_shifts")
    if shifts_denied:
        return shifts_denied
    shift = _get_active_shift(current_user)
    if not shift:
        return jsonify({"success": False, "shift": None}), 200
    return jsonify({"success": True, "shift": shift.to_dict(include_sensitive=_can_view_expected())})


@pos_bp.route("/api/shift/open", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_shift_open():
    shifts_denied = _pos_feature_denied("pos_shifts")
    if shifts_denied:
        return shifts_denied
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True) or {}
    starting_cash = payload.get("starting_cash", 0) or 0

    session = get_active_session(current_user)
    if not session:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً."),
                }
            ),
            403,
        )

    existing = _get_active_shift(current_user)
    if existing:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext(f"يوجد وردية مفتوحة: {existing.shift_number}."),
                }
            ),
            409,
        )

    try:
        with atomic_transaction("pos_shift_open"):
            tid = get_active_tenant_id(current_user)
            number = generate_number(
                prefix="SHF",
                model=PosShift,
                field_name="shift_number",
                branch_code=session.branch_id,
                tenant_id=int(tid or 0),
            )
            shift = PosShift(
                tenant_id=int(tid or 0),
                session_id=session.id,
                user_id=current_user.id,
                shift_number=number,
                starting_cash=Decimal(str(starting_cash)),
                status=PosShift.SHIFT_OPEN,
            )
            db.session.add(shift)
            db.session.flush()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "shift": shift.to_dict(include_sensitive=_can_view_expected())}), 201


@pos_bp.route("/api/shift/reconcile", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_shift_reconcile():
    shifts_denied = _pos_feature_denied("pos_shifts")
    if shifts_denied:
        return shifts_denied
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True) or {}
    # Blind close: the cashier's physical count is mandatory — no silent zero.
    if payload.get("actual_cash") is None:
        return (
            jsonify({"success": False, "error": gettext("المبلغ المعدود (actual_cash) مطلوب لتسوية الوردية.")}),
            400,
        )
    try:
        actual_cash = Decimal(str(payload.get("actual_cash") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"success": False, "error": gettext("المبلغ المعدود غير صالح.")}), 400
    notes = (payload.get("notes") or "").strip() or None

    shift = _get_active_shift(current_user)
    if not shift:
        return jsonify({"success": False, "error": gettext("لا توجد وردية مفتوحة.")}), 404

    try:
        with atomic_transaction("pos_shift_reconcile"):
            _accumulate_shift_totals(shift)
            shift.reconcile(actual_cash, notes)
            db.session.flush()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "shift": shift.to_dict(include_sensitive=_can_view_expected())})


@pos_bp.route("/api/shift/close", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_shift_close():
    shifts_denied = _pos_feature_denied("pos_shifts")
    if shifts_denied:
        return shifts_denied
    shift = _get_active_shift(current_user)
    if not shift:
        return jsonify({"success": False, "error": gettext("لا توجد وردية مفتوحة.")}), 404

    if shift.status == PosShift.SHIFT_OPEN:
        return (
            jsonify({"success": False, "error": gettext("يرجى تسوية الوردية قبل إغلاقها.")}),
            400,
        )

    try:
        with atomic_transaction("pos_shift_close"):
            shift.close()
            db.session.flush()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "shift": shift.to_dict(include_sensitive=_can_view_expected())})


def _accumulate_shift_totals(shift: PosShift):
    """Recompute shift totals with per-payment base-currency conversion.

    Payment rows are capped at invoice totals (overpayment is an unlinked
    prepayment), so the cash figure is NET. It is grossed up by the shift's
    tracked ``total_change_given`` so ``reconcile()`` derives:
    expected = starting + gross tender − change + pay-ins − pay-outs.
    Pay-in/out totals are recomputed from PosCashMovement rows.

    NOTE: shift close posts NO GL — Cash Over/Short journals are posted at
    session close only (single posting level, no double-posting).
    """
    from models import PosCashMovement, Sale

    sales = Sale.query.filter(Sale.tenant_id == shift.tenant_id, Sale.pos_session_id == shift.session_id).all()
    total = Decimal("0")
    cash = Decimal("0")
    card = Decimal("0")
    for sale in sales:
        total += Decimal(str(sale.total_amount or 0))
        for payment in sale.payments:
            method = getattr(payment, "payment_method", "")
            amt = payment_amount_base(payment, tenant_id=shift.tenant_id)
            if method == "cash":
                cash += amt
            elif method in ("card", "bank_transfer", "e_wallet"):
                card += amt

    change_given = Decimal(str(shift.total_change_given or 0))
    pay_ins = Decimal("0")
    pay_outs = Decimal("0")
    movements = PosCashMovement.query.filter(
        PosCashMovement.tenant_id == shift.tenant_id,
        PosCashMovement.shift_id == shift.id,
    ).all()
    for movement in movements:
        amount = Decimal(str(movement.amount or 0))
        if movement.movement_type == PosCashMovement.TYPE_PAY_IN:
            pay_ins += amount
        elif movement.movement_type == PosCashMovement.TYPE_PAY_OUT:
            pay_outs += amount

    shift.total_sales = total
    shift.total_cash_sales = cash + change_given
    shift.total_card_sales = card
    shift.total_pay_ins = pay_ins
    shift.total_pay_outs = pay_outs


# ─── Phase 3 — manager overrides, drawer, cash movements ───


@pos_bp.route("/api/authorize-override", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_authorize_override():
    """Exchange a supervisor PIN for a short-lived, single-use override token."""
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"success": False, "error": gettext("بيانات غير صالحة.")}), 400
    pin = str(payload.get("pin") or "")
    action = (payload.get("action") or "").strip()

    session = get_active_session(current_user)
    try:
        with atomic_transaction("pos_authorize_override"):
            token_row = PosOverrideService.authorize_with_pin(
                pin=pin,
                action=action,
                cashier=current_user,
                session=session,
            )
            override_token = sign_override_token(token_row)
    except PosOverrideError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify(
        {
            "success": True,
            "override_token": override_token,
            "action": token_row.action,
            "expires_in": OVERRIDE_TOKEN_TTL_SECONDS,
        }
    )


@pos_bp.route("/api/supervisor-pin", methods=["POST"])
@login_required
@permission_required(PermissionEnum.POS_AUTHORIZE_OVERRIDE)
def api_supervisor_pin_set():
    """Set/rotate the current supervisor's own override PIN."""
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"success": False, "error": gettext("بيانات غير صالحة.")}), 400
    pin = str(payload.get("pin") or "").strip()
    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        return (
            jsonify({"success": False, "error": gettext("الرمز السري يجب أن يكون 4-8 أرقام.")}),
            400,
        )
    with atomic_transaction("pos_supervisor_pin_set"):
        current_user.set_supervisor_pin(pin)
        db.session.flush()
        LoggingCore.log_audit(
            "pos_supervisor_pin_set",
            "users",
            current_user.id,
            {"user_id": current_user.id},
            severity="medium",
        )
    return jsonify({"success": True})


@pos_bp.route("/api/drawer/open", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_drawer_open():
    """No-sale cash drawer open — always requires pos_no_sale_drawer or a
    supervisor override token, and is audit-logged with both actors."""
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True) or {}

    session = get_active_session(current_user)
    if not session:
        if get_paused_session(current_user):
            return _paused_session_error_response()
        return (
            jsonify({"success": False, "error": gettext("لا توجد جلسة كاشير مفتوحة.")}),
            403,
        )
    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error

    reason = (payload.get("reason") or "").strip()
    try:
        with atomic_transaction("pos_drawer_open"):
            supervisor_id = PosOverrideService.require_permission_or_override(
                user=current_user,
                action="no_sale_drawer",
                override_token=payload.get("override_token"),
            )
            LoggingCore.log_audit(
                "pos_no_sale_drawer",
                "pos",
                session.id,
                {
                    "session_id": session.id,
                    "reason": reason,
                    "cashier_user_id": current_user.id,
                    "supervisor_user_id": supervisor_id,
                },
                severity="high",
            )
    except PosOverrideError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403

    # Best-effort hardware kick — a drawer hardware failure must not undo the
    # audit record, and must not leak internals to the client.
    drawer_kicked = False
    try:
        response = requests.post(f"{_HARDWARE_AGENT_URL}/drawer/open", json={"session_id": session.id}, timeout=2)
        drawer_kicked = response.status_code < 400
    except Exception:
        current_app.logger.warning("POS drawer hardware agent unreachable", exc_info=True)

    return jsonify({"success": True, "drawer_kicked": drawer_kicked})


@pos_bp.route("/api/cash-movements", methods=["GET"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_cash_movements_list():
    """Pay-in/out movements for the cashier's active session.

    A specific ``session_id`` may be listed only with expected-balance
    visibility (managers/owners) — it exposes drawer composition.
    """
    shifts_denied = _pos_feature_denied("pos_shifts")
    if shifts_denied:
        return shifts_denied
    session_id = request.args.get("session_id", type=int)
    if session_id:
        if not _can_view_expected():
            return jsonify({"success": False, "error": gettext("ليس لديك صلاحية عرض حركات هذه الجلسة.")}), 403
        session = tenant_get(PosSession, session_id)
        if not session:
            return jsonify({"success": False, "error": gettext("الجلسة غير موجودة.")}), 404
    else:
        session = get_active_session(current_user)
        if not session:
            return jsonify({"success": True, "movements": []})

    limit = request.args.get("limit", 100, type=int)
    movements = PosCashMovementService.list_movements(user=current_user, session=session, limit=limit)
    return jsonify({"success": True, "movements": [m.to_dict() for m in movements]})


@pos_bp.route("/api/cash-movements", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_cash_movement_create():
    """Create a pay-in / pay-out with immediate balanced GL posting.

    Pay-outs always require ``pos_pay_in_out`` or a supervisor override;
    pay-ins follow the same gate for drawer integrity.
    """
    shifts_denied = _pos_feature_denied("pos_shifts")
    if shifts_denied:
        return shifts_denied
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"success": False, "error": gettext("بيانات غير صالحة.")}), 400

    movement_type = (payload.get("type") or payload.get("movement_type") or "").strip()
    if movement_type not in ("pay_in", "pay_out"):
        return jsonify({"success": False, "error": gettext("نوع الحركة يجب أن يكون pay_in أو pay_out.")}), 400
    try:
        amount = Decimal(str(payload.get("amount") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"success": False, "error": gettext("مبلغ الحركة غير صالح.")}), 400
    reason = (payload.get("reason") or "").strip()

    session = get_active_session(current_user)
    if not session:
        if get_paused_session(current_user):
            return _paused_session_error_response()
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً."),
                }
            ),
            403,
        )
    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error

    shift = _get_active_shift(current_user)
    try:
        with atomic_transaction("pos_cash_movement"):
            supervisor_id = PosOverrideService.require_permission_or_override(
                user=current_user,
                action=movement_type,
                override_token=payload.get("override_token"),
            )
            movement = PosCashMovementService.create_movement(
                user=current_user,
                session=session,
                shift=shift,
                movement_type=movement_type,
                amount=amount,
                reason=reason,
                authorized_by_user_id=supervisor_id,
            )
    except PosOverrideError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "movement": movement.to_dict()}), 201


@pos_bp.route("/api/carts/<int:cart_id>/void-line", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_cart_void_line(cart_id):
    """Void a single line from a parked cart — requires pos_void_line or a
    supervisor override token; both actors are audit-logged."""
    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"success": False, "error": gettext("بيانات غير صالحة.")}), 400

    session = get_active_session(current_user)
    if not session:
        if get_paused_session(current_user):
            return _paused_session_error_response()
        return (
            jsonify({"success": False, "error": gettext("لا توجد جلسة كاشير مفتوحة.")}),
            403,
        )
    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error

    try:
        product_id = int(payload.get("product_id") or 0)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": gettext("معرف المنتج غير صالح.")}), 400
    if not product_id:
        return jsonify({"success": False, "error": gettext("معرف المنتج مطلوب.")}), 400

    try:
        with atomic_transaction("pos_void_line"):
            supervisor_id = PosOverrideService.require_permission_or_override(
                user=current_user,
                action="void_line",
                override_token=payload.get("override_token"),
            )
            cart = PosCartService.void_line(user=current_user, cart_id=cart_id, product_id=product_id)
            LoggingCore.log_audit(
                "pos_void_line",
                "pos_carts",
                cart.id,
                {
                    "cart_id": cart.id,
                    "product_id": product_id,
                    "session_id": session.id,
                    "cashier_user_id": current_user.id,
                    "supervisor_user_id": supervisor_id,
                },
                severity="high",
            )
    except PosOverrideError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except PosCartConflictError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "cart": cart.to_summary_dict()})


# ─── Phase 4 — omnichannel: receipt lookup, smart returns, cross-branch stock ───


@pos_bp.route("/api/receipts/lookup")
@login_required
@permission_required(PermissionEnum.POS_RETURN)
def api_receipt_lookup():
    """Exact receipt lookup for the POS returns screen.

    Tenant isolation is absolute and branch scope is enforced; a miss is a
    uniform 404 so cross-tenant probing is indistinguishable from a wrong
    number. The ``pos_return`` permission (not the HTML returns flow's
    own-sales rule) gates this endpoint.
    """
    returns_denied = _pos_feature_denied("pos_returns")
    if returns_denied:
        return returns_denied

    number = (request.args.get("number") or request.args.get("barcode") or "").strip()
    try:
        receipt = PosRmaService.lookup_receipt(current_user, number)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if receipt is None:
        return jsonify({"success": False, "error": gettext("الإيصال غير موجود.")}), 404
    return jsonify({"success": True, "receipt": receipt})


@pos_bp.route("/api/returns", methods=["POST"])
@login_required
@permission_required(PermissionEnum.POS_RETURN)
def api_pos_return_create():
    """Smart RMA at the register — wraps ReturnService.create_return.

    The reversal always uses the ORIGINAL sale's exchange rate and reverses
    promotional discounts proportionally (exact GL parity). ``refund_method``
    defaults to 'credit' (AR credit); 'cash' settles from the session drawer
    and decrements the expected drawer via ``total_cash_refunds``.
    """
    returns_denied = _pos_feature_denied("pos_returns")
    if returns_denied:
        return returns_denied

    if not request.is_json:
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("Content-Type يجب أن يكون application/json."),
                }
            ),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"success": False, "error": gettext("بيانات غير صالحة.")}), 400

    session = get_active_session(current_user)
    if not session:
        if get_paused_session(current_user):
            return _paused_session_error_response()
        return (
            jsonify(
                {
                    "success": False,
                    "error": gettext("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً."),
                }
            ),
            403,
        )
    token_error = _require_session_token(session, payload)
    if token_error:
        return token_error

    refund_method = (payload.get("refund_method") or "credit").strip().lower()
    return_lines = payload.get("lines") or []
    if not isinstance(return_lines, list) or not return_lines:
        return jsonify({"success": False, "error": gettext("يرجى تحديد أصناف المرتجع.")}), 400
    notes = (payload.get("notes") or "").strip() or None

    # Resolve OUTSIDE the transaction: a 404 here must not commit an
    # in-flight idempotency row that would poison the key for retries.
    sale_id = PosRmaService.resolve_sale_id(
        current_user,
        sale_id=payload.get("sale_id"),
        sale_number=payload.get("sale_number") or payload.get("receipt_number"),
    )
    if sale_id is None:
        return jsonify({"success": False, "error": gettext("الإيصال غير موجود.")}), 404

    idempotency_key = _extract_idempotency_key(payload)
    try:
        with atomic_transaction("pos_return_create"):
            idem_record = None
            if idempotency_key:
                idem_record, idem_stored, idem_error = _idempotent_begin(
                    "pos.return", payload, idempotency_key
                )
                if idem_error:
                    return idem_error
                if idem_stored is not None:
                    stored_body, stored_status = idem_stored
                    return jsonify(stored_body), stored_status

            product_return, refund_payment = PosRmaService.create_pos_return(
                user=current_user,
                session=session,
                shift=_get_active_shift(current_user),
                sale_id=sale_id,
                return_lines=return_lines,
                refund_method=refund_method,
                notes=notes,
            )
            log_mutation(
                "create",
                "ProductReturn",
                product_return.id,
                {
                    "return_number": product_return.return_number,
                    "sale_id": sale_id,
                    "source": "pos",
                    "refund_method": refund_method,
                    "amount": float(product_return.refund_amount or 0),
                },
            )
            response = {
                "success": True,
                "return_id": product_return.id,
                "return_number": product_return.return_number,
                "sale_id": sale_id,
                "refund_method": refund_method,
                "refund_amount": float(product_return.refund_amount or 0),
                "currency": product_return.currency,
                "exchange_rate": float(product_return.exchange_rate or 1),
                "amount_base": float(product_return.amount_aed or 0),
                "refund_payment_number": (
                    refund_payment.payment_number if refund_payment is not None else None
                ),
            }
            if idem_record is not None:
                IdempotencyService.complete(idem_record, response, 201)
    except IntegrityError:
        if idempotency_key:
            return _idempotency_conflict_response()
        current_app.logger.error("POS return integrity error", exc_info=True)
        return jsonify({"success": False, "error": gettext("فشل إنشاء المرتجع. حاول مرة أخرى.")}), 500
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"POS return error: {exc}")
        return jsonify({"success": False, "error": gettext("فشل إنشاء المرتجع. تحقق من البيانات وحاول مرة أخرى.")}), 500

    return jsonify(response), 201


@pos_bp.route("/api/stock/lookup")
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_stock_lookup():
    """Cross-branch stock visibility — per-warehouse on-hand breakdown across
    the tenant's accessible branches (single grouped aggregate, no N+1)."""
    product_id = request.args.get("product_id", type=int)
    barcode = (request.args.get("barcode") or request.args.get("sku") or "").strip() or None
    if not product_id and not barcode:
        return jsonify({"success": False, "error": gettext("معرف المنتج أو الباركود مطلوب.")}), 400
    try:
        result = PosRmaService.stock_breakdown(current_user, product_id=product_id, barcode=barcode)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": gettext("معرف المنتج غير صالح.")}), 400
    if result is None:
        return jsonify({"success": False, "error": gettext("المنتج غير موجود.")}), 404
    return jsonify({"success": True, **result})


_HARDWARE_AGENT_URL = _os.environ.get("POS_HARDWARE_AGENT_URL", "http://127.0.0.1:8567")
_KDS_SUBSCRIBERS: list[tuple[int | None, _queue.Queue]] = []


def _notify_kds(data, tenant_id: int | None = None):
    msg = f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    target_tid = tenant_id if tenant_id is not None else data.get("tenant_id")
    stale: list[tuple[int | None, _queue.Queue]] = []
    for sub_tid, q in _KDS_SUBSCRIBERS[:]:
        if target_tid is not None and sub_tid is not None and sub_tid != target_tid:
            continue
        try:
            q.put_nowait(msg)
        except Exception:
            stale.append((sub_tid, q))
    for entry in stale:
        if entry in _KDS_SUBSCRIBERS:
            _KDS_SUBSCRIBERS.remove(entry)


@pos_bp.route("/api/kds/stream")
@login_required
@permission_required("view_kds")
def kds_stream():
    subscriber_tid = get_active_tenant_id(current_user)

    def stream():
        q = _queue.Queue()
        _KDS_SUBSCRIBERS.append((subscriber_tid, q))
        try:
            while True:
                msg = q.get()
                yield msg
        except GeneratorExit:
            _KDS_SUBSCRIBERS[:] = [entry for entry in _KDS_SUBSCRIBERS if entry[1] is not q]

    return stream(), {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }


@pos_bp.route("/api/kds/orders")
@login_required
@permission_required("view_kds")
def kds_orders():
    from models import PosKdsOrder

    tid = get_active_tenant_id(current_user)
    orders = PosKdsOrder.query.filter_by(tenant_id=tid).order_by(PosKdsOrder.created_at.desc()).limit(50).all()
    return jsonify(
        [
            {
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "created_at": o.created_at.isoformat(),
                "items": json.loads(o.items_json),
            }
            for o in orders
        ]
    )


@pos_bp.route("/api/kds/orders/<int:order_id>/status", methods=["POST"])
@login_required
@permission_required("view_kds")
def kds_update_status(order_id):
    from models import PosKdsOrder
    from datetime import datetime, timezone

    tid = get_active_tenant_id(current_user)
    order = PosKdsOrder.query.filter_by(id=order_id, tenant_id=tid).first()
    if not order:
        return jsonify({"error": gettext("الطلب غير موجود")}), 404
    payload = request.get_json(silent=True) or {}
    new_status = payload.get("status", "")
    if new_status not in ("pending", "preparing", "ready", "served", "cancelled"):
        return jsonify({"error": gettext("حالة غير صالحة")}), 400
    with atomic_transaction("pos_kds_status"):
        order.status = new_status
        if new_status in ("served", "cancelled"):
            order.completed_at = datetime.now(timezone.utc)
        order.updated_at = datetime.now(timezone.utc)
    _notify_kds(
        {
            "type": "status_update",
            "order_id": order.id,
            "status": new_status,
            "tenant_id": tid,
        },
        tenant_id=tid,
    )
    return jsonify({"success": True})


@pos_bp.route("/kds")
@login_required
@permission_required("view_kds")
def kds_dashboard():
    return render_template("pos/kds.html")


@pos_bp.route("/api/customer-display/<int:session_id>/stream")
def customer_display_stream(session_id):
    display_tenant_id = request.args.get("tenant_id", type=int)

    def stream():
        last_status = None
        while True:
            if not display_tenant_id:
                yield f"data: {json.dumps({'type': 'closed'})}\n\n"
                break
            session = db.session.get(PosSession, session_id)
            if not session or session.tenant_id != display_tenant_id:
                yield f"data: {json.dumps({'type': 'closed'})}\n\n"
                break
            from models import Sale

            sales = (
                Sale.query.filter(
                    Sale.tenant_id == session.tenant_id,
                    Sale.pos_session_id == session_id,
                )
                .order_by(Sale.id.desc())
                .limit(5)
                .all()
            )
            if not sales:
                yield f"data: {json.dumps({'type': 'waiting'})}\n\n"
                import time

                time.sleep(3)
                continue
            latest = sales[0]
            from models import PosKdsOrder

            kds_order = PosKdsOrder.query.filter_by(
                sale_id=latest.id,
                tenant_id=session.tenant_id,
            ).first()
            status = kds_order.status if kds_order else "confirmed"
            if status != last_status:
                last_status = status
                items = []
                for line in latest.lines:
                    items.append(
                        {
                            "name": line.product.name_ar or line.product.name,
                            "quantity": float(line.quantity),
                            "total": float(line.line_total or 0),
                        }
                    )
                yield f"data: {json.dumps({'type': 'order_update', 'order_number': latest.sale_number, 'items': items, 'total': float(latest.total_amount or 0), 'status': status})}\n\n"
            import time

            time.sleep(3)

    return stream(), {"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}


@pos_bp.route("/customer-display")
def customer_display():
    return render_template("pos/customer_display.html")


@pos_bp.route("/receipt/<int:sale_id>")
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def thermal_receipt(sale_id):
    from models import Sale

    sale = tenant_get(Sale, sale_id)
    if not sale:
        abort(404)
    customer = sale.customer
    return render_template("pos/receipt.html", sale=sale, customer=customer)


@pos_bp.route("/api/hardware/print-receipt", methods=["POST"])
@login_required
@permission_required("manage_sales")
def hardware_print_receipt():
    """توجيه طباعة الفاتورة إلى وكيل الأجهزة المحلي"""
    try:
        body = request.get_data()
        resp = requests.post(
            f"{_HARDWARE_AGENT_URL}/print-receipt",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=10,
            verify=True,
        )
        result = resp.json()
        return jsonify(result), resp.status_code
    except requests.RequestException:
        return (
            jsonify({"error": gettext("وكيل الأجهزة غير متصل. تأكد من تشغيل pos_hardware_agent.py")}),
            503,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pos_bp.route("/api/hardware/open-drawer", methods=["POST"])
@login_required
@permission_required("manage_sales")
def hardware_open_drawer():
    """فتح درج النقود"""
    try:
        body = request.get_data()
        resp = requests.post(
            f"{_HARDWARE_AGENT_URL}/open-drawer",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=5,
            verify=True,
        )
        result = resp.json()
        return jsonify(result), resp.status_code
    except requests.RequestException:
        return jsonify({"error": gettext("وكيل الأجهزة غير متصل")}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pos_bp.route("/api/hardware/status")
@login_required
@permission_required("manage_sales")
def hardware_status():
    """حالة وكيل الأجهزة"""
    try:
        resp = requests.get(
            f"{_HARDWARE_AGENT_URL}/status",
            timeout=3,
            verify=True,
        )
        result = resp.json()
        return jsonify(result)
    except requests.RequestException:
        return jsonify({"status": "disconnected", "error": gettext("غير متصل")}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 200


@pos_bp.route("/api/floors")
@login_required
@permission_required("manage_sales")
def api_floors():
    from models import PosFloor

    tid = get_active_tenant_id(current_user)
    floors = PosFloor.query.filter_by(tenant_id=tid).order_by(PosFloor.sort_order).all()
    return jsonify(
        [
            {
                "id": f.id,
                "name": f.name_ar or f.name,
                "sort_order": f.sort_order,
                "table_count": f.tables.filter_by(is_active=True).count(),
            }
            for f in floors
        ]
    )


@pos_bp.route("/api/floors/create", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_floor_create():
    from models import PosFloor

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    name_ar = (payload.get("name_ar") or "").strip()
    if not name:
        return jsonify({"error": gettext("اسم الطابق مطلوب")}), 400
    tid = get_active_tenant_id(current_user)
    floor = PosFloor(tenant_id=tid, name=name, name_ar=name_ar or None)
    with atomic_transaction("pos_floor_create"):
        db.session.add(floor)
    return jsonify({"success": True, "floor_id": floor.id})


@pos_bp.route("/api/floors/<int:floor_id>/tables")
@login_required
@permission_required("manage_sales")
def api_floor_tables(floor_id):
    from models import PosFloor, PosTable

    tid = get_active_tenant_id(current_user)
    floor = PosFloor.query.filter_by(id=floor_id, tenant_id=tid).first()
    if not floor:
        return jsonify({"error": gettext("الطابق غير موجود")}), 404
    tables = PosTable.query.filter_by(floor_id=floor_id, is_active=True).order_by(PosTable.sort_order).all()
    return jsonify(
        [
            {
                "id": t.id,
                "label": t.label,
                "capacity": t.capacity,
                "pos_x": t.pos_x,
                "pos_y": t.pos_y,
                "shape": t.shape,
                "status": t.status,
            }
            for t in tables
        ]
    )


@pos_bp.route("/api/tables/create", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_table_create():
    from models import PosFloor, PosTable

    payload = request.get_json(silent=True) or {}
    floor_id = payload.get("floor_id")
    label = (payload.get("label") or "").strip()
    if not floor_id or not label:
        return jsonify({"error": gettext("الطابق والتسمية مطلوبان")}), 400
    tid = get_active_tenant_id(current_user)
    floor = PosFloor.query.filter_by(id=floor_id, tenant_id=tid).first()
    if not floor:
        return jsonify({"error": gettext("الطابق غير موجود")}), 404
    table = PosTable(
        tenant_id=tid,
        floor_id=floor_id,
        label=label,
        capacity=payload.get("capacity", 4),
        pos_x=payload.get("pos_x", 0),
        pos_y=payload.get("pos_y", 0),
        shape=payload.get("shape", "rectangle"),
    )
    with atomic_transaction("pos_table_create"):
        db.session.add(table)
    return jsonify({"success": True, "table_id": table.id})


@pos_bp.route("/api/tables/<int:table_id>/status", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_table_update_status(table_id):
    from models import PosTable

    tid = get_active_tenant_id(current_user)
    table = PosTable.query.filter_by(id=table_id, tenant_id=tid).first()
    if not table:
        return jsonify({"error": gettext("الطاولة غير موجودة")}), 404
    payload = request.get_json(silent=True) or {}
    new_status = payload.get("status", "")
    if new_status not in ("free", "occupied", "reserved"):
        return jsonify({"error": gettext("حالة غير صالحة")}), 400
    with atomic_transaction("pos_table_status"):
        table.status = new_status
    return jsonify({"success": True})


@pos_bp.route("/api/tables/<int:table_id>/assign", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_table_assign(table_id):
    from models import PosTable, PosTableOrder

    tid = get_active_tenant_id(current_user)
    table = PosTable.query.filter_by(id=table_id, tenant_id=tid).first()
    if not table:
        return jsonify({"error": gettext("الطاولة غير موجودة")}), 404
    payload = request.get_json(silent=True) or {}
    sale_id = payload.get("sale_id")
    if not sale_id:
        return jsonify({"error": gettext("رقم الفاتورة مطلوب")}), 400
    table.status = "occupied"
    torder = PosTableOrder(
        tenant_id=tid,
        table_id=table_id,
        sale_id=sale_id,
        guest_count=payload.get("guest_count", 1),
    )
    with atomic_transaction("pos_table_assign"):
        table.status = "occupied"
        db.session.add(torder)
    return jsonify({"success": True})
