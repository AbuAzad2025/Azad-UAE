from datetime import datetime, date, timedelta
from decimal import Decimal
from extensions import db
from models import GLAccount, GLJournalEntry, GLJournalLine, Sale, Purchase, Expense
from sqlalchemy import func
import json

class AdvancedFinancialAnalytics:
    """نظام التحليل المالي المتقدم"""
    
    @staticmethod
    def get_financial_ratios(date_from=None, date_to=None, tenant_id=None):
        """حساب النسب المالية"""
        from utils.gl_tenant import active_tenant_id
        tenant_id = tenant_id if tenant_id is not None else active_tenant_id()
        if not date_from:
            date_from = date.today() - timedelta(days=365)
        if not date_to:
            date_to = date.today()
        
        current_assets = AdvancedFinancialAnalytics._calculate_balance_by_prefix('11', date_to, tenant_id=tenant_id)
        total_assets = AdvancedFinancialAnalytics._calculate_balance_by_prefix('1', date_to, tenant_id=tenant_id)
        current_liabilities = AdvancedFinancialAnalytics._calculate_balance_by_prefix('21', date_to, tenant_id=tenant_id)
        total_liabilities = AdvancedFinancialAnalytics._calculate_balance_by_prefix('2', date_to, tenant_id=tenant_id)
        equity = AdvancedFinancialAnalytics._calculate_balance_by_prefix('3', date_to, tenant_id=tenant_id)
        revenue = AdvancedFinancialAnalytics._calculate_balance_by_prefix('4', date_from, date_to, is_pl=True, tenant_id=tenant_id)
        expenses = AdvancedFinancialAnalytics._calculate_balance_by_prefix(['5', '6'], date_from, date_to, is_pl=True, tenant_id=tenant_id)
        
        # صافي الربح
        net_profit = revenue - expenses
        
        # النسب المالية
        ratios = {
            # نسب السيولة
            'liquidity': {
                'current_ratio': float(current_assets / current_liabilities) if current_liabilities > 0 else 0,
                'quick_ratio': float((current_assets * Decimal('0.8')) / current_liabilities) if current_liabilities > 0 else 0,
                'cash_ratio': float((current_assets * Decimal('0.3')) / current_liabilities) if current_liabilities > 0 else 0
            },
            
            # نسب الربحية
            'profitability': {
                'gross_profit_margin': float((net_profit / revenue) * 100) if revenue > 0 else 0,
                'net_profit_margin': float((net_profit / revenue) * 100) if revenue > 0 else 0,
                'return_on_assets': float((net_profit / total_assets) * 100) if total_assets > 0 else 0,
                'return_on_equity': float((net_profit / equity) * 100) if equity > 0 else 0
            },
            
            # نسب الكفاءة
            'efficiency': {
                'asset_turnover': float(revenue / total_assets) if total_assets > 0 else 0,
                'expense_ratio': float((expenses / revenue) * 100) if revenue > 0 else 0
            },
            
            # نسب المديونية
            'leverage': {
                'debt_to_equity': float(total_liabilities / equity) if equity > 0 else 0,
                'debt_to_assets': float(total_liabilities / total_assets) if total_assets > 0 else 0,
                'equity_multiplier': float(total_assets / equity) if equity > 0 else 0
            },
            
            # البيانات الأساسية
            'base_data': {
                'current_assets': float(current_assets),
                'total_assets': float(total_assets),
                'current_liabilities': float(current_liabilities),
                'total_liabilities': float(total_liabilities),
                'equity': float(equity),
                'revenue': float(revenue),
                'expenses': float(expenses),
                'net_profit': float(net_profit)
            }
        }
        
        return ratios
    
    @staticmethod
    def _calculate_balance_by_prefix(prefix, date_from=None, date_to=None, is_pl=False, tenant_id=None):
        """
        حساب رصيد الحسابات التي تبدأ برمز معين
        """
        from utils.gl_tenant import scope_gl_accounts, active_tenant_id
        tenant_id = tenant_id if tenant_id is not None else active_tenant_id()
        query = scope_gl_accounts(
            GLAccount.query.filter(GLAccount.is_active == True, GLAccount.is_header == False),
            tenant_id=tenant_id,
        )
        
        if isinstance(prefix, list):
            from sqlalchemy import or_
            conditions = [GLAccount.code.startswith(p) for p in prefix]
            query = query.filter(or_(*conditions))
        else:
            query = query.filter(GLAccount.code.startswith(prefix))
            
        accounts = query.all()
        total = Decimal(0)
        
        # تحديد تواريخ الفلترة
        filter_start = date_from if is_pl else None
        filter_end = date_to
        
        # Ensure filter_end includes the full day if it's a date object
        if filter_end and isinstance(filter_end, date) and not isinstance(filter_end, datetime):
             filter_end = datetime.combine(filter_end, datetime.max.time())
        
        for account in accounts:
            lines_query = GLJournalLine.query.join(GLJournalEntry).filter(
                GLJournalLine.account_id == account.id,
                GLJournalEntry.is_posted == True,
            )
            if tenant_id is not None:
                lines_query = lines_query.filter(GLJournalEntry.tenant_id == int(tenant_id))
            if filter_start:
                lines_query = lines_query.filter(GLJournalEntry.entry_date >= filter_start)
            
            if filter_end:
                lines_query = lines_query.filter(GLJournalEntry.entry_date <= filter_end)
                
            lines = lines_query.all()
            
            for line in lines:
                # amount_aed represents (Debit - Credit) in AED
                # Asset/Expense: Normal Balance is Debit (+)
                # Liability/Equity/Revenue: Normal Balance is Credit (-)
                
                val = line.amount_aed
                
                if account.type in ['asset', 'expense']:
                    total += val
                else:
                    # For credit-normal accounts, a positive amount_aed (Debit > Credit) reduces the balance
                    # A negative amount_aed (Credit > Debit) increases the balance (absolute value)
                    # So we subtract val:
                    # If Credit=100, Debit=0 -> amount_aed = -100 -> total -= (-100) -> total += 100 (Correct)
                    total -= val
                    
        return total

    @staticmethod
    def _calculate_account_type_balance(account_type, date_from=None, date_to=None, tenant_id=None):
        """حساب رصيد نوع حساب معين"""
        from utils.gl_tenant import scope_gl_accounts, active_tenant_id
        tenant_id = tenant_id if tenant_id is not None else active_tenant_id()
        accounts = scope_gl_accounts(
            GLAccount.query.filter_by(type=account_type, is_active=True, is_header=False),
            tenant_id=tenant_id,
        ).all()
        total = Decimal(0)
        
        # Ensure date_to includes the full day if it's a date object
        if date_to and isinstance(date_to, date) and not isinstance(date_to, datetime):
             date_to = datetime.combine(date_to, datetime.max.time())
        
        for account in accounts:
            if date_from and date_to:
                lines_q = GLJournalLine.query.join(GLJournalEntry).filter(
                    GLJournalLine.account_id == account.id,
                    GLJournalEntry.entry_date >= date_from,
                    GLJournalEntry.entry_date <= date_to,
                    GLJournalEntry.is_posted == True,
                )
                if tenant_id is not None:
                    lines_q = lines_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
                lines = lines_q.all()
                
                for line in lines:
                    if account_type in ['asset', 'expense']:
                        total += line.amount_aed
                    else:
                        total -= line.amount_aed
            else:
                # الرصيد الكامل
                balance = account.get_balance()
                total += abs(balance)
        
        return total
    
    @staticmethod
    def get_trend_analysis(months=12):
        """تحليل الاتجاهات"""
        end_date = date.today()
        start_date = end_date - timedelta(days=months*30)
        
        trends = []
        current_date = start_date
        
        for i in range(months):
            month_start = current_date
            month_end = month_start + timedelta(days=30)
            
            revenue = AdvancedFinancialAnalytics._calculate_account_type_balance('revenue', month_start, month_end)
            expenses = AdvancedFinancialAnalytics._calculate_account_type_balance('expense', month_start, month_end)
            profit = revenue - expenses
            
            trends.append({
                'month': month_start.strftime('%Y-%m'),
                'revenue': float(revenue),
                'expenses': float(expenses),
                'profit': float(profit),
                'margin': float((profit / revenue) * 100) if revenue > 0 else 0
            })
            
            current_date = month_end
        
        # حساب التغيرات الشهرية
        for i in range(1, len(trends)):
            prev_profit = trends[i-1]['profit']
            current_profit = trends[i]['profit']
            
            if prev_profit != 0:
                change = ((current_profit - prev_profit) / abs(prev_profit)) * 100
                trends[i]['change'] = round(change, 2)
            else:
                trends[i]['change'] = 0
        
        if trends:
            trends[0]['change'] = 0
        
        return trends
    
    @staticmethod
    def get_comparative_analysis(periods=['current', 'last_month', 'last_year']):
        """تحليل مقارن"""
        today = date.today()
        
        periods_data = {}
        
        for period in periods:
            if period == 'current':
                start_date = today.replace(day=1)
                end_date = today
            elif period == 'last_month':
                last_month = today.replace(day=1) - timedelta(days=1)
                start_date = last_month.replace(day=1)
                end_date = last_month
            elif period == 'last_year':
                start_date = today.replace(year=today.year-1, month=1, day=1)
                end_date = today.replace(year=today.year-1, month=12, day=31)
            else:
                continue
            
            revenue = AdvancedFinancialAnalytics._calculate_account_type_balance('revenue', start_date, end_date)
            expenses = AdvancedFinancialAnalytics._calculate_account_type_balance('expense', start_date, end_date)
            profit = revenue - expenses
            
            periods_data[period] = {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'revenue': float(revenue),
                'expenses': float(expenses),
                'profit': float(profit),
                'margin': float((profit / revenue) * 100) if revenue > 0 else 0
            }
        
        return periods_data
    
    @staticmethod
    def get_expense_breakdown(tenant_id=None):
        """تحليل تفصيلي للمصروفات"""
        from utils.gl_tenant import scope_gl_accounts, active_tenant_id
        tenant_id = tenant_id if tenant_id is not None else active_tenant_id()
        expense_accounts = scope_gl_accounts(
            GLAccount.query.filter_by(type='expense', is_active=True, is_header=False),
            tenant_id=tenant_id,
        ).all()
        
        breakdown = []
        total_expenses = Decimal(0)
        
        for account in expense_accounts:
            balance = abs(account.get_balance())
            total_expenses += balance
            
            breakdown.append({
                'account_code': account.code,
                'account_name': account.full_name,
                'amount': float(balance)
            })
        
        # حساب النسب المئوية
        for item in breakdown:
            if total_expenses > 0:
                item['percentage'] = round((item['amount'] / float(total_expenses)) * 100, 2)
            else:
                item['percentage'] = 0
        
        # ترتيب حسب المبلغ
        breakdown.sort(key=lambda x: x['amount'], reverse=True)
        
        return {
            'items': breakdown,
            'total': float(total_expenses)
        }
    
    @staticmethod
    def get_revenue_breakdown(tenant_id=None):
        """تحليل تفصيلي للإيرادات"""
        from utils.gl_tenant import scope_gl_accounts, active_tenant_id
        tenant_id = tenant_id if tenant_id is not None else active_tenant_id()
        revenue_accounts = scope_gl_accounts(
            GLAccount.query.filter_by(type='revenue', is_active=True, is_header=False),
            tenant_id=tenant_id,
        ).all()
        
        breakdown = []
        total_revenue = Decimal(0)
        
        for account in revenue_accounts:
            balance = abs(account.get_balance())
            total_revenue += balance
            
            breakdown.append({
                'account_code': account.code,
                'account_name': account.full_name,
                'amount': float(balance)
            })
        
        # حساب النسب المئوية
        for item in breakdown:
            if total_revenue > 0:
                item['percentage'] = round((item['amount'] / float(total_revenue)) * 100, 2)
            else:
                item['percentage'] = 0
        
        # ترتيب حسب المبلغ
        breakdown.sort(key=lambda x: x['amount'], reverse=True)
        
        return {
            'items': breakdown,
            'total': float(total_revenue)
        }
    
    @staticmethod
    def get_forecasting_data(months_ahead=6):
        """توقعات مالية"""
        # الحصول على البيانات التاريخية
        historical = AdvancedFinancialAnalytics.get_trend_analysis(months=12)
        
        if not historical or len(historical) < 3:
            return []
        
        # حساب المتوسطات للتوقع البسيط
        avg_revenue = sum(item['revenue'] for item in historical) / len(historical)
        avg_expenses = sum(item['expenses'] for item in historical) / len(historical)
        avg_growth = sum(item.get('change', 0) for item in historical[1:]) / (len(historical) - 1)
        
        # توقعات الأشهر القادمة
        forecasts = []
        last_month = historical[-1]
        
        for i in range(months_ahead):
            # تطبيق معدل النمو المتوسط
            growth_factor = 1 + (avg_growth / 100)
            
            forecast_revenue = last_month['revenue'] * (growth_factor ** (i + 1))
            forecast_expenses = last_month['expenses'] * (growth_factor ** (i + 1))
            forecast_profit = forecast_revenue - forecast_expenses
            
            future_date = date.today() + timedelta(days=(i+1)*30)
            
            forecasts.append({
                'month': future_date.strftime('%Y-%m'),
                'revenue': round(forecast_revenue, 2),
                'expenses': round(forecast_expenses, 2),
                'profit': round(forecast_profit, 2),
                'margin': round((forecast_profit / forecast_revenue) * 100, 2) if forecast_revenue > 0 else 0,
                'is_forecast': True
            })
        
        return forecasts
    
    @staticmethod
    def get_dashboard_summary():
        """ملخص شامل للوحة المعلومات"""
        ratios = AdvancedFinancialAnalytics.get_financial_ratios()
        trends = AdvancedFinancialAnalytics.get_trend_analysis(months=6)
        expense_breakdown = AdvancedFinancialAnalytics.get_expense_breakdown()
        revenue_breakdown = AdvancedFinancialAnalytics.get_revenue_breakdown()
        forecast = AdvancedFinancialAnalytics.get_forecasting_data(months_ahead=3)
        
        return {
            'ratios': ratios,
            'trends': trends,
            'expense_breakdown': expense_breakdown,
            'revenue_breakdown': revenue_breakdown,
            'forecast': forecast,
            'generated_at': datetime.now().isoformat()
        }
