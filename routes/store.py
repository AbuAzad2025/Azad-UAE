from decimal import Decimal

import os

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Product, Sale, TenantStore, ShopCustomerAccount
from services.stock_service import StockService
from services.store_analytics_service import StoreAnalyticsService
from services.store_coupon_service import StoreCouponService
from services.store_order_service import StoreOrderService
from services.store_payment_method_service import StorePaymentMethodService
from services.store_service import StoreService
from utils.decorators import permission_required
from utils.error_messages import ErrorMessages
from services.logging_core import LoggingCore
from utils.helpers import save_uploaded_file
from utils.tenanting import get_active_tenant_id

store_bp = Blueprint('store', __name__, url_prefix='/store')


def _tenant_id():
    tid = get_active_tenant_id(current_user)
    if tid is None:
        abort(403)
    return int(tid)


@store_bp.route('/admin')
@login_required
@permission_required('manage_store')
def admin_index():
    tenant_id = _tenant_id()
    store = StoreService.get_tenant_store(tenant_id, create=True)
    online_wh = StoreService.get_online_warehouse(tenant_id, create=False)
    visible_count = StoreService.count_visible_products(tenant_id) if online_wh else 0
    stock_map = StoreService.online_stock_map(tenant_id) if online_wh else {}
    total_units = sum((qty for qty in stock_map.values()), Decimal('0'))
    platform_stores_on = StoreService.stores_globally_enabled()
    pending_orders = StoreOrderService.order_counts(tenant_id)['pending']
    low_stock = StoreAnalyticsService.low_stock_products(tenant_id)
    stats = StoreAnalyticsService.order_stats(tenant_id)

    return render_template(
        'store/admin_index.html',
        store=store,
        online_warehouse=online_wh,
        visible_count=visible_count,
        total_units=total_units,
        platform_stores_on=platform_stores_on,
        pending_orders=pending_orders,
        low_stock=low_stock,
        stats=stats,
    )


@store_bp.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@permission_required('manage_store')
def admin_settings():
    tenant_id = _tenant_id()
    store = StoreService.ensure_tenant_store(tenant_id)
    online_wh = StoreService.ensure_online_warehouse(tenant_id)
    if store.warehouse_id != online_wh.id:
        store.warehouse_id = online_wh.id

    if request.method == 'POST':
        try:
            is_enabled = request.form.get('is_enabled') == 'on'
            if store.platform_disabled and is_enabled:
                is_enabled = False
                flash('تم تعطيل هذا المتجر من قبل مالك المنصة، ولا يمكنك تفعيله.', 'warning')
            title = (request.form.get('title') or '').strip()
            tagline = (request.form.get('tagline') or '').strip()
            phone = (request.form.get('phone') or '').strip()
            whatsapp = (request.form.get('whatsapp') or '').strip()
            email = (request.form.get('email') or '').strip()
            slug_raw = request.form.get('store_slug') or store.store_slug
            slug = StoreService.validate_slug(slug_raw)
            slug = StoreService.ensure_unique_slug(slug, tenant_id=tenant_id)

            if is_enabled and not title:
                raise ValueError('عنوان المتجر مطلوب عند التفعيل.')

            store.is_enabled = is_enabled
            store.store_slug = slug
            store.title = title or store.title
            store.tagline = tagline or None
            store.phone = phone or None
            store.whatsapp = whatsapp or None
            store.email = email or None
            store.warehouse_id = online_wh.id

            min_raw = (request.form.get('min_order_amount') or '').strip()
            if min_raw:
                store.min_order_amount = Decimal(min_raw)
            else:
                store.min_order_amount = None
            store.delivery_note = (request.form.get('delivery_note') or '').strip() or None

            store.meta_title = (request.form.get('meta_title') or '').strip() or None
            store.meta_description = (request.form.get('meta_description') or '').strip() or None
            store.meta_keywords = (request.form.get('meta_keywords') or '').strip() or None
            store.meta_title_en = (request.form.get('meta_title_en') or '').strip() or None
            store.meta_description_en = (request.form.get('meta_description_en') or '').strip() or None
            store.return_policy_ar = (request.form.get('return_policy_ar') or '').strip() or None
            store.return_policy_en = (request.form.get('return_policy_en') or '').strip() or None
            store.notify_whatsapp_on_order = request.form.get('notify_whatsapp_on_order') == 'on'
            store.notify_email_on_order = request.form.get('notify_email_on_order') == 'on'

            threshold_raw = (request.form.get('low_stock_threshold') or '').strip()
            store.low_stock_threshold = Decimal(threshold_raw) if threshold_raw else Decimal('5')

            subdomain_raw = (request.form.get('subdomain') or '').strip()
            if subdomain_raw:
                subdomain = StoreService.normalize_subdomain(subdomain_raw)
                store.subdomain = StoreService.ensure_unique_subdomain(subdomain, tenant_id=tenant_id)
            else:
                store.subdomain = None

            custom_domain = (request.form.get('custom_domain') or '').strip().lower()
            if custom_domain:
                clash = TenantStore.query.filter(
                    TenantStore.custom_domain == custom_domain,
                    TenantStore.tenant_id != tenant_id,
                ).first()
                if clash:
                    raise ValueError('النطاق المخصص مستخدم من متجر آخر.')
            store.custom_domain = custom_domain or None

            logo_file = request.files.get('logo')
            if logo_file and logo_file.filename:
                logo_path = save_uploaded_file(logo_file, 'uploads/store_logos', {'png', 'jpg', 'jpeg', 'webp', 'gif'})
                if logo_path:
                    store.logo_path = logo_path

            db.session.commit()
            LoggingCore.log_audit('update', 'tenant_stores', store.id)
            flash('تم حفظ إعدادات المتجر.', 'success')
            return redirect(url_for('store.admin_index'))
        except ValueError as exc:
            db.session.rollback()
            current_app.logger.warning(f"ValueError in store settings: {exc}")
            flash(str(exc), 'warning')
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f"Error saving store settings: {exc}")
            flash(ErrorMessages.action_failed('حفظ الإعدادات'), 'danger')

    return render_template(
        'store/admin_settings.html',
        store=store,
        online_warehouse=online_wh,
    )


@store_bp.route('/admin/catalog')
@login_required
@permission_required('manage_store')
def admin_catalog():
    tenant_id = _tenant_id()
    store = StoreService.get_tenant_store(tenant_id, create=True)
    online_wh = StoreService.get_online_warehouse(tenant_id, create=False)
    include_zero = request.args.get('all') == '1'
    products, stock_map = StoreService.get_catalog_products(tenant_id, include_zero=include_zero)

    rows = []
    for product in products:
        qty = stock_map.get(product.id, Decimal('0'))
        rows.append({'product': product, 'quantity': qty})

    return render_template(
        'store/admin_catalog.html',
        store=store,
        online_warehouse=online_wh,
        rows=rows,
        include_zero=include_zero,
    )


@store_bp.route('/admin/transfer', methods=['GET', 'POST'])
@login_required
@permission_required('manage_store')
def admin_transfer():
    tenant_id = _tenant_id()
    store = StoreService.ensure_tenant_store(tenant_id)
    online_wh = StoreService.ensure_online_warehouse(tenant_id)
    physical_warehouses = StoreService.get_physical_warehouses(tenant_id, user=current_user)

    products = (
        Product.query.filter_by(tenant_id=tenant_id, is_active=True)
        .order_by(Product.name.asc())
        .all()
    )

    if request.method == 'POST':
        try:
            direction = request.form.get('direction', 'to_online')
            product_id = request.form.get('product_id', type=int)
            source_id = request.form.get('source_warehouse_id', type=int)
            quantity = request.form.get('quantity', type=float)
            notes = (request.form.get('notes') or '').strip()

            if not product_id or not quantity or quantity <= 0:
                raise ValueError('اختر منتجاً وكمية صحيحة.')

            product = Product.query.filter_by(id=product_id, tenant_id=tenant_id).first()
            if not product:
                raise ValueError('المنتج غير موجود.')

            if direction == 'to_online':
                if not source_id:
                    raise ValueError('اختر المستودع المصدر.')
                from_id, to_id = source_id, online_wh.id
                label = notes or 'نشر للمتجر — تحويل إلى مستودع أونلاين'
            else:
                if not source_id:
                    source_id = online_wh.id
                from_id, to_id = online_wh.id, source_id
                label = notes or 'سحب من المتجر — تحويل من مستودع أونلاين'

            StockService.transfer_stock(
                product_id=product_id,
                from_warehouse_id=from_id,
                to_warehouse_id=to_id,
                quantity=quantity,
                notes=label,
            )
            db.session.commit()
            LoggingCore.log_audit('transfer', 'stock_movements', product_id)
            flash('تم تحويل المخزون بنجاح.', 'success')
            return redirect(url_for('store.admin_catalog'))
        except ValueError as exc:
            db.session.rollback()
            current_app.logger.warning(f"ValueError in stock transfer: {exc}")
            flash(str(exc), 'warning')
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f"Error transferring stock: {exc}")
            flash(ErrorMessages.action_failed('تحويل المخزون'), 'danger')

    online_stock = StoreService.online_stock_map(tenant_id, [p.id for p in products])

    return render_template(
        'store/admin_transfer.html',
        store=store,
        online_warehouse=online_wh,
        physical_warehouses=physical_warehouses,
        products=products,
        online_stock=online_stock,
    )


@store_bp.route('/admin/orders')
@login_required
@permission_required('manage_store')
def admin_orders():
    tenant_id = _tenant_id()
    store = StoreService.get_tenant_store(tenant_id, create=True)
    page = request.args.get('page', 1, type=int)
    status_filter = (request.args.get('status') or '').strip().lower()
    per_page = 20
    query = (
        Sale.query.filter_by(tenant_id=tenant_id, source='online_store')
        .order_by(Sale.sale_date.desc())
    )
    if status_filter in StoreOrderService.STORE_ORDER_STATUSES:
        query = query.filter_by(status=status_filter)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    payment_methods = {
        m.code: m for m in StorePaymentMethodService.list_all()
    }
    return render_template(
        'store/admin_orders.html',
        store=store,
        orders=pagination.items,
        pagination=pagination,
        status_filter=status_filter,
        order_counts=StoreOrderService.order_counts(tenant_id),
        payment_methods=payment_methods,
        status_labels=StoreOrderService.STATUS_LABELS_AR,
    )


@store_bp.route('/admin/orders/<int:order_id>')
@login_required
@permission_required('manage_store')
def admin_order_detail(order_id):
    tenant_id = _tenant_id()
    store = StoreService.get_tenant_store(tenant_id, create=True)
    sale = StoreOrderService.get_tenant_order(tenant_id, order_id)
    if not sale:
        abort(404)
    pay_method = StorePaymentMethodService.get_by_code(sale.checkout_payment_method or 'cod')
    stock_issues = []
    if sale.status == 'pending' and not StoreOrderService.is_fulfilled(sale):
        stock_issues = StoreOrderService.validate_stock_for_order(sale)
    from services.store_notification_service import StoreNotificationService
    wa_admin = StoreNotificationService.whatsapp_admin_link(sale, store) if sale.status == 'pending' else None
    return render_template(
        'store/admin_order_detail.html',
        store=store,
        order=sale,
        pay_method=pay_method,
        stock_issues=stock_issues,
        is_fulfilled=StoreOrderService.is_fulfilled(sale),
        status_label=StoreOrderService.status_label(sale.status),
        wa_admin_url=wa_admin,
    )


@store_bp.route('/admin/orders/<int:order_id>/confirm', methods=['POST'])
@login_required
@permission_required('manage_store')
def admin_order_confirm(order_id):
    tenant_id = _tenant_id()
    sale = StoreOrderService.get_tenant_order(tenant_id, order_id)
    if not sale:
        abort(404)
    mark_paid = request.form.get('mark_paid') == 'on'
    try:
        StoreOrderService.confirm_order(sale, mark_paid=mark_paid)
        LoggingCore.log_audit('confirm', 'store_orders', sale.id)
        flash(f'تم تأكيد الطلب {sale.sale_number}.', 'success')
    except ValueError as exc:
        db.session.rollback()
        current_app.logger.warning(f"ValueError confirming order {order_id}: {exc}")
        flash(str(exc), 'warning')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"Error confirming order {order_id}: {exc}")
        flash(ErrorMessages.action_failed('تأكيد الطلب'), 'danger')
    return redirect(url_for('store.admin_order_detail', order_id=order_id))


@store_bp.route('/admin/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
@permission_required('manage_store')
def admin_order_cancel(order_id):
    tenant_id = _tenant_id()
    sale = StoreOrderService.get_tenant_order(tenant_id, order_id)
    if not sale:
        abort(404)
    try:
        StoreOrderService.cancel_order(sale)
        LoggingCore.log_audit('cancel', 'store_orders', sale.id)
        flash(f'تم إلغاء الطلب {sale.sale_number}.', 'success')
    except ValueError as exc:
        db.session.rollback()
        current_app.logger.warning(f"ValueError cancelling order {order_id}: {exc}")
        flash(str(exc), 'warning')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"Error cancelling order {order_id}: {exc}")
        flash(ErrorMessages.action_failed('إلغاء الطلب'), 'danger')
    return redirect(url_for('store.admin_order_detail', order_id=order_id))


@store_bp.route('/admin/customers')
@login_required
@permission_required('manage_store')
def admin_customers():
    tenant_id = _tenant_id()
    store = StoreService.get_tenant_store(tenant_id, create=True)
    accounts = (
        ShopCustomerAccount.query.filter_by(tenant_id=tenant_id)
        .order_by(ShopCustomerAccount.created_at.desc())
        .limit(200)
        .all()
    )
    return render_template('store/admin_customers.html', store=store, accounts=accounts)


@store_bp.route('/admin/stats')
@login_required
@permission_required('manage_store')
def admin_stats():
    tenant_id = _tenant_id()
    store = StoreService.get_tenant_store(tenant_id, create=True)
    stats = StoreAnalyticsService.order_stats(tenant_id)
    top_products = StoreAnalyticsService.top_products(tenant_id, limit=10)
    chart = StoreAnalyticsService.daily_orders_chart(tenant_id, days=14)
    low_stock = StoreAnalyticsService.low_stock_products(tenant_id)
    return render_template(
        'store/admin_stats.html',
        store=store,
        stats=stats,
        top_products=top_products,
        chart=chart,
        low_stock=low_stock,
    )


@store_bp.route('/admin/coupons', methods=['GET', 'POST'])
@login_required
@permission_required('manage_store')
def admin_coupons():
    tenant_id = _tenant_id()
    store = StoreService.get_tenant_store(tenant_id, create=True)

    if request.method == 'POST':
        action = request.form.get('action', 'create')
        try:
            if action == 'create':
                StoreCouponService.create_coupon(tenant_id, {
                    'code': request.form.get('code'),
                    'description': request.form.get('description'),
                    'discount_percent': request.form.get('discount_percent'),
                    'discount_amount': request.form.get('discount_amount'),
                    'min_order_amount': request.form.get('min_order_amount'),
                    'max_uses': request.form.get('max_uses'),
                    'is_active': request.form.get('is_active') == 'on',
                })
                flash('تم إنشاء الكوبون.', 'success')
            elif action == 'toggle':
                coupon_id = request.form.get('coupon_id', type=int)
                enabled = request.form.get('enabled') == '1'
                StoreCouponService.update_coupon(coupon_id, tenant_id, {'is_active': enabled})
                flash('تم تحديث الكوبون.', 'success')
        except ValueError as exc:
            current_app.logger.warning(f"ValueError in coupon operation: {exc}")
            flash(str(exc), 'warning')
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f"Error in coupon operation: {exc}")
            flash(ErrorMessages.action_failed('العملية على الكوبون'), 'danger')
        return redirect(url_for('store.admin_coupons'))

    coupons = StoreCouponService.list_for_tenant(tenant_id)
    return render_template('store/admin_coupons.html', store=store, coupons=coupons)
