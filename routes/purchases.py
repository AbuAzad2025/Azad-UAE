from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from extensions import db, limiter, csrf
from models import Purchase, PurchaseLine, PurchaseReturn, PurchaseReturnLine, Product, Supplier, Warehouse
from services.stock_service import StockService
from services.currency_service import CurrencyService
from services.gl_service import GLService
from services.purchase_service import PurchaseService
from utils.decorators import permission_required
from utils.branching import ensure_warehouse_access, get_accessible_warehouses, should_show_all_branch_columns
from services.logging_core import LoggingCore
from utils.helpers import generate_number
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from decimal import Decimal
from utils.tenanting import tenant_query, tenant_get_or_404
from utils.db_safety import atomic_transaction
from utils.structured_logging import log_mutation
from utils.gl_reference_types import GLRef, delete_entries_by_ref

purchases_bp = Blueprint('purchases', __name__, url_prefix='/purchases')


@purchases_bp.route('/')
@login_required
@permission_required('manage_purchases')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '', type=str)
    
    query = tenant_query(Purchase)
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                Purchase.purchase_number.ilike(search_filter),
                Purchase.supplier_name.ilike(search_filter)
            )
        )
    query = query.filter_by(status='confirmed')
    from utils.decorators import branch_scope_id
    branch_id = branch_scope_id()
    if branch_id is not None:
        query = query.filter(Purchase.branch_id == branch_id)
    pagination = query.order_by(Purchase.purchase_date.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    return render_template('purchases/index.html',
                         purchases=pagination.items,
                         pagination=pagination,
                         show_branch_columns=should_show_all_branch_columns(current_user))


@purchases_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_purchases')
@limiter.limit("10 per minute", methods=['POST'])
def create():
    warehouse_id_val = request.form.get('warehouse_id', type=int) if request.method == 'POST' else None

    if request.method == 'POST':
        try:
            current_app.logger.info("POST request received for purchase creation")
            
            warehouse_id_val = request.form.get('warehouse_id', type=int)
            if not warehouse_id_val:
                flash('⚠️ يجب اختيار المستودع الذي ستُضاف إليه البضاعة.', 'danger')
                return redirect(url_for('purchases.create'))
            ensure_warehouse_access(warehouse_id_val, user=current_user)

            # Parse Lines
            lines_data = []
            line_count = int(request.form.get('line_count', 0))
            
            for i in range(line_count):
                product_id = request.form.get(f'lines[{i}][product_id]', type=int)
                quantity = request.form.get(f'lines[{i}][quantity]', type=float)
                unit_cost = request.form.get(f'lines[{i}][unit_cost]', type=float)
                discount_percent = request.form.get(f'lines[{i}][discount_percent]', type=float, default=0)
                serials_raw = request.form.get(f'lines[{i}][serials]', '')
                serials = [s.strip() for s in serials_raw.split('\n') if s.strip()] if serials_raw else []
                if product_id and quantity and quantity > 0:
                    lines_data.append({
                        'product_id': product_id,
                        'quantity': quantity,
                        'unit_cost': unit_cost,
                        'discount_percent': discount_percent,
                        'serials': serials,
                    })
            
            # Create Purchase via Service
            try:
                from models import Tenant
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()

            with atomic_transaction('purchase_creation'):
                purchase = PurchaseService.create_purchase(
                    user=current_user,
                supplier_data={
                    'supplier_id': request.form.get('supplier_id', type=int),
                    'supplier_name': request.form.get('supplier_name', ''),
                    'phone': request.form.get('supplier_phone', ''),
                    'email': request.form.get('supplier_email', '')
                },
                lines_data=lines_data,
                warehouse_id=warehouse_id_val,
                currency=request.form.get('currency') or default_currency,
                user_exchange_rate=request.form.get('exchange_rate', type=float),
                discount_amount=request.form.get('discount_amount', type=float, default=0),
                tax_rate=request.form.get('tax_rate', type=float, default=0),
                notes=request.form.get('notes'),
                freight=request.form.get('freight', type=float, default=0),
                insurance=request.form.get('insurance', type=float, default=0),
                customs_duty=request.form.get('customs_duty', type=float, default=0),
                other_landed_cost=request.form.get('other_landed_cost', type=float, default=0)
            )
            
            flash('✅ تم إنشاء فاتورة الشراء بنجاح!', 'success')
            return redirect(url_for('purchases.view', id=purchase.id))
        
        except ValueError as e:
            db.session.rollback()
            flash(f'⚠️ {str(e)}', 'warning')
        except Exception as e:
            current_app.logger.error(f"Error in purchase creation: {str(e)}")
            current_app.logger.error(f"Error type: {type(e)}")
            import traceback
            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            db.session.rollback()
            flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
    
    try:
        from models import Tenant
        tenant = Tenant.get_current()
        base_currency = resolve_default_currency(tenant)
    except Exception:
        base_currency = get_system_default_currency()
    exchange_rates = CurrencyService.get_all_rates(base_currency)
    warehouses = get_accessible_warehouses(current_user)
    
    return render_template('purchases/create.html', exchange_rates=exchange_rates, warehouses=warehouses)


@purchases_bp.route('/<int:id>')
@login_required
@permission_required('manage_purchases')
def view(id):
    purchase = tenant_get_or_404(Purchase, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    return render_template('purchases/view.html', purchase=purchase)


@purchases_bp.route('/<int:id>/print')
@login_required
@permission_required('manage_purchases')
def print_purchase(id):
    purchase = tenant_get_or_404(Purchase, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context
    tid = purchase.tenant_id
    tenant, settings, company = InvoiceSettings.company_print_context(tid)
    print_branding = get_print_header_context(tid)
    return render_template(
        'purchases/print.html',
        purchase=purchase,
        company=company,
        settings=settings,
        print_branding=print_branding,
        print_tenant_id=tid,
    )


@purchases_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('manage_purchases')
def edit(id):
    """تعديل فاتورة شراء - الملاحظات والخصم فقط"""
    purchase = tenant_get_or_404(Purchase, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    
    # منع التعديل للفواتير المدفوعة
    if purchase.get_paid_amount() > 0:
        flash('⚠️ لا يمكن تعديل فاتورة شراء تم الدفع عليها.\n💡 للحفاظ على السجلات المحاسبية.', 'danger')
        return redirect(url_for('purchases.view', id=id))
    
    if request.method == 'POST':
        try:
            # تعديل الملاحظات فقط
            purchase.notes = request.form.get('notes', '')
            
            db.session.commit()
            LoggingCore.log_audit('update', 'purchases', id)
            
            flash('✅ تم تحديث فاتورة الشراء بنجاح!', 'success')
            return redirect(url_for('purchases.view', id=id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات.', 'danger')
    
    return render_template('purchases/edit.html', purchase=purchase)


@purchases_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('manage_purchases')
def delete(id):
    """حذف (أرشفة) فاتورة شراء"""
    from services.archive_service import ArchiveService
    from models import Payment, Cheque, GLJournalEntry, PurchaseLine
    from services.gl_service import GLService
    
    purchase = tenant_get_or_404(Purchase, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    
    # التحقق من الارتباطات
    has_links = False
    
    # 1. التحقق من المدفوعات (Payments - outgoing linked to this purchase)
    # ملاحظة: المدفوعات للموردين قد لا تكون مرتبطة مباشرة بحقل purchase_id في جدول payments القديم،
    # ولكن إذا كان هناك حقل purchase_id أو عبر supplier_id وتاريخ متزامن، 
    # لكن سنفترض وجود علاقة أو استخدام get_paid_amount() كمؤشر
    if purchase.get_paid_amount() > 0:
        has_links = True
        
    # 2. التحقق من الشيكات (Cheques)
    linked_cheques = Cheque.query.filter_by(purchase_id=purchase.id, tenant_id=purchase.tenant_id).count()
    if linked_cheques > 0:
        has_links = True

    # التحقق من حركات المخزون (منع الحذف النهائي للفواتير التي أثرت على المخزون)
    from models.warehouse import StockMovement
    has_stock = StockMovement.query.filter_by(
        reference_type=GLRef.PURCHASE,
        reference_id=purchase.id,
    ).count() > 0

    try:
        if has_links:
            # أرشفة فقط (بدون عكس القيد - الأرشفة إخفاء إداري)
            archive_service = ArchiveService()
            archive_service.archive_record('purchases', purchase, reason='تم أرشفة الفاتورة لوجود مدفوعات أو شيكات', commit=False)
            
            LoggingCore.log_audit('archive', 'purchases', id)
            db.session.commit()
            flash(f'✅ تم أرشفة فاتورة الشراء "{purchase.purchase_number}" (لوجود ارتباطات مالية)', 'warning')
        elif has_stock:
            # منع الحذف النهائي لفواتير الشراء التي أثرت على المخزون
            flash(f'⚠️ لا يمكن حذف فاتورة الشراء "{purchase.purchase_number}" لأنها أثرت على المخزون. يمكنك أرشفتها بدلاً من ذلك.', 'warning')
            archive_service = ArchiveService()
            archive_service.archive_record('purchases', purchase, reason='تم أرشفة الفاتورة لوجود حركة مخزون', commit=False)
            LoggingCore.log_audit('archive', 'purchases', id)
            db.session.commit()
        else:
            # حذف نهائي (Hard Delete) - فقط للفواتير غير المرتبطة
            PurchaseLine.query.filter_by(purchase_id=purchase.id).delete()
            delete_entries_by_ref(purchase.id, GLRef.PURCHASE)
            db.session.delete(purchase)
            LoggingCore.log_audit('delete', 'purchases', id)
            db.session.commit()
            flash(f'✅ تم حذف فاتورة الشراء "{purchase.purchase_number}" نهائياً', 'success')
            
        return redirect(url_for('purchases.index'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'❌ حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('purchases.view', id=id))


@purchases_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@permission_required('manage_purchases')
def cancel(id):
    """إلغاء فاتورة شراء مع عكس القيد المحاسبي والمخزون ورصيد المورد"""
    purchase = tenant_get_or_404(Purchase, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403

    try:
        PurchaseService.cancel_purchase(purchase)
        LoggingCore.log_audit('cancel', 'purchases', purchase.id)
        flash('✅ تم إلغاء فاتورة الشراء بنجاح!', 'success')
    except ValueError as e:
        flash(f'❌ {str(e)}', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ حدث خطأ: {str(e)}', 'danger')

    return redirect(url_for('purchases.view', id=id))


@purchases_bp.route('/<int:id>/return', methods=['GET', 'POST'])
@login_required
@permission_required('manage_purchases')
def purchase_return(id):
    """إنشاء مرتجع مشتريات"""
    purchase = tenant_get_or_404(Purchase, id)
    from utils.decorators import branch_scope_id
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403

    if purchase.status in ('draft', 'cancelled'):
        flash('❌ لا يمكن عمل مرتجع لفاتورة شراء في حالة مسودة أو ملغاة', 'danger')
        return redirect(url_for('purchases.view', id=id))

    if request.method == 'POST':
        lines_data = request.json.get('lines', []) if request.is_json else request.form.getlist('lines')
        reason = request.form.get('reason', '')
        notes = request.form.get('notes', '')

        if not lines_data:
            flash('❌ يجب تحديد منتج واحد على الأقل للإرجاع', 'danger')
            return redirect(url_for('purchases.purchase_return', id=id))

        try:
            result = PurchaseService.create_purchase_return(
                purchase, current_user, lines_data, reason=reason, notes=notes,
            )
            flash(f'✅ تم إنشاء مرتجع المشتريات رقم {result.return_number} بنجاح!', 'success')
            return redirect(url_for('purchases.view', id=id))
        except ValueError as e:
            flash(f'❌ {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ حدث خطأ: {str(e)}', 'danger')
            current_app.logger.exception('Purchase return error')

    returns = PurchaseReturn.query.filter_by(purchase_id=purchase.id).order_by(PurchaseReturn.created_at.desc()).all()
    return_lines = PurchaseReturnLine.query.filter(PurchaseReturnLine.return_id.in_([r.id for r in returns])).all() if returns else []
    return render_template('purchases/return.html', purchase=purchase, returns=returns, return_lines=return_lines)


# =====================================
# API Endpoints - Backend Calculations
# =====================================

@purchases_bp.route('/api/calculate-totals', methods=['POST'])
@login_required
@permission_required('manage_purchases')
def api_calculate_purchase_totals():
    """API لحساب إجماليات فاتورة المشتريات - Backend Calculation"""
    try:
        from flask import jsonify
        
        data = request.get_json(force=True)
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        lines = data.get('lines', [])
        tax_rate = Decimal(str(data.get('tax_rate', 0)))
        from utils.tax_settings import normalize_tax_rate
        tax_rate = normalize_tax_rate(tax_rate)
        
        # حساب المجموع الفرعي
        subtotal = Decimal('0')
        for line in lines:
            try:
                qty = Decimal(str(line.get('quantity', 0)))
                cost = Decimal(str(line.get('unit_cost', 0)))
                discount_percent = Decimal(str(line.get('discount_percent', 0)))
                
                if qty > 0 and cost > 0:
                    line_subtotal = qty * cost
                    line_discount = line_subtotal * (discount_percent / Decimal('100'))
                    line_total = line_subtotal - line_discount
                    subtotal += line_total
            except (ValueError, TypeError, KeyError):
                continue
        
        # حساب تكاليف الوصول
        freight = Decimal(str(data.get('freight', 0) or 0))
        insurance = Decimal(str(data.get('insurance', 0) or 0))
        customs_duty = Decimal(str(data.get('customs_duty', 0) or 0))
        other_landed_cost = Decimal(str(data.get('other_landed_cost', 0) or 0))
        landed_total = freight + insurance + customs_duty + other_landed_cost

        # حساب الضريبة والإجمالي
        tax_amount = subtotal * (tax_rate / Decimal('100'))
        total = subtotal + tax_amount + landed_total

        return jsonify({
            'success': True,
            'subtotal': float(subtotal),
            'tax_rate': float(tax_rate),
            'tax_amount': float(tax_amount),
            'landed_cost': float(landed_total),
            'total': float(total),
            'line_count': len([l for l in lines if Decimal(str(l.get('quantity', 0))) > 0])
        }), 200
        
    except Exception:
        current_app.logger.exception('calculate_purchase_totals failed')
        return jsonify({'success': False, 'error': 'تعذر حساب الإجماليات حالياً'}), 500

