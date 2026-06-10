import logging
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


def _learn_sale_patterns(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        day_of_week = target.sale_date.strftime('%A') if target.sale_date else 'Unknown'
        hour = target.sale_date.hour if target.sale_date else 0
        month = target.sale_date.month if target.sale_date else 0
        learning_data = {
            'sale_id': target.id,
            'customer_id': target.customer_id,
            'amount': float(target.amount_aed),
            'items_count': len(target.lines) if target.lines else 0,
            'discount_percent': float(target.discount_amount / target.subtotal * 100) if target.subtotal > 0 else 0,
            'payment_status': target.payment_status,
            'time_pattern': {
                'day_of_week': day_of_week,
                'hour': hour,
                'month': month,
                'is_weekend': day_of_week in ['Friday', 'Saturday']
            }
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question="Sale pattern analysis",
            response=json.dumps(learning_data),
            user_feedback=5,
            context={'type': 'sale_pattern', 'data': learning_data}
        )
        logger.info(f"AI Learned: Sale {target.sale_number} | {day_of_week} {hour}:00 | {target.amount_aed} AED")
    except Exception as e:
        logger.error(f"AI learning failed: {e}")


def _customer_analysis(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        customer_insights = {
            'customer_id': target.id,
            'balance': float(target.balance or 0),
            'total_purchases': float(target.total_purchases or 0),
            'classification': target.customer_classification,
            'credit_limit': float(target.credit_limit or 0)
        }
        alerts = []
        if target.balance and target.balance > Decimal('10000'):
            alerts.append('high_balance')
            logger.info(f"AI Priority: Customer {target.id} - High balance: {target.balance} AED")
        if target.balance > target.credit_limit and target.credit_limit > 0:
            alerts.append('credit_limit_exceeded')
            logger.warning(f"AI Alert: Customer {target.id} exceeded credit limit!")
        if target.total_purchases > 100000 and target.customer_classification != 'vip':
            alerts.append('vip_candidate')
            logger.info(f"AI Insight: Customer {target.id} qualifies for VIP upgrade!")
        try:
            learning_system = AzadLearningSystem()
            learning_system.learn_from_interaction(
                question=f"Customer behavior analysis - {target.id}",
                response=json.dumps({'insights': customer_insights, 'alerts': alerts}),
                user_feedback=5,
                context={'type': 'customer_behavior', 'customer_id': target.id}
            )
        except:
            pass
    except Exception as e:
        logger.error(f"AI customer analysis failed: {e}")


def _learn_product_performance(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        product_data = {
            'product_id': target.id,
            'name': target.name,
            'current_stock': float(target.current_stock or 0),
            'min_stock': float(target.min_stock_alert or 0),
            'cost_price': float(target.cost_price or 0),
            'sell_price': float(target.regular_price or 0),
            'margin': float((target.regular_price - target.cost_price) if target.regular_price and target.cost_price else 0)
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question=f"Product performance - {target.name}",
            response=json.dumps(product_data),
            user_feedback=5,
            context={'type': 'product_performance', 'product_id': target.id}
        )
        if target.current_stock < target.min_stock_alert:
            logger.warning(f"AI Reorder Alert: Product {target.name} - Stock: {target.current_stock}")
    except Exception as e:
        logger.error(f"AI product learning failed: {e}")


def _detect_stock_anomaly(mapper, connection, target):
    try:
        if target.current_stock and target.current_stock < target.min_stock_alert:
            logger.warning(f"AI Alert: Product {target.id} ({target.name}) - Low stock: {target.current_stock}")
        if target.current_stock and target.current_stock > 1000:
            logger.warning(f"AI Alert: Product {target.id} ({target.name}) - High stock: {target.current_stock} - Possible slow-moving item")
    except Exception as e:
        logger.error(f"AI stock anomaly detection failed: {e}")


def _comprehensive_sale_analysis(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        anomalies = []
        insights = []
        if target.amount_aed and target.amount_aed > Decimal('50000'):
            anomalies.append('large_amount')
            logger.warning(f"AI Anomaly: Large sale! {target.sale_number} - {target.amount_aed} AED")
        if target.discount_amount and target.subtotal:
            discount_percent = (target.discount_amount / target.subtotal) * 100
            if discount_percent > Decimal('50'):
                anomalies.append('large_discount')
                logger.warning(f"AI Anomaly: Large discount! {target.sale_number} - {discount_percent:.1f}%")
        if target.lines:
            total_cost = sum(line.cost_price * line.quantity for line in target.lines if line.cost_price)
            if total_cost > 0:
                profit = target.amount_aed - total_cost
                margin_percent = (profit / total_cost) * 100
                if margin_percent < 10:
                    insights.append('low_margin')
                    logger.warning(f"AI Insight: Low profit margin! {target.sale_number} - {margin_percent:.1f}%")
                elif margin_percent > 100:
                    insights.append('high_margin')
                    logger.info(f"AI Insight: Excellent profit! {target.sale_number} - {margin_percent:.1f}%")
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question=f"Sale analysis - {target.sale_number}",
            response=json.dumps({'anomalies': anomalies, 'insights': insights}),
            user_feedback=5 if not anomalies else 3,
            context={'type': 'sale_analysis', 'sale_id': target.id}
        )
    except Exception as e:
        logger.error(f"AI sale analysis failed: {e}")


def _learn_product_terminology(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        terminology = {
            'arabic': target.name_ar or target.name,
            'english': target.name,
            'commercial_name': target.commercial_name,
            'part_number': target.part_number,
            'category': target.category.name if target.category else None
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question=f"Product terminology: {target.name}",
            response=json.dumps(terminology, ensure_ascii=False),
            user_feedback=5,
            context={'type': 'linguistic_learning', 'subtype': 'product_terms'}
        )
        logger.info(f"AI Linguistic: Learned product terminology - {target.name}")
    except Exception as e:
        logger.error(f"AI linguistic learning failed: {e}")


def _learn_customer_names(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        names_data = {
            'arabic_name': target.name,
            'english_name': target.name_ar,
            'customer_type': target.customer_type,
            'phone': target.phone,
            'email': target.email
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question=f"Customer names: {target.name}",
            response=json.dumps(names_data, ensure_ascii=False),
            user_feedback=5,
            context={'type': 'linguistic_learning', 'subtype': 'customer_names'}
        )
        logger.info(f"AI Linguistic: Learned customer name - {target.name}")
    except Exception as e:
        logger.error(f"AI name learning failed: {e}")


def _learn_sales_practices(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        practice_data = {
            'sale_number': target.sale_number,
            'payment_terms': {
                'cash_percentage': float(target.paid_amount_aed / target.amount_aed * 100) if target.amount_aed > 0 else 0,
                'credit_given': target.payment_status in ['unpaid', 'partial']
            },
            'discount_strategy': {
                'discount_amount': float(target.discount_amount or 0),
                'discount_percent': float(target.discount_amount / target.subtotal * 100) if target.subtotal > 0 else 0
            },
            'shipping_included': target.shipping_cost > 0 if target.shipping_cost else False,
            'tax_applied': target.tax_amount > 0 if target.tax_amount else False
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question="Sales practice analysis",
            response=json.dumps(practice_data, ensure_ascii=False),
            user_feedback=5,
            context={'type': 'professional_learning', 'subtype': 'sales_practice'}
        )
        logger.info(f"AI Professional: Learned sales practice from {target.sale_number}")
    except Exception as e:
        logger.error(f"AI professional learning failed: {e}")


def _learn_procurement_strategy(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        procurement_data = {
            'supplier_id': target.supplier_id,
            'amount': float(target.amount_aed),
            'payment_method': getattr(target, 'payment_method', None),
            'credit_terms': target.status != 'paid_in_full'
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question="Procurement strategy analysis",
            response=json.dumps(procurement_data),
            user_feedback=5,
            context={'type': 'professional_learning', 'subtype': 'procurement'}
        )
        logger.info(f"AI Professional: Learned procurement from {target.purchase_number}")
    except Exception as e:
        logger.error(f"AI procurement learning failed: {e}")


def _learn_expense_patterns(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        expense_data = {
            'category_id': target.category_id,
            'amount': float(target.amount_aed),
            'payment_method': target.payment_method,
            'is_recurring': target.is_recurring if hasattr(target, 'is_recurring') else False
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question="Expense pattern analysis",
            response=json.dumps(expense_data),
            user_feedback=5,
            context={'type': 'professional_learning', 'subtype': 'expense_management'}
        )
        logger.info(f"AI Professional: Learned expense pattern - {target.amount_aed} AED")
    except Exception as e:
        logger.error(f"AI expense learning failed: {e}")


def _learn_accounting_entries(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        from sqlalchemy import inspect
        lines_count = 0
        ins = inspect(target)
        if 'lines' not in ins.unloaded:
            lines_count = len(target.lines)
        entry_data = {
            'entry_number': target.entry_number,
            'total_debit': float(target.total_debit or 0),
            'total_credit': float(target.total_credit or 0),
            'is_balanced': target.is_balanced() if hasattr(target, 'is_balanced') else True,
            'reference_type': target.reference_type,
            'reference_id': target.reference_id,
            'lines_count': lines_count
        }
        try:
            learning_system = AzadLearningSystem()
            learning_system.learn_from_interaction(
                question=f"Accounting entry analysis - {target.entry_number}",
                response=json.dumps(entry_data),
                user_feedback=5 if entry_data['is_balanced'] else 1,
                context={'type': 'accounting_learning', 'subtype': 'journal_entry'}
            )
            logger.info(f"AI Accounting: Learned entry {target.entry_number} - {'Balanced' if entry_data['is_balanced'] else 'Unbalanced'}")
        except:
            pass
    except Exception as e:
        logger.error(f"AI accounting learning failed: {e}")


def _learn_revenue_recognition(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        revenue_data = {
            'sale_number': target.sale_number,
            'total_revenue': float(target.amount_aed),
            'revenue_recognized': target.status == 'confirmed',
            'cash_received': float(target.paid_amount_aed or 0),
            'accounts_receivable': float(target.balance_due or 0),
            'recognition_principle': 'accrual' if target.status == 'confirmed' else 'cash'
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question="Revenue recognition principle",
            response=json.dumps(revenue_data),
            user_feedback=5,
            context={'type': 'accounting_learning', 'subtype': 'revenue_recognition'}
        )
        logger.info(f"AI Accounting: Revenue recognized - {target.sale_number}")
    except Exception as e:
        logger.error(f"AI revenue learning failed: {e}")


def _learn_expense_recognition(mapper, connection, target):
    try:
        from ai_knowledge.core.learning_system import AzadLearningSystem
        matching_data = {
            'purchase_number': target.purchase_number,
            'total_cost': float(target.amount_aed),
            'recognized_as_expense': target.status == 'confirmed',
            'cash_paid': float(getattr(target, 'paid_amount_aed', 0) or 0),
            'accounts_payable': float(((target.amount_aed or 0) - (getattr(target, 'paid_amount_aed', 0) or 0)) if target.amount_aed else 0)
        }
        learning_system = AzadLearningSystem()
        learning_system.learn_from_interaction(
            question="Expense recognition and matching principle",
            response=json.dumps(matching_data),
            user_feedback=5,
            context={'type': 'accounting_learning', 'subtype': 'expense_recognition'}
        )
        logger.info(f"AI Accounting: Expense recognized - {target.purchase_number}")
    except Exception as e:
        logger.error(f"AI expense recognition learning failed: {e}")


def _predict_future_sales(mapper, connection, target):
    try:
        from sqlalchemy import func
        from models import Sale
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_sales = connection.execute(
            Sale.__table__.select().where(
                Sale.sale_date >= thirty_days_ago,
                Sale.status == 'confirmed'
            )
        ).fetchall()
        if len(recent_sales) > 10:
            total_recent = sum(sale.amount_aed or Decimal('0') for sale in recent_sales)
            avg_daily = total_recent / 30
            predicted_month = avg_daily * 30
            logger.info(f"AI Prediction: Monthly sales forecast: {predicted_month:.2f} AED (based on {len(recent_sales)} sales)")
    except Exception as e:
        logger.error(f"AI prediction failed: {e}")


def _predict_stockout(mapper, connection, target):
    try:
        from models import StockMovement
        if target.current_stock and target.current_stock < target.min_stock_alert:
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            movements = connection.execute(
                StockMovement.__table__.select().where(
                    StockMovement.product_id == target.id,
                    StockMovement.movement_type == 'sale',
                    StockMovement.created_at >= thirty_days_ago
                )
            ).fetchall()
            if movements:
                total_sold = sum(abs(mov.quantity or Decimal('0')) for mov in movements)
                daily_rate = total_sold / 30
                if daily_rate > 0:
                    days_until_stockout = target.current_stock / daily_rate
                    if days_until_stockout < 7:
                        logger.warning(f"AI Prediction: Product {target.name} will run out in {days_until_stockout:.0f} days! (Selling {daily_rate:.1f} units/day)")
                    else:
                        logger.info(f"AI Prediction: Product {target.name} stock will last {days_until_stockout:.0f} days")
    except Exception as e:
        logger.error(f"AI stockout prediction failed: {e}")


def _predict_customer_churn(mapper, connection, target):
    try:
        from sqlalchemy import func
        from models import Sale
        last_sale = connection.execute(
            Sale.__table__.select().where(
                Sale.customer_id == target.id,
                Sale.status == 'confirmed'
            ).order_by(Sale.sale_date.desc()).limit(1)
        ).first()
        if last_sale:
            sale_date = last_sale.sale_date
            if sale_date.tzinfo is None:
                from datetime import timezone as tz
                sale_date = sale_date.replace(tzinfo=tz.utc)
            days_since_purchase = (datetime.now(timezone.utc) - sale_date).days
            if days_since_purchase > 90:
                churn_risk = 'high'
                logger.warning(f"AI Churn Risk: Customer {target.id} - {days_since_purchase} days inactive - HIGH RISK!")
            elif days_since_purchase > 60:
                churn_risk = 'medium'
                logger.info(f"AI Churn Risk: Customer {target.id} - {days_since_purchase} days inactive - Medium risk")
            else:
                churn_risk = 'low'
            from ai_knowledge.core.learning_system import AzadLearningSystem
            learning_system = AzadLearningSystem()
            learning_system.learn_from_interaction(
                question=f"Customer churn prediction - {target.id}",
                response=json.dumps({'days_inactive': days_since_purchase, 'risk': churn_risk}),
                user_feedback=5,
                context={'type': 'predictive_learning', 'subtype': 'churn_prediction'}
            )
    except Exception as e:
        logger.error(f"AI churn prediction failed: {e}")


def _neural_auto_retrain(mapper, connection, target):
    try:
        from models import Sale
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler
        from flask import current_app
        total_sales = connection.execute(
            Sale.__table__.select().where(Sale.status == 'confirmed')
        ).fetchall()
        sales_count = len(total_sales)
        if sales_count % 100 == 0:
            logger.info(f"Neural Milestone: {sales_count} sales - Checking auto-retraining...")
            try:
                import threading
                app = current_app._get_current_object()
                def _run():
                    with app.app_context():
                        AutoRetrainingScheduler.check_and_train_if_needed()
                thread = threading.Thread(target=_run)
                thread.daemon = True
                thread.start()
            except:
                pass
    except Exception as e:
        logger.error(f"Neural auto-retrain failed: {e}")


def _neural_customer_data(mapper, connection, target):
    try:
        from models import Customer
        total_customers = connection.execute(
            Customer.__table__.select().where(Customer.is_active == True)
        ).fetchall()
        customers_count = len(total_customers)
        if customers_count % 50 == 0:
            logger.info(f"Neural: {customers_count} customers - Retraining customer classifier...")
    except Exception as e:
        logger.error(f"Neural customer accumulation failed: {e}")


def _neural_inventory_learning(mapper, connection, target):
    try:
        if hasattr(target, 'current_stock'):
            if target.current_stock == 0:
                logger.warning(f"Neural Alert: Product {target.id} out of stock - Learning from stockout event")
            elif target.current_stock < target.min_stock_alert:
                logger.info(f"Neural: Product {target.id} low stock - Updating demand predictions")
    except Exception as e:
        logger.error(f"Neural inventory learning failed: {e}")


def _intelligent_sale_analysis(mapper, connection, target):
    try:
        from flask import current_app
        if current_app and current_app.config.get('TESTING'):
            return
        if target.status != 'confirmed' or not target.is_active:
            return
        from ai_knowledge.analytics.data_analyzer import data_analyzer
        sale_context = {
            'amount': float(target.amount_aed),
            'items_count': len(target.lines) if target.lines else 0,
            'customer_type': target.customer.customer_type if target.customer else None,
            'payment_status': target.payment_status,
            'profit_margin': (
                float(
                    ((target.amount_aed or Decimal('0')) -
                     sum((line.cost_price or Decimal('0')) * (line.quantity or 0) for line in (target.lines or []))
                    ) / (target.amount_aed or Decimal('1'))
                ) * 100
            ) if (target.amount_aed and target.amount_aed > 0) else 0
        }
        insights = []
        if sale_context['profit_margin'] < 10:
            insights.append(f"⚠️ هامش ربح منخفض ({sale_context['profit_margin']:.1f}%) - راجع التسعير")
        elif sale_context['profit_margin'] > 40:
            insights.append(f"✅ هامش ربح ممتاز ({sale_context['profit_margin']:.1f}%)")
        if sale_context['amount'] > 10000:
            insights.append(f"🎉 فاتورة كبيرة! {sale_context['amount']:,.0f} درهم")
        if sale_context['items_count'] > 10:
            insights.append(f"📦 طلبية كبيرة: {sale_context['items_count']} صنف")
        if insights:
            logger.info(f"Intelligent Insights for Sale {target.sale_number}: {' | '.join(insights)}")
    except Exception as e:
        logger.error(f"Intelligent sale analysis failed: {e}")


def _intelligent_customer_monitoring(mapper, connection, target):
    try:
        from flask import current_app
        if current_app and current_app.config.get('TESTING'):
            return
        from ai_knowledge.analytics.data_analyzer import data_analyzer
        debt_analysis = data_analyzer.analyze_customer_debt(target.id)
        if debt_analysis['success']:
            debt_info = debt_analysis['debt_analysis']
            if debt_info['total_debt'] > 10000:
                logger.warning(f"High debt alert: Customer {target.id} owes {debt_info['total_debt']:,.0f} AED")
            if debt_info['overdue_count'] > 3:
                logger.warning(f"Payment issue: Customer {target.id} has {debt_info['overdue_count']} overdue invoices")
    except Exception as e:
        logger.error(f"Intelligent customer monitoring failed: {e}")


def _intelligent_inventory_alert(mapper, connection, target):
    try:
        if target.current_stock <= target.min_stock_alert:
            days_until_stockout = 0
            if target.current_stock > 0:
                days_until_stockout = target.current_stock / (target.min_stock_alert * 0.1)
            if days_until_stockout < 7:
                logger.warning(f"Intelligent Alert: Product {target.id} ({target.name}) will run out in ~{days_until_stockout:.0f} days!")
                logger.info(f"Recommendation: Order at least {target.min_stock_alert * 2:.0f} units")
    except Exception as e:
        logger.error(f"Intelligent inventory alert failed: {e}")


def register_ai_event_listeners():
    from models import Sale, Customer, Product, GLJournalEntry, Purchase, Expense
    from sqlalchemy import event

    @event.listens_for(Sale, 'after_insert')
    def _h1(mapper, connection, target):
        _learn_sale_patterns(mapper, connection, target)

    @event.listens_for(Customer, 'after_update')
    def _h2(mapper, connection, target):
        _customer_analysis(mapper, connection, target)

    @event.listens_for(Product, 'after_update')
    def _h3(mapper, connection, target):
        _learn_product_performance(mapper, connection, target)

    @event.listens_for(Product, 'before_update')
    def _h4(mapper, connection, target):
        _detect_stock_anomaly(mapper, connection, target)

    @event.listens_for(Sale, 'after_insert')
    def _h5(mapper, connection, target):
        _comprehensive_sale_analysis(mapper, connection, target)

    @event.listens_for(Product, 'after_insert')
    def _h6(mapper, connection, target):
        _learn_product_terminology(mapper, connection, target)

    @event.listens_for(Customer, 'after_insert')
    def _h7(mapper, connection, target):
        _learn_customer_names(mapper, connection, target)

    @event.listens_for(Sale, 'after_insert')
    def _h8(mapper, connection, target):
        _learn_sales_practices(mapper, connection, target)

    @event.listens_for(Purchase, 'after_insert')
    def _h9(mapper, connection, target):
        _learn_procurement_strategy(mapper, connection, target)

    @event.listens_for(Expense, 'after_insert')
    def _h10(mapper, connection, target):
        _learn_expense_patterns(mapper, connection, target)

    @event.listens_for(GLJournalEntry, 'after_insert')
    def _h11(mapper, connection, target):
        _learn_accounting_entries(mapper, connection, target)

    @event.listens_for(Sale, 'after_insert')
    def _h12(mapper, connection, target):
        _learn_revenue_recognition(mapper, connection, target)

    @event.listens_for(Purchase, 'after_insert')
    def _h13(mapper, connection, target):
        _learn_expense_recognition(mapper, connection, target)

    @event.listens_for(Sale, 'after_insert')
    def _h14(mapper, connection, target):
        _predict_future_sales(mapper, connection, target)

    @event.listens_for(Product, 'before_update')
    def _h15(mapper, connection, target):
        _predict_stockout(mapper, connection, target)

    @event.listens_for(Customer, 'after_update')
    def _h16(mapper, connection, target):
        _predict_customer_churn(mapper, connection, target)

    @event.listens_for(Sale, 'after_insert')
    def _h17(mapper, connection, target):
        _intelligent_sale_analysis(mapper, connection, target)

    @event.listens_for(Customer, 'after_update')
    def _h18(mapper, connection, target):
        _intelligent_customer_monitoring(mapper, connection, target)

    @event.listens_for(Product, 'after_update')
    def _h19(mapper, connection, target):
        _intelligent_inventory_alert(mapper, connection, target)


def register_neural_event_listeners():
    from models import Sale, Customer, Product
    from sqlalchemy import event

    @event.listens_for(Sale, 'after_insert')
    def _h1(mapper, connection, target):
        _neural_auto_retrain(mapper, connection, target)

    @event.listens_for(Customer, 'after_insert')
    def _h2(mapper, connection, target):
        _neural_customer_data(mapper, connection, target)

    @event.listens_for(Product, 'after_update')
    def _h3(mapper, connection, target):
        _neural_inventory_learning(mapper, connection, target)
