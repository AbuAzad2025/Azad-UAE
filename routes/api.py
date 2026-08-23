import os
from datetime import UTC, datetime
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, make_response, request
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import csrf, db, limiter
from models import Customer, Product, Supplier
from services.logging_core import LoggingCore
from services.payment_service import PaymentService
from services.platform_query_service import PlatformQueryService
from services.stock_service import StockService
from utils.api_response import error_response, success_response
from utils.branching import (
    get_accessible_warehouse_ids,
    get_accessible_warehouses,
    get_branch_stock_map,
)
from utils.decorators import branch_scope_id, permission_required
from utils.logger import log_event
from utils.tenanting import get_active_tenant_id

api_bp = Blueprint("api", __name__, url_prefix="/api")

_DEV_TRUSTED_ORIGINS = frozenset(
    {
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:55014",
        "http://127.0.0.1:55014",
    }
)

_TELEMETRY_BATCH_MAX_EVENTS = 50
_TELEMETRY_PAYLOAD_MAX_BYTES = 50 * 1024
_TELEMETRY_MAX_BREADCRUMBS = 20
_FRONTEND_TELEMETRY_CATEGORIES = frozenset({"SOFTWARE_EXCEPTION", "HARDWARE_WARN"})
_FRONTEND_TELEMETRY_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _is_production_env() -> bool:
    app_env = (current_app.config.get("APP_ENV") or os.environ.get("APP_ENV") or "production").strip().lower()
    debug = bool(current_app.config.get("DEBUG")) or (os.environ.get("DEBUG") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
    )
    return app_env == "production" and not debug


def _origin_from_referer(referer: str) -> str | None:
    try:
        parsed = urlparse(referer or "")
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    except (TypeError, ValueError):
        return None
    return None


def _split_origins(value) -> set[str]:
    if not value:
        return set()
    raw_items = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    return {str(item).strip().rstrip("/") for item in raw_items if str(item).strip()}


def _trusted_telemetry_origins() -> frozenset[str]:
    origins: set[str] = set()
    for key in (
        "CLIENT_ERROR_TRUSTED_ORIGINS",
        "TRUSTED_ORIGINS",
        "CORS_ORIGINS",
        "PAYMENT_VAULT_TRUSTED_ORIGINS",
    ):
        origins.update(_split_origins(current_app.config.get(key) or os.environ.get(key)))
    if origins:
        return frozenset(origins)
    if _is_production_env():
        base = (current_app.config.get("BASE_URL") or os.environ.get("BASE_URL") or "").strip().rstrip("/")
        return frozenset({base}) if base else frozenset()
    return _DEV_TRUSTED_ORIGINS


def _validate_public_telemetry_origin():
    """Protect the public JS-error collector from cross-site log spam."""
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    referer = (request.headers.get("Referer") or "").strip()

    # Native clients / local curl in development often omit Origin/Referer.
    if not _is_production_env() and not origin and not referer:
        return None

    trusted = _trusted_telemetry_origins()
    if not trusted:
        current_app.logger.warning("client_error telemetry rejected: no trusted origins configured")
        return error_response("Origin policy not configured", status_code=503)

    if origin:
        if origin in trusted:
            return None
        current_app.logger.warning("client_error telemetry rejected: origin=%s", origin[:120])
        return error_response(gettext("Origin غير مسموح"), status_code=403)

    if referer:
        ref_origin = _origin_from_referer(referer)
        if ref_origin and ref_origin in trusted:
            return None
        current_app.logger.warning("client_error telemetry rejected: referer=%s", referer[:120])
        return error_response(gettext("Referer غير مسموح"), status_code=403)

    return error_response(gettext("Origin أو Referer مطلوب"), status_code=403)


def _scoped_customer_query():
    return PlatformQueryService.scoped_customers_query(current_user)


def _scoped_supplier_query():
    return PlatformQueryService.scoped_suppliers_query(current_user)


def _customer_balance(customer_id):
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        return PlatformQueryService.customer_balance_unscoped(customer_id, current_user)
    return float(PaymentService.get_customer_balance_scoped(customer_id, branch_id=scoped_branch_id))


def _supplier_balance(supplier_id):
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        return PlatformQueryService.supplier_balance_unscoped(supplier_id, current_user)
    return float(PaymentService.get_supplier_balance_scoped(supplier_id, branch_id=scoped_branch_id))


@api_bp.route("/health")
def health():
    return success_response(data={"status": "ok", "message": "API is running"})


@api_bp.route("/version")
def version():
    return success_response(data={"version": "1.0.0", "name": "Warehouse & Sales Management System"})


@api_bp.route("/payment-fields/<payment_method>")
@login_required
def payment_fields(payment_method):
    fields = {
        "cash": {
            "fields": [],
            "ar_title": gettext("دفع نقدي"),
            "en_title": "Cash Payment",
        },
        "card": {
            "fields": [
                {
                    "name": "reference_number",
                    "type": "text",
                    "label_ar": gettext("رقم المعاملة"),
                    "label_en": "Transaction Number",
                    "required": False,
                },
                {
                    "name": "card_last4",
                    "type": "text",
                    "label_ar": gettext("آخر 4 أرقام البطاقة"),
                    "label_en": "Card Last 4 Digits",
                    "required": False,
                },
            ],
            "ar_title": gettext("دفع ببطاقة"),
            "en_title": "Card Payment",
        },
        "bank_transfer": {
            "fields": [
                {
                    "name": "reference_number",
                    "type": "text",
                    "label_ar": gettext("رقم الحوالة"),
                    "label_en": "Transfer Reference",
                    "required": True,
                },
                {
                    "name": "bank_name",
                    "type": "text",
                    "label_ar": gettext("اسم البنك"),
                    "label_en": "Bank Name",
                    "required": False,
                },
            ],
            "ar_title": gettext("تحويل بنكي"),
            "en_title": "Bank Transfer",
        },
        "cheque": {
            "fields": [
                {
                    "name": "cheque_number",
                    "type": "text",
                    "label_ar": gettext("رقم الشيك"),
                    "label_en": "Cheque Number",
                    "required": True,
                },
                {
                    "name": "cheque_date",
                    "type": "date",
                    "label_ar": gettext("تاريخ الاستحقاق"),
                    "label_en": "Due Date",
                    "required": True,
                },
                {
                    "name": "bank_name",
                    "type": "text",
                    "label_ar": gettext("اسم البنك"),
                    "label_en": "Bank Name",
                    "required": True,
                },
            ],
            "ar_title": gettext("دفع بشيك"),
            "en_title": "Cheque Payment",
        },
        "e_wallet": {
            "fields": [
                {
                    "name": "reference_number",
                    "type": "text",
                    "label_ar": gettext("رقم المعاملة"),
                    "label_en": "Transaction ID",
                    "required": True,
                },
                {
                    "name": "wallet_provider",
                    "type": "select",
                    "label_ar": gettext("المحفظة"),
                    "label_en": "Wallet Provider",
                    "required": False,
                    "options": [
                        {
                            "value": "apple_pay",
                            "label_ar": "Apple Pay",
                            "label_en": "Apple Pay",
                        },
                        {
                            "value": "google_pay",
                            "label_ar": "Google Pay",
                            "label_en": "Google Pay",
                        },
                        {
                            "value": "samsung_pay",
                            "label_ar": "Samsung Pay",
                            "label_en": "Samsung Pay",
                        },
                        {
                            "value": "other",
                            "label_ar": gettext("أخرى"),
                            "label_en": "Other",
                        },
                    ],
                },
            ],
            "ar_title": gettext("محفظة إلكترونية"),
            "en_title": "E-Wallet",
        },
    }

    return success_response(data=fields.get(payment_method, {"fields": []}))


@api_bp.route("/currency-rate/<from_currency>/<to_currency>")
@login_required
def currency_rate(from_currency, to_currency):
    from services.currency_service import CurrencyService

    try:
        details = CurrencyService.get_exchange_rate_details(from_currency, to_currency)
        payload = {
            "from": from_currency,
            "to": to_currency,
            "rate": float(details["rate"]),
            "source": details.get("source", "unknown"),
            "cached": bool(details.get("cached", False)),
            "age_seconds": int(details.get("age_seconds") or 0),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        body, code = success_response(data=payload)
        resp = make_response(body, code)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    except Exception:
        current_app.logger.exception("currency_rate failed from=%s to=%s", from_currency, to_currency)
        body, code = error_response(
            gettext("تعذر جلب سعر الصرف الآن. الرجاء المحاولة لاحقاً أو إدخال السعر يدوياً."),
            meta={"manual_input_required": True},
            status_code=400,
        )
        resp = make_response(body, code)
        resp.headers["Cache-Control"] = "no-store"
        return resp


@api_bp.route("/currencies")
@login_required
def currencies():
    from services.currency_service import CurrencyService

    codes = CurrencyService.get_supported_currencies()
    currency_items = [{"code": c, "label": CurrencyService.get_currency_label(c)} for c in codes]
    return success_response(
        data={
            "currencies": codes,
            "currency_items": currency_items,
            "common": list(CurrencyService.COMMON_CURRENCIES),
        }
    )


@api_bp.route("/search")
@login_required
@permission_required("view_reports")
def api_search():
    """
    🔍 API بحث موحد: زبائن، موردين، منتجات
    """
    query = request.args.get("q", "")
    search_type = request.args.get("type", "customers")
    page = request.args.get("page", 1, type=int)
    per_page = 20

    if search_type == "products":
        warehouse_id = request.args.get("warehouse_id", type=int)
        purpose = request.args.get("purpose", "").strip()
        warehouse_ids = [warehouse_id] if warehouse_id else get_accessible_warehouse_ids(current_user)
        products_query = PlatformQueryService.products_base_query(current_user, purpose)
        if query:
            products_query = products_query.filter(
                db.or_(
                    Product.name.ilike(f"%{query}%"),
                    Product.sku.ilike(f"%{query}%"),
                    Product.barcode.ilike(f"%{query}%"),
                )
            )
        products = products_query.order_by(Product.name).limit(per_page).all()
        stock_map = (
            get_branch_stock_map(
                product_ids=[p.id for p in products],
                warehouse_ids=warehouse_ids,
            )
            if warehouse_ids
            else {}
        )

        results = [
            {
                "id": p.id,
                "text": p.name,
                "name": p.name,
                "sku": p.sku,
                "current_stock": float(stock_map.get(p.id, p.current_stock or 0)),
                "default_price": float(p.regular_price or 0),
                "unit_price": float(p.regular_price or 0),
                "regular_price": float(p.regular_price or 0),
                "merchant_price": float(p.merchant_price) if p.merchant_price else None,
                "partner_price": float(p.partner_price) if p.partner_price else None,
                "cost_price": float(p.cost_price) if p.cost_price else 0,
                "unit": p.unit,
                "is_low_stock": p.is_low_stock(),
                "has_serial_number": getattr(p, "has_serial_number", False),
            }
            for p in products
        ]

        return success_response(data={"results": results, "has_more": len(results) >= per_page})

    elif search_type == "suppliers":
        base_query = _scoped_supplier_query().filter(Supplier.is_active).order_by(Supplier.name)

        if query:
            base_query = base_query.filter(
                db.or_(
                    Supplier.name.ilike(f"%{query}%"),
                    Supplier.company_name.ilike(f"%{query}%"),
                    Supplier.phone.ilike(f"%{query}%"),
                    Supplier.email.ilike(f"%{query}%"),
                )
            )

        offset = (page - 1) * per_page
        suppliers = base_query.limit(per_page + 1).offset(offset).all()
        has_more = len(suppliers) > per_page
        suppliers = suppliers[:per_page]

        results = [
            {
                "id": s.id,
                "text": gettext(
                    f"{s.name} {('- ' + s.company_name) if s.company_name else ''} - {s.phone or 'لا يوجد رقم'}"
                ),
                "name": s.name,
                "company_name": s.company_name,
                "phone": s.phone,
                "email": s.email,
                "supplier_type": s.supplier_type,
                "type_display": s.get_type_display(),
                "balance_aed": _supplier_balance(s.id),
                "rating": s.rating,
                "is_verified": s.is_verified,
            }
            for s in suppliers
        ]

        return success_response(data={"results": results, "has_more": has_more})

    else:
        base_query = _scoped_customer_query().filter(Customer.is_active).order_by(Customer.name)

        if query:
            base_query = base_query.filter(
                db.or_(
                    Customer.name.ilike(f"%{query}%"),
                    Customer.phone.ilike(f"%{query}%"),
                    Customer.email.ilike(f"%{query}%") if Customer.email else False,
                )
            )

        offset = (page - 1) * per_page
        customers = base_query.limit(per_page + 1).offset(offset).all()
        has_more = len(customers) > per_page
        customers = customers[:per_page]

        results = [
            {
                "id": c.id,
                "text": gettext(f"{c.name} - {c.phone or 'لا يوجد رقم'}"),
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "customer_type": c.customer_type,
                "balance_aed": _customer_balance(c.id),
            }
            for c in customers
        ]

        return success_response(data={"results": results, "has_more": has_more})


@api_bp.route("/check-username")
@login_required
def check_username():
    """التحقق من توفر اسم المستخدم"""
    username = request.args.get("username", "").strip()

    if not username or len(username) < 3:
        return success_response(data={"available": False, "error": gettext("اسم المستخدم قصير جداً")})

    import re

    if not re.match(r"^[a-zA-Z0-9_]{3,20}$", username):
        return success_response(data={"available": False, "error": gettext("استخدم حروف إنجليزية وأرقام و_ فقط")})

    existing = PlatformQueryService.find_existing_username(username, current_user)

    if existing:
        year = datetime.now().year
        suggestions = [f"{username}_{year}", f"{username}_2024", f"{username}_admin"]

        return success_response(
            data={
                "available": False,
                "message": gettext(f'اسم المستخدم "{username}" موجود مسبقاً'),
                "suggestions": suggestions,
            }
        )

    return success_response(data={"available": True, "message": gettext("اسم المستخدم متاح ✓")})


@api_bp.route("/products/low-stock")
@login_required
@permission_required("view_reports")
def products_low_stock():
    """API للمنتجات قليلة المخزون"""
    try:
        low_stock_products = StockService.get_low_stock_products(user=current_user)

        products_data = []
        for product in low_stock_products:
            products_data.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "sku": product.sku,
                    "current_stock": float(getattr(product, "visible_stock", product.current_stock or 0)),
                    "min_stock_alert": float(product.min_stock_alert or 0),
                    "needed": float(
                        (product.min_stock_alert or 0) - (getattr(product, "visible_stock", product.current_stock or 0))
                    ),
                }
            )

        return success_response(data={"products": products_data, "count": len(products_data)})

    except Exception:
        current_app.logger.exception("products_low_stock failed")
        return error_response(
            gettext("تعذر تحميل المنتجات قليلة المخزون حالياً"),
            status_code=500,
        )


@api_bp.route("/exchange-rates/display")
@login_required
def exchange_rates_display():
    """
    Display-only exchange rates for the navbar / fxModal.
    NEVER use these for accounting, invoicing, payments, or GL entries.
    Use /api/currency-rate/<from>/<to> for accounting rates.
    """
    from flask_login import current_user

    from services.exchange_rate_service import ExchangeRateService
    from utils.tenanting import get_active_tenant_id

    # Use tenant's base currency as the base for display
    tenant_id = get_active_tenant_id(current_user)
    base = PlatformQueryService.tenant_base_currency(tenant_id, request.args.get("base", "USD").upper())

    symbols_str = request.args.get("symbols", "")
    if symbols_str:
        symbols = tuple(s.strip().upper() for s in symbols_str.split(",") if s.strip())
    else:
        symbols = ExchangeRateService.DISPLAY_CURRENCIES

    # Ensure the tenant's base currency is included in symbols
    if base not in symbols:
        symbols = (base,) + symbols

    result = ExchangeRateService.get_online_rates_for_display(base=base, symbols=symbols)
    # Add tenant base currency info for the UI
    result["tenant_base_currency"] = base
    body, code = success_response(data=result)
    resp = make_response(body, code)
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@api_bp.route("/echo", methods=["PUT", "PATCH", "DELETE"])
@login_required
def echo():
    """Development-only HTTP method echo. Hidden in production."""
    if _is_production_env():
        abort(404)
    payload = request.get_json(silent=True) or {}
    return success_response(data=payload)


@api_bp.route("/log-client-error", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per minute")
def log_client_error():
    """Receive JS errors from the browser and store them via LoggingCore.

    Defenses:
    - Origin/Referer allowlist to prevent cross-site log spam.
    - Rate limit: 30/min per user/IP.
    - Payload capped at 50 KB (Nginx / WAF layer recommended for stricter limit).
    - Stack trace truncated by service layer.
    - Cookies / auth headers explicitly excluded from storage.
    """
    origin_error = _validate_public_telemetry_origin()
    if origin_error:
        return origin_error

    if request.content_length and request.content_length > 50 * 1024:
        return "", 413

    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "Unknown JS error"))[:2000]
    source_file = str(data.get("source", "frontend.unknown"))[:500]
    event_type = str(data.get("type", "runtime")).lower()[:40]
    allowed_types = {
        "runtime",
        "promise",
        "resource",
        "fetch",
        "fetch_slow",
        "ajax",
        "api",
        "api_slow",
        "concurrency",
        "longtask",
        "layout",
        "theme",
    }
    if event_type not in allowed_types:
        event_type = "runtime"
    lineno = data.get("lineno")
    colno = data.get("colno")
    stack = str(data.get("stack", "")) if data.get("stack") else None
    url = str(data.get("url", request.referrer or request.url))[:500]
    request_url = str(data.get("request_url", ""))[:500]
    status = data.get("status")
    method = str(data.get("method", ""))[:10]

    source = f"frontend.{event_type or 'runtime'}"
    level = (
        "WARNING"
        if event_type
        in {
            "resource",
            "fetch",
            "fetch_slow",
            "ajax",
            "api_slow",
            "concurrency",
            "longtask",
            "layout",
            "theme",
        }
        else "ERROR"
    )

    enriched_message = message
    if lineno:
        enriched_message += f" (line {lineno}, col {colno})"
    if status:
        enriched_message += f" [HTTP {status}]"

    # Build extra WITHOUT cookies, tokens, or auth headers
    extra = {
        "type": event_type,
        "source_file": source_file,
        "line": lineno,
        "column": colno,
        "request_url": request_url,
        "status": status,
        "method": method,
        "route": str(data.get("route", ""))[:300],
        "browser_time": str(data.get("browser_time", ""))[:80],
        "duration_ms": data.get("duration_ms"),
        "active_requests": data.get("active_requests"),
        "repeat_count": data.get("repeat_count"),
        "request_id": str(data.get("request_id", ""))[:80],
        "response_size": data.get("response_size"),
        "cls": data.get("cls"),
        "ui_mode": str(data.get("ui_mode", ""))[:40],
        "ui_variant": str(data.get("ui_variant", ""))[:40],
        "reason": str(data.get("reason", ""))[:120],
        "fingerprint_key": str(data.get("fingerprint_key", ""))[:300],
        "client": data.get("client") if isinstance(data.get("client"), dict) else {},
    }
    if getattr(current_user, "is_authenticated", False):
        extra["user_id"] = getattr(current_user, "id", None)
        extra["tenant_id"] = getattr(current_user, "tenant_id", None)

    LoggingCore.log_frontend_error(
        message=enriched_message,
        level=level,
        source=source,
        url=url,
        user_agent=request.headers.get("User-Agent", "")[:255],
        stack=stack,
        extra=extra,
    )
    return "", 204


def _sanitize_breadcrumbs(raw) -> list[dict]:
    """Keep only dict breadcrumbs; cap count, key count and string length."""
    crumbs: list[dict] = []
    if not isinstance(raw, list):
        return crumbs
    for crumb in raw[:_TELEMETRY_MAX_BREADCRUMBS]:
        if not isinstance(crumb, dict):
            continue
        clean: dict = {}
        for key, value in crumb.items():
            clean[str(key)[:40]] = str(value)[:300] if isinstance(value, str) else value
            if len(clean) >= 12:
                break
        crumbs.append(clean)
    return crumbs


@api_bp.route("/v1/telemetry/logs", methods=["POST"])
@csrf.exempt
@limiter.limit("60 per minute")
def ingest_telemetry_logs():
    """Batch ingest of frontend telemetry events into the JSONL sink (utils/logger).

    Contract: ``{"events": [{"category", "message", "level?", "url?", "stack?",
    "breadcrumbs?", "client_ts?", "extra?"}]}`` — up to 50 events / 50 KB.

    Defenses mirror ``log_client_error``: origin allowlist, rate limit, payload
    cap, and server-side tenant/user resolution. Client-supplied categories are
    restricted to SOFTWARE_EXCEPTION / HARDWARE_WARN — security and financial
    categories are server-only and are stripped (mapped to SOFTWARE_EXCEPTION).
    Bad client data yields 400/413, never 500.
    """
    origin_error = _validate_public_telemetry_origin()
    if origin_error:
        return origin_error

    if request.content_length and request.content_length > _TELEMETRY_PAYLOAD_MAX_BYTES:
        return "", 413

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("malformed payload", status_code=400)
    events = data.get("events")
    if not isinstance(events, list) or not events:
        return error_response("events must be a non-empty list", status_code=400)
    if len(events) > _TELEMETRY_BATCH_MAX_EVENTS:
        return error_response("batch too large (max 50)", status_code=400)

    tenant_id = get_active_tenant_id(current_user)
    user_id = getattr(current_user, "id", None) if getattr(current_user, "is_authenticated", False) else None

    accepted = 0
    for raw_event in events:
        if not isinstance(raw_event, dict):
            continue
        try:
            message = str(raw_event.get("message") or "").strip()[:2000]
            if not message:
                continue
            category = str(raw_event.get("category") or "").strip().upper()
            if category not in _FRONTEND_TELEMETRY_CATEGORIES:
                category = "SOFTWARE_EXCEPTION"
            level = str(raw_event.get("level") or "").strip().upper()
            if level not in _FRONTEND_TELEMETRY_LEVELS:
                level = "WARNING" if category == "HARDWARE_WARN" else "ERROR"
            client_extra = raw_event.get("extra") if isinstance(raw_event.get("extra"), dict) else {}
            log_event(
                category,
                message,
                level=level,
                tenant_id=tenant_id,
                user_id=user_id,
                source="frontend",
                url=str(raw_event.get("url") or "")[:500],
                stack=(str(raw_event.get("stack"))[:4000] if raw_event.get("stack") else None),
                breadcrumbs=_sanitize_breadcrumbs(raw_event.get("breadcrumbs")),
                client_ts=str(raw_event.get("client_ts") or "")[:80],
                client_extra=client_extra,
            )
            accepted += 1
        except Exception:
            # One poisoned event must not kill the batch — never 500 on client data.
            current_app.logger.warning("Dropped malformed client telemetry event", exc_info=True)
            continue

    return success_response(data={"accepted": accepted}, status_code=202)


@api_bp.route("/industry-fields")
@login_required
def industry_fields():
    industry_code = request.args.get("industry", "general")
    from services.industry_service import IndustryService

    fields = IndustryService.get_fields_for(industry_code)
    return success_response(
        data={
            "industry": industry_code,
            "fields": [
                {
                    "field_code": f.field_code,
                    "field_name_ar": f.field_name_ar,
                    "field_name_en": f.field_name_en,
                    "field_type": f.field_type,
                    "is_required": f.is_required,
                }
                for f in fields
            ],
        }
    )


def _query_accessible_warehouses():
    from models import Warehouse

    q = request.args.get("q", "").strip()
    whs = get_accessible_warehouses(current_user)
    if q:
        whs = whs.filter(Warehouse.name.ilike(f"%{q}%"))
    whs = whs.order_by(Warehouse.name).limit(20).all()
    return [{"id": w.id, "text": w.name, "name": w.name} for w in whs]


def _query_products(warehouse_id=None):
    q = request.args.get("q", "").strip()
    products = StockService.get_visible_products_query(current_user)
    if q:
        products = products.filter(
            db.or_(
                Product.name.ilike(f"%{q}%"),
                Product.sku.ilike(f"%{q}%"),
                Product.barcode.ilike(f"%{q}%"),
            )
        )
    products = products.order_by(Product.name).limit(20).all()
    warehouse_ids = [warehouse_id] if warehouse_id else get_accessible_warehouse_ids(current_user)
    stock_map = (
        get_branch_stock_map(
            product_ids=[p.id for p in products],
            warehouse_ids=warehouse_ids,
        )
        if warehouse_ids
        else {}
    )
    return [
        {
            "id": p.id,
            "text": f"{p.name} ({p.sku})" if p.sku else p.name,
            "name": p.name,
            "sku": p.sku,
            "price": float(p.regular_price or 0),
            "stock": float(stock_map.get(p.id, p.current_stock or 0)),
        }
        for p in products
    ]


@api_bp.route("/warehouses")
@login_required
def api_warehouses():
    return success_response(data={"results": _query_accessible_warehouses()})


@api_bp.route("/products")
@login_required
@permission_required("view_reports")
def api_products():
    wid = request.args.get("warehouse_id", type=int)
    return success_response(data={"results": _query_products(wid)})


@api_bp.route("/search_warehouses")
@login_required
def api_search_warehouses():
    return success_response(data={"results": _query_accessible_warehouses()})


@api_bp.route("/warehouses/<int:wid>/products")
@login_required
def api_warehouse_products(wid):
    """منتجات مستودع محدد (Select2)"""
    return success_response(data={"results": _query_products(wid)})


@api_bp.route("/products/<int:pid>/info")
@login_required
def api_product_info(pid):
    """معلومات منتج (سعر، مخزون)"""
    product = PlatformQueryService.product_for_info(pid, current_user)
    if not product:
        return error_response(gettext("المنتج غير موجود"), status_code=404)
    warehouse_id = request.args.get("warehouse_id", type=int)
    if warehouse_id:
        from utils.branching import ensure_warehouse_access

        try:
            ensure_warehouse_access(warehouse_id, user=current_user)
        except Exception:
            return error_response(
                gettext("غير مصرح بالوصول إلى المستودع"),
                status_code=403,
            )
    stock = float(product.current_stock or 0)
    if warehouse_id:
        stock_map = get_branch_stock_map(
            product_ids=[product.id],
            warehouse_ids=[warehouse_id],
        )
        stock = float(stock_map.get(product.id, stock))
    return success_response(
        data={
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "barcode": product.barcode,
            "price": float(product.regular_price or 0),
            "stock": stock,
            "unit": product.unit,
            "is_low_stock": stock <= float(product.min_stock_alert or 0),
        }
    )


@api_bp.route("/products/barcode/<code>")
@login_required
def api_product_by_barcode(code):
    """البحث عن منتج بواسطة الباركود"""
    product = PlatformQueryService.find_product_by_barcode(code, current_user)
    if not product:
        return error_response(
            gettext("لم يتم العثور على منتج بهذا الباركود"),
            status_code=404,
        )
    return success_response(
        data={
            "id": product.id,
            "name": product.name,
            "text": f"{product.name} ({product.sku})" if product.sku else product.name,
            "sku": product.sku,
        }
    )


@api_bp.route("/barcode/validate")
@login_required
def api_barcode_validate():
    """التحقق من صلاحية الباركود"""
    code = request.args.get("code", "").strip()
    if not code:
        return success_response(data={"valid": False, "exists": False, "normalized": ""})
    normalized = code
    exists = PlatformQueryService.find_product_by_barcode(code, current_user) is not None
    return success_response(
        data={
            "valid": not exists,
            "exists": exists,
            "normalized": normalized,
        }
    )
