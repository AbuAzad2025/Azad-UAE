from datetime import datetime, timedelta, timezone
from decimal import Decimal
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, select
from extensions import db
from models import PartnerCommissionEntry, Sale, SaleLine, Purchase, Product, Customer, ProductPartner
from utils.decorators import permission_required, branch_scope_id
from utils.tenanting import get_active_tenant_id, tenant_query, apply_tenant_scope

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


def _scoped_customer_query():
    from models import Payment, Receipt

    query = tenant_query(Customer)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        return query

    sale_ids = select(Sale.customer_id).where(Sale.customer_id.isnot(None), Sale.branch_id == scoped_branch_id)
    payment_ids = select(Payment.customer_id).where(Payment.customer_id.isnot(None), Payment.branch_id == scoped_branch_id)
    receipt_ids = select(Receipt.customer_id).where(Receipt.customer_id.isnot(None), Receipt.branch_id == scoped_branch_id)
    return query.filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))


def _scoped_supplier_query():
    from models import Payment

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        from models import Supplier
        return tenant_query(Supplier)

    from models import Supplier
    purchase_ids = select(Purchase.supplier_id).where(Purchase.supplier_id.isnot(None), Purchase.branch_id == scoped_branch_id)
    payment_ids = select(Payment.supplier_id).where(Payment.supplier_id.isnot(None), Payment.branch_id == scoped_branch_id)
    return tenant_query(Supplier).filter(Supplier.id.in_(purchase_ids.union(payment_ids)))


@reports_bp.route('/')
@login_required
@permission_required('view_reports')
def index():
    return render_template('reports/index.html')


@reports_bp.route('/partners')
@login_required
@permission_required('view_reports')
def partners():
    """تقرير الشركاء والمنتجات التابعة للتجار"""
    from models import Payment, Receipt, Supplier
    
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)
    scoped_branch_id = branch_scope_id()
    
    tenant_id = get_active_tenant_id(current_user)

    partners_data = []
    partner_share_totals = {}

    entries_query = db.session.query(PartnerCommissionEntry.id).join(Sale, PartnerCommissionEntry.sale_id == Sale.id).filter(
        Sale.status == 'confirmed'
    )
    if tenant_id is not None:
        entries_query = entries_query.filter(PartnerCommissionEntry.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        entries_query = entries_query.filter(PartnerCommissionEntry.branch_id == scoped_branch_id)
    if date_from:
        entries_query = entries_query.filter(func.date(Sale.sale_date) >= date_from)
    if date_to:
        entries_query = entries_query.filter(func.date(Sale.sale_date) <= date_to)

    has_entries = db.session.query(entries_query.exists()).scalar()

    if has_entries:
        rows = db.session.query(
            Product.name.label('product_name'),
            Customer.name.label('partner_name'),
            PartnerCommissionEntry.percentage.label('percentage'),
            func.coalesce(func.sum(SaleLine.quantity), 0).label('total_qty'),
            func.coalesce(func.sum(PartnerCommissionEntry.base_amount_aed), 0).label('total_revenue'),
            func.coalesce(func.sum(PartnerCommissionEntry.commission_amount_aed), 0).label('partner_share_amount'),
            Customer.id.label('partner_id'),
        ).join(
            Sale, PartnerCommissionEntry.sale_id == Sale.id
        ).join(
            Customer, PartnerCommissionEntry.partner_customer_id == Customer.id
        ).outerjoin(
            SaleLine, PartnerCommissionEntry.sale_line_id == SaleLine.id
        ).outerjoin(
            Product, PartnerCommissionEntry.product_id == Product.id
        ).filter(
            Sale.status == 'confirmed'
        )

        if tenant_id is not None:
            rows = rows.filter(PartnerCommissionEntry.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            rows = rows.filter(PartnerCommissionEntry.branch_id == scoped_branch_id)
        if date_from:
            rows = rows.filter(func.date(Sale.sale_date) >= date_from)
        if date_to:
            rows = rows.filter(func.date(Sale.sale_date) <= date_to)

        rows = rows.group_by(
            Product.name,
            Customer.name,
            PartnerCommissionEntry.percentage,
            Customer.id,
        ).all()

        for r in rows:
            total_qty = Decimal(str(r.total_qty or 0))
            total_revenue = Decimal(str(r.total_revenue or 0))
            partner_amount = Decimal(str(r.partner_share_amount or 0))
            avg_unit_price = (total_revenue / total_qty) if total_qty > 0 else Decimal('0')
            partners_data.append({
                'product_name': r.product_name or '',
                'partner_name': r.partner_name or '',
                'percentage': r.percentage,
                'avg_unit_price': avg_unit_price,
                'total_qty': total_qty,
                'total_revenue': total_revenue,
                'partner_share_amount': partner_amount
            })
            partner_share_totals[r.partner_id] = partner_share_totals.get(r.partner_id, Decimal('0')) + partner_amount
    else:
        partner_products = Product.query.join(ProductPartner).filter(Product.is_active == True).distinct().all()

        for product in partner_products:
            sales_query = SaleLine.query.join(Sale).filter(
                SaleLine.product_id == product.id,
                Sale.status == 'confirmed'
            )
            if scoped_branch_id is not None:
                sales_query = sales_query.filter(Sale.branch_id == scoped_branch_id)

            if date_from:
                sales_query = sales_query.filter(func.date(Sale.sale_date) >= date_from)
            if date_to:
                sales_query = sales_query.filter(func.date(Sale.sale_date) <= date_to)

            sales_lines = sales_query.all()

            total_revenue = sum(line.line_total for line in sales_lines)
            total_qty = sum(line.quantity for line in sales_lines)

            avg_unit_price = total_revenue / total_qty if total_qty > 0 else 0

            if total_revenue > 0:
                for share in product.partner_shares:
                    percentage = Decimal(str(share.percentage))
                    partner_amount = total_revenue * (percentage / Decimal('100'))
                    partners_data.append({
                        'product_name': product.name,
                        'partner_name': share.partner_customer.name,
                        'percentage': share.percentage,
                        'avg_unit_price': avg_unit_price,
                        'total_qty': total_qty,
                        'total_revenue': total_revenue,
                        'partner_share_amount': partner_amount
                    })

                    p_id = share.partner_customer.id
                    partner_share_totals[p_id] = partner_share_totals.get(p_id, Decimal('0')) + partner_amount

    # Find products linked to a merchant
    merchant_products = Product.query.filter(
        Product.merchant_customer_id.isnot(None),
        Product.is_active == True
    ).all()
    
    merchants_data = []
    # Dictionary to aggregate shares per merchant: {merchant_id: total_share_amount}
    merchant_share_totals = {}
    
    for product in merchant_products:
        sales_query = SaleLine.query.join(Sale).filter(
            SaleLine.product_id == product.id,
            Sale.status == 'confirmed'
        )
        if scoped_branch_id is not None:
            sales_query = sales_query.filter(Sale.branch_id == scoped_branch_id)
        
        if date_from:
            sales_query = sales_query.filter(func.date(Sale.sale_date) >= date_from)
        if date_to:
            sales_query = sales_query.filter(func.date(Sale.sale_date) <= date_to)
            
        sales_lines = sales_query.all()
        
        total_revenue = sum(line.line_total for line in sales_lines)
        total_qty = sum(line.quantity for line in sales_lines)
        
        # Calculate average unit price
        avg_unit_price = total_revenue / total_qty if total_qty > 0 else 0
        
        if total_revenue > 0:
            merchant_percentage = float(product.merchant_share or 100)
            merchant_amount = total_revenue * (Decimal(merchant_percentage) / 100)
            
            merchants_data.append({
                'product_name': product.name,
                'merchant_name': product.merchant_customer.name,
                'percentage': merchant_percentage,
                'avg_unit_price': avg_unit_price,
                'total_qty': total_qty,
                'total_revenue': total_revenue,
                'merchant_share_amount': merchant_amount
            })
            
            # Aggregate for summary
            m_id = product.merchant_customer.id
            merchant_share_totals[m_id] = merchant_share_totals.get(m_id, Decimal('0')) + merchant_amount

    # --- 2. FINANCIAL SUMMARIES (Partners & Merchants) ---
    # Helper to get payments/receipts
    def get_financials(customer_type, share_totals_dict):
        customers = _scoped_customer_query().filter_by(customer_type=customer_type).all()
        summary_list = []
        
        for cust in customers:
            # Paid TO Customer (Outgoing Payments)
            paid_query = db.session.query(func.sum(Payment.amount_aed)).filter(
                Payment.customer_id == cust.id,
                Payment.direction == 'outgoing'
            )
            # Received FROM Customer (Receipts OR Incoming Payments)
            # 1. Receipts
            receipts_query = db.session.query(func.sum(Receipt.amount_aed)).filter(
                Receipt.customer_id == cust.id
            )
            # 2. Incoming Payments (Refunds/etc)
            payment_in_query = db.session.query(func.sum(Payment.amount_aed)).filter(
                Payment.customer_id == cust.id,
                Payment.direction == 'incoming'
            )
            
            if date_from:
                paid_query = paid_query.filter(func.date(Payment.payment_date) >= date_from)
                receipts_query = receipts_query.filter(func.date(Receipt.receipt_date) >= date_from)
                payment_in_query = payment_in_query.filter(func.date(Payment.payment_date) >= date_from)
            if date_to:
                paid_query = paid_query.filter(func.date(Payment.payment_date) <= date_to)
                receipts_query = receipts_query.filter(func.date(Receipt.receipt_date) <= date_to)
                payment_in_query = payment_in_query.filter(func.date(Payment.payment_date) <= date_to)
            if scoped_branch_id is not None:
                paid_query = paid_query.filter(Payment.branch_id == scoped_branch_id)
                receipts_query = receipts_query.filter(Receipt.branch_id == scoped_branch_id)
                payment_in_query = payment_in_query.filter(Payment.branch_id == scoped_branch_id)
            
            total_paid_to = paid_query.scalar() or Decimal('0')
            total_receipts = receipts_query.scalar() or Decimal('0')
            total_payment_in = payment_in_query.scalar() or Decimal('0')
            total_received_from = total_receipts + total_payment_in
            
            total_share = share_totals_dict.get(cust.id, Decimal('0'))
            
            # For Partner/Merchant:
            # Balance (Net) = (Total Share + Total Received From) - Total Paid To
            # Assuming 'Share' is money they earned (credit to them).
            # 'Received From' is money they gave us (credit to them, or debt repayment?).
            # Usually: Balance = (Earnings + Deposits) - Withdrawals
            net_balance = (total_share + total_received_from) - total_paid_to
            
            # Only add if there's any activity
            if total_share > 0 or total_paid_to > 0 or total_received_from > 0:
                summary_list.append({
                    'name': cust.name,
                    'total_share': total_share,
                    'paid_to': total_paid_to,
                    'received_from': total_received_from,
                    'net_balance': net_balance
                })
        return summary_list

    partners_summary = get_financials('partner', partner_share_totals)
    merchants_summary = get_financials('merchant', merchant_share_totals)
    
    # --- 3. SUPPLIERS SUMMARY ---
    suppliers = _scoped_supplier_query().all()
    suppliers_summary = []
    
    for sup in suppliers:
        # Total Purchases
        purchases_query = db.session.query(func.sum(Purchase.amount_aed)).filter(
            Purchase.supplier_id == sup.id,
            Purchase.status == 'confirmed'
        )
        # Paid TO Supplier (Outgoing)
        paid_query = db.session.query(func.sum(Payment.amount_aed)).filter(
            Payment.supplier_id == sup.id,
            Payment.direction == 'outgoing'
        )
        # Received FROM Supplier (Incoming - Refunds)
        received_query = db.session.query(func.sum(Payment.amount_aed)).filter(
            Payment.supplier_id == sup.id,
            Payment.direction == 'incoming'
        )
        
        if date_from:
            purchases_query = purchases_query.filter(func.date(Purchase.purchase_date) >= date_from)
            paid_query = paid_query.filter(func.date(Payment.payment_date) >= date_from)
            received_query = received_query.filter(func.date(Payment.payment_date) >= date_from)
        if date_to:
            purchases_query = purchases_query.filter(func.date(Purchase.purchase_date) <= date_to)
            paid_query = paid_query.filter(func.date(Payment.payment_date) <= date_to)
            received_query = received_query.filter(func.date(Payment.payment_date) <= date_to)
        if scoped_branch_id is not None:
            purchases_query = purchases_query.filter(Purchase.branch_id == scoped_branch_id)
            paid_query = paid_query.filter(Payment.branch_id == scoped_branch_id)
            received_query = received_query.filter(Payment.branch_id == scoped_branch_id)
            
        total_purchases = purchases_query.scalar() or Decimal('0')
        total_paid_to = paid_query.scalar() or Decimal('0')
        total_refunds = received_query.scalar() or Decimal('0')
        
        # Balance = Purchases - (Paid - Refunds)
        # Or: Purchases - Net Paid
        net_paid = total_paid_to - total_refunds
        balance_due = total_purchases - net_paid
        
        if total_purchases > 0 or total_paid_to > 0 or total_refunds > 0:
            suppliers_summary.append({
                'name': sup.name,
                'total_purchases': total_purchases,
                'paid_to': total_paid_to,
                'received_from': total_refunds,
                'balance_due': balance_due
            })

    return render_template('reports/partners.html', 
                         partners_data=partners_data,
                         merchants_data=merchants_data,
                         partners_summary=partners_summary,
                         merchants_summary=merchants_summary,
                         suppliers_summary=suppliers_summary)


@reports_bp.route('/sales')
@login_required
@permission_required('view_reports')
def sales():
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)
    customer_id = request.args.get('customer', type=int)
    seller_id = request.args.get('seller', type=int)
    
    query = tenant_query(Sale).filter_by(status='confirmed')
    scoped_branch_id = branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None:
        query = query.filter(Sale.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        query = query.filter(Sale.branch_id == scoped_branch_id)
    
    if date_from:
        query = query.filter(func.date(Sale.sale_date) >= date_from)
    
    if date_to:
        query = query.filter(func.date(Sale.sale_date) <= date_to)
    
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    
    if seller_id:
        query = query.filter_by(seller_id=seller_id)
    elif current_user.is_seller():
        query = query.filter_by(seller_id=current_user.id)
    
    sales_list = query.order_by(Sale.sale_date.desc()).all()
    
    total_sales = Decimal('0')
    total_paid = Decimal('0')
    total_due = Decimal('0')
    
    for sale in sales_list:
        total_sales += (sale.amount_aed or Decimal('0'))
        total_paid += (sale.paid_amount_aed or Decimal('0'))
        total_due += ((sale.amount_aed or Decimal('0')) - (sale.paid_amount_aed or Decimal('0')))
    
    total_profit = Decimal('0')
    if current_user.can_see_costs():
        for sale in sales_list:
            total_profit += (sale.get_profit() or Decimal('0'))
    
    summary = {
        'sales_count': len(sales_list),
        'total_sales_aed': float(total_sales),
        'total_paid_aed': float(total_paid),
        'total_pending_aed': float(total_due),
        'total_profit': float(total_profit) if current_user.can_see_costs() else None
    }

    customers_query = Customer.query
    if tenant_id is not None:
        customers_query = customers_query.filter(Customer.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        customer_ids = select(Sale.customer_id).where(Sale.branch_id == scoped_branch_id, Sale.customer_id.isnot(None))
        customers_query = customers_query.filter(Customer.id.in_(customer_ids))
    customers = customers_query.order_by(Customer.name).limit(500).all()

    if current_user.is_seller():
        sellers = [current_user]
    else:
        from models import User
        sellers_query = User.query.filter(User.is_active == True)
        if tenant_id is not None:
            sellers_query = sellers_query.filter(User.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            seller_ids = select(Sale.seller_id).where(Sale.branch_id == scoped_branch_id, Sale.seller_id.isnot(None))
            sellers_query = sellers_query.filter(User.id.in_(seller_ids))
        sellers = sellers_query.order_by(User.username).limit(500).all()
    
    return render_template('reports/sales.html',
                         sales=sales_list,
                         summary=summary,
                         date_from=date_from,
                         date_to=date_to,
                         customer_id=customer_id,
                         seller_id=seller_id,
                         customers=customers,
                         sellers=sellers)


@reports_bp.route('/sales/export')
@login_required
@permission_required('view_reports')
def sales_export():
    from flask import send_file
    from services.export_service import ExportService

    fmt = (request.args.get('format') or 'csv').strip().lower()
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)
    customer_id = request.args.get('customer', type=int)
    seller_id = request.args.get('seller', type=int)

    query = tenant_query(Sale).filter_by(status='confirmed')
    scoped_branch_id = branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None:
        query = query.filter(Sale.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        query = query.filter(Sale.branch_id == scoped_branch_id)
    if date_from:
        query = query.filter(func.date(Sale.sale_date) >= date_from)
    if date_to:
        query = query.filter(func.date(Sale.sale_date) <= date_to)
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    if seller_id:
        query = query.filter_by(seller_id=seller_id)
    elif current_user.is_seller():
        query = query.filter_by(seller_id=current_user.id)

    sales_list = query.order_by(Sale.sale_date.desc()).all()

    headers = [
        'رقم الفاتورة',
        'تاريخ الفاتورة',
        'الزبون',
        'البائع',
        'الفرع',
        'المستودع',
        'العملة',
        'سعر الصرف',
        'إجمالي (AED)',
        'مدفوع (AED)',
        'المتبقي (AED)',
        'حالة الدفع',
    ]

    data = []
    for s in sales_list:
        total_aed = Decimal(str(s.amount_aed or 0))
        paid_aed = Decimal(str(s.paid_amount_aed or 0))
        due_aed = total_aed - paid_aed
        data.append([
            s.sale_number,
            s.sale_date.strftime('%Y-%m-%d') if s.sale_date else '',
            s.customer.name if s.customer else '',
            s.seller.get_display_name() if s.seller else '',
            (s.branch.name if s.branch else ''),
            (s.warehouse.name_ar or s.warehouse.name) if getattr(s, 'warehouse', None) else '',
            s.currency or '',
            float(s.exchange_rate or 1),
            float(total_aed),
            float(paid_aed),
            float(due_aed),
            s.payment_status or '',
        ])

    base_name = f"sales_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == 'xlsx':
        output = ExportService.export_to_xlsx(data, headers, filename=f'{base_name}.xlsx', sheet_name='Sales')
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


@reports_bp.route('/purchases')
@login_required
@permission_required('view_reports')
def purchases():
    if current_user.is_seller():
        return render_template('errors/403.html'), 403
    
    date_from = request.args.get('start_date', '', type=str)
    date_to = request.args.get('end_date', '', type=str)
    supplier_id = request.args.get('supplier_id', type=int)
    
    query = tenant_query(Purchase).filter_by(status='confirmed')
    scoped_branch_id = branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None:
        query = query.filter(Purchase.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        query = query.filter(Purchase.branch_id == scoped_branch_id)
    
    if date_from:
        query = query.filter(func.date(Purchase.purchase_date) >= date_from)
    
    if date_to:
        query = query.filter(func.date(Purchase.purchase_date) <= date_to)

    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)
    
    purchases_list = query.order_by(Purchase.purchase_date.desc()).all()
    
    total_amount = Decimal('0')
    
    # Calculate total purchases amount
    for p in purchases_list:
        amount = p.amount_aed or Decimal('0')
        total_amount += amount
        # Add dummy attributes for template compatibility if not present
        if not hasattr(p, 'paid_amount'):
            p.paid_amount = Decimal('0')
        if not hasattr(p, 'balance_due'):
            p.balance_due = amount

    # Calculate total paid from Payments table
    from models import Payment
    payment_query = Payment.query.filter(
        Payment.direction == 'outgoing',
        Payment.supplier_id != None
    )
    if scoped_branch_id is not None:
        payment_query = payment_query.filter(Payment.branch_id == scoped_branch_id)
    
    if date_from:
        payment_query = payment_query.filter(func.date(Payment.payment_date) >= date_from)
    if date_to:
        payment_query = payment_query.filter(func.date(Payment.payment_date) <= date_to)
    if supplier_id:
        payment_query = payment_query.filter_by(supplier_id=supplier_id)
        
    payments_list = payment_query.all()
    total_paid = sum((p.amount_aed or Decimal('0') for p in payments_list), Decimal('0'))
    
    # Total due is rough estimate: Purchases - Payments
    # Note: This doesn't account for opening balance
    total_due = total_amount - total_paid
     
    stats = {
        'total_purchases': len(purchases_list),
        'total_amount': float(total_amount),
        'total_paid': float(total_paid),
        'total_due': float(total_due)
    }
    
    # Get suppliers for filter within the active branch scope only
    from models import Supplier
    suppliers = _scoped_supplier_query().filter(Supplier.is_active == True).order_by(Supplier.name).all()
    
    return render_template('reports/purchases.html',
                         purchases=purchases_list,
                         stats=stats,
                         suppliers=suppliers,
                         start_date=date_from,
                         end_date=date_to,
                         supplier_id=supplier_id)


@reports_bp.route('/purchases/export')
@login_required
@permission_required('view_reports')
def purchases_export():
    from flask import send_file
    from services.export_service import ExportService

    if current_user.is_seller():
        return render_template('errors/403.html'), 403

    fmt = (request.args.get('format') or 'csv').strip().lower()
    date_from = request.args.get('start_date', '', type=str)
    date_to = request.args.get('end_date', '', type=str)
    supplier_id = request.args.get('supplier_id', type=int)

    query = tenant_query(Purchase).filter_by(status='confirmed')
    scoped_branch_id = branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None:
        query = query.filter(Purchase.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        query = query.filter(Purchase.branch_id == scoped_branch_id)
    if date_from:
        query = query.filter(func.date(Purchase.purchase_date) >= date_from)
    if date_to:
        query = query.filter(func.date(Purchase.purchase_date) <= date_to)
    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)

    purchases_list = query.order_by(Purchase.purchase_date.desc()).all()

    headers = [
        'رقم الفاتورة',
        'تاريخ الفاتورة',
        'المورد',
        'الفرع',
        'المستودع',
        'العملة',
        'سعر الصرف',
        'الإجمالي (AED)',
        'الإجمالي (عملة الفاتورة)',
        'الحالة',
    ]

    data = []
    for p in purchases_list:
        data.append([
            p.purchase_number,
            p.purchase_date.strftime('%Y-%m-%d') if p.purchase_date else '',
            p.supplier.name if p.supplier else '',
            (p.branch.name if p.branch else ''),
            (p.warehouse.name_ar or p.warehouse.name) if getattr(p, 'warehouse', None) else '',
            p.currency or '',
            float(p.exchange_rate or 1),
            float(Decimal(str(p.amount_aed or 0))),
            float(Decimal(str(p.total_amount or 0))),
            p.status or '',
        ])

    base_name = f"purchases_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == 'xlsx':
        output = ExportService.export_to_xlsx(data, headers, filename=f'{base_name}.xlsx', sheet_name='Purchases')
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


@reports_bp.route('/receivables')
@login_required
@permission_required('view_reports')
def receivables():
    now = datetime.now(timezone.utc)
    
    all_sales = tenant_query(Sale).filter(
        Sale.status == 'confirmed'
    )
    scoped_branch_id = branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None:
        all_sales = all_sales.filter(Sale.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        all_sales = all_sales.filter(Sale.branch_id == scoped_branch_id)

    customer_id = request.args.get('customer', type=int)
    if customer_id:
        all_sales = all_sales.filter(Sale.customer_id == customer_id)
    all_sales = all_sales.all()
    
    all_sales = [sale for sale in all_sales if (sale.amount_aed or Decimal('0')) > (sale.paid_amount_aed or Decimal('0'))]
    
    aging_data = {
        'current': {'sales': [], 'total': Decimal('0')},
        'days_30': {'sales': [], 'total': Decimal('0')},
        'days_60': {'sales': [], 'total': Decimal('0')},
        'days_90': {'sales': [], 'total': Decimal('0')},
        'over_90': {'sales': [], 'total': Decimal('0')},
    }
    
    for sale in all_sales:
        sale_date = sale.sale_date
        if sale_date.tzinfo is None:
            sale_date = sale_date.replace(tzinfo=timezone.utc)
        days_old = (now - sale_date).days
        balance = (sale.amount_aed or Decimal('0')) - (sale.paid_amount_aed or Decimal('0'))
        
        sale.days_old = days_old
        sale.calculated_balance = balance
        
        if days_old <= 30:
            aging_data['current']['sales'].append(sale)
            aging_data['current']['total'] += balance
        elif days_old <= 60:
            aging_data['days_30']['sales'].append(sale)
            aging_data['days_30']['total'] += balance
        elif days_old <= 90:
            aging_data['days_60']['sales'].append(sale)
            aging_data['days_60']['total'] += balance
        elif days_old <= 120:
            aging_data['days_90']['sales'].append(sale)
            aging_data['days_90']['total'] += balance
        else:
            aging_data['over_90']['sales'].append(sale)
            aging_data['over_90']['total'] += balance
    
    total_receivables = sum(data['total'] for data in aging_data.values())
    
    summary = {
        'total_receivables': float(total_receivables),
        'current': float(aging_data['current']['total']),
        'days_30': float(aging_data['days_30']['total']),
        'days_60': float(aging_data['days_60']['total']),
        'days_90': float(aging_data['days_90']['total']),
        'over_90': float(aging_data['over_90']['total']),
    }

    customers_query = Customer.query
    if tenant_id is not None:
        customers_query = customers_query.filter(Customer.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        customer_ids = select(Sale.customer_id).where(Sale.branch_id == scoped_branch_id, Sale.customer_id.isnot(None))
        customers_query = customers_query.filter(Customer.id.in_(customer_ids))
    customers = customers_query.order_by(Customer.name).limit(500).all()
    
    return render_template('reports/receivables.html',
                         aging_data=aging_data,
                         summary=summary,
                         customers=customers,
                         customer_id=customer_id)


@reports_bp.route('/receivables/export')
@login_required
@permission_required('view_reports')
def receivables_export():
    from flask import send_file
    from services.export_service import ExportService

    fmt = (request.args.get('format') or 'csv').strip().lower()
    customer_id = request.args.get('customer', type=int)

    now = datetime.now(timezone.utc)
    all_sales = tenant_query(Sale).filter(Sale.status == 'confirmed')
    scoped_branch_id = branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None:
        all_sales = all_sales.filter(Sale.tenant_id == tenant_id)
    if scoped_branch_id is not None:
        all_sales = all_sales.filter(Sale.branch_id == scoped_branch_id)
    if customer_id:
        all_sales = all_sales.filter(Sale.customer_id == customer_id)
    all_sales = all_sales.all()

    all_sales = [sale for sale in all_sales if (sale.amount_aed or Decimal('0')) > (sale.paid_amount_aed or Decimal('0'))]

    def bucket_for(days_old: int) -> str:
        if days_old <= 30:
            return 'حالي (0-30)'
        if days_old <= 60:
            return '31-60'
        if days_old <= 90:
            return '61-90'
        if days_old <= 120:
            return '91-120'
        return '+120'

    headers = [
        'الفئة',
        'رقم الفاتورة',
        'تاريخ الفاتورة',
        'العمر (يوم)',
        'الزبون',
        'الفرع',
        'العملة',
        'سعر الصرف',
        'الرصيد المستحق (AED)',
    ]

    data = []
    for sale in all_sales:
        sale_date = sale.sale_date
        if sale_date and sale_date.tzinfo is None:
            sale_date = sale_date.replace(tzinfo=timezone.utc)
        days_old = (now - sale_date).days if sale_date else 0
        balance = (sale.amount_aed or Decimal('0')) - (sale.paid_amount_aed or Decimal('0'))
        data.append([
            bucket_for(days_old),
            sale.sale_number,
            sale.sale_date.strftime('%Y-%m-%d') if sale.sale_date else '',
            days_old,
            sale.customer.name if sale.customer else '',
            (sale.branch.name if sale.branch else ''),
            sale.currency or '',
            float(sale.exchange_rate or 1),
            float(Decimal(str(balance or 0))),
        ])

    base_name = f"receivables_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == 'xlsx':
        output = ExportService.export_to_xlsx(data, headers, filename=f'{base_name}.xlsx', sheet_name='Receivables')
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


@reports_bp.route('/inventory')
@login_required
@permission_required('view_reports')
def inventory():
    from models import StockMovement, Warehouse
    from utils.decorators import branch_scope_id
    from utils.branching import (
        user_can_access_branch,
        get_accessible_branches,
        get_accessible_warehouse_ids,
    )

    category_id = request.args.get('category', type=int)
    include_zero = (request.args.get('include_zero') or '').strip() in ('1', 'true', 'yes', 'on')
    warehouse_id = request.args.get('warehouse_id', type=int)
    in_date_from = (request.args.get('in_date_from') or '').strip()
    in_date_to = (request.args.get('in_date_to') or '').strip()
    out_date_from = (request.args.get('out_date_from') or '').strip()
    out_date_to = (request.args.get('out_date_to') or '').strip()

    branch_id = request.args.get('branch_id', type=int)
    scoped_branch_id = branch_scope_id()
    if branch_id is None:
        branch_id = scoped_branch_id
    elif scoped_branch_id is not None and branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    elif scoped_branch_id is None and branch_id is not None and not user_can_access_branch(branch_id, current_user):
        return render_template('errors/403.html'), 403

    tenant_id = get_active_tenant_id(current_user)

    warehouses_query = tenant_query(Warehouse).filter_by(is_active=True)
    if tenant_id is not None:
        warehouses_query = warehouses_query.filter(Warehouse.tenant_id == tenant_id)
    if branch_id is not None:
        warehouses_query = warehouses_query.filter(Warehouse.branch_id == branch_id)
    else:
        accessible_ids = get_accessible_warehouse_ids(current_user)
        if accessible_ids:
            warehouses_query = warehouses_query.filter(Warehouse.id.in_(accessible_ids))
        elif not current_user.is_admin():
            warehouses_query = warehouses_query.filter(Warehouse.id < 0)
    warehouses = warehouses_query.order_by(Warehouse.is_main.desc(), Warehouse.name).all()

    selected_warehouse = None
    if warehouse_id is not None:
        selected_warehouse = next((w for w in warehouses if w.id == warehouse_id), None)
        if not selected_warehouse and not current_user.is_admin():
            return render_template('errors/403.html'), 403
        if not selected_warehouse:
            selected_warehouse = Warehouse.query.filter_by(id=warehouse_id, is_active=True).first()
            if not selected_warehouse:
                return render_template('errors/404.html'), 404
            if tenant_id is not None and selected_warehouse.tenant_id != tenant_id:
                return render_template('errors/403.html'), 403
            if branch_id is not None and selected_warehouse.branch_id != branch_id:
                return render_template('errors/403.html'), 403
            warehouses.append(selected_warehouse)

    if selected_warehouse:
        warehouse_ids = [selected_warehouse.id]
    elif warehouses:
        warehouse_ids = [w.id for w in warehouses]
    else:
        warehouse_ids = [-1]

    stock_query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(StockMovement.quantity), 0).label('qty')
    ).filter(StockMovement.warehouse_id.in_(warehouse_ids))
    if tenant_id is not None:
        stock_query = stock_query.filter(StockMovement.tenant_id == tenant_id)
    stock_map = dict(stock_query.group_by(StockMovement.product_id).all())

    in_query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(StockMovement.quantity), 0).label('qty')
    ).filter(
        StockMovement.warehouse_id.in_(warehouse_ids),
        StockMovement.quantity > 0
    )
    if tenant_id is not None:
        in_query = in_query.filter(StockMovement.tenant_id == tenant_id)
    if in_date_from:
        in_query = in_query.filter(func.date(StockMovement.created_at) >= in_date_from)
    if in_date_to:
        in_query = in_query.filter(func.date(StockMovement.created_at) <= in_date_to)
    in_map = dict(in_query.group_by(StockMovement.product_id).all())

    out_query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(-StockMovement.quantity), 0).label('qty')
    ).filter(
        StockMovement.warehouse_id.in_(warehouse_ids),
        StockMovement.quantity < 0
    )
    if tenant_id is not None:
        out_query = out_query.filter(StockMovement.tenant_id == tenant_id)
    if out_date_from:
        out_query = out_query.filter(func.date(StockMovement.created_at) >= out_date_from)
    if out_date_to:
        out_query = out_query.filter(func.date(StockMovement.created_at) <= out_date_to)
    out_map = dict(out_query.group_by(StockMovement.product_id).all())

    sold_query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(-StockMovement.quantity), 0).label('qty')
    ).filter(
        StockMovement.warehouse_id.in_(warehouse_ids),
        StockMovement.movement_type == 'sale',
        StockMovement.quantity < 0
    )
    if tenant_id is not None:
        sold_query = sold_query.filter(StockMovement.tenant_id == tenant_id)
    if out_date_from:
        sold_query = sold_query.filter(func.date(StockMovement.created_at) >= out_date_from)
    if out_date_to:
        sold_query = sold_query.filter(func.date(StockMovement.created_at) <= out_date_to)
    sold_map = dict(sold_query.group_by(StockMovement.product_id).all())

    query = tenant_query(Product).filter_by(is_active=True)
    if category_id:
        query = query.filter_by(category_id=category_id)

    if not include_zero:
        product_ids = [pid for pid, qty in stock_map.items() if (qty or 0) != 0]
        if product_ids:
            query = query.filter(Product.id.in_(product_ids))
        else:
            query = query.filter(Product.id < 0)

    products = query.order_by(Product.name).all()

    total_value = Decimal('0')
    total_items = Decimal('0')
    for p in products:
        qty = Decimal(str(stock_map.get(p.id) or 0))
        total_items += qty
        if current_user.can_see_costs():
            total_value += qty * (p.cost_price or Decimal('0'))

    summary = {
        'products_count': len(products),
        'total_items': float(total_items),
        'total_value': float(total_value) if current_user.can_see_costs() else None
    }
    branches = get_accessible_branches(current_user)
    stats = None
    if products:
        def qty_for(p):
            return Decimal(str(stock_map.get(p.id) or 0))
        in_stock = sum(1 for p in products if qty_for(p) > 0)
        low = sum(1 for p in products if 0 < qty_for(p) <= (p.min_stock_alert or 0))
        out = sum(1 for p in products if qty_for(p) <= 0)
        stats = {'total_products': len(products), 'in_stock': in_stock, 'low_stock': low, 'out_of_stock': out}

    return render_template(
        'reports/inventory.html',
        products=products,
        summary=summary,
        branches=branches,
        selected_branch_id=branch_id,
        warehouses=warehouses,
        selected_warehouse_id=warehouse_id,
        stock_map=stock_map,
        in_map=in_map,
        out_map=out_map,
        sold_map=sold_map,
        stats=stats,
        category_id=category_id,
        include_zero=include_zero,
        in_date_from=in_date_from,
        in_date_to=in_date_to,
        out_date_from=out_date_from,
        out_date_to=out_date_to,
    )


@reports_bp.route('/inventory/export')
@login_required
@permission_required('view_reports')
def inventory_export():
    from flask import send_file
    from models import StockMovement, Warehouse
    from utils.decorators import branch_scope_id
    from utils.branching import (
        user_can_access_branch,
        get_accessible_warehouse_ids,
    )
    from services.export_service import ExportService

    fmt = (request.args.get('format') or 'csv').strip().lower()
    category_id = request.args.get('category', type=int)
    include_zero = (request.args.get('include_zero') or '').strip() in ('1', 'true', 'yes', 'on')
    warehouse_id = request.args.get('warehouse_id', type=int)
    in_date_from = (request.args.get('in_date_from') or '').strip()
    in_date_to = (request.args.get('in_date_to') or '').strip()
    out_date_from = (request.args.get('out_date_from') or '').strip()
    out_date_to = (request.args.get('out_date_to') or '').strip()

    branch_id = request.args.get('branch_id', type=int)
    scoped_branch_id = branch_scope_id()
    if branch_id is None:
        branch_id = scoped_branch_id
    elif scoped_branch_id is not None and branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    elif scoped_branch_id is None and branch_id is not None and not user_can_access_branch(branch_id, current_user):
        return render_template('errors/403.html'), 403

    tenant_id = get_active_tenant_id(current_user)

    warehouses_query = tenant_query(Warehouse).filter_by(is_active=True)
    if tenant_id is not None:
        warehouses_query = warehouses_query.filter(Warehouse.tenant_id == tenant_id)
    if branch_id is not None:
        warehouses_query = warehouses_query.filter(Warehouse.branch_id == branch_id)
    else:
        accessible_ids = get_accessible_warehouse_ids(current_user)
        if accessible_ids:
            warehouses_query = warehouses_query.filter(Warehouse.id.in_(accessible_ids))
        elif not current_user.is_admin():
            warehouses_query = warehouses_query.filter(Warehouse.id < 0)
    warehouses = warehouses_query.all()

    selected_warehouse = None
    if warehouse_id is not None:
        selected_warehouse = next((w for w in warehouses if w.id == warehouse_id), None)
        if not selected_warehouse and not current_user.is_admin():
            return render_template('errors/403.html'), 403
        if not selected_warehouse:
            selected_warehouse = Warehouse.query.filter_by(id=warehouse_id, is_active=True).first()
            if not selected_warehouse:
                return render_template('errors/404.html'), 404
            if tenant_id is not None and selected_warehouse.tenant_id != tenant_id:
                return render_template('errors/403.html'), 403
            if branch_id is not None and selected_warehouse.branch_id != branch_id:
                return render_template('errors/403.html'), 403
            warehouses = [selected_warehouse]

    if selected_warehouse:
        warehouse_ids = [selected_warehouse.id]
        warehouse_label = selected_warehouse.name_ar or selected_warehouse.name
    elif warehouses:
        warehouse_ids = [w.id for w in warehouses]
        warehouse_label = 'متعدد'
    else:
        warehouse_ids = [-1]
        warehouse_label = ''

    stock_query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(StockMovement.quantity), 0).label('qty')
    ).filter(StockMovement.warehouse_id.in_(warehouse_ids))
    if tenant_id is not None:
        stock_query = stock_query.filter(StockMovement.tenant_id == tenant_id)
    stock_map = dict(stock_query.group_by(StockMovement.product_id).all())

    in_query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(StockMovement.quantity), 0).label('qty')
    ).filter(
        StockMovement.warehouse_id.in_(warehouse_ids),
        StockMovement.quantity > 0
    )
    if tenant_id is not None:
        in_query = in_query.filter(StockMovement.tenant_id == tenant_id)
    if in_date_from:
        in_query = in_query.filter(func.date(StockMovement.created_at) >= in_date_from)
    if in_date_to:
        in_query = in_query.filter(func.date(StockMovement.created_at) <= in_date_to)
    in_map = dict(in_query.group_by(StockMovement.product_id).all())

    out_query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(-StockMovement.quantity), 0).label('qty')
    ).filter(
        StockMovement.warehouse_id.in_(warehouse_ids),
        StockMovement.quantity < 0
    )
    if tenant_id is not None:
        out_query = out_query.filter(StockMovement.tenant_id == tenant_id)
    if out_date_from:
        out_query = out_query.filter(func.date(StockMovement.created_at) >= out_date_from)
    if out_date_to:
        out_query = out_query.filter(func.date(StockMovement.created_at) <= out_date_to)
    out_map = dict(out_query.group_by(StockMovement.product_id).all())

    sold_query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(-StockMovement.quantity), 0).label('qty')
    ).filter(
        StockMovement.warehouse_id.in_(warehouse_ids),
        StockMovement.movement_type == 'sale',
        StockMovement.quantity < 0
    )
    if tenant_id is not None:
        sold_query = sold_query.filter(StockMovement.tenant_id == tenant_id)
    if out_date_from:
        sold_query = sold_query.filter(func.date(StockMovement.created_at) >= out_date_from)
    if out_date_to:
        sold_query = sold_query.filter(func.date(StockMovement.created_at) <= out_date_to)
    sold_map = dict(sold_query.group_by(StockMovement.product_id).all())

    query = tenant_query(Product).filter_by(is_active=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if not include_zero:
        product_ids = [pid for pid, qty in stock_map.items() if (qty or 0) != 0]
        if product_ids:
            query = query.filter(Product.id.in_(product_ids))
        else:
            query = query.filter(Product.id < 0)
    products = query.order_by(Product.name).all()

    headers = [
        'المنتج',
        'SKU',
        'Barcode',
        'المستودع',
        'الكمية المتاحة',
        'إدخال (حسب التاريخ)',
        'إخراج (حسب التاريخ)',
        'مباع (حسب التاريخ)',
        'سعر التكلفة',
        'سعر البيع',
        'قيمة المخزون (تكلفة)',
    ]

    data = []
    for p in products:
        qty = Decimal(str(stock_map.get(p.id) or 0))
        in_qty = Decimal(str(in_map.get(p.id) or 0))
        out_qty = Decimal(str(out_map.get(p.id) or 0))
        sold_qty = Decimal(str(sold_map.get(p.id) or 0))
        cost = p.cost_price or Decimal('0')
        total_cost_value = qty * cost if current_user.can_see_costs() else None
        data.append([
            p.name,
            p.sku or '',
            getattr(p, 'barcode', '') or '',
            warehouse_label,
            float(qty),
            float(in_qty),
            float(out_qty),
            float(sold_qty),
            float(cost) if current_user.can_see_costs() else '',
            float(p.regular_price or 0),
            float(total_cost_value) if current_user.can_see_costs() else '',
        ])

    base_name = f"inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == 'xlsx':
        output = ExportService.export_to_xlsx(data, headers, filename=f'{base_name}.xlsx', sheet_name='Inventory')
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


@reports_bp.route('/api/model_fields')
@login_required
@permission_required('view_reports')
def api_model_fields():
    """Return column names and date fields for a given model/table (for dynamic report builder)."""
    model = (request.args.get('model') or '').strip()
    if not model:
        return jsonify(columns=[], date_fields=[], all_fields=[])
    model_lower = model.lower()
    columns = []
    date_fields = []
    if model_lower in ('sale', 'sales'):
        columns = ['id', 'sale_number', 'sale_date', 'customer_id', 'total', 'status', 'branch_id', 'created_at']
        date_fields = ['sale_date', 'created_at']
    elif model_lower in ('purchase', 'purchases'):
        columns = ['id', 'purchase_number', 'purchase_date', 'supplier_id', 'total', 'status', 'branch_id', 'created_at']
        date_fields = ['purchase_date', 'created_at']
    elif model_lower in ('customer', 'customers'):
        columns = ['id', 'name', 'phone', 'email', 'customer_type', 'balance', 'created_at']
        date_fields = ['created_at']
    elif model_lower in ('product', 'products'):
        columns = ['id', 'name', 'sku', 'barcode', 'regular_price', 'cost_price', 'current_stock', 'created_at']
        date_fields = ['created_at']
    elif model_lower in ('expense', 'expenses'):
        columns = ['id', 'expense_date', 'amount', 'category_id', 'description', 'branch_id', 'created_at']
        date_fields = ['expense_date', 'created_at']
    else:
        date_fields = ['created_at', 'date', 'updated_at']
    all_fields = list(columns) if columns else []
    return jsonify(columns=columns, date_fields=date_fields, all_fields=all_fields)


@reports_bp.route('/api/entity-search')
@login_required
@permission_required('view_reports')
def api_entity_search():
    from models import Supplier
    query = request.args.get('q', '').strip()
    entity_type = request.args.get('type', 'supplier')
    
    results = []
    
    if entity_type == 'supplier':
        suppliers = _scoped_supplier_query().filter(
            db.or_(
                Supplier.name.ilike(f'%{query}%'),
                Supplier.phone.ilike(f'%{query}%')
            )
        ).limit(10).all()
        for s in suppliers:
            results.append({
                'id': s.id,
                'name': s.name,
                'phone': s.phone,
                'type': 'supplier'
            })
            
    else: # customer, partner, merchant
        q_filter = _scoped_customer_query().filter(
            db.or_(
                Customer.name.ilike(f'%{query}%'),
                Customer.phone.ilike(f'%{query}%')
            )
        )
        
        if entity_type == 'partner':
            q_filter = q_filter.filter_by(customer_type='partner')
        elif entity_type == 'merchant':
            q_filter = q_filter.filter_by(customer_type='merchant')
        # If 'customer', we search all or just regular? Let's search all if type is generic, or filter if specific.
        # User dropdown will likely send specific types.
        
        customers = q_filter.limit(10).all()
        for c in customers:
            results.append({
                'id': c.id,
                'name': c.name,
                'phone': c.phone,
                'type': c.customer_type
            })
            
    return jsonify(results)


@reports_bp.route('/entity_report_fragment/<type>/<id>')
@login_required
@permission_required('view_reports')
def entity_report_fragment(type, id):
    try:
        from models import Receipt, Payment, PurchaseLine, Supplier
        scoped_branch_id = branch_scope_id()


        
        context = {
            'entity': None,
            'type_label': '',
            'balance': 0,
            'balance_label': '',
            'products': [],
            'invoices': [],
            'transactions': []
        }
        
        if type == 'supplier':
            entity = Supplier.query.get_or_404(id)
            if branch_scope_id() is not None and not db.session.query(_scoped_supplier_query().filter_by(id=id).exists()).scalar():
                return render_template('errors/403.html'), 403
            context['entity'] = entity
            context['type_label'] = 'مورد'

            # Products (Purchased)
            p_lines = db.session.query(
                Product.name,
                func.sum(PurchaseLine.quantity).label('qty'),
                func.sum(PurchaseLine.line_total).label('total'),
                func.max(Purchase.purchase_date).label('last_date')
            ).join(Purchase).join(Product).filter(
                Purchase.supplier_id == id,
                Purchase.status == 'confirmed'
            )
            if scoped_branch_id is not None:
                p_lines = p_lines.filter(Purchase.branch_id == scoped_branch_id)
            p_lines = p_lines.group_by(Product.name).all()
            
            context['products'] = [{
                'name': p.name,
                'quantity': p.qty,
                'total': p.total,
                'last_date': p.last_date.strftime('%Y-%m-%d') if p.last_date else '-'
            } for p in p_lines]
            
            # Invoices (Purchases)
            purchases = Purchase.query.filter_by(supplier_id=id)
            if scoped_branch_id is not None:
                purchases = purchases.filter(Purchase.branch_id == scoped_branch_id)
            purchases = purchases.order_by(Purchase.purchase_date.desc()).all()

            fifo_purchases = sorted(
                purchases,
                key=lambda p: (p.purchase_date or datetime.min, p.id or 0)
            )
            supplier_payments_q = Payment.query.filter(
                Payment.supplier_id == id,
                Payment.direction == 'outgoing',
                Payment.payment_confirmed == True
            )
            if scoped_branch_id is not None:
                supplier_payments_q = supplier_payments_q.filter(Payment.branch_id == scoped_branch_id)
            total_paid_fifo = Decimal(str(
                supplier_payments_q.with_entities(func.sum(Payment.amount_aed)).scalar() or 0
            ))
            remaining_paid = total_paid_fifo
            paid_map = {}
            for p in fifo_purchases:
                amount = Decimal(str(p.amount_aed or 0))
                allocated = min(amount, remaining_paid) if remaining_paid > 0 else Decimal('0')
                paid_map[p.id] = allocated
                remaining_paid = max(Decimal('0'), remaining_paid - allocated)

            context['invoices'] = [{
                'number': p.purchase_number,
                'date': p.purchase_date.strftime('%Y-%m-%d'),
                'status': p.status,
                'amount': p.amount_aed or 0,
                'paid': paid_map.get(p.id, Decimal('0')),
                'balance': (Decimal(str(p.amount_aed or 0)) - paid_map.get(p.id, Decimal('0')))
            } for p in purchases]
            
            # Transactions (Payments TO Supplier)
            payments = Payment.query.filter_by(supplier_id=id)
            if scoped_branch_id is not None:
                payments = payments.filter(Payment.branch_id == scoped_branch_id)
            payments = payments.order_by(Payment.payment_date.desc()).all()
            total_purchases_amount = sum((p.amount_aed or 0) for p in purchases)
            total_payments_amount = sum(
                (p.amount_aed or 0)
                for p in payments
                if p.direction == 'outgoing' and getattr(p, 'payment_confirmed', True)
            )

            # Balance
            context['balance'] = total_purchases_amount - total_payments_amount
            context['balance_label'] = 'مستحق للمورد'
            context['transactions'] = [{
                'number': p.payment_number,
                'type': 'out', # Payment out
                'date': p.payment_date.strftime('%Y-%m-%d'),
                'amount': p.amount_aed,
                'method': p.payment_method,
                'notes': p.notes or '-'
            } for p in payments]
            
        else: # Customer/Partner/Merchant
            entity = Customer.query.get_or_404(id)
            if branch_scope_id() is not None and not db.session.query(_scoped_customer_query().filter_by(id=id).exists()).scalar():
                return render_template('errors/403.html'), 403
            context['entity'] = entity
            context['type_label'] = {
                'partner': 'شريك',
                'merchant': 'تاجر',
                'regular': 'زبون',
                'vip': 'VIP'
            }.get(entity.customer_type, 'زبون')
            
            # Balance calculation (Receivables/Payables)
            # Sales (He took goods) + Payments Out (He took money) - Receipts (He gave money)
            total_sales_query = db.session.query(func.sum(Sale.amount_aed)).filter(Sale.customer_id==id, Sale.status=='confirmed')
            total_receipts_query = db.session.query(func.sum(Receipt.amount_aed)).filter(
                Receipt.customer_id==id,
                Receipt.payment_confirmed == True
            )
            # Payments made TO customer (e.g. returns/share/drawings)
            total_payments_query = db.session.query(func.sum(Payment.amount_aed)).filter(Payment.customer_id==id, Payment.direction=='outgoing')
            if scoped_branch_id is not None:
                total_sales_query = total_sales_query.filter(Sale.branch_id == scoped_branch_id)
                total_receipts_query = total_receipts_query.filter(Receipt.branch_id == scoped_branch_id)
                total_payments_query = total_payments_query.filter(Payment.branch_id == scoped_branch_id)
            total_sales = total_sales_query.scalar() or 0
            total_receipts = total_receipts_query.scalar() or 0
            total_payments_to = total_payments_query.scalar() or 0
            
            context['balance'] = (total_sales + total_payments_to) - total_receipts # Positive means they owe us
            context['balance_label'] = 'مستحق لنا'
            if context['balance'] < 0:
                context['balance'] = abs(context['balance'])
                context['balance_label'] = 'مستحق للعميل'

            # Products (Sold) - Products the customer BOUGHT
            s_lines = db.session.query(
                Product.name,
                func.sum(SaleLine.quantity).label('qty'),
                func.sum(SaleLine.line_total).label('total'),
                func.max(Sale.sale_date).label('last_date')
            ).join(Sale).join(Product).filter(
                Sale.customer_id == id,
                Sale.status == 'confirmed'
            )
            if scoped_branch_id is not None:
                s_lines = s_lines.filter(Sale.branch_id == scoped_branch_id)
            s_lines = s_lines.group_by(Product.name).all()
            
            context['products'] = [{
                'name': p.name,
                'quantity': p.qty,
                'total': p.total,
                'last_date': p.last_date.strftime('%Y-%m-%d') if p.last_date else '-'
            } for p in s_lines]

            # IF PARTNER: Fetch products they have a share in (Products they EARN from)
            if entity.customer_type == 'partner':
                shared_products_query = db.session.query(
                    Product.name,
                    ProductPartner.percentage,
                    func.sum(SaleLine.quantity).label('qty'),
                    func.sum(SaleLine.line_total).label('total_sales'),
                    func.max(Sale.sale_date).label('last_date')
                ).join(ProductPartner, Product.id == ProductPartner.product_id)\
                 .join(SaleLine, SaleLine.product_id == Product.id)\
                 .join(Sale, Sale.id == SaleLine.sale_id)\
                 .filter(
                     ProductPartner.partner_customer_id == id,
                     Sale.status == 'confirmed'
                 )
                if scoped_branch_id is not None:
                    shared_products_query = shared_products_query.filter(Sale.branch_id == scoped_branch_id)
                shared_products_query = shared_products_query.group_by(Product.name, ProductPartner.percentage).all()
                
                for sp in shared_products_query:
                    share_amount = sp.total_sales * (sp.percentage / 100)
                    context['products'].append({
                        'name': f"{sp.name} (Share: {sp.percentage}%)",
                        'quantity': sp.qty,
                        'total': share_amount,
                        'last_date': sp.last_date.strftime('%Y-%m-%d') if sp.last_date else '-'
                    })
                    
            # IF MERCHANT: Fetch products they own (Products they EARN from)
            if entity.customer_type == 'merchant':
                merchant_products_query = db.session.query(
                    Product.name,
                    Product.merchant_share,
                    func.sum(SaleLine.quantity).label('qty'),
                    func.sum(SaleLine.line_total).label('total_sales'),
                    func.max(Sale.sale_date).label('last_date')
                ).join(SaleLine, SaleLine.product_id == Product.id)\
                 .join(Sale, Sale.id == SaleLine.sale_id)\
                 .filter(
                     Product.merchant_customer_id == id,
                     Sale.status == 'confirmed'
                 )
                if scoped_branch_id is not None:
                    merchant_products_query = merchant_products_query.filter(Sale.branch_id == scoped_branch_id)
                merchant_products_query = merchant_products_query.group_by(Product.name, Product.merchant_share).all()
                 
                for mp in merchant_products_query:
                    share_pct = mp.merchant_share or 100
                    share_amount = mp.total_sales * (share_pct / 100)
                    context['products'].append({
                        'name': f"{mp.name} (Merchant: {share_pct}%)",
                        'quantity': mp.qty,
                        'total': share_amount,
                        'last_date': mp.last_date.strftime('%Y-%m-%d') if mp.last_date else '-'
                    })
            
            # Invoices (Sales)
            sales = Sale.query.filter_by(customer_id=id)
            if scoped_branch_id is not None:
                sales = sales.filter(Sale.branch_id == scoped_branch_id)
            sales = sales.order_by(Sale.sale_date.desc()).all()
            context['invoices'] = [{
                'number': s.sale_number,
                'date': s.sale_date.strftime('%Y-%m-%d'),
                'status': s.status,
                'amount': s.amount_aed or 0,
                'paid': s.paid_amount_aed or 0,
                'balance': (s.amount_aed or 0) - (s.paid_amount_aed or 0)
            } for s in sales]
            
            # Transactions (Receipts + Payments)
            receipts = Receipt.query.filter_by(customer_id=id)
            payments_out = Payment.query.filter_by(customer_id=id, direction='outgoing')
            if scoped_branch_id is not None:
                receipts = receipts.filter(Receipt.branch_id == scoped_branch_id)
                payments_out = payments_out.filter(Payment.branch_id == scoped_branch_id)
            receipts = receipts.all()
            payments_out = payments_out.all()
            
            all_trans = []
            for r in receipts:
                all_trans.append({
                    'number': r.receipt_number,
                    'type': 'in', # Money In
                    'date': r.receipt_date,
                    'amount': r.amount_aed,
                    'method': r.payment_method,
                    'notes': 'قبض'
                })
            for p in payments_out:
                all_trans.append({
                    'number': p.payment_number,
                    'type': 'out', # Money Out
                    'date': p.payment_date,
                    'amount': p.amount_aed,
                    'method': p.payment_method,
                    'notes': p.notes or 'دفع'
                })
                
            all_trans.sort(key=lambda x: x['date'], reverse=True)
            for t in all_trans:
                t['date'] = t['date'].strftime('%Y-%m-%d')
                
            context['transactions'] = all_trans

        return render_template('reports/partials/entity_report.html', **context)
        
    except Exception as e:
        return render_template('reports/partials/entity_report.html', error=str(e))



@reports_bp.route('/top-selling')
@login_required
@permission_required('view_reports')
def top_selling():
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)
    limit = request.args.get('limit', 20, type=int)
    
    query = db.session.query(
        Product.id,
        Product.name,
        func.sum(SaleLine.quantity).label('total_quantity'),
        func.sum(SaleLine.line_total).label('total_sales')
    ).join(
        SaleLine, Product.id == SaleLine.product_id
    ).join(
        Sale, SaleLine.sale_id == Sale.id
    ).filter(
        Sale.status == 'confirmed'
    )
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        query = query.filter(Sale.branch_id == scoped_branch_id)
    
    if date_from:
        query = query.filter(func.date(Sale.sale_date) >= date_from)
    
    if date_to:
        query = query.filter(func.date(Sale.sale_date) <= date_to)
    
    products = query.group_by(
        Product.id, Product.name
    ).order_by(
        func.sum(SaleLine.quantity).desc()
    ).limit(limit).all()
    
    return render_template('reports/top_selling.html', products=products)

