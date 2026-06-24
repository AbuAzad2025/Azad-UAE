"""
Consolidated module: core_engine.py
Merged: core/context_engine.py, core/conversation_manager.py, core/memory_system.py, core/system_integration.py, core/learning_system.py, core/reasoning_engine.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: core/context_engine.py =====
"""
🧠 محرك السياق الذكي - Context Engine
يفهم السياق ويربط جميع ملفات المعرفة والمحركات
"""
import logging

from ai_knowledge.analytics.data_analyzer import data_analyzer
from ai_knowledge.expansion.global_knowledge import global_connector
from ai_knowledge.expansion.knowledge_expansion import knowledge_expander
from ai_knowledge.generation.document_generator import document_generator
from ai_knowledge.specialized.advanced_laws import advanced_laws

_context_logger = logging.getLogger(__name__)


class ContextEngine:
    """محرك السياق الذكي"""
    
    @staticmethod
    def analyze_context(message, context=None):
        """
        تحليل السياق والرسالة لفهم النية
        Returns: dict with intent, entities, context_data
        """
        msg_lower = message.lower()
        
        # استخراج الكيانات المهمة
        entities = {
            'customer_name': None,
            'product_name': None,
            'date_range': None,
            'amount': None,
            'user_name': None
        }
        
        # تحديد النية الأساسية
        intent = ContextEngine._detect_intent(msg_lower)
        
        # جمع البيانات السياقية
        context_data = {
            'user_role': context.get('is_owner', False) if context else False,
            'previous_interactions': [],  # سيتم تطويره لاحقاً
            'system_state': system_integrator.get_system_summary() if intent in ['analysis', 'data_query'] else None
        }
        
        return {
            'intent': intent,
            'entities': entities,
            'context_data': context_data,
            'confidence': 0.8
        }
    
    @staticmethod
    def _detect_intent(msg_lower):
        """كشف النية من الرسالة"""
        intents = {
            'greeting': ['مرحبا', 'أهلا', 'السلام', 'hello', 'hi'],
            'help': ['مساعدة', 'help', 'كيف', 'how', 'شرح', 'explain'],
            'analysis': ['حلل', 'تحليل', 'analyze', 'analysis', 'تقرير', 'report'],
            'data_query': ['كم', 'ما هو', 'what', 'how many', 'how much', 'أعطني', 'give me'],
            'security': ['كلمة المرور', 'password', 'مستخدم', 'user', 'صلاحيات', 'permissions'],
            'tax_customs': ['ضريبة', 'tax', 'جمارك', 'customs', 'vat'],
            'parts': ['قطعة', 'part', 'محرك', 'engine', 'بستم', 'piston'],
            'prediction': ['توقع', 'predict', 'تنبؤ', 'forecast'],
            'create': ['أنشئ', 'create', 'اعمل', 'make', 'وثيقة', 'document'],
            'search': ['ابحث', 'search', 'أين أجد', 'where to find']
        }
        
        for intent, keywords in intents.items():
            if any(kw in msg_lower for kw in keywords):
                return intent
        
        return 'general'
    
    @staticmethod
    def enhance_response(message, basic_response, context=None):
        """
        تحسين الرد باستخدام جميع المحركات المتاحة
        """
        analysis = ContextEngine.analyze_context(message, context)
        intent = analysis['intent']
        
        enhanced = basic_response
        additional_info = []
        
        # إضافة معلومات حسب النية
        if intent == 'analysis':
            # استخدام محرك التحليل
            try:
                financial_data = data_analyzer.get_financial_ratios()
                if financial_data.get('success'):
                    additional_info.append("\n\n📊 **معلومات إضافية:**")
                    ratios = financial_data.get('ratios', {})
                    if ratios:
                        additional_info.append(f"• هامش الربح الإجمالي: {ratios.get('gross_profit_margin', 0):.1f}%")
                        additional_info.append(f"• هامش الربح الصافي: {ratios.get('net_profit_margin', 0):.1f}%")
            except Exception as exc:
                _context_logger.debug('Financial ratios enrichment failed: %s', exc)
        
        elif intent == 'data_query':
            # استخدام محرك التكامل
            try:
                summary = system_integrator.get_system_summary()
                if summary.get('success'):
                    sys_data = summary.get('summary', {})
                    additional_info.append("\n\n📈 **حالة النظام:**")
                    additional_info.append(f"• إجمالي العملاء: {sys_data.get('total_customers', 0)}")
                    additional_info.append(f"• إجمالي المنتجات: {sys_data.get('total_products', 0)}")
                    additional_info.append(f"• المبيعات اليوم: {sys_data.get('today_sales', 0)} درهم")
            except Exception as exc:
                _context_logger.debug('System summary enrichment failed: %s', exc)
        
        elif intent == 'prediction':
            # استخدام التحليلات التنبؤية
            additional_info.append("\n\n🔮 **يمكنني مساعدتك في:**")
            additional_info.append("• توقع المبيعات للأيام القادمة")
            additional_info.append("• تحليل اتجاهات المخزون")
            additional_info.append("• توقع التدفق النقدي")
        
        elif intent == 'create':
            # استخدام مولد الوثائق
            additional_info.append("\n\n📝 **يمكنني إنشاء:**")
            additional_info.append("• تقارير مالية مفصلة")
            additional_info.append("• تحليلات للعملاء والمنتجات")
            additional_info.append("• وثائق مخصصة حسب طلبك")
        
        elif intent == 'search':
            # استخدام محرك المعرفة الموسعة
            try:
                search_results = knowledge_expander.search_knowledge(message)
                if search_results.get('success') and search_results.get('results'):
                    additional_info.append("\n\n🔍 **نتائج البحث في قاعدة المعرفة:**")
                    for result in search_results['results'][:3]:
                        additional_info.append(f"• {result.get('title', 'نتيجة')}")
            except Exception as exc:
                _context_logger.debug('Knowledge search enrichment failed: %s', exc)
        
        # إضافة رؤى من التعلم الذاتي
        try:
            learning_insights = learning_system.get_learning_insights()
            if learning_insights.get('total_interactions', 0) > 10:
                additional_info.append("\n\n💡 **من خبرتي معك:**")
                top_topic = learning_insights.get('top_topics', [{}])[0] if learning_insights.get('top_topics') else {}
                if top_topic:
                    additional_info.append(f"• أكثر موضوع تهتم به: {top_topic.get('topic', 'غير محدد')}")
        except Exception as exc:
            _context_logger.debug('Learning insights enrichment failed: %s', exc)
        
        # دمج المعلومات الإضافية
        if additional_info:
            enhanced += '\n'.join(additional_info)
        
        return enhanced
    
    @staticmethod
    def get_smart_suggestions(message, context=None):
        """
        اقتراحات ذكية بناءً على السياق
        """
        analysis = ContextEngine.analyze_context(message, context)
        intent = analysis['intent']
        
        suggestions = []
        
        if intent == 'analysis':
            suggestions = [
                "حلل المبيعات للأسبوع الماضي",
                "ما هي هوامش الربح؟",
                "أعطني تقرير المخزون"
            ]
        elif intent == 'data_query':
            suggestions = [
                "كم عدد العملاء النشطين؟",
                "ما هي أفضل المنتجات مبيعاً؟",
                "أعطني حالة المخزون"
            ]
        elif intent == 'help':
            suggestions = [
                "كيف أنشئ فاتورة؟",
                "كيف أضيف منتج؟",
                "دليل النظام الكامل"
            ]
        else:
            suggestions = [
                "حلل المبيعات",
                "روابط النظام",
                "مصادر موثوقة"
            ]
        
        return suggestions


# إنشاء نسخة عامة
context_engine = ContextEngine()



# ===== Consolidated from: core/conversation_manager.py =====
"""
💬 مدير المحادثات المتقدم - Advanced Conversation Manager
محادثات طبيعية على طريقة ChatGPT

القدرات:
- محادثات سياقية
- تذكر السياق
- ردود طبيعية
- أسلوب محترف
- تعدد اللغات
"""

import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    مدير المحادثات المتقدم
    
    يدير:
    - السياق في المحادثة
    - التاريخ
    - الانتقالات الطبيعية
    - الشخصية المتسقة
    """
    
    def __init__(self):
        self.active_conversations = {}  # {user_id: conversation_data}
        self.conversation_styles = {
            'professional': 'احترافي وواضح',
            'friendly': 'ودود ومرح',
            'technical': 'تقني ومفصل',
            'simple': 'بسيط ومباشر'
        }
    
    def start_conversation(self, user_id: int, user_info: dict = None) -> dict:
        """بدء محادثة جديدة"""
        self.active_conversations[user_id] = {
            'user_id': user_id,
            'user_info': user_info or {},
            'started_at': datetime.now().isoformat(),
            'messages': [],
            'context': {},
            'style': 'professional'  # افتراضي
        }
        
        greeting = self._generate_greeting(user_info)
        
        return {
            'conversation_id': user_id,
            'greeting': greeting,
            'status': 'active'
        }
    
    def _generate_greeting(self, user_info: dict) -> str:
        """توليد تحية مخصصة"""
        name = user_info.get('name', 'عزيزي') if user_info else 'عزيزي'
        
        hour = datetime.now().hour
        
        if hour < 12:
            time_greeting = "صباح الخير"
        elif hour < 17:
            time_greeting = "مساء الخير"
        else:
            time_greeting = "مساء الخير"
        
        greeting = f"{time_greeting} {name}! 👋\n\n"
        greeting += "أنا أزاد، مساعدك الذكي المتخصص في:\n"
        greeting += "🔧 الصيانة والمعدات\n"
        greeting += "📊 المحاسبة والمالية\n"
        greeting += "💼 إدارة الأعمال\n"
        greeting += "📈 التحليلات والتوقعات\n\n"
        greeting += "كيف يمكنني مساعدتك اليوم؟"
        
        return greeting
    
    def process_message(self, user_id: int, message: str) -> dict:
        """
        معالجة رسالة في محادثة نشطة
        
        Returns:
            {
                'response': الرد,
                'context_updated': bool,
                'suggestions': اقتراحات للمتابعة
            }
        """
        # التأكد من وجود محادثة نشطة
        if user_id not in self.active_conversations:
            self.start_conversation(user_id)
        
        conversation = self.active_conversations[user_id]
        
        # إضافة الرسالة للتاريخ
        conversation['messages'].append({
            'timestamp': datetime.now().isoformat(),
            'role': 'user',
            'content': message
        })
        
        # تحليل النية
        intent, entities = self._analyze_intent(message)
        
        # تحديث السياق
        self._update_context(user_id, intent, entities)
        
        # توليد الرد
        response = self._generate_response(user_id, message, intent, entities)
        
        # إضافة الرد للتاريخ
        conversation['messages'].append({
            'timestamp': datetime.now().isoformat(),
            'role': 'assistant',
            'content': response['text']
        })
        
        # توليد اقتراحات للمتابعة
        suggestions = self._generate_suggestions(intent, entities)
        
        # حفظ في الذاكرة طويلة المدى
        self._save_to_long_term_memory(user_id, message, response['text'])
        
        return {
            'response': response['text'],
            'context_updated': True,
            'suggestions': suggestions,
            'intent': intent,
            'confidence': response['confidence']
        }
    
    def _analyze_intent(self, message: str) -> tuple:
        """تحليل النية من الرسالة"""
        message_lower = message.lower()
        
        # تحديد النية
        if any(kw in message_lower for kw in ['سعر', 'price', 'كم', 'how much']):
            intent = 'pricing_query'
        elif any(kw in message_lower for kw in ['توقع', 'predict', 'متوقع', 'forecast']):
            intent = 'prediction_query'
        elif any(kw in message_lower for kw in ['محاسبة', 'قيد', 'accounting', 'journal']):
            intent = 'accounting_query'
        elif any(kw in message_lower for kw in ['صيانة', 'maintenance', 'إصلاح', 'repair']):
            intent = 'maintenance_query'
        elif any(kw in message_lower for kw in ['مخزون', 'inventory', 'stock']):
            intent = 'inventory_query'
        elif any(kw in message_lower for kw in ['عميل', 'customer', 'زبون']):
            intent = 'customer_query'
        elif any(kw in message_lower for kw in ['كيف', 'how', 'طريقة', 'method']):
            intent = 'howto_query'
        else:
            intent = 'general_query'
        
        # استخراج الكيانات (entities)
        entities = {}
        
        # أرقام
        import re
        numbers = re.findall(r'\d+', message)
        if numbers:
            entities['numbers'] = numbers
        
        # كلمات مفتاحية
        if 'منتج' in message_lower:
            entities['entity_type'] = 'product'
        elif 'عميل' in message_lower:
            entities['entity_type'] = 'customer'
        
        return intent, entities
    
    def _update_context(self, user_id: int, intent: str, entities: dict):
        """تحديث سياق المحادثة"""
        conversation = self.active_conversations[user_id]
        
        # تحديث السياق
        conversation['context']['last_intent'] = intent
        conversation['context']['last_entities'] = entities
        conversation['context']['updated_at'] = datetime.now().isoformat()
        
        # الاحتفاظ بتاريخ النيات
        if 'intent_history' not in conversation['context']:
            conversation['context']['intent_history'] = []
        
        conversation['context']['intent_history'].append(intent)
        
        # الاحتفاظ بآخر 10 نيات فقط
        if len(conversation['context']['intent_history']) > 10:
            conversation['context']['intent_history'] = conversation['context']['intent_history'][-10:]
    
    def _generate_response(self, user_id: int, message: str, intent: str, entities: dict) -> dict:
        """توليد الرد المناسب"""
        conversation = self.active_conversations[user_id]
        style = conversation.get('style', 'professional')
        
        # استخدام الأنظمة الذكية المتاحة
        try:
            if intent == 'pricing_query':
                # استخدام Neural Network
                # from services.ai_service import AIService
                
                response_text = "دعني أحلل السعر الأمثل باستخدام الشبكات العصبية...\n\n"
                
                # يمكن إضافة منطق التسعير هنا
                response_text += "للحصول على سعر دقيق، أحتاج:\n"
                response_text += "- معرف المنتج\n"
                response_text += "- نوع العميل\n"
                response_text += "- الكمية المطلوبة"
                
                confidence = 0.8
            
            elif intent == 'prediction_query':
                response_text = "يمكنني التوقع باستخدام 11 نموذج عصبي مدرب:\n\n"
                response_text += "📈 توقع المبيعات\n"
                response_text += "📦 توقع الطلب\n"
                response_text += "💰 توقع التدفق النقدي\n"
                response_text += "🚪 توقع خسارة العملاء\n\n"
                response_text += "ما نوع التوقع الذي تحتاجه؟"
                
                confidence = 0.9
            
            elif intent == 'maintenance_query':
                response_text = "كمهندس صيانة، يمكنني مساعدتك في:\n\n"
                response_text += "🔧 تشخيص الأعطال\n"
                response_text += "⚙️ توقع موعد الصيانة\n"
                response_text += "🔩 توصيات قطع الغيار\n"
                response_text += "📋 جدولة الصيانة الوقائية\n\n"
                response_text += "ما المشكلة التقنية؟"
                
                confidence = 0.85
            
            elif intent == 'accounting_query':
                response_text = "كمحاسب قانوني، أستطيع:\n\n"
                response_text += "✅ مراجعة القيود المحاسبية\n"
                response_text += "📊 إعداد القوائم المالية\n"
                response_text += "🔍 التدقيق والمراجعة\n"
                response_text += "📈 تحليل النسب المالية\n\n"
                response_text += "ما الذي تحتاج مراجعته؟"
                
                confidence = 0.95
            
            else:
                response_text = "فهمت سؤالك. دعني أفكر في أفضل إجابة...\n\n"
                response_text += f"السؤال يتعلق بـ: {intent}\n"
                response_text += "هل يمكنك تقديم تفاصيل أكثر؟"
                
                confidence = 0.6
            
            return {
                'text': response_text,
                'confidence': confidence,
                'style': style
            }
        
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return {
                'text': "عذراً، حدث خطأ. يمكنك إعادة صياغة السؤال؟",
                'confidence': 0.3,
                'style': style
            }
    
    def _generate_suggestions(self, intent: str, entities: dict) -> List[str]:
        """توليد اقتراحات للمتابعة"""
        suggestions = []
        
        if intent == 'pricing_query':
            suggestions = [
                "احسب السعر لمنتج محدد",
                "قارن الأسعار بين منتجات",
                "اعرض استراتيجية التسعير"
            ]
        
        elif intent == 'prediction_query':
            suggestions = [
                "توقع المبيعات لأسبوع قادم",
                "توقع التدفق النقدي",
                "توقع نفاذ المخزون"
            ]
        
        elif intent == 'maintenance_query':
            suggestions = [
                "جدول الصيانة الوقائية",
                "قائمة قطع الغيار المطلوبة",
                "تقدير تكاليف الصيانة"
            ]
        
        else:
            suggestions = [
                "اسأل عن المبيعات",
                "اسأل عن المخزون",
                "اسأل عن العملاء"
            ]
        
        return suggestions[:3]  # أول 3 فقط
    
    def _save_to_long_term_memory(self, user_id: int, message: str, response: str):
        """حفظ في الذاكرة طويلة المدى"""
        try:
            from ai_knowledge.core.memory_system import get_memory_system
            
            memory = get_memory_system()
            memory.remember_conversation(user_id, message, response)
        
        except Exception as e:
            logger.error(f"Failed to save to long-term memory: {e}")
    
    def get_conversation_history(self, user_id: int, limit: int = 10) -> List[dict]:
        """الحصول على تاريخ المحادثة"""
        if user_id not in self.active_conversations:
            return []
        
        messages = self.active_conversations[user_id]['messages']
        return messages[-limit:] if messages else []
    
    def end_conversation(self, user_id: int) -> dict:
        """إنهاء محادثة"""
        if user_id in self.active_conversations:
            conversation = self.active_conversations[user_id]
            
            summary = {
                'user_id': user_id,
                'started_at': conversation['started_at'],
                'ended_at': datetime.now().isoformat(),
                'messages_count': len(conversation['messages']),
                'topics': list(set(conversation['context'].get('intent_history', [])))
            }
            
            # حذف من الذاكرة النشطة
            del self.active_conversations[user_id]
            
            farewell = "شكراً لاستخدامك المساعد أزاد! 🌟\n"
            farewell += "سعيد بخدمتك دائماً.\n"
            farewell += "إلى اللقاء! 👋"
            
            return {
                'summary': summary,
                'farewell': farewell
            }
        
        return {'error': 'No active conversation'}


# ============================================================================
# Singleton
# ============================================================================

_conversation_manager_instance = None

def get_conversation_manager():
    """الحصول على مدير المحادثات"""
    global _conversation_manager_instance
    if _conversation_manager_instance is None:
        _conversation_manager_instance = ConversationManager()
    return _conversation_manager_instance



# ===== Consolidated from: core/memory_system.py =====
"""
🧠 نظام الذاكرة طويلة المدى - Long-term Memory System
ذاكرة متقدمة على طريقة ChatGPT

القدرات:
- تذكر المحادثات السابقة
- تذكر تفضيلات المستخدمين
- تذكر السياق طويل المدى
- الربط بين المعلومات
- الاسترجاع الذكي
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    نظام الذاكرة طويلة المدى
    
    أنواع الذاكرة:
    1. Episodic Memory (ذاكرة الأحداث) - المحادثات
    2. Semantic Memory (ذاكرة المعاني) - المعرفة العامة
    3. Procedural Memory (ذاكرة الإجراءات) - كيف تفعل الأشياء
    4. User Preferences (تفضيلات المستخدمين)
    """
    
    def __init__(self):
        from ai_knowledge import get_knowledge_path
        self.memory_dir = get_knowledge_path('memory')
        self.ensure_memory_dir()
        
        # أنواع الذاكرة
        self.episodic_memory = self._load_memory('episodic')  # المحادثات
        self.semantic_memory = self._load_memory('semantic')  # المعرفة
        self.procedural_memory = self._load_memory('procedural')  # الإجراءات
        self.user_preferences = self._load_memory('preferences')  # التفضيلات
        
        # فهرس للبحث السريع
        self.memory_index = defaultdict(list)
        self._build_index()
    
    def ensure_memory_dir(self):
        """التأكد من وجود مجلد الذاكرة"""
        if not os.path.exists(self.memory_dir):
            os.makedirs(self.memory_dir)
    
    def _load_memory(self, memory_type):
        """تحميل نوع محدد من الذاكرة"""
        file_path = os.path.join(self.memory_dir, f'{memory_type}_memory.json')
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug('Could not load %s memory: %s', memory_type, exc)
        
        return {'memories': [], 'metadata': {'created': datetime.now().isoformat()}}
    
    def _save_memory(self, memory_type, data):
        """حفظ الذاكرة"""
        file_path = os.path.join(self.memory_dir, f'{memory_type}_memory.json')
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save {memory_type} memory: {e}")
            return False
    
    def remember_conversation(self, user_id, message, response, context=None):
        """
        تذكر محادثة (Episodic Memory)
        
        يحفظ:
        - من قال ماذا
        - متى
        - السياق
        - النتيجة
        """
        memory_entry = {
            'id': len(self.episodic_memory['memories']) + 1,
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'user_message': message,
            'assistant_response': response,
            'context': context or {},
            'type': 'conversation'
        }
        
        self.episodic_memory['memories'].append(memory_entry)
        
        # الاحتفاظ بآخر 1000 محادثة فقط
        if len(self.episodic_memory['memories']) > 1000:
            self.episodic_memory['memories'] = self.episodic_memory['memories'][-1000:]
        
        # حفظ
        self._save_memory('episodic', self.episodic_memory)
        
        # تحديث الفهرس
        self._add_to_index(message, memory_entry['id'], 'episodic')
        
        logger.info(f"💭 Remembered conversation for user {user_id}")
    
    def remember_fact(self, fact, category, source=None):
        """
        تذكر معلومة (Semantic Memory)
        
        معلومات عامة مثل:
        - "ضريبة القيمة المضافة في الإمارات 5%"
        - "قطعة X تتوافق مع محرك Y"
        """
        memory_entry = {
            'id': len(self.semantic_memory['memories']) + 1,
            'timestamp': datetime.now().isoformat(),
            'fact': fact,
            'category': category,
            'source': source,
            'type': 'fact'
        }
        
        self.semantic_memory['memories'].append(memory_entry)
        self._save_memory('semantic', self.semantic_memory)
        
        self._add_to_index(fact, memory_entry['id'], 'semantic')
        
        logger.info(f"📚 Remembered fact: {fact[:50]}...")
    
    def remember_procedure(self, procedure_name, steps, category='general'):
        """
        تذكر إجراء (Procedural Memory)
        
        كيفية فعل الأشياء:
        - "كيف تنشئ فاتورة"
        - "كيف تصلح محرك"
        """
        memory_entry = {
            'id': len(self.procedural_memory['memories']) + 1,
            'timestamp': datetime.now().isoformat(),
            'procedure': procedure_name,
            'steps': steps,
            'category': category,
            'type': 'procedure'
        }
        
        self.procedural_memory['memories'].append(memory_entry)
        self._save_memory('procedural', self.procedural_memory)
        
        self._add_to_index(procedure_name, memory_entry['id'], 'procedural')
        
        logger.info(f"📋 Remembered procedure: {procedure_name}")
    
    def remember_user_preference(self, user_id, preference_key, preference_value):
        """
        تذكر تفضيل مستخدم
        
        مثل:
        - اللغة المفضلة
        - اللهجة المفضلة
        - أسلوب الرد
        - المواضيع المهتم بها
        """
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {
                'user_id': user_id,
                'preferences': {},
                'created': datetime.now().isoformat()
            }
        
        self.user_preferences[user_id]['preferences'][preference_key] = preference_value
        self.user_preferences[user_id]['updated'] = datetime.now().isoformat()
        
        self._save_memory('preferences', self.user_preferences)
        
        logger.info(f"⚙️ Remembered preference for user {user_id}: {preference_key}")
    
    def recall_conversations(self, user_id, limit=10):
        """
        استرجاع المحادثات السابقة مع مستخدم
        
        للحفاظ على السياق في المحادثات الطويلة
        """
        user_conversations = [
            mem for mem in self.episodic_memory['memories']
            if mem.get('user_id') == user_id
        ]
        
        # الأحدث أولاً
        user_conversations.reverse()
        
        return user_conversations[:limit]
    
    def recall_similar_conversations(self, query, limit=5):
        """
        استرجاع محادثات مشابهة
        
        للتعلم من التجارب السابقة
        """
        # بحث بسيط في الكلمات المفتاحية
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        similar = []
        
        for memory in self.episodic_memory['memories']:
            message = memory.get('user_message', '').lower()
            message_words = set(message.split())
            
            # حساب التشابه (Jaccard similarity)
            intersection = query_words & message_words
            union = query_words | message_words
            
            similarity = len(intersection) / len(union) if union else 0
            
            if similarity > 0.2:  # عتبة التشابه
                similar.append({
                    'memory': memory,
                    'similarity': similarity
                })
        
        # الترتيب حسب التشابه
        similar.sort(key=lambda x: x['similarity'], reverse=True)
        
        return [s['memory'] for s in similar[:limit]]
    
    def recall_fact(self, query, category=None):
        """
        استرجاع معلومة محفوظة
        """
        relevant_facts = []
        
        query_lower = query.lower()
        
        for memory in self.semantic_memory['memories']:
            if category and memory.get('category') != category:
                continue
            
            fact = memory.get('fact', '').lower()
            
            if any(word in fact for word in query_lower.split()):
                relevant_facts.append(memory)
        
        return relevant_facts
    
    def recall_procedure(self, procedure_name):
        """
        استرجاع إجراء محفوظ
        
        "كيف أفعل X؟"
        """
        procedure_name_lower = procedure_name.lower()
        
        for memory in self.procedural_memory['memories']:
            if procedure_name_lower in memory.get('procedure', '').lower():
                return memory
        
        return None
    
    def get_user_preferences(self, user_id):
        """الحصول على تفضيلات مستخدم"""
        return self.user_preferences.get(user_id, {}).get('preferences', {})
    
    def _build_index(self):
        """بناء فهرس للبحث السريع"""
        # فهرسة المحادثات
        for idx, memory in enumerate(self.episodic_memory['memories']):
            message = memory.get('user_message', '')
            for word in message.lower().split():
                if len(word) > 3:  # تجاهل الكلمات القصيرة
                    self.memory_index[word].append(('episodic', idx))
        
        # فهرسة المعلومات
        for idx, memory in enumerate(self.semantic_memory['memories']):
            fact = memory.get('fact', '')
            for word in fact.lower().split():
                if len(word) > 3:
                    self.memory_index[word].append(('semantic', idx))
    
    def _add_to_index(self, text, memory_id, memory_type):
        """إضافة إلى الفهرس"""
        for word in text.lower().split():
            if len(word) > 3:
                self.memory_index[word].append((memory_type, memory_id))
    
    def search_memory(self, query, limit=10):
        """
        بحث شامل في جميع أنواع الذاكرة
        
        Returns:
            {
                'conversations': [...],
                'facts': [...],
                'procedures': [...]
            }
        """
        results = {
            'conversations': [],
            'facts': [],
            'procedures': []
        }
        
        # البحث في المحادثات
        results['conversations'] = self.recall_similar_conversations(query, limit)
        
        # البحث في المعلومات
        results['facts'] = self.recall_fact(query)[:limit]
        
        # البحث في الإجراءات
        for memory in self.procedural_memory['memories']:
            if query.lower() in memory.get('procedure', '').lower():
                results['procedures'].append(memory)
        
        results['procedures'] = results['procedures'][:limit]
        
        return results
    
    def forget_old_memories(self, days=365):
        """
        نسيان الذاكرة القديمة جداً
        
        للحفاظ على الأداء
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.isoformat()
        
        # تنظيف المحادثات القديمة
        original_count = len(self.episodic_memory['memories'])
        self.episodic_memory['memories'] = [
            mem for mem in self.episodic_memory['memories']
            if mem.get('timestamp', '') > cutoff_str
        ]
        
        deleted = original_count - len(self.episodic_memory['memories'])
        
        if deleted > 0:
            self._save_memory('episodic', self.episodic_memory)
            logger.info(f"🗑️ Forgot {deleted} old conversations (>{days} days)")
        
        return {'deleted': deleted, 'remaining': len(self.episodic_memory['memories'])}
    
    def consolidate_memories(self):
        """
        دمج الذاكرة المتشابهة
        
        للحفاظ على الكفاءة
        """
        # تجميع المحادثات المتشابهة
        # (يمكن تطويره لاحقاً باستخدام ML)
        pass
    
    def get_memory_stats(self):
        """إحصائيات الذاكرة"""
        return {
            'episodic': {
                'count': len(self.episodic_memory['memories']),
                'oldest': self.episodic_memory['memories'][0]['timestamp'] if self.episodic_memory['memories'] else None,
                'newest': self.episodic_memory['memories'][-1]['timestamp'] if self.episodic_memory['memories'] else None
            },
            'semantic': {
                'count': len(self.semantic_memory['memories'])
            },
            'procedural': {
                'count': len(self.procedural_memory['memories'])
            },
            'user_preferences': {
                'users_count': len(self.user_preferences)
            },
            'total_memories': (
                len(self.episodic_memory['memories']) +
                len(self.semantic_memory['memories']) +
                len(self.procedural_memory['memories'])
            )
        }


# ============================================================================
# Singleton
# ============================================================================

_memory_instance = None

def get_memory_system():
    """الحصول على نظام الذاكرة"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = LongTermMemory()
    return _memory_instance



# ===== Consolidated from: core/system_integration.py =====
"""
🔗 تكامل النظام - System Integration
أزاد يتفاعل مباشرة مع النظام
"""

from datetime import datetime, timedelta
from decimal import Decimal
import json


class SystemIntegrator:
    """مكامل النظام لأزاد"""
    
    def __init__(self):
        pass
    
    def get_customer_balance(self, customer_name_or_id):
        """الحصول على رصيد العميل"""
        try:
            from models import Customer, Sale
            
            # البحث بالاسم أو المعرف
            if customer_name_or_id.isdigit():
                customer = Customer.query.get(int(customer_name_or_id))
            else:
                customer = Customer.query.filter(
                    Customer.name.ilike(f'%{customer_name_or_id}%')
                ).first()
            
            if not customer:
                return {
                    'success': False,
                    'error': f'العميل "{customer_name_or_id}" غير موجود'
                }
            
            # حساب الرصيد - استخدام الدالة الصحيحة
            balance_aed = customer.get_balance_aed()  # ✅ تم التحديث 2025-10-19
            total_sales = customer.sales.count()
            last_sale = customer.sales.order_by(Sale.created_at.desc()).first()
            
            return {
                'success': True,
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                    'balance_aed': float(balance_aed),
                    'total_sales': total_sales,
                    'last_sale_date': last_sale.created_at.strftime('%Y-%m-%d') if last_sale else None,
                    'customer_type': customer.customer_type,
                    'phone': customer.phone,
                    'email': customer.email
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في جلب بيانات العميل: {str(e)}'
            }
    
    def get_supplier_balance(self, supplier_name_or_id):
        """الحصول على رصيد المورد - ✅ جديد 2025-10-19"""
        try:
            from models import Supplier, Purchase
            
            # البحث بالاسم أو المعرف
            if str(supplier_name_or_id).isdigit():
                supplier = Supplier.query.get(int(supplier_name_or_id))
            else:
                supplier = Supplier.query.filter(
                    Supplier.name.ilike(f'%{supplier_name_or_id}%')
                ).first()
            
            if not supplier:
                return {
                    'success': False,
                    'error': f'المورد "{supplier_name_or_id}" غير موجود'
                }
            
            # حساب الرصيد - استخدام الدالة المحدثة
            balance_aed = supplier.get_balance_aed()  # ✅ الدالة الصحيحة
            total_purchases = supplier.purchases.count()
            last_purchase = supplier.purchases.order_by(Purchase.created_at.desc()).first()
            
            return {
                'success': True,
                'supplier': {
                    'id': supplier.id,
                    'name': supplier.name,
                    'balance_aed': float(balance_aed),
                    'total_purchases': total_purchases,
                    'last_purchase_date': last_purchase.created_at.strftime('%Y-%m-%d') if last_purchase else None,
                    'supplier_type': supplier.supplier_type,
                    'phone': supplier.phone,
                    'email': supplier.email
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في جلب بيانات المورد: {str(e)}'
            }
    
    def get_customer_sales_summary(self, customer_id):
        """ملخص مبيعات العميل"""
        try:
            from models import Customer
            
            customer = Customer.query.get(customer_id)
            if not customer:
                return {'success': False, 'error': 'العميل غير موجود'}
            
            # إحصائيات المبيعات
            sales = customer.sales.all()
            total_sales = len(sales)
            total_amount = sum(float(sale.total_amount) for sale in sales)
            paid_amount = sum(float(sale.paid_amount) for sale in sales)
            balance_due = total_amount - paid_amount
            
            # آخر 5 مبيعات
            recent_sales = sales[-5:] if sales else []
            
            return {
                'success': True,
                'summary': {
                    'total_sales': total_sales,
                    'total_amount': total_amount,
                    'paid_amount': paid_amount,
                    'balance_due': balance_due,
                    'recent_sales': [
                        {
                            'id': sale.id,
                            'date': sale.created_at.strftime('%Y-%m-%d'),
                            'amount': float(sale.total_amount),
                            'status': 'مدفوع' if sale.paid_amount >= sale.total_amount else 'جزئي' if sale.paid_amount > 0 else 'غير مدفوع'
                        }
                        for sale in recent_sales
                    ]
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في جلب ملخص المبيعات: {str(e)}'
            }
    
    def add_customer(self, customer_data):
        """إضافة عميل جديد"""
        try:
            from models import Customer
            from extensions import db
            
            # التحقق من البيانات المطلوبة
            required_fields = ['name', 'customer_type']
            for field in required_fields:
                if field not in customer_data or not customer_data[field]:
                    return {
                        'success': False,
                        'error': f'المجال "{field}" مطلوب'
                    }
            
            # تحديد التينانت
            from models.tenant import Tenant
            tenant = Tenant.get_current()
            tenant_id = tenant.id if tenant else customer_data.get('tenant_id')
            if not tenant_id:
                return {
                    'success': False,
                    'error': 'لا يوجد تينانت نشط — يرجى تسجيل الدخول لشركة محددة'
                }

            # إنشاء العميل
            customer = Customer(
                tenant_id=tenant_id,
                name=customer_data['name'],
                customer_type=customer_data['customer_type'],
                phone=customer_data.get('phone', ''),
                email=customer_data.get('email', ''),
                address=customer_data.get('address', ''),
                credit_limit=customer_data.get('credit_limit', 0)
            )
            
            db.session.add(customer)
            db.session.commit()
            
            return {
                'success': True,
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                    'customer_type': customer.customer_type,
                    'phone': customer.phone,
                    'email': customer.email
                },
                'message': f'تم إضافة العميل "{customer.name}" بنجاح'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': f'خطأ في إضافة العميل: {str(e)}'
            }
    
    def get_product_stock(self, product_name_or_sku):
        """الحصول على مخزون المنتج"""
        try:
            from models import Product
            
            # البحث بالاسم أو SKU
            product = Product.query.filter(
                (Product.name.ilike(f'%{product_name_or_sku}%')) |
                (Product.sku.ilike(f'%{product_name_or_sku}%'))
            ).first()
            
            if not product:
                return {
                    'success': False,
                    'error': f'المنتج "{product_name_or_sku}" غير موجود'
                }
            
            return {
                'success': True,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'sku': product.sku,
                    'current_stock': product.current_stock,
                    'alert_limit': product.min_stock_alert,
                    'unit_price': float(product.unit_price),
                    'category': product.category.name if product.category else 'غير محدد',
                    'status': 'منخفض' if product.current_stock <= product.min_stock_alert else 'جيد'
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في جلب بيانات المنتج: {str(e)}'
            }
    
    def get_system_summary(self):
        """ملخص النظام الشامل"""
        try:
            from models import Customer, Sale, Product, Payment
            
            # إحصائيات العملاء
            total_customers = Customer.query.count()
            vip_customers = Customer.query.filter(Customer.customer_type == 'VIP').count()
            
            # إحصائيات المبيعات
            total_sales = Sale.query.count()
            today_sales = Sale.query.filter(
                Sale.created_at >= datetime.now().date()
            ).count()
            
            # إحصائيات المنتجات
            total_products = Product.query.count()
            low_stock_products = Product.query.filter(
                Product.current_stock <= Product.min_stock_alert
            ).count()
            out_of_stock_products = Product.query.filter(
                Product.current_stock == 0
            ).count()
            
            # إحصائيات المدفوعات
            total_payments = Payment.query.count()
            today_payments = Payment.query.filter(
                Payment.created_at >= datetime.now().date()
            ).count()
            
            # آخر 5 مبيعات
            recent_sales = Sale.query.order_by(Sale.created_at.desc()).limit(5).all()
            
            # آخر 5 عملاء
            recent_customers = Customer.query.order_by(Customer.created_at.desc()).limit(5).all()
            
            return {
                'success': True,
                'summary': {
                    'customers': {
                        'total': total_customers,
                        'vip': vip_customers,
                        'recent': [
                            {
                                'id': c.id,
                                'name': c.name,
                                'type': c.customer_type,
                                'balance': float(c.get_balance_aed())
                            }
                            for c in recent_customers
                        ]
                    },
                    'sales': {
                        'total': total_sales,
                        'today': today_sales,
                        'recent': [
                            {
                                'id': s.id,
                                'customer': s.customer.name if s.customer else 'غير محدد',
                                'amount': float(s.total_amount),
                                'date': s.created_at.strftime('%Y-%m-%d %H:%M')
                            }
                            for s in recent_sales
                        ]
                    },
                    'products': {
                        'total': total_products,
                        'low_stock': low_stock_products,
                        'out_of_stock': out_of_stock_products
                    },
                    'payments': {
                        'total': total_payments,
                        'today': today_payments
                    }
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في جلب ملخص النظام: {str(e)}'
            }
    
    def get_financial_summary(self):
        """ملخص مالي شامل"""
        try:
            from models import Sale, Payment
            from extensions import db
            
            # إجمالي المبيعات
            total_sales_amount = db.session.query(
                db.func.sum(Sale.total_amount)
            ).scalar() or Decimal('0')
            
            # إجمالي المدفوعات
            total_payments_amount = db.session.query(
                db.func.sum(Payment.amount)
            ).scalar() or Decimal('0')
            
            # إجمالي الذمم
            total_receivables = total_sales_amount - total_payments_amount
            
            # مبيعات اليوم
            today_sales = db.session.query(
                db.func.sum(Sale.total_amount)
            ).filter(
                Sale.created_at >= datetime.now().date()
            ).scalar() or Decimal('0')
            
            # مدفوعات اليوم
            today_payments = db.session.query(
                db.func.sum(Payment.amount)
            ).filter(
                Payment.created_at >= datetime.now().date()
            ).scalar() or Decimal('0')
            
            # إحصائيات شهرية
            month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            monthly_sales = db.session.query(
                db.func.sum(Sale.total_amount)
            ).filter(
                Sale.created_at >= month_start
            ).scalar() or Decimal('0')
            
            return {
                'success': True,
                'financial': {
                    'total_sales': float(total_sales_amount),
                    'total_payments': float(total_payments_amount),
                    'total_receivables': float(total_receivables),
                    'today_sales': float(today_sales),
                    'today_payments': float(today_payments),
                    'monthly_sales': float(monthly_sales),
                    'currency': 'AED'
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في جلب الملخص المالي: {str(e)}'
            }
    
    def search_data(self, query, data_type='all'):
        """البحث في البيانات"""
        try:
            from models import Customer, Product, Sale
            
            results = {
                'customers': [],
                'products': [],
                'sales': []
            }
            
            if data_type in ['all', 'customers']:
                # البحث في العملاء
                customers = Customer.query.filter(
                    Customer.name.ilike(f'%{query}%')
                ).limit(10).all()
                
                results['customers'] = [
                    {
                        'id': c.id,
                        'name': c.name,
                        'type': c.customer_type,
                        'phone': c.phone,
                        'balance': float(c.get_balance_aed())
                    }
                    for c in customers
                ]
            
            if data_type in ['all', 'products']:
                # البحث في المنتجات
                products = Product.query.filter(
                    (Product.name.ilike(f'%{query}%')) |
                    (Product.sku.ilike(f'%{query}%'))
                ).limit(10).all()
                
                results['products'] = [
                    {
                        'id': p.id,
                        'name': p.name,
                        'sku': p.sku,
                        'stock': p.current_stock,
                        'price': float(p.unit_price)
                    }
                    for p in products
                ]
            
            if data_type in ['all', 'sales']:
                # البحث في المبيعات
                sales = Sale.query.join(Customer).filter(
                    Customer.name.ilike(f'%{query}%')
                ).limit(10).all()
                
                results['sales'] = [
                    {
                        'id': s.id,
                        'customer': s.customer.name if s.customer else 'غير محدد',
                        'amount': float(s.total_amount),
                        'date': s.created_at.strftime('%Y-%m-%d')
                    }
                    for s in sales
                ]
            
            return {
                'success': True,
                'query': query,
                'results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في البحث: {str(e)}'
            }


# إنشاء مثيل عالمي
system_integrator = SystemIntegrator()


# ===== Consolidated from: core/learning_system.py =====
"""
🧠 نظام التعلم الذاتي - Self-Learning System
أزاد يتعلم ويطور نفسه ذاتياً

NOTE: AzadLearningSystem and learning_system are lazy-loaded via
module __getattr__ to avoid circular imports between core_engine.py
and core/__init__.py → core/learning_system.py.
"""


# ===== Consolidated from: core/reasoning_engine.py =====
"""
🧠 محرك التفكير المنطقي المتقدم - Advanced Reasoning Engine
نظام التفكير العميق على طريقة DeepSeek + GPT-4

القدرات:
- Chain of Thought (سلسلة التفكير)
- Step-by-Step Reasoning (التفكير خطوة بخطوة)
- Mathematical Reasoning (الاستدلال الرياضي)
- Logical Deduction (الاستنتاج المنطقي)
- Problem Decomposition (تفكيك المشاكل)
- Multi-step Planning (التخطيط متعدد الخطوات)
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any, Tuple

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """
    محرك التفكير المنطقي المتقدم
    يحاكي طريقة تفكير DeepSeek و GPT-4
    """
    
    def __init__(self):
        self.reasoning_history = []
        self.knowledge_base = {}
        self.reasoning_patterns = {
            'mathematical': [],
            'logical': [],
            'financial': [],
            'technical': []
        }
    
    def think(self, problem: str, context: dict = None) -> dict:
        """
        التفكير العميق في مشكلة
        
        Args:
            problem: المشكلة المطلوب حلها
            context: السياق والبيانات المتاحة
        
        Returns:
            {
                'solution': الحل النهائي,
                'reasoning_steps': خطوات التفكير,
                'confidence': مستوى الثقة,
                'alternatives': حلول بديلة
            }
        """
        try:
            # 1. فهم المشكلة
            problem_type, key_elements = self._analyze_problem(problem, context)
            
            # 2. تفكيك المشكلة
            sub_problems = self._decompose_problem(problem, key_elements)
            
            # 3. حل كل جزء
            partial_solutions = []
            reasoning_steps = []
            
            for idx, sub_problem in enumerate(sub_problems, 1):
                step_result = self._solve_step(sub_problem, context)
                partial_solutions.append(step_result['solution'])
                reasoning_steps.append({
                    'step': idx,
                    'problem': sub_problem,
                    'reasoning': step_result['reasoning'],
                    'solution': step_result['solution'],
                    'confidence': step_result['confidence']
                })
            
            # 4. دمج الحلول
            final_solution = self._combine_solutions(partial_solutions, problem_type)
            
            # 5. التحقق من المنطقية
            verification = self._verify_solution(final_solution, problem, context)
            
            # 6. حلول بديلة
            alternatives = self._generate_alternatives(problem, context, final_solution)
            
            # حفظ في التاريخ
            self.reasoning_history.append({
                'timestamp': datetime.now().isoformat(),
                'problem': problem,
                'solution': final_solution,
                'steps': reasoning_steps,
                'verified': verification['is_valid']
            })
            
            return {
                'solution': final_solution,
                'reasoning_steps': reasoning_steps,
                'confidence': verification['confidence'],
                'alternatives': alternatives,
                'verification': verification,
                'problem_type': problem_type
            }
        
        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            return {
                'solution': None,
                'reasoning_steps': [],
                'confidence': 0,
                'error': str(e)
            }
    
    def _analyze_problem(self, problem: str, context: dict) -> Tuple[str, List[str]]:
        """تحليل نوع المشكلة واستخراج العناصر الرئيسية"""
        problem_lower = problem.lower()
        
        # تحديد النوع
        if any(kw in problem_lower for kw in ['سعر', 'price', 'تسعير', 'pricing']):
            problem_type = 'pricing'
        elif any(kw in problem_lower for kw in ['مخزون', 'stock', 'inventory']):
            problem_type = 'inventory'
        elif any(kw in problem_lower for kw in ['توقع', 'predict', 'forecast', 'متوقع']):
            problem_type = 'prediction'
        elif any(kw in problem_lower for kw in ['قيد', 'journal', 'محاسبة', 'accounting']):
            problem_type = 'accounting'
        elif any(kw in problem_lower for kw in ['صيانة', 'maintenance', 'إصلاح', 'repair']):
            problem_type = 'maintenance'
        elif any(kw in problem_lower for kw in ['عميل', 'customer', 'client']):
            problem_type = 'customer'
        else:
            problem_type = 'general'
        
        # استخراج العناصر الرئيسية
        key_elements = []
        
        # أرقام
        import re
        numbers = re.findall(r'\d+\.?\d*', problem)
        key_elements.extend(numbers)
        
        # كلمات مفتاحية
        keywords = ['منتج', 'عميل', 'مورد', 'فاتورة', 'مبلغ', 'كمية']
        for kw in keywords:
            if kw in problem:
                key_elements.append(kw)
        
        return problem_type, key_elements
    
    def _decompose_problem(self, problem: str, key_elements: List[str]) -> List[str]:
        """تفكيك المشكلة إلى خطوات فرعية"""
        sub_problems = []
        
        # مثال: "ما السعر المثالي لمنتج تكلفته 100 درهم لعميل VIP؟"
        # →  1. تحديد نوع العميل
        #    2. حساب الهامش المناسب
        #    3. مراعاة السوق
        #    4. حساب السعر النهائي
        
        if 'سعر' in problem.lower() or 'price' in problem.lower():
            sub_problems.extend([
                "تحديد سعر التكلفة",
                "تحديد نوع العميل والهامش المناسب",
                "مراعاة حجم الطلب والخصومات",
                "حساب السعر النهائي المقترح"
            ])
        elif 'توقع' in problem.lower() or 'predict' in problem.lower():
            sub_problems.extend([
                "جمع البيانات التاريخية",
                "تحليل الاتجاهات",
                "تطبيق النموذج التنبؤي",
                "حساب الثقة في التوقع"
            ])
        elif 'محاسبة' in problem.lower() or 'قيد' in problem.lower():
            sub_problems.extend([
                "تحديد نوع القيد",
                "حساب المدين والدائن",
                "التحقق من التوازن",
                "التأكد من تطبيق المبادئ المحاسبية"
            ])
        else:
            # مشكلة عامة
            sub_problems.extend([
                "فهم المشكلة",
                "تحليل المعطيات",
                "تطبيق المنطق",
                "استخلاص الحل"
            ])
        
        return sub_problems
    
    def _solve_step(self, sub_problem: str, context: dict) -> dict:
        """حل خطوة واحدة"""
        # محاكاة التفكير المنطقي
        
        if 'سعر التكلفة' in sub_problem:
            reasoning = "سعر التكلفة هو الأساس، يجب أن يكون السعر النهائي أعلى منه لتحقيق الربح"
            solution = context.get('cost_price', 100) if context else 100
            confidence = 1.0
        
        elif 'نوع العميل' in sub_problem:
            reasoning = "نوع العميل يحدد الهامش: Regular=30%, Merchant=20%, Partner=15%"
            customer_type = context.get('customer_type', 'regular') if context else 'regular'
            margin = {'regular': 1.30, 'merchant': 1.20, 'partner': 1.15}.get(customer_type, 1.25)
            solution = margin
            confidence = 0.9
        
        elif 'حجم الطلب' in sub_problem:
            reasoning = "الكميات الكبيرة تستحق خصومات أكثر"
            quantity = context.get('quantity', 1) if context else 1
            discount = 0 if quantity < 10 else 5 if quantity < 50 else 10
            solution = discount
            confidence = 0.85
        
        elif 'السعر النهائي' in sub_problem:
            reasoning = "السعر النهائي = التكلفة × الهامش - الخصم"
            cost = context.get('cost_price', 100) if context else 100
            margin = context.get('margin', 1.25) if context else 1.25
            discount = context.get('discount', 0) if context else 0
            solution = cost * margin * (1 - discount/100)
            confidence = 0.95
        
        else:
            reasoning = f"تحليل: {sub_problem}"
            solution = "يحتاج معلومات إضافية"
            confidence = 0.5
        
        return {
            'solution': solution,
            'reasoning': reasoning,
            'confidence': confidence
        }
    
    def _combine_solutions(self, partial_solutions: List, problem_type: str) -> Any:
        """دمج الحلول الجزئية"""
        if problem_type == 'pricing':
            # دمج خطوات التسعير
            if len(partial_solutions) >= 4:
                return partial_solutions[-1]  # السعر النهائي
            return None
        
        elif problem_type == 'prediction':
            # دمج التوقعات
            if partial_solutions:
                return partial_solutions[-1]
            return None
        
        else:
            # دمج عام
            return partial_solutions[-1] if partial_solutions else None
    
    def _verify_solution(self, solution: Any, problem: str, context: dict) -> dict:
        """التحقق من منطقية الحل"""
        is_valid = True
        confidence = 0.9
        verification_notes = []
        
        # التحقق من الأسعار
        if isinstance(solution, (int, float, Decimal)):
            if solution <= 0:
                is_valid = False
                confidence = 0.0
                verification_notes.append("السعر يجب أن يكون موجب")
            
            # التحقق من الهامش
            if context and 'cost_price' in context:
                cost = context['cost_price']
                if solution < cost:
                    is_valid = False
                    confidence = 0.2
                    verification_notes.append("السعر أقل من التكلفة - خسارة!")
                elif solution < cost * 1.05:
                    confidence = 0.6
                    verification_notes.append("الهامش منخفض جداً (<5%)")
        
        return {
            'is_valid': is_valid,
            'confidence': confidence,
            'notes': verification_notes
        }
    
    def _generate_alternatives(self, problem: str, context: dict, main_solution: Any) -> List[dict]:
        """توليد حلول بديلة"""
        alternatives = []
        
        if isinstance(main_solution, (int, float)):
            # حلول بديلة للأسعار
            alternatives.append({
                'solution': main_solution * 0.95,
                'description': 'سعر أقل بـ 5% - لزيادة المبيعات',
                'pros': ['جذب عملاء أكثر', 'تنافسية أعلى'],
                'cons': ['هامش أقل']
            })
            
            alternatives.append({
                'solution': main_solution * 1.05,
                'description': 'سعر أعلى بـ 5% - لزيادة الربح',
                'pros': ['ربح أعلى', 'صورة premium'],
                'cons': ['قد يقلل المبيعات']
            })
        
        return alternatives
    
    def chain_of_thought(self, question: str, data: dict = None) -> dict:
        """
        Chain of Thought Reasoning (طريقة DeepSeek)
        
        يفكر خطوة بخطوة بصوت عالٍ
        """
        thought_chain = []
        
        # الخطوة 1: فهم السؤال
        thought_chain.append({
            'step': 1,
            'thought': f"فهم السؤال: {question}",
            'action': 'analyzing question'
        })
        
        # الخطوة 2: تحديد المعطيات
        available_data = list(data.keys()) if data else []
        thought_chain.append({
            'step': 2,
            'thought': f"المعطيات المتاحة: {', '.join(available_data)}",
            'action': 'identifying data'
        })
        
        # الخطوة 3: تحديد المطلوب
        thought_chain.append({
            'step': 3,
            'thought': "تحديد ما هو المطلوب بالضبط",
            'action': 'identifying goal'
        })
        
        # الخطوة 4: التفكير في الحل
        thought_chain.append({
            'step': 4,
            'thought': "تطبيق المنطق والمعرفة للوصول للحل",
            'action': 'applying logic'
        })
        
        # الخطوة 5: التحقق
        thought_chain.append({
            'step': 5,
            'thought': "التحقق من منطقية الحل",
            'action': 'verification'
        })
        
        # الحل النهائي
        final_solution = self.think(question, data)
        
        return {
            'question': question,
            'thought_chain': thought_chain,
            'solution': final_solution,
            'method': 'chain_of_thought'
        }
    
    def mathematical_reasoning(self, calculation_problem: str) -> dict:
        """
        الاستدلال الرياضي المتقدم
        
        يحل المسائل الرياضية خطوة بخطوة
        """
        steps = []
        
        try:
            # استخراج الأرقام
            import re
            numbers = [float(n) for n in re.findall(r'\d+\.?\d*', calculation_problem)]
            
            # تحديد العملية
            if '+' in calculation_problem or 'جمع' in calculation_problem:
                operation = 'addition'
                result = sum(numbers)
                steps.append(f"الجمع: {' + '.join(map(str, numbers))} = {result}")
            
            elif '-' in calculation_problem or 'طرح' in calculation_problem:
                operation = 'subtraction'
                result = numbers[0] - sum(numbers[1:])
                steps.append(f"الطرح: {numbers[0]} - {sum(numbers[1:])} = {result}")
            
            elif '×' in calculation_problem or '*' in calculation_problem or 'ضرب' in calculation_problem:
                operation = 'multiplication'
                result = 1
                for n in numbers:
                    result *= n
                steps.append(f"الضرب: {' × '.join(map(str, numbers))} = {result}")
            
            elif '÷' in calculation_problem or '/' in calculation_problem or 'قسمة' in calculation_problem:
                operation = 'division'
                result = numbers[0] / numbers[1] if len(numbers) > 1 and numbers[1] != 0 else 0
                steps.append(f"القسمة: {numbers[0]} ÷ {numbers[1]} = {result}")
            
            elif '%' in calculation_problem or 'نسبة' in calculation_problem:
                operation = 'percentage'
                if len(numbers) >= 2:
                    result = numbers[0] * (numbers[1] / 100)
                    steps.append(f"النسبة: {numbers[0]} × {numbers[1]}% = {result}")
                else:
                    result = 0
            
            else:
                operation = 'unknown'
                result = None
                steps.append("لم أتمكن من تحديد العملية المطلوبة")
            
            return {
                'operation': operation,
                'numbers': numbers,
                'steps': steps,
                'result': result,
                'confidence': 1.0 if result is not None else 0.0
            }
        
        except Exception as e:
            return {
                'operation': 'error',
                'steps': [f"خطأ في الحساب: {e}"],
                'result': None,
                'confidence': 0.0
            }
    
    def financial_reasoning(self, financial_question: str, financial_data: dict) -> dict:
        """
        الاستدلال المالي المتقدم
        
        يحلل:
        - النسب المالية
        - القرارات الاستثمارية
        - التحليل المالي
        """
        reasoning = []
        metrics = {}
        
        try:
            # استخراج البيانات المالية
            sales = financial_data.get('sales', 0)
            costs = financial_data.get('costs', 0)
            expenses = financial_data.get('expenses', 0)
            assets = financial_data.get('assets', 0)
            liabilities = financial_data.get('liabilities', 0)
            
            # 1. هامش الربح الإجمالي
            if sales > 0 and costs > 0:
                gross_profit = sales - costs
                gross_margin = (gross_profit / sales) * 100
                
                reasoning.append(f"هامش الربح الإجمالي = (المبيعات - التكلفة) / المبيعات")
                reasoning.append(f"= ({sales} - {costs}) / {sales} = {gross_margin:.1f}%")
                
                metrics['gross_margin'] = gross_margin
                
                if gross_margin < 20:
                    reasoning.append("⚠️ الهامش منخفض - حاول زيادة الأسعار أو تقليل التكاليف")
                elif gross_margin > 40:
                    reasoning.append("✅ الهامش ممتاز - استمر")
            
            # 2. صافي الربح
            if sales > 0:
                net_profit = sales - costs - expenses
                net_margin = (net_profit / sales) * 100
                
                reasoning.append(f"صافي الربح = المبيعات - التكلفة - المصروفات")
                reasoning.append(f"= {sales} - {costs} - {expenses} = {net_profit}")
                reasoning.append(f"هامش صافي الربح = {net_margin:.1f}%")
                
                metrics['net_profit'] = net_profit
                metrics['net_margin'] = net_margin
            
            # 3. نسبة السيولة
            if liabilities > 0:
                current_ratio = assets / liabilities
                reasoning.append(f"نسبة السيولة الجارية = الأصول / الخصوم")
                reasoning.append(f"= {assets} / {liabilities} = {current_ratio:.2f}")
                
                metrics['current_ratio'] = current_ratio
                
                if current_ratio < 1:
                    reasoning.append("⚠️ خطر! الخصوم أكبر من الأصول")
                elif current_ratio > 2:
                    reasoning.append("✅ سيولة ممتازة")
            
            # التوصية النهائية
            if metrics.get('net_margin', 0) > 15 and metrics.get('current_ratio', 0) > 1.5:
                recommendation = "🎯 الوضع المالي ممتاز - استمر في الاستراتيجية الحالية"
            elif metrics.get('net_margin', 0) < 5:
                recommendation = "⚠️ الربحية منخفضة - راجع التكاليف والأسعار"
            else:
                recommendation = "✅ الوضع جيد - هناك فرص للتحسين"
            
            return {
                'reasoning_steps': reasoning,
                'metrics': metrics,
                'recommendation': recommendation,
                'confidence': 0.9
            }
        
        except Exception as e:
            return {
                'reasoning_steps': [f"خطأ في التحليل: {e}"],
                'metrics': {},
                'recommendation': "تعذر التحليل",
                'confidence': 0.0
            }
    
    def technical_reasoning(self, technical_problem: str) -> dict:
        """
        الاستدلال التقني - مهندس الصيانة
        
        يحلل:
        - الأعطال المحتملة
        - الأسباب الجذرية
        - الحلول التقنية
        """
        diagnosis_steps = []
        possible_causes = []
        solutions = []
        
        problem_lower = technical_problem.lower()
        
        # تشخيص الأعطال الشائعة
        if 'محرك' in problem_lower or 'engine' in problem_lower:
            diagnosis_steps.append("1. فحص نظام الوقود")
            diagnosis_steps.append("2. فحص نظام الإشعال")
            diagnosis_steps.append("3. فحص نظام التبريد")
            diagnosis_steps.append("4. فحص الضغط")
            
            possible_causes = [
                "فلتر وقود مسدود",
                "شمعات إشعال تالفة",
                "مشكلة في مضخة الوقود",
                "ارتفاع حرارة المحرك",
                "مشكلة في الكمبيوتر"
            ]
            
            solutions = [
                "استبدال فلتر الوقود",
                "تنظيف أو استبدال الشمعات",
                "فحص مضخة الوقود",
                "فحص نظام التبريد",
                "فحص كمبيوتر المحرك"
            ]
        
        elif 'فرامل' in problem_lower or 'brake' in problem_lower:
            diagnosis_steps.append("1. فحص سماكة الفحمات")
            diagnosis_steps.append("2. فحص سائل الفرامل")
            diagnosis_steps.append("3. فحص الأقراص")
            
            possible_causes = [
                "فحمات فرامل بالية",
                "سائل فرامل ملوث",
                "تسرب في الدائرة الهيدروليكية",
                "أقراص فرامل مشروخة"
            ]
            
            solutions = [
                "استبدال فحمات الفرامل",
                "تغيير سائل الفرامل",
                "إصلاح التسرب",
                "استبدال الأقراص"
            ]
        
        elif 'زيت' in problem_lower or 'oil' in problem_lower:
            diagnosis_steps.append("1. فحص مستوى الزيت")
            diagnosis_steps.append("2. فحص جودة الزيت")
            diagnosis_steps.append("3. فحص وجود تسريب")
            
            possible_causes = [
                "الزيت قديم أو متسخ",
                "مستوى الزيت منخفض",
                "تسرب من الجوان",
                "فلتر الزيت مسدود"
            ]
            
            solutions = [
                "تغيير الزيت والفلتر",
                "إضافة زيت للمستوى المطلوب",
                "استبدال الجوان",
                "تغيير فلتر الزيت"
            ]
        
        else:
            diagnosis_steps.append("فحص عام للنظام")
            possible_causes.append("يحتاج معلومات أكثر للتشخيص الدقيق")
            solutions.append("استشر مهندس صيانة متخصص")
        
        return {
            'problem': technical_problem,
            'diagnosis_steps': diagnosis_steps,
            'possible_causes': possible_causes,
            'recommended_solutions': solutions,
            'priority': 'high' if 'محرك' in problem_lower else 'medium',
            'estimated_time': '2-4 ساعات',
            'estimated_cost': 'متوسط'
        }
    
    def business_reasoning(self, business_question: str, business_data: dict) -> dict:
        """
        الاستدلال التجاري - مستشار أعمال
        
        يحلل:
        - القرارات الاستراتيجية
        - الفرص والتهديدات
        - خطط النمو
        """
        analysis = {
            'question': business_question,
            'swot': {},
            'recommendations': [],
            'action_plan': []
        }
        
        # SWOT Analysis
        analysis['swot'] = {
            'strengths': [
                "نظام محاسبي متقدم",
                "مساعد ذكي متطور",
                "إدارة مخزون فعالة"
            ],
            'weaknesses': [
                "يحتاج تدريب النماذج بشكل دوري"
            ],
            'opportunities': [
                "توسع في الأسواق الجديدة",
                "إضافة منتجات جديدة",
                "تحسين تجربة العملاء"
            ],
            'threats': [
                "المنافسة",
                "تغيرات السوق"
            ]
        }
        
        # التوصيات
        analysis['recommendations'] = [
            "1. استثمر في التسويق الرقمي",
            "2. حسّن خدمة العملاء",
            "3. وسّع نطاق المنتجات",
            "4. درّب الفريق على النظام",
            "5. راقب المنافسين باستمرار"
        ]
        
        # خطة العمل
        analysis['action_plan'] = [
            {
                'action': 'تدريب جميع النماذج العصبية',
                'priority': 'high',
                'timeline': 'هذا الأسبوع',
                'responsible': 'مدير النظام'
            },
            {
                'action': 'مراجعة الأسعار بناءً على AI',
                'priority': 'medium',
                'timeline': 'نهاية الشهر',
                'responsible': 'مدير المبيعات'
            }
        ]
        
        return analysis
    
    def get_reasoning_history(self, limit=10):
        """الحصول على تاريخ التفكير"""
        return self.reasoning_history[-limit:] if self.reasoning_history else []
    
    def explain_decision(self, decision: str, factors: dict) -> str:
        """
        شرح قرار بطريقة مفهومة
        
        يحول القرارات المعقدة إلى شرح بسيط
        """
        explanation = f"📊 شرح القرار: {decision}\n\n"
        
        explanation += "العوامل المؤثرة:\n"
        for idx, (factor, value) in enumerate(factors.items(), 1):
            explanation += f"{idx}. {factor}: {value}\n"
        
        explanation += "\nالاستنتاج:\n"
        explanation += "بناءً على تحليل العوامل أعلاه، هذا القرار هو الأنسب حالياً.\n"
        
        return explanation


# ============================================================================
# Singleton
# ============================================================================

_reasoning_engine_instance = None

def get_reasoning_engine():
    """الحصول على instance واحد"""
    global _reasoning_engine_instance
    if _reasoning_engine_instance is None:
        _reasoning_engine_instance = ReasoningEngine()
    return _reasoning_engine_instance


# ============================================================================
# Lazy re-exports (avoid circular import with core/__init__.py)
# ============================================================================

def __getattr__(name):
    """Lazy-load AzadLearningSystem / learning_system from core/learning_system.py."""
    if name in ('AzadLearningSystem', 'learning_system'):
        import importlib
        mod = importlib.import_module('ai_knowledge.core.learning_system')
        val = getattr(mod, name)
        import sys as _sys
        setattr(_sys.modules[__name__], name, val)
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

