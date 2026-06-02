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

