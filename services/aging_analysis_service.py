"""
خدمة تحليل العمر - Aging Analysis Service
"""

from decimal import Decimal
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_
from extensions import db
from models import Customer, Supplier, Sale, Purchase, Payment, GLJournalLine, GLJournalEntry, GLAccount
from utils.constants import SALE_PAYMENT_STATUSES
from utils.gl_reference_types import GLRef


class AgingAnalysisService:
    
    @staticmethod
    def get_receivables_aging(as_of_date=None, branch_id=None, tenant_id=None):
        """
        تحليل عمر الذمم المدينة (Accounts Receivable)
        
        Args:
            as_of_date: التاريخ المرجعي (default: اليوم)
        
        Returns:
            {
                'customers': [...],
                'totals': {...},
                'as_of_date': date
            }
        """
        from utils.tenanting import active_tenant_id, tenant_query
        tid = tenant_id or active_tenant_id()
        if not as_of_date:
            as_of_date = date.today()
        elif isinstance(as_of_date, str):
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        
        results = []
        totals = {
            '0-30': Decimal('0'),
            '31-60': Decimal('0'),
            '61-90': Decimal('0'),
            '91-120': Decimal('0'),
            'over_120': Decimal('0'),
            'total': Decimal('0')
        }
        
        # جميع العملاء النشطين
        customers = tenant_query(Customer, tenant_id=tid).filter_by(is_active=True).order_by(Customer.name).all()
        
        for customer in customers:
            aging = {
                'customer': customer,
                '0-30': Decimal('0'),
                '31-60': Decimal('0'),
                '61-90': Decimal('0'),
                '91-120': Decimal('0'),
                'over_120': Decimal('0'),
                'total': Decimal('0'),
                'invoices': []
            }
            
            # المبيعات غير المدفوعة بالكامل (partial أو unpaid فقط - لا paid)
            unpaid_sales = Sale.query.filter(
                Sale.customer_id == customer.id,
                Sale.tenant_id == tid,
                Sale.payment_status.in_(tuple(s for s in SALE_PAYMENT_STATUSES if s != 'paid')),
                Sale.status == 'confirmed',
                func.date(Sale.sale_date) <= as_of_date
            ).order_by(Sale.sale_date).all()
            if branch_id:
                unpaid_sales = [sale for sale in unpaid_sales if sale.branch_id == branch_id]
            
            for sale in unpaid_sales:
                # حساب الرصيد المتبقي
                balance = (sale.amount_aed or Decimal('0')) - (sale.paid_amount_aed or Decimal('0'))
                
                if balance > 0:
                    # حساب عمر الفاتورة
                    days_old = (as_of_date - sale.sale_date.date()).days
                    
                    # تصنيف حسب العمر
                    if days_old <= 30:
                        aging['0-30'] += balance
                        age_category = '0-30'
                    elif days_old <= 60:
                        aging['31-60'] += balance
                        age_category = '31-60'
                    elif days_old <= 90:
                        aging['61-90'] += balance
                        age_category = '61-90'
                    elif days_old <= 120:
                        aging['91-120'] += balance
                        age_category = '91-120'
                    else:
                        aging['over_120'] += balance
                        age_category = '+120'
                    
                    aging['total'] += balance
                    
                    # إضافة تفاصيل الفاتورة
                    aging['invoices'].append({
                        'sale_number': sale.sale_number,
                        'sale_date': sale.sale_date.date(),
                        'total': float(sale.amount_aed or 0),
                        'paid': float(sale.paid_amount_aed or 0),
                        'balance': float(balance),
                        'days_old': days_old,
                        'age_category': age_category
                    })
            
            # إضافة العميل إذا كان لديه رصيد
            if aging['total'] > 0:
                # تحويل Decimals لـ floats
                aging_float = {
                    'customer': customer,
                    '0-30': float(aging['0-30']),
                    '31-60': float(aging['31-60']),
                    '61-90': float(aging['61-90']),
                    '91-120': float(aging['91-120']),
                    'over_120': float(aging['over_120']),
                    'total': float(aging['total']),
                    'invoices': aging['invoices']
                }
                results.append(aging_float)
                
                # إضافة للإجماليات
                totals['0-30'] += aging['0-30']
                totals['31-60'] += aging['31-60']
                totals['61-90'] += aging['61-90']
                totals['91-120'] += aging['91-120']
                totals['over_120'] += aging['over_120']
                totals['total'] += aging['total']
        
        # تحويل الإجماليات لـ floats
        totals_float = {k: float(v) for k, v in totals.items()}
        
        return {
            'customers': results,
            'totals': totals_float,
            'as_of_date': as_of_date,
            'customer_count': len(results)
        }
    
    @staticmethod
    def get_payables_aging(as_of_date=None, branch_id=None, tenant_id=None):
        """
        تحليل عمر الذمم الدائنة (Accounts Payable)
        """
        from utils.tenanting import active_tenant_id, tenant_query
        tid = tenant_id or active_tenant_id()
        if not as_of_date:
            as_of_date = date.today()
        elif isinstance(as_of_date, str):
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        
        results = []
        totals = {
            '0-30': Decimal('0'),
            '31-60': Decimal('0'),
            '61-90': Decimal('0'),
            '91-120': Decimal('0'),
            'over_120': Decimal('0'),
            'total': Decimal('0')
        }
        
        # جميع الموردين النشطين
        suppliers = tenant_query(Supplier, tenant_id=tid).filter_by(is_active=True).order_by(Supplier.name).all()
        
        for supplier in suppliers:
            aging = {
                'supplier': supplier,
                '0-30': Decimal('0'),
                '31-60': Decimal('0'),
                '61-90': Decimal('0'),
                '91-120': Decimal('0'),
                'over_120': Decimal('0'),
                'total': Decimal('0'),
                'invoices': []
            }
            
            # المشتريات غير المدفوعة بالكامل بطريقة FIFO على مستوى المورد
            # ملاحظة: Payment لا يحتوي purchase_id، لذلك نوزّع مدفوعات المورد على أقدم الفواتير أولاً.
            purchases_query = Purchase.query.filter(
                Purchase.supplier_id == supplier.id,
                Purchase.tenant_id == tid,
                Purchase.status == 'confirmed',
                func.date(Purchase.purchase_date) <= as_of_date
            ).order_by(Purchase.purchase_date)
            if branch_id:
                purchases_query = purchases_query.filter(Purchase.branch_id == branch_id)
            all_purchases = purchases_query.all()

            payments_query = db.session.query(func.sum(Payment.amount_aed)).filter(
                Payment.supplier_id == supplier.id,
                Payment.tenant_id == tid,
                Payment.direction == 'outgoing',
                Payment.payment_confirmed == True,
                func.date(Payment.payment_date) <= as_of_date
            )
            if branch_id:
                payments_query = payments_query.filter(Payment.branch_id == branch_id)
            total_paid_for_supplier = payments_query.scalar() or Decimal('0')

            remaining_paid = Decimal(str(total_paid_for_supplier))

            for purchase in all_purchases:
                purchase_total = Decimal(str(purchase.total_amount or 0))
                allocated_paid = min(purchase_total, remaining_paid) if remaining_paid > 0 else Decimal('0')
                balance = purchase_total - allocated_paid
                remaining_paid = max(Decimal('0'), remaining_paid - allocated_paid)
                
                if balance > 0:
                    # حساب عمر الفاتورة
                    days_old = (as_of_date - purchase.purchase_date.date()).days
                    
                    # تصنيف حسب العمر
                    if days_old <= 30:
                        aging['0-30'] += balance
                        age_category = '0-30'
                    elif days_old <= 60:
                        aging['31-60'] += balance
                        age_category = '31-60'
                    elif days_old <= 90:
                        aging['61-90'] += balance
                        age_category = '61-90'
                    elif days_old <= 120:
                        aging['91-120'] += balance
                        age_category = '91-120'
                    else:
                        aging['over_120'] += balance
                        age_category = '+120'
                    
                    aging['total'] += balance
                    
                    # إضافة تفاصيل الفاتورة
                    aging['invoices'].append({
                        'purchase_number': purchase.purchase_number,
                        'purchase_date': purchase.purchase_date.date() if purchase.purchase_date else None,
                        'total': float(purchase_total),
                        'paid': float(allocated_paid),
                        'balance': float(balance),
                        'days_old': days_old,
                        'age_category': age_category
                    })
            
            # إضافة المورد إذا كان لديه رصيد
            if aging['total'] > 0:
                aging_float = {
                    'supplier': supplier,
                    '0-30': float(aging['0-30']),
                    '31-60': float(aging['31-60']),
                    '61-90': float(aging['61-90']),
                    '91-120': float(aging['91-120']),
                    'over_120': float(aging['over_120']),
                    'total': float(aging['total']),
                    'invoices': aging['invoices']
                }
                results.append(aging_float)
                
                # إضافة للإجماليات
                totals['0-30'] += aging['0-30']
                totals['31-60'] += aging['31-60']
                totals['61-90'] += aging['61-90']
                totals['91-120'] += aging['91-120']
                totals['over_120'] += aging['over_120']
                totals['total'] += aging['total']
        
        totals_float = {k: float(v) for k, v in totals.items()}
        
        return {
            'suppliers': results,
            'totals': totals_float,
            'as_of_date': as_of_date,
            'supplier_count': len(results)
        }

    @staticmethod
    def _resolve_aging_account(concept_code: str, tenant_id=None, branch_id=None):
        """إيجاد حساب GL للمقارنة."""
        from services.gl_service import GL_ACCOUNTS
        code = GL_ACCOUNTS.get('receivable' if 'AR' in concept_code or 'receivable' in concept_code else 'payable', '1130')
        if 'payable' in concept_code or 'AP' in concept_code:
            code = GL_ACCOUNTS.get('payable', '2110')
        q = GLAccount.query.filter_by(code=code)
        if tenant_id:
            q = q.filter_by(tenant_id=int(tenant_id))
        return q.first()

    @staticmethod
    def verify_receivables_with_gl(as_of_date=None, branch_id=None, tenant_id=None):
        """مقارنة تحليل أعمال الذمم المدينة مع GL Accounts Receivable."""
        tid = tenant_id
        if not as_of_date:
            as_of_date = date.today()
        elif isinstance(as_of_date, str):
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()

        ar_report = AgingAnalysisService.get_receivables_aging(as_of_date, branch_id, tid)
        aging_total = Decimal(str(ar_report['totals']['total']))

        ar_acc = AgingAnalysisService._resolve_aging_account('AR', tid, branch_id)
        gl_total = Decimal('0')
        if ar_acc:
            query = db.session.query(
                func.coalesce(func.sum(GLJournalLine.debit), 0) - func.coalesce(func.sum(GLJournalLine.credit), 0)
            ).join(GLJournalEntry).filter(
                GLJournalLine.account_id == ar_acc.id,
                GLJournalEntry.is_posted == True,
            )
            if tid:
                query = query.filter(GLJournalEntry.tenant_id == int(tid))
            if branch_id:
                query = query.filter(GLJournalEntry.branch_id == branch_id)
            if as_of_date:
                query = query.filter(func.date(GLJournalEntry.entry_date) <= as_of_date)
            gl_total = abs(Decimal(str(query.scalar() or 0)))

        return {
            'aging_total': float(aging_total),
            'gl_total': float(gl_total),
            'difference': float(aging_total - gl_total),
            'in_balance': abs(aging_total - gl_total) < Decimal('0.01'),
        }

    @staticmethod
    def verify_payables_with_gl(as_of_date=None, branch_id=None, tenant_id=None):
        """مقارنة تحليل أعمار الموردين مع GL Accounts Payable."""
        tid = tenant_id
        if not as_of_date:
            as_of_date = date.today()
        elif isinstance(as_of_date, str):
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()

        ap_report = AgingAnalysisService.get_payables_aging(as_of_date, branch_id, tid)
        aging_total = Decimal(str(ap_report['totals']['total']))

        ap_acc = AgingAnalysisService._resolve_aging_account('AP', tid, branch_id)
        gl_total = Decimal('0')
        if ap_acc:
            query = db.session.query(
                func.coalesce(func.sum(GLJournalLine.credit), 0) - func.coalesce(func.sum(GLJournalLine.debit), 0)
            ).join(GLJournalEntry).filter(
                GLJournalLine.account_id == ap_acc.id,
                GLJournalEntry.is_posted == True,
            )
            if tid:
                query = query.filter(GLJournalEntry.tenant_id == int(tid))
            if branch_id:
                query = query.filter(GLJournalEntry.branch_id == branch_id)
            if as_of_date:
                query = query.filter(func.date(GLJournalEntry.entry_date) <= as_of_date)
            gl_total = abs(Decimal(str(query.scalar() or 0)))

        return {
            'aging_total': float(aging_total),
            'gl_total': float(gl_total),
            'difference': float(aging_total - gl_total),
            'in_balance': abs(aging_total - gl_total) < Decimal('0.01'),
        }

