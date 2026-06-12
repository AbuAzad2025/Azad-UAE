from io import BytesIO
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy import select
from extensions import db, limiter
from models import Product, ProductCategory, Customer, ProductPartner, StockMovement
from utils.decorators import permission_required, any_permission_required
from utils.decorators import branch_scope_id
from utils.branching import (
    ensure_warehouse_access,
    get_accessible_warehouse_ids,
    get_accessible_warehouses,
    get_branch_stock_map,
    should_show_all_branch_columns,
)
from services.logging_core import LoggingCore
from utils.helpers import generate_sku, generate_barcode, save_uploaded_file
from utils.static_asset_paths import tenant_upload_dir
from services.stock_service import StockService
from utils.gl_reference_types import GLRef
from utils.tenanting import tenant_query, tenant_get_or_404, assign_tenant_id, get_active_tenant_id

products_bp = Blueprint('products', __name__, url_prefix='/products')


def _scoped_customers_query(customer_type=None):
    from models import Payment, Receipt, Sale

    query = tenant_query(Customer).filter(Customer.is_active == True)
    if customer_type:
        query = query.filter(Customer.customer_type == customer_type)

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        return query

    sale_ids = select(Sale.customer_id).where(
        Sale.customer_id.isnot(None),
        Sale.branch_id == scoped_branch_id,
    )
    payment_ids = select(Payment.customer_id).where(
        Payment.customer_id.isnot(None),
        Payment.branch_id == scoped_branch_id,
    )
    receipt_ids = select(Receipt.customer_id).where(
        Receipt.customer_id.isnot(None),
        Receipt.branch_id == scoped_branch_id,
    )
    return query.filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))


def _ensure_product_scope(product):
    """Tenant isolation is enforced by tenant_get_or_404 on CRUD routes.

    Branch stock visibility (get_visible_products_query) applies to listings,
    POS, and warehouse pickers — not to product master view/edit/delete.
    """
    return product

def _parse_product_partners(form):
    raw_partner_ids = form.getlist('partner_customer_id[]')
    raw_percentages = form.getlist('partner_percentage[]')
    count = max(len(raw_partner_ids), len(raw_percentages))
    
    seen_partner_ids = set()
    partners = []
    total = 0.0
    
    for i in range(count):
        partner_id_raw = (raw_partner_ids[i] if i < len(raw_partner_ids) else '') or ''
        percentage_raw = (raw_percentages[i] if i < len(raw_percentages) else '') or ''
        
        partner_id_raw = partner_id_raw.strip()
        percentage_raw = percentage_raw.strip()
        
        if not partner_id_raw and not percentage_raw:
            continue
        
        if not partner_id_raw or not percentage_raw:
            return None, '⚠️ يرجى اختيار الشريك وإدخال نسبته في كل سطر.'
        
        try:
            partner_id = int(partner_id_raw)
        except Exception:
            return None, '⚠️ الشريك المحدد غير صالح.'
        
        try:
            percentage = float(percentage_raw)
        except Exception:
            return None, '⚠️ نسبة الشريك غير صحيحة.'
        
        if percentage <= 0 or percentage > 100:
            return None, '⚠️ نسبة الشريك يجب أن تكون بين 0 و 100.'
        
        if partner_id in seen_partner_ids:
            return None, '⚠️ لا يمكن تكرار نفس الشريك أكثر من مرة لنفس المنتج.'
        
        partner_customer = _scoped_customers_query('partner').filter(Customer.id == partner_id).first()
        if not partner_customer:
            return None, '⚠️ الشريك المحدد غير موجود أو غير مُعرّف كـ شريك.'
        
        seen_partner_ids.add(partner_id)
        total += percentage
        partners.append({'partner_customer_id': partner_id, 'percentage': percentage})
    
    if total > 100.000001:
        return None, '⚠️ مجموع نسب الشركاء لا يمكن أن يتجاوز 100%.'
    
    return partners, None


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
            product.visible_stock = stock_map.get(product.id, 0)
        else:
            product.visible_stock = product.current_stock or 0
    return products


def _annotate_branch_and_warehouse_info(products, warehouse_ids):
    """
    For all-branches views, annotate each product with visible warehouse names
    and branch names based on accessible stock movements.
    """
    if not products:
        return products

    from models import Warehouse, Branch

    for product in products:
        product.visible_warehouse_names = []
        product.visible_branch_names = []

    if not warehouse_ids:
        return products

    product_ids = [p.id for p in products]
    rows = (
        db.session.query(
            StockMovement.product_id,
            Warehouse.name,
            Warehouse.name_ar,
            Branch.name,
            Branch.code,
        )
        .join(Warehouse, Warehouse.id == StockMovement.warehouse_id)
        .outerjoin(Branch, Branch.id == Warehouse.branch_id)
        .filter(StockMovement.product_id.in_(product_ids))
        .filter(StockMovement.warehouse_id.in_(warehouse_ids))
        .all()
    )

    by_product = {}
    for product_id, wh_name, wh_name_ar, branch_name, branch_code in rows:
        bucket = by_product.setdefault(product_id, {"warehouses": set(), "branches": set()})
        if wh_name_ar or wh_name:
            bucket["warehouses"].add((wh_name_ar or wh_name).strip())
        if branch_name:
            branch_label = f"{branch_name} ({branch_code})" if branch_code else branch_name
            bucket["branches"].add(branch_label.strip())

    for product in products:
        info = by_product.get(product.id, {"warehouses": set(), "branches": set()})
        product.visible_warehouse_names = sorted(info["warehouses"])
        product.visible_branch_names = sorted(info["branches"])

    return products


@products_bp.route('/import-template')
@login_required
@permission_required('manage_products')
def download_import_template():
    """Generate and return Excel template for product import."""
    try:
        import pandas as pd
        df = pd.DataFrame(columns=[
            'اسم المنتج', 'السعر', 'التكلفة', 'الكمية', 'SKU', 'الباركود', 'الوصف', 'التصنيف', 'مدة الكفالة'
        ])
        df.loc[0] = ['', 0, 0, 0, '', '', '', '', 0]
        output = BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='product_import_template.xlsx'
        )
    except Exception as e:
        current_app.logger.warning('Import template generation failed: %s', e)
        return redirect(url_for('products.import_products'))


@products_bp.route('/import', methods=['GET', 'POST'])
@login_required
@permission_required('manage_products')
def import_products():
    import pandas as pd
    from werkzeug.utils import secure_filename
    import os
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('⚠️ لم يتم اختيار ملف', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('⚠️ لم يتم اختيار ملف', 'danger')
            return redirect(request.url)
        
        if file:
            filepath = None
            try:
                import uuid
                ext = os.path.splitext(secure_filename(file.filename))[1].lower()
                if ext not in ('.csv', '.xlsx', '.xls'):
                    flash('⚠️ نوع الملف غير مدعوم', 'danger')
                    return redirect(request.url)
                filename = f"import_{uuid.uuid4().hex}{ext}"
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Read file
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath)
                else:
                    df = pd.read_excel(filepath)
                
                # Process Data
                success_count = 0
                error_count = 0
                errors = []
                
                required_cols = ['name', 'price'] # Minimal requirements
                # Check columns (case insensitive)
                df.columns = df.columns.str.lower().str.strip()
                
                # Mapping Arabic headers to English if needed
                column_map = {
                    'اسم المنتج': 'name',
                    'السعر': 'price',
                    'سعر البيع': 'price',
                    'التكلفة': 'cost',
                    'الكمية': 'stock',
                    'المخزون': 'stock',
                    'الباركود': 'barcode',
                    'sku': 'sku',
                    'الوصف': 'description',
                    'التصنيف': 'category',
                    'الكفالة': 'warranty',
                    'مدة الكفالة': 'warranty'
                }
                df.rename(columns=column_map, inplace=True)
                
                # Validate minimal columns
                if not set(['name', 'price']).issubset(df.columns):
                    flash('⚠️ الملف يفتقد للأعمدة المطلوبة: اسم المنتج، السعر', 'danger')
                    return redirect(request.url)
                
                # Default Warehouse
                from models import Warehouse, ProductCategory
                tid = get_active_tenant_id(current_user)
                warehouse = Warehouse.query.filter_by(is_active=True, is_main=True, tenant_id=tid).first()
                if not warehouse:
                    warehouse = Warehouse.query.filter_by(tenant_id=tid).first()
                
                for index, row in df.iterrows():
                    try:
                        name = str(row['name']).strip()
                        if not name or pd.isna(name): continue
                        
                        price = float(row['price']) if not pd.isna(row['price']) else 0.0
                        cost = float(row.get('cost', 0)) if not pd.isna(row.get('cost')) else 0.0
                        stock = float(row.get('stock', 0)) if not pd.isna(row.get('stock')) else 0.0
                        
                        # Handle Warranty
                        warranty_days = 0
                        warranty_raw = row.get('warranty', 0)
                        if not pd.isna(warranty_raw):
                            try:
                                warranty_days = int(float(warranty_raw))
                            except (ValueError, TypeError):
                                warranty_days = 0
                        
                        sku = str(row.get('sku', '')).strip()
                        if pd.isna(sku) or not sku:
                            sku = generate_sku() # Auto-generate
                        
                        barcode = str(row.get('barcode', '')).strip()
                        if pd.isna(barcode) or not barcode:
                            # Auto-generate barcode if missing (using SKU or random)
                            barcode = sku 
                        
                        # Check existing (per-tenant)
                        from utils.tenanting import get_active_tenant_id

                        tid = get_active_tenant_id()
                        dup_q = Product.query.filter(
                            (Product.sku == sku) | (Product.barcode == barcode)
                        )
                        if tid is not None:
                            dup_q = dup_q.filter(Product.tenant_id == tid)
                        existing = dup_q.first()
                        
                        if existing:
                            if request.form.get('update_existing'):
                                # Update logic
                                existing.name = name
                                existing.regular_price = price
                                existing.cost_price = cost
                                existing.warranty_days = warranty_days
                                # Stock update is tricky - usually we add adjustment or overwrite
                                # For simplicity in import: Overwrite if stock provided
                                if stock > 0:
                                     # Calculate diff
                                     diff = stock - float(existing.current_stock)
                                     if diff != 0:
                                         StockService.adjust_stock(existing.id, diff, "Import Update", warehouse.id if warehouse else None)
                                success_count += 1
                            else:
                                error_count += 1
                                errors.append(f"المنتج {name} موجود مسبقاً (SKU: {sku})")
                            continue
                        
                        # Create New
                        category_name = str(row.get('category', '')).strip()
                        category_id = None
                        if category_name and not pd.isna(category_name) and category_name.lower() != 'nan':
                            cat = ProductCategory.query.filter_by(tenant_id=tid).filter(ProductCategory.name.ilike(category_name)).first()
                            if cat:
                                category_id = cat.id
                            else:
                                # Create category on fly? Or skip. Let's create.
                                new_cat = ProductCategory(name=category_name)
                                assign_tenant_id(new_cat, current_user)
                                db.session.add(new_cat)
                                db.session.flush()
                                category_id = new_cat.id
                        
                        new_product = Product(
                            name=name,
                            sku=sku,
                            barcode=barcode,
                            regular_price=price,
                            cost_price=cost,
                            category_id=category_id,
                            warranty_days=warranty_days,
                            current_stock=0 # Will adjust via service
                        )
                        assign_tenant_id(new_product, current_user)
                        db.session.add(new_product)
                        db.session.flush()
                        
                        if stock > 0:
                            StockService.add_opening_stock(
                                product_id=new_product.id,
                                quantity=stock,
                                notes='مخزون افتتاحي من استيراد ملف',
                                warehouse_id=warehouse.id if warehouse else None,
                            )
                        
                        success_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        errors.append(f"خطأ في السطر {index+2}: {str(e)}")
                
                db.session.commit()
                
                if success_count > 0:
                    flash(f'✅ تم استيراد {success_count} منتج بنجاح.', 'success')
                
                if error_count > 0:
                    flash(f'⚠️ فشل استيراد {error_count} منتج. راجع السجلات.', 'warning')
                    # Could log errors to file/session to show user
                
                return redirect(url_for('products.index'))
                
            except Exception as e:
                flash(f'❌ حدث خطأ أثناء معالجة الملف: {str(e)}', 'danger')
                current_app.logger.error(f"Import Failed: {e}")
            finally:
                if filepath and os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
    
    return render_template('products/import.html')


@products_bp.route('/import-grid', methods=['POST'])
@login_required
@permission_required('manage_products')
def import_grid():
    names = request.form.getlist('name[]')
    prices = request.form.getlist('price[]')
    costs = request.form.getlist('cost[]')
    stocks = request.form.getlist('stock[]')
    skus = request.form.getlist('sku[]')
    barcodes = request.form.getlist('barcode[]')
    
    count = 0
    errors = 0
    
    from models import Warehouse
    tid = get_active_tenant_id(current_user)
    warehouse = Warehouse.query.filter_by(is_active=True, is_main=True, tenant_id=tid).first()
    if not warehouse:
        warehouse = Warehouse.query.filter_by(tenant_id=tid).first()
    
    for i in range(len(names)):
        name = names[i].strip()
        if not name: continue
        
        try:
            price = float(prices[i]) if i < len(prices) and prices[i] else 0.0
            cost = float(costs[i]) if i < len(costs) and costs[i] else 0.0
            stock = float(stocks[i]) if i < len(stocks) and stocks[i] else 0.0
            
            sku = skus[i].strip() if i < len(skus) else ''
            if not sku: sku = generate_sku()
            
            barcode = barcodes[i].strip() if i < len(barcodes) else ''
            if not barcode: barcode = sku
            
            # Create
            new_product = Product(
                name=name,
                sku=sku,
                barcode=barcode,
                regular_price=price,
                cost_price=cost,
                current_stock=0
            )
            assign_tenant_id(new_product, current_user)
            db.session.add(new_product)
            db.session.flush()
            
            if stock > 0:
                StockService.add_opening_stock(
                    product_id=new_product.id,
                    quantity=stock,
                    notes='مخزون افتتاحي من إدخال سريع',
                    warehouse_id=warehouse.id if warehouse else None,
                )
            
            count += 1
        except Exception as e:
            errors += 1
            current_app.logger.error(f"Grid Import Error: {e}")
            
    db.session.commit()
    
    if count > 0:
        flash(f'✅ تم إضافة {count} منتج بنجاح.', 'success')
    if errors > 0:
        flash(f'⚠️ حدث خطأ في {errors} صف.', 'warning')
        
    return redirect(url_for('products.index'))


@products_bp.route('/')
@login_required
@permission_required('manage_products')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
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
    
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        products = query.order_by(Product.name).all()
        _annotate_visible_stock(products)
        if stock_filter == 'low':
            products = [p for p in products if 0 < (p.visible_stock or 0) <= (p.min_stock_alert or 0)]
        elif stock_filter == 'out':
            products = [p for p in products if (p.visible_stock or 0) <= 0]
        total = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        page_items = products[start:end]

        class SimplePagination:
            def __init__(self, page, per_page, total):
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = (total + per_page - 1) // per_page if total else 0
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None

        pagination = SimplePagination(page, per_page, total)
        items = page_items
    else:
        if stock_filter == 'low':
            query = query.filter(Product.current_stock <= Product.min_stock_alert)
        elif stock_filter == 'out':
            query = query.filter(Product.current_stock <= 0)
        pagination = query.order_by(Product.name).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        items = pagination.items
        _annotate_visible_stock(items)
    
    categories = ProductCategory.query.filter_by(is_active=True, tenant_id=get_active_tenant_id(current_user)).all()
    show_branch_columns = should_show_all_branch_columns(current_user)
    warehouse_ids = get_accessible_warehouse_ids(current_user)
    if show_branch_columns:
        _annotate_branch_and_warehouse_info(items, warehouse_ids)
    
    return render_template('products/index.html',
                         products=items,
                         pagination=pagination,
                         categories=categories,
                         show_branch_columns=show_branch_columns)


@products_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_products')
@limiter.limit("10 per minute", methods=['POST'])
def create():
    from forms.product import ProductForm
    from models import Warehouse
    
    form = ProductForm()
    
    # تعيين choices للتصنيفات
    categories = ProductCategory.query.filter_by(is_active=True, tenant_id=get_active_tenant_id(current_user)).all()
    form.category_id.choices = [(0, 'بلا')] + [(c.id, c.name) for c in categories]
    preselected_warehouse_id = request.args.get('warehouse_id', type=int)
    merchants = _scoped_customers_query('merchant').order_by(Customer.name).all()
    partners = _scoped_customers_query('partner').order_by(Customer.name).all()
    
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                sku = request.form.get('sku')
                if not sku:
                    sku = generate_sku()
                
                # تحويل الأسعار إلى float مع التعامل مع القيم الفارغة
                def safe_float(value, default=0.0):
                    if not value or value.strip() == '':
                        return default
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return default
                
                warehouse_id = request.form.get('warehouse_id', type=int)
                current_stock = safe_float(request.form.get('current_stock'))
                initial_stock = current_stock
                
                # التحقق من المستودع
                if not warehouse_id:
                    flash('⚠️ يجب اختيار المستودع', 'warning')
                    warehouses = get_accessible_warehouses(current_user)
                    return render_template('products/create.html', form=form, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
                
                try:
                    warehouse = ensure_warehouse_access(warehouse_id, user=current_user)
                except ValueError as exc:
                    flash('⚠️ المستودع المحدد غير صالح', 'warning')
                    warehouses = get_accessible_warehouses(current_user)
                    return render_template('products/create.html', form=form, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
                
                merchant_customer_id = request.form.get('merchant_customer_id', type=int)
                if merchant_customer_id:
                    merchant_customer = _scoped_customers_query('merchant').filter(Customer.id == merchant_customer_id).first()
                    if not merchant_customer:
                        flash('⚠️ التاجر المحدد غير موجود أو غير مُعرّف كتاجر.', 'warning')
                        warehouses = get_accessible_warehouses(current_user)
                        return render_template('products/create.html', form=form, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
                
                partner_rows, partner_error = _parse_product_partners(request.form)
                if partner_error:
                    flash(partner_error, 'warning')
                    warehouses = get_accessible_warehouses(current_user)
                    return render_template('products/create.html', form=form, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
                
                unit_value = request.form.get('unit') or None
                has_serial_number = request.form.get('has_serial_number') in ('on', 'true', '1', True)
                warranty_days_raw = request.form.get('warranty_days', '0')
                try:
                    warranty_days = int(float(warranty_days_raw or 0))
                except (ValueError, TypeError):
                    warranty_days = 0
                
                # Check tenant product limit
                try:
                    from utils.tenant_limits import check_products_limit, TenantLimitError
                    check_products_limit()
                except TenantLimitError as e:
                    flash(str(e), 'danger')
                    return redirect(url_for('products.create'))
                
                product = Product(
                    name=request.form.get('name'),
                    name_ar=request.form.get('name_ar'),
                    sku=sku,
                    part_number=request.form.get('part_number'),
                    barcode=request.form.get('barcode') or generate_barcode(),
                    category_id=(form.category_id.data or None),
                    regular_price=safe_float(request.form.get('regular_price')),
                    merchant_price=safe_float(request.form.get('merchant_price')),
                    merchant_share=safe_float(request.form.get('merchant_share'), default=100.0),
                    partner_price=safe_float(request.form.get('partner_price')),
                    cost_price=safe_float(request.form.get('cost_price')),
                    current_stock=0,
                    min_stock_alert=safe_float(request.form.get('min_stock_alert')),
                    unit=unit_value,
                    location=request.form.get('location'),
                    description=request.form.get('description'),
                    notes=request.form.get('notes'),
                    merchant_customer_id=merchant_customer_id or None,
                    has_serial_number=has_serial_number,
                    warranty_days=warranty_days,
                    industry=request.form.get('industry', 'general') or 'general',
                )
                extra_fields = {}
                for key in request.form:
                    if key.startswith('extra_'):
                        val = request.form.get(key)
                        if val:
                            extra_fields[key[6:]] = val
                if extra_fields:
                    product.extra_fields = extra_fields
                assign_tenant_id(product, current_user)
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file.filename and product.tenant_id:
                        image_path = save_uploaded_file(
                            file, tenant_upload_dir(product.tenant_id, "products")
                        )
                        if image_path:
                            product.image_url = image_path
                
                db.session.add(product)
                db.session.flush()
                for tier_code, field_name in [
                    ('wholesale', 'tier_wholesale_price'),
                    ('retail', 'tier_retail_price'),
                    ('distributor', 'tier_distributor_price'),
                    ('rep', 'tier_rep_price'),
                ]:
                    price_val = safe_float(request.form.get(field_name))
                    if price_val and price_val > 0:
                        from models import ProductPriceTier
                        tier = ProductPriceTier(
                            tenant_id=product.tenant_id,
                            product_id=product.id,
                            tier_code=tier_code,
                            price=price_val,
                        )
                        db.session.add(tier)
                if partner_rows:
                    for row in partner_rows:
                        partner_row = ProductPartner(
                            product_id=product.id,
                            partner_customer_id=row['partner_customer_id'],
                            percentage=row['percentage'],
                        )
                        assign_tenant_id(partner_row, current_user)
                        product.partner_shares.append(partner_row)
                
                if initial_stock > 0:
                    StockService.add_opening_stock(
                        product_id=product.id,
                        quantity=initial_stock,
                        notes=f'مخزون افتتاحي عند إضافة المنتج إلى المستودع: {warehouse.name_ar or warehouse.name}',
                        warehouse_id=warehouse_id,
                    )
                
                db.session.commit()
                
                LoggingCore.log_audit('create', 'products', product.id)
                
                flash(f'✓ تم إضافة المنتج "{product.name}" بنجاح إلى المستودع "{warehouse.name_ar or warehouse.name}"', 'success')
                return redirect(url_for('products.index'))
            
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error creating product: {str(e)}")
                flash(f'❌ فشل إضافة المنتج: {str(e)}\n💡 تأكد من:\n   • اسم المنتج فريد\n   • الأسعار صحيحة\n   • SKU غير مكرر', 'danger')
        else:
            # Form validation failed
            current_app.logger.warning(f"Form validation failed. Errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'⚠️ خطأ في حقل {field}: {error}', 'danger')
    
    # GET request - إرسال البيانات للقالب
    categories = ProductCategory.query.filter_by(is_active=True, tenant_id=get_active_tenant_id(current_user)).all()
    warehouses = get_accessible_warehouses(current_user)
    
    return render_template('products/create.html',
                           form=form,
                           categories=categories,
                           warehouses=warehouses,
                           merchants=merchants,
                           partners=partners,
                           preselected_warehouse_id=preselected_warehouse_id)


@products_bp.route('/<int:id>')
@login_required
@permission_required('manage_products')
def view(id):
    product = tenant_get_or_404(Product, id)
    if not _ensure_product_scope(product):
        return render_template('errors/403.html'), 403
    movements_query = product.stock_movements
    scoped_warehouse_ids = get_accessible_warehouse_ids(current_user)
    if branch_scope_id() is not None:
        movements_query = movements_query.filter(StockMovement.warehouse_id.in_(scoped_warehouse_ids))

    movements = movements_query.order_by(db.desc('created_at')).limit(20).all()

    product.visible_stock = StockService.get_product_stock(product.id, warehouse_ids=scoped_warehouse_ids or None, user=current_user)
    
    return render_template('products/view.html',
                         product=product,
                         movements=movements)


@products_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('manage_products')
def edit(id):
    product = tenant_get_or_404(Product, id)
    if not _ensure_product_scope(product):
        return render_template('errors/403.html'), 403
    from forms.product import ProductForm
    from models import Warehouse
    form = ProductForm(obj=product)
    
    # تعيين choices للتصنيفات
    categories = ProductCategory.query.filter_by(is_active=True, tenant_id=get_active_tenant_id(current_user)).all()
    form.category_id.choices = [(0, 'بلا')] + [(c.id, c.name) for c in categories]
    warehouses = get_accessible_warehouses(current_user)
    merchants = _scoped_customers_query('merchant').order_by(Customer.name).all()
    partners = _scoped_customers_query('partner').order_by(Customer.name).all()
    
    if request.method == 'POST' and form.validate_on_submit():
        try:
            def safe_float(value, default=None):
                if value is None or value == '':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            warehouse_id = request.form.get('warehouse_id', type=int)
            scoped_branch_id = branch_scope_id()
            if warehouse_id:
                ensure_warehouse_access(warehouse_id, user=current_user)
            old_stock_value = StockService.get_product_stock(
                product.id,
                warehouse_id=warehouse_id,
                user=current_user
            ) if (scoped_branch_id is not None or warehouse_id) else (product.current_stock or 0)
            old_stock = float(old_stock_value or 0)
            new_stock = safe_float(request.form.get('current_stock'), default=old_stock)
            
            if new_stock is not None and new_stock < 0:
                flash('⚠️ لا يمكن أن تكون الكمية أقل من صفر.', 'warning')
                return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
            
            merchant_customer_id = request.form.get('merchant_customer_id', type=int)
            if merchant_customer_id:
                merchant_customer = _scoped_customers_query('merchant').filter(Customer.id == merchant_customer_id).first()
                if not merchant_customer:
                    flash('⚠️ التاجر المحدد غير موجود أو غير مُعرّف كتاجر.', 'warning')
                    return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
            
            partner_rows, partner_error = _parse_product_partners(request.form)
            if partner_error:
                flash(partner_error, 'warning')
                return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
            
            product.name = request.form.get('name')
            product.name_ar = request.form.get('name_ar')
            product.sku = request.form.get('sku')
            product.part_number = request.form.get('part_number')
            product.barcode = request.form.get('barcode')
            product.category_id = (form.category_id.data or None)
            product.regular_price = safe_float(request.form.get('regular_price'), default=0)
            product.merchant_price = safe_float(request.form.get('merchant_price'))
            product.merchant_share = safe_float(request.form.get('merchant_share'), default=100.0)
            product.partner_price = safe_float(request.form.get('partner_price'))
            product.min_stock_alert = safe_float(request.form.get('min_stock_alert'), default=0)
            unit_value = request.form.get('unit')
            if 'unit' in request.form:
                product.unit = unit_value or None
            product.location = request.form.get('location')
            product.description = request.form.get('description')
            product.notes = request.form.get('notes')
            product.merchant_customer_id = merchant_customer_id or None
            product.industry = request.form.get('industry', product.industry or 'general') or 'general'
            extra_fields = dict(product.extra_fields or {})
            for key in request.form:
                if key.startswith('extra_'):
                    val = request.form.get(key)
                    if val:
                        extra_fields[key[6:]] = val
                    else:
                        extra_fields.pop(key[6:], None)
            product.extra_fields = extra_fields if extra_fields else None
            if current_user.can_see_costs():
                new_cost = safe_float(request.form.get('cost_price'), default=0)
                if new_cost != (product.cost_price or 0):
                    from services.stock_service import StockService
                    total_stock = StockService.get_product_stock(product.id)
                    if total_stock > 0:
                        flash('⚠️ لا يمكن تعديل سعر التكلفة لوجود مخزون. قم بتسوية المخزون أولاً.', 'warning')
                        return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
                    product.cost_price = new_cost
            
            if partner_rows and not product.tenant_id:
                flash('⚠️ المنتج غير مرتبط بشركة — لا يمكن حفظ شركاء المنتج.', 'warning')
                return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)

            product.partner_shares.clear()
            if partner_rows:
                product_tid = int(product.tenant_id)
                for row in partner_rows:
                    partner_customer = Customer.query.filter_by(id=row['partner_customer_id'], tenant_id=product_tid).first()
                    if not partner_customer:
                        flash('⚠️ الشريك المحدد غير موجود.', 'warning')
                        return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
                    p_tid = getattr(partner_customer, 'tenant_id', None)
                    if p_tid is not None and int(p_tid) != product_tid:
                        flash('⚠️ الشريك المحدد ينتمي لشركة أخرى.', 'warning')
                        return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
                    product.partner_shares.append(ProductPartner(
                        product_id=product.id,
                        partner_customer_id=row['partner_customer_id'],
                        percentage=row['percentage'],
                        tenant_id=product_tid,
                    ))
            
            from models import ProductPriceTier
            for tier_code, field_name in [
                ('wholesale', 'tier_wholesale_price'),
                ('retail', 'tier_retail_price'),
                ('distributor', 'tier_distributor_price'),
                ('rep', 'tier_rep_price'),
            ]:
                price_val = safe_float(request.form.get(field_name))
                existing = ProductPriceTier.query.filter_by(
                    product_id=product.id,
                    tier_code=tier_code,
                ).first()
                if price_val and price_val > 0:
                    if existing:
                        existing.price = price_val
                    else:
                        tier = ProductPriceTier(
                            tenant_id=product.tenant_id,
                            product_id=product.id,
                            tier_code=tier_code,
                            price=price_val,
                        )
                        db.session.add(tier)
                elif existing:
                    existing.is_active = False
            if new_stock is not None and abs(new_stock - old_stock) > 1e-6:
                if scoped_branch_id is not None and not warehouse_id:
                    flash('⚠️ يجب اختيار مستودع التعديل عند تغيير مخزون هذا الفرع.', 'warning')
                    return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)
                StockService.adjust_stock(
                    product_id=product.id,
                    quantity=new_stock - old_stock,
                    notes=f'تعديل مخزون من {old_stock} إلى {new_stock}',
                    warehouse_id=warehouse_id,
                    reference_type=GLRef.PRODUCT_UPDATE,
                    reference_id=product.id,
                )
            
            if 'image' in request.files:
                file = request.files['image']
                if file.filename and product.tenant_id:
                    image_path = save_uploaded_file(
                        file, tenant_upload_dir(product.tenant_id, "products")
                    )
                    if image_path:
                        product.image_url = image_path
            
            db.session.commit()
            
            LoggingCore.log_audit('update', 'products', product.id)
            
            flash('✅ تم تحديث بيانات المنتج بنجاح!', 'success')
            return redirect(url_for('products.view', id=product.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ فشل تحديث المنتج: {str(e)}', 'danger')
    
    categories = ProductCategory.query.filter_by(is_active=True, tenant_id=get_active_tenant_id(current_user)).all()
    product.visible_stock = StockService.get_product_stock(product.id, user=current_user)
    return render_template('products/edit.html', form=form, product=product, categories=categories, warehouses=warehouses, merchants=merchants, partners=partners)


@products_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('manage_products')
def delete(id):
    """حذف (إلغاء تفعيل) المنتج - soft delete"""
    product = tenant_get_or_404(Product, id)
    if not _ensure_product_scope(product):
        return render_template('errors/403.html'), 403
    
    try:
        # التحقق من وجود عمليات مرتبطة
        from models import SaleLine, PurchaseLine
        tid = get_active_tenant_id(current_user)
        sales_query = SaleLine.query.filter_by(product_id=id)
        purchases_query = PurchaseLine.query.filter_by(product_id=id)
        if tid is not None:
            sales_query = sales_query.filter(SaleLine.tenant_id == tid)
            purchases_query = purchases_query.filter(PurchaseLine.tenant_id == tid)
        sales_count = sales_query.count()
        purchases_count = purchases_query.count()
        
        if sales_count > 0 or purchases_count > 0:
            # soft delete
            product.is_active = False
            db.session.commit()
            flash(f'⚠️ تم إلغاء تفعيل المنتج "{product.name}" (لديه عمليات مسجلة).\n💡 لا يمكن حذفه نهائياً للحفاظ على السجلات.', 'warning')
            LoggingCore.log_audit('deactivate', 'products', id)
        else:
            # hard delete
            db.session.delete(product)
            db.session.commit()
            flash(f'✅ تم حذف المنتج "{product.name}" نهائياً!', 'success')
            LoggingCore.log_audit('delete', 'products', id)
        
        return redirect(url_for('products.index'))
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting product {id}: {e}")
        flash('❌ فشل حذف المنتج. حدث خطأ غير متوقع.', 'danger')
        return redirect(url_for('products.view', id=id))


@products_bp.route('/api/search')
@login_required
@any_permission_required('manage_sales', 'manage_purchases', 'manage_products')
def api_search():
    """API endpoint للبحث عن المنتجات"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    warehouse_id = request.args.get('warehouse_id', type=int)
    warehouse_ids = [warehouse_id] if warehouse_id else get_accessible_warehouse_ids(current_user)
    products_query = StockService.get_visible_products_query(current_user)
    if query and len(query) >= 1:
        products_query = products_query.filter(
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%'),
                Product.barcode.ilike(f'%{query}%')
            )
        )
    products = products_query.order_by(Product.name).limit(per_page).all()
    stock_map = get_branch_stock_map(
        product_ids=[p.id for p in products],
        warehouse_ids=warehouse_ids,
    ) if warehouse_ids else {}
    
    results = [{
        'id': p.id,
        'name': p.name,
        'code': p.sku or '',
        'text': f"{p.name} ({p.sku})" if p.sku else p.name,
        'sku': p.sku,
        'price': float(p.regular_price),
        'stock': float(stock_map.get(p.id, p.current_stock or 0)),
        'unit': p.unit,
        'is_low_stock': float(stock_map.get(p.id, p.current_stock or 0)) <= float(p.min_stock_alert or 0),
    } for p in products]
    
    return jsonify(results)


@products_bp.route('/categories')
@login_required
@permission_required('manage_products')
def categories():
    categories = ProductCategory.query.filter_by(is_active=True, tenant_id=get_active_tenant_id(current_user)).order_by(ProductCategory.name).all()
    return render_template('products/categories.html', categories=categories)


@products_bp.route('/categories/create', methods=['POST'])
@login_required
@permission_required('manage_products')
def create_category():
    try:
        # دعم JSON و Form Data
        data = request.get_json() if request.is_json else request.form

        name = (data.get('name') or '').strip()
        name_ar = (data.get('name_ar') or '').strip() or None
        description = (data.get('description') or '').strip() or None

        if not name:
            message = '⚠️ يجب إدخال اسم الفئة.'
            if request.is_json:
                return jsonify({'success': False, 'error': message}), 400
            flash(message, 'warning')
            return redirect(url_for('products.categories'))

        # منع التكرار (نفس الاسم بغض النظر عن حالة الأحرف)
        tid = get_active_tenant_id(current_user)
        existing = ProductCategory.query.filter(
            ProductCategory.tenant_id == tid,
            db.func.lower(ProductCategory.name) == name.lower()
        ).first()
        if existing:
            message = '⚠️ هذه الفئة موجودة مسبقاً.'
            if request.is_json:
                return jsonify({'success': False, 'error': message}), 400
            flash(message, 'warning')
            return redirect(url_for('products.categories'))

        category = ProductCategory(
            tenant_id=tid,
            name=name,
            name_ar=name_ar,
            description=description,
            is_active=True
        )

        db.session.add(category)
        db.session.commit()

        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'تم إضافة الفئة بنجاح',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'name_ar': category.name_ar,
                    'description': category.description
                }
            })

        flash('✅ تم إضافة التصنيف بنجاح!', 'success')
        return redirect(url_for('products.categories'))

    except Exception as e:
        db.session.rollback()

        if request.is_json:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400

        flash(f'❌ حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('products.categories'))


@products_bp.route('/<int:id>/adjust-stock', methods=['POST'])
@login_required
@permission_required('manage_products')
def adjust_stock(id):
    product = tenant_get_or_404(Product, id)
    if not _ensure_product_scope(product):
        return jsonify({'success': False, 'message': 'المنتج خارج نطاق الفرع الحالي'}), 403
    
    try:
        adjustment_type = request.form.get('adjustment_type')
        quantity = float(request.form.get('quantity', 0))
        reason = request.form.get('reason', 'adjustment')
        notes = request.form.get('notes', '')
        warehouse_id = request.form.get('warehouse_id', type=int)
        scoped_branch_id = branch_scope_id()
        warehouse = None
        if warehouse_id:
            warehouse = ensure_warehouse_access(warehouse_id, user=current_user)
        elif scoped_branch_id is not None:
            accessible_warehouses = get_accessible_warehouses(current_user)
            if len(accessible_warehouses) == 1:
                warehouse = accessible_warehouses[0]
            else:
                return jsonify({'success': False, 'message': 'يجب اختيار مستودع داخل الفرع الحالي لتعديل المخزون'}), 400
        
        if quantity <= 0:
            return jsonify({'success': False, 'message': 'الكمية يجب أن تكون أكبر من صفر'})
        
        old_stock = StockService.get_product_stock(product.id, warehouse_id=(warehouse.id if warehouse else None), user=current_user) if (warehouse or scoped_branch_id is not None) else product.current_stock
        
        if adjustment_type == 'add':
            new_stock = old_stock + quantity
        elif adjustment_type == 'subtract':
            new_stock = old_stock - quantity
            if new_stock < 0:
                return jsonify({'success': False, 'message': 'لا يمكن أن يكون المخزون سالباً'})
        elif adjustment_type == 'set':
            new_stock = quantity
        else:
            return jsonify({'success': False, 'message': 'نوع التعديل غير صحيح'})
        
        delta = quantity if adjustment_type != 'set' else (new_stock - old_stock)
        StockService.adjust_stock(
            product_id=product.id,
            quantity=delta if adjustment_type != 'subtract' else -quantity,
            notes=notes or f'تعديل يدوي - {reason}',
            warehouse_id=warehouse.id if warehouse else None
        )
        db.session.commit()
        
        LoggingCore.log_audit('update', 'products', product.id, f'تعديل مخزون: {old_stock} → {new_stock}')
        
        return jsonify({
            'success': True, 
            'message': f'تم تعديل المخزون من {old_stock} إلى {new_stock}',
            'new_stock': new_stock
        })
        
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Product stock update failed')
        return jsonify({'success': False, 'message': 'تعذر تحديث المخزون حالياً'})


@products_bp.route('/<int:id>/print-label')
@login_required
@permission_required('view_products')
def print_label(id):
    from services.label_print_service import get_single_label_html
    product = tenant_get_or_404(Product, id, get_active_tenant_id(current_user))
    branch_id = None
    try:
        from utils.branching import report_branch_scope_id
        branch_id = report_branch_scope_id()
    except Exception:
        pass
    return get_single_label_html(product, branch_id=branch_id)


@products_bp.route('/print-labels', methods=['POST'])
@login_required
@permission_required('view_products')
def print_labels():
    from services.label_print_service import get_product_labels_html
    ids = request.json.get('product_ids', []) if request.is_json else request.form.getlist('product_ids')
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        flash('اختر منتجات للطباعة.', 'warning')
        return redirect(url_for('products.index'))
    tenant_id = get_active_tenant_id(current_user)
    branch_id = None
    try:
        from utils.branching import report_branch_scope_id
        branch_id = report_branch_scope_id()
    except Exception:
        pass
    return get_product_labels_html(ids, tenant_id, branch_id=branch_id)
