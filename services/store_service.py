"""Online store — tenant-bound catalog via online warehouse only (not POS)."""
from __future__ import annotations

import re
from decimal import Decimal

from extensions import db
from models import Product, Tenant, TenantStore, Warehouse, Branch
from models.system_settings import SystemSettings
from utils.branching import get_branch_stock_map, get_accessible_warehouses
from utils.tenanting import require_active_tenant_id


class StoreService:
    SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

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
            raise ValueError('الشركة غير موجودة.')

        branch = (
            Branch.query.filter_by(tenant_id=tenant_id, is_active=True)
            .order_by(Branch.is_main.desc(), Branch.id.asc())
            .first()
        )

        suffix = tenant_id
        code = f'ONLINE-{suffix}'
        name = f'Online Store WH {suffix}'
        name_ar = f'مستودع المتجر الإلكتروني ({tenant.name_ar or tenant.name})'

        if Warehouse.query.filter_by(tenant_id=tenant_id, code=code).first():
            code = f'ONLINE-T{suffix}'
        if Warehouse.query.filter_by(tenant_id=tenant_id, name=name).first():
            name = f'Online Store WH T{suffix}'

        warehouse = Warehouse(
            tenant_id=tenant_id,
            name=name,
            name_ar=name_ar,
            code=code,
            location='Online / أونلاين',
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
            raise ValueError('الشركة غير موجودة.')

        online_wh = StoreService.ensure_online_warehouse(tenant_id)
        slug = StoreService.normalize_slug(tenant.slug or f'tenant-{tenant_id}')
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
        slug = (value or '').strip().lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = re.sub(r'-{2,}', '-', slug).strip('-')
        return slug or 'store'

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
            candidate = f'{base}-{n}'
            n += 1

    @staticmethod
    def validate_slug(slug: str) -> str:
        normalized = StoreService.normalize_slug(slug)
        if not StoreService.SLUG_RE.match(normalized):
            raise ValueError('رابط المتجر يجب أن يحتوي على حروف إنجليزية صغيرة وأرقام وشرطات فقط.')
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

        products = (
            Product.query.filter_by(tenant_id=int(tenant_id), is_active=True)
            .order_by(Product.name.asc())
            .all()
        )
        stock_map = StoreService.online_stock_map(tenant_id, [p.id for p in products])

        if not include_zero:
            products = [p for p in products if (stock_map.get(p.id) or Decimal('0')) > 0]

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
            qty = stock_map.get(product.id, Decimal('0'))
            if qty <= 0:
                continue
            related.append({'product': product, 'quantity': qty})
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
            raise ValueError('يوجد مستودع أونلاين نشط بالفعل لهذه الشركة. مسموح بواحد فقط.')

    @staticmethod
    def get_physical_warehouses(tenant_id: int, *, user=None):
        warehouses = get_accessible_warehouses(user) if user else Warehouse.query.filter_by(is_active=True).all()
        return [
            wh for wh in warehouses
            if wh.tenant_id == int(tenant_id) and not wh.is_online
        ]

    @staticmethod
    def active_tenant_id_for_user(user=None) -> int:
        return StoreService.resolve_tenant_id(user)

    @staticmethod
    def stores_globally_enabled() -> bool:
        try:
            settings = SystemSettings.get_current()
            return bool(getattr(settings, 'enable_ecommerce', False))
        except Exception:
            return False

    @staticmethod
    def set_stores_globally_enabled(enabled: bool):
        settings = SystemSettings.get_current()
        settings.enable_ecommerce = bool(enabled)
        db.session.commit()

    @staticmethod
    def is_platform_locked(store: 'TenantStore | None') -> bool:
        """True when the platform owner has force-disabled this tenant store."""
        return bool(store and getattr(store, 'platform_disabled', False))

    @staticmethod
    def effective_enabled(store: 'TenantStore | None') -> bool:
        """Tenant store is effectively on only if enabled and not platform-locked."""
        return bool(store and store.is_enabled and not StoreService.is_platform_locked(store))

    @staticmethod
    def set_platform_disabled(store: 'TenantStore', disabled: bool):
        """Platform-owner only: hard force-OFF lock. Tenant cannot re-enable while locked."""
        store.platform_disabled = bool(disabled)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

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
        host = (host or '').split(':')[0].lower().strip()
        if host.startswith('www.'):
            host = host[4:]
        if not host:
            return None

        store = TenantStore.query.filter_by(custom_domain=host).first()
        if store:
            return store

        label = host.split('.')[0]
        if label and label not in ('localhost', '127', '0'):
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
            candidate = f'{base}-{n}'
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
        if not tenant or not getattr(tenant, 'is_active', True) or getattr(tenant, 'is_suspended', False):
            return False
        online_wh = db.session.get(Warehouse, store.warehouse_id)
        return bool(online_wh and online_wh.is_active and online_wh.is_online)

    @staticmethod
    def cart_session_key(tenant_id: int) -> str:
        return f'shop_cart_{int(tenant_id)}'

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
                continue
        return cleaned

    @staticmethod
    def save_cart(session, tenant_id: int, cart: dict):
        session[StoreService.cart_session_key(tenant_id)] = cart
        session.modified = True

    @staticmethod
    def get_public_catalog(tenant_id: int, *, category_id=None, search: str = None, page=1, per_page=24, sort=None, min_price=None, max_price=None, in_stock_only=False):
        """Storefront catalog — in-stock online warehouse, no serial-tracked products."""
        products, stock_map = StoreService.get_catalog_products(tenant_id, include_zero=False)
        items = []
        q = (search or '').strip().lower()
        for product in products:
            if product.has_serial_number:
                continue
            if category_id and product.category_id != int(category_id):
                continue
            if q:
                blob = f'{product.name} {product.name_ar or ""} {product.sku or ""}'.lower()
                if q not in blob:
                    continue
            qty = stock_map.get(product.id, Decimal('0'))
            if qty <= 0:
                continue
            if in_stock_only and qty <= 0:
                continue
            items.append({'product': product, 'quantity': qty})
        if min_price is not None:
            items = [i for i in items if float(i['product'].regular_price or 0) >= float(min_price)]
        if max_price is not None:
            items = [i for i in items if float(i['product'].regular_price or 0) <= float(max_price)]
        if sort == 'price_asc':
            items.sort(key=lambda x: float(x['product'].regular_price or 0))
        elif sort == 'price_desc':
            items.sort(key=lambda x: float(x['product'].regular_price or 0), reverse=True)
        elif sort == 'name_asc':
            items.sort(key=lambda x: (x['product'].get_display_name('en') or '').lower())
        elif sort == 'name_desc':
            items.sort(key=lambda x: (x['product'].get_display_name('en') or '').lower(), reverse=True)
        elif sort == 'newest':
            items.sort(key=lambda x: x['product'].created_at or '', reverse=True)
        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page
        page_items = items[start:end]
        return {'items': page_items, 'total': total, 'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page}

    @staticmethod
    def cart_totals(tenant_id: int, cart: dict) -> dict:
        lines = []
        subtotal = Decimal('0')
        stock_map = StoreService.online_stock_map(tenant_id, [int(k) for k in cart.keys()] if cart else None)
        for pid, qty_raw in cart.items():
            product = Product.query.filter_by(id=int(pid), tenant_id=int(tenant_id), is_active=True).first()
            if not product:
                continue
            qty = Decimal(str(qty_raw))
            max_q = stock_map.get(product.id, Decimal('0'))
            if qty > max_q:
                qty = max_q
            if qty <= 0:
                continue
            line_total = Decimal(str(product.regular_price or 0)) * qty
            subtotal += line_total
            lines.append({'product': product, 'quantity': qty, 'line_total': line_total})
        return {'lines': lines, 'subtotal': subtotal, 'count': sum(l['quantity'] for l in lines)}

    @staticmethod
    def get_recently_viewed_products(tenant_id: int, product_ids: list, exclude_id: int | None = None, limit: int = 6):
        if not product_ids:
            return []
        ids = [pid for pid in product_ids if pid != exclude_id]
        ids = ids[:limit]
        products = Product.query.filter(
            Product.id.in_(ids),
            Product.tenant_id == int(tenant_id),
            Product.is_active == True,
        ).all()
        product_map = {p.id: p for p in products}
        ordered = [product_map[pid] for pid in ids if pid in product_map]
        return ordered

    @staticmethod
    def get_product_variants(tenant_id: int, product_id: int):
        from models.shop_product_variant import ShopProductVariant
        return ShopProductVariant.query.filter_by(
            tenant_id=int(tenant_id),
            product_id=int(product_id),
            is_active=True,
        ).order_by(ShopProductVariant.sort_order.asc()).all()

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
            lp = ShopLoyalty(tenant_id=int(tenant_id), account_id=int(account_id), points=0, points_earned=0, points_redeemed=0)
            db.session.add(lp)
        lp.points = (lp.points or 0) + points_earned
        lp.points_earned = (lp.points_earned or 0) + points_earned
        txn = ShopLoyaltyTransaction(tenant_id=int(tenant_id), account_id=int(account_id), sale_id=sale_id, points=points_earned, reason='order')
        db.session.add(txn)

    @staticmethod
    def redeem_loyalty_points(tenant_id: int, account_id: int, points: int):
        from models.shop_loyalty import ShopLoyalty, ShopLoyaltyTransaction
        lp = ShopLoyalty.query.filter_by(account_id=int(account_id)).first()
        if not lp or (lp.points or 0) < points:
            raise ValueError('Insufficient loyalty points')
        lp.points = (lp.points or 0) - points
        lp.points_redeemed = (lp.points_redeemed or 0) + points
        txn = ShopLoyaltyTransaction(tenant_id=int(tenant_id), account_id=int(account_id), points=-points, reason='redeem')
        db.session.add(txn)
        return Decimal(points) / Decimal('100')
