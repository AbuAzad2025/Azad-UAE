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

