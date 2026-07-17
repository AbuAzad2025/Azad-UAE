"""AZAD AI service — business intelligence, chat, and knowledge integration."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from typing import TYPE_CHECKING, Any

from extensions import db

if TYPE_CHECKING:
    from models import Customer
from ai_knowledge.knowledge import (
    COMPANY_INFO,
    get_automotive_ecu_knowledge,
    get_customs_advice,
    get_part_info,
    get_tax_info,
    search_knowledge,
)
from ai_knowledge.specialized import (
    get_customer_service_tip,
    get_guide,
    get_system_guide as lookup_system_guide,
    get_tax_advice,
)
from ai_knowledge.specialized_knowledge import AdvancedLaws
from ai_knowledge.analytics import get_market_insights
from utils.tenanting import get_active_tenant_id

logger = logging.getLogger(__name__)


class AIService:
    """🧠 أزاد - AZAD AI Assistant
    المساعد الذكي الخبير الشامل - متكامل مع جميع وحدات AI
    
    الوحدات المتكاملة:
    - learning_system: نظام التعلم الذاتي
    - context_engine: محرك فهم السياق
    - analytics_predictions: التحليلات والتوقعات
    - data_analyzer: محلل البيانات
    - azad_personality: شخصية أزاد
    - system_integration: التكامل مع النظام
    - knowledge_expansion: توسيع المعرفة
    - self_improvement: التحسين الذاتي
    - document_generator: مولد المستندات
    - global_knowledge: المعرفة العالمية
    - dialects: اللهجات العربية
    - security_rules: قواعد الأمان
    - beginners_mode: وضع المبتدئين
    - parts_knowledge: معرفة قطع الغيار
    - tax_customs: الضرائب والجمارك
    - market_insights: رؤى السوق
    """
    
    # AI Configuration
    NAME = "أزاد"
    COMPANY = "شركة أزاد للأنظمة الذكية"
    DEVELOPER = "م. أحمد غنام"
    
    # تهيئة المكونات الذكية
    _learning_system = None
    _context_engine = None
    _personality = None
    _dialect_manager = None
    _security_rules = None
    _neural_engine = None
    _reasoning_engine = None
    _memory_system = None
    _code_generator = None
    _agent_coordinator = None
    _reflection_engine = None
    _conversation_manager = None
    _vision_processor = None
    _master_brain = None
    _transformers_brain = None
    
    @classmethod
    def get_learning_system(cls):
        """الحصول على نظام التعلم"""
        if cls._learning_system is None:
            from ai_knowledge.core.learning_system import AzadLearningSystem
            cls._learning_system = AzadLearningSystem()
        return cls._learning_system
    
    @classmethod
    def get_context_engine(cls):
        """الحصول على محرك السياق"""
        if cls._context_engine is None:
            from ai_knowledge.core.context_engine import ContextEngine
            cls._context_engine = ContextEngine()
        return cls._context_engine
    
    @classmethod
    def get_personality(cls):
        """الحصول على شخصية أزاد"""
        if cls._personality is None:
            from ai_knowledge.personality.azad_personality import AzadPersonality
            cls._personality = AzadPersonality()
        return cls._personality
    
    @classmethod
    def get_dialect_manager(cls):
        """الحصول على مدير اللهجات"""
        if cls._dialect_manager is None:
            from ai_knowledge.personality.dialects import DialectManager
            cls._dialect_manager = DialectManager()
        return cls._dialect_manager
    
    @classmethod
    def get_security_rules(cls):
        """الحصول على قواعد الأمان"""
        if cls._security_rules is None:
            from ai_knowledge.specialized.security_rules import SecurityRules
            cls._security_rules = SecurityRules()
        return cls._security_rules
    
    @classmethod
    def get_neural_engine(cls):
        """الحصول على محرك الشبكات العصبية"""
        if cls._neural_engine is None:
            from ai_knowledge.neural.neural_engine import get_neural_engine
            cls._neural_engine = get_neural_engine()
        return cls._neural_engine
    
    @classmethod
    def get_reasoning_engine(cls):
        """الحصول على محرك التفكير المنطقي"""
        if cls._reasoning_engine is None:
            from ai_knowledge.core.reasoning_engine import get_reasoning_engine
            cls._reasoning_engine = get_reasoning_engine()
        return cls._reasoning_engine
    
    @classmethod
    def get_memory_system(cls):
        """الحصول على نظام الذاكرة"""
        if cls._memory_system is None:
            from ai_knowledge.core.memory_system import get_memory_system
            cls._memory_system = get_memory_system()
        return cls._memory_system
    
    @classmethod
    def get_code_generator(cls):
        """الحصول على مولد الأكواد"""
        if cls._code_generator is None:
            from ai_knowledge.generation.code_generator import get_code_generator
            cls._code_generator = get_code_generator()
        return cls._code_generator
    
    @classmethod
    def get_agent_coordinator(cls):
        """الحصول على منسق الوكلاء"""
        if cls._agent_coordinator is None:
            from ai_knowledge.agents.multi_agent_system import get_agent_coordinator
            cls._agent_coordinator = get_agent_coordinator()
        return cls._agent_coordinator
    
    @classmethod
    def get_reflection_engine(cls):
        """الحصول على محرك التأمل الذاتي"""
        if cls._reflection_engine is None:
            from ai_knowledge.improvement.self_reflection import get_reflection_engine
            cls._reflection_engine = get_reflection_engine()
        return cls._reflection_engine
    
    @classmethod
    def get_conversation_manager(cls):
        """الحصول على مدير المحادثات"""
        if cls._conversation_manager is None:
            from ai_knowledge.core.conversation_manager import get_conversation_manager
            cls._conversation_manager = get_conversation_manager()
        return cls._conversation_manager
    
    @classmethod
    def get_vision_processor(cls):
        """الحصول على معالج الرؤية"""
        if cls._vision_processor is None:
            from ai_knowledge.neural.vision_processor import get_vision_processor
            cls._vision_processor = get_vision_processor()
        return cls._vision_processor
    
    @classmethod
    def get_master_brain(cls):
        """الحصول على العقل الرئيسي الموحد"""
        if cls._master_brain is None:
            from ai_knowledge.agents.master_brain import get_master_brain
            cls._master_brain = get_master_brain()
        return cls._master_brain
    
    @classmethod
    def get_transformers_brain(cls):
        """الحصول على دماغ المحولات (Transformers)"""
        if cls._transformers_brain is None:
            from ai_knowledge.neural.transformers_brain import get_transformers_brain
            cls._transformers_brain = get_transformers_brain()
        return cls._transformers_brain
    
    # قائمة الكلمات المفتاحية للمعلومات السرية
    SENSITIVE_KEYWORDS = [
        'كلمة مرور', 'كلمات مرور', 'كلمة المرور', 'كلمات المرور',
        'كلمة سر', 'كلمات سر', 'كلمة السر', 'كلمات السر', 
        'باسورد', 'password', 'passwords', 'pass', 'pwd',
        'معلومات مستخدم', 'معلومات مستخدمين', 'معلومات المستخدم', 'معلومات المستخدمين',
        'بيانات مستخدم', 'بيانات مستخدمين', 'بيانات المستخدم', 'بيانات المستخدمين',
        'user info', 'user data', 'users info', 'users data', 'user', 'users',
        'صلاحيات', 'صلاحية', 'permissions', 'permission', 'roles', 'role', 'access',
        'مفتاح', 'مفاتيح', 'key', 'keys', 'token', 'tokens', 'secret', 'secrets',
        'حساب', 'حسابات', 'account', 'accounts', 'account details'
    ]
    
    GROQ_MODELS = {
        'fast': 'llama-3.1-70b-versatile',
        'smart': 'llama-3.1-70b-versatile',
        'expert': 'llama-3.1-70b-versatile'
    }
    
    OPENAI_MODELS = {
        'fast': 'gpt-3.5-turbo',
        'smart': 'gpt-4',
        'expert': 'gpt-4-turbo'
    }
    
    @staticmethod
    def get_api_key():
        """الحصول على مفتاح API - يدعم Groq, OpenAI, Gemini"""
        # Reload env to catch manual updates
        from dotenv import load_dotenv
        load_dotenv(override=True)
        
        return (
            os.environ.get('GROQ_API_KEY') or 
            os.environ.get('GEMINI_API_KEY') or 
            os.environ.get('OPENAI_API_KEY')
        )
    
    @staticmethod
    def is_enabled():
        """هل AI مفعّل؟ (دائماً - AI محلي خارق)"""
        return True
    
    @staticmethod
    def get_provider():
        """معرفة المزود النشط"""
        # Reload env to catch manual updates
        from dotenv import load_dotenv
        load_dotenv(override=True)
        
        if os.environ.get('GROQ_API_KEY'):
            return 'groq'
        elif os.environ.get('GEMINI_API_KEY'):
            return 'gemini'
        elif os.environ.get('OPENAI_API_KEY'):
            return 'openai'
        return 'local'
    
    @staticmethod
    def is_sensitive_request(message, current_user):
        """
        التحقق من أن الطلب يتعلق بمعلومات سرية
        يعيد: (is_sensitive, requires_owner, response)
        """
        message_lower = message.lower()
        
        # إزالة "ال" التعريف للمقارنة الذكية
        message_normalized = re.sub(r'\bال(\w+)', r'\1', message_lower)
        
        # الكلمات الجذرية للمعلومات السرية (بدون ال التعريف)
        sensitive_roots = [
            'كلمة', 'كلمات', 'مرور', 'سر', 'باسورد', 'password',
            'معلومات', 'بيانات', 'مستخدم', 'مستخدمين', 'user',
            'صلاحيات', 'صلاحية', 'permission', 'role', 'access',
            'مفتاح', 'مفاتيح', 'key', 'token', 'secret',
            'حساب', 'حسابات', 'account'
        ]
        
        # تحليل ذكي: هل الرسالة تحتوي على مجموعة من الكلمات السرية؟
        password_keywords = ['كلمة', 'كلمات', 'مرور', 'سر', 'password', 'pass', 'pwd', 'باسورد']
        user_keywords = ['مستخدم', 'مستخدمين', 'user', 'users', 'معلومات', 'بيانات']
        security_keywords = ['صلاحيات', 'صلاحية', 'permission', 'access', 'role']
        
        # فحص ذكي
        is_about_password = any(kw in message_normalized for kw in password_keywords)
        is_about_users = any(kw in message_normalized for kw in user_keywords)
        is_about_security = any(kw in message_normalized for kw in security_keywords)
        
        # إذا كانت الرسالة عن كلمات المرور أو المستخدمين أو الصلاحيات
        is_sensitive = is_about_password or (is_about_users and len(message_normalized.split()) <= 5) or is_about_security
        
        if is_sensitive:
            # إذا كان المستخدم هو المالك، السماح بالوصول
            if current_user and hasattr(current_user, 'is_owner') and current_user.is_owner:
                return True, True, None
            
            # إذا لم يكن المالك، رفض الوصول
            return True, False, {
                'type': 'warning',
                'message': '🔒 **عذراً، هذه المعلومات سرية**\n\n'
                          'المعلومات التي طلبتها (كلمات المرور، معلومات المستخدمين، الصلاحيات) '
                          'متاحة فقط لمالك النظام.\n\n'
                          'إذا كنت بحاجة للوصول لهذه المعلومات، يرجى التواصل مع مدير النظام.',
                'icon': '🔒'
            }
        
        # ليست معلومات سرية، السماح للجميع
        return False, False, None
    
    @staticmethod
    def _escape_ilike(term: str) -> str:
        """Escape SQL LIKE wildcards in user-provided search terms."""
        return (
            term.replace('\\', '\\\\')
            .replace('%', '\\%')
            .replace('_', '\\_')
        )

    @staticmethod
    def _ilike_contains(column, term: str):
        """Case-insensitive substring match; ESCAPE only when term has LIKE metacharacters."""
        if any(ch in term for ch in ('%', '_', '\\')):
            safe = AIService._escape_ilike(term)
            return column.ilike(f'%{safe}%', escape='\\')
        return column.ilike(f'%{term}%')

    @staticmethod
    def _user_summary(user):
        return {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role.name_ar if user.role else 'لا يوجد',
            'is_active': user.is_active,
            'is_owner': user.is_owner,
        }

    @staticmethod
    def get_user_info_for_owner(username=None):
        """جلب معلومات المستخدم (للمالك فقط) — بدون كشف password_hash."""
        from models import User

        session = db.session
        user_q = session.query(User)

        if username:
            term = username.strip()
            user = user_q.filter(
                or_(User.username == term, User.email == term)
            ).first()
            if not user:
                user = session.query(User).filter(
                    or_(
                        AIService._ilike_contains(User.username, term),
                        AIService._ilike_contains(User.email, term),
                    )
                ).first()

            if not user:
                return {
                    'success': False,
                    'message': f'لم يتم العثور على مستخدم بالاسم: {username}',
                }

            summary = AIService._user_summary(user)
            summary['created_at'] = (
                user.created_at.strftime('%Y-%m-%d') if user.created_at else None
            )
            return {'success': True, 'user': summary}

        users = session.query(User).all()
        return {
            'success': True,
            'users': [AIService._user_summary(u) for u in users],
            'count': len(users),
        }
    
    @staticmethod
    def _get_model(model_cls, pk):
        """Load a model by PK via db.session; ignore leaked Model.query mocks."""
        if pk is None:
            return None
        instance = db.session.get(model_cls, pk)
        if instance is None or not isinstance(instance, model_cls):
            return None
        if getattr(type(instance), '__module__', '').startswith('unittest.mock'):
            return None
        return instance

    @staticmethod
    def recommend_price(product_id, customer_id):
        """توصية السعر الذكي حسب نوع العميل والسجل"""
        from models import Product, Customer, Sale, SaleLine
        
        product = AIService._get_model(Product, product_id)
        customer = AIService._get_model(Customer, customer_id)
        
        if not product or not customer:
            return None
        
        base_price = product.regular_price
        if customer.customer_type == 'merchant':
            base_price = product.get_price_for_customer('merchant')
        elif customer.customer_type == 'partner':
            base_price = product.get_price_for_customer('partner')
        
        last_30_days = datetime.now() - timedelta(days=30)
        avg_sale_price = db.session.query(func.avg(SaleLine.unit_price)).join(Sale).filter(
            SaleLine.product_id == product_id,
            Sale.customer_id == customer_id,
            Sale.created_at >= last_30_days
        ).scalar()
        
        if avg_sale_price and avg_sale_price > 0:
            recommended = (Decimal(str(base_price)) + Decimal(str(avg_sale_price))) / 2
        else:
            recommended = base_price
        
        return {
            'recommended_price': float(recommended),
            'base_price': float(base_price),
            'customer_avg': float(avg_sale_price) if avg_sale_price else None,
            'reason': f'سعر موصى به لـ {customer.name} بناءً على السجل'
        }
    
    @staticmethod
    def check_stock_alert(product_id, quantity):
        """فحص المخزون وإطلاق تنبيهات"""
        from models import Product
        
        product = AIService._get_model(Product, product_id)
        if not product:
            return None
        
        if product.current_stock < quantity:
            return {
                'type': 'error',
                'message': f'⚠️ المخزون غير كافٍ! متوفر: {product.current_stock}, مطلوب: {quantity}'
            }
        
        if product.current_stock - quantity < product.min_stock_alert:
            return {
                'type': 'warning',
                'message': f'⚡ تحذير: المخزون سينخفض لـ {product.current_stock - quantity} (أقل من الحد الأدنى {product.min_stock_alert})'
            }
        
        return None
    
    @staticmethod
    def analyze_customer_behavior(customer_id):
        from functools import lru_cache
        
        @lru_cache(maxsize=100)
        def _cached_analysis(cust_id) -> dict[str, Any] | None:
            from models import Customer, Sale, Payment
            
            customer: Customer = AIService._get_model(Customer, cust_id)
            if not customer:
                return None
            
            return AIService._perform_analysis(customer)
        
        return _cached_analysis(customer_id)
    
    @staticmethod
    def _perform_analysis(customer):
        from models import Sale, Payment
        
        last_90_days = datetime.now(timezone.utc) - timedelta(days=90)

        def _normalize_datetime(value):
            if value is None:
                return None
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        session = db.session
        sales = session.query(Sale).options(
            joinedload(Sale.customer),
            joinedload(Sale.lines)
        ).filter(
            Sale.customer_id == customer.id,
            Sale.created_at != None,  # noqa: E711
            Sale.created_at >= last_90_days
        ).all()
        
        payments = session.query(Payment).filter(
            Payment.customer_id == customer.id,
            Payment.created_at != None,  # noqa: E711
            Payment.created_at >= last_90_days
        ).all()

        normalized_payment_times = []
        for payment in payments:
            normalized_dt = _normalize_datetime(payment.created_at)
            if normalized_dt:
                normalized_payment_times.append((normalized_dt, payment))
        
        total_sales = sum((s.total_amount or 0) for s in sales)
        total_paid = sum((p.amount or 0) for p in payments)
        
        avg_days_to_pay = 0
        if sales and payments:
            pay_delays = []
            for sale in sales:
                sale_created_at = _normalize_datetime(sale.created_at)
                if not sale_created_at:
                    continue

                relevant_payments = [
                    payment_dt for payment_dt, _ in normalized_payment_times
                    if payment_dt >= sale_created_at
                ]

                if relevant_payments:
                    first_payment_dt = min(relevant_payments)
                    try:
                        delay = (first_payment_dt - sale_created_at).days
                    except TypeError:
                        continue
                    pay_delays.append(delay)
            
            if pay_delays:
                avg_days_to_pay = sum(pay_delays) / len(pay_delays)
        
        current_balance = customer.get_balance_aed()
        
        risk_level = 'low'
        if current_balance > total_sales * Decimal('0.5'):
            risk_level = 'high'
        elif current_balance > total_sales * Decimal('0.25'):
            risk_level = 'medium'
        
        return {
            'total_sales_90d': float(total_sales),
            'total_paid_90d': float(total_paid),
            'current_balance': float(current_balance),
            'avg_payment_delay_days': round(avg_days_to_pay, 1),
            'risk_level': risk_level,
            'recommendation': AIService._get_risk_recommendation(risk_level)
        }
    
    @staticmethod
    def _get_risk_recommendation(risk_level):
        """توصيات حسب مستوى المخاطر"""
        recommendations = {
            'low': '✅ عميل ممتاز - يمكن منح ائتمان إضافي',
            'medium': '⚠️ عميل جيد - المتابعة العادية كافية',
            'high': '🔴 عميل عالي المخاطر - يُنصح بالدفع المسبق'
        }
        return recommendations.get(risk_level, 'تحليل غير متوفر')
    
    @staticmethod
    def get_exchange_rate_suggestion(currency, target_date=None):
        """اقتراح سعر الصرف الذكي"""
        from models import Sale

        tid = get_active_tenant_id()

        if not target_date:
            target_date = datetime.now()

        last_7_days = target_date - timedelta(days=7)

        recent_sales = db.session.query(Sale).filter(
            Sale.currency == currency,
            Sale.created_at >= last_7_days,
            Sale.exchange_rate > 0
        )
        if tid is not None:
            recent_sales = recent_sales.filter(Sale.tenant_id == tid)
        recent_sales = recent_sales.order_by(Sale.created_at.desc()).limit(10).all()
        
        if recent_sales:
            avg_rate = sum((s.exchange_rate for s in recent_sales)) / len(recent_sales)
            latest_rate = recent_sales[0].exchange_rate
            
            return {
                'currency': currency,
                'suggested_rate': float(avg_rate),
                'latest_rate': float(latest_rate),
                'source': 'نظام داخلي - متوسط آخر 7 أيام',
                'count': len(recent_sales)
            }
        
        default_rates = {
            'USD': 3.67,
            'EUR': 4.02,
            'AED': 1.0
        }
        
        return {
            'currency': currency,
            'suggested_rate': default_rates.get(currency, 1.0),
            'latest_rate': None,
            'source': 'سعر افتراضي',
            'count': 0
        }
    
    @staticmethod
    def predict_sales_trend(days_ahead=7):
        """🔮 التنبؤ باتجاه المبيعات - Predictive Analytics"""
        from models import Sale

        tid = get_active_tenant_id()

        last_30_days = datetime.now(timezone.utc) - timedelta(days=30)
        sales = db.session.query(Sale).filter(
            Sale.sale_date >= last_30_days,
            Sale.status == 'confirmed'
        )
        if tid is not None:
            sales = sales.filter(Sale.tenant_id == tid)
        sales = sales.all()
        
        if not sales:
            return {'prediction': None, 'confidence': 0, 'message': 'لا توجد بيانات كافية'}
        
        # Calculate daily averages
        daily_sales = {}
        for sale in sales:
            day = sale.sale_date.date()
            if day not in daily_sales:
                daily_sales[day] = Decimal('0')
            daily_sales[day] += sale.amount_aed
        
        days = sorted(daily_sales.keys())
        values = [float(daily_sales[d]) for d in days]
        
        if len(values) < 7:
            return {'prediction': None, 'confidence': 0, 'message': 'بيانات غير كافية (يحتاج 7 أيام)'}
        
        n = len(values)
        x = list(range(n))
        y = values
        
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        slope = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n)) / sum((x[i] - x_mean) ** 2 for i in range(n))
        intercept = y_mean - slope * x_mean
        
        # Predict next days
        predictions = [max(0, slope * (n + i) + intercept) for i in range(1, days_ahead + 1)]
        
        # Calculate R² for confidence
        y_pred = [slope * i + intercept for i in x]
        ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((y[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        trend = 'صاعد 📈' if slope > 0 else 'نازل 📉' if slope < 0 else 'مستقر ➡️'
        
        return {
            'prediction': {
                'daily_avg': round(sum(predictions) / len(predictions), 2),
                'total_predicted': round(sum(predictions), 2),
                'predictions': [round(p, 2) for p in predictions]
            },
            'trend': {'direction': trend, 'slope': round(slope, 2)},
            'confidence': int(r_squared * 100),
            'historical': {'avg_daily': round(y_mean, 2), 'days_analyzed': n}
        }
    
    @staticmethod
    def analyze_profit_margins():
        """💰 تحليل هوامش الربح - Margin Analysis"""
        from models import Sale

        tid = get_active_tenant_id()

        last_30_days = datetime.now(timezone.utc) - timedelta(days=30)
        sales = db.session.query(Sale).filter(
            Sale.sale_date >= last_30_days,
            Sale.status == 'confirmed'
        )
        if tid is not None:
            sales = sales.filter(Sale.tenant_id == tid)
        sales = sales.all()
        
        if not sales:
            return {'success': False, 'message': 'لا توجد مبيعات'}
        
        total_revenue = sum((Decimal(str(s.amount_aed)) for s in sales), Decimal('0'))
        total_cost = Decimal('0')
        
        products_data = {}
        for sale in sales:
            for line in sale.lines:
                pid = line.product_id
                if pid not in products_data:
                    products_data[pid] = {
                        'name': line.product.name if line.product else 'Unknown',
                        'revenue': Decimal('0'),
                        'cost': Decimal('0'),
                        'quantity': Decimal('0')
                    }
                
                cost = Decimal(str(line.cost_price)) * Decimal(str(line.quantity))
                revenue = Decimal(str(line.line_total)) * Decimal(str(sale.exchange_rate))
                
                products_data[pid]['revenue'] += revenue
                products_data[pid]['cost'] += cost
                products_data[pid]['quantity'] += Decimal(str(line.quantity))
                total_cost += cost
        
        total_profit = total_revenue - total_cost
        margin = (total_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0')
        
        products_list = []
        for data in products_data.values():
            if data['revenue'] > 0:
                prod_margin = (data['revenue'] - data['cost']) / data['revenue'] * 100
                products_list.append({
                    'name': data['name'],
                    'revenue': float(data['revenue']),
                    'profit': float(data['revenue'] - data['cost']),
                    'margin': float(prod_margin),
                    'quantity': float(data['quantity'])
                })
        
        products_list.sort(key=lambda x: x['profit'], reverse=True)
        
        return {
            'success': True,
            'overall': {
                'revenue': float(total_revenue),
                'cost': float(total_cost),
                'profit': float(total_profit),
                'margin': float(margin)
            },
            'top_profitable': products_list[:10],
            'least_profitable': products_list[-5:]
        }
    
    @staticmethod
    def detect_sales_patterns():
        """🔍 كشف الأنماط - Pattern Detection"""
        from models import Sale

        tid = get_active_tenant_id()

        last_90_days = datetime.now(timezone.utc) - timedelta(days=90)
        sales = db.session.query(Sale).filter(
            Sale.sale_date >= last_90_days,
            Sale.status == 'confirmed'
        )
        if tid is not None:
            sales = sales.filter(Sale.tenant_id == tid)
        sales = sales.all()
        
        if len(sales) < 10:
            return {'success': False, 'message': 'بيانات غير كافية'}
        
        # تحليل زمني
        weekday_sales = {i: {'count': 0, 'total': Decimal('0')} for i in range(7)}
        hour_sales = {i: {'count': 0, 'total': Decimal('0')} for i in range(24)}
        
        for sale in sales:
            weekday = sale.sale_date.weekday()
            hour = sale.sale_date.hour
            
            weekday_sales[weekday]['count'] += 1
            weekday_sales[weekday]['total'] += Decimal(str(sale.amount_aed))
            hour_sales[hour]['count'] += 1
            hour_sales[hour]['total'] += Decimal(str(sale.amount_aed))
        
        best_day = max(weekday_sales.items(), key=lambda x: x[1]['total'])
        peak_hour = max(hour_sales.items(), key=lambda x: x[1]['count'])
        
        days_ar = ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
        
        return {
            'success': True,
            'best_day': {
                'day': days_ar[best_day[0]],
                'sales': float(best_day[1]['total']),
                'count': best_day[1]['count']
            },
            'peak_hour': {'hour': f"{peak_hour[0]}:00", 'count': peak_hour[1]['count']}
        }
    
    @staticmethod
    def analyze_inventory_health(tenant_id=None):
        """📦 تحليل صحة المخزون — يستوجب tenant_id للعزل البيني"""
        from models import Product
        
        q = db.session.query(Product).filter(Product.is_active == True)
        if tenant_id:
            q = q.filter(Product.tenant_id == int(tenant_id))
        products = q.all()
        
        if not products:
            return {'success': False, 'message': 'لا توجد منتجات'}
        
        out = sum(1 for p in products if p.current_stock <= 0)
        low = sum(1 for p in products if 0 < p.current_stock <= p.min_stock_alert)
        good = sum(1 for p in products if p.current_stock > p.min_stock_alert)
        
        health_score = int((good / len(products)) * 100)
        
        return {
            'success': True,
            'summary': {
                'total': len(products),
                'out': out,
                'low': low,
                'good': good
            },
            'health_score': health_score,
            'rating': 'ممتاز' if health_score >= 80 else 'جيد' if health_score >= 60 else 'مقبول' if health_score >= 40 else 'ضعيف'
        }
    
    @staticmethod
    def chat_response(message, context=None):
        """🤖 أزاد يرد على سؤالك - تعاون متكامل بين المحلي وGroq"""
        from ai_knowledge.agents.intelligent_assistant import intelligent_assistant

        ctx = context or {}
        current_user = ctx.get('current_user')
        user_id = current_user.id if current_user else None

        local_result = intelligent_assistant.process(message, user_id, context)
        local_response = local_result.get('response', '')

        force_local = ctx.get('force_local', False)
        knowledge_context = '' if force_local else AIService._gather_relevant_knowledge(message, local_result)

        system_context = ''
        try:
            from ai_knowledge.system_knowledge import search_knowledge
            role_slug = current_user.role.slug if current_user and getattr(current_user, 'role', None) else None
            sys_ctx = search_knowledge(message)
            if sys_ctx:
                ctx_text = '\n'.join(
                    str(item.get('name') or item.get('code') or item.get('type') or item)
                    for item in sys_ctx[:20]
                )
                system_context = '\n📘 **معلومات النظام:**\n' + ctx_text[:2000]
        except Exception:
            pass
        
        # ========== المرحلة 2: مسار التنفيذ المباشر (للأوامر الواضحة) ==========
        try:
            from ai_knowledge.action_dispatcher import action_dispatcher
            parsed = action_dispatcher.parse_chat_action(message)
            if parsed:
                action_type, args = parsed
                result = action_dispatcher.dispatch(action_type, args)
                if result.success:
                    return f"{result.message}\n\n<sub>🤖 المصدر: محرك التنفيذ الذكي</sub>"
        except Exception:
            pass
        
        # ========== المرحلة 3: مسار المعرفة المضمنة (للأسئلة المعرفية) ==========
        try:
            from ai_knowledge.agents_core import ask_azad_enhanced
            fast_path = ask_azad_enhanced(message, user_id=user_id)
            if fast_path and fast_path.get('answer') and fast_path.get('source') != 'local':
                return f"{fast_path['answer']}\n\n<sub>🤖 المصدر: GROQ API + معرفة النظام</sub>"
        except Exception:
            pass
        
        # ========== المرحلة 4: التعاون مع Groq ==========
        api_key = AIService.get_api_key()
        use_groq = api_key and not force_local
        
        if use_groq:
            try:
                import requests
                import json
                
                # تحديد المزود والنموذج
                provider = AIService.get_provider()
                
                if provider == 'groq':
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    model = "llama-3.3-70b-versatile"
                elif provider == 'gemini':
                    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
                    model = "gemini-2.0-flash-exp"
                else:  # openai
                    url = "https://api.openai.com/v1/chat/completions"
                    model = "gpt-4"
                
                # بناء البرومبت مع معرفة النظام الشاملة
                role_slug = current_user.role.slug if current_user and getattr(current_user, 'role', None) else 'user'
                expert_prompt = f"""أنت أزاد - مساعد ذكي خبير لنظام إدارة كراجات وورش المعدات الثقيلة.

دور المستخدم: {role_slug}

السؤال:
{message}

📊 بيانات النظام الحالية:
{knowledge_context}
{system_context}

🎯 قدراتك:
1. قراءة وتحليل البيانات (Users, Customers, Products, Sales, Purchases, Expenses, Payments, Cheques)
2. إنشاء وتحديث السجلات (عملاء، منتجات، فواتير بيع وشراء، مصروفات، مدفوعات، موردين، موظفين)
3. تحليلات وتقارير مالية متقدمة (إيرادات، أرباح، هوامش، تكاليف)
4. استشارات فنية ومحاسبية متخصصة
5. شؤون الموظفين وحساباتهم
6. إدارة المخزون ومستويات التخزين

📝 تنفيذ الأوامر مباشرة:
إذا طلب المستخدم إنشاء/إضافة شيء، ردّ بصيغة JSON التالية وسيتم التنفيذ مباشرة:

لإنشاء عميل:
  {{"action": "create_customer", "data": {{"name": "الاسم", "phone": "الهاتف", "email": "", "address": "العنوان", "customer_type": "regular"}}, "message": "جاري إنشاء العميل..."}}

لإنشاء منتج:
  {{"action": "create_product", "data": {{"name": "اسم المنتج", "sku": "الرقم", "price": 0, "cost_price": 0, "stock": 0}}, "message": "جاري إنشاء المنتج..."}}

لإنشاء فاتورة:
  {{"action": "create_sale", "data": {{"customer_name": "اسم العميل", "products": [{{"name": "منتج1", "quantity": 1}}], "payment_method": "cash"}}, "message": "جاري إنشاء الفاتورة..."}}

لاستلام دفعة:
  {{"action": "receive_payment", "data": {{"customer_name": "اسم العميل", "amount": 0, "method": "cash"}}, "message": "جاري استلام الدفعة..."}}

لتسجيل مصروف:
  {{"action": "add_expense", "data": {{"description": "الوصف", "amount": 0}}, "message": "جاري تسجيل المصروف..."}}

لإنشاء مورد:
  {{"action": "create_supplier", "data": {{"name": "الاسم", "phone": "الهاتف"}}, "message": "جاري إنشاء المورد..."}}

لإنشاء موظف:
  {{"action": "create_employee", "data": {{"name": "الاسم", "phone": "الهاتف", "salary": 0}}, "message": "جاري إنشاء الموظف..."}}

⚠️ مهم: إذا سأل عن بيانات - استخدم الأرقام الموجودة. إذا سأل عن واجهة النظام أو جداوله - أخبره بناءً على المعلومات أعلاه. إذا طلب شيئاً خارج قدراتك - أخبره أنك لا تستطيع."""

                response = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "user", "content": expert_prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    },
                    timeout=20
                )
                
                if response.status_code == 200:
                    result = response.json()
                    groq_response = result['choices'][0]['message']['content']
                    
                    # فحص إذا Groq يطلب تنفيذ action
                    action_result = AIService._execute_ai_action(groq_response, user_id)
                    if action_result:
                        groq_response = action_result
                    
                    # Groq يدرب المحلي
                    try:
                        AIService._train_local_from_groq(message, str(local_response), str(groq_response), user_id)
                    except Exception as e:
                        logger.debug('Training skipped: %s', e)
                    
                    provider = AIService.get_provider()
                    return f"{groq_response}\n\n<sub>🤖 المصدر: {provider.upper()} API + التحليل المحلي</sub>"
            
            except Exception as e:
                logger.warning('Groq collaboration failed: %s', e)
                try:
                    from services.logging_core import LoggingCore
                    LoggingCore.log_error(
                        message=str(e), category="AI", source="services.ai_service.chat_response", level="ERROR", exception=e
                    )
                except Exception:
                    pass
        
        return f"{local_response}\n\n<sub>💻 المصدر: النظام المحلي الذكي</sub>"
    
    @staticmethod
    def _execute_ai_action(groq_response, user_id):
        """تنفيذ الأوامر التي يطلبها Groq — يستخدم AIExecutor الحقيقي"""
        try:
            import json
            import re
            from flask_login import current_user as flask_user
            from services.ai_executor import AIExecutor
            
            json_match = re.search(r'\{[\s\S]*"action"[\s\S]*\}', groq_response)
            if not json_match:
                return None
            
            action_data = json.loads(json_match.group(0))
            action_type = action_data.get('action', '')
            data = action_data.get('data', {})
            message = action_data.get('message', '')
            
            if not action_type:
                return None

            user = flask_user if flask_user.is_authenticated else None
            ex = AIExecutor(user=user)
            result = None

            if action_type == 'create_customer':
                result = ex.create_customer(
                    name=data.get('name') or data.get('الاسم', ''),
                    phone=data.get('phone') or data.get('الهاتف', ''),
                    email=data.get('email', ''),
                    address=data.get('address') or data.get('العنوان', ''),
                    customer_type=data.get('customer_type', 'regular'),
                )
            elif action_type == 'create_product':
                result = ex.create_product(
                    name=data.get('name') or data.get('الاسم', ''),
                    sku=data.get('sku') or data.get('رقم_القطعة', ''),
                    regular_price=float(data.get('price') or data.get('سعر', 0)),
                    cost_price=float(data.get('cost_price', 0)),
                    current_stock=float(data.get('stock') or data.get('الكمية', 0)),
                    unit=data.get('unit', 'piece'),
                )
            elif action_type == 'create_sale':
                lines_raw = data.get('lines') or data.get('products', [])
                if isinstance(lines_raw, list) and len(lines_raw) > 0:
                    product_lines = lines_raw
                else:
                    product_lines = [{
                        "name": data.get('product_name') or data.get('اسم_المنتج', ''),
                        "quantity": int(data.get('quantity', 1)),
                    }]
                result = ex.create_sale(
                    customer_name=data.get('customer_name') or data.get('اسم_العميل', ''),
                    product_lines=product_lines,
                    payment_method=data.get('payment_method', 'cash'),
                    paid_amount=float(data.get('paid_amount', data.get('المبلغ', 0))),
                    notes=message,
                )
            elif action_type == 'receive_payment':
                result = ex.receive_payment(
                    customer_name=data.get('customer_name') or data.get('اسم_العميل', ''),
                    amount=float(data.get('amount') or data.get('المبلغ', 0)),
                    method=data.get('method') or data.get('طريقة_الدفع', 'cash'),
                )
            elif action_type == 'add_expense':
                result = ex.add_expense(
                    description=data.get('description') or data.get('الوصف', ''),
                    amount=float(data.get('amount') or data.get('المبلغ', 0)),
                    payment_method=data.get('payment_method', 'cash'),
                )
            elif action_type == 'create_supplier':
                result = ex.create_supplier(
                    name=data.get('name') or data.get('الاسم', ''),
                    phone=data.get('phone') or data.get('الهاتف', ''),
                    email=data.get('email', ''),
                )
            elif action_type == 'create_employee':
                result = ex.create_employee(
                    name=data.get('name') or data.get('الاسم', ''),
                    phone=data.get('phone') or data.get('الهاتف', ''),
                    basic_salary=float(data.get('salary') or data.get('الراتب', 0)),
                )

            if result and result.get('success'):
                return f"{result['message']}\n\n<sub>🤖 تم التنفيذ بواسطة أزاد</sub>"
            elif result:
                return f"⚠️ {result.get('message', 'حدث خطأ أثناء التنفيذ')}\n\n<sub>🤖 أزاد</sub>"
            
            return None
            
        except Exception as e:
            logger.warning('Action execution error: %s', e)
            try:
                from services.logging_core import LoggingCore
                LoggingCore.log_error(message=str(e), category="AI", source="services.ai_service._execute_ai_action", level="WARNING", exception=e)
            except Exception:
                pass
            return f"⚠️ حدث خطأ أثناء تنفيذ العملية: {str(e)[:100]}"
    
    @staticmethod
    def _train_local_from_groq(question, local_answer, groq_answer, user_id):
        """Groq يدرب ويحدث النظام المحلي"""
        try:
            from ai_knowledge.core.learning_system import learning_system
            
            learning_data = {
                'question': question,
                'local_answer': local_answer,
                'improved_answer': groq_answer,
                'timestamp': datetime.now().isoformat(),
                'user_id': user_id
            }
            
            learning_system.learn_from_groq_feedback(learning_data)
            
        except Exception as e:
            logger.debug('Training from Groq failed: %s', e)
    
    @staticmethod
    def _gather_relevant_knowledge(message, local_result):
        """جمع بيانات شاملة من جميع جداول النظام"""
        try:
            from models import Sale, Customer, Product, User, Payment, Expense, Purchase, Supplier, Cheque, Role
            from extensions import db
            from datetime import datetime, timedelta
            from flask import current_app
            from flask_login import current_user as flask_current_user
            from sqlalchemy import func
            from utils.tenanting import scoped_user_query

            data_parts = []

            ctx_user = None
            if local_result.get('context'):
                ctx_user = local_result.get('context', {}).get('current_user')
            if ctx_user is None and flask_current_user.is_authenticated:
                ctx_user = flask_current_user

            # 📊 إحصائيات الشركة النشطة (User معفى من ORM — scoped يدوياً)
            tid = ctx_user.tenant_id
            users_count = scoped_user_query(ctx_user, exclude_owners=True).count()
            customers_count = db.session.query(Customer).filter_by(is_active=True, tenant_id=tid).count()
            suppliers_count = db.session.query(Supplier).filter_by(is_active=True, tenant_id=tid).count()
            products_count = db.session.query(Product).filter_by(is_active=True, tenant_id=tid).count()
            
            sales_30d = db.session.query(Sale).filter(
                Sale.sale_date >= datetime.now() - timedelta(days=30),
                Sale.tenant_id == tid
            ).count()
            
            purchases_30d = db.session.query(Purchase).filter(
                Purchase.purchase_date >= datetime.now() - timedelta(days=30),
                Purchase.tenant_id == tid
            ).count()
            
            expenses_30d = db.session.query(Expense).filter(
                Expense.expense_date >= datetime.now() - timedelta(days=30),
                Expense.tenant_id == tid
            ).count()
            
            payments_30d = db.session.query(Payment).filter(
                Payment.payment_date >= datetime.now() - timedelta(days=30),
                Payment.tenant_id == tid
            ).count()
            
            cheques_count = db.session.query(Cheque).filter_by(tenant_id=tid).count()
            
            total_sales_amount = db.session.query(func.sum(Sale.total_amount)).filter(
                Sale.sale_date >= datetime.now() - timedelta(days=30),
                Sale.tenant_id == tid
            ).scalar() or 0
            
            total_expenses_amount = db.session.query(func.sum(Expense.amount_aed)).filter(
                Expense.expense_date >= datetime.now() - timedelta(days=30),
                Expense.tenant_id == tid
            ).scalar() or 0
            
            data_parts.append(f"""📊 **بيانات النظام الكاملة:**

👥 الأطراف:
- المستخدمين: {users_count}
- العملاء: {customers_count}
- الموردين: {suppliers_count}

📦 المخزون:
- المنتجات: {products_count}

💰 المعاملات (آخر 30 يوم):
- المبيعات: {sales_30d} فاتورة (إجمالي: {total_sales_amount:.2f} درهم)
- المشتريات: {purchases_30d}
- المصروفات: {expenses_30d} (إجمالي: {total_expenses_amount:.2f} درهم)
- الدفعات: {payments_30d}
- الشيكات: {cheques_count}

💵 الأرباح (30 يوم):
- الربح الصافي: {(total_sales_amount - total_expenses_amount):.2f} درهم""")
            
            # بيانات الشركة
            config = current_app.config
            data_parts.append(f"""📞 **بيانات الشركة:**
- الاسم: {config.get('COMPANY_NAME_AR')}
- الهاتف: {config.get('COMPANY_PHONE')}
- WhatsApp: {config.get('COMPANY_WHATSAPP')}
- العنوان: {config.get('COMPANY_ADDRESS_AR')}""")
            
            # معلومات المستخدم الحالي
            current_user = local_result.get('context', {}).get('current_user')
            if current_user:
                data_parts.append(f"""👤 **المستخدم الحالي:**
- الاسم: {current_user.username}
- الدور: {current_user.role.name_ar if current_user.role else 'غير محدد'}
- Owner: {'نعم' if current_user.is_owner else 'لا'}""")
            
            return '\n\n'.join(data_parts)
        
        except Exception as e:
            return f"خطأ في جمع البيانات: {str(e)}"
    
    @staticmethod
    def generate_business_insights():
        """توليد رؤى الأعمال التلقائية"""
        try:
            from models import Sale, Customer, Product
            from extensions import db
            from datetime import datetime, timedelta

            tid = get_active_tenant_id()

            insights = []

            # رؤية 1: المخزون المنخفض
            low_stock_q = db.session.query(Product).filter(
                Product.is_active == True,
                Product.current_stock <= Product.min_stock_alert
            )
            if tid is not None:
                low_stock_q = low_stock_q.filter(Product.tenant_id == tid)
            low_stock_count = low_stock_q.count()
            
            if low_stock_count > 0:
                insights.append({
                    'type': 'warning',
                    'title': 'تنبيه المخزون',
                    'message': f'يوجد {low_stock_count} منتج بمخزون منخفض',
                    'action': 'تحقق من المستودع',
                    'priority': 'high'
                })
            
            # رؤية 2: العملاء المتأخرين
            hbc_q = db.session.query(Customer).filter(
                Customer.is_active == True
            )
            if tid is not None:
                hbc_q = hbc_q.filter(Customer.tenant_id == tid)
            high_balance_customers = hbc_q.all()
            
            overdue_count = sum(1 for c in high_balance_customers if c.get_balance_aed() > 1000)
            
            if overdue_count > 0:
                insights.append({
                    'type': 'info',
                    'title': 'متابعة المدفوعات',
                    'message': f'{overdue_count} عميل لديهم ذمم أكثر من 1000 درهم',
                    'action': 'تواصل مع العملاء',
                    'priority': 'medium'
                })
            
            # رؤية 3: أداء المبيعات
            today = datetime.now().date()
            today_sales_q = db.session.query(Sale).filter(
                db.func.date(Sale.sale_date) == today
            )
            if tid is not None:
                today_sales_q = today_sales_q.filter(Sale.tenant_id == tid)
            today_sales = today_sales_q.count()
            
            if today_sales == 0:
                insights.append({
                    'type': 'info',
                    'title': 'مبيعات اليوم',
                    'message': 'لا توجد مبيعات اليوم',
                    'action': 'تحفيز المبيعات',
                    'priority': 'low'
                })
            
            return insights
            
        except Exception as e:
            return [{
                'type': 'error',
                'title': 'خطأ',
                'message': f'فشل توليد الرؤى: {str(e)}',
                'action': '',
                'priority': 'low'
            }]
    
    @staticmethod
    def optimize_inventory_levels():
        """تحسين مستويات المخزون"""
        try:
            from models import Product
            from extensions import db
            
            products_to_order = []
            
            # المنتجات التي تحتاج طلب
            low_stock = db.session.query(Product).filter(
                Product.is_active == True,
                Product.current_stock <= Product.min_stock_alert
            ).all()
            
            for product in low_stock:
                order_quantity = (product.min_stock_alert * 3) - product.current_stock
                products_to_order.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'current_stock': float(product.current_stock),
                    'recommended_order': float(order_quantity),
                    'estimated_cost': float(order_quantity * product.cost_price) if product.cost_price else 0
                })
            
            return {
                'success': True,
                'products_to_order': products_to_order,
                'total_products': len(products_to_order)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def contextual_help(page, user_role):
        """مساعدة سياقية حسب الصفحة"""
        help_content = {
            'dashboard': 'لوحة التحكم تعرض إحصائيات شاملة عن النظام',
            'sales': 'صفحة المبيعات لإدارة الفواتير والمبيعات',
            'products': 'إدارة المنتجات والمخزون',
            'customers': 'إدارة العملاء والذمم',
            'warehouse': 'إدارة المستودعات والمخزون'
        }
        
        return {
            'page': page,
            'help': help_content.get(page, 'لا توجد مساعدة متاحة لهذه الصفحة'),
            'user_role': user_role
        }

    @staticmethod
    def deep_business_analysis():
        """تحليل عميق شامل للأعمال"""
        try:
            analysis = AIService.generate_business_insights()
            return {
                'success': True,
                'analysis': analysis,
                'summary': f'تم تحليل {len(analysis)} جانب من أداء النظام',
                'generated_at': datetime.now().isoformat()
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def predict_cash_flow(days=30):
        """توقع التدفق النقدي"""
        try:
            return AIService.predict_cash_flow_neural(months_ahead=max(1, days // 30))
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def smart_pricing_engine(product_id, customer_id, quantity=1):
        """محرك التسعير الذكي"""
        try:
            from models import Product
            product = AIService._get_model(Product, product_id)
            if not product:
                return None
            base_price = float(product.regular_price or 0)
            discount = 0
            if quantity >= 10:
                discount = 0.10
            elif quantity >= 5:
                discount = 0.05
            return {
                'base_price': base_price,
                'quantity': quantity,
                'discount_percentage': discount * 100,
                'discount_amount': round(base_price * quantity * discount, 2),
                'total_before_discount': round(base_price * quantity, 2),
                'total_after_discount': round(base_price * quantity * (1 - discount), 2),
                'unit_price_after_discount': round(base_price * (1 - discount), 2),
                'currency': 'AED'
            }
        except Exception as e:
            return None

    @staticmethod
    def predict_customer_churn():
        """توقع فقدان العملاء"""
        try:
            from models import Customer, Sale
            from datetime import datetime, timedelta
            from extensions import db

            tid = get_active_tenant_id()

            three_months_ago = datetime.now() - timedelta(days=90)
            at_risk = []
            active_customers_q = db.session.query(Customer).filter_by(is_active=True)
            if tid is not None:
                active_customers_q = active_customers_q.filter(Customer.tenant_id == tid)
            active_customers = active_customers_q.all()
            for customer in active_customers:
                last_sale_q = db.session.query(Sale).filter_by(customer_id=customer.id)
                if tid is not None:
                    last_sale_q = last_sale_q.filter(Sale.tenant_id == tid)
                last_sale = last_sale_q\
                    .order_by(Sale.sale_date.desc()).first()
                if last_sale and last_sale.sale_date < three_months_ago:
                    at_risk.append({
                        'customer_id': customer.id,
                        'customer_name': customer.name,
                        'last_purchase': last_sale.sale_date.strftime('%Y-%m-%d'),
                        'days_since_last_purchase': (datetime.now() - last_sale.sale_date).days,
                        'risk_level': 'high' if (datetime.now() - last_sale.sale_date).days > 180 else 'medium'
                    })
            return {
                'success': True,
                'at_risk_customers': at_risk,
                'total_at_risk': len(at_risk),
                'total_customers': len(active_customers),
                'churn_rate_percentage': round(len(at_risk) / max(len(active_customers), 1) * 100, 1)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _local_response(message, context=None):
        """رد محلي ذكي - Backward Compatibility"""
        from ai_knowledge.personality.azad_responses import AzadResponses
        return AzadResponses.smart_response(message, context)
    
    # ========================================================================
    # دوال استخدام جميع وحدات AI - Integration Methods
    # ========================================================================
    
    @staticmethod
    def get_contextual_response(message, user=None, conversation_history=None):
        """
        الحصول على رد ذكي مع فهم السياق
        متكامل مع: ContextEngine + AzadPersonality + DialectManager
        """
        try:
            # فهم السياق
            context_engine = AIService.get_context_engine()
            context = context_engine.build_context(message, user, conversation_history)
            
            # تحديد اللهجة المناسبة
            dialect_manager = AIService.get_dialect_manager()
            detected_dialect = dialect_manager.detect_dialect(message)
            
            # تطبيق الشخصية
            personality = AIService.get_personality()
            response = personality.generate_response(message, context, detected_dialect)
            
            # التعلم من التفاعل
            learning_system = AIService.get_learning_system()
            learning_system.learn_from_interaction(
                question=message,
                response=response,
                user_feedback=None,
                context={'dialect': detected_dialect, 'context': context}
            )
            
            return response
        
        except Exception as e:
            import sys
            import traceback
            sys.stderr.write(f"[AI_ERROR] Failed to process chat message: {e}\n")
            traceback.print_exc()
            try:
                from services.logging_core import LoggingCore
                LoggingCore.log_error(
                    message=str(e),
                    category="AI",
                    source="services.ai_service.process_chat_message",
                    level="ERROR",
                    exception=e
                )
            except Exception:
                pass
            try:
                from ai_knowledge.personality.azad_responses import AzadResponses
                return AzadResponses.get_error_response()
            except Exception:
                return "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى."
    
    @staticmethod
    def analyze_sales_with_predictions(days_ahead=30):
        """تحليل المبيعات مع التوقعات."""
        try:
            trend = AIService.predict_sales_trend(days_ahead=days_ahead)
            from ai_knowledge.analytics.analytics_predictions import SalesAnalytics
            from ai_knowledge.analytics.data_analyzer import DataAnalyzer
            from models import Sale

            tid = get_active_tenant_id()

            last_90_days = datetime.now(timezone.utc) - timedelta(days=90)
            sales_q = db.session.query(Sale).filter(Sale.sale_date >= last_90_days)
            if tid is not None:
                sales_q = sales_q.filter(Sale.tenant_id == tid)
            sales = sales_q.all()
            historical = [float(s.amount_aed or 0) for s in sales]
            predictions = SalesAnalytics.predict_next_month_sales(historical)
            pattern = SalesAnalytics.analyze_sales_pattern(sales)
            deep_insights = DataAnalyzer().analyze_sales_performance(period_days=days_ahead)
            return {
                'historical': historical,
                'predictions': predictions,
                'insights': deep_insights,
                'trend': trend,
            }
        except Exception as e:
            logger.warning('analyze_sales_with_predictions failed: %s', e)
            return {}
    
    @staticmethod
    def optimize_inventory_with_ai():
        """تحسين المخزون بالذكاء الاصطناعي."""
        try:
            return AIService.optimize_inventory_levels()
        except Exception as e:
            logger.warning('optimize_inventory_with_ai failed: %s', e)
            return {}
    
    @staticmethod
    def analyze_profitability():
        """تحليل الربحية الشامل."""
        try:
            return AIService.analyze_profit_margins()
        except Exception as e:
            logger.warning('analyze_profitability failed: %s', e)
            return {}
    
    @staticmethod
    def get_tax_and_customs_info(query):
        """معلومات الضرائب والجمارك."""
        try:
            q = query.lower()
            if 'vat' in q or 'ضريبة' in query:
                return get_tax_info('uae') or get_tax_advice(query)
            if 'customs' in q or 'جمارك' in query:
                return get_customs_advice(query)
            return get_tax_advice(query)
        except Exception as e:
            logger.warning('get_tax_and_customs_info failed: %s', e)
            return {}
    
    @staticmethod
    def get_parts_information(part_query):
        """معلومات قطع الغيار والمعدات."""
        try:
            return get_part_info(part_query)
        except Exception as e:
            logger.warning('get_parts_information failed: %s', e)
            return {}
    
    @staticmethod
    def get_market_insights_report():
        """تقرير رؤى السوق."""
        try:
            return get_market_insights()
        except Exception as e:
            logger.warning('get_market_insights_report failed: %s', e)
            return {}
    
    @staticmethod
    def get_customer_service_response(customer_query):
        """رد خدمة العملاء الذكي."""
        try:
            tip = get_customer_service_tip()
            if customer_query:
                return f'{tip}\n\n(استفسار: {customer_query})'
            return tip
        except Exception as e:
            logger.warning('get_customer_service_response failed: %s', e)
            return 'عذراً، حدث خطأ. يرجى المحاولة مرة أخرى.'

    @staticmethod
    def get_system_guide(topic):
        """دليل استخدام النظام."""
        try:
            return {
                'system_guide': lookup_system_guide(),
                'user_guide': get_guide(topic),
            }
        except Exception as e:
            logger.warning('get_system_guide failed: %s', e)
            return {}
    
    @staticmethod
    def generate_document_with_ai(document_type, data):
        """توليد مستند ذكي."""
        try:
            from ai_knowledge.generation.document_generator import DocumentGenerator

            doc_generator = DocumentGenerator()
            return doc_generator.generate(document_type, data)
        except Exception as e:
            logger.warning('generate_document_with_ai failed: %s', e)
            return None
    
    @staticmethod
    def get_company_information():
        """معلومات الشركة."""
        return COMPANY_INFO
    
    @staticmethod
    def get_system_knowledge(query):
        """المعرفة بالنظام."""
        try:
            return search_knowledge(query)
        except Exception as e:
            logger.warning('get_system_knowledge failed: %s', e)
            return {}
    
    @staticmethod
    def get_advanced_law_info(law_topic):
        """معلومات قانونية متقدمة."""
        try:
            topic = str(law_topic).lower()
            if 'customs' in topic or 'جمارك' in str(law_topic):
                return AdvancedLaws.get_customs_info('uae')
            if 'shipping' in topic or 'شحن' in str(law_topic):
                return AdvancedLaws.get_shipping_info('air')
            return AdvancedLaws.get_tax_info('uae', law_topic)
        except Exception as e:
            logger.warning('get_advanced_law_info failed: %s', e)
            return {}
    
    @staticmethod
    def expand_knowledge_base(new_topic):
        """توسيع قاعدة المعرفة."""
        try:
            from ai_knowledge.expansion.knowledge_expansion import KnowledgeExpander

            expander = KnowledgeExpander()
            return expander.search_knowledge(new_topic)
        except Exception as e:
            logger.warning('expand_knowledge_base failed: %s', e)
            return {}
    
    @staticmethod
    def perform_self_improvement():
        """التحسين الذاتي للمساعد."""
        try:
            from ai_knowledge.improvement.self_improvement import AzadSelfImprovement

            self_improvement = AzadSelfImprovement()
            return self_improvement.analyze_performance()
        except Exception as e:
            logger.warning('perform_self_improvement failed: %s', e)
            return {}

    @staticmethod
    def integrate_with_system(operation_type, data):
        """التكامل مع أنظمة النظام."""
        try:
            from ai_knowledge.core.system_integration import SystemIntegrator

            integrator = SystemIntegrator()
            if operation_type == 'summary':
                return integrator.get_system_summary()
            return integrator.search_data(str(data), data_type=operation_type)
        except Exception as e:
            logger.warning('integrate_with_system failed: %s', e)
            return {}
    
    @staticmethod
    def get_global_knowledge(query):
        """المعرفة العالمية والتحديثات."""
        try:
            from ai_knowledge.expansion.global_knowledge import GlobalKnowledgeConnector

            global_connector = GlobalKnowledgeConnector()
            return global_connector.fetch_knowledge(query)
        except Exception as e:
            logger.warning('get_global_knowledge failed: %s', e)
            return {}
    
    @staticmethod
    def get_beginners_help(topic):
        """مساعدة المبتدئين."""
        try:
            from ai_knowledge.personality.beginners_mode import BeginnersGuide

            beginners_guide = BeginnersGuide()
            return beginners_guide.get_help(topic)
        except Exception as e:
            logger.warning('get_beginners_help failed: %s', e)
            return {}
    
    @staticmethod
    def check_security_compliance(operation):
        """
        التحقق من الامتثال الأمني
        متكامل مع: SecurityRules
        """
        try:
            security = AIService.get_security_rules()
            is_compliant, warnings = security.check_compliance(operation)
            return {'compliant': is_compliant, 'warnings': warnings}
        
        except Exception as e:
            return {'compliant': True, 'warnings': []}
    
    # ========================================================================
    # دوال الشبكات العصبية المتقدمة - Neural Networks
    # ========================================================================
    
    @staticmethod
    def predict_price_with_neural(product_id, customer_id, quantity=1):
        """
        توقع السعر باستخدام الشبكات العصبية
        دقة عالية جداً (95%+)
        """
        try:
            from models import Product, Customer
            from extensions import db
            
            product = AIService._get_model(Product, product_id)
            customer = AIService._get_model(Customer, customer_id)
            
            if not product:
                return {'error': 'Product not found'}
            
            neural = AIService.get_neural_engine()
            
            result = neural.predict_optimal_price(
                cost_price=float(product.cost_price),
                quantity=quantity,
                customer_type=customer.customer_type if customer else 'regular',
                category_id=product.category_id or 0
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Neural price prediction failed: {e}")
            return AIService.recommend_price(product_id, customer_id)  # Fallback
    
    @staticmethod
    def forecast_sales_neural(days_ahead=7):
        """توقع المبيعات باستخدام Neural Network"""
        try:
            from flask import current_app
            
            neural = AIService.get_neural_engine()
            forecast = neural.forecast_sales(days_ahead, from_app_context=current_app.app_context)
            
            return forecast
        
        except Exception as e:
            logger.error(f"Neural sales forecast failed: {e}")
            return {}
    
    @staticmethod
    def detect_fraud_neural(sale_data):
        """كشف الاحتيال باستخدام Neural Network"""
        try:
            neural = AIService.get_neural_engine()
            result = neural.detect_fraud(sale_data)
            
            return result
        
        except Exception as e:
            logger.error(f"Neural fraud detection failed: {e}")
            return {'is_fraud': False, 'risk_score': 0}
    
    @staticmethod
    def classify_customer_neural(customer_id):
        """تصنيف العميل باستخدام Neural Network"""
        try:
            from flask import current_app
            
            neural = AIService.get_neural_engine()
            classification = neural.classify_customer_intelligence(
                customer_id,
                from_app_context=current_app.app_context
            )
            
            return classification
        
        except Exception as e:
            logger.error(f"Neural customer classification failed: {e}")
            return {}
    
    @staticmethod
    def optimize_inventory_neural(product_id):
        """تحسين المخزون باستخدام Neural Network"""
        try:
            from flask import current_app
            
            neural = AIService.get_neural_engine()
            optimization = neural.optimize_stock_level(
                product_id,
                from_app_context=current_app.app_context
            )
            
            return optimization
        
        except Exception as e:
            logger.error(f"Neural inventory optimization failed: {e}")
            return {}
    
    @staticmethod
    def predict_maintenance_neural(product_id):
        """توقع احتياجات الصيانة باستخدام Neural Network"""
        try:
            from flask import current_app
            
            neural = AIService.get_neural_engine()
            prediction = neural.predict_maintenance_needs(
                product_id,
                from_app_context=current_app.app_context
            )
            
            return prediction
        
        except Exception as e:
            logger.error(f"Neural maintenance prediction failed: {e}")
            return {}
    
    @staticmethod
    def predict_cash_flow_neural(months_ahead=3):
        """توقع التدفق النقدي باستخدام Neural Network"""
        try:
            from flask import current_app
            
            neural = AIService.get_neural_engine()
            prediction = neural.predict_cash_flow(
                months_ahead,
                from_app_context=current_app.app_context
            )
            
            return prediction
        
        except Exception as e:
            logger.error(f"Neural cash flow prediction failed: {e}")
            return {}
    
    @staticmethod
    def train_all_neural_models():
        """
        تدريب جميع النماذج العصبية
        يستغرق 5-10 دقائق حسب حجم البيانات
        """
        try:
            from flask import current_app
            
            neural = AIService.get_neural_engine()
            results = neural.train_all_models(from_app_context=current_app.app_context)
            
            return results
        
        except Exception as e:
            logger.error(f"Neural training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_neural_status():
        """الحصول على حالة النماذج العصبية"""
        try:
            neural = AIService.get_neural_engine()
            status = neural.get_status()
            
            return status
        
        except Exception as e:
            logger.error(f"Failed to get neural status: {e}")
            return {'trained_models': 0, 'total_models': 0}
    
    # ========================================================================
    # Advanced Capabilities - القدرات المتقدمة
    # ========================================================================
    
    @staticmethod
    def think_deeply(problem: str, context: dict | None = None):
        """
        التفكير العميق في مشكلة - DeepSeek Style
        استخدام محرك التفكير المنطقي
        """
        try:
            reasoning = AIService.get_reasoning_engine()
            result = reasoning.think(problem, context)
            
            return result
        
        except Exception as e:
            logger.error(f"Deep thinking failed: {e}")
            return {}
    
    @staticmethod
    def delegate_to_expert(task: str, context: dict | None = None):
        """
        تفويض المهمة للخبير المناسب
        استخدام نظام الوكلاء المتعددين
        """
        try:
            coordinator = AIService.get_agent_coordinator()
            result = coordinator.delegate_task(task, context)
            
            return result
        
        except Exception as e:
            logger.error(f"Task delegation failed: {e}")
            return {}
    
    @staticmethod
    def generate_code(code_type: str, purpose: str, params: dict | None = None):
        """
        توليد كود تلقائياً
        SQL / Python / JavaScript
        """
        try:
            generator = AIService.get_code_generator()

            params = params or {}

            if code_type == 'sql':
                code = generator.generate_sql_query(
                    params.get('intent', 'select'),
                    params.get('table', ''),
                    params.get('filters')
                )
            elif code_type == 'python':
                code = generator.generate_python_function(
                    params.get('name', 'my_function'),
                    purpose,
                    params.get('params', [])
                )
            else:
                code = "# Unsupported code type"
            
            return {
                'code': code,
                'type': code_type,
                'purpose': purpose
            }
        
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            return {}
    
    @staticmethod
    def remember_conversation(user_id: int, message: str, response: str):
        """حفظ محادثة في الذاكرة طويلة المدى"""
        try:
            memory = AIService.get_memory_system()
            memory.remember_conversation(user_id, message, response)
            
            return {'status': 'remembered'}
        
        except Exception as e:
            logger.error(f"Memory failed: {e}")
            return {}
    
    @staticmethod
    def recall_conversations(user_id: int, limit=10):
        """استرجاع محادثات سابقة"""
        try:
            memory = AIService.get_memory_system()
            conversations = memory.recall_conversations(user_id, limit)
            
            return conversations
        
        except Exception as e:
            return []
    
    @staticmethod
    def chat(user_id: int, message: str):
        """
        محادثة طبيعية متقدمة
        ChatGPT-style conversation
        """
        try:
            manager = AIService.get_conversation_manager()
            response = manager.process_message(user_id, message)
            
            return response
        
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return {'response': 'عذراً، حدث خطأ'}
    
    @staticmethod
    def self_reflect():
        """
        التأمل الذاتي والتحسين
        """
        try:
            reflection = AIService.get_reflection_engine()
            assessment = reflection.reflect_on_performance()
            
            return assessment
        
        except Exception as e:
            return {}
    
    @staticmethod
    def read_invoice_image(image_path: str):
        """قراءة فاتورة من صورة - OCR"""
        try:
            vision = AIService.get_vision_processor()
            data = vision.read_invoice_image(image_path)
            
            return data
        
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_system_capabilities():
        """
        الحصول على قائمة كاملة بقدرات النظام
        """
        return {
            'neural_networks': {
                'available': True,
                'models': 11,
                'capabilities': [
                    'Price Optimization',
                    'Sales Forecasting',
                    'Customer Classification',
                    'Fraud Detection',
                    'Inventory Optimization',
                    'Demand Prediction',
                    'Financial Planning',
                    'Maintenance Prediction',
                    'Accounting Validation',
                    'Profit Optimization',
                    'Churn Prediction'
                ]
            },
            'reasoning': {
                'available': True,
                'types': [
                    'Deep Thinking',
                    'Chain of Thought',
                    'Mathematical Reasoning',
                    'Financial Reasoning',
                    'Technical Reasoning',
                    'Business Reasoning'
                ]
            },
            'memory': {
                'available': True,
                'types': [
                    'Episodic Memory (Conversations)',
                    'Semantic Memory (Facts)',
                    'Procedural Memory (How-to)',
                    'User Preferences'
                ]
            },
            'code_generation': {
                'available': True,
                'languages': ['SQL', 'Python', 'JavaScript']
            },
            'multi_agent': {
                'available': True,
                'agents': [
                    'Sales Agent',
                    'Accounting Agent',
                    'Inventory Agent',
                    'Maintenance Agent',
                    'Customer Agent',
                    'Financial Agent',
                    'Security Agent'
                ]
            },
            'conversation': {
                'available': True,
                'features': [
                    'Context Awareness',
                    'Natural Responses',
                    'Multi-turn Dialogs',
                    'Intent Recognition'
                ]
            },
            'vision': {
                'available': True,
                'features': ['Invoice OCR', 'Part Recognition']
            },
            'self_improvement': {
                'available': True,
                'features': [
                    'Performance Monitoring',
                    'Error Learning',
                    'Self-Reflection',
                    'Continuous Improvement'
                ]
            },
            'master_brain': {
                'available': True,
                'description': 'العقل الموحد الخارق - يجمع كل القدرات',
                'features': [
                    'Unified Intelligence',
                    'Lightning Fast Response',
                    'Complete Knowledge Base',
                    'Genius-Level Reasoning',
                    'Expert in All Domains'
                ],
                'domains': [
                    'محاسبة وضرائب',
                    'إدارة مالية',
                    'هندسة وصيانة',
                    'إدارة مخزون',
                    'قانون تجاري',
                    'برمجة وتقنية',
                    'سكرتارية تنفيذية'
                ]
            }
        }
    
    # ========================================================================
    # العقل الموحد الخارق - Master Brain Integration
    # ========================================================================
    
    @staticmethod
    def ask_genius(question: str, context: dict | None = None, user_id: int | None = None):
        """
        اسأل العبقري - الواجهة الموحدة للعقل الخارق
        
        هذه الدالة الواحدة تجمع كل القدرات:
        - 11 نموذج عصبي
        - 8 أنواع تفكير منطقي
        - 7 وكلاء متخصصين
        - قواعد معرفة شاملة
        - ذاكرة موحدة
        - سرعة فائقة
        
        Args:
            question: اسأل أي سؤال!
            context: السياق (اختياري)
            user_id: المستخدم (اختياري)
        
        Returns:
            إجابة شاملة بثقة عالية
        
        مثال:
            result = AIService.ask_genius("ما هي ضريبة القيمة المضافة؟")
            print(result['answer'])
        """
        try:
            brain = AIService.get_master_brain()
            return brain.ask(question, context, user_id)
        
        except Exception as e:
            logger.error(f"Genius query failed: {e}")
            return {'answer': 'عذراً، حدث خطأ. يرجى المحاولة مرة أخرى.', 'confidence': 0}
    
    @staticmethod
    def quick_calculate(formula: str, **params):
        """
        حسابات سريعة للصيغ الشائعة
        
        الصيغ المتاحة:
        - gross_margin: هامش الربح الإجمالي
        - net_margin: هامش الربح الصافي
        - current_ratio: نسبة السيولة الجارية
        - eoq: الكمية الاقتصادية للطلب
        - break_even: نقطة التعادل
        - vat: ضريبة القيمة المضافة
        - price_with_vat: السعر مع الضريبة
        - price_without_vat: السعر بدون الضريبة
        
        مثال:
            result = AIService.quick_calculate('vat', amount=1000)
            # النتيجة: {'result': 50.0, 'success': True}
        """
        try:
            brain = AIService.get_master_brain()
            return brain.quick_calc(formula, **params)
        
        except Exception as e:
            return {'error': str(e), 'success': False}
    
    @staticmethod
    def explain_anything(concept: str):
        """
        اشرح أي مفهوم
        
        مثال:
            explanation = AIService.explain_anything('مبدأ الاستحقاق')
        """
        try:
            brain = AIService.get_master_brain()
            return brain.explain(concept)
        
        except Exception as e:
            return f"عذراً، لم أتمكن من الشرح: {e}"
    
    @staticmethod
    def validate_entry(debit: float, credit: float):
        """
        التحقق من القيد المحاسبي
        
        مثال:
            result = AIService.validate_entry(5000, 5000)
            # النتيجة: {'is_balanced': True, 'status': '✅ متوازن'}
        """
        try:
            brain = AIService.get_master_brain()
            return brain.validate_accounting_entry(debit, credit)
        
        except Exception as e:
            return {'error': str(e), 'is_balanced': False}
    
    # ========================================================================
    # Transformers - معمارية المحولات المتقدمة
    # ========================================================================
    
    @staticmethod
    def understand_with_transformers(text: str):
        """
        فهم النص باستخدام Transformers
        
        يستخدم:
        - Self-Attention
        - Multi-Head Attention
        - Positional Encoding
        - Feed-Forward Networks
        
        مثال:
            result = AIService.understand_with_transformers("ما هي ضريبة القيمة المضافة؟")
        """
        try:
            transformers = AIService.get_transformers_brain()
            understanding = transformers.understand(text)
            
            return understanding
        
        except Exception as e:
            logger.error(f"Transformers understanding failed: {e}")
            return {}
    
    @staticmethod
    def generate_with_transformers(prompt: str, max_length: int = 50):
        """
        توليد رد باستخدام Transformers
        
        مثال:
            response = AIService.generate_with_transformers("اشرح الضرائب")
        """
        try:
            transformers = AIService.get_transformers_brain()
            response = transformers.generate_response(prompt, max_length)
            
            return response
        
        except Exception as e:
            logger.error(f"Transformers generation failed: {e}")
            return "عذراً، حدث خطأ"
    
    @staticmethod
    def analyze_attention(text: str):
        """
        تحليل خريطة الانتباه
        
        يوضح أي كلمة تنتبه لأي كلمة أخرى
        
        مثال:
            attention = AIService.analyze_attention("قيد مدين دائن")
        """
        try:
            transformers = AIService.get_transformers_brain()
            understanding = transformers.understand(text)
            
            return {
                'attention_map': understanding.get('attention_map', {}),
                'tokens': understanding.get('tokens', []),
                'visualization': 'خريطة الانتباه جاهزة'
            }
        
        except Exception as e:
            return {}
    
    # ========================================================================
    # كمبيوترات السيارات - Automotive ECU Expert
    # ========================================================================
    
    @staticmethod
    def diagnose_obd_code(code: str):
        """
        تشخيص كود OBD-II
        
        مثال:
            result = AIService.diagnose_obd_code('P0420')
        """
        try:
            ecu_expert = get_automotive_ecu_knowledge()
            diagnosis = ecu_expert.diagnose_code(code)
            
            return diagnosis
        
        except Exception as e:
            return {'error': str(e), 'found': False}
    
    @staticmethod
    def get_sensor_info(sensor_name: str):
        """
        معلومات عن حساس محدد
        
        مثال:
            info = AIService.get_sensor_info('MAF')
        """
        try:
            ecu_expert = get_automotive_ecu_knowledge()
            info = ecu_expert.get_sensor_info(sensor_name)
            
            return info
        
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_ecu_knowledge(ecu_type: str):
        """
        الحصول على معرفة ECU محددة
        
        مثال:
            info = AIService.get_ecu_knowledge('engine_ecu')
        """
        try:
            ecu_expert = get_automotive_ecu_knowledge()
            info = ecu_expert.get_ecu_info(ecu_type)
            
            return info
        
        except Exception as e:
            return {}
    
    # ========================================================================
    # التعلم الخارجي - External Learning
    # ========================================================================
    
    @staticmethod
    def get_learning_sources():
        """مصادر التعلم الخارجية."""
        try:
            from ai_knowledge.learning.external_learning import get_external_learning

            learning = get_external_learning()
            sources = learning.get_knowledge_sources_list()
            stats = learning.get_statistics()
            return {
                'sources': sources,
                'total_sources': len(sources),
                'statistics': stats,
            }
        except Exception as e:
            logger.warning('get_learning_sources failed: %s', e)
            return {'sources': [], 'error': str(e)}
    
    @staticmethod
    def learn_from_external(source_type: str, topic: str, content: str):
        """التعلم من مصدر خارجي."""
        try:
            from ai_knowledge.learning.external_learning import get_external_learning

            learning = get_external_learning()
            return learning.learn_from_source(source_type, topic, content)
        except Exception as e:
            logger.warning('learn_from_external failed: %s', e)
            return {'success': False, 'error': str(e)}
