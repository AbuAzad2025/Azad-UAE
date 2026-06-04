from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy import select
from extensions import db, limiter
from models import Customer, Sale
from utils.decorators import permission_required, branch_scope_id
from utils.branching import should_show_all_branch_columns
from utils.helpers import create_audit_log
from services.payment_service import PaymentService
from decimal import Decimal
from datetime import datetime
from utils.tenanting import get_active_tenant_id, tenant_query, tenant_get_or_404, assert_tenant_record

customers_bp = Blueprint('customers', __name__, url_prefix='/customers')


def _scoped_customer_query():
    from models import Payment, Receipt

    query = tenant_query(Customer)
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
    customer_ids = sale_ids.union(payment_ids, receipt_ids)
    return query.filter(Customer.id.in_(customer_ids))


def _customer_in_scope(customer_id):
    if branch_scope_id() is None:
        return True
    return db.session.query(
        _scoped_customer_query().filter(Customer.id == customer_id).exists()
    ).scalar()


def _get_customer_balance(customer_id):
    from models import Payment, Receipt

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        customer = tenant_get_or_404(Customer, customer_id)
        return PaymentService.get_customer_balance_aed(customer)

    sales_total = db.session.query(db.func.sum(Sale.amount_aed)).filter(
        Sale.customer_id == customer_id,
        Sale.status == 'confirmed',
        Sale.branch_id == scoped_branch_id,
    ).scalar() or Decimal('0')
    receipts_total = db.session.query(db.func.sum(Receipt.amount_aed)).filter(
        Receipt.customer_id == customer_id,
        Receipt.branch_id == scoped_branch_id,
    ).scalar() or Decimal('0')
    outgoing_total = db.session.query(db.func.sum(Payment.amount_aed)).filter(
        Payment.customer_id == customer_id,
        Payment.direction == 'outgoing',
        Payment.branch_id == scoped_branch_id,
    ).scalar() or Decimal('0')
    return Decimal(str(sales_total or 0)) + Decimal(str(outgoing_total or 0)) - Decimal(str(receipts_total or 0))


def _get_unpaid_sales(customer_id):
    query = Sale.query.filter(
        Sale.customer_id == customer_id,
        Sale.status == 'confirmed',
        Sale.balance_due > 0,
    )
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        query = query.filter(Sale.branch_id == scoped_branch_id)
    return query.order_by(Sale.sale_date.asc()).all()


def _attach_customer_branch_labels(customers):
    """Annotate customers with branch labels aggregated from related transactions."""
    if not customers:
        return

    from models import Payment, Receipt, Branch

    customer_ids = [c.id for c in customers]
    branch_map = {cid: set() for cid in customer_ids}

    sale_rows = db.session.query(Sale.customer_id, Sale.branch_id).filter(
        Sale.customer_id.in_(customer_ids),
        Sale.branch_id.isnot(None),
    ).all()
    payment_rows = db.session.query(Payment.customer_id, Payment.branch_id).filter(
        Payment.customer_id.in_(customer_ids),
        Payment.branch_id.isnot(None),
    ).all()
    receipt_rows = db.session.query(Receipt.customer_id, Receipt.branch_id).filter(
        Receipt.customer_id.in_(customer_ids),
        Receipt.branch_id.isnot(None),
    ).all()

    branch_ids = set()
    for cid, bid in sale_rows + payment_rows + receipt_rows:
        if cid in branch_map and bid:
            branch_map[cid].add(bid)
            branch_ids.add(bid)

    branches = Branch.query.filter(Branch.id.in_(branch_ids)).all() if branch_ids else []
    branch_labels = {
        b.id: (f"{b.name} ({b.code})" if getattr(b, "code", None) else b.name)
        for b in branches
    }

    for customer in customers:
        labels = [branch_labels.get(bid, str(bid)) for bid in sorted(branch_map.get(customer.id, set()))]
        customer.branch_labels = labels


@customers_bp.route('/')
@login_required
@permission_required('manage_customers')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '', type=str)
    customer_type = request.args.get('type', '', type=str)
    
    query = _scoped_customer_query()
    
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                Customer.name.ilike(search_filter),
                Customer.phone.ilike(search_filter),
                Customer.email.ilike(search_filter)
            )
        )
    
    if customer_type:
        query = query.filter_by(customer_type=customer_type)
    
    query = query.filter_by(is_active=True)
    
    pagination = query.order_by(Customer.name).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    show_branch_columns = should_show_all_branch_columns(current_user)
    if show_branch_columns:
        _attach_customer_branch_labels(pagination.items)

    return render_template(
        'customers/index.html',
        customers=pagination.items,
        pagination=pagination,
        show_branch_columns=show_branch_columns,
    )


@customers_bp.route('/export')
@login_required
@permission_required('manage_customers')
def export():
    from services.export_service import ExportService
    from models import Payment, Receipt

    fmt = (request.args.get('format') or 'csv').strip().lower()
    search = request.args.get('search', '', type=str)
    customer_type = request.args.get('type', '', type=str)

    tenant_id = get_active_tenant_id(current_user)
    query = _scoped_customer_query()
    if tenant_id is not None:
        query = query.filter(Customer.tenant_id == tenant_id)
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                Customer.name.ilike(search_filter),
                Customer.phone.ilike(search_filter),
                Customer.email.ilike(search_filter)
            )
        )
    if customer_type:
        query = query.filter_by(customer_type=customer_type)
    query = query.filter_by(is_active=True)
    customers = query.order_by(Customer.name).all()

    scoped_branch = branch_scope_id()
    balance_map = {}
    if scoped_branch is not None and customers:
        customer_ids = [c.id for c in customers]
        sales_rows = db.session.query(
            Sale.customer_id,
            db.func.coalesce(db.func.sum(Sale.amount_aed), 0).label('sales_total'),
        ).filter(
            Sale.status == 'confirmed',
            Sale.branch_id == scoped_branch,
            Sale.customer_id.in_(customer_ids),
        ).group_by(Sale.customer_id).all()
        receipts_rows = db.session.query(
            Receipt.customer_id,
            db.func.coalesce(db.func.sum(Receipt.amount_aed), 0).label('receipts_total'),
        ).filter(
            Receipt.branch_id == scoped_branch,
            Receipt.customer_id.in_(customer_ids),
        ).group_by(Receipt.customer_id).all()
        outgoing_rows = db.session.query(
            Payment.customer_id,
            db.func.coalesce(db.func.sum(Payment.amount_aed), 0).label('outgoing_total'),
        ).filter(
            Payment.direction == 'outgoing',
            Payment.branch_id == scoped_branch,
            Payment.customer_id.in_(customer_ids),
        ).group_by(Payment.customer_id).all()

        sales_map = {cid: Decimal(str(total or 0)) for cid, total in sales_rows}
        receipts_map = {cid: Decimal(str(total or 0)) for cid, total in receipts_rows}
        outgoing_map = {cid: Decimal(str(total or 0)) for cid, total in outgoing_rows}

        for cid in customer_ids:
            balance_map[cid] = sales_map.get(cid, Decimal('0')) + outgoing_map.get(cid, Decimal('0')) - receipts_map.get(cid, Decimal('0'))

    headers = [
        'الاسم',
        'الاسم (ع)',
        'النوع',
        'الهاتف',
        'الإيميل',
        'العملة المفضلة',
        'الرصيد',
        'تاريخ الإنشاء',
    ]

    data = []
    for c in customers:
        if scoped_branch is not None:
            bal = balance_map.get(c.id, Decimal('0'))
        else:
            bal = Decimal(str(c.balance or 0))
        data.append([
            c.name,
            c.name_ar or '',
            c.customer_type or '',
            c.phone or '',
            c.email or '',
            c.preferred_currency or '',
            float(bal),
            c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
        ])

    base_name = f"customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == 'xlsx':
        output = ExportService.export_to_xlsx(data, headers, filename=f'{base_name}.xlsx', sheet_name='Customers')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{base_name}.xlsx',
        )

    output = ExportService.export_to_csv(data, headers, filename=f'{base_name}.csv')
    return send_file(
        output,
        mimetype='text/csv; charset=utf-8',
        as_attachment=True,
        download_name=f'{base_name}.csv',
    )


@customers_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_customers')
@limiter.limit("10 per minute", methods=['POST'])
def create():
    from forms.customer import CustomerForm
    form = CustomerForm()
    
    if form.validate_on_submit():
        try:
            from utils.field_validators import normalize_phone_optional, validate_currency_code
            try:
                from models import Tenant
                default_currency = (Tenant.get_current().default_currency or '').strip() or 'AED'
            except Exception:
                default_currency = 'AED'

            # Check tenant customer limit
            try:
                from utils.tenant_limits import check_customers_limit, TenantLimitError
                check_customers_limit()
            except TenantLimitError as e:
                flash(str(e), 'danger')
                return redirect(url_for('customers.create'))

            customer = Customer(
                name=form.name.data,
                name_ar=form.name_ar.data,
                customer_type=form.customer_type.data,
                phone=normalize_phone_optional(form.phone.data),
                email=form.email.data,
                address=form.address.data,
                tax_number=form.tax_number.data,
                preferred_currency=validate_currency_code(form.preferred_currency.data or default_currency),
                is_active=bool(form.is_active.data),
                notes=form.notes.data
            )
            
            db.session.add(customer)
            db.session.commit()
            
            create_audit_log('create', 'customers', customer.id)
            
            flash('✅ تم إضافة الزبون بنجاح!', 'success')
            return redirect(url_for('customers.index'))
        
        except Exception as e:
            db.session.rollback()
            from utils.error_messages import ErrorMessages
            current_app.logger.error(f"Error in customer operation: {e}")
            flash(ErrorMessages.database_error(), 'danger')
    
    return render_template('customers/create.html', form=form)


@customers_bp.route('/<int:id>')
@login_required
@permission_required('manage_customers')
def view(id):
    customer = tenant_get_or_404(Customer, id)
    if not _customer_in_scope(id):
        return render_template('errors/403.html'), 403
    
    sales = Sale.query.filter_by(customer_id=id)
    if branch_scope_id() is not None:
        sales = sales.filter(Sale.branch_id == branch_scope_id())
    sales = sales.order_by(Sale.sale_date.desc()).limit(20).all()
    
    balance = _get_customer_balance(id)
    
    unpaid_sales = _get_unpaid_sales(id)
    
    return render_template('customers/view.html',
                         customer=customer,
                         sales=sales,
                         balance=balance,
                         unpaid_sales=unpaid_sales)


@customers_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('manage_customers')
def edit(id):
    customer = tenant_get_or_404(Customer, id)
    if not _customer_in_scope(id):
        return render_template('errors/403.html'), 403
    
    if request.method == 'POST':
        try:
            customer.name = request.form.get('name')
            customer.name_ar = request.form.get('name_ar')
            customer.customer_type = request.form.get('customer_type')
            from utils.field_validators import normalize_phone_optional, validate_currency_code
            try:
                from models import Tenant
                default_currency = (Tenant.get_current().default_currency or '').strip() or 'AED'
            except Exception:
                default_currency = 'AED'

            customer.phone = normalize_phone_optional(request.form.get('phone'))
            customer.email = request.form.get('email')
            customer.address = request.form.get('address')
            customer.tax_number = request.form.get('tax_number')
            customer.preferred_currency = validate_currency_code(
                request.form.get('preferred_currency') or request.form.get('default_currency') or default_currency
            )
            is_active_raw = request.form.get('is_active', '1')
            customer.is_active = str(is_active_raw) in ('1', 'true', 'on', 'True')
            customer.notes = request.form.get('notes')
            
            db.session.commit()
            
            create_audit_log('update', 'customers', customer.id)
            
            flash('✅ تم تحديث بيانات الزبون بنجاح!', 'success')
            return redirect(url_for('customers.view', id=customer.id))
        
        except Exception as e:
            db.session.rollback()
            from utils.error_messages import ErrorMessages
            current_app.logger.error(f"Error in customer operation: {e}")
            flash(ErrorMessages.database_error(), 'danger')
    
    return render_template('customers/edit.html', customer=customer)


@customers_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('manage_customers')
def delete(id):
    customer = tenant_get_or_404(Customer, id)
    if not _customer_in_scope(id):
        return render_template('errors/403.html'), 403
    
    try:
        # Check for related records preventing deletion
        sales_query = Sale.query.filter_by(customer_id=id)
        from models import Payment, Receipt
        payments_query = Payment.query.filter_by(customer_id=id)
        receipts_query = Receipt.query.filter_by(customer_id=id)
        if branch_scope_id() is not None:
            sales_query = sales_query.filter(Sale.branch_id == branch_scope_id())
            payments_query = payments_query.filter(Payment.branch_id == branch_scope_id())
            receipts_query = receipts_query.filter(Receipt.branch_id == branch_scope_id())
        sales_count = sales_query.count()
        payments_count = payments_query.count()
        receipts_count = receipts_query.count()
        
        if sales_count > 0 or payments_count > 0 or receipts_count > 0:
            customer.is_active = False
            db.session.commit()
            flash(f'⚠️ تم إلغاء تفعيل العميل "{customer.name}" بدلاً من حذفه لوجود ({sales_count} فاتورة، {payments_count} دفعة، {receipts_count} سند قبض) مرتبطة به.', 'warning')
        else:
            db.session.delete(customer)
            db.session.commit()
            flash(f'✅ تم حذف العميل "{customer.name}" نهائياً!', 'success')
        
        create_audit_log('delete', 'customers', id)
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting customer {id}: {e}")
        # Fallback to soft delete if hard delete fails (e.g. other constraints)
        try:
            # Re-fetch customer to ensure it's attached to the new session transaction
            customer = Customer.query.get(id)
            if customer:
                customer.is_active = False
                db.session.add(customer)
                db.session.commit()
                flash(f'⚠️ تعذر الحذف النهائي للعميل "{customer.name}" بسبب ارتباطات في قاعدة البيانات. تم إلغاء تفعيله بدلاً من ذلك.', 'warning')
        except Exception as inner_e:
            current_app.logger.error(f"Error falling back to soft delete for customer {id}: {inner_e}")
            from utils.error_messages import ErrorMessages
            flash(ErrorMessages.delete_failed('العميل'), 'danger')
    
    return redirect(url_for('customers.index'))


@customers_bp.route('/<int:id>/statement')
@login_required
@permission_required('manage_customers')
def statement(id):
    customer = tenant_get_or_404(Customer, id)
    if not _customer_in_scope(id):
        return render_template('errors/403.html'), 403
    
    try:
        from models import Tenant
        default_currency = (Tenant.get_current().default_currency or '').strip() or 'AED'
    except Exception:
        default_currency = 'AED'
    
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)
    transaction_type = request.args.get('transaction_type', 'all')
    
    from sqlalchemy import func
    from models import Payment
    
    sales_query = Sale.query.filter_by(customer_id=id, status='confirmed')
    payments_query = Payment.query.filter_by(customer_id=id)
    if branch_scope_id() is not None:
        sales_query = sales_query.filter(Sale.branch_id == branch_scope_id())
        payments_query = payments_query.filter(Payment.branch_id == branch_scope_id())
    
    if date_from:
        sales_query = sales_query.filter(func.date(Sale.sale_date) >= date_from)
        payments_query = payments_query.filter(func.date(Payment.payment_date) >= date_from)
    
    if date_to:
        sales_query = sales_query.filter(func.date(Sale.sale_date) <= date_to)
        payments_query = payments_query.filter(func.date(Payment.payment_date) <= date_to)
    
    sales = sales_query.order_by(Sale.sale_date).all()
    payments = payments_query.order_by(Payment.payment_date).all()

    transactions = []

    for sale in sales:
        sale_lines_data = []
        for idx, line in enumerate(sale.lines, start=1):
            quantity = Decimal(str(line.quantity or 0))
            unit_price = Decimal(str(line.unit_price or 0))
            discount_percent = Decimal(str(line.discount_percent or 0))
            gross_amount = (quantity * unit_price)
            discount_value = (gross_amount * discount_percent / Decimal('100')) if discount_percent else Decimal('0')
            sale_lines_data.append({
                'index': idx,
                'product_name': line.product.get_display_name('ar') if line.product else 'بند غير معرف',
                'product_sku': line.product.sku if line.product and line.product.sku else None,
                'unit': line.product.unit if line.product and hasattr(line.product, 'unit') else None,
                'quantity': float(quantity),
                'unit_price': float(unit_price),
                'discount_percent': float(discount_percent),
                'discount_value': float(discount_value),
                'gross_amount': float(gross_amount),
                'line_total': float(line.line_total or 0),
                'notes': line.notes or ''
            })

        sale_payments = sale.payments.order_by(Payment.payment_date.asc()).all()
        sale_payments_data = []
        last_payment_date = None

        for payment in sale_payments:
            if last_payment_date is None or payment.payment_date > last_payment_date:
                last_payment_date = payment.payment_date

            cheque = payment.cheque if hasattr(payment, 'cheque') else None
            sale_payments_data.append({
                'id': payment.id,
                'payment_number': payment.payment_number,
                'payment_date': payment.payment_date,
                'amount_aed': float(payment.amount_aed or 0),
                'amount_original': float(payment.amount or 0),
                'currency': payment.currency or default_currency,
                'exchange_rate': float(payment.exchange_rate or 1),
                'reference_number': payment.reference_number or '-',
                'payment_method': payment.payment_method,
                'payment_method_display': payment.get_method_display('ar') if hasattr(payment, 'get_method_display') else payment.payment_method,
                'status_ar': payment.status_ar if hasattr(payment, 'status_ar') else ('مؤكدة ✅' if payment.payment_confirmed else 'معلقة ⏳'),
                'payment_confirmed': payment.payment_confirmed,
                'user': payment.user.get_display_name('ar') if payment.user and hasattr(payment.user, 'get_display_name') else (payment.user.full_name if payment.user else None),
                'notes': payment.notes or '',
                'direction': payment.direction,
                'cheque_number': cheque.cheque_number if cheque else payment.cheque_number,
                'cheque_bank': cheque.bank_name if cheque else payment.bank_name,
                'cheque_due_date': cheque.due_date if cheque else None
            })

        sale_data = {
            'id': sale.id,
            'number': sale.sale_number,
            'date': sale.sale_date,
            'status': sale.payment_status,
            'subtotal': float(sale.subtotal or 0),
            'discount_amount': float(sale.discount_amount or 0),
            'shipping_cost': float(sale.shipping_cost or 0),
            'tax_rate': float(sale.tax_rate or 0),
            'tax_amount': float(sale.tax_amount or 0),
            'total_amount': float(sale.total_amount or sale.amount_aed or 0),
            'amount_aed': float(sale.amount_aed or 0),
            'paid_amount': float(sale.paid_amount_aed or 0),
            'balance_due': float(sale.balance_due or 0),
            'currency': sale.currency or default_currency,
            'exchange_rate': float(sale.exchange_rate or 1),
            'seller': sale.seller.get_display_name('ar') if sale.seller and hasattr(sale.seller, 'get_display_name') else (sale.seller.full_name if sale.seller else None),
            'notes': sale.notes or '',
            'lines': sale_lines_data,
            'payments': sale_payments_data,
            'last_payment_date': last_payment_date
        }

        transactions.append({
            'date': sale.sale_date,
            'type': 'sale',
            'reference': sale.sale_number,
            'debit': float(sale.amount_aed or 0),
            'credit': 0,
            'balance': 0,
            'description': 'فاتورة بيع',
            'currency': sale.currency or default_currency,
            'exchange_rate': float(sale.exchange_rate or 1),
            'paid_amount': float(sale.paid_amount_aed or 0),
            'balance_due': float(sale.balance_due or 0),
            'status': sale.payment_status,
            'sale': sale_data
        })

    for payment in payments:
        credit_amount = float(payment.amount_aed or 0) if payment.direction == 'incoming' else 0.0
        debit_amount = float(payment.amount_aed or 0) if payment.direction != 'incoming' else 0.0

        cheque = payment.cheque if hasattr(payment, 'cheque') else None

        transactions.append({
            'date': payment.payment_date,
            'type': 'payment',
            'reference': payment.reference_number or payment.payment_number or f'دفع #{payment.id}',
            'debit': debit_amount,
            'credit': credit_amount,
            'balance': 0,
            'description': f'دفعة - {payment.get_method_display("ar") if hasattr(payment, "get_method_display") else payment.payment_method}',
            'currency': payment.currency or default_currency,
            'exchange_rate': float(payment.exchange_rate or 1),
            'paid_amount': credit_amount,
            'balance_due': 0,
            'status': payment.status_ar if hasattr(payment, 'status_ar') else ('مؤكدة ✅' if payment.payment_confirmed else 'معلقة ⏳'),
            'payment': {
                'id': payment.id,
                'payment_number': payment.payment_number,
                'payment_date': payment.payment_date,
                'amount_aed': float(payment.amount_aed or 0),
                'amount_original': float(payment.amount or 0),
                'base_amount': float(payment.amount_aed or 0),
                'currency': payment.currency or default_currency,
                'exchange_rate': float(payment.exchange_rate or 1),
                'payment_method': payment.payment_method,
                'payment_method_display': payment.get_method_display('ar') if hasattr(payment, 'get_method_display') else payment.payment_method,
                'reference_number': payment.reference_number or '-',
                'direction': payment.direction,
                'payment_confirmed': payment.payment_confirmed,
                'status_ar': payment.status_ar if hasattr(payment, 'status_ar') else ('مؤكدة ✅' if payment.payment_confirmed else 'معلقة ⏳'),
                'user': payment.user.get_display_name('ar') if payment.user and hasattr(payment.user, 'get_display_name') else (payment.user.full_name if payment.user else None),
                'notes': payment.notes or '',
                'cheque_number': cheque.cheque_number if cheque else payment.cheque_number,
                'cheque_bank': cheque.bank_name if cheque else payment.bank_name,
                'cheque_due_date': cheque.due_date if cheque else payment.cheque_date,
                'cheque_clearance_date': cheque.clearance_date if cheque else None
            }
        })

    transactions.sort(key=lambda x: (x['date'] or datetime.min))

    if transaction_type in {'sale', 'payment'}:
        transactions = [trans for trans in transactions if trans['type'] == transaction_type]

    running_balance = 0
    for trans in transactions:
        running_balance += trans['debit'] - trans['credit']
        trans['balance'] = running_balance

    return render_template(
        'customers/statement.html',
        customer=customer,
        transactions=transactions,
        final_balance=running_balance,
        filters={
            'date_from': date_from or '',
            'date_to': date_to or '',
            'transaction_type': transaction_type
        }
    )


@customers_bp.route('/api/search')
@login_required
@permission_required('manage_customers')
def api_search():
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    base_query = _scoped_customer_query().filter(Customer.is_active == True).order_by(Customer.name)
    
    # السماح بالبحث حتى بدون query (لعرض كل العملاء)
    if query and len(query) >= 1:
        customers = base_query.filter(
            db.or_(
                Customer.name.ilike(f'%{query}%'),
                Customer.phone.ilike(f'%{query}%'),
                Customer.email.ilike(f'%{query}%')
            )
        ).order_by(Customer.name).limit(per_page).all()
    else:
        # عرض كل العملاء (مرتبين أبجدياً)
        customers = base_query.limit(per_page).all()
    
    results = [{
        'id': c.id,
        'name': c.name,
        'phone': c.phone or '',
        'text': f"{c.name} - {c.phone}" if c.phone else c.name,
        'customer_type': c.customer_type,
        'customer_classification': c.customer_classification,
        'balance': float(_get_customer_balance(c.id))
    } for c in customers]
    
    return jsonify(results)


@customers_bp.route('/<int:id>/balance')
@login_required
@permission_required('manage_payments')
def customer_balance(id):
    """رصيد العميل + فواتير غير المدفوعة - API موحد (مصدر واحد مع payments)."""
    customer = tenant_get_or_404(Customer, id)
    if not _customer_in_scope(id):
        return jsonify({'error': 'forbidden'}), 403
    try:
        from models import Tenant
        default_currency = (Tenant.get_current().default_currency or '').strip() or 'AED'
    except Exception:
        default_currency = 'AED'
    return jsonify({
        'balance_aed': float(_get_customer_balance(id)),
        'balance': float(_get_customer_balance(id)),
        'currency': default_currency,
        'unpaid_sales': [{
            'id': s.id,
            'sale_number': s.sale_number,
            'sale_date': s.sale_date.strftime('%Y-%m-%d') if getattr(s.sale_date, 'strftime', None) else str(s.sale_date),
            'total_amount': float(s.total_amount),
            'balance_due': float(s.balance_due),
            'currency': s.currency or default_currency,
        } for s in _get_unpaid_sales(id)]
    })


@customers_bp.route('/<int:id>/sales')
@login_required
@permission_required('manage_customers')
def customer_sales(id):
    customer = tenant_get_or_404(Customer, id)
    if not _customer_in_scope(id):
        return render_template('errors/403.html'), 403
    
    sales = Sale.query.filter_by(
        customer_id=id, 
        status='confirmed'
    )
    if branch_scope_id() is not None:
        sales = sales.filter(Sale.branch_id == branch_scope_id())
    sales = sales.order_by(Sale.sale_date.desc()).all()
    
    sales_data = []
    for sale in sales:
        balance = sale.amount_aed - sale.paid_amount_aed
        if balance > 0:
            sales_data.append({
                'id': sale.id,
                'invoice_number': sale.sale_number or f'#{sale.id}',
                'sale_date': sale.sale_date.strftime('%Y-%m-%d'),
                'amount_aed': float(sale.amount_aed),
                'paid_amount_aed': float(sale.paid_amount_aed),
                'balance': float(balance)
            })
    
    return jsonify({'sales': sales_data})

