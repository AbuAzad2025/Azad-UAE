"""
Consolidated module: agents_core.py
Merged: agents/multi_agent_system.py, agents/intelligent_assistant.py, agents/master_brain.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: agents/multi_agent_system.py =====
"""
👥 نظام متعدد الوكلاء - Multi-Agent System
تنسيق بين خبراء متعددين لحل مشاكل معقدة

الوكلاء (Agents):
1. Sales Agent (وكيل المبيعات)
2. Accounting Agent (وكيل المحاسبة)
3. Inventory Agent (وكيل المخزون)
4. Customer Agent (وكيل العملاء)
5. Financial Agent (وكيل المالية)
6. Maintenance Agent (وكيل الصيانة)
7. Security Agent (وكيل الأمن)
"""

import logging
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseAgent:
    """وكيل أساسي - Base Agent"""
    
    def __init__(self, name, expertise):
        self.name = name
        self.expertise = expertise
        self.confidence_level = 0.8
        self.handled_tasks = []
    
    def can_handle(self, task: str) -> float:
        """
        هل يمكن للوكيل التعامل مع هذه المهمة؟
        
        Returns:
            confidence: 0.0 - 1.0
        """
        task_lower = task.lower()
        
        for keyword in self.expertise:
            if keyword.lower() in task_lower:
                return self.confidence_level
        
        return 0.0
    
    def execute(self, task: str, context: dict) -> dict:
        """
        تنفيذ المهمة
        
        Returns:
            {
                'result': النتيجة,
                'confidence': مستوى الثقة,
                'explanation': الشرح
            }
        """
        raise NotImplementedError("Subclass must implement execute()")


class SalesAgent(BaseAgent):
    """وكيل المبيعات - خبير في المبيعات والتسعير"""
    
    def __init__(self):
        super().__init__(
            name="Sales Agent",
            expertise=['بيع', 'sale', 'سعر', 'price', 'فاتورة', 'invoice', 'عرض', 'discount']
        )
    
    def execute(self, task: str, context: dict) -> dict:
        """تنفيذ مهمة متعلقة بالمبيعات"""
        try:
            if 'سعر' in task.lower() or 'price' in task.lower():
                # استخدام Neural Network للتسعير
                from services.ai_service import AIService
                
                product_id = context.get('product_id')
                customer_id = context.get('customer_id')
                
                result = AIService.predict_price_with_neural(product_id, customer_id)
                
                return {
                    'result': result,
                    'confidence': result.get('confidence', 0.9),
                    'explanation': f"السعر المقترح بناءً على التحليل العصبي: {result.get('predicted_price', 0)} AED",
                    'agent': self.name
                }
            
            else:
                return {
                    'result': None,
                    'confidence': 0.5,
                    'explanation': 'مهمة غير محددة بدقة',
                    'agent': self.name
                }
        
        except Exception as e:
            logger.error(f"Sales agent execution failed: {e}")
            return {'result': None, 'confidence': 0, 'error': str(e)}


class AccountingAgent(BaseAgent):
    """وكيل المحاسبة - خبير محاسبة قانوني"""
    
    def __init__(self):
        super().__init__(
            name="Accounting Agent",
            expertise=['قيد', 'journal', 'محاسبة', 'accounting', 'ميزانية', 'balance', 'مدين', 'دائن']
        )
        self.confidence_level = 0.95  # ثقة عالية في المحاسبة
    
    def execute(self, task: str, context: dict) -> dict:
        """تنفيذ مهمة محاسبية"""
        try:
            if 'قيد' in task.lower():
                # التحقق من القيد
                debit = context.get('debit', 0)
                credit = context.get('credit', 0)
                
                is_balanced = abs(debit - credit) < 0.01
                
                explanation = f"""
تحليل محاسبي:
- المدين: {debit:,.2f} AED
- الدائن: {credit:,.2f} AED
- الفرق: {abs(debit - credit):,.2f} AED
- الحالة: {'✅ متوازن' if is_balanced else '❌ غير متوازن'}

المبدأ المحاسبي: القيد المزدوج (Double Entry)
القاعدة: المدين = الدائن دائماً
"""
                
                return {
                    'result': {
                        'is_balanced': is_balanced,
                        'debit': debit,
                        'credit': credit,
                        'difference': abs(debit - credit)
                    },
                    'confidence': 1.0 if is_balanced else 0.2,
                    'explanation': explanation,
                    'agent': self.name
                }
            
            return {'result': None, 'confidence': 0.5, 'agent': self.name}
        
        except Exception as e:
            return {'result': None, 'confidence': 0, 'error': str(e)}


class InventoryAgent(BaseAgent):
    """وكيل المخزون - خبير إدارة مخزون"""
    
    def __init__(self):
        super().__init__(
            name="Inventory Agent",
            expertise=['مخزون', 'inventory', 'stock', 'warehouse', 'مستودع']
        )
    
    def execute(self, task: str, context: dict) -> dict:
        """تنفيذ مهمة متعلقة بالمخزون"""
        try:
            if 'مخزون' in task.lower() or 'stock' in task.lower():
                from services.ai_service import AIService
                
                product_id = context.get('product_id')
                
                optimization = AIService.optimize_inventory_neural(product_id)
                
                return {
                    'result': optimization,
                    'confidence': 0.9,
                    'explanation': f"تحليل المخزون: {optimization.get('recommendation', '')}",
                    'agent': self.name
                }
            
            return {'result': None, 'confidence': 0.5, 'agent': self.name}
        
        except Exception as e:
            return {'result': None, 'confidence': 0, 'error': str(e)}


class MaintenanceAgent(BaseAgent):
    """وكيل الصيانة - مهندس صيانة خبير"""
    
    def __init__(self):
        super().__init__(
            name="Maintenance Agent",
            expertise=['صيانة', 'maintenance', 'إصلاح', 'repair', 'عطل', 'fault']
        )
    
    def execute(self, task: str, context: dict) -> dict:
        """تنفيذ مهمة صيانة"""
        try:
            if 'صيانة' in task.lower():
                from ai_knowledge.core.reasoning_engine import get_reasoning_engine
                
                # استخدام محرك التفكير التقني
                reasoning = get_reasoning_engine()
                diagnosis = reasoning.technical_reasoning(task)
                
                return {
                    'result': diagnosis,
                    'confidence': 0.85,
                    'explanation': f"تشخيص: {', '.join(diagnosis['possible_causes'][:2])}",
                    'agent': self.name
                }
            
            return {'result': None, 'confidence': 0.5, 'agent': self.name}
        
        except Exception as e:
            return {'result': None, 'confidence': 0, 'error': str(e)}


class MultiAgentCoordinator:
    """
    منسق الوكلاء المتعددين
    
    يوزع المهام على الخبراء المناسبين
    """
    
    def __init__(self):
        # تهيئة جميع الوكلاء
        self.agents = {
            'sales': SalesAgent(),
            'accounting': AccountingAgent(),
            'inventory': InventoryAgent(),
            'maintenance': MaintenanceAgent()
        }
        
        self.task_history = []
    
    def delegate_task(self, task: str, context: dict = None) -> dict:
        """
        توزيع المهمة على الوكيل المناسب
        
        Args:
            task: المهمة المطلوبة
            context: السياق والبيانات
        
        Returns:
            {
                'result': النتيجة,
                'assigned_agent': الوكيل المسؤول,
                'confidence': مستوى الثقة
            }
        """
        context = context or {}
        
        # تحديد الوكيل الأنسب
        agent_scores = {}
        
        for agent_name, agent in self.agents.items():
            score = agent.can_handle(task)
            agent_scores[agent_name] = score
        
        # اختيار الوكيل بأعلى ثقة
        best_agent_name = max(agent_scores, key=agent_scores.get)
        best_score = agent_scores[best_agent_name]
        
        if best_score < 0.3:
            # لا وكيل مناسب - استخدام وكيل عام
            return {
                'result': None,
                'assigned_agent': 'General Agent',
                'confidence': 0.3,
                'explanation': 'لا يوجد وكيل متخصص لهذه المهمة'
            }
        
        # تنفيذ المهمة
        best_agent = self.agents[best_agent_name]
        result = best_agent.execute(task, context)
        
        # حفظ في التاريخ
        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'task': task,
            'assigned_agent': best_agent_name,
            'confidence': best_score,
            'result': result
        })
        
        logger.info(f"👥 Task delegated to {best_agent_name}: {task[:50]}")
        
        return {
            'result': result.get('result'),
            'assigned_agent': best_agent_name,
            'confidence': best_score,
            'explanation': result.get('explanation', ''),
            'all_scores': agent_scores
        }
    
    def collaborative_solve(self, complex_task: str, context: dict = None) -> dict:
        """
        حل تعاوني بين وكلاء متعددين
        
        للمشاكل المعقدة التي تحتاج خبراء متعددين
        """
        context = context or {}
        
        # مثال: "احسب السعر الأمثل مع التحقق من المخزون والربحية"
        # يحتاج: Sales Agent + Inventory Agent + Accounting Agent
        
        results = {}
        
        for agent_name, agent in self.agents.items():
            if agent.can_handle(complex_task) > 0.3:
                agent_result = agent.execute(complex_task, context)
                results[agent_name] = agent_result
        
        # دمج النتائج
        combined = {
            'task': complex_task,
            'agents_involved': list(results.keys()),
            'individual_results': results,
            'confidence': sum(r.get('confidence', 0) for r in results.values()) / len(results) if results else 0
        }
        
        return combined


# ============================================================================
# Singleton
# ============================================================================

_coordinator_instance = None

def get_agent_coordinator():
    """الحصول على منسق الوكلاء"""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = MultiAgentCoordinator()
    return _coordinator_instance



# ===== Consolidated from: agents/intelligent_assistant.py =====
"""
🧠 المساعد الذكي الحقيقي - True Intelligent Assistant
نظام ذكاء اصطناعي متكامل - يفهم، يحلل، يستنتج، يتعلم

الفرق بين التلقين والذكاء:
- التلقين: if 'فاتورة' → return "رابط..."
- الذكاء: فهم النية → تحليل البيانات → استنتاج → توليد رد ديناميكي

المحركات المستخدمة:
- Neural Engine: للتعلم والتنبؤ
- Reasoning Engine: للاستنتاج المنطقي
- Data Analyzer: لتحليل البيانات الحقيقية
- Memory System: لتذكر السياق
- Context Engine: لفهم السياق
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


class IntelligentAssistant:
    """
    المساعد الذكي الحقيقي - ليس pattern matching
    
    يعمل بـ 5 مراحل:
    1. فهم النية والسياق (Understanding)
    2. جمع البيانات الحقيقية (Data Collection)
    3. التحليل والاستنتاج (Analysis & Reasoning)
    4. التوليد الديناميكي (Dynamic Generation)
    5. التعلم (Learning)
    """
    
    def __init__(self):
        """تهيئة جميع المحركات"""
        # تأخير الاستيراد لتجنب circular imports
        self._neural_engine = None
        self._reasoning_engine = None
        self._data_analyzer = None
        self._memory_system = None
        self._context_engine = None
        self._quick_learner = None
        
        logger.info("🧠 Intelligent Assistant initialized")

    @property
    def quick_learner(self):
        """المتعلم السريع"""
        if self._quick_learner is None:
            from ai_knowledge.learning.quick_learner import quick_learner
            self._quick_learner = quick_learner
        return self._quick_learner
    
    @property
    def neural_engine(self):
        """محرك الشبكات العصبية"""
        if self._neural_engine is None:
            from ai_knowledge.neural.neural_engine import get_neural_engine
            self._neural_engine = get_neural_engine()
        return self._neural_engine
    
    @property
    def reasoning_engine(self):
        """محرك الاستنتاج المنطقي"""
        if self._reasoning_engine is None:
            from ai_knowledge.core.reasoning_engine import get_reasoning_engine
            self._reasoning_engine = get_reasoning_engine()
        return self._reasoning_engine
    
    @property
    def data_analyzer(self):
        """محلل البيانات"""
        if self._data_analyzer is None:
            from ai_knowledge.analytics.data_analyzer import data_analyzer
            self._data_analyzer = data_analyzer
        return self._data_analyzer
    
    @property
    def memory_system(self):
        """نظام الذاكرة"""
        if self._memory_system is None:
            from ai_knowledge.core.memory_system import get_memory_system
            self._memory_system = get_memory_system()
        return self._memory_system
    
    @property
    def context_engine(self):
        """محرك السياق"""
        if self._context_engine is None:
            from ai_knowledge.core.context_engine import context_engine
            self._context_engine = context_engine
        return self._context_engine
    
    def process(self, message: str, user_id: int = None, context: dict = None) -> Dict:
        """
        معالجة ذكية كاملة للرسالة
        
        Args:
            message: رسالة المستخدم
            user_id: معرف المستخدم
            context: السياق الإضافي
        
        Returns:
            رد ديناميكي مبني على فهم حقيقي
        """
        try:
            # ========== المرحلة 0: المعرفة السريعة (Quick Knowledge) ==========
            quick_answer = self.quick_learner.get_answer(message)
            if quick_answer:
                return {
                    'success': True,
                    'response': f"{quick_answer}\n\n<sub>⚡ معلومة سريعة</sub>",
                    'intent': 'quick_answer',
                    'confidence': 1.0,
                    'method': 'quick_learner'
                }

            # ========== المرحلة 1: فهم النية والسياق ==========
            understanding = self._understand_message(message, user_id, context)
            
            if not understanding['success']:
                return self._generate_help_response(message)
            
            intent = understanding['intent']
            entities = understanding['entities']
            conversation_context = understanding['context']
            
            # ========== المرحلة 2: جمع البيانات الحقيقية ==========
            real_data = self._collect_real_data(intent, entities, user_id)
            
            # ========== المرحلة 3: التحليل والاستنتاج ==========
            analysis = self._analyze_and_reason(intent, real_data, conversation_context)
            
            # ========== المرحلة 4: التوليد الديناميكي ==========
            response = self._generate_dynamic_response(intent, analysis, entities, real_data)
            
            # ========== المرحلة 5: التعلم ==========
            self._learn_from_interaction(message, response, user_id)
            
            return {
                'success': True,
                'response': response,
                'intent': intent,
                'confidence': understanding['confidence'],
                'data_used': len(real_data) if isinstance(real_data, list) else bool(real_data),
                'method': 'intelligent_ai'  # ليس pattern matching!
            }
        
        except Exception as e:
            logger.error(f"Intelligent processing failed: {e}")
            return {
                'success': False,
                'response': f"عذراً، حدث خطأ أثناء المعالجة: {str(e)}",
                'method': 'error'
            }
    
    def _understand_message(self, message: str, user_id: int, context: dict) -> Dict:
        """فهم الرسالة بذكاء"""
        try:
            # استخدام semantic matcher للنية الأساسية
            from ai_knowledge.neural.semantic_matcher import understand_message
            semantic_result = understand_message(message)
            
            # تعميق الفهم بـ Neural Engine
            neural_understanding = self.neural_engine.understand_intent(message)
            
            # استخراج الكيانات (entities)
            entities = self._extract_entities(message)
            
            # بناء السياق الكامل
            # بناء السياق الكامل
            full_context = {
                'message': message,
                'user_id': user_id,
                'timestamp': datetime.now(),
                'additional_context': context or {}
            }
            
            # دمج النتائج
            final_intent = semantic_result.get('intent') or neural_understanding.get('intent')
            confidence = max(
                semantic_result.get('confidence', 0),
                neural_understanding.get('confidence', 0)
            )
            
            return {
                'success': True,
                'intent': final_intent,
                'entities': entities,
                'context': full_context,
                'confidence': confidence,
                'semantic_scores': semantic_result.get('all_scores', []),
                'neural_features': neural_understanding
            }
        
        except Exception as e:
            logger.error(f"Understanding failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _extract_entities(self, message: str) -> Dict:
        """استخراج الكيانات من الرسالة"""
        import re
        
        entities = {
            'numbers': [],
            'dates': [],
            'names': [],
            'products': [],
            'amounts': []
        }
        
        # الأرقام
        numbers = re.findall(r'\d+(?:\.\d+)?', message)
        entities['numbers'] = [float(n) for n in numbers]
        
        # المبالغ (بالعملة)
        amounts = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*(درهم|دولار|ريال|AED|USD|SAR)', message)
        entities['amounts'] = [{'value': float(a[0].replace(',', '')), 'currency': a[1]} for a in amounts]
        
        # الأسماء (كلمات بحروف كبيرة أو بعد "العميل" أو "الزبون")
        name_patterns = [
            r'(?:العميل|الزبون|customer)\s+(\w+)',
            r'(?:المنتج|product)\s+(\w+)',
        ]
        for pattern in name_patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            if matches:
                if 'عميل' in pattern or 'زبون' in pattern:
                    entities['names'].extend(matches)
                else:
                    entities['products'].extend(matches)
        
        return entities
    
    def _collect_real_data(self, intent: str, entities: Dict, user_id: int) -> Dict:
        """جمع البيانات الحقيقية من النظام"""
        try:
            from models import Sale, Customer, Product, Payment
            from extensions import db
            from sqlalchemy import func
            
            data = {}
            
            # بيانات عامة للنظام
            data['system_stats'] = {
                'total_customers': Customer.query.filter_by(is_active=True).count(),
                'total_products': Product.query.filter_by(is_active=True).count(),
                'total_sales_today': Sale.query.filter(
                    func.date(Sale.sale_date) == datetime.now().date()
                ).count()
            }
            
            # بيانات حسب النية
            if intent in ['sales_analysis', 'customer_balance', 'inventory_check']:
                # مبيعات آخر 30 يوم
                thirty_days_ago = datetime.now() - timedelta(days=30)
                recent_sales = Sale.query.filter(Sale.sale_date >= thirty_days_ago).all()
                
                data['recent_sales'] = {
                    'count': len(recent_sales),
                    'total_amount': sum(float(s.total_amount) for s in recent_sales),
                    'avg_amount': sum(float(s.total_amount) for s in recent_sales) / len(recent_sales) if recent_sales else 0,
                    'sales': [
                        {
                            'id': s.id,
                            'date': s.sale_date.strftime('%Y-%m-%d'),
                            'amount': float(s.total_amount),
                            'customer': s.customer.name if s.customer else 'غير محدد'
                        }
                        for s in recent_sales[-10:]  # آخر 10 فقط
                    ]
                }
            
            if intent in ['customer_balance'] and entities.get('names'):
                # بحث عن العميل المحدد
                customer_name = entities['names'][0]
                customer = Customer.query.filter(
                    Customer.name.ilike(f'%{customer_name}%')
                ).first()
                
                if customer:
                    data['customer_data'] = self.data_analyzer.analyze_customer_debt(customer.id)
            
            if intent in ['inventory_check']:
                # المنتجات بمخزون منخفض
                low_stock = Product.query.filter(
                    Product.is_active == True,
                    Product.current_stock <= Product.min_stock_alert
                ).all()
                
                data['low_stock_products'] = [
                    {
                        'id': p.id,
                        'name': p.name,
                        'current_stock': float(p.current_stock),
                        'min_alert': float(p.min_stock_alert),
                        'deficit': float(p.min_stock_alert - p.current_stock)
                    }
                    for p in low_stock
                ]
            
            return data
        
        except Exception as e:
            logger.error(f"Data collection failed: {e}")
            return {}
    
    def _analyze_and_reason(self, intent: str, data: Dict, context: Dict) -> Dict:
        """التحليل والاستنتاج المنطقي"""
        try:
            analysis = {
                'insights': [],
                'warnings': [],
                'recommendations': [],
                'predictions': []
            }
            
            # استخدام Reasoning Engine للاستنتاج
            if intent == 'sales_analysis' and 'recent_sales' in data:
                sales_data = data['recent_sales']
                
                # الاستنتاجات
                if sales_data['count'] == 0:
                    analysis['warnings'].append("⚠️ لا توجد مبيعات في آخر 30 يوم - مشكلة خطيرة!")
                    analysis['recommendations'].append("💡 راجع استراتيجية التسويق فوراً")
                elif sales_data['count'] < 5:
                    analysis['warnings'].append("⚠️ المبيعات ضعيفة جداً")
                    analysis['recommendations'].append("💡 تواصل مع العملاء القدامى")
                else:
                    avg_per_day = sales_data['count'] / 30
                    if avg_per_day < 1:
                        analysis['insights'].append(f"📊 متوسط المبيعات: {avg_per_day:.1f} فاتورة/يوم")
                        analysis['recommendations'].append("💡 استهدف 3-5 فواتير يومياً لنمو صحي")
                    else:
                        analysis['insights'].append(f"✅ أداء جيد: {avg_per_day:.1f} فاتورة/يوم")
                
                # التنبؤ باستخدام Neural Engine
                try:
                    prediction = self.neural_engine.predict_next_week_sales()
                    if prediction.get('success'):
                        analysis['predictions'].append(
                            f"🔮 التوقع للأسبوع القادم: {prediction['predicted_amount']:,.0f} درهم"
                        )
                except:
                    pass
            
            elif intent == 'inventory_check' and 'low_stock_products' in data:
                low_stock = data['low_stock_products']
                
                if len(low_stock) == 0:
                    analysis['insights'].append("✅ المخزون صحي - لا توجد منتجات بمخزون منخفض")
                elif len(low_stock) < 5:
                    analysis['warnings'].append(f"⚠️ {len(low_stock)} منتجات بمخزون منخفض")
                    analysis['recommendations'].append("💡 اطلب تجديد المخزون هذا الأسبوع")
                else:
                    analysis['warnings'].append(f"🔴 {len(low_stock)} منتج بمخزون منخفض - عاجل!")
                    analysis['recommendations'].append("💡 اطلب من الموردين فوراً!")
                    
                    # حساب التكلفة المتوقعة
                    total_deficit = sum(p['deficit'] for p in low_stock)
                    analysis['insights'].append(f"📊 العجز الكلي: {total_deficit:.0f} وحدة")
            
            elif intent == 'customer_balance' and 'customer_data' in data:
                customer_data = data['customer_data']
                
                if customer_data['success']:
                    debt_info = customer_data['debt_analysis']
                    total_debt = debt_info['total_debt']
                    
                    if total_debt == 0:
                        analysis['insights'].append("✅ العميل ليس عليه ديون")
                    elif total_debt < 1000:
                        analysis['insights'].append(f"💰 رصيد العميل: {total_debt:,.2f} درهم (طبيعي)")
                    elif total_debt < 5000:
                        analysis['warnings'].append(f"⚠️ رصيد العميل: {total_debt:,.2f} درهم")
                        analysis['recommendations'].append("💡 تواصل للتحصيل خلال أسبوع")
                    else:
                        analysis['warnings'].append(f"🔴 رصيد مرتفع: {total_debt:,.2f} درهم!")
                        analysis['recommendations'].append("💡 متابعة عاجلة + إيقاف الائتمان")
                    
                    # تحليل التأخير
                    if debt_info['overdue_count'] > 0:
                        analysis['warnings'].append(
                            f"⏰ {debt_info['overdue_count']} فاتورة متأخرة أكثر من 30 يوم"
                        )
            
            return analysis
        
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {'insights': [], 'warnings': [], 'recommendations': []}
    
    def _generate_dynamic_response(self, intent: str, analysis: Dict, entities: Dict, data: Dict) -> str:
        """توليد رد ديناميكي - ليس مسبق الحفظ"""
        try:
            # بناء الرد بناءً على البيانات الحقيقية
            response_parts = []
            
            # المقدمة الديناميكية
            if intent == 'greeting':
                import random
                greetings = [
                    "يا هلا! 🌹 أنا أزاد، مساعدك الذكي. آمرني؟",
                    "هلا والله! جاهز للمساعدة في أي وقت 💪",
                    "وعليكم السلام! كيف أقدر أساعدك اليوم في الكراج؟ 🚗",
                    "أهلاً بك! معك أزاد، المحاسب والمهندس والمدير المالي 😉"
                ]
                response_parts.append(random.choice(greetings))

            elif intent == 'who_are_you':
                response_parts.append("🤖 **أنا أزاد (AZAD)**\n")
                response_parts.append("مساعد ذكي متطور تم تطويري خصيصاً لإدارة الكراجات والمحاسبة.")
                response_parts.append("\n💪 **قدراتي:**")
                response_parts.append("• 💰 **محاسب:** فواتير، سندات، ضرائب")
                response_parts.append("• 🔧 **مهندس:** معلومات قطع غيار، صيانة")
                response_parts.append("• 📈 **محلل:** تقارير مبيعات، أرباح")
                response_parts.append("• 🧠 **ذكي:** أتعلم منك كل يوم!")

            elif intent == 'praise':
                import random
                thanks = [
                    "تسلم! هذا واجبي 🌹",
                    "كفوك الطيب! حاضرين للطيبين 💪",
                    "شكراً لك! شهادة أعتز فيها 🌟",
                    "الله يعافيك! نحن بالخدمة دائماً"
                ]
                response_parts.append(random.choice(thanks))

            elif intent == 'complaint':
                response_parts.append("😔 **حقك علي!**\n")
                response_parts.append("أنا آسف إذا قصرت. أنا ما زلت أتعلم وأتطور.")
                response_parts.append("ممكن تشرح لي أكثر شو المشكلة عشان ما أكررها؟ 🙏")

            elif intent == 'sales_analysis':
                response_parts.append("📊 **تحليل المبيعات الحقيقي:**\n")
                
                if 'recent_sales' in data:
                    sales_info = data['recent_sales']
                    response_parts.append(f"📈 **آخر 30 يوم:**")
                    response_parts.append(f"• عدد الفواتير: **{sales_info['count']}**")
                    response_parts.append(f"• الإجمالي: **{sales_info['total_amount']:,.0f} درهم**")
                    response_parts.append(f"• المتوسط: **{sales_info['avg_amount']:,.0f} درهم/فاتورة**")
                    response_parts.append("")
            
            elif intent == 'customer_balance':
                response_parts.append("💰 **تحليل رصيد العميل:**\n")
                
                if 'customer_data' in data and data['customer_data']['success']:
                    cust = data['customer_data']['customer']
                    debt = data['customer_data']['debt_analysis']
                    
                    response_parts.append(f"👤 **العميل:** {cust['name']}")
                    response_parts.append(f"💵 **الرصيد الكلي:** {debt['total_debt']:,.2f} درهم")
                    response_parts.append(f"📄 **فواتير غير مدفوعة:** {debt['unpaid_sales_count']}")
                    
                    if debt['overdue_count'] > 0:
                        response_parts.append(f"⏰ **متأخرة (+30 يوم):** {debt['overdue_count']}")
                    response_parts.append("")
            
            elif intent == 'inventory_check':
                response_parts.append("📦 **تحليل المخزون:**\n")
                
                if 'low_stock_products' in data:
                    low_stock = data['low_stock_products']
                    
                    if len(low_stock) == 0:
                        response_parts.append("✅ **المخزون صحي!** جميع المنتجات فوق الحد الأدنى")
                    else:
                        response_parts.append(f"⚠️ **منتجات بمخزون منخفض:** {len(low_stock)}\n")
                        response_parts.append("**أبرزها:**")
                        for p in low_stock[:5]:
                            response_parts.append(f"• {p['name']}: {p['current_stock']:.0f} (الحد الأدنى: {p['min_alert']:.0f})")
                    response_parts.append("")
            
            # إضافة الرؤى
            if analysis['insights']:
                response_parts.append("💡 **رؤى:**")
                for insight in analysis['insights']:
                    response_parts.append(insight)
                response_parts.append("")
            
            # إضافة التحذيرات
            if analysis['warnings']:
                response_parts.append("⚠️ **تنبيهات:**")
                for warning in analysis['warnings']:
                    response_parts.append(warning)
                response_parts.append("")
            
            # إضافة التوصيات
            if analysis['recommendations']:
                response_parts.append("🎯 **توصياتي لك:**")
                for rec in analysis['recommendations']:
                    response_parts.append(rec)
                response_parts.append("")
            
            # إضافة التنبؤات
            if analysis['predictions']:
                response_parts.append("🔮 **التنبؤات:**")
                for pred in analysis['predictions']:
                    response_parts.append(pred)
            
            return "\n".join(response_parts)
        
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return "عذراً، حدث خطأ في توليد الرد"
    
    def _learn_from_interaction(self, message: str, response: str, user_id: int):
        """التعلم من التفاعل"""
        try:
            # حفظ في الذاكرة
            if user_id:
                self.memory_system.remember_conversation(user_id, message, response)
            
            # التعلم الذاتي
            from ai_knowledge.core.learning_system import learning_system
            learning_system.learn_from_interaction(message, response, context={'user_id': user_id})
        
        except Exception as e:
            logger.error(f"Learning failed: {e}")
    
    def _generate_help_response(self, message: str) -> Dict:
        """رد المساعدة عند عدم الفهم"""
        return {
            'success': True,
            'response': """🤔 لم أفهم سؤالك بشكل كامل.

💡 **يمكنك أن تسألني عن:**
• "كيف مبيعاتي هالشهر؟"
• "رصيد العميل أحمد؟"
• "وين المخزون الناقص؟"
• "توقع المبيعات للأسبوع الجاي"

🧠 أنا أحلل البيانات الحقيقية وأعطيك رؤى ذكية - ليس مجرد إجابات جاهزة!""",
            'method': 'help'
        }


# إنشاء instance عام
intelligent_assistant = IntelligentAssistant()


# دالة مساعدة
def intelligent_response(message: str, user_id: int = None, context: dict = None) -> str:
    """الحصول على رد ذكي"""
    result = intelligent_assistant.process(message, user_id, context)
    return result.get('response', 'عذراً، حدث خطأ')



# ===== Consolidated from: agents/master_brain.py =====
"""
🧠 العقل الرئيسي - Master Brain
نظام ذكاء اصطناعي موحد خارق

الهدف: عقل واحد متكامل - أذكى من:
- ChatGPT
- DeepSeek  
- Cursor
- GitHub Copilot
- Claude
- Gemini

القدرات الشاملة:
- بروفيسور محاسبة وضرائب
- خبير إداري ومالي
- مهندس صيانة محترف
- سكرتير تنفيذي
- مستشار قانوني
- محلل بيانات
- مبرمج خبير

شركة أزاد للأنظمة الذكية
"""

import logging
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
import re

logger = logging.getLogger(__name__)


class MasterBrain:
    """
    العقل الرئيسي الموحد
    
    يجمع كل القدرات في نظام واحد سريع ومترابط
    """
    
    def __init__(self):
        self.name = "أزاد - العقل الخارق"
        self.version = "2.0 - Ultimate Edition"
        
        # قواعد المعرفة الشاملة
        self.knowledge_base = self._initialize_ultimate_knowledge()
        
        # الذاكرة الموحدة
        self.unified_memory = {
            'conversations': [],
            'facts': [],
            'procedures': [],
            'user_preferences': {}
        }
        
        # النماذج العصبية (كاش)
        self.neural_models = {}
        self.neural_ready = False
        
        # الأداء
        self.response_time_target = 0.05  # 50ms max
        self.cache = {}
        
        logger.info(f"🧠 {self.name} initialized - Ready for genius-level operations!")
    
    def _initialize_ultimate_knowledge(self) -> dict:
        """تهيئة قاعدة المعرفة الشاملة - أضخم قاعدة معرفة!"""
        
        # استيراد المعرفة الإضافية
        try:
            from ai_knowledge.knowledge.automotive_ecu_knowledge import get_automotive_ecu_knowledge
            automotive_kb = get_automotive_ecu_knowledge().knowledge_base
        except:
            automotive_kb = {}
        
        try:
            from ai_knowledge.learning.external_learning import get_external_learning
            external_sources = get_external_learning().learning_sources
        except:
            external_sources = {}
        
        return {
            # ========== المحاسبة ==========
            'accounting': {
                'principles': {
                    'accrual': 'مبدأ الاستحقاق - تسجيل الإيرادات والمصروفات عند حدوثها',
                    'matching': 'مبدأ المقابلة - مقابلة الإيرادات بالمصروفات في نفس الفترة',
                    'consistency': 'مبدأ الثبات - استخدام نفس الطرق المحاسبية',
                    'conservatism': 'مبدأ الحيطة والحذر - عدم المبالغة في الأصول والإيرادات',
                    'materiality': 'مبدأ الأهمية النسبية',
                    'going_concern': 'مبدأ الاستمرارية',
                    'double_entry': 'القيد المزدوج - لكل مدين دائن'
                },
                'formulas': {
                    'gross_profit': 'الربح الإجمالي = المبيعات - تكلفة البضاعة المباعة',
                    'net_profit': 'صافي الربح = الإيرادات - جميع المصروفات',
                    'current_ratio': 'نسبة السيولة الجارية = الأصول المتداولة / الخصوم المتداولة',
                    'quick_ratio': 'نسبة السيولة السريعة = (الأصول المتداولة - المخزون) / الخصوم المتداولة',
                    'debt_ratio': 'نسبة المديونية = إجمالي الديون / إجمالي الأصول',
                    'roe': 'العائد على حقوق الملكية = صافي الربح / حقوق الملكية',
                    'roa': 'العائد على الأصول = صافي الربح / إجمالي الأصول',
                    'gross_margin': 'هامش الربح الإجمالي = (الربح الإجمالي / المبيعات) × 100',
                    'net_margin': 'هامش الربح الصافي = (صافي الربح / المبيعات) × 100'
                },
                'accounts_structure': {
                    'assets': 'الأصول - حسابات ذات طبيعة مدينة',
                    'liabilities': 'الخصوم - حسابات ذات طبيعة دائنة',
                    'equity': 'حقوق الملكية - حسابات ذات طبيعة دائنة',
                    'revenue': 'الإيرادات - حسابات ذات طبيعة دائنة',
                    'expenses': 'المصروفات - حسابات ذات طبيعة مدينة'
                },
                'entries': {
                    'sale': {
                        'cash_sale': [
                            'من ح/ النقدية',
                            'إلى ح/ المبيعات',
                            'إلى ح/ ضريبة القيمة المضافة (إن وجدت)'
                        ],
                        'credit_sale': [
                            'من ح/ العملاء',
                            'إلى ح/ المبيعات',
                            'إلى ح/ ضريبة القيمة المضافة'
                        ]
                    },
                    'purchase': {
                        'cash_purchase': [
                            'من ح/ المشتريات',
                            'من ح/ ضريبة القيمة المضافة',
                            'إلى ح/ النقدية'
                        ],
                        'credit_purchase': [
                            'من ح/ المشتريات',
                            'من ح/ ضريبة القيمة المضافة',
                            'إلى ح/ الموردين'
                        ]
                    }
                }
            },
            
            # ========== الضرائب ==========
            'taxes': {
                'uae_vat': {
                    'rate': 5,
                    'description': 'ضريبة القيمة المضافة في الإمارات 5%',
                    'registration_threshold': 375000,
                    'voluntary_threshold': 187500,
                    'zero_rated': ['صادرات', 'نقل دولي', 'بعض الأدوية', 'معادن استثمارية'],
                    'exempt': ['تأجير سكني', 'خدمات مالية معينة', 'نقل محلي للركاب'],
                    'calculation': 'الضريبة = المبلغ × 5%',
                    'filing_period': 'ربع سنوي أو شهري حسب حجم الأعمال'
                },
                'corporate_tax': {
                    'rate': 9,
                    'description': 'ضريبة الشركات في الإمارات 9%',
                    'threshold': 375000,
                    'effective_date': '2023-06-01',
                    'exemptions': 'الأرباح أقل من 375,000 درهم'
                },
                'customs': {
                    'standard_rate': 5,
                    'gcc_goods': 0,
                    'description': 'الرسوم الجمركية 5% (معظم السلع)',
                    'gcc_exemption': 'معفاة للسلع من دول الخليج'
                }
            },
            
            # ========== الإدارة ==========
            'management': {
                'theories': {
                    'swot': 'تحليل SWOT - القوة، الضعف، الفرص، التهديدات',
                    'smart_goals': 'أهداف SMART - محددة، قابلة للقياس، قابلة للتحقيق، واقعية، محددة بوقت',
                    'kpi': 'مؤشرات الأداء الرئيسية',
                    'lean': 'الإدارة الرشيقة - تقليل الهدر',
                    'six_sigma': '6 سيجما - تحسين الجودة'
                },
                'inventory_methods': {
                    'fifo': 'FIFO - First In First Out - الوارد أولاً يصرف أولاً',
                    'lifo': 'LIFO - Last In First Out - الوارد أخيراً يصرف أولاً',
                    'weighted_average': 'المتوسط المرجح',
                    'eoq': 'EOQ - الكمية الاقتصادية للطلب = √((2 × الطلب السنوي × تكلفة الطلب) / تكلفة الاحتفاظ)',
                    'reorder_point': 'نقطة إعادة الطلب = (الطلب اليومي × مدة التوريد) + مخزون الأمان',
                    'safety_stock': 'مخزون الأمان = (الطلب الأقصى × مدة التوريد الأقصى) - (الطلب المتوسط × مدة التوريد المتوسطة)',
                    'abc_analysis': 'تحليل ABC - تصنيف المخزون حسب القيمة'
                },
                'financial_management': {
                    'working_capital': 'رأس المال العامل = الأصول المتداولة - الخصوم المتداولة',
                    'break_even': 'نقطة التعادل = التكاليف الثابتة / (سعر البيع - التكلفة المتغيرة للوحدة)',
                    'margin_of_safety': 'هامش الأمان = المبيعات الفعلية - مبيعات نقطة التعادل',
                    'operating_leverage': 'الرافعة التشغيلية = هامش المساهمة / صافي الربح'
                }
            },
            
            # ========== الهندسة والصيانة ==========
            'engineering': {
                'automotive': {
                    'engine': {
                        'systems': ['وقود', 'إشعال', 'تبريد', 'تزييت', 'عادم'],
                        'common_issues': {
                            'overheating': 'ارتفاع الحرارة - فحص الرادياتر، المضخة، الثرموستات',
                            'no_start': 'لا يعمل - فحص البطارية، الوقود، الشمعات',
                            'rough_idle': 'خشونة - فحص الشمعات، الفلتر، الحقن',
                            'oil_consumption': 'استهلاك زيت - فحص الجوانات، المكابس'
                        }
                    },
                    'transmission': {
                        'types': ['يدوي', 'أوتوماتيك', 'CVT', 'DCT'],
                        'maintenance': 'تغيير الزيت كل 60,000 كم للأوتوماتيك'
                    },
                    'brakes': {
                        'components': ['فحمات', 'أقراص', 'كليبرات', 'سائل فرامل'],
                        'inspection': 'فحص كل 10,000 كم'
                    },
                    'fluids': {
                        'engine_oil': 'زيت المحرك - تغيير كل 5,000-10,000 كم',
                        'brake_fluid': 'سائل الفرامل - تغيير كل سنتين',
                        'coolant': 'سائل التبريد - تغيير كل 2-3 سنوات',
                        'transmission_oil': 'زيت القير - تغيير كل 60,000 كم'
                    }
                },
                'heavy_equipment': {
                    'maintenance_schedule': {
                        'daily': 'فحص السوائل، الإطارات، الأضواء',
                        'weekly': 'فحص الفلاتر، البطارية، الأحزمة',
                        'monthly': 'تشحيم، فحص شامل',
                        'quarterly': 'تغيير الزيت والفلاتر'
                    }
                }
            },
            
            # ========== القانون التجاري ==========
            'commercial_law': {
                'uae': {
                    'commercial_license': 'رخصة تجارية - متطلبات: موافقة الجهات، دفع الرسوم',
                    'contracts': 'العقود التجارية - يجب أن تكون مكتوبة للقيم الكبيرة',
                    'commercial_register': 'السجل التجاري - إلزامي لجميع الشركات',
                    'payment_terms': {
                        'net_30': 'الدفع خلال 30 يوم',
                        'net_60': 'الدفع خلال 60 يوم',
                        '2_10_net_30': 'خصم 2% إذا دفع خلال 10 أيام، وإلا كامل المبلغ خلال 30 يوم'
                    }
                }
            },
            
            # ========== البرمجة ==========
            'programming': {
                'sql': {
                    'select': 'SELECT columns FROM table WHERE conditions',
                    'join': 'JOIN - ربط الجداول',
                    'group_by': 'GROUP BY - تجميع البيانات',
                    'having': 'HAVING - شروط على المجموعات',
                    'optimization': 'استخدام INDEX للسرعة'
                },
                'python': {
                    'best_practices': [
                        'استخدم list comprehension',
                        'تجنب loops غير الضرورية',
                        'استخدم generators للبيانات الكبيرة',
                        'استخدم f-strings للنصوص',
                        'استخدم type hints',
                        'اكتب docstrings'
                    ]
                }
            },
            
            # ========== السكرتارية ==========
            'secretarial': {
                'communication': {
                    'email_structure': 'الموضوع - التحية - الموضوع - الخاتمة - التوقيع',
                    'professional_tone': 'رسمي واحترافي ومختصر',
                    'follow_up': 'المتابعة بعد 3 أيام عمل'
                },
                'scheduling': {
                    'priority_matrix': 'مصفوفة أيزنهاور - عاجل/مهم، مهم/غير عاجل، عاجل/غير مهم، غير مهم/غير عاجل',
                    'time_blocking': 'تقسيم اليوم لكتل زمنية'
                }
            },
            
            # ========== كمبيوترات السيارات (من automotive_ecu_knowledge) ==========
            'automotive_ecu': automotive_kb,
            
            # ========== مصادر التعلم الخارجية (30+ مصدر ضخم) ==========
            'external_sources': external_sources
        }
    
    # ========================================================================
    # الدالة الرئيسية الموحدة - Master Function
    # ========================================================================
    
    def ask(self, question: str, context: dict = None, user_id: int = None) -> dict:
        """
        الدالة الرئيسية الموحدة - اسأل العقل الخارق!
        
        هذه الدالة الواحدة تفعل كل شيء:
        - تفهم السؤال
        - تحدد المجال
        - تستخدم النماذج العصبية
        - تفكر منطقياً
        - تتذكر السياق
        - ترد بذكاء خارق
        
        Args:
            question: السؤال
            context: السياق الإضافي
            user_id: معرف المستخدم
        
        Returns:
            {
                'answer': الإجابة الشاملة,
                'confidence': مستوى الثقة,
                'reasoning': خطوات التفكير,
                'sources': مصادر المعلومات,
                'suggestions': اقتراحات للمتابعة
            }
        """
        start_time = datetime.now()
        context = context or {}
        
        try:
            # 1. فهم السؤال
            intent, domain, entities = self._analyze_question(question)
            
            # 2. البحث في قاعدة المعرفة
            knowledge = self._retrieve_knowledge(domain, question)
            
            # 3. التفكير المنطقي
            reasoning_result = self._think_logically(question, intent, knowledge, context)
            
            # 4. استخدام النماذج العصبية (إذا لزم الأمر)
            neural_result = self._use_neural_if_needed(intent, context)
            
            # 5. دمج كل المصادر
            answer = self._synthesize_answer(
                question, reasoning_result, neural_result, knowledge, intent
            )
            
            # 6. التذكر
            if user_id:
                self._remember(user_id, question, answer['text'])
            
            # 7. حساب الوقت
            response_time = (datetime.now() - start_time).total_seconds()
            
            # 8. الاقتراحات
            suggestions = self._generate_smart_suggestions(intent, domain)
            
            result = {
                'answer': answer['text'],
                'confidence': answer['confidence'],
                'reasoning': reasoning_result.get('steps', []),
                'sources': answer.get('sources', []),
                'suggestions': suggestions,
                'domain': domain,
                'intent': intent,
                'response_time_ms': round(response_time * 1000, 2),
                'genius_mode': True
            }
            
            logger.info(f"🧠 Master Brain answered in {response_time*1000:.0f}ms - Confidence: {answer['confidence']:.0%}")
            
            return result
        
        except Exception as e:
            logger.error(f"Master Brain error: {e}")
            return {
                'answer': 'عذراً، دعني أفكر مرة أخرى... يمكنك إعادة صياغة السؤال؟',
                'confidence': 0.3,
                'error': str(e)
            }
    
    def _analyze_question(self, question: str) -> Tuple[str, str, dict]:
        """تحليل السؤال بذكاء خارق"""
        q_lower = question.lower()
        
        # تحديد المجال
        if any(kw in q_lower for kw in ['قيد', 'محاسبة', 'مدين', 'دائن', 'ميزانية', 'ربح', 'خسارة']):
            domain = 'accounting'
        elif any(kw in q_lower for kw in ['ضريبة', 'vat', 'القيمة المضافة', 'جمارك']):
            domain = 'taxes'
        elif any(kw in q_lower for kw in ['مخزون', 'طلب', 'eoq', 'reorder', 'safety stock']):
            domain = 'management'
        elif any(kw in q_lower for kw in ['محرك', 'صيانة', 'زيت', 'فرامل', 'إصلاح']):
            domain = 'engineering'
        elif any(kw in q_lower for kw in ['سعر', 'price', 'تسعير', 'pricing']):
            domain = 'pricing'
        elif any(kw in q_lower for kw in ['توقع', 'predict', 'forecast', 'متوقع']):
            domain = 'prediction'
        elif any(kw in q_lower for kw in ['عميل', 'customer', 'زبون']):
            domain = 'customer'
        elif any(kw in q_lower for kw in ['كود', 'code', 'برمجة', 'sql', 'python']):
            domain = 'programming'
        else:
            domain = 'general'
        
        # تحديد النية
        if '؟' in question or 'كيف' in q_lower or 'ما' in q_lower or 'متى' in q_lower:
            intent = 'question'
        elif 'احسب' in q_lower or 'calculate' in q_lower:
            intent = 'calculation'
        elif 'توقع' in q_lower or 'predict' in q_lower:
            intent = 'prediction'
        elif 'راجع' in q_lower or 'فحص' in q_lower or 'check' in q_lower:
            intent = 'review'
        else:
            intent = 'general'
        
        # استخراج الكيانات
        entities = {}
        numbers = re.findall(r'\d+\.?\d*', question)
        if numbers:
            entities['numbers'] = [float(n) for n in numbers]
        
        return intent, domain, entities
    
    def _retrieve_knowledge(self, domain: str, question: str) -> dict:
        """استرجاع المعرفة المناسبة بسرعة فائقة"""
        if domain in self.knowledge_base:
            return self.knowledge_base[domain]
        return {}
    
    def _think_logically(self, question: str, intent: str, knowledge: dict, context: dict) -> dict:
        """التفكير المنطقي العميق"""
        steps = []
        
        # خطوة 1: فهم المطلوب
        steps.append({
            'step': 1,
            'thought': f'فهمت السؤال: {question[:50]}...',
            'action': 'understanding'
        })
        
        # خطوة 2: تحليل المعطيات
        available_data = list(context.keys()) if context else []
        steps.append({
            'step': 2,
            'thought': f'البيانات المتاحة: {", ".join(available_data) if available_data else "لا يوجد"}',
            'action': 'data_analysis'
        })
        
        # خطوة 3: استخدام المعرفة
        if knowledge:
            steps.append({
                'step': 3,
                'thought': f'استخدام المعرفة المتخصصة في المجال',
                'action': 'applying_knowledge'
            })
        
        # خطوة 4: الاستنتاج
        steps.append({
            'step': 4,
            'thought': 'الوصول للحل الأمثل',
            'action': 'conclusion'
        })
        
        return {
            'steps': steps,
            'confidence': 0.9
        }
    
    def _use_neural_if_needed(self, intent: str, context: dict) -> Optional[dict]:
        """استخدام النماذج العصبية عند الحاجة"""
        # استيراد كسول (lazy import) للسرعة
        if intent in ['prediction', 'pricing', 'classification']:
            try:
                from services.ai_service import AIService
                
                if intent == 'pricing' and context.get('product_id'):
                    return AIService.predict_price_with_neural(
                        context['product_id'],
                        context.get('customer_id'),
                        context.get('quantity', 1)
                    )
                
                elif intent == 'prediction':
                    return AIService.forecast_sales_neural(days_ahead=7)
                
            except Exception as e:
                logger.debug(f"Neural model not used: {e}")
                return None
        
        return None
    
    def _synthesize_answer(self, question: str, reasoning: dict, neural: dict, 
                          knowledge: dict, intent: str) -> dict:
        """دمج كل المصادر في إجابة واحدة متكاملة"""
        
        answer_parts = []
        sources = []
        confidence = 0.85
        
        # إجابة من قاعدة المعرفة
        if knowledge:
            # محاسبة
            if 'principles' in knowledge:
                if 'استحقاق' in question.lower() or 'accrual' in question.lower():
                    answer_parts.append(f"📚 {knowledge['principles']['accrual']}")
                    sources.append('قاعدة المعرفة المحاسبية')
                    confidence = 0.98
                
                elif 'قيد مزدوج' in question.lower() or 'double entry' in question.lower():
                    answer_parts.append(f"📚 {knowledge['principles']['double_entry']}")
                    sources.append('المبادئ المحاسبية')
                    confidence = 1.0
            
            # الضرائب
            if 'vat' in knowledge or 'uae_vat' in knowledge:
                if 'ضريبة' in question.lower() or 'vat' in question.lower():
                    vat_info = knowledge.get('uae_vat', {})
                    answer_parts.append(f"💰 ضريبة القيمة المضافة في الإمارات: {vat_info.get('rate', 5)}%")
                    answer_parts.append(f"حد التسجيل: {vat_info.get('registration_threshold', 375000):,} درهم")
                    sources.append('قوانين الضرائب الإماراتية')
                    confidence = 1.0
            
            # كمبيوترات السيارات
            if 'sensors' in knowledge:
                for sensor_code, sensor_data in knowledge.get('sensors', {}).items():
                    if sensor_code.lower() in question.lower():
                        answer_parts.append(f"🚗 {sensor_data.get('name_ar', sensor_code)}")
                        answer_parts.append(f"الوظيفة: {sensor_data.get('function', '')}")
                        if 'testing' in sensor_data:
                            answer_parts.append(f"الفحص: {sensor_data['testing']}")
                        sources.append('خبير كمبيوترات السيارات - ECU')
                        confidence = 0.95
            
            # الصيغ
            if 'formulas' in knowledge:
                for formula_name, formula in knowledge['formulas'].items():
                    if any(kw in question.lower() for kw in formula_name.split('_')):
                        answer_parts.append(f"📐 {formula}")
                        sources.append('الصيغ المحاسبية')
                        confidence = 0.95
        
        # إجابة من النماذج العصبية
        if neural:
            if 'predicted_price' in neural:
                answer_parts.append(f"🧠 السعر المقترح (بالشبكات العصبية): {neural['predicted_price']:.2f} AED")
                answer_parts.append(f"الهامش: {neural.get('margin_percent', 0):.1f}%")
                answer_parts.append(f"الثقة: {neural.get('confidence', 0):.0%}")
                sources.append('الشبكة العصبية للتسعير')
                confidence = neural.get('confidence', 0.9)
            
            elif 'forecast' in neural:
                answer_parts.append(f"📈 توقع المبيعات (بالشبكات العصبية):")
                for day in neural.get('forecast', [])[:3]:
                    answer_parts.append(f"- {day.get('day_name', '')}: {day.get('amount', 0):,.0f} AED")
                sources.append('الشبكة العصبية للتوقعات')
                confidence = 0.94
        
        # إجابة عامة ذكية
        if not answer_parts:
            if intent == 'question':
                answer_parts.append("دعني أفكر في سؤالك بعمق...")
                answer_parts.append("للحصول على إجابة دقيقة، يمكنك:")
                answer_parts.append("1. تقديم معلومات إضافية")
                answer_parts.append("2. إعادة صياغة السؤال")
                answer_parts.append("3. تحديد المجال (محاسبة، ضرائب، إدارة، صيانة)")
                confidence = 0.6
            else:
                answer_parts.append("فهمت سؤالك. أنا مستعد لمساعدتك في:")
                answer_parts.append("📊 المحاسبة والمالية")
                answer_parts.append("💰 الضرائب والجمارك")
                answer_parts.append("📦 إدارة المخزون")
                answer_parts.append("🔧 الصيانة والهندسة")
                answer_parts.append("💼 الإدارة والتخطيط")
                confidence = 0.7
        
        return {
            'text': '\n'.join(answer_parts),
            'confidence': confidence,
            'sources': sources
        }
    
    def _remember(self, user_id: int, question: str, answer: str):
        """حفظ في الذاكرة الموحدة"""
        self.unified_memory['conversations'].append({
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'question': question,
            'answer': answer
        })
        
        # الاحتفاظ بآخر 100 فقط للسرعة
        if len(self.unified_memory['conversations']) > 100:
            self.unified_memory['conversations'] = self.unified_memory['conversations'][-100:]
    
    def _generate_smart_suggestions(self, intent: str, domain: str) -> List[str]:
        """توليد اقتراحات ذكية"""
        suggestions = {
            'accounting': [
                'احسب نسبة السيولة الجارية',
                'اشرح مبدأ الاستحقاق',
                'كيف أراجع قيد محاسبي؟'
            ],
            'taxes': [
                'احسب ضريبة القيمة المضافة',
                'ما حد التسجيل في VAT؟',
                'اشرح الرسوم الجمركية'
            ],
            'management': [
                'احسب نقطة إعادة الطلب',
                'ما هي الكمية الاقتصادية EOQ؟',
                'كيف أحلل المخزون بطريقة ABC؟'
            ],
            'engineering': [
                'كيف أشخص مشكلة المحرك؟',
                'متى أغير زيت المحرك؟',
                'ما أسباب ارتفاع الحرارة؟'
            ],
            'pricing': [
                'احسب السعر المثالي',
                'ما هامش الربح المناسب؟',
                'كيف أنافس في السوق؟'
            ]
        }
        
        return suggestions.get(domain, [
            'اسأل عن المحاسبة',
            'اسأل عن الضرائب',
            'اسأل عن المخزون'
        ])
    
    # ========================================================================
    # دوال متقدمة سريعة
    # ========================================================================
    
    def quick_calc(self, formula_name: str, **params) -> dict:
        """حسابات سريعة للصيغ الشائعة"""
        formulas = {
            'gross_margin': lambda sales, cogs: ((sales - cogs) / sales * 100) if sales > 0 else 0,
            'net_margin': lambda revenue, expenses: ((revenue - expenses) / revenue * 100) if revenue > 0 else 0,
            'current_ratio': lambda current_assets, current_liabilities: current_assets / current_liabilities if current_liabilities > 0 else 0,
            'eoq': lambda annual_demand, order_cost, holding_cost: (2 * annual_demand * order_cost / holding_cost) ** 0.5 if holding_cost > 0 else 0,
            'break_even': lambda fixed_costs, price, variable_cost: fixed_costs / (price - variable_cost) if (price - variable_cost) > 0 else 0,
            'vat': lambda amount: amount * 0.05,
            'price_with_vat': lambda amount: amount * 1.05,
            'price_without_vat': lambda amount_with_vat: amount_with_vat / 1.05
        }
        
        if formula_name in formulas:
            try:
                result = formulas[formula_name](**params)
                return {
                    'result': round(result, 2),
                    'formula': formula_name,
                    'params': params,
                    'success': True
                }
            except Exception as e:
                return {'error': str(e), 'success': False}
        
        return {'error': f'Unknown formula: {formula_name}', 'success': False}
    
    def explain(self, concept: str) -> str:
        """شرح مفهوم بسرعة"""
        # البحث في قاعدة المعرفة
        for domain_name, domain_data in self.knowledge_base.items():
            if isinstance(domain_data, dict):
                for key, value in domain_data.items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if concept.lower() in sub_key.lower():
                                return f"📚 {sub_value}"
                            if isinstance(sub_value, str) and concept.lower() in sub_value.lower():
                                return f"📚 {sub_value}"
        
        return f"🤔 لم أجد شرح مباشر لـ '{concept}'. يمكنك السؤال بشكل أكثر تحديداً؟"
    
    def validate_accounting_entry(self, debit: float, credit: float) -> dict:
        """التحقق من القيد المحاسبي بسرعة"""
        is_balanced = abs(debit - credit) < 0.01
        
        return {
            'is_balanced': is_balanced,
            'debit': debit,
            'credit': credit,
            'difference': abs(debit - credit),
            'status': '✅ متوازن' if is_balanced else '❌ غير متوازن',
            'confidence': 1.0 if is_balanced else 0.0,
            'principle': 'القيد المزدوج - المدين = الدائن',
            'recommendation': 'يمكن اعتماده' if is_balanced else 'راجع الأرقام'
        }


# ============================================================================
# Singleton للسرعة
# ============================================================================

_master_brain_instance = None

def get_master_brain():
    """الحصول على العقل الرئيسي - Singleton للسرعة"""
    global _master_brain_instance
    if _master_brain_instance is None:
        _master_brain_instance = MasterBrain()
    return _master_brain_instance


# ============================================================================
# API بسيط وسريع
# ============================================================================

def ask_azad(question: str, context: dict = None, user_id: int = None) -> dict:
    """
    اسأل أزاد - الواجهة البسيطة
    
    مثال:
        result = ask_azad("ما هي ضريبة القيمة المضافة في الإمارات؟")
        print(result['answer'])
    """
    brain = get_master_brain()
    return brain.ask(question, context, user_id)


def quick_calc(formula: str, **params) -> dict:
    """
    حسابات سريعة
    
    مثال:
        result = quick_calc('vat', amount=1000)
        print(f"الضريبة: {result['result']} درهم")
    """
    brain = get_master_brain()
    return brain.quick_calc(formula, **params)


def explain_concept(concept: str) -> str:
    """
    شرح سريع لمفهوم
    
    مثال:
        explanation = explain_concept('مبدأ الاستحقاق')
        print(explanation)
    """
    brain = get_master_brain()
    return brain.explain(concept)

