from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models import Product, StockMovement, Warehouse, Branch
from services.stock_service import StockService
from utils.decorators import permission_required, admin_required, branch_scope_id
from utils.error_messages import ErrorMessages
from flask import abort
from decimal import Decimal
from utils.branching import (
    get_accessible_warehouses,
    get_accessible_branches_query,
    get_accessible_warehouse_ids,
    get_branch_stock_map,
    ensure_warehouse_access,
    should_show_all_branch_columns,
)
from utils.tenanting import tenant_get_or_404, tenant_query
from utils.tenanting import scoped_user_query, get_active_tenant_id
from utils.db_safety import atomic_transaction
from utils.structured_logging import log_mutation

warehouse_bp = Blueprint('warehouse', __name__, url_prefix='/warehouse')


def _annotate_visible_stock(products):
    warehouse_ids = get_accessible_warehouse_ids(current_user)
    stock_map = {}
    if warehouse_ids:
        stock_map = get_branch_stock_map(
            product_ids=[product.id for product in products],
            warehouse_ids=warehouse_ids,
        )

    for product in products:
        if warehouse_ids:
            product.visible_stock = stock_map.get(product.id, Decimal('0'))
        else:
            product.visible_stock = product.current_stock or Decimal('0')
    return products


@warehouse_bp.route('/')
@login_required
@permission_required('manage_warehouse')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search = request.args.get('search', '', type=str)
    category_id = request.args.get('category', type=int)
    stock_filter = request.args.get('stock', '', type=str)

    query = StockService.get_visible_products_query(current_user)
    
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                Product.name.ilike(search_filter),
                Product.sku.ilike(search_filter),
                Product.barcode.ilike(search_filter)
            )
        )
    
    if category_id:
        query = query.filter_by(category_id=category_id)

    products = query.order_by(Product.name).all()
    _annotate_visible_stock(products)

    if stock_filter == 'low':
        products = [product for product in products if 0 < (product.visible_stock or 0) <= (product.min_stock_alert or 0)]
    elif stock_filter == 'out':
        products = [product for product in products if (product.visible_stock or 0) <= 0]

    total = len(products)
    summary = {
        'total_products': total,
        'good_stock': sum(1 for product in products if (product.visible_stock or 0) > (product.min_stock_alert or 0)),
        'low_stock': sum(1 for product in products if 0 < (product.visible_stock or 0) <= (product.min_stock_alert or 0)),
        'out_of_stock': sum(1 for product in products if (product.visible_stock or 0) <= 0),
    }

    start = (page - 1) * per_page
    end = start + per_page
    page_items = products[start:end]

    class _Pagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page if per_page else 0
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1
            self.next_num = page + 1

        def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
            last = 0
            for num in range(1, self.pages + 1):
                if (
                    num <= left_edge
                    or (self.page - left_current - 1 < num < self.page + right_current)
                    or num > self.pages - right_edge
                ):
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    pagination = _Pagination(page_items, page, per_page, total)

    return render_template('warehouse/index.html',
                         products=page_items,
                         pagination=pagination,
                         summary=summary)


@warehouse_bp.route('/movements')
@login_required
@permission_required('manage_warehouse')
def movements():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    product_id = request.args.get('product', type=int)
    movement_type = request.args.get('type', '', type=str)
    warehouse_id = request.args.get('warehouse', type=int)
    
    branch_id = branch_scope_id()
    tid = get_active_tenant_id(current_user)
    if branch_id is not None:
        wh_query = Warehouse.query.filter_by(is_active=True, branch_id=branch_id)
        if tid is not None:
            wh_query = wh_query.filter(Warehouse.tenant_id == tid)
        warehouse_ids = [w.id for w in wh_query.all()]
        if not warehouse_ids:
            warehouse_ids = [-1]
    else:
        warehouse_ids = None
    
    query = StockMovement.query
    if tid is not None:
        query = query.filter(StockMovement.tenant_id == tid)
    if warehouse_ids is not None:
        query = query.filter(StockMovement.warehouse_id.in_(warehouse_ids))
    
    if product_id:
        query = query.filter_by(product_id=product_id)
    
    if movement_type:
        query = query.filter_by(movement_type=movement_type)

    if warehouse_id:
        query = query.filter_by(warehouse_id=warehouse_id)
        current_warehouse = Warehouse.query.filter_by(id=warehouse_id, tenant_id=get_active_tenant_id(current_user)).first()
        if branch_id is not None and (not current_warehouse or current_warehouse.branch_id != branch_id):
            abort(403)
    else:
        current_warehouse = None
    
    pagination = query.order_by(StockMovement.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    warehouses = tenant_query(Warehouse).filter_by(is_active=True).order_by(Warehouse.name).all()
    if branch_id is not None:
        warehouses = [w for w in warehouses if w.branch_id == branch_id]
    
    return render_template('warehouse/movements.html',
                         movements=pagination.items,
                         pagination=pagination,
                         warehouses=warehouses,
                         current_warehouse=current_warehouse)


@warehouse_bp.route('/low-stock')
@login_required
@permission_required('manage_warehouse')
def low_stock():
    products = StockService.get_low_stock_products()
    return render_template('warehouse/low_stock.html', products=products)


@warehouse_bp.route('/out-of-stock')
@login_required
@permission_required('manage_warehouse')
def out_of_stock():
    products = StockService.get_out_of_stock_products()
    return render_template('warehouse/out_of_stock.html', products=products)


@warehouse_bp.route('/<int:id>')
@login_required
@permission_required('manage_warehouse')
def view_warehouse(id):
    warehouse = tenant_get_or_404(Warehouse, id)
    branch_id = branch_scope_id()
    if branch_id is not None and warehouse.branch_id != branch_id:
        abort(403)
    
    # Calculate stock for this warehouse from movements
    stock_query = db.session.query(
        StockMovement.product_id,
        db.func.sum(StockMovement.quantity).label('total_quantity')
    ).filter_by(warehouse_id=id).group_by(StockMovement.product_id).all()
    
    warehouse_stock = []
    for product_id, quantity in stock_query:
        # Convert quantity to float for comparison and display, handling None
        qty = float(quantity) if quantity is not None else 0.0
        if qty != 0:
            product = Product.query.filter_by(id=product_id, tenant_id=warehouse.tenant_id).first()
            if product:
                warehouse_stock.append({
                    'product': product,
                    'quantity': qty
                })
    
    return render_template('warehouse/view_warehouse.html', 
                         warehouse=warehouse, 
                         stock=warehouse_stock)


@warehouse_bp.route('/create', methods=['GET', 'POST'])
@warehouse_bp.route('/create-warehouse', methods=['GET', 'POST'])
@login_required
@admin_required
def create_warehouse():
    from models import User
    
    tid = get_active_tenant_id(current_user)
    parent_warehouses = Warehouse.query.filter_by(is_active=True, parent_id=None)
    if tid is not None:
        parent_warehouses = parent_warehouses.filter(Warehouse.tenant_id == tid)
    parent_warehouses = parent_warehouses.all()
    users = scoped_user_query(active_only=True, exclude_owners=True).all()
    branches = get_accessible_branches_query(current_user).order_by(Branch.is_main.desc(), Branch.code, Branch.name).all()
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            name_ar = request.form.get('name_ar', '').strip()
            code = request.form.get('code', '').strip()
            location = request.form.get('location', '').strip()
            parent_id = request.form.get('parent_id', type=int) or None
            manager_id = request.form.get('manager_id', type=int) or None
            branch_id = request.form.get('branch_id', type=int) or None
            is_main = request.form.get('is_main') == 'on'
            warehouse_type = request.form.get('warehouse_type') or Warehouse.TYPE_PHYSICAL
            if warehouse_type not in Warehouse.WAREHOUSE_TYPES:
                warehouse_type = Warehouse.TYPE_PHYSICAL

            tenant_id = get_active_tenant_id(current_user)
            if warehouse_type == Warehouse.TYPE_ONLINE:
                is_main = False
                parent_id = None
                if tenant_id:
                    from services.store_service import StoreService
                    StoreService.assert_single_online_warehouse(tenant_id)
                if not location:
                    location = 'Online / أونلاين'

            if not name:
                flash('اسم المستودع مطلوب', 'warning')
                return render_template('warehouse/create_warehouse.html',
                                       parent_warehouses=parent_warehouses,
                                       users=users,
                                       branches=branches,
                                       form_data=request.form)
            
            if not location:
                flash('الموقع مطلوب', 'warning')
                return render_template('warehouse/create_warehouse.html',
                                       parent_warehouses=parent_warehouses,
                                       users=users,
                                       branches=branches,
                                       form_data=request.form)
            
            if code:
                existing = Warehouse.query.filter_by(code=code, tenant_id=tenant_id).first()
                if existing:
                    flash('رمز المستودع موجود مسبقاً', 'warning')
                    return render_template('warehouse/create_warehouse.html',
                                           parent_warehouses=parent_warehouses,
                                           users=users,
                                           branches=branches,
                                           form_data=request.form)
            
            if parent_id:
                parent_warehouse = Warehouse.query.filter_by(id=parent_id, tenant_id=tenant_id).first()
                if not parent_warehouse:
                    flash('المستودع الأب غير موجود', 'warning')
                    return render_template('warehouse/create_warehouse.html',
                                           parent_warehouses=parent_warehouses,
                                           users=users,
                                           branches=branches,
                                           form_data=request.form)
                if not parent_warehouse.is_active:
                    flash('المستودع الأب غير نشط', 'warning')
                    return render_template('warehouse/create_warehouse.html',
                                           parent_warehouses=parent_warehouses,
                                           users=users,
                                           branches=branches,
                                           form_data=request.form)
            
            # Check tenant warehouse limit
            try:
                from utils.tenant_limits import check_warehouses_limit, TenantLimitError
                check_warehouses_limit()
            except TenantLimitError as e:
                flash(str(e), 'danger')
                return redirect(url_for('warehouse.create'))

            with atomic_transaction('warehouse_creation'):
                warehouse = Warehouse(
                    tenant_id=tenant_id,
                name=name,
                name_ar=name_ar,
                code=code,
                branch_id=branch_id,
                location=location,
                parent_id=parent_id,
                is_main=is_main,
                manager_id=manager_id,
                warehouse_type=warehouse_type,
                is_active=True
            )
            
            db.session.add(warehouse)
            db.session.flush()

            if warehouse_type == Warehouse.TYPE_ONLINE and tenant_id:
                from services.store_service import StoreService
                store = StoreService.get_tenant_store(tenant_id, create=True)
                if store and store.warehouse_id != warehouse.id:
                    store.warehouse_id = warehouse.id

            # (atomic_transaction ستقوم بالـ commit عند الخروج)
            
            type_label = 'أونلاين' if warehouse_type == Warehouse.TYPE_ONLINE else ('فرعي' if parent_id else 'مستقل')
            flash(f'✓ تم إنشاء المستودع ({type_label}) "{name}" بنجاح', 'success')
            return redirect(url_for('warehouse.list_warehouses'))
            
        except ValueError as e:
            db.session.rollback()
            current_app.logger.warning(f"ValueError creating warehouse: {e}")
            flash(str(e), 'warning')
            return render_template('warehouse/create_warehouse.html',
                                   parent_warehouses=parent_warehouses,
                                   users=users,
                                   branches=branches,
                                   form_data=request.form)
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating warehouse: {e}")
            flash(ErrorMessages.create_failed('warehouse'), 'error')
            return render_template('warehouse/create_warehouse.html',
                                   parent_warehouses=parent_warehouses,
                                   users=users,
                                   branches=branches,
                                   form_data=request.form)
    
    return render_template('warehouse/create_warehouse.html', 
                         parent_warehouses=parent_warehouses,
                         users=users,
                         branches=branches)


@warehouse_bp.route('/list')
@login_required
@permission_required('manage_warehouse')
def list_warehouses():
    query = tenant_query(Warehouse).filter_by(is_active=True)
    branch_id = branch_scope_id()
    if branch_id is not None:
        query = query.filter_by(branch_id=branch_id)
    warehouses = query.order_by(Warehouse.name).all()
    return render_template(
        'warehouse/list_warehouses.html',
        warehouses=warehouses,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )


@warehouse_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_warehouse(id):
    """حذف مستودع"""
    warehouse = tenant_get_or_404(Warehouse, id)
    
    # Check if main warehouse
    if warehouse.is_main:
        flash('لا يمكن حذف المستودع الرئيسي', 'danger')
        return redirect(url_for('warehouse.list_warehouses'))
        
    try:
        # Check for stock
        has_stock = StockMovement.query.filter_by(warehouse_id=id).first()
        if has_stock:
            # Soft delete
            warehouse.is_active = False
            db.session.commit()
            flash(f'تم إلغاء تفعيل المستودع "{warehouse.name}" لوجود حركات مخزنية مرتبطة به', 'warning')
        else:
            db.session.delete(warehouse)
            db.session.commit()
            flash(f'تم حذف المستودع "{warehouse.name}" بنجاح', 'success')
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting warehouse {id}: {e}")
        flash(ErrorMessages.delete_failed('warehouse'), 'danger')
        
    return redirect(url_for('warehouse.list_warehouses'))


@warehouse_bp.route('/add-stock/<int:product_id>', methods=['POST'])
@login_required
@permission_required('manage_warehouse')
def add_stock(product_id):
    try:
        product = tenant_get_or_404(Product, product_id)
        quantity = Decimal(request.form.get('quantity', 0))
        notes = request.form.get('notes', '').strip()
        warehouse_id = request.form.get('warehouse_id', type=int)
        
        if quantity <= 0:
            return jsonify({'success': False, 'message': 'الكمية يجب أن تكون أكبر من صفر'}), 400
        
        if not warehouse_id:
            accessible_query = tenant_query(Warehouse).filter_by(is_active=True)
            scoped_branch_id = branch_scope_id()
            if scoped_branch_id is not None:
                accessible_query = accessible_query.filter_by(branch_id=scoped_branch_id)

            warehouse = accessible_query.filter_by(is_main=True).first()
            if not warehouse:
                warehouse = accessible_query.order_by(Warehouse.name).first()
            if not warehouse:
                return jsonify({'success': False, 'message': 'لا يوجد مستودع نشط'}), 400
            warehouse_id = warehouse.id
        else:
            ensure_warehouse_access(warehouse_id, current_user)
        
        movement = StockService.adjust_stock(
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=quantity,
            notes=notes or 'إضافة كمية يدوية'
        )
        
        db.session.commit()
        product = movement.product
        
        return jsonify({
            'success': True,
            'message': f'تم إضافة {quantity} وحدة للمنتج {product.name}',
            'new_stock': float(product.current_stock)
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding stock: {e}")
        return jsonify({'success': False, 'message': ErrorMessages.unexpected_error()}), 500

