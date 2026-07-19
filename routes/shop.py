from flask_babel import gettext
from decimal import Decimal


from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


from extensions import db, limiter

from models import Product, ProductCategory, Sale, Tenant
from models.sale import SaleLine

from models.shop_wishlist import ShopWishlist
from models.shop_review import ShopReview

from services.shop_customer_auth_service import ShopCustomerAuthService

from services.store_checkout_service import StoreCheckoutService

from services.store_order_service import StoreOrderService

from services.store_payment_method_service import StorePaymentMethodService

from services.store_service import StoreService

from utils.db_safety import atomic_transaction
from utils.shop_i18n import shop_lang, t
from utils.safe_redirect import is_safe_redirect_url, safe_redirect_target

shop_bp = Blueprint("shop", __name__, url_prefix="/s")


def _shop_redirect_after_login(next_url, store):
    if is_safe_redirect_url(next_url):
        return redirect(next_url)
    return redirect(url_for("shop.catalog", slug=store.store_slug))


def _resolve_store(slug):

    store = StoreService.get_store_by_slug(slug)

    if not store:
        abort(404)

    return store


def _closed_response(store, reason):
    # (tenant, lang, t, theme...). Build it so the page never 500s.
    ctx = _store_context(store)
    return render_template("shop/closed.html", reason=reason, **ctx), 503


def _require_open_store(store):

    if not StoreService.stores_globally_enabled():
        return _closed_response(store, "platform")

    if StoreService.is_platform_locked(store):
        return _closed_response(store, "platform")

    if not store.is_enabled:
        return _closed_response(store, "tenant")

    tenant = db.session.get(Tenant, store.tenant_id)

    if not tenant or not tenant.is_active or getattr(tenant, "is_suspended", False):
        return _closed_response(store, "tenant")

    return None


def _shop_account(store):

    return ShopCustomerAuthService.get_logged_in_account(store.tenant_id)


def _require_shop_account(store, ctx):

    account = ctx.get("shop_account") or _shop_account(store)

    if not account:
        flash(t("login_required", ctx.get("lang")), "warning")

        return None, redirect(
            url_for("shop.account_login", slug=store.store_slug, next=request.url)
        )

    return account, None


def _store_context(store):

    tenant = db.session.get(Tenant, store.tenant_id)

    lang = shop_lang()

    account = _shop_account(store)

    primary = (tenant.brand_color_primary if tenant else None) or "#1B7A4E"

    secondary = (tenant.brand_color_secondary if tenant else None) or "#CE1126"

    cart_count = int(sum(StoreService.get_cart(session, store.tenant_id).values()) or 0)

    return {
        "store": store,
        "tenant": tenant,
        "lang": lang,
        "is_rtl": lang == "ar",
        "t": lambda k: t(k, lang),
        "theme_primary": primary,
        "theme_secondary": secondary,
        "cart_count": cart_count,
        "shop_account": account,
        "is_shop_logged_in": account is not None,
        "analytics_id": current_app.config.get("ANALYTICS_GA_ID", ""),
    }


def _require_shop_customer(store, next_url=None):

    if _shop_account(store):
        return None

    flash(t("login_required", shop_lang()), "warning")

    return redirect(
        url_for(
            "shop.account_login", slug=store.store_slug, next=next_url or request.url
        )
    )


def _whatsapp_digits(store) -> str:

    import re

    wa = (store.whatsapp or store.phone or "").strip()

    return re.sub(r"\D", "", wa)


def _is_ajax():
    return (
        request.content_type and "application/json" in request.content_type
    ) or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _track_cart_activity(store, account, session):
    from models.shop_abandoned_cart import ShopAbandonedCart

    cart = StoreService.get_cart(session, store.tenant_id)
    if not cart:
        return
    import json

    cart_json = json.dumps(cart)
    email = account.email if account else None
    existing = ShopAbandonedCart.query.filter_by(
        tenant_id=store.tenant_id,
        account_id=account.id if account else None,
        recovered=False,
    ).first()
    if existing:
        existing.cart_data = cart_json
    else:
        ac = ShopAbandonedCart(
            tenant_id=store.tenant_id,
            account_id=account.id if account else None,
            email=email,
            cart_data=cart_json,
        )
        db.session.add(ac)
    db.session.flush()


@shop_bp.route("/<slug>/lang/<lang_code>")
def set_lang(slug, lang_code):

    store = _resolve_store(slug)

    session["shop_lang"] = "en" if str(lang_code).lower().startswith("en") else "ar"

    return redirect(
        safe_redirect_target(request.referrer, "shop.catalog", slug=store.store_slug)
    )


@shop_bp.route("/<slug>/offline")
def offline(slug):
    store = _resolve_store(slug)
    ctx = _store_context(store)
    return render_template("shop/offline.html", **ctx)


@shop_bp.route("/<slug>/wishlist/add/<int:product_id>", methods=["POST"])
@limiter.limit("30 per minute")
def wishlist_add(slug, product_id):
    store = _resolve_store(slug)
    account = _shop_account(store)
    if not account:
        return jsonify({"success": False, "message": "Login required"}), 401
    if request.content_type and "application/json" in request.content_type:
        existing = ShopWishlist.query.filter_by(
            account_id=account.id, product_id=product_id, tenant_id=store.tenant_id
        ).first()
        if not existing:
            with atomic_transaction("wishlist_add"):
                wl = ShopWishlist(
                    tenant_id=store.tenant_id,
                    account_id=account.id,
                    product_id=product_id,
                )
                db.session.add(wl)
        count = ShopWishlist.query.filter_by(
            account_id=account.id, tenant_id=store.tenant_id
        ).count()
        return jsonify({"success": True, "wishlisted": True, "count": count})
    return redirect(request.referrer or url_for("shop.catalog", slug=store.store_slug))


@shop_bp.route("/<slug>/wishlist/remove/<int:product_id>", methods=["POST"])
def wishlist_remove(slug, product_id):
    store = _resolve_store(slug)
    account = _shop_account(store)
    if not account:
        return jsonify({"success": False}), 401
    with atomic_transaction("wishlist_remove"):
        ShopWishlist.query.filter_by(
            account_id=account.id, product_id=product_id, tenant_id=store.tenant_id
        ).delete()
    if request.content_type and "application/json" in request.content_type:
        return jsonify({"success": True, "wishlisted": False})
    return redirect(request.referrer or url_for("shop.catalog", slug=store.store_slug))


@shop_bp.route("/<slug>/wishlist")
def wishlist_view(slug):
    store = _resolve_store(slug)
    blocked = _require_open_store(store)
    if blocked:
        return blocked
    ctx = _store_context(store)
    account = ctx["shop_account"]
    if not account:
        flash(t("login_required", ctx["lang"]), "warning")
        return redirect(url_for("shop.account_login", slug=store.store_slug))
    items = (
        ShopWishlist.query.filter_by(account_id=account.id, tenant_id=store.tenant_id)
        .order_by(ShopWishlist.created_at.desc())
        .all()
    )
    return render_template(
        "shop/wishlist.html", wishlist_items=items, noindex=True, **ctx
    )


@shop_bp.route("/<slug>/account/login", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
def account_login(slug):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    next_url = request.args.get("next") or request.form.get("next")

    if ctx["is_shop_logged_in"]:
        return _shop_redirect_after_login(next_url, store)

    if request.method == "POST":
        try:
            account = ShopCustomerAuthService.authenticate(
                store.tenant_id,
                request.form.get("email", ""),
                request.form.get("password", ""),
            )

            ShopCustomerAuthService.login(session, store.tenant_id, account)

            flash(t("login_success", ctx["lang"]), "success")

            return _shop_redirect_after_login(next_url, store)

        except ValueError as exc:
            flash(str(exc), "danger")

    return render_template(
        "shop/account_login.html", next_url=next_url, noindex=True, **ctx
    )


@shop_bp.route("/<slug>/account/register", methods=["GET", "POST"])
@limiter.limit("15 per minute", methods=["POST"])
def account_register(slug):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    if ctx["is_shop_logged_in"]:
        return redirect(url_for("shop.catalog", slug=store.store_slug))

    if request.method == "POST":
        if request.form.get("website"):
            abort(400)

        try:
            account = ShopCustomerAuthService.register(
                store.tenant_id,
                request.form.get("name", ""),
                request.form.get("email", ""),
                request.form.get("phone", ""),
                request.form.get("password", ""),
                (request.form.get("address") or "").strip() or None,
            )

            ShopCustomerAuthService.login(session, store.tenant_id, account)

            flash(t("register_success", ctx["lang"]), "success")

            return redirect(url_for("shop.catalog", slug=store.store_slug))

        except ValueError as exc:
            flash(str(exc), "danger")

    return render_template("shop/account_register.html", noindex=True, **ctx)


@shop_bp.route("/<slug>/account/logout", methods=["POST"])
def account_logout(slug):

    store = _resolve_store(slug)

    ShopCustomerAuthService.logout(session, store.tenant_id)

    StoreService.save_cart(session, store.tenant_id, {})

    flash(t("logout_success", shop_lang()), "info")

    return redirect(url_for("shop.catalog", slug=store.store_slug))


@shop_bp.route("/<slug>/account/orders")
def account_orders(slug):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    account, redirect_resp = _require_shop_account(store, ctx)

    if redirect_resp:
        return redirect_resp

    orders = StoreOrderService.list_for_customer(store.tenant_id, account.customer_id)

    payment_methods = {m.code: m for m in StorePaymentMethodService.list_all()}

    return render_template(
        "shop/account_orders.html",
        orders=orders,
        payment_methods=payment_methods,
        noindex=True,
        **ctx,
    )


@shop_bp.route("/<slug>/account/orders/<int:order_id>")
def account_order_detail(slug, order_id):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    account, redirect_resp = _require_shop_account(store, ctx)

    if redirect_resp:
        return redirect_resp

    sale = StoreOrderService.get_tenant_order(store.tenant_id, order_id)

    if not sale or sale.customer_id != account.customer_id:
        abort(404)

    pay_method = StorePaymentMethodService.get_by_code(
        sale.checkout_payment_method or "cod"
    )

    return render_template(
        "shop/account_order_detail.html",
        order=sale,
        pay_method=pay_method,
        status_label=StoreOrderService.status_label(sale.status, ctx.get("lang", "")),
        noindex=True,
        **ctx,
    )


@shop_bp.route("/<slug>")
@shop_bp.route("/<slug>/")
def catalog(slug):

    store = _resolve_store(slug)

    for param in [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
    ]:
        if request.args.get(param):
            session[param] = request.args.get(param)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    category_id = request.args.get("category", type=int)

    search = (request.args.get("q") or "").strip()

    page = request.args.get("page", 1, type=int)

    sort = request.args.get("sort", "")
    valid_sorts = ["price_asc", "price_desc", "name_asc", "name_desc", "newest"]
    current_sort = sort if sort in valid_sorts else ""
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    in_stock_only = request.args.get("in_stock_only", type=int) == 1
    catalog_result = StoreService.get_public_catalog(
        store.tenant_id,
        category_id=category_id,
        search=search,
        page=page,
        sort=current_sort,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
    )

    items = catalog_result["items"]

    categories = (
        ProductCategory.query.filter_by(tenant_id=store.tenant_id, is_active=True)
        .order_by(ProductCategory.name.asc())
        .all()
    )

    wa_digits = _whatsapp_digits(store)

    return render_template(
        "shop/catalog.html",
        items=items,
        categories=categories,
        category_id=category_id,
        search=search,
        wa_digits=wa_digits,
        page=catalog_result["page"],
        pages=catalog_result["pages"],
        total=catalog_result["total"],
        current_sort=current_sort,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
        **ctx,
    )


@shop_bp.route("/<slug>/api/search")
def api_search(slug):
    """AJAX search — returns JSON for autocomplete."""
    store = _resolve_store(slug)
    q = (request.args.get("q") or "").strip()
    if not q or len(q) < 2:
        return jsonify({"results": []})
    items = StoreService.get_public_catalog(
        store.tenant_id, search=q, page=1, per_page=5
    )
    results = []
    for row in items["items"]:
        product = row["product"]
        results.append(
            {
                "id": product.id,
                "name": product.get_display_name(shop_lang()),
                "price": float(product.regular_price or 0),
                "image": product.image_url or "",
                "url": url_for(
                    "shop.product_detail", slug=store.store_slug, product_id=product.id
                ),
            }
        )
    return jsonify({"results": results})


@shop_bp.route("/<slug>/p/<int:product_id>")
def product_detail(slug, product_id):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    product = Product.query.filter_by(
        id=product_id, tenant_id=store.tenant_id, is_active=True
    ).first_or_404()

    stock_map = StoreService.online_stock_map(store.tenant_id, [product.id])

    qty = stock_map.get(product.id, Decimal("0"))

    if qty <= 0 or product.has_serial_number:
        abort(404)

    related_products = StoreService.get_related_products(
        store.tenant_id, product.id, product.category_id, limit=4
    )

    recent_key = f"shop_recent_{store.tenant_id}"
    recent = session.get(recent_key, [])
    recent = [pid for pid in recent if pid != product.id]
    recent.insert(0, product.id)
    recent = recent[:10]
    session[recent_key] = recent
    session.modified = True

    recent_ids = session.get(f"shop_recent_{store.tenant_id}", [])
    recent_products = StoreService.get_recently_viewed_products(
        store.tenant_id, recent_ids, exclude_id=product.id, limit=6
    )

    wa_url = ShopCustomerAuthService.whatsapp_order_url(store, product, ctx["lang"], 1)

    variants = StoreService.get_product_variants(store.tenant_id, product.id)
    loyalty_points = (
        StoreService.get_loyalty_points(ctx["shop_account"].id)
        if ctx["shop_account"]
        else 0
    )
    reviews = (
        ShopReview.query.filter_by(
            product_id=product.id, tenant_id=store.tenant_id, is_approved=True
        )
        .order_by(ShopReview.created_at.desc())
        .all()
    )
    review_count = len(reviews)
    avg_rating = (
        round(sum(r.rating for r in reviews) / review_count, 1)
        if review_count
        else None
    )
    return render_template(
        "shop/product.html",
        product=product,
        available=qty,
        wa_url=wa_url,
        related_products=related_products,
        recent_products=recent_products,
        variants=variants,
        loyalty_points=loyalty_points,
        reviews=reviews,
        review_count=review_count,
        avg_rating=avg_rating,
        **ctx,
    )


@shop_bp.route("/<slug>/p/<int:product_id>/reviews", methods=["GET"])
def product_reviews(slug, product_id):
    store = _resolve_store(slug)
    reviews = (
        ShopReview.query.filter_by(
            product_id=product_id, tenant_id=store.tenant_id, is_approved=True
        )
        .order_by(ShopReview.created_at.desc())
        .all()
    )
    return jsonify(
        {
            "reviews": [
                {
                    "id": r.id,
                    "customer_name": r.customer_name,
                    "rating": r.rating,
                    "comment": r.comment,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in reviews
            ]
        }
    )


@shop_bp.route("/<slug>/p/<int:product_id>/review/add", methods=["POST"])
@limiter.limit("10 per minute", methods=["POST"])
def add_review(slug, product_id):
    store = _resolve_store(slug)
    account = _shop_account(store)
    if not account:
        flash(t("login_required", shop_lang()), "warning")
        return redirect(url_for("shop.account_login", slug=store.store_slug))
    rating = request.form.get("rating", type=int)
    comment = (request.form.get("comment") or "").strip()
    if not rating or rating < 1 or rating > 5:
        flash("Rating must be 1-5", "danger")
        return redirect(
            request.referrer
            or url_for(
                "shop.product_detail", slug=store.store_slug, product_id=product_id
            )
        )
    review = ShopReview(
        tenant_id=store.tenant_id,
        product_id=product_id,
        account_id=account.id,
        customer_name=account.name or "Customer",
        rating=rating,
        comment=comment or None,
        is_approved=False,
    )
    with atomic_transaction("review_add"):
        db.session.add(review)
    flash(t("review_submitted", shop_lang()), "success")
    return redirect(
        url_for("shop.product_detail", slug=store.store_slug, product_id=product_id)
    )


@shop_bp.route("/<slug>/stock-alert/<int:product_id>", methods=["POST"])
@limiter.limit("10 per minute", methods=["POST"])
def stock_alert(slug, product_id):
    store = _resolve_store(slug)
    email = (request.form.get("email") or "").strip()
    if not email or "@" not in email:
        flash("Email is required", "danger")
        return redirect(
            request.referrer
            or url_for(
                "shop.product_detail", slug=store.store_slug, product_id=product_id
            )
        )
    from models.shop_stock_alert import ShopStockAlert

    existing = ShopStockAlert.query.filter_by(
        email=email, product_id=product_id, tenant_id=store.tenant_id
    ).first()
    if existing:
        flash(t("alert_exists", shop_lang()), "info")
    else:
        with atomic_transaction("stock_alert"):
            alert = ShopStockAlert(
                tenant_id=store.tenant_id, product_id=product_id, email=email
            )
            db.session.add(alert)
        flash(t("alert_created", shop_lang()), "success")
    return redirect(
        url_for("shop.product_detail", slug=store.store_slug, product_id=product_id)
    )


@shop_bp.route("/<slug>/newsletter/subscribe", methods=["POST"])
@limiter.limit("10 per minute", methods=["POST"])
def newsletter_subscribe(slug):
    store = _resolve_store(slug)
    email = (request.form.get("email") or "").strip()
    if not email or "@" not in email:
        flash(t("invalid_email", shop_lang()), "danger")
        return redirect(
            request.referrer or url_for("shop.catalog", slug=store.store_slug)
        )
    from models.shop_newsletter import ShopNewsletter

    existing = ShopNewsletter.query.filter_by(
        tenant_id=store.tenant_id, email=email
    ).first()
    if not existing:
        with atomic_transaction("newsletter_subscribe"):
            sub = ShopNewsletter(tenant_id=store.tenant_id, email=email)
            db.session.add(sub)
    flash(t("newsletter_subscribed", shop_lang()), "success")
    return redirect(request.referrer or url_for("shop.catalog", slug=store.store_slug))


@shop_bp.route("/<slug>/cart")
def cart_view(slug):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    cart = StoreService.get_cart(session, store.tenant_id)

    totals = StoreService.cart_totals(store.tenant_id, cart)

    return render_template("shop/cart.html", totals=totals, noindex=True, **ctx)


@shop_bp.route("/<slug>/cart/add", methods=["POST"])
@limiter.limit("30 per minute")
def cart_add(slug):

    store = _resolve_store(slug)

    if _require_open_store(store):
        abort(503)

    product_id = request.form.get("product_id", type=int)

    quantity = request.form.get("quantity", type=float, default=1)

    if not product_id or quantity <= 0:
        if _is_ajax():
            return (
                jsonify({"success": False, "message": t("out_of_stock", shop_lang())}),
                400,
            )

        flash(t("out_of_stock", shop_lang()), "warning")

        return redirect(
            safe_redirect_target(
                request.referrer, "shop.catalog", slug=store.store_slug
            )
        )

    product = Product.query.filter_by(
        id=product_id,
        tenant_id=store.tenant_id,
        is_active=True,
    ).first()
    if not product or product.has_serial_number:
        if _is_ajax():
            return (
                jsonify({"success": False, "message": t("out_of_stock", shop_lang())}),
                400,
            )
        flash(t("out_of_stock", shop_lang()), "warning")
        return redirect(
            safe_redirect_target(
                request.referrer, "shop.catalog", slug=store.store_slug
            )
        )

    stock_map = StoreService.online_stock_map(store.tenant_id, [product_id])

    available = float(stock_map.get(product_id, 0))

    cart = StoreService.get_cart(session, store.tenant_id)

    current = float(cart.get(str(product_id), 0))

    new_qty = min(available, current + quantity)

    if new_qty <= 0:
        if _is_ajax():
            return (
                jsonify({"success": False, "message": t("out_of_stock", shop_lang())}),
                400,
            )

        flash(t("out_of_stock", shop_lang()), "warning")

        return redirect(
            safe_redirect_target(
                request.referrer, "shop.catalog", slug=store.store_slug
            )
        )

    cart[str(product_id)] = new_qty

    StoreService.save_cart(session, store.tenant_id, cart)
    _track_cart_activity(store, _shop_account(store), session)

    if _is_ajax():
        cart_ajax = StoreService.get_cart(session, store.tenant_id)
        count = int(sum(cart_ajax.values()) or 0)
        return jsonify(
            {"success": True, "cart_count": count, "message": "Added to cart"}
        )

    return redirect(url_for("shop.cart_view", slug=store.store_slug))


@shop_bp.route("/<slug>/cart/update", methods=["POST"])
@limiter.limit("40 per minute")
def cart_update(slug):

    store = _resolve_store(slug)

    if _require_open_store(store):
        abort(503)

    cart = StoreService.get_cart(session, store.tenant_id)

    stock_map = StoreService.online_stock_map(
        store.tenant_id, list(cart.keys()) or None
    )

    for key in list(cart.keys()):
        field = f"qty_{key}"

        if field not in request.form:
            continue

        try:
            qty = float(request.form.get(field, 0))

        except (TypeError, ValueError):
            qty = 0

        max_q = float(stock_map.get(int(key), 0))

        if qty <= 0:
            cart.pop(key, None)

        else:
            cart[key] = min(qty, max_q)

    StoreService.save_cart(session, store.tenant_id, cart)
    _track_cart_activity(store, _shop_account(store), session)

    if _is_ajax():
        cart_ajax = StoreService.get_cart(session, store.tenant_id)
        totals_ajax = StoreService.cart_totals(store.tenant_id, cart_ajax)
        count = int(sum(cart_ajax.values()) or 0)
        return jsonify(
            {
                "success": True,
                "cart_count": count,
                "subtotal": float(totals_ajax["subtotal"]),
                "count": int(totals_ajax.get("count", 0)),
            }
        )

    return redirect(url_for("shop.cart_view", slug=store.store_slug))


@shop_bp.route("/<slug>/cart/remove/<int:product_id>", methods=["POST"])
@limiter.limit("40 per minute")
def cart_remove(slug, product_id):

    store = _resolve_store(slug)

    cart = StoreService.get_cart(session, store.tenant_id)

    cart.pop(str(product_id), None)

    StoreService.save_cart(session, store.tenant_id, cart)
    _track_cart_activity(store, _shop_account(store), session)

    if _is_ajax():
        cart_ajax = StoreService.get_cart(session, store.tenant_id)
        count = int(sum(cart_ajax.values()) or 0)
        return jsonify({"success": True, "cart_count": count})

    return redirect(url_for("shop.cart_view", slug=store.store_slug))


@shop_bp.route("/<slug>/cart/count", methods=["GET"])
def cart_count(slug):
    store = _resolve_store(slug)
    cart = StoreService.get_cart(session, store.tenant_id)
    count = int(sum(cart.values()) or 0)
    return jsonify({"count": count})


@shop_bp.route("/<slug>/checkout", methods=["GET", "POST"])
@limiter.limit("15 per minute", methods=["POST"])
def checkout(slug):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    account = ctx["shop_account"]

    cart = StoreService.get_cart(session, store.tenant_id)

    totals = StoreService.cart_totals(store.tenant_id, cart)

    if not totals["lines"]:
        return redirect(url_for("shop.catalog", slug=store.store_slug))

    min_order = Decimal(str(store.min_order_amount or 0))

    if min_order > 0 and totals["subtotal"] < min_order:
        flash(f"{t('free_from', ctx['lang'])}: {min_order}", "warning")

    if request.method == "POST":
        if request.form.get("website"):
            abort(400)

        try:
            name = (
                request.form.get("customer_name")
                or (account.name if account else "")
                or ""
            ).strip()

            email = (
                request.form.get("customer_email")
                or (account.email if account else "")
                or ""
            ).strip()

            phone = (
                request.form.get("phone") or (account.phone if account else "") or ""
            ).strip()

            address = (
                request.form.get("address")
                or (account.address if account else "")
                or ""
            ).strip()

            notes = (request.form.get("notes") or "").strip()

            payment_method = (request.form.get("payment_method") or "").strip()

            if not address:
                raise ValueError(
                    gettext("عنوان التوصيل مطلوب.")
                    if ctx["lang"] == "ar"
                    else "Delivery address is required."
                )

            if min_order > 0 and totals["subtotal"] < min_order:
                raise ValueError(
                    gettext(f"الحد الأدنى للطلب {min_order}")
                    if ctx["lang"] == "ar"
                    else f"Minimum order is {min_order}"
                )

            with atomic_transaction("store_checkout"):
                sale = StoreCheckoutService.create_web_order(
                    store,
                    cart,
                    name,
                    phone,
                    address,
                    notes,
                    payment_method_code=payment_method,
                    shop_account=account,
                    coupon_code=(request.form.get("coupon_code") or "").strip(),
                    customer_email=email or None,
                )

                StoreService.save_cart(session, store.tenant_id, {})

            if payment_method == "online_pay":
                from services.store_online_payment_service import (
                    StoreOnlinePaymentService,
                )

                try:
                    payment = StoreOnlinePaymentService.create_payment_for_sale(
                        sale,
                        store,
                        customer_email=getattr(account, "email", None),
                    )
                    return redirect(payment["payment_url"])
                except ValueError as pe:
                    with atomic_transaction("checkout_payment_fail"):
                        sale.payment_status = "init_failed"
                        sale.notes = (sale.notes or "") + gettext(
                            f"\n[فشل init الدفع الإلكتروني: {str(pe)}]"
                        )
                    token = StoreCheckoutService.make_order_token(
                        sale.id, store.tenant_id
                    )
                    flash(
                        str(pe) + gettext(" — تم حفظ طلبك، يمكنك إتمام الدفع لاحقاً."),
                        "warning",
                    )
                    return redirect(
                        url_for(
                            "shop.order_confirmation",
                            slug=store.store_slug,
                            token=token,
                        )
                    )

            token = StoreCheckoutService.make_order_token(sale.id, store.tenant_id)

            return redirect(
                url_for("shop.order_confirmation", slug=store.store_slug, token=token)
            )

        except ValueError as exc:
            flash(str(exc), "danger")

        except Exception:
            flash(
                (
                    gettext("تعذر إتمام الطلب. حاول مجدداً.")
                    if ctx["lang"] == "ar"
                    else "Could not place order. Try again."
                ),
                "danger",
            )

    payment_methods = StorePaymentMethodService.list_for_checkout(store.tenant_id)

    if not payment_methods:
        flash(
            (
                gettext("لا توجد طرق دفع متاحة حالياً.")
                if ctx["lang"] == "ar"
                else "No payment methods available."
            ),
            "warning",
        )
    loyalty_points = StoreService.get_loyalty_points(account.id) if account else 0

    return render_template(
        "shop/checkout.html",
        totals=totals,
        min_order=min_order,
        noindex=True,
        payment_methods=payment_methods,
        payment_hint=lambda pm: StorePaymentMethodService.format_checkout_instructions(
            pm, ctx["lang"]
        ),
        loyalty_points=loyalty_points,
        coupon_code=(
            (request.form.get("coupon_code") or "").strip()
            if request.method == "POST"
            else ""
        ),
        prefilled={
            "name": (
                (
                    request.form.get("customer_name")
                    or (account.name if account else "")
                    or ""
                )
                if request.method == "POST"
                else ((account.name if account else "") or "")
            ),
            "email": (
                (
                    request.form.get("customer_email")
                    or (account.email if account else "")
                    or ""
                )
                if request.method == "POST"
                else ((account.email if account else "") or "")
            ),
            "phone": (
                (request.form.get("phone") or (account.phone if account else "") or "")
                if request.method == "POST"
                else ((account.phone if account else "") or "")
            ),
            "address": (
                (
                    request.form.get("address")
                    or (account.address if account else "")
                    or ""
                )
                if request.method == "POST"
                else ((account.address if account else "") or "")
            ),
        },
        **ctx,
    )


@shop_bp.route("/<slug>/return-policy")
def return_policy(slug):

    store = _resolve_store(slug)

    ctx = _store_context(store)

    policy = store.return_policy(ctx["lang"])

    if not policy:
        abort(404)

    return render_template("shop/return_policy.html", policy=policy, **ctx)


@shop_bp.route("/<slug>/quick-view/<int:product_id>")
def quick_view(slug, product_id):
    store = _resolve_store(slug)
    ctx = _store_context(store)
    product = Product.query.filter_by(
        id=product_id, tenant_id=store.tenant_id, is_active=True
    ).first_or_404()
    stock_map = StoreService.online_stock_map(store.tenant_id, [product.id])
    qty = stock_map.get(product.id, Decimal("0"))
    wa_url = (
        ShopCustomerAuthService.whatsapp_order_url(store, product, ctx["lang"], 1)
        if not ctx["is_shop_logged_in"]
        else None
    )
    return render_template(
        "shop/partials/quick_view_body.html",
        product=product,
        available=qty,
        wa_url=wa_url,
        **ctx,
    )


@shop_bp.route("/<slug>/sitemap.xml")
def store_sitemap(slug):

    from flask import Response

    from datetime import datetime, timezone

    store = _resolve_store(slug)

    if not StoreService.is_store_publicly_available(store):
        abort(404)

    base = request.url_root.rstrip("/")

    catalog_result = StoreService.get_public_catalog(store.tenant_id, per_page=9999)
    items = catalog_result["items"]

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    xml.append(
        f"  <url><loc>{base}/s/{store.store_slug}</loc><lastmod>{today}</lastmod><priority>1.0</priority></url>"
    )

    for row in items:
        product = row["product"]

        xml.append(
            f"  <url><loc>{base}/s/{store.store_slug}/p/{product.id}</loc>"
            f"<priority>0.8</priority><changefreq>weekly</changefreq></url>"
        )

    xml.append("</urlset>")

    return Response("\n".join(xml), mimetype="application/xml")


@shop_bp.route("/<slug>/robots.txt")
def store_robots(slug):
    from flask import Response

    store = _resolve_store(slug)
    lines = [
        "User-agent: *",
        "Disallow: /s/" + store.store_slug + "/cart",
        "Disallow: /s/" + store.store_slug + "/checkout",
        "Disallow: /s/" + store.store_slug + "/account/",
        "Disallow: /s/" + store.store_slug + "/wishlist",
        "",
        "Sitemap: "
        + request.url_root.rstrip("/")
        + url_for("shop.store_sitemap", slug=store.store_slug),
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@shop_bp.route("/<slug>/account/forgot-password", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def account_forgot_password(slug):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    if request.method == "POST":
        try:
            account = ShopCustomerAuthService.request_password_reset(
                store.tenant_id, request.form.get("email", "")
            )

            if account:
                reset_url = url_for(
                    "shop.account_reset_password",
                    slug=store.store_slug,
                    token=account.password_reset_token,
                    _external=True,
                )

                ShopCustomerAuthService.send_password_reset_email(
                    account, store, reset_url
                )

            flash(t("reset_email_sent", ctx["lang"]), "success")

            return redirect(url_for("shop.account_login", slug=store.store_slug))

        except ValueError as exc:
            flash(str(exc), "danger")

    return render_template("shop/account_forgot_password.html", noindex=True, **ctx)


@shop_bp.route("/<slug>/account/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def account_reset_password(slug, token):

    store = _resolve_store(slug)

    blocked = _require_open_store(store)

    if blocked:
        return blocked

    ctx = _store_context(store)

    if request.method == "POST":
        try:
            ShopCustomerAuthService.reset_password(
                store.tenant_id, token, request.form.get("password", "")
            )

            flash(t("reset_success", ctx["lang"]), "success")

            return redirect(url_for("shop.account_login", slug=store.store_slug))

        except ValueError as exc:
            flash(str(exc), "danger")

    return render_template(
        "shop/account_reset_password.html", token=token, noindex=True, **ctx
    )


@shop_bp.route("/<slug>/account/payments")
def saved_payments(slug):
    store = _resolve_store(slug)
    ctx = _store_context(store)
    account = ctx["shop_account"]
    if not account:
        return redirect(url_for("shop.account_login", slug=store.store_slug))
    from models.shop_saved_payment import ShopSavedPayment

    payments = ShopSavedPayment.query.filter_by(
        account_id=account.id, tenant_id=store.tenant_id
    ).all()
    return render_template(
        "shop/saved_payments.html", payments=payments, noindex=True, **ctx
    )


@shop_bp.route("/<slug>/account/payments/save", methods=["POST"])
@limiter.limit("10 per minute", methods=["POST"])
def save_payment(slug):
    store = _resolve_store(slug)
    account = _shop_account(store)
    if not account:
        return jsonify({"success": False}), 401
    method_code = request.form.get("method_code", "").strip()
    label = (request.form.get("label") or "").strip() or method_code
    from models.shop_saved_payment import ShopSavedPayment

    with atomic_transaction("save_payment"):
        pm = ShopSavedPayment(
            tenant_id=store.tenant_id,
            account_id=account.id,
            method_code=method_code,
            label=label,
            details="{}",
        )
        db.session.add(pm)
    flash(t("payment_saved", shop_lang()), "success")
    return redirect(url_for("shop.saved_payments", slug=store.store_slug))


@shop_bp.route("/<slug>/account/payments/delete/<int:payment_id>", methods=["POST"])
def delete_saved_payment(slug, payment_id):
    store = _resolve_store(slug)
    account = _shop_account(store)
    if not account:
        return jsonify({"success": False}), 401
    from models.shop_saved_payment import ShopSavedPayment

    pm = ShopSavedPayment.query.filter_by(
        id=payment_id, account_id=account.id, tenant_id=store.tenant_id
    ).first_or_404()
    with atomic_transaction("delete_payment"):
        db.session.delete(pm)
    flash(t("payment_deleted", shop_lang()), "success")
    return redirect(url_for("shop.saved_payments", slug=store.store_slug))


@shop_bp.route("/<slug>/order/reorder/<int:sale_id>", methods=["POST"])
@limiter.limit("10 per minute")
def reorder(slug, sale_id):
    store = _resolve_store(slug)
    account = _shop_account(store)
    if not account:
        flash(t("login_required", shop_lang()), "warning")
        return redirect(url_for("shop.account_login", slug=store.store_slug))
    sale = Sale.query.filter_by(
        id=sale_id, tenant_id=store.tenant_id, source="online_store"
    ).first_or_404()
    if sale.customer_id != account.customer_id:
        abort(404)
    lines = SaleLine.query.filter_by(sale_id=sale.id, tenant_id=store.tenant_id).all()
    if not lines:
        flash("No items to reorder", "warning")
        return redirect(url_for("shop.account_orders", slug=store.store_slug))
    cart = StoreService.get_cart(session, store.tenant_id)
    stock_map = StoreService.online_stock_map(
        store.tenant_id, [line.product_id for line in lines]
    )
    for line in lines:
        available = float(stock_map.get(line.product_id, 0))
        if available > 0:
            qty = min(float(line.quantity), available)
            cart[str(line.product_id)] = cart.get(str(line.product_id), 0) + qty
    StoreService.save_cart(session, store.tenant_id, cart)
    flash(t("cart_updated"), "success")
    return redirect(url_for("shop.cart_view", slug=store.store_slug))


@shop_bp.route("/<slug>/order/<int:sale_id>/invoice")
@limiter.limit("10 per minute")
def order_invoice(slug, sale_id):
    store = _resolve_store(slug)
    ctx = _store_context(store)
    account = ctx["shop_account"]
    if not account:
        flash(t("login_required", ctx["lang"]), "warning")
        return redirect(url_for("shop.account_login", slug=store.store_slug))
    sale = Sale.query.filter_by(
        id=sale_id, tenant_id=store.tenant_id, source="online_store"
    ).first_or_404()
    if sale.customer_id != account.customer_id:
        abort(404)
    pay_method = StorePaymentMethodService.get_by_code(
        sale.checkout_payment_method or "cod"
    )
    ctx.update(
        status_label=StoreOrderService.status_label(sale.status, ctx.get("lang", "")),
        pay_method=pay_method,
    )
    return render_template("shop/order_invoice.html", sale=sale, **ctx)


@shop_bp.route("/<slug>/track")
def order_track(slug):
    store = _resolve_store(slug)
    ctx = _store_context(store)
    order_number = (request.args.get("order") or "").strip()
    sale = None
    if order_number:
        sale = Sale.query.filter_by(
            tenant_id=store.tenant_id,
            sale_number=order_number,
            source="online_store",
        ).first()
        if not sale:
            flash(t("order_not_found", ctx["lang"]), "warning")
    return render_template(
        "shop/order_track.html",
        sale=sale,
        order_number=order_number,
        status_label=(
            StoreOrderService.status_label(sale.status, ctx.get("lang", ""))
            if sale
            else None
        ),
        **ctx,
    )


@shop_bp.route("/<slug>/order/<token>")
def order_confirmation(slug, token):

    store = _resolve_store(slug)

    ctx = _store_context(store)

    payload = StoreCheckoutService.load_order_token(token)

    if not payload or int(payload.get("tenant_id", 0)) != int(store.tenant_id):
        abort(404)

    sale = Sale.query.filter_by(
        id=int(payload["sale_id"]), tenant_id=store.tenant_id, source="online_store"
    ).first_or_404()

    pay_method = StorePaymentMethodService.get_by_code(
        sale.checkout_payment_method or "cod"
    )

    return render_template(
        "shop/order_success.html", sale=sale, token=token, pay_method=pay_method, **ctx
    )
