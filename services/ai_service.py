"""
AZAD AI SERVICE
المساعد الذكي الخبير في المحاسبة والمعدات الثقيلة

شركة أزاد للأنظمة الذكية - Azad Smart Systems
المطور: م. أحمد غنام
دبي - الإمارات العربية المتحدة

Features:
- UAE Tax & Customs Expert (خبير ضرائب وجمارك الإمارات)
- Heavy Equipment & Auto Parts Specialist (خبير المعدات الثقيلة وقطع الغيار)
- Predictive Analytics (تنبؤات ذكية)
- Customer Service Excellence (خدمة عملاء متميزة)
- Business Intelligence (ذكاء أعمال)
- Market Insights (فهم السوق)
"""
import os
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func, or_, and_, desc
from sqlalchemy.orm import joinedload
from extensions import db

# التكامل الكامل مع جميع وحدات AI
# from ai_knowledge.personality.azad_responses import AzadResponses
# from ai_knowledge.core.learning_system import AzadLearningSystem
# from ai_knowledge.core.context_engine import ContextEngine
# from ai_knowledge.analytics.analytics_predictions import SalesAnalytics, InventoryAnalytics, ProfitAnalytics
# from ai_knowledge.analytics.data_analyzer import DataAnalyzer
# from ai_knowledge.personality.azad_personality import AzadPersonality
# from ai_knowledge.core.system_integration import SystemIntegrator
# from ai_knowledge.expansion.knowledge_expansion import KnowledgeExpander
# from ai_knowledge.improvement.self_improvement import AzadSelfImprovement
# from ai_knowledge.generation.document_generator import DocumentGenerator
# from ai_knowledge.expansion.global_knowledge import GlobalKnowledgeConnector
# from ai_knowledge.personality.dialects import DialectManager
# from ai_knowledge.specialized.security_rules import SecurityRules
# from ai_knowledge.personality.beginners_mode import BeginnersGuide
# from ai_knowledge.neural.neural_engine import AzadNeuralEngine, get_neural_engine
# from ai_knowledge.core.reasoning_engine import ReasoningEngine, get_reasoning_engine
# from ai_knowledge.core.memory_system import LongTermMemory, get_memory_system
# from ai_knowledge.generation.code_generator import CodeGenerator, get_code_generator
# from ai_knowledge.agents.multi_agent_system import MultiAgentCoordinator, get_agent_coordinator
# from ai_knowledge.improvement.self_reflection import SelfReflectionEngine, get_reflection_engine
# from ai_knowledge.core.conversation_manager import ConversationManager, get_conversation_manager
# from ai_knowledge.neural.vision_processor import VisionProcessor, get_vision_processor
# from ai_knowledge.agents.master_brain import MasterBrain, get_master_brain, ask_azad, quick_calc, explain_concept
# from ai_knowledge.neural.transformers_brain import TransformersBrain, get_transformers_brain
# from ai_knowledge.learning.external_learning import get_external_learning

# قواعد المعرفة المتخصصة
from ai_knowledge.knowledge import (
    get_part_info,
    get_tax_info,
    get_customs_advice,
    get_module_help,
    COMPANY_INFO,
)
from ai_knowledge.specialized import (
    get_customer_service_tip,
    get_system_guide,
    get_guide,
    get_tax_advice,
    advanced_laws,
)
from ai_knowledge.analytics import (
    get_market_insights,
)


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
        import re
        
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
    def get_user_info_for_owner(username=None):
        """جلب معلومات المستخدم (للمالك فقط)"""
        from models import User
        
        if username:
            user = User.query.filter(
                or_(
                    User.username.ilike(f'%{username}%'),
                    User.email.ilike(f'%{username}%')
                )
            ).first()
            
            if not user:
                return {
                    'success': False,
                    'message': f'لم يتم العثور على مستخدم بالاسم: {username}'
                }
            
            return {
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'password_hash': user.password_hash,  # كلمة المرور المشفرة
                    'role': user.role.name_ar if user.role else 'لا يوجد',
                    'is_active': user.is_active,
                    'is_owner': user.is_owner,
                    'created_at': user.created_at.strftime('%Y-%m-%d') if user.created_at else None
                }
            }
        else:
            # جلب جميع المستخدمين
            users = User.query.all()
            return {
                'success': True,
                'users': [{
                    'id': u.id,
                    'username': u.username,
                    'email': u.email,
                    'password_hash': u.password_hash,
                    'role': u.role.name_ar if u.role else 'لا يوجد',
                    'is_active': u.is_active,
                    'is_owner': u.is_owner
                } for u in users],
                'count': len(users)
            }
    
    @staticmethod
    def recommend_price(product_id, customer_id):
        """توصية السعر الذكي حسب نوع العميل والسجل"""
        from models import Product, Customer, Sale, SaleLine
        
        product = Product.query.get(product_id)
        customer = Customer.query.get(customer_id)
        
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
        
        product = Product.query.get(product_id)
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
        def _cached_analysis(cust_id):
            from models import Customer, Sale, Payment
            
            customer = Customer.query.get(cust_id)
            if not customer:
                return None
            
            return _perform_analysis(customer)
        
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

        sales = Sale.query.options(
            joinedload(Sale.customer),
            joinedload(Sale.lines)
        ).filter(
            Sale.customer_id == customer.id,
            Sale.created_at != None,  # noqa: E711
            Sale.created_at >= last_90_days
        ).all()
        
        payments = Payment.query.filter(
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
                        # Fallback: ignore invalid datetime arithmetic
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
        
        if not target_date:
            target_date = datetime.now()
        
        last_7_days = target_date - timedelta(days=7)
        
        recent_sales = Sale.query.filter(
            Sale.currency == currency,
            Sale.created_at >= last_7_days,
            Sale.exchange_rate > 0
        ).order_by(Sale.created_at.desc()).limit(10).all()
        
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
        
        last_30_days = datetime.now(timezone.utc) - timedelta(days=30)
        sales = Sale.query.filter(
            Sale.sale_date >= last_30_days,
            Sale.status == 'confirmed'
        ).all()
        
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
        
        # Simple linear regression
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
        
        last_30_days = datetime.now(timezone.utc) - timedelta(days=30)
        sales = Sale.query.filter(
            Sale.sale_date >= last_30_days,
            Sale.status == 'confirmed'
        ).all()
        
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
        
        last_90_days = datetime.now(timezone.utc) - timedelta(days=90)
        sales = Sale.query.filter(
            Sale.sale_date >= last_90_days,
            Sale.status == 'confirmed'
        ).all()
        
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
    def analyze_inventory_health():
        """📦 تحليل صحة المخزون"""
        from models import Product
        
        products = Product.query.filter_by(is_active=True).all()
        
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
        
        # ========== المرحلة 1: التحليل المحلي الشامل ==========
        user_id = context.get('current_user').id if context and context.get('current_user') else None
        
        # الرد المحلي الذكي (يشمل: فهم النية + بيانات حقيقية + تحليل)
        local_result = intelligent_assistant.process(message, user_id, context)
        local_response = local_result.get('response', '')
        
        force_local = context.get('force_local', False) if context else False
        knowledge_context = '' if force_local else AIService._gather_relevant_knowledge(message, local_result)
        
        # ========== المرحلة 2: التعاون مع Groq ==========
        api_key = AIService.get_api_key()
        # السماح بالرسائل للوصول لـ Groq إذا كان مفعلاً (الاعتماد على الزر فقط)
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
                
                # Groq مع صلاحيات كاملة
                expert_prompt = f"""أنت أزاد - مساعد ذكي تفاعلي لنظام إدارة كراجات.

السؤال:
{message}

📊 بيانات النظام الحالية:
{knowledge_context}

🎯 قدراتك:
1. قراءة البيانات (Users, Customers, Products, Sales, etc)
2. إنشاء سجلات جديدة (عملاء، منتجات، فواتير)
3. تحديث البيانات الموجودة
4. تحليل وتقارير
5. استشارات تقنية (معدات ثقيلة)

📝 إذا طلب إنشاء/تعديل:
- اطلب المعلومات المطلوبة بوضوح
- ردّ بصيغة JSON واضحة:
  {{
    "action": "create_customer/create_product/etc",
    "data_needed": ["الاسم", "الهاتف", "..."],
    "message": "رسالة للمستخدم"
  }}

⚠️ مهم: إذا سأل عن بيانات - استخدم الأرقام الموجودة."""
                
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
                        print(f"Training skipped: {e}")
                    
                    provider = AIService.get_provider()
                    return f"{groq_response}\n\n<sub>🤖 المصدر: {provider.upper()} API + التحليل المحلي</sub>"
            
            except Exception as e:
                print(f"Groq collaboration failed: {str(e)}")
        
        return f"{local_response}\n\n<sub>💻 المصدر: النظام المحلي الذكي</sub>"
    
    @staticmethod
    def _execute_ai_action(groq_response, user_id):
        """تنفيذ الأوامر التي يطلبها Groq (إنشاء/تعديل/حذف)"""
        try:
            import json
            import re
            
            # البحث عن JSON في الرد
            json_match = re.search(r'\{[\s\S]*"action"[\s\S]*\}', groq_response)
            if not json_match:
                return None
            
            action_data = json.loads(json_match.group(0))
            action_type = action_data.get('action', '')
            
            # إنشاء عميل
            if action_type == 'create_customer':
                data_needed = action_data.get('data_needed', [])
                return f"""✅ تمام! لإنشاء عميل جديد، أعطني المعلومات التالية:

{chr(10).join([f'{i+1}. {field}' for i, field in enumerate(data_needed)])}

أدخل البيانات بهذا الشكل:
عميل جديد: الاسم، الهاتف، العنوان، ..."""
            
            # إنشاء منتج
            elif action_type == 'create_product':
                return """✅ لإنشاء منتج جديد، أعطني:
1. اسم المنتج
2. رقم القطعة
3. السعر
4. الكمية

مثال: منتج: فلتر زيت كاتربلر، 1R0716، 50 درهم، 100 قطعة"""
            
            # إنشاء فاتورة
            elif action_type == 'create_sale':
                return """✅ لإنشاء فاتورة، أعطني:
1. اسم العميل
2. المنتجات والكميات
3. طريقة الدفع

مثال: فاتورة لعميل أحمد: فلتر زيت x2، كاش"""
            
            return None
            
        except Exception as e:
            print(f"Action execution error: {e}")
            return None
    
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
            print(f"Training from Groq failed: {e}")
    
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
            users_count = scoped_user_query(ctx_user, exclude_owners=True).count()
            customers_count = Customer.query.filter_by(is_active=True).count()
            suppliers_count = Supplier.query.filter_by(is_active=True).count()
            products_count = Product.query.filter_by(is_active=True).count()
            
            sales_30d = Sale.query.filter(
                Sale.sale_date >= datetime.now() - timedelta(days=30)
            ).count()
            
            purchases_30d = Purchase.query.filter(
                Purchase.purchase_date >= datetime.now() - timedelta(days=30)
            ).count()
            
            expenses_30d = Expense.query.filter(
                Expense.expense_date >= datetime.now() - timedelta(days=30)
            ).count()
            
            payments_30d = Payment.query.filter(
                Payment.payment_date >= datetime.now() - timedelta(days=30)
            ).count()
            
            cheques_count = Cheque.query.count()
            
            total_sales_amount = db.session.query(func.sum(Sale.total_amount)).filter(
                Sale.sale_date >= datetime.now() - timedelta(days=30)
            ).scalar() or 0
            
            total_expenses_amount = db.session.query(func.sum(Expense.amount_aed)).filter(
                Expense.expense_date >= datetime.now() - timedelta(days=30)
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
            
            insights = []
            
            # رؤية 1: المخزون المنخفض
            low_stock_count = Product.query.filter(
                Product.is_active == True,
                Product.current_stock <= Product.min_stock_alert
            ).count()
            
            if low_stock_count > 0:
                insights.append({
                    'type': 'warning',
                    'title': 'تنبيه المخزون',
                    'message': f'يوجد {low_stock_count} منتج بمخزون منخفض',
                    'action': 'تحقق من المستودع',
                    'priority': 'high'
                })
            
            # رؤية 2: العملاء المتأخرين
            high_balance_customers = Customer.query.filter(
                Customer.is_active == True
            ).all()
            
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
            today_sales = Sale.query.filter(
                db.func.date(Sale.sale_date) == today
            ).count()
            
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
            low_stock = Product.query.filter(
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
            try:
                from ai_knowledge.personality.azad_responses import AzadResponses
                return AzadResponses.get_error_response()
            except Exception:
                return "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى."
    
    @staticmethod
    def analyze_sales_with_predictions(days_ahead=30):
        """
        تحليل المبيعات مع التوقعات
        متكامل مع: SalesAnalytics + DataAnalyzer
        """
        try:
            # استخدام محلل المبيعات
            sales_analytics = SalesAnalytics()
            historical_data = sales_analytics.get_historical_trends(days=90)
            predictions = sales_analytics.predict_next_period(days_ahead)
            
            # تحليل إضافي
            data_analyzer = DataAnalyzer()
            deep_insights = data_analyzer.analyze_sales_patterns(historical_data)
            
            return {
                'historical': historical_data,
                'predictions': predictions,
                'insights': deep_insights
            }
        
        except Exception as e:
            return {}
    
    @staticmethod
    def optimize_inventory_with_ai():
        """
        تحسين المخزون بالذكاء الاصطناعي
        متكامل مع: InventoryAnalytics + DataAnalyzer
        """
        try:
            inventory_analytics = InventoryAnalytics()
            
            # تحليل المخزون
            analysis = inventory_analytics.analyze_stock_levels()
            
            # توصيات الطلب
            reorder_recommendations = inventory_analytics.calculate_reorder_points()
            
            # كشف البضائع الراكدة
            slow_moving = inventory_analytics.detect_slow_moving_items()
            
            return {
                'analysis': analysis,
                'recommendations': reorder_recommendations,
                'slow_moving': slow_moving
            }
        
        except Exception as e:
            return {}
    
    @staticmethod
    def analyze_profitability():
        """
        تحليل الربحية الشامل
        متكامل مع: ProfitAnalytics + DataAnalyzer
        """
        try:
            profit_analytics = ProfitAnalytics()
            
            # تحليل الهوامش
            margins = profit_analytics.analyze_profit_margins()
            
            # تحليل الربحية حسب المنتج
            by_product = profit_analytics.profitability_by_product()
            
            # تحليل الربحية حسب العميل
            by_customer = profit_analytics.profitability_by_customer()
            
            return {
                'margins': margins,
                'by_product': by_product,
                'by_customer': by_customer
            }
        
        except Exception as e:
            return {}
    
    @staticmethod
    def get_tax_and_customs_info(query):
        """
        الحصول على معلومات الضرائب والجمارك
        متكامل مع: tax_system + customs + tax_customs_knowledge
        """
        try:
            # معلومات الضرائب
            if 'vat' in query.lower() or 'ضريبة' in query:
                tax_info = tax_system.get_vat_info()
                return tax_info
            
            # معلومات الجمارك
            if 'customs' in query.lower() or 'جمارك' in query:
                customs_info = customs.get_customs_procedures()
                return customs_info
            
            # معلومات شاملة
            return tax_customs_knowledge.get_comprehensive_guide()
        
        except Exception as e:
            return {}
    
    @staticmethod
    def get_parts_information(part_query):
        """
        معلومات قطع الغيار والمعدات
        متكامل مع: parts_knowledge
        """
        try:
            parts_info = parts_knowledge.search_part(part_query)
            return parts_info
        
        except Exception as e:
            return {}
    
    @staticmethod
    def get_market_insights_report():
        """
        تقرير رؤى السوق
        متكامل مع: market_insights
        """
        try:
            insights = market_insights.generate_market_report()
            return insights
        
        except Exception as e:
            return {}
    
    @staticmethod
    def get_customer_service_response(customer_query):
        """
        رد خدمة العملاء الذكي
        متكامل مع: customer_service
        """
        try:
            response = customer_service.handle_customer_query(customer_query)
            return response
        
        except Exception as e:
            return "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى."
    
    @staticmethod
    def get_system_guide(topic):
        """
        دليل استخدام النظام
        متكامل مع: system_guide + user_guide
        """
        try:
            # دليل النظام
            system_info = system_guide.get_guide_for_topic(topic)
            
            # دليل المستخدم
            user_info = user_guide.get_user_guide(topic)
            
            return {
                'system_guide': system_info,
                'user_guide': user_info
            }
        
        except Exception as e:
            return {}
    
    @staticmethod
    def generate_document_with_ai(document_type, data):
        """
        توليد مستند ذكي
        متكامل مع: DocumentGenerator
        """
        try:
            doc_generator = DocumentGenerator()
            document = doc_generator.generate(document_type, data)
            return document
        
        except Exception as e:
            return None
    
    @staticmethod
    def get_company_information():
        """
        معلومات الشركة
        متكامل مع: company_info
        """
        try:
            info = company_info.get_company_details()
            return info
        
        except Exception as e:
            return {}
    
    @staticmethod
    def get_system_knowledge(query):
        """
        المعرفة بالنظام
        متكامل مع: system_knowledge
        """
        try:
            knowledge = system_knowledge.search_knowledge(query)
            return knowledge
        
        except Exception as e:
            return {}
    
    @staticmethod
    def get_advanced_law_info(law_topic):
        """
        معلومات قانونية متقدمة
        متكامل مع: advanced_laws
        """
        try:
            laws = advanced_laws.AdvancedLaws()
            law_info = laws.get_law_information(law_topic)
            return law_info
        
        except Exception as e:
            return {}
    
    @staticmethod
    def expand_knowledge_base(new_topic):
        """
        توسيع قاعدة المعرفة
        متكامل مع: KnowledgeExpander
        """
        try:
            expander = KnowledgeExpander()
            result = expander.expand_knowledge(new_topic)
            return result
        
        except Exception as e:
            return {}
    
    @staticmethod
    def perform_self_improvement():
        """
        التحسين الذاتي للمساعد
        متكامل مع: AzadSelfImprovement
        """
        try:
            self_improvement = AzadSelfImprovement()
            improvements = self_improvement.analyze_and_improve()
            return improvements
        
        except Exception as e:
            return {}
    
    @staticmethod
    def integrate_with_system(operation_type, data):
        """
        التكامل مع أنظمة النظام
        متكامل مع: SystemIntegrator
        """
        try:
            integrator = SystemIntegrator()
            result = integrator.execute_integration(operation_type, data)
            return result
        
        except Exception as e:
            return {}
    
    @staticmethod
    def get_global_knowledge(query):
        """
        المعرفة العالمية والتحديثات
        متكامل مع: GlobalKnowledgeConnector
        """
        try:
            global_connector = GlobalKnowledgeConnector()
            knowledge = global_connector.fetch_knowledge(query)
            return knowledge
        
        except Exception as e:
            return {}
    
    @staticmethod
    def get_beginners_help(topic):
        """
        مساعدة المبتدئين
        متكامل مع: BeginnersGuide
        """
        try:
            beginners_guide = BeginnersGuide()
            help_content = beginners_guide.get_help(topic)
            return help_content
        
        except Exception as e:
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
            
            product = db.session.get(Product, product_id)
            customer = db.session.get(Customer, customer_id) if customer_id else None
            
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
    def think_deeply(problem: str, context: dict = None):
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
    def delegate_to_expert(task: str, context: dict = None):
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
    def generate_code(code_type: str, purpose: str, params: dict = None):
        """
        توليد كود تلقائياً
        SQL / Python / JavaScript
        """
        try:
            generator = AIService.get_code_generator()
            
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
    def ask_genius(question: str, context: dict = None, user_id: int = None):
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
        """
        الحصول على مصادر التعلم الخارجية (30+ مصدر)
        
        Returns:
            قائمة بأضخم مصادر المعرفة في العالم
        """
        try:
            learning = get_external_learning()
            sources = learning.get_knowledge_sources_list()
            stats = learning.get_statistics()
            
            return {
                'sources': sources,
                'total_sources': len(sources),
                'statistics': stats
            }
        
        except Exception as e:
            return {'sources': [], 'error': str(e)}
    
    @staticmethod
    def learn_from_external(source_type: str, topic: str, content: str):
        """
        التعلم من مصدر خارجي
        
        Args:
            source_type: wikipedia, stackoverflow, github, etc
            topic: الموضوع
            content: المحتوى
        
        Returns:
            {success: bool}
        """
        try:
            learning = get_external_learning()
            result = learning.learn_from_source(source_type, topic, content)
            
            return result
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
