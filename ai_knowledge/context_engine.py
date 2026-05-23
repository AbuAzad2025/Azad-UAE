"""
🧠 محرك السياق الذكي - Context Engine
يفهم السياق ويربط جميع ملفات المعرفة والمحركات
"""
from .system_integration import system_integrator
from .data_analyzer import data_analyzer
from .learning_system import learning_system
from .global_knowledge import global_connector
from .knowledge_expansion import knowledge_expander
from .document_generator import document_generator
from .advanced_laws import advanced_laws


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
            except:
                pass
        
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
            except:
                pass
        
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
            except:
                pass
        
        # إضافة رؤى من التعلم الذاتي
        try:
            learning_insights = learning_system.get_learning_insights()
            if learning_insights.get('total_interactions', 0) > 10:
                additional_info.append("\n\n💡 **من خبرتي معك:**")
                top_topic = learning_insights.get('top_topics', [{}])[0] if learning_insights.get('top_topics') else {}
                if top_topic:
                    additional_info.append(f"• أكثر موضوع تهتم به: {top_topic.get('topic', 'غير محدد')}")
        except:
            pass
        
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

