"""Online store — tenant-bound catalog via online warehouse only (not POS)."""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from extensions import db

logger = logging.getLogger(__name__)
from flask_babel import gettext

from models import Branch, Product, Tenant, TenantStore, Warehouse
from models.system_settings import SystemSettings
from utils.branching import get_accessible_warehouses, get_branch_stock_map
from utils.db_safety import atomic_transaction
from utils.tenanting import require_active_tenant_id


class StoreService:
    SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    @staticmethod
    def resolve_tenant_id(user=None) -> int:
        return require_active_tenant_id(user)

    @staticmethod
    def get_online_warehouse(tenant_id: int, *, create: bool = False) -> Warehouse | None:
        query = Warehouse.query.filter_by(
            tenant_id=int(tenant_id),
            warehouse_type=Warehouse.TYPE_ONLINE,
            is_active=True,
        )
        warehouse = query.order_by(Warehouse.id.asc()).first()
        if warehouse or not create:
            return warehouse
        return StoreService.ensure_online_warehouse(tenant_id)

    @staticmethod
    def ensure_online_warehouse(tenant_id: int) -> Warehouse:
        tenant_id = int(tenant_id)
        existing = StoreService.get_online_warehouse(tenant_id, create=False)
        if existing:
            return existing

        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError(gettext("الشركة غير موجودة."))

        branch = (
            Branch.query.filter_by(tenant_id=tenant_id, is_active=True)
            .order_by(Branch.is_main.desc(), Branch.id.asc())
            .first()
        )

        suffix = tenant_id
        code = f"ONLINE-{suffix}"
        name = f"Online Store WH {suffix}"
        name_ar = gettext("مستودع المتجر الإلكتروني (%(name)s)") % {"name": tenant.name_ar or tenant.name}

        if Warehouse.query.filter_by(tenant_id=tenant_id, code=code).first():
            code = f"ONLINE-T{suffix}"
        if Warehouse.query.filter_by(tenant_id=tenant_id, name=name).first():
            name = f"Online Store WH T{suffix}"

        warehouse = Warehouse(
            tenant_id=tenant_id,
            name=name,
            name_ar=name_ar,
            code=code,
            location="Online / أونلاين",
            warehouse_type=Warehouse.TYPE_ONLINE,
            branch_id=branch.id if branch else None,
            is_main=False,
            is_active=True,
        )
        db.session.add(warehouse)
        db.session.flush()
        return warehouse

    @staticmethod
    def get_tenant_store(tenant_id: int, *, create: bool = False) -> TenantStore | None:
        store = TenantStore.query.filter_by(tenant_id=int(tenant_id)).first()
        if store or not create:
            return store
        return StoreService.ensure_tenant_store(tenant_id)

    @staticmethod
    def ensure_tenant_store(tenant_id: int) -> TenantStore:
        tenant_id = int(tenant_id)
        store = TenantStore.query.filter_by(tenant_id=tenant_id).first()
        if store:
            if not store.warehouse_id:
                store.warehouse_id = StoreService.ensure_online_warehouse(tenant_id).id
            return store

        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError(gettext("الشركة غير موجودة."))

        online_wh = StoreService.ensure_online_warehouse(tenant_id)
        slug = StoreService.normalize_slug(tenant.slug or f"tenant-{tenant_id}")
        slug = StoreService.ensure_unique_slug(slug, tenant_id=tenant_id)

        store = TenantStore(
            tenant_id=tenant_id,
            warehouse_id=online_wh.id,
            is_enabled=False,
            store_slug=slug,
            title=tenant.name_ar or tenant.name,
        )
        db.session.add(store)
        db.session.flush()
        return store

    @staticmethod
    def normalize_slug(value: str) -> str:
        slug = (value or "").strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug or "store"

    @staticmethod
    def ensure_unique_slug(slug: str, *, tenant_id: int | None = None) -> str:
        base = StoreService.normalize_slug(slug)
        candidate = base
        n = 2
        while True:
            q = TenantStore.query.filter_by(store_slug=candidate)
            if tenant_id:
                q = q.filter(TenantStore.tenant_id != int(tenant_id))
            if not q.first():
                return candidate
            candidate = f"{base}-{n}"
            n += 1

    @staticmethod
    def validate_slug(slug: str) -> str:
        normalized = StoreService.normalize_slug(slug)
        if not StoreService.SLUG_RE.match(normalized):
            raise ValueError(gettext("رابط المتجر يجب أن يحتوي على حروف إنجليزية صغيرة وأرقام وشرطات فقط."))
        return normalized

    @staticmethod
    def online_stock_map(tenant_id: int, product_ids=None) -> dict[int, Decimal]:
        online_wh = StoreService.get_online_warehouse(tenant_id, create=False)
        if not online_wh:
            return {}
        return get_branch_stock_map(product_ids=product_ids, warehouse_ids=[online_wh.id])

    @staticmethod
    def get_catalog_products(tenant_id: int, *, include_zero: bool = False):
        """Products visible in store admin — scoped to tenant, stock from online warehouse only."""
        online_wh = StoreService.get_online_warehouse(tenant_id, create=False)
        if not online_wh:
            return [], {}

        products = Product.query.filter_by(tenant_id=int(tenant_id), is_active=True).order_by(Product.name.asc()).all()
        stock_map = StoreService.online_stock_map(tenant_id, [p.id for p in products])

        if not include_zero:
            products = [p for p in products if (stock_map.get(p.id) or Decimal("0")) > 0]

        return products, stock_map

    @staticmethod
    def get_related_products(tenant_id: int, product_id: int, category_id: int, limit: int = 4):
        products, stock_map = StoreService.get_catalog_products(tenant_id, include_zero=False)
        related = []
        for product in products:
            if product.id == product_id:
                continue
            if product.category_id != category_id:
                continue
            if product.has_serial_number:
                continue
            qty = stock_map.get(product.id, Decimal("0"))
            if qty <= 0:
                continue
            related.append({"product": product, "quantity": qty})
            if len(related) >= limit:
                break
        return related

    @staticmethod
    def count_visible_products(tenant_id: int) -> int:
        products, _ = StoreService.get_catalog_products(tenant_id, include_zero=False)
        return len(products)

    @staticmethod
    def assert_single_online_warehouse(tenant_id: int, warehouse_id: int | None = None):
        q = Warehouse.query.filter_by(
            tenant_id=int(tenant_id),
            warehouse_type=Warehouse.TYPE_ONLINE,
            is_active=True,
        )
        if warehouse_id:
            q = q.filter(Warehouse.id != int(warehouse_id))
        if q.first():
            raise ValueError(gettext("يوجد مستودع أونلاين نشط بالفعل لهذه الشركة. مسموح بواحد فقط."))

    @staticmethod
    def get_physical_warehouses(tenant_id: int, *, user=None):
        warehouses = get_accessible_warehouses(user) if user else Warehouse.query.filter_by(is_active=True).all()
        return [wh for wh in warehouses if wh.tenant_id == int(tenant_id) and not wh.is_online]

    @staticmethod
    def active_tenant_id_for_user(user=None) -> int:
        return StoreService.resolve_tenant_id(user)

    @staticmethod
    def stores_globally_enabled() -> bool:
        try:
            settings = SystemSettings.get_current()
            return bool(getattr(settings, "enable_ecommerce", False))
        except Exception:
            logger.debug("Store availability check failed; treating as disabled", exc_info=True)
            return False

    @staticmethod
    def set_stores_globally_enabled(enabled: bool):
        settings = SystemSettings.get_current()
        settings.enable_ecommerce = bool(enabled)
        db.session.flush()

    @staticmethod
    def is_platform_locked(store: TenantStore | None) -> bool:
        """True when the platform owner has force-disabled this tenant store."""
        return bool(store and getattr(store, "platform_disabled", False))

    @staticmethod
    def effective_enabled(store: TenantStore | None) -> bool:
        """Tenant store is effectively on only if enabled and not platform-locked."""
        return bool(store and store.is_enabled and not StoreService.is_platform_locked(store))

    @staticmethod
    def set_platform_disabled(store: TenantStore, disabled: bool):
        """Platform-owner only: hard force-OFF lock. Tenant cannot re-enable while locked."""
        with atomic_transaction("set_platform_disabled"):
            store.platform_disabled = bool(disabled)
        return store

    @staticmethod
    def get_store_by_slug(slug: str) -> TenantStore | None:
        normalized = StoreService.normalize_slug(slug)
        return TenantStore.query.filter_by(store_slug=normalized).first()

    @staticmethod
    def normalize_subdomain(value: str) -> str:
        return StoreService.normalize_slug(value)

    @staticmethod
    def get_store_by_host(host: str) -> TenantStore | None:
        host = (host or "").split(":")[0].lower().strip()
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return None

        store = TenantStore.query.filter_by(custom_domain=host).first()
        if store:
            return store

        label = host.split(".")[0]
        if label and label not in ("localhost", "127", "0"):
            store = TenantStore.query.filter_by(subdomain=label).first()
            if store:
                return store
        return None

    @staticmethod
    def ensure_unique_subdomain(subdomain: str, *, tenant_id: int | None = None) -> str:
        base = StoreService.normalize_subdomain(subdomain)
        candidate = base
        n = 2
        while True:
            q = TenantStore.query.filter_by(subdomain=candidate)
            if tenant_id:
                q = q.filter(TenantStore.tenant_id != int(tenant_id))
            if not q.first():
                return candidate
            candidate = f"{base}-{n}"
            n += 1

    @staticmethod
    def is_store_publicly_available(store: TenantStore | None) -> bool:
        if not store or not store.is_enabled:
            return False
        if StoreService.is_platform_locked(store):
            return False
        if not StoreService.stores_globally_enabled():
            return False
        tenant = db.session.get(Tenant, store.tenant_id)
        if not tenant or not getattr(tenant, "is_active", True) or getattr(tenant, "is_suspended", False):
            return False
        online_wh = db.session.get(Warehouse, store.warehouse_id)
        return bool(online_wh and online_wh.is_active and online_wh.is_online)

    @staticmethod
    def cart_session_key(tenant_id: int) -> str:
        return f"shop_cart_{int(tenant_id)}"

    @staticmethod
    def get_cart(session, tenant_id: int) -> dict:
        raw = session.get(StoreService.cart_session_key(tenant_id), {})
        if not isinstance(raw, dict):
            return {}
        cleaned = {}
        for k, v in raw.items():
            try:
                q = float(v)
                if q > 0:
                    cleaned[str(int(k))] = q
            except (TypeError, ValueError):
                logger.debug("Skipping invalid cart entry %r=%r", k, v, exc_info=True)
                continue
        return cleaned

    @staticmethod
    def save_cart(session, tenant_id: int, cart: dict):
        session[StoreService.cart_session_key(tenant_id)] = cart
        session.modified = True

    @staticmethod
    def get_public_catalog(
        tenant_id: int,
        *,
        category_id=None,
        search: str | None = None,
        page=1,
        per_page=24,
        sort=None,
        min_price=None,
        max_price=None,
        in_stock_only=False,
        display_currency: str | None = None,
    ):
        """Storefront catalog — in-stock online warehouse, no serial-tracked products.

        display_price is resolved through StorePricingService (single pricing
        engine) so the catalog matches product/cart/checkout exactly.
        """
        from services.store_pricing_service import StorePricingService

        products, stock_map = StoreService.get_catalog_products(tenant_id, include_zero=False)
        tenant = db.session.get(Tenant, int(tenant_id))
        items = []
        q = (search or "").strip().lower()
        for product in products:
            if product.has_serial_number:
                continue
            if category_id and product.category_id != int(category_id):
                continue
            if q:
                blob = f"{product.name} {product.name_ar or ''} {product.sku or ''}".lower()
                if q not in blob:
                    continue
            qty = stock_map.get(product.id, Decimal("0"))
            if qty <= 0:
                continue
            display_price = StorePricingService.resolve_display_price(product, tenant, display_currency)
            items.append(
                {
                    "product": product,
                    "stock": qty,
                    "quantity": qty,
                    "display_price": display_price,
                }
            )
        if min_price is not None:
            items = [i for i in items if float(i["display_price"]) >= float(min_price)]
        if max_price is not None:
            items = [i for i in items if float(i["display_price"]) <= float(max_price)]
        if sort == "price_asc":
            items.sort(key=lambda x: float(x["display_price"]))
        elif sort == "price_desc":
            items.sort(key=lambda x: float(x["display_price"]), reverse=True)
        elif sort == "name_asc":
            items.sort(key=lambda x: (x["product"].get_display_name("en") or "").lower())
        elif sort == "name_desc":
            items.sort(
                key=lambda x: (x["product"].get_display_name("en") or "").lower(),
                reverse=True,
            )
        elif sort == "newest":
            items.sort(key=lambda x: x["product"].created_at or "", reverse=True)
        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page
        page_items = items[start:end]
        return {
            "items": page_items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    @staticmethod
    def cart_totals(tenant_id: int, cart: dict, display_currency: str | None = None) -> dict:
        """Cart lines + totals. When display_currency is provided, each line also
        carries display_price / display_line_total and the dict display_subtotal —
        resolved via the unified StorePricingService."""
        from services.store_pricing_service import StorePricingService

        lines = []
        subtotal = Decimal("0")
        display_subtotal = Decimal("0")
        tenant = db.session.get(Tenant, int(tenant_id))
        stock_map = StoreService.online_stock_map(tenant_id, [int(k) for k in cart] if cart else None)
        for pid, qty_raw in cart.items():
            product = Product.query.filter_by(id=int(pid), tenant_id=int(tenant_id), is_active=True).first()
            if not product:
                continue
            qty = Decimal(str(qty_raw))
            max_q = stock_map.get(product.id, Decimal("0"))
            if qty > max_q:
                qty = max_q
            if qty <= 0:
                continue
            line_total = Decimal(str(product.regular_price or 0)) * qty
            subtotal += line_total
            line = {"product": product, "quantity": qty, "line_total": line_total}
            if display_currency:
                display_price = StorePricingService.resolve_display_price(product, tenant, display_currency)
                display_line_total = (display_price * qty).quantize(Decimal("0.01"))
                display_subtotal += display_line_total
                line["display_price"] = display_price
                line["display_line_total"] = display_line_total
            lines.append(line)
        result = {
            "lines": lines,
            "subtotal": subtotal,
            "count": sum(line["quantity"] for line in lines),
        }
        if display_currency:
            result["display_subtotal"] = display_subtotal
        return result

    @staticmethod
    def get_recently_viewed_products(tenant_id: int, product_ids: list, exclude_id: int | None = None, limit: int = 6):
        if not product_ids:
            return []
        ids = [pid for pid in product_ids if pid != exclude_id]
        ids = ids[:limit]
        products = Product.query.filter(
            Product.id.in_(ids),
            Product.tenant_id == int(tenant_id),
            Product.is_active,
        ).all()
        product_map = {p.id: p for p in products}
        ordered = [product_map[pid] for pid in ids if pid in product_map]
        return ordered

    @staticmethod
    def get_product_variants(tenant_id: int, product_id: int):
        from models.shop_product_variant import ShopProductVariant

        return (
            ShopProductVariant.query.filter_by(
                tenant_id=int(tenant_id),
                product_id=int(product_id),
                is_active=True,
            )
            .order_by(ShopProductVariant.sort_order.asc())
            .all()
        )

    @staticmethod
    def get_loyalty_points(account_id: int):
        from models.shop_loyalty import ShopLoyalty

        lp = ShopLoyalty.query.filter_by(account_id=int(account_id)).first()
        return lp.points if lp else 0

    @staticmethod
    def earn_loyalty_points(tenant_id: int, account_id: int, sale_id: int, total_amount: Decimal):
        if not account_id:
            return
        from models.shop_loyalty import ShopLoyalty, ShopLoyaltyTransaction

        points_earned = int(total_amount)
        lp = ShopLoyalty.query.filter_by(account_id=int(account_id)).first()
        if not lp:
            lp = ShopLoyalty(
                tenant_id=int(tenant_id),
                account_id=int(account_id),
                points=0,
                points_earned=0,
                points_redeemed=0,
            )
            db.session.add(lp)
        lp.points = (lp.points or 0) + points_earned
        lp.points_earned = (lp.points_earned or 0) + points_earned
        txn = ShopLoyaltyTransaction(
            tenant_id=int(tenant_id),
            account_id=int(account_id),
            sale_id=sale_id,
            points=points_earned,
            reason="order",
        )
        db.session.add(txn)

    @staticmethod
    def redeem_loyalty_points(tenant_id: int, account_id: int, points: int):
        from models.shop_loyalty import ShopLoyalty, ShopLoyaltyTransaction

        lp = ShopLoyalty.query.filter_by(account_id=int(account_id)).first()
        if not lp or (lp.points or 0) < points:
            raise ValueError("Insufficient loyalty points")
        lp.points = (lp.points or 0) - points
        lp.points_redeemed = (lp.points or 0) + points
        txn = ShopLoyaltyTransaction(
            tenant_id=int(tenant_id),
            account_id=int(account_id),
            points=-points,
            reason="redeem",
        )
        db.session.add(txn)
        return Decimal(points) / Decimal("100")

    # ─── Route-facing scoped fetches ───

    @staticmethod
    def find_custom_domain_clash(custom_domain: str, exclude_tenant_id: int):
        """Another tenant's store already claiming this custom domain (or None)."""
        from models import TenantStore

        return TenantStore.query.filter(
            TenantStore.custom_domain == custom_domain,
            TenantStore.tenant_id != exclude_tenant_id,
        ).first()

    @staticmethod
    def list_active_products(tenant_id: int):
        """Tenant-scoped active products ordered by name (transfer picker)."""
        from models import Product

        return Product.query.filter_by(tenant_id=tenant_id, is_active=True).order_by(Product.name.asc()).all()

    @staticmethod
    def get_transfer_product(tenant_id: int, product_id: int):
        """Fetch a product for a stock transfer; raises ValueError when missing."""
        from flask_babel import gettext

        from models import Product

        product = Product.query.filter_by(id=product_id, tenant_id=tenant_id).first()
        if not product:
            raise ValueError(gettext("المنتج غير موجود."))
        return product

    @staticmethod
    def online_orders_query(tenant_id: int, status_filter=None):
        """Online-store orders query, newest first, optionally status-filtered."""
        from models import Sale
        from services.store_order_service import StoreOrderService

        query = Sale.query.filter_by(tenant_id=tenant_id, source="online_store").order_by(Sale.sale_date.desc())
        if status_filter in StoreOrderService.STORE_ORDER_STATUSES:
            query = query.filter_by(status=status_filter)
        return query

    @staticmethod
    def list_customer_accounts(tenant_id: int, limit: int = 200):
        """Most recent shop customer accounts for the store admin."""
        from models import ShopCustomerAccount

        return (
            ShopCustomerAccount.query.filter_by(tenant_id=tenant_id)
            .order_by(ShopCustomerAccount.created_at.desc())
            .limit(limit)
            .all()
        )

    # ─── Storefront route queries (relocated from routes/shop.py) ───

    @staticmethod
    def save_abandoned_cart_snapshot(tenant_id, account_id, email, cart_json):
        """Upsert the abandoned-cart snapshot for a storefront session."""
        from models.shop_abandoned_cart import ShopAbandonedCart

        existing = ShopAbandonedCart.query.filter_by(
            tenant_id=tenant_id,
            account_id=account_id,
            recovered=False,
        ).first()
        if existing:
            existing.cart_data = cart_json
        else:
            ac = ShopAbandonedCart(
                tenant_id=tenant_id,
                account_id=account_id,
                email=email,
                cart_data=cart_json,
            )
            db.session.add(ac)
        db.session.flush()

    @staticmethod
    def wishlist_entry(tenant_id, account_id, product_id):
        from models.shop_wishlist import ShopWishlist

        return ShopWishlist.query.filter_by(
            account_id=account_id, product_id=product_id, tenant_id=tenant_id
        ).first()

    @staticmethod
    def wishlist_count(tenant_id, account_id) -> int:
        from models.shop_wishlist import ShopWishlist

        return ShopWishlist.query.filter_by(account_id=account_id, tenant_id=tenant_id).count()

    @staticmethod
    def remove_wishlist_entry(tenant_id, account_id, product_id):
        from models.shop_wishlist import ShopWishlist

        ShopWishlist.query.filter_by(account_id=account_id, product_id=product_id, tenant_id=tenant_id).delete()

    @staticmethod
    def wishlist_items(tenant_id, account_id):
        from models.shop_wishlist import ShopWishlist

        return (
            ShopWishlist.query.filter_by(account_id=account_id, tenant_id=tenant_id)
            .order_by(ShopWishlist.created_at.desc())
            .all()
        )

    @staticmethod
    def active_categories(tenant_id: int):
        """Active product categories ordered by name for the catalog sidebar."""
        from models import ProductCategory

        return (
            ProductCategory.query.filter_by(tenant_id=tenant_id, is_active=True)
            .order_by(ProductCategory.name.asc())
            .all()
        )

    @staticmethod
    def active_product_or_404(tenant_id: int, product_id: int):
        """Tenant-scoped active product or 404."""
        from models import Product

        return Product.query.filter_by(id=product_id, tenant_id=tenant_id, is_active=True).first_or_404()

    @staticmethod
    def active_product(tenant_id: int, product_id: int):
        """Tenant-scoped active product or None."""
        from models import Product

        return Product.query.filter_by(
            id=product_id,
            tenant_id=tenant_id,
            is_active=True,
        ).first()

    @staticmethod
    def approved_reviews(tenant_id: int, product_id: int):
        """Approved reviews for a product, newest first."""
        from models.shop_review import ShopReview

        return (
            ShopReview.query.filter_by(product_id=product_id, tenant_id=tenant_id, is_approved=True)
            .order_by(ShopReview.created_at.desc())
            .all()
        )

    @staticmethod
    def stock_alert_subscriber(tenant_id: int, product_id: int, email: str):
        """Existing stock-alert subscription for an email/product pair."""
        from models.shop_stock_alert import ShopStockAlert

        return ShopStockAlert.query.filter_by(email=email, product_id=product_id, tenant_id=tenant_id).first()

    @staticmethod
    def newsletter_subscriber(tenant_id: int, email: str):
        """Existing newsletter subscription for an email."""
        from models.shop_newsletter import ShopNewsletter

        return ShopNewsletter.query.filter_by(tenant_id=tenant_id, email=email).first()

    @staticmethod
    def saved_payment_methods(tenant_id: int, account_id: int):
        """Saved payment methods of a shop customer account."""
        from models.shop_saved_payment import ShopSavedPayment

        return ShopSavedPayment.query.filter_by(account_id=account_id, tenant_id=tenant_id).all()

    @staticmethod
    def saved_payment_or_404(tenant_id: int, account_id: int, payment_id: int):
        """Account-owned saved payment method or 404."""
        from models.shop_saved_payment import ShopSavedPayment

        return ShopSavedPayment.query.filter_by(
            id=payment_id, account_id=account_id, tenant_id=tenant_id
        ).first_or_404()

    @staticmethod
    def online_order_or_404(tenant_id: int, sale_id: int):
        """Online-store order scoped to the tenant or 404."""
        from models import Sale

        return Sale.query.filter_by(id=sale_id, tenant_id=tenant_id, source="online_store").first_or_404()

    @staticmethod
    def online_order_lines(tenant_id: int, sale_id: int):
        """Sale lines of an online-store order."""
        from models.sale import SaleLine

        return SaleLine.query.filter_by(sale_id=sale_id, tenant_id=tenant_id).all()

    @staticmethod
    def online_order_by_number(tenant_id: int, order_number: str):
        """Online-store order by sale number or None."""
        from models import Sale

        return Sale.query.filter_by(
            tenant_id=tenant_id,
            sale_number=order_number,
            source="online_store",
        ).first()
