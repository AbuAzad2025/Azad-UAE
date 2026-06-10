from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db, csrf, limiter
from models import Sale, SaleLine, Customer, Product, InvoiceSettings
from services.sale_service import SaleService
from services.stock_service import StockService
from services.currency_service import CurrencyService
from utils.decorators import permission_required
from utils.branching import ensure_warehouse_access, get_accessible_warehouses, should_show_all_branch_columns
from services.logging_core import LoggingCore
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from utils.tenanting import tenant_query, tenant_get_or_404, tenant_get, get_active_tenant_id
from utils.db_safety import atomic_transaction
from utils.structured_logging import log_mutation
from services.store_service import StoreService
from utils.gl_tenant import reverse_document_gl
from utils.gl_reference_types import GLRef, delete_entries_by_ref
from utils.number_to_arabic import number_to_arabic_words
from utils.qr_generator import generate_qr_data_url

sales_bp = Blueprint('sales', __name__, url_prefix='/sales')


@sales_bp.route('/')
@login_required
@permission_required('manage_sales')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '', type=str)
    status = request.args.get('status', '', type=str)
    payment_status = request.args.get('payment_status', '', type=str)
    
    query = tenant_query(Sale)
    
    # إخفاء المبيعات المؤرشفة
    from models import ArchivedRecord
    from sqlalchemy import select
    archived_sales = select(ArchivedRecord.record_id).filter(
        ArchivedRecord.table_name == 'sales'
    ).scalar_subquery()
    query = query.filter(~Sale.id.in_(archived_sales))
    
    if search:
        search_filter = f'%{search}%'
        query = query.join(Customer).filter(
            db.or_(
                Sale.sale_number.ilike(search_filter),
                Customer.name.ilike(search_filter)
            )
        )
    
    if status:
        query = query.filter_by(status=status)
    else:
        query = query.filter_by(status='confirmed')
    
    if payment_status:
        query = query.filter_by(payment_status=payment_status)
    
    if current_user.is_seller():
        query = query.filter_by(seller_id=current_user.id)
    from utils.decorators import branch_scope_id
    branch_id = branch_scope_id()
    if branch_id is not None:
        query = query.filter(Sale.branch_id == branch_id)
    pagination = query.order_by(Sale.sale_date.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    return render_template('sales/index.html',
                         sales=pagination.items,
                         pagination=pagination,
                         show_branch_columns=should_show_all_branch_columns(current_user))


@sales_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_sales')
@limiter.limit("15 per minute", methods=['POST'])
def create():
    if request.method == 'POST':
        try:
            customer_id = request.form.get('customer_id', type=int)
            customer = tenant_get_or_404(Customer, customer_id)
            
            lines_data = []
            line_count = int(request.form.get('line_count', 0))
            
            for i in range(line_count):
                try:
                    product_id_str = request.form.get(f'lines[{i}][product_id]')
                    product_id = int(product_id_str) if product_id_str else None
                    
                    quantity_str = request.form.get(f'lines[{i}][quantity]')
                    quantity = float(quantity_str) if quantity_str else None
                    
                    discount_str = request.form.get(f'lines[{i}][discount_percent]')
                    discount_percent = float(discount_str) if discount_str else 0
                    
                    price_str = request.form.get(f'lines[{i}][unit_price]')
                    override_price = float(price_str) if price_str else None
                    
                    # Get Serials if any
                    serials = request.form.getlist(f'lines[{i}][serials][]')
                    
                    if product_id and quantity and quantity > 0:
                        product = tenant_get_or_404(Product, product_id)
                        if product:
                            lines_data.append({
                                'product': product,
                                'quantity': quantity,
                                'discount_percent': discount_percent,
                                'unit_price': override_price,
                                'serials': serials # Pass serials to service
                            })
                except (ValueError, TypeError) as e:
                    # Skip invalid lines
                    continue
            
            if not lines_data:
                from utils.error_messages import ErrorMessages
                flash(ErrorMessages.sale_no_lines(), 'danger')
                return redirect(url_for('sales.create'))
            
            try:
                from models import Tenant
                default_currency = resolve_default_currency()
            except Exception as e:
                import sys
                import traceback
                sys.stderr.write(f"[SALES_WARNING] Failed to get tenant default currency (create sale): {e}\n")
                traceback.print_exc()
                try:
                    from services.logging_core import LoggingCore
                    LoggingCore.log_error(
                        message=str(e),
                        category="SALES",
                        source="routes.sales.create_sale.get_default_currency",
                        level="WARNING",
                        exception=e
                    )
                except Exception:
                    pass
                default_currency = get_system_default_currency()
            currency_value = request.form.get('currency')
            currency = currency_value if currency_value else default_currency
            user_exchange_rate = request.form.get('exchange_rate', type=float)
            
            # Track manual exchange rate changes for audit
            exchange_rate_manual = request.form.get('exchange_rate_manual') == 'true'
            exchange_rate_server = request.form.get('exchange_rate_server', type=float)
            exchange_rate_diff = request.form.get('exchange_rate_difference', type=float)
            
            discount_amount = request.form.get('discount_amount', type=float, default=0)
            shipping_cost = request.form.get('shipping_cost', type=float, default=0)
            tax_rate = request.form.get('tax_rate', type=float, default=0)
            notes = request.form.get('notes')
            sales_rep_id = request.form.get('sales_rep_id', type=int)
            coupon_code = request.form.get('coupon_code', '').strip()
            if coupon_code:
                notes = (notes or '') + f'\n[كوبون] {coupon_code}'
            if exchange_rate_manual and exchange_rate_server and user_exchange_rate:
                if user_exchange_rate < exchange_rate_server:
                    audit_note = f"\n[تنبيه] سعر صرف يدوي: {user_exchange_rate:.6f} (سعر السيرفر: {exchange_rate_server:.6f}, فرق: {exchange_rate_diff:.2f}%)"
                    notes = (notes or '') + audit_note
            
            payment_amount = request.form.get('payment_amount', type=float, default=0)
            payment_method = request.form.get('payment_method', 'cash')
            
            payment_data = {
                'amount': payment_amount,
                'payment_method': payment_method,
                'currency': currency,  # Payment currency
                'exchange_rate': user_exchange_rate,  # Payment exchange rate
                'reference_number': request.form.get('reference_number'),
                'cheque_number': request.form.get('cheque_number'),
                'cheque_date': request.form.get('cheque_date'),
                'bank_name': request.form.get('bank_name'),
                'notes': request.form.get('notes')
            } if payment_amount > 0 else None
            
            # قراءة warehouse_id من النموذج
            warehouse_id = request.form.get('warehouse_id', type=int)
            ensure_warehouse_access(warehouse_id, user=current_user)
            
            with atomic_transaction('sale_creation'):
                sale = SaleService.create_sale(
                customer=customer,
                seller=current_user,
                lines_data=lines_data,
                warehouse_id=warehouse_id,
                currency=currency,
                user_exchange_rate=user_exchange_rate,
                discount_amount=discount_amount,
                shipping_cost=shipping_cost,
                tax_rate=tax_rate,
                notes=notes,
                payment_data=payment_data,
                sales_rep_id=sales_rep_id,
            )
            
            LoggingCore.log_audit('create', 'sales', sale.id)
            
            flash('✅ تم إنشاء الفاتورة بنجاح!', 'success')
            return redirect(url_for('sales.view', id=sale.id))
        
        except ValueError as e:
            # رسالة الخطأ من SaleService (مثل: insufficient stock)
            current_app.logger.warning(f"ValueError creating sale: {e}")
            flash(f'⚠️ {str(e)}\n💡 تحقق من الكميات المتوفرة في المخزون.', 'danger')
        except Exception as e:
            from utils.error_messages import ErrorMessages
            current_app.logger.error(f"Error creating sale: {e}")
            flash(ErrorMessages.database_error(), 'danger')
    
    # تحميل المستودعات للقالب
    tid = get_active_tenant_id(current_user)
    if tid:
        warehouses = StoreService.get_physical_warehouses(tid, user=current_user)
    else:
        warehouses = [wh for wh in get_accessible_warehouses(current_user) if not wh.is_online]
    preselected_customer = None
    preselected_customer_id = request.args.get('customer_id', type=int)
    if preselected_customer_id:
        preselected_customer = tenant_get(Customer, preselected_customer_id)
    
    from models import User
    users = User.query.filter_by(tenant_id=tid, is_active=True).all() if tid else []
    return render_template(
        'sales/create.html',
        warehouses=warehouses,
        preselected_customer=preselected_customer,
        users=users,
    )


@sales_bp.route('/<int:id>')
@login_required
@permission_required('manage_sales')
def view(id):
    sale = tenant_get_or_404(Sale, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and sale.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    
    if current_user.is_seller() and sale.seller_id != current_user.id:
        from utils.error_messages import ErrorMessages
        flash(ErrorMessages.permission_denied('عرض هذه الفاتورة'), 'danger')
        return redirect(url_for('sales.index'))
    
    return render_template('sales/view.html', sale=sale)


@sales_bp.route('/<int:id>/print')
@login_required
@permission_required('manage_sales')
def print_invoice(id):
    sale = tenant_get_or_404(Sale, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and sale.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    
    if current_user.is_seller() and sale.seller_id != current_user.id:
        from utils.error_messages import ErrorMessages
        flash(ErrorMessages.permission_denied('طباعة هذه الفاتورة'), 'danger')
        return redirect(url_for('sales.index'))
    
    from config import Config
    from models import Branch
    from utils.tenant_branding import get_print_header_context
    tid = sale.tenant_id
    settings = InvoiceSettings.get_active(tid)
    # Get default currency from tenant or config
    from models import Tenant
    tenant = Tenant.query.get(tid) if tid else None
    default_currency = tenant.default_currency if tenant and tenant.default_currency else Config.DEFAULT_CURRENCY
    print_branding = get_print_header_context(tid)
    print_branch = Branch.query.get(sale.branch_id) if sale.branch_id else None
    print_user_name = (
        sale.seller.get_display_name('ar')
        if sale.seller and hasattr(sale.seller, 'get_display_name')
        else (sale.seller.full_name if sale.seller and sale.seller.full_name else (sale.seller.username if sale.seller else ''))
    )
    amount_in_words = number_to_arabic_words(float(sale.total_amount or 0), sale.currency or default_currency)
    qr_data_url = ''
    if settings and settings.enable_qr_code:
        qr_data_url = generate_qr_data_url({
            't': 'invoice',
            'n': sale.sale_number,
            'a': float(sale.total_amount or 0),
            'c': sale.currency or default_currency,
            'd': sale.sale_date.strftime('%Y-%m-%d') if sale.sale_date else '',
            'co': (
                settings.company_name_ar
                if settings and settings.company_name_ar and settings.company_name_ar != 'None'
                else 'نظام المحاسبة'
            ),
            'u': print_user_name,
            'b': print_branch.name if print_branch else '',
        })
    
    # استخدام القالب النشط من الإعدادات
    template = settings.active_template if settings and settings.active_template else 'modern'
    template_path = f'invoices/{template}.html'
    
    # التحقق من وجود القالب، وإلا استخدام القالب الافتراضي
    try:
        return render_template(
            template_path,
            sale=sale,
            settings=settings,
            config=Config,
            print_branch=print_branch,
            print_user_name=print_user_name,
            amount_in_words=amount_in_words,
            qr_data_url=qr_data_url,
            print_branding=print_branding,
            print_tenant_id=tid,
        )
    except:
        # إذا لم يوجد القالب، استخدام modern كافتراضي
        return render_template(
            'invoices/modern.html',
            sale=sale,
            settings=settings,
            config=Config,
            print_branch=print_branch,
            print_user_name=print_user_name,
            amount_in_words=amount_in_words,
            qr_data_url=qr_data_url,
            print_branding=print_branding,
            print_tenant_id=tid,
        )


@sales_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('manage_sales')
def edit(id):
    """تعديل فاتورة - فقط الفواتير غير المدفوعة وغير الملغاة"""
    sale = tenant_get_or_404(Sale, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and sale.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    
    # منع التعديل للفواتير المدفوعة أو الملغاة
    if sale.payment_status == 'paid':
        flash('⚠️ لا يمكن تعديل فاتورة مدفوعة بالكامل.\n💡 الفواتير المدفوعة لا يمكن تعديلها محاسبياً.', 'danger')
        return redirect(url_for('sales.view', id=id))
    
    if sale.status == 'cancelled':
        flash('⚠️ لا يمكن تعديل فاتورة ملغاة.\n💡 قم بإنشاء فاتورة جديدة بدلاً من ذلك.', 'danger')
        return redirect(url_for('sales.view', id=id))
    
    if request.method == 'POST':
        try:
            # السماح فقط بتعديل الملاحظات والخصم
            sale.notes = request.form.get('notes', '')
            discount_amount = request.form.get('discount_amount', type=float, default=0)
            sale.discount_amount = discount_amount
            
            # إعادة حساب الإجماليات
            sale.calculate_totals()
            
            db.session.commit()
            LoggingCore.log_audit('update', 'sales', id)
            
            flash('✅ تم تحديث الفاتورة بنجاح!', 'success')
            return redirect(url_for('sales.view', id=id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة.', 'danger')
    
    return render_template('sales/edit.html', sale=sale)


@sales_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@permission_required('manage_sales')
def cancel(id):
    if current_user.is_seller():
        from utils.error_messages import ErrorMessages
        flash(ErrorMessages.permission_denied('إلغاء الفواتير'), 'danger')
        return redirect(url_for('sales.index'))
    
    sale = tenant_get_or_404(Sale, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and sale.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    
    try:
        SaleService.cancel_sale(sale)
        
        LoggingCore.log_audit('cancel', 'sales', sale.id)
        
        flash('✅ تم إلغاء الفاتورة بنجاح!', 'success')
    
    except Exception as e:
        flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
    
    return redirect(url_for('sales.view', id=id))


@sales_bp.route('/api/get-price')
@login_required
@permission_required('manage_sales')
def api_get_price():
    product_id = request.args.get('product_id', type=int)
    customer_id = request.args.get('customer_id', type=int)
    warehouse_id = request.args.get('warehouse_id', type=int)
    
    if not product_id or not customer_id:
        return jsonify({'error': 'Missing parameters'}), 400
    
    product = tenant_get_or_404(Product, product_id)
    customer = tenant_get_or_404(Customer, customer_id)
    
    if not product or not customer:
        return jsonify({'error': 'Not found'}), 404
    
    price = product.get_price_for_customer(customer.customer_type)
    current_stock = StockService.get_product_stock(product.id, warehouse_id=warehouse_id, user=current_user)
    
    return jsonify({
        'price': float(price),
        'cost_price': float(product.cost_price) if current_user.can_see_costs() else None,
        'current_stock': float(current_stock),
        'unit': product.unit or 'بلا'
    })


@sales_bp.route('/archived')
@login_required
@permission_required('manage_sales')
def archived():
    """عرض المبيعات المؤرشفة"""
    from models import ArchivedRecord
    from datetime import datetime
    
    archived_sales_query = db.session.query(ArchivedRecord).filter(
        ArchivedRecord.table_name == 'sales'
    )
    
    from utils.tenanting import get_active_tenant_id
    tenant_id = get_active_tenant_id(current_user)
    
    archived_items = []
    
    for archived in archived_sales_query.order_by(ArchivedRecord.archived_at.desc()).limit(500).all():
        data = archived.data
        sale = tenant_get(Sale, archived.record_id) if archived.record_id else None
        if sale is None:
            continue
        if tenant_id is not None and getattr(sale, 'tenant_id', None) not in (None, tenant_id):
            continue
        archived_items.append({
            'id': archived.record_id,
            'sale_number': data.get('sale_number'),
            'sale_date': datetime.fromisoformat(data.get('sale_date').replace('Z', '+00:00')) if isinstance(data.get('sale_date'), str) else data.get('sale_date'),
            'customer': sale.customer if sale else None,
            'total_amount': float(data.get('total_amount', 0)),
            'currency': data.get('currency'),
            'payment_status': data.get('payment_status'),
            'archived_at': archived.archived_at
        })
    
    archived_items.sort(key=lambda x: x['archived_at'], reverse=True)
    
    return render_template('sales/archived.html', sales=archived_items)


@sales_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('manage_sales')
def delete(id):
    """حذف (أرشفة) فاتورة مبيعات"""
    if not current_user.is_owner:
        from utils.error_messages import ErrorMessages
        flash(ErrorMessages.permission_denied('حذف الفواتير'), 'danger')
        return redirect(url_for('sales.index'))

    from services.archive_service import ArchiveService
    from models import Payment, Cheque, GLJournalEntry
    from services.gl_service import GLService
    
    sale = tenant_get_or_404(Sale, id)
    
    # التحقق من الارتباطات
    has_links = False
    
    # 1. التحقق من المدفوعات (Payments)
    linked_payments = Payment.query.filter_by(sale_id=sale.id, tenant_id=sale.tenant_id).count()
    if linked_payments > 0:
        has_links = True
        
    # 2. التحقق من الشيكات (Cheques)
    linked_cheques = Cheque.query.filter_by(sale_id=sale.id, tenant_id=sale.tenant_id).count()
    if linked_cheques > 0:
        has_links = True

    try:
        if has_links:
            # أرشفة (Soft Delete)
            # عكس القيد المحاسبي
            if sale.status != 'cancelled':
                reverse_document_gl(
                    [GLRef.SALE, GLRef.SALE_COGS], sale.id,
                    f'Reverse Sale {sale.sale_number} (Archived)',
                    tenant_id=getattr(sale, 'tenant_id', None),
                )

            archive_service = ArchiveService()
            archive_service.archive_record('sales', sale, reason='تم أرشفة الفاتورة لوجود ارتباطات مالية', commit=False)
            
            # يمكن أرشفة المدفوعات والشيكات المرتبطة أيضاً إذا لزم الأمر، ولكن سنكتفي بأرشفة الفاتورة حالياً
            # أو يمكن تركها كما هي ولكن الفاتورة ستختفي من القائمة النشطة
            
            LoggingCore.log_audit('archive', 'sales', id)
            db.session.commit()
            flash(f'✅ تم أرشفة الفاتورة "{sale.sale_number}" (لوجود ارتباطات مالية)', 'warning')
        else:
            # حذف نهائي (Hard Delete)
            # 1. حذف البنود (SaleLines) - يتم تلقائياً عادةً عبر cascade ولكن للأمان
            SaleLine.query.filter_by(sale_id=sale.id).delete()
            
            # 2. حذف القيود المحاسبية
            delete_entries_by_ref(sale.id, GLRef.SALE, GLRef.SALE_COGS)
            
            # 3. حذف الفاتورة
            db.session.delete(sale)
            LoggingCore.log_audit('delete', 'sales', id)
            db.session.commit()
            flash(f'✅ تم حذف الفاتورة "{sale.sale_number}" نهائياً', 'success')
            
        return redirect(url_for('sales.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ في الحذف: {str(e)}', 'danger')
        return redirect(url_for('sales.index'))


@sales_bp.route('/<int:id>/archive', methods=['POST'])
@login_required
@permission_required('manage_sales')
def archive(id):
    """أرشفة فاتورة"""
    from services.archive_service import ArchiveService
    
    sale = tenant_get_or_404(Sale, id)
    
    try:
        # عكس القيد المحاسبي قبل الأرشفة (إذا لم تكن ملغاة)
        if sale.status != 'cancelled':
            reverse_document_gl(
                [GLRef.SALE, GLRef.SALE_COGS], sale.id,
                f'Reverse Sale {sale.sale_number} (Archived)',
                tenant_id=getattr(sale, 'tenant_id', None),
            )

        archive_service = ArchiveService()
        archive_service.archive_record('sales', sale, reason='تم أرشفة فاتورة المبيعات')
        LoggingCore.log_audit('archive', 'sales', sale.id)
    except Exception as e:
        db.session.rollback()
    
    return redirect(url_for('sales.index'))


@sales_bp.route('/<int:id>/restore', methods=['POST'])
@login_required
@permission_required('manage_sales')
def restore(id):
    """استعادة فاتورة من الأرشيف"""
    from models import ArchivedRecord
    
    tid = get_active_tenant_id(current_user)
    archived_query = ArchivedRecord.query.filter_by(
        table_name='sales',
        record_id=id
    )
    if tid is not None:
        archived_query = archived_query.filter(ArchivedRecord.tenant_id == tid)
    archived = archived_query.first_or_404()
    
    try:
        db.session.delete(archived)
        db.session.commit()
        LoggingCore.log_audit('restore', 'sales', id)
    except Exception as e:
        db.session.rollback()
    
    return redirect(url_for('sales.archived'))


# =====================================
# API Endpoints - Backend Calculations
# =====================================

@sales_bp.route('/api/calculate-totals', methods=['POST'])
@login_required
@permission_required('manage_sales')
def api_calculate_sale_totals():
    """API لحساب إجماليات فاتورة المبيعات - Backend Calculation"""
    try:
        from decimal import Decimal
        
        data = request.get_json(force=True)
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        lines = data.get('lines', [])
        discount_amount = Decimal(str(data.get('discount_amount', 0)))
        shipping_cost = Decimal(str(data.get('shipping_cost', 0)))
        tax_rate = Decimal(str(data.get('tax_rate', 0)))
        from utils.tax_settings import normalize_tax_rate
        tax_rate = normalize_tax_rate(tax_rate)
        
        # حساب المجموع الفرعي
        subtotal = Decimal('0')
        for line in lines:
            try:
                qty = Decimal(str(line.get('quantity', 0)))
                price = Decimal(str(line.get('unit_price', 0)))
                discount_percent = Decimal(str(line.get('discount_percent', 0)))
                
                if qty > 0 and price > 0:
                    line_subtotal = qty * price
                    line_discount = line_subtotal * (discount_percent / Decimal('100'))
                    line_total = line_subtotal - line_discount
                    subtotal += line_total
            except (ValueError, TypeError, KeyError):
                continue
        
        # حساب الإجماليات
        after_discount = subtotal - discount_amount + shipping_cost
        tax_amount = after_discount * (tax_rate / Decimal('100'))
        total = after_discount + tax_amount
        
        return jsonify({
            'success': True,
            'subtotal': float(subtotal),
            'discount': float(discount_amount),
            'shipping': float(shipping_cost),
            'tax_rate': float(tax_rate),
            'tax_amount': float(tax_amount),
            'total': float(total),
            'line_count': len([l for l in lines if Decimal(str(l.get('quantity', 0))) > 0])
        }), 200
        
    except Exception:
        current_app.logger.exception('calculate_sale_totals failed')
        return jsonify({'success': False, 'error': 'تعذر حساب الإجماليات حالياً'}), 500
