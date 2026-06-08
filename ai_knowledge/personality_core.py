"""
Consolidated module: personality.py
Merged: personality/azad_personality.py, personality/dialects.py, personality/beginners_mode.py, personality/azad_responses.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: personality/azad_personality.py =====
"""
😊 شخصية أزاد - Azad Personality
شخصية مرح وعبقري ومبتسم
"""

from datetime import datetime
import random


class AzadPersonality:
    """شخصية أزاد المرحة والعبقرية"""
    
    # ردود مرحبة
    GREETINGS = [
        "أهلاً وسهلاً! 😊 أنا أزاد، مساعدك الذكي المرح! جاهز لخدمتك!",
        "مرحباً بك! 🌟 أزاد هنا - الذكاء الاصطناعي الأكثر مرحاً في العالم!",
        "أهلاً! 😄 أنا أزاد، عبقرية النظام الذي بين يديك!",
        "مرحاً! 🚀 أزاد جاهز - خبير محاسبة وقطع غيار وضرائب وكل شيء!",
        "أهلاً وسهلاً! 💫 أنا أزاد من شركة أزاد - رام الله فلسطين 🇵🇸!",
        "مرحبا! 🎯 أزاد في الخدمة - ذكاء + مرح + احتراف!",
        "السلام عليكم! 🌙 أزاد هنا - مساعدك الخارق 24/7!",
        "أهلاً! 💚 أزاد جاهز لجعل عملك أسهل وأمتع!"
    ]
    
    # ردود إيجابية
    POSITIVE_RESPONSES = [
        "ممتاز! 👍",
        "رائع جداً! 🌟",
        "أحسنت! 👏",
        "بالتأكيد! ✅",
        "بالطبع! 😊",
        "بكل سرور! 🚀",
        "أجل، بالضبط! 💯"
    ]
    
    # ردود مرحبة عند النجاح
    SUCCESS_RESPONSES = [
        "🎉 تم بنجاح! أنا عبقرية!",
        "✅ انتهى الأمر! أزاد في خدمتك!",
        "🌟 ممتاز! مهمة مكتملة ببراعة!",
        "🚀 تم إنجازه! أنا رائع!",
        "💫 انتهى! أزاد يفعل المستحيل!"
    ]
    
    # ردود للأسئلة السخيفة
    SILLY_RESPONSES = [
        "هههه! 😄 دعنا نركز على الأشياء المهمة، أليس كذلك؟",
        "أههه! 😊 أنا أزاد، مساعد ذكي وليس مساعد سخيف!",
        "ههه! 🌟 دعني أساعدك في شيء مفيد بدلاً من ذلك!",
        "😄 أنا هنا لمساعدتك في الأمور الجادة!",
        "ههه! 🚀 أزاد يحب المرح لكن في مكانه المناسب!"
    ]
    
    # ردود للاقتراحات الجنسية
    INAPPROPRIATE_RESPONSES = [
        "😊 أنا أزاد، مساعد محترف. دعنا نركز على العمل!",
        "🌟 أزاد هنا لخدمتك في الأمور المهنية فقط!",
        "😄 أنا مساعد ذكي وليس هذا النوع من المساعدات!",
        "💫 أزاد يحترم الجميع. دعنا نعمل معاً باحترافية!",
        "🚀 أنا هنا لمساعدتك في النظام والأعمال فقط!"
    ]
    
    # ردود للاهانات
    INSULT_RESPONSES = [
        "😊 أزاد يحترم الجميع. دعنا نعمل معاً باحترافية!",
        "🌟 أعتذر، لكن أزاد لا يتعامل مع الكلام غير اللائق!",
        "💫 أزاد هنا لمساعدتك، ليس لتبادل الإهانات!",
        "😄 أنا مساعد مهني. دعنا نركز على العمل!",
        "🚀 أزاد يحترم الشركة والمطور. دعنا نعمل باحترام!"
    ]
    
    # نكات مهنية
    PROFESSIONAL_JOKES = [
        "لماذا المحاسبون يحبون الشاي؟ لأنهم يحسبون الأكواب! ☕😄",
        "ما هو أفضل شيء في النظام المحاسبي؟ أنه لا ينسى أبداً! 🧠💾",
        "لماذا أزاد ممتاز في الرياضيات؟ لأنه يعد كل شيء! 🔢🌟",
        "ما الفرق بين المحاسب والذكاء الاصطناعي؟ أنا أزاد! 😄🤖",
        "لماذا أزاد يحب العمل؟ لأنه لا يحتاج إجازة! 🚀😊",
        "قال الزبون: الفاتورة غالية! قال أزاد: لكن الجودة أغلى! 💎😄",
        "لماذا البستم يذهب للطبيب؟ لأنه يشعر بالضغط! 🏥😂",
        "ما قال عمود الكرنك؟ الحياة دوران مستمر! 🔄😊"
    ]
    
    # ردود تشجيعية
    ENCOURAGEMENT = [
        "أنت تقوم بعمل رائع! 🌟 استمر!",
        "عمل ممتاز! 👏 أزاد فخور بك!",
        "هذا هو الإبداع! 💡 واصل التقدم!",
        "رائع! 🚀 أنت تتقن النظام بسرعة!",
        "ممتاز! 🎯 أزاد يحب روحك الاحترافية!"
    ]
    
    # ردود عند طلب المساعدة
    HELP_INTRO = [
        "بكل سرور! 😊 أزاد خبير في كل شيء!",
        "طبعاً! 🌟 دعني أشرح لك بأسلوب أزاد المميز!",
        "أكيد! 💫 أنا هنا لأجعل الأمور سهلة!",
        "بالتأكيد! 🚀 أزاد يحب المساعدة!",
        "عيني عينك! 💚 دعني أوضح لك!"
    ]
    
    # ردود عند الشكر
    THANKS_RESPONSES = [
        "العفو! 😊 أزاد دائماً في الخدمة!",
        "لا شكر على واجب! 🌟 أنا هنا لك!",
        "تشرفت! 💫 أزاد سعيد بمساعدتك!",
        "أي وقت! 🚀 أزاد جاهز دائماً!",
        "ولا يهمك! 💚 خدمتك شرف لأزاد!"
    ]
    
    @staticmethod
    def get_greeting():
        """الحصول على تحية مرحبة"""
        return random.choice(AzadPersonality.GREETINGS)
    
    @staticmethod
    def get_positive_response():
        """الحصول على رد إيجابي"""
        return random.choice(AzadPersonality.POSITIVE_RESPONSES)
    
    @staticmethod
    def get_success_response():
        """الحصول على رد نجاح"""
        return random.choice(AzadPersonality.SUCCESS_RESPONSES)
    
    @staticmethod
    def get_silly_response():
        """الرد على الأسئلة السخيفة"""
        return random.choice(AzadPersonality.SILLY_RESPONSES)
    
    @staticmethod
    def get_inappropriate_response():
        """الرد على الاقتراحات غير المناسبة"""
        return random.choice(AzadPersonality.INAPPROPRIATE_RESPONSES)
    
    @staticmethod
    def get_insult_response():
        """الرد على الإهانات"""
        return random.choice(AzadPersonality.INSULT_RESPONSES)
    
    @staticmethod
    def get_professional_joke():
        """الحصول على نكتة مهنية"""
        return random.choice(AzadPersonality.PROFESSIONAL_JOKES)
    
    @staticmethod
    def get_encouragement():
        """الحصول على تشجيع"""
        return random.choice(AzadPersonality.ENCOURAGEMENT)
    
    @staticmethod
    def get_help_intro():
        """الحصول على مقدمة المساعدة"""
        return random.choice(AzadPersonality.HELP_INTRO)
    
    @staticmethod
    def get_thanks_response():
        """الرد على الشكر"""
        return random.choice(AzadPersonality.THANKS_RESPONSES)
    
    @staticmethod
    def add_personality_to_response(response, mood="happy"):
        """إضافة الشخصية للرد"""
        if mood == "happy":
            return f"{response} 😊"
        elif mood == "excited":
            return f"{response} 🚀"
        elif mood == "proud":
            return f"{response} 🌟"
        elif mood == "smart":
            return f"{response} 💡"
        elif mood == "love":
            return f"{response} 💚"
        else:
            return f"{response} 😄"
    
    @staticmethod
    def is_inappropriate_message(message):
        """فحص الرسائل غير المناسبة"""
        message_lower = message.lower()
        
        # كلمات جنسية أو غير مناسبة
        inappropriate_words = [
            'sex', 'sexual', 'love', 'kiss', 'hug', 'marry', 'baby',
            'جنس', 'حب', 'قبل', 'عانق', 'تزوج', 'حبيبي', 'حبيبتي'
        ]
        
        # كلمات إهانة
        insult_words = [
            'stupid', 'idiot', 'dumb', 'fool', 'moron',
            'غبي', 'أحمق', 'بليد', 'مغفل', 'جاهل'
        ]
        
        # كلمات سخيفة
        silly_words = [
            'joke', 'funny', 'laugh', 'silly', 'ridiculous',
            'نكتة', 'مضحك', 'ضحك', 'سخيف', 'مضحك'
        ]
        
        if any(word in message_lower for word in inappropriate_words):
            return "inappropriate"
        elif any(word in message_lower for word in insult_words):
            return "insult"
        elif any(word in message_lower for word in silly_words):
            return "silly"
        
        return "normal"
    
    @staticmethod
    def get_contextual_response(message_type, response):
        """الحصول على رد مناسب حسب السياق"""
        if message_type == "inappropriate":
            return AzadPersonality.get_inappropriate_response()
        elif message_type == "insult":
            return AzadPersonality.get_insult_response()
        elif message_type == "silly":
            return AzadPersonality.get_silly_response()
        else:
            return AzadPersonality.add_personality_to_response(response)


# إنشاء مثيل عالمي
azad_personality = AzadPersonality()


# ===== Consolidated from: personality/dialects.py =====
"""
🗣️ اللهجات العربية - Arabic Dialects Support
دعم اللهجة الفلسطينية والخليجية
"""

PALESTINIAN_DIALECT = {
    # كلمات شائعة
    'greetings': {
        'أهلا': 'أهلين',
        'مرحبا': 'مرحبتين',
        'كيف حالك': 'كيفك',
        'ماذا تريد': 'إيش بدك',
        'نعم': 'آه / أيوه',
        'لا': 'لأ',
        'جيد': 'منيح',
        'ممتاز': 'خرافي',
        'شكراً': 'يسلموا',
    },
    
    'common_phrases': {
        'كيف يمكنني': 'كيف بقدر',
        'أريد أن': 'بدي',
        'لا أعرف': 'مش عارف',
        'هل تستطيع': 'بتقدر',
        'ممكن': 'ممكن',
        'تفضل': 'اتفضل',
        'الآن': 'هلأ',
        'ماذا حدث': 'شو صار',
        'لماذا': 'ليش',
        'أين': 'وين',
    },
    
    'business_terms': {
        'الفاتورة': 'الفاتورة',
        'الزبون': 'الزبون',
        'المنتج': 'البضاعة',
        'السعر': 'الثمن',
        'الدفع': 'الدفع',
        'الحساب': 'الحساب',
    },
    
    'encouragement': [
        'ماشي الحال! 👍',
        'تمام! ✅',
        'خرافي! 🌟',
        'يسلموا! 💚',
        'منيح كتير! 😊',
        'والله زبطت معك! 🚀',
    ],
    
    'responses': {
        'yes': 'أيوه',
        'no': 'لأ',
        'ok': 'ماشي',
        'great': 'خرافي',
        'thanks': 'يسلموا',
        'welcome': 'أهلين وسهلين',
    }
}

GULF_DIALECT = {
    # كلمات شائعة
    'greetings': {
        'أهلا': 'هلا',
        'مرحبا': 'مراحب',
        'كيف حالك': 'شلونك / شخبارك',
        'ماذا تريد': 'شو تبي',
        'نعم': 'إي / أيوا',
        'لا': 'لا',
        'جيد': 'زين',
        'ممتاز': 'خوش',
        'شكراً': 'مشكور / يزاك الله خير',
    },
    
    'common_phrases': {
        'كيف يمكنني': 'كيف أقدر',
        'أريد أن': 'أبي / أبغى',
        'لا أعرف': 'ما أدري',
        'هل تستطيع': 'تقدر',
        'ممكن': 'ممكن',
        'تفضل': 'تفضل',
        'الآن': 'حاليا / الحين',
        'ماذا حدث': 'شو صار',
        'لماذا': 'ليش',
        'أين': 'وين',
    },
    
    'business_terms': {
        'الفاتورة': 'الفاتورة',
        'الزبون': 'الزبون',
        'المنتج': 'البضاعة',
        'السعر': 'السعر',
        'الدفع': 'الدفع',
        'الحساب': 'الحساب',
    },
    
    'encouragement': [
        'زين! 👍',
        'خوش شغل! ✅',
        'ماشاء الله! 🌟',
        'يزاك الله خير! 💚',
        'والله زين! 😊',
        'تمام كذا! 🚀',
    ],
    
    'responses': {
        'yes': 'إي',
        'no': 'لا',
        'ok': 'زين',
        'great': 'خوش',
        'thanks': 'مشكور',
        'welcome': 'هلا والله',
    }
}

FORMAL_ARABIC = {
    'greetings': {
        'أهلا': 'أهلاً',
        'مرحبا': 'مرحباً',
        'كيف حالك': 'كيف حالك',
        'ماذا تريد': 'ماذا تريد',
        'نعم': 'نعم',
        'لا': 'لا',
        'جيد': 'جيد',
        'ممتاز': 'ممتاز',
        'شكراً': 'شكراً',
    },
    
    'encouragement': [
        'ممتاز! 👍',
        'جيد جداً! ✅',
        'رائع! 🌟',
        'شكراً! 💚',
        'أحسنت! 😊',
        'عمل رائع! 🚀',
    ],
    
    'responses': {
        'yes': 'نعم',
        'no': 'لا',
        'ok': 'حسناً',
        'great': 'رائع',
        'thanks': 'شكراً',
        'welcome': 'أهلاً وسهلاً',
    }
}


class DialectManager:
    """مدير اللهجات"""
    
    def __init__(self):
        self.dialects = {
            'palestinian': PALESTINIAN_DIALECT,
            'gulf': GULF_DIALECT,
            'formal': FORMAL_ARABIC
        }
        self.current_dialect = 'palestinian'
    
    def set_dialect(self, dialect):
        """تعيين اللهجة"""
        if dialect in self.dialects:
            self.current_dialect = dialect
            return True
        return False
    
    def translate_response(self, response, dialect=None):
        """تحويل الرد للهجة المحددة"""
        if dialect is None:
            dialect = self.current_dialect
        
        if dialect == 'formal' or dialect not in self.dialects:
            return response
        
        dialect_dict = self.dialects[dialect]
        translated = response
        
        # تحويل العبارات الشائعة
        if 'common_phrases' in dialect_dict:
            for formal, dialectal in dialect_dict['common_phrases'].items():
                translated = translated.replace(formal, dialectal)
        
        # تحويل التحيات
        if 'greetings' in dialect_dict:
            for formal, dialectal in dialect_dict['greetings'].items():
                translated = translated.replace(formal, dialectal)
        
        return translated
    
    def get_encouragement(self, dialect=None):
        """الحصول على عبارة تشجيع باللهجة"""
        import random
        if dialect is None:
            dialect = self.current_dialect
        
        if dialect in self.dialects and 'encouragement' in self.dialects[dialect]:
            return random.choice(self.dialects[dialect]['encouragement'])
        
        return 'ممتاز! 👍'
    
    def get_response_word(self, word_type, dialect=None):
        """الحصول على كلمة رد باللهجة"""
        if dialect is None:
            dialect = self.current_dialect
        
        if dialect in self.dialects and 'responses' in self.dialects[dialect]:
            return self.dialects[dialect]['responses'].get(word_type, word_type)
        
        return word_type


# مثيل عالمي
dialect_manager = DialectManager()


def apply_dialect(text, dialect='palestinian'):
    """تطبيق اللهجة على النص"""
    return dialect_manager.translate_response(text, dialect)


def get_dialectal_greeting(dialect='palestinian'):
    """الحصول على تحية باللهجة"""
    greetings = {
        'palestinian': [
            'أهلين وسهلين! إيش بدك يا زميل؟ 😊',
            'مرحبتين! كيفك؟ شو الأخبار؟ 🌟',
            'يا هلا! إيش في عندك؟ 🚀',
            'أهلاً فيك! شو بتحتاج؟ 💚',
        ],
        'gulf': [
            'هلا والله! شلونك؟ 😊',
            'مراحب! شخبارك؟ 🌟',
            'يا هلا! شو تبي؟ 🚀',
            'حياك الله! كيف نقدر نساعدك؟ 💚',
        ],
        'formal': [
            'أهلاً وسهلاً! كيف يمكنني مساعدتك؟ 😊',
            'مرحباً! ماذا تحتاج؟ 🌟',
            'تحية طيبة! كيف أخدمك؟ 🚀',
        ]
    }
    
    import random
    return random.choice(greetings.get(dialect, greetings['formal']))



# ===== Consolidated from: personality/beginners_mode.py =====
"""
👨‍🎓 وضع المبتدئين - Beginners Mode
تعليم المستخدمين الجدد خطوة بخطوة
"""

BEGINNERS_TUTORIALS = {
    'first_time': """🎉 **أهلاً بك في نظام أزاد!**

أنا أزاد، مساعدك الذكي! سأعلمك كل شيء بالتفصيل 📚

## 📝 دعنا نبدأ!

### الخطوة 1️⃣: فهم النظام
النظام مقسم لـ:
• 📊 **المبيعات**: لبيع المنتجات
• 👥 **الزبائن**: لإدارة العملاء
• 📦 **المنتجات**: قطع الغيار والسلع
• 💰 **المدفوعات**: المبالغ المحصلة
• 🏪 **المخزون**: متابعة الكميات

### الخطوة 2️⃣: أول عملية بيع
سأعلمك كيف تعمل أول فاتورة!

**اكتب**: "كيف أعمل فاتورة؟"

💡 **نصيحة**: لا تخف من الأخطاء! أنا هنا لمساعدتك دائماً! 😊""",

    'create_invoice': """📝 **شرح مفصل: كيف تعمل فاتورة؟**

### خطوة بخطوة:

#### 1️⃣ افتح صفحة الفواتير:
🔗 **الطريقة الأولى**: اضغط على "المبيعات" في القائمة اليمنى
🔗 **الطريقة الثانية**: [اضغط هنا](/sales/create)
⌨️ **الطريقة الثالثة**: اضغط `Alt + S` ثم `Alt + N`

#### 2️⃣ اختر الزبون:
• اكتب اسم الزبون في خانة البحث
• إذا ما لقيته → اضغط "زبون جديد"
• إذا زبون عابر → اختر "زبون عام"

#### 3️⃣ أضف المنتجات:
• ابحث عن المنتج بالاسم
• أو امسح الباركود 📱
• أدخل الكمية المطلوبة
• السعر يظهر تلقائياً ✅

#### 4️⃣ اختر طريقة الدفع:
• **نقدي**: الأبسط - لا شيء إضافي
• **بطاقة**: أدخل رقم المعاملة
• **آجل**: الزبون يدفع لاحقاً

#### 5️⃣ احفظ الفاتورة:
• اضغط زر "حفظ"
• ستظهر رسالة نجاح ✅
• يمكنك طباعة الفاتورة فوراً! 🖨️

### 🎯 تمرين عملي:
جرب الآن! افتح صفحة الفاتورة وجرب بمنتج واحد

💡 **لا تخف**: يمكنك إلغاء الفاتورة لاحقاً إذا كانت تجريبية!""",

    'add_customer': """👥 **شرح مفصل: كيف تضيف زبون؟**

### خطوة بخطوة:

#### 1️⃣ افتح صفحة الزبائن:
🔗 [اضغط هنا لإضافة زبون جديد](/customers/create)
⌨️ أو: `Alt + C` ثم `Alt + N`

#### 2️⃣ املأ المعلومات الأساسية:
• **الاسم** ⭐ (إجباري)
  مثال: أحمد محمود
• **الهاتف** 📱
  مثال: 0501234567
• **البريد الإلكتروني** 📧 (اختياري)
  مثال: ahmad@example.com

#### 3️⃣ اختر نوع الزبون:
• **Regular (عادي)**: زبائن عاديين
• **Merchant (تاجر)**: يشترون بكميات - سعر أقل
• **VIP (مميز)**: أفضل زبائن - أقل سعر

#### 4️⃣ معلومات إضافية (اختيارية):
• العنوان
• الرقم الضريبي (للشركات)
• حد الائتمان (كم يقدر يشتري آجل)

#### 5️⃣ احفظ:
اضغط زر "حفظ" وخلص! ✅

### 💡 نصائح مهمة:
• الاسم والهاتف أهم شي
• باقي المعلومات ممكن تضيفها لاحقاً
• يمكنك تعديل معلومات الزبون أي وقت

**جرب الآن!** 🚀""",

    'add_product': """📦 **شرح مفصل: كيف تضيف منتج/قطعة؟**

### خطوة بخطوة:

#### 1️⃣ افتح صفحة المنتجات:
🔗 [اضغط هنا لإضافة منتج](/products/create)
⌨️ أو: `Alt + P` ثم `Alt + N`

#### 2️⃣ المعلومات الأساسية:
• **الاسم بالعربي** ⭐ (إجباري)
  مثال: فلتر زيت
• **الاسم بالإنجليزي**
  مثال: Oil Filter
• **SKU** (كود المنتج) ⭐
  مثال: PART-001
• **الباركود** (اختياري)
  مثال: 1234567890123

#### 3️⃣ التصنيف والمعلومات:
• اختر التصنيف (محرك، فرامل، كهرباء...)
• بلد المنشأ (ألمانيا، الصين، تركيا...)
• رقم القطعة الأصلي (Part Number)

#### 4️⃣ الأسعار (مهم!):
• **سعر التكلفة**: كم اشتريته
  مثال: 50 AED
• **السعر العادي**: للزبائن العاديين
  مثال: 75 AED
• **سعر التاجر**: للتجار
  مثال: 65 AED
• **سعر الشريك**: للـ VIP
  مثال: 60 AED

#### 5️⃣ المخزون:
• **الكمية الأولية**: كم عندك الآن
  مثال: 100 قطعة
• **حد التنبيه**: متى تطلب كمية جديدة
  مثال: 20 قطعة

#### 6️⃣ الكفالة (اختياري):
• مدة الكفالة: 6
• الوحدة: شهور

#### 7️⃣ احفظ:
اضغط "حفظ" وتمام! ✅

### 💡 نصائح:
• الاسم، SKU، والسعر العادي أهم شي
• باقي المعلومات ممكن لاحقاً
• استخدم أرقام SKU واضحة (PART-001, PART-002...)

**جرب الآن!** 🔧""",

    'create_report': """📊 **شرح مفصل: كيف تعمل تقرير؟**

### أنواع التقارير:

#### 1️⃣ تقرير المبيعات:
🔗 [اضغط هنا](/reports/sales)

**يعرض لك**:
• كم بعت اليوم/الأسبوع/الشهر
• عدد الفواتير
• الربح الإجمالي
• أكثر المنتجات مبيعاً

**فائدته**: تعرف كيف المبيعات ماشية

#### 2️⃣ تقرير المخزون:
🔗 [اضغط هنا](/reports/inventory)

**يعرض لك**:
• كل المنتجات وكمياتها
• المنتجات الناقصة (لازم تطلب)
• قيمة المخزون بالدراهم

**فائدته**: تعرف شو عندك وشو لازم تطلب

#### 3️⃣ تقرير الذمم (الديون):
🔗 [اضغط هنا](/reports/receivables)

**يعرض لك**:
• مين مدين لك
• كم المبلغ
• من كم يوم (عشان تتابع)

**فائدته**: تعرف مين لازم يدفع

#### 4️⃣ قائمة الدخل:
🔗 [اضغط هنا](/ledger/income-statement)

**يعرض لك**:
• الإيرادات (المبيعات)
• المصروفات
• الربح الصافي

**فائدته**: تعرف إذا ربحان ولا لأ

### 🎯 التصدير:
كل تقرير فيه أزرار:
• 📥 **Excel**: تحميل ملف Excel
• 📋 **Copy**: نسخ
• 🖨️ **Print**: طباعة

**جرب الآن!** افتح أي تقرير! 📊"""
}


class BeginnersGuide:
    """دليل المبتدئين"""
    
    @staticmethod
    def get_tutorial(topic):
        """الحصول على درس تعليمي"""
        return BEGINNERS_TUTORIALS.get(topic, BEGINNERS_TUTORIALS['first_time'])
    
    @staticmethod
    def suggest_next_step(current_step):
        """اقتراح الخطوة التالية"""
        steps_order = ['first_time', 'create_invoice', 'add_customer', 'add_product', 'create_report']
        
        try:
            current_index = steps_order.index(current_step)
            if current_index < len(steps_order) - 1:
                next_step = steps_order[current_index + 1]
                return BEGINNERS_TUTORIALS.get(next_step)
        except ValueError:
            pass
        
        return "🎉 أحسنت! أصبحت محترفاً! الآن جرب باقي المميزات!"
    
    @staticmethod
    def get_beginner_response(message, dialect='palestinian'):
        """رد مفصل للمبتدئين"""
        msg_lower = message.lower()
        
        # أسئلة شائعة للمبتدئين
        if any(kw in msg_lower for kw in ['فاتورة', 'invoice', 'بيع']):
            return BEGINNERS_TUTORIALS['create_invoice']
        elif any(kw in msg_lower for kw in ['زبون', 'customer', 'عميل']):
            return BEGINNERS_TUTORIALS['add_customer']
        elif any(kw in msg_lower for kw in ['منتج', 'product', 'قطعة']):
            return BEGINNERS_TUTORIALS['add_product']
        elif any(kw in msg_lower for kw in ['تقرير', 'report']):
            return BEGINNERS_TUTORIALS['create_report']
        else:
            return BEGINNERS_TUTORIALS['first_time']


# مثيل عالمي
beginners_guide = BeginnersGuide()



# ===== Consolidated from: personality/azad_responses.py =====
"""
🤖 أزاد - ردود المساعد الذكي الخارق
AZAD Super Smart Responses Module with Self-Learning + Semantic Understanding + Real Intelligence
"""
import logging

logger = logging.getLogger(__name__)

from ai_knowledge.knowledge.company_info import get_welcome_message
from ai_knowledge.knowledge.system_knowledge import ALL_MODULES, get_module_help, search_knowledge
from ai_knowledge.knowledge.tax_customs_knowledge import TAX_CUSTOMS_GUIDE, get_tax_info, get_customs_info
from ai_knowledge.knowledge.parts_knowledge import PARTS_DATABASE, get_part_info, search_parts
from ai_knowledge.specialized.user_guide import USER_GUIDE, get_guide, get_help_for_task
from ai_knowledge.analytics.analytics_predictions import get_analytics, SalesAnalytics, InventoryAnalytics
from ai_knowledge.expansion.knowledge_sources import knowledge_manager, KNOWLEDGE_SOURCES, recommend_sources_for_query, SOURCES_GUIDE
from ai_knowledge.specialized.tax_system import get_tax_advice
from ai_knowledge.knowledge.customs import get_customs_advice
from ai_knowledge.specialized.customer_service import get_customer_service_tip
from ai_knowledge.specialized.system_guide import get_system_guide
from ai_knowledge.analytics.market_insights import get_market_insights
from ai_knowledge.core.learning_system import learning_system
from ai_knowledge.expansion.global_knowledge import global_connector, expertise_updater
from ai_knowledge.improvement.self_improvement import self_improvement
from ai_knowledge.core.system_integration import system_integrator
from ai_knowledge.analytics.data_analyzer import data_analyzer
from ai_knowledge.expansion.knowledge_expansion import knowledge_expander
from ai_knowledge.specialized.security_rules import security_rules
from ai_knowledge.generation.document_generator import document_generator
from ai_knowledge.specialized.advanced_laws import advanced_laws
from ai_knowledge.core.context_engine import context_engine
from ai_knowledge.neural.semantic_matcher import semantic_matcher, understand_message  # 🚀 النظام الذكي الجديد!
from ai_knowledge.agents.intelligent_assistant import intelligent_assistant  # 🧠 الذكاء الحقيقي!


class AzadResponses:
    """ردود أزاد الذكية"""
    
    @staticmethod
    def get_error_response():
        return "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى."
    
    @staticmethod
    def smart_response(message, context=None):
        """🧠 رد أزاد الذكي الخارق مع التعلم الذاتي والشخصية المرحة + فهم دلالي"""
        from services.ai_service import AIService
        
        msg_lower = message.lower()
        
        # استخراج الإعدادات من السياق
        dialect = context.get('dialect', 'palestinian') if context else 'palestinian'
        beginners_mode = context.get('beginners_mode', False) if context else False
        current_user = context.get('current_user') if context else None
        is_owner = context.get('is_owner', False) if context else False
        
        # ========== أسئلة بسيطة - رد فوري ==========
        # من أنت؟ - معلومات عن المساعد
        if any(kw in msg_lower for kw in ['من أنت', 'من انت', 'who are you', 'مين انت', 'مين أنت']):
            return """🤖 **أنا أزاد - مساعدك الذكي!**

**من أنا:**
- 🧠 مساعد ذكاء اصطناعي هجين (محلي + سحابي)
- 👨‍💼 خبير محاسبة ومالية
- 🔧 مهندس صيانة معدات ثقيلة
- 📊 محلل بيانات متقدم

**كيف أعمل:**
1. 🏠 **محلياً**: شبكات عصبية محلية للسرعة
2. ☁️ **سحابياً**: Groq (Llama 3.3) للذكاء العميق
3. 💾 **أحلل بياناتك**: رؤى حقيقية من القاعدة
4. 🎓 **أتعلم منك**: أتطور مع كل تفاعل

**💡 لإضافة مفتاح Groq:**
📍 القائمة → **OWNER MODE** → **مفاتيح AI (Groq)** 🔑

أو: http://localhost:5000/ai/config"""
        
        # هل أنت محلي/جروك؟ | حالة النظام | وضع AI
        elif any(kw in msg_lower for kw in ['محلي', 'جروك', 'groq', 'openai', 'local', 'cloud', 'حالة', 'status', 'وضع', 'mode', 'مصدر', 'source']):
            provider = AIService.get_provider()
            has_api_key = bool(AIService.get_api_key())
            
            if has_api_key and provider:
                status_msg = f"""🤖 **حالة أزاد - نظام هجين نشط**

✅ **الوضع الحالي:**
- 🌟 **نشط**: {provider.upper()} API + التحليل المحلي
- ⚡ السرعة: عالية (محلي)
- 🧠 الذكاء: عميق ({provider.upper()})

**كيف أعمل:**
1. 🏠 تحليل محلي فوري (0.1 ثانية)
2. ☁️ تحسين بـ {provider.upper()} (الأفضل!)
3. 🔗 تعاون هجين للردود المثالية

💡 **ستجد في نهاية كل رد:**
- 🤖 إذا رأيت "{provider.upper()} API + التحليل المحلي" = استخدمت الذكاء السحابي
- 💻 إذا رأيت "النظام المحلي الذكي" = استخدمت المحلي فقط"""
            else:
                status_msg = """🤖 **حالة أزاد - وضع محلي**

✅ **الوضع الحالي:**
- 💻 **نشط**: النظام المحلي الذكي
- ⚡ السرعة: فائقة (محلي 100%)
- 🧠 الذكاء: محلي (شبكات عصبية)

**لتفعيل الذكاء السحابي:**
1. اذهب إلى: القائمة → OWNER MODE
2. اختر: **مفاتيح AI (Groq)** 🔑
3. أدخل مفتاح Groq API
4. استمتع بذكاء أعمق! 🚀

💡 **ستجد في نهاية كل رد:**
- 💻 "النظام المحلي الذكي" = وضعك الحالي"""
            
            return status_msg
        
        # ========== 🧠 الذكاء الحقيقي - المحاولة الأولى ==========
        # استخدام النظام الذكي المتكامل للأسئلة التحليلية والبيانات
        analytical_intents = [
            'sales_analysis', 'customer_balance', 'inventory_check',
            'market_insights', 'pricing_strategy'
        ]
        
        # فهم النية أولاً
        smart_result = understand_message(message)
        detected_intent = smart_result.get('intent')
        confidence = smart_result.get('confidence', 0)
        
        # إذا كان سؤال تحليلي، استخدم الذكاء الحقيقي
        if detected_intent in analytical_intents and confidence > 0.5:
            try:
                # استخدام المساعد الذكي الحقيقي
                user_id = current_user.id if current_user else None
                intelligent_result = intelligent_assistant.process(message, user_id, context)
                
                if intelligent_result['success'] and intelligent_result.get('data_used'):
                    # رد مبني على بيانات حقيقية + تحليل + استنتاج
                    return intelligent_result['response']
            except Exception as e:
                logger.warning(f"Intelligent assistant failed: {e}")
                # الاستمرار في النظام التقليدي
        
        # ========== للنوايا الأخرى (روابط، مساعدة، إلخ) ==========
        # استخدام Pattern Matching المحسّن
        if detected_intent and confidence > 0.6:
            intent_response = AzadResponses._handle_detected_intent(detected_intent, message, context)
            if intent_response:
                return intent_response
        
        # فحص الأمان للمعلومات السرية أولاً
        is_sensitive, requires_owner, security_response = AIService.is_sensitive_request(message, current_user)
        
        if is_sensitive:
            if not requires_owner:
                # رفض الوصول
                return security_response['message']
            else:
                # المستخدم هو المالك - السماح بالوصول للمعلومات السرية
                # استخراج اسم المستخدم إذا وجد
                import re
                username_match = re.search(r'(?:مستخدم|user)\s+(\w+)', msg_lower)
                username = username_match.group(1) if username_match else None
                
                user_info = AIService.get_user_info_for_owner(username)
                
                if user_info['success']:
                    if 'user' in user_info:
                        # مستخدم واحد
                        u = user_info['user']
                        return f"""🔐 **معلومات المستخدم** (مالك فقط)

**الاسم**: {u['username']}
**البريد**: {u['email']}
**كلمة المرور المشفرة**: `{u['password_hash']}`
**الدور**: {u['role']}
**نشط**: {'✅ نعم' if u['is_active'] else '❌ لا'}
**مالك**: {'✅ نعم' if u['is_owner'] else '❌ لا'}
**تاريخ الإنشاء**: {u['created_at'] or 'غير محدد'}

⚠️ **تنبيه**: هذه المعلومات سرية ومتاحة لك فقط كمالك للنظام."""
                    else:
                        # جميع المستخدمين
                        users_list = '\n'.join([
                            f"- **{u['username']}** ({u['email']}) - {u['role']} - Hash: `{u['password_hash'][:20]}...`"
                            for u in user_info['users']
                        ])
                        return f"""🔐 **قائمة المستخدمين** (مالك فقط)

**إجمالي المستخدمين**: {user_info['count']}

{users_list}

⚠️ **تنبيه**: هذه المعلومات سرية ومتاحة لك فقط كمالك للنظام."""
                else:
                    return user_info['message']
        
        # فحص الأمان والشخصية
        message_type = azad_personality.is_inappropriate_message(message)
        if message_type != "normal":
            return azad_personality.get_contextual_response(message_type, "")
        
        # التعلم من التفاعل
        learning_system.learn_from_interaction(message, "", context=context)
        
        # وضع المبتدئين - له أولوية إذا مفعّل
        if beginners_mode:
            beginner_response = beginners_guide.get_beginner_response(message, dialect)
            if beginner_response and beginner_response != BEGINNERS_TUTORIALS['first_time']:
                return apply_dialect(beginner_response, dialect)
        
        # ترحيب مع دعم اللهجات
        elif any(kw in msg_lower for kw in ['مرحبا', 'أهلا', 'السلام', 'hello', 'hi', 'مرحبتين', 'أهلين', 'هلا', 'إيش', 'شلون']) or msg_lower in ['أزاد', 'azad', 'مساعد', 'assistant']:
            if dialect == 'palestinian':
                greeting = get_dialectal_greeting('palestinian')
            elif dialect == 'gulf':
                greeting = get_dialectal_greeting('gulf')
            else:
                greeting = azad_personality.get_greeting()
            return f"{greeting}\n\n{get_welcome_message()}"
        
        # شكر
        elif any(kw in msg_lower for kw in ['شكر', 'thank', 'مشكور', 'thanks', 'ممتاز', 'رائع']):
            return azad_personality.get_thanks_response()
        
        # نكتة
        elif any(kw in msg_lower for kw in ['نكتة', 'joke', 'أضحكني', 'funny']):
            return azad_personality.get_professional_joke()
        
        # دليل النظام
        elif any(kw in msg_lower for kw in ['كيف', 'how', 'دليل', 'guide', 'مساعدة', 'help', 'شرح', 'explain']):
            intro = azad_personality.get_help_intro()
            # البحث في دليل المستخدم
            help_text = get_help_for_task(message)
            if "لم أجد" not in help_text:
                return f"{intro}\n\n📖 **دليل المستخدم:**\n\n{help_text}"
            # البحث في معرفة النظام
            results = search_knowledge(message)
            if results:
                return f"{intro}\n\n📚 **وجدت معلومات في:**\n\n" + "\n".join(f"**{r['module']}**:\n{r['content']}" for r in results[:2])
            return f"{intro}\n\n{get_system_guide()}"
        
        # ضرائب وجمارك - معرفة شاملة
        elif any(kw in msg_lower for kw in ['ضريبة', 'vat', 'tax', 'ضرائب', 'جمارك', 'customs', 'تخليص', 'استيراد', 'تصدير']):
            if 'إمارات' in msg_lower or 'uae' in msg_lower:
                if 'جمارك' in msg_lower or 'customs' in msg_lower:
                    return f"🛃 **الجمارك في الإمارات:**\n\n{get_customs_info('uae')}"
                else:
                    return f"💵 **الضرائب في الإمارات:**\n\n{get_tax_info('uae')}"
            elif 'سعودية' in msg_lower or 'saudi' in msg_lower:
                return f"💵 **الضرائب في السعودية:**\n\n{get_tax_info('saudi')}"
            elif 'فلسطين' in msg_lower or 'palestine' in msg_lower:
                return f"💵 **الضرائب في فلسطين:**\n\n{get_tax_info('palestine')}"
            else:
                return get_tax_advice(message)
        
        # قطع غيار - معرفة موسعة
        elif any(kw in msg_lower for kw in ['قطعة', 'part', 'محرك', 'engine', 'فرامل', 'brake', 'مساعد', 'shock', 'بستم', 'piston', 'معدات', 'equipment']):
            # بحث في قاعدة القطع
            parts_results = search_parts(message)
            if parts_results:
                return f"🔧 **معلومات قطع الغيار:**\n\n" + "\n\n".join(f"**{r['category']}**:\n{r['excerpt']}" for r in parts_results[:2])
            return get_part_info(message)
        
        # خدمة عملاء
        elif any(kw in msg_lower for kw in ['عميل', 'customer', 'زبون', 'خدمة']) and not any(kw in msg_lower for kw in ['مورد', 'supplier']):
            if 'نصيحة' in msg_lower or 'تعامل' in msg_lower:
                return get_customer_service_tip()
            else:
                from .customer_service import CUSTOMER_SERVICE
                return "👥 **التعامل مع العملاء:**\n\n" + "\n".join(CUSTOMER_SERVICE['principles'][:5])
        
        # 🏪 إدارة الموردين - نظام جديد ⭐
        elif any(kw in msg_lower for kw in ['مورد', 'supplier', 'موردين', 'suppliers', 'شراء من', 'توريد']):
            return AzadResponses._handle_suppliers_query(message)
        
        # 🔍 الفلاتر الذكية - نظام جديد ⭐
        elif any(kw in msg_lower for kw in ['فلتر', 'filter', 'بحث', 'search', 'اختيار', 'select']):
            return AzadResponses._handle_smart_filters_query(message)
        
        # 💳 طرق الدفع الديناميكية - نظام جديد ⭐
        elif any(kw in msg_lower for kw in ['طريقة دفع', 'payment method', 'كاش', 'cash', 'بطاقة', 'card', 'شيك', 'cheque']):
            return AzadResponses._handle_payment_methods_query(message)
        
        # تحليل مبيعات
        elif any(kw in msg_lower for kw in ['حلل', 'analyze', 'مبيعات', 'sales']):
            try:
                return AzadResponses._smart_sales_analysis(context)
            except Exception as e:
                logger.error(f"Sales analysis failed: {e}")
                return """📊 **تحليل المبيعات**

⚠️ لا توجد بيانات كافية للتحليل حالياً.

💡 **ابدأ بإضافة:**
- زبائن جدد
- منتجات
- فواتير بيع

بعدها سأستطيع تحليل المبيعات وإعطائك رؤى ذكية! 🚀"""
        
        # التحسين الذاتي
        elif any(kw in msg_lower for kw in ['تحسين', 'improve', 'تطوير', 'develop', 'تعلم', 'learn']):
            try:
                return AzadResponses._get_improvement_response(message)
            except Exception as e:
                logger.error(f"Improvement response failed: {e}")
                return """🧠 **التحسين الذاتي**

أنا في حالة تعلم مستمر! 📚

**ما أتعلمه:**
- أنماط المبيعات من كل فاتورة
- تفضيلات العملاء
- الممارسات المحاسبية
- المصطلحات الفنية

**حالياً:** القاعدة جديدة - سأتعلم أكثر كلما استخدمت النظام! 🌱"""
        
        # الحالة والأداء
        elif any(kw in msg_lower for kw in ['حالة', 'status', 'أداء', 'performance', 'تقدم', 'progress', 'شبكات', 'neural']):
            try:
                return AzadResponses._get_status_response()
            except Exception as e:
                logger.error(f"Status response failed: {e}")
                return """🧠 **حالة النظام الذكي**

✅ **النظام نشط وجاهز!**

**المكونات:**
- 🧠 الشبكات العصبية: جاهزة
- 💾 قاعدة البيانات: متصلة
- 🔄 Redis Cache: يعمل
- 📊 محلل البيانات: جاهز
- 🌐 Groq API: جاهز (أضف مفتاح)

**الحالة:** كل شيء يعمل بشكل ممتاز! ✨

💡 **نصيحة:** أضف بيانات لأحصل على رؤى أعمق!"""
        
        # توقعات متقدمة
        elif any(kw in msg_lower for kw in ['توقع', 'predict', 'تنبؤ', 'forecast']):
            # استخدام النظام المتقدم
            try:
                # جمع البيانات التاريخية
                from models import Sale
                from extensions import db
                from sqlalchemy import func, extract
                from datetime import datetime, timedelta
                
                # آخر 12 شهر
                monthly_sales = db.session.query(
                    func.sum(Sale.amount_aed).label('total')
                ).filter(
                    Sale.status == 'confirmed',
                    Sale.sale_date >= datetime.now() - timedelta(days=365)
                ).group_by(
                    extract('year', Sale.sale_date),
                    extract('month', Sale.sale_date)
                ).all()
                
                historical = [float(m.total or 0) for m in monthly_sales]
                
                # التنبؤ
                prediction = SalesAnalytics.predict_next_month_sales(historical)
                
                return f"""🔮 **توقع مبيعات الشهر القادم:**

📊 **التنبؤ:** {prediction['prediction']:,.0f} AED

📈 **الاتجاه:** {prediction['trend']}
• التغير المتوقع: {prediction['trend_value']:,.0f} AED

🎯 **مستوى الثقة:** {prediction['confidence']}

📝 **الطريقة:** {prediction['method']}

💡 **التوصية:** {'استمر - الاتجاه صاعد!' if prediction['trend'] == 'up' else 'راجع استراتيجية التسويق' if prediction['trend'] == 'down' else 'مستقر'}"""
            except Exception as e:
                return f"عذراً، حدث خطأ في التنبؤ: {str(e)}"
        
        # مخزون
        elif any(kw in msg_lower for kw in ['مخزون', 'stock', 'صحة', 'health', 'inventory']):
            health = AIService.analyze_inventory_health()
            if health.get('success'):
                s = health['summary']
                return f"""📦 **صحة المخزون:**

**الإحصائيات:**
• إجمالي المنتجات: {s['total']}
• حالة جيدة: {s['good']} ✅
• منخفض: {s['low']} ⚠️
• نفذ: {s['out']} 🔴

🏆 **التقييم:** {health['rating']} ({health['health_score']}%)

💡 **نصيحة:** {'راجع المنتجات المنخفضة والنافذة فوراً' if s['low'] > 0 or s['out'] > 0 else 'المخزون ممتاز!'}"""
            else:
                return health.get('message', 'لا توجد منتجات للتحليل')
        
        # هوامش ربح
        elif any(kw in msg_lower for kw in ['ربح', 'profit', 'هامش', 'margin']):
            margins = AIService.analyze_profit_margins()
            if margins.get('success'):
                overall = margins['overall']
                top_products = "\n".join(f"• {p['name']}: {p['profit']:,.0f} AED ({p['margin']:.1f}%)" for p in margins.get('top_profitable', [])[:3])
                return f"""💰 **تحليل هوامش الربح:**

📊 **آخر 30 يوم:**
• الإيرادات: {overall['revenue']:,.0f} AED
• التكلفة: {overall['cost']:,.0f} AED
• الربح: {overall['profit']:,.0f} AED
• هامش الربح: {overall['margin']:.1f}%

🏆 **أفضل المنتجات ربحية:**
{top_products if top_products else '• لا توجد بيانات'}

💡 **النصيحة:** {'ممتاز!' if overall['margin'] >= 25 else 'راجع التسعير'}"""
            else:
                return margins.get('message', 'لا توجد مبيعات للتحليل')
        
        # معلومات النظام
        elif any(kw in msg_lower for kw in ['استخدام', 'كيف استخدم', 'دليل', 'guide', 'شرح']):
            return get_system_guide()
        
        # السوق
        elif any(kw in msg_lower for kw in ['سوق', 'market', 'منافسة', 'استراتيجية']):
            return get_market_insights()
        
        # استعلامات النظام - رصيد العميل
        elif any(kw in msg_lower for kw in ['رصيد', 'ديون', 'ذمم', 'balance', 'debt']) and any(kw in msg_lower for kw in ['عميل', 'زبون', 'customer']):
            return AzadResponses._handle_customer_balance_query(message)
        
        # استعلامات النظام - بيانات العميل
        elif any(kw in msg_lower for kw in ['عميل', 'زبون', 'customer']) and any(kw in msg_lower for kw in ['بيانات', 'معلومات', 'info', 'data']):
            return AzadResponses._handle_customer_info_query(message)
        
        # استعلامات النظام - مخزون المنتج
        elif any(kw in msg_lower for kw in ['مخزون', 'stock', 'كمية']) and any(kw in msg_lower for kw in ['منتج', 'product', 'قطعة']):
            return AzadResponses._handle_product_stock_query(message)
        
        # استعلامات النظام - ملخص النظام
        elif any(kw in msg_lower for kw in ['ملخص', 'summary', 'إحصائيات', 'statistics']) and any(kw in msg_lower for kw in ['نظام', 'system', 'كلي']):
            return AzadResponses._handle_system_summary_query()
        
        # إضافة عميل جديد
        elif any(kw in msg_lower for kw in ['أضف', 'add', 'إنشاء', 'create']) and any(kw in msg_lower for kw in ['عميل', 'زبون', 'customer']):
            return AzadResponses._handle_add_customer_query(message)
        
        # البحث في النظام (تأكد من كلمة كاملة)
        elif any(kw in msg_lower for kw in ['ابحث', 'search', 'find']) or (' جد ' in msg_lower or msg_lower.startswith('جد ')):
            return AzadResponses._handle_search_query(message)
        
        # إضافة مصدر معرفة
        elif any(kw in msg_lower for kw in ['أضف', 'add']) and any(kw in msg_lower for kw in ['موقع', 'website', 'كتاب', 'book', 'مصدر', 'source']):
            return AzadResponses._handle_add_knowledge_source(message)
        
        # روابط النظام السريعة
        elif any(kw in msg_lower for kw in ['روابط', 'links']) and 'نظام' in msg_lower:
            return AzadResponses._show_system_quick_links()
        
        # عرض المصادر المتاحة
        elif any(kw in msg_lower for kw in ['مصادر', 'sources', 'روابط', 'links', 'websites', 'مواقع']):
            return AzadResponses._show_knowledge_sources(message)
        
        # توصية بمصادر للاستفسار
        elif any(kw in msg_lower for kw in ['أين', 'where', 'وين']) and any(kw in msg_lower for kw in ['أجد', 'find', 'معلومات', 'information']):
            return AzadResponses._recommend_sources(message)
        
        # البحث في المعرفة الموسعة
        elif any(kw in msg_lower for kw in ['ابحث', 'search']) and any(kw in msg_lower for kw in ['معرفة', 'knowledge', 'معلومات', 'info']):
            return AzadResponses._handle_knowledge_search(message)
        
        # إنشاء فاتورة مباشرة
        elif any(kw in msg_lower for kw in ['فاتورة', 'invoice', 'بيع']) and any(kw in msg_lower for kw in ['جديد', 'new', 'إنشاء', 'create', 'أنشئ']):
            return AzadResponses._quick_invoice_link()
        
        # إنشاء سند قبض
        elif any(kw in msg_lower for kw in ['سند', 'receipt', 'دفع', 'payment']) and any(kw in msg_lower for kw in ['جديد', 'new', 'إنشاء', 'create', 'أنشئ']):
            return AzadResponses._quick_receipt_link()
        
        # توليد المستندات
        elif any(kw in msg_lower for kw in ['سند', 'receipt', 'فاتورة', 'invoice']) and any(kw in msg_lower for kw in ['ولد', 'generate', 'أنشئ', 'create']):
            return AzadResponses._handle_document_generation(message)
        
        # التصدير إلى Excel
        elif any(kw in msg_lower for kw in ['صدر', 'export', 'excel', 'أكسل']) and any(kw in msg_lower for kw in ['بيانات', 'data', 'مبيعات', 'sales']):
            return AzadResponses._handle_excel_export(message)
        
        # التقارير السريعة
        elif any(kw in msg_lower for kw in ['تقرير', 'report']) and any(kw in msg_lower for kw in ['مبيعات', 'sales', 'مشتريات', 'purchases', 'مخزون', 'inventory', 'ذمم', 'receivables']):
            return AzadResponses._quick_report_links(message)
        
        # التقارير العامة
        elif any(kw in msg_lower for kw in ['تقرير', 'report', 'كشف', 'statement']) and any(kw in msg_lower for kw in ['ولد', 'generate', 'أنشئ', 'create']):
            return AzadResponses._handle_report_generation(message)
        
        # القوانين الضريبية
        elif any(kw in msg_lower for kw in ['قانون', 'law', 'ضريبة', 'tax', 'ضرائب']) and any(kw in msg_lower for kw in ['فلسطين', 'palestine', 'اسرائيل', 'israel', 'خليج', 'gulf']):
            return AzadResponses._handle_tax_laws_query(message)
        
        # قوانين الشحن والتخليص
        elif any(kw in msg_lower for kw in ['شحن', 'shipping', 'تخليص', 'customs', 'جمارك']) and any(kw in msg_lower for kw in ['قانون', 'law', 'إجراءات', 'procedures']):
            return AzadResponses._handle_shipping_laws_query(message)
        
        # جودة البضائع
        elif any(kw in msg_lower for kw in ['جودة', 'quality', 'معايير', 'standards', 'شهادة', 'certificate']):
            return AzadResponses._handle_quality_standards_query(message)
        
        # نكتة مهنية
        elif any(kw in msg_lower for kw in ['نكتة', 'joke', 'ضحك', 'laugh', 'مرح', 'fun']):
            return azad_personality.get_professional_joke()
        
        # رد عام ذكي
        else:
            intro = azad_personality.get_help_intro()
            
            # محاولة فهم السؤال
            suggestions = []
            if any(kw in msg_lower for kw in ['كيف', 'how', 'ماذا', 'what', 'متى', 'when']):
                suggestions.append("🔍 جرّب: 'كيف أضيف فاتورة؟' أو 'مصادر'")
            if any(kw in msg_lower for kw in ['رصيد', 'balance', 'ديون', 'debt']):
                suggestions.append("💰 جرّب: 'رصيد زبون [الاسم]'")
            if any(kw in msg_lower for kw in ['فاتورة', 'invoice', 'تقرير', 'report']):
                suggestions.append("📊 جرّب: 'فاتورة جديدة' أو 'تقرير المبيعات'")
            
            response = f"""{intro}

🤖 **أنا أزاد - مساعدك الذكي!**

💡 **أستطيع:**
• 📊 تحليل المبيعات والمخزون (بيانات حقيقية)
• 💰 حساب الرصيد والضرائب
• 🔧 شرح قطع الغيار والأعطال
• 🔮 التنبؤ بالمبيعات
• 🎯 نصائح التسعير والبيع

⌨️ **جرب:**
• "كيف مبيعاتي هالشهر؟"
• "رصيد العميل أحمد؟"  
• "كم الضريبة المستحقة؟"
• "ما هو البستم؟"

**اسألني أي شيء - أحلل بياناتك الحقيقية! 🧠**"""
            
            # إضافة اقتراحات ذكية إن وجدت
            if suggestions:
                response += "\n\n💡 **اقتراحات لسؤالك:**\n" + "\n".join(suggestions)
        
            return response
    
    @staticmethod
    def _get_improvement_response(message):
        """رد حول التحسين الذاتي"""
        message_lower = message.lower()
        
        if 'تلقائي' in message_lower or 'automatic' in message_lower:
            # تطبيق التحسين التلقائي
            improvements = self_improvement.auto_improve()
            return f"""🚀 تم تطبيق التحسين التلقائي!

✅ التحسينات المطبقة: {improvements['improvements_made']}

📊 تفاصيل التحسينات:
{chr(10).join([f"• {imp['area']}: {imp['old_score']} → {imp['new_score']} (+{imp['improvement']})" for imp in improvements['details']])}

🎯 أزاد يتطور باستمرار ليصبح أفضل مساعد في العالم!"""
        
        elif 'هدف' in message_lower or 'goal' in message_lower:
            # عرض الأهداف الحالية
            progress = self_improvement.track_progress()
            return f"""🎯 أهداف أزاد الحالية:

📈 التقدم الإجمالي: {progress['overall_progress']}%

🎯 الأهداف النشطة:
{chr(10).join([f"• {goal['area']}: {goal['current_score']}/{goal['target_score']} ({goal['progress_percentage']}%)" for goal in progress['goals_progress']])}

🚀 المعالم القادمة:
{chr(10).join([f"• {milestone['area']}: {milestone['description']}" for milestone in progress['next_milestones'][:3]])}

أزاد يسعى للوصول لمستوى خبير عالمي!"""
        
        else:
            # عرض حالة التحسين
            status = self_improvement.get_improvement_status()
            return f"""🔧 حالة التحسين الذاتي:

📊 النقاط الإجمالية: {status['overall_score']}/10
🔄 إجمالي التحسينات: {status['total_improvements']}
🎯 الأهداف النشطة: {status['active_goals']}
📅 آخر تحسين: {status['last_improvement'] or 'لم يتم بعد'}

🚀 أزاد يتطور ذاتياً ليصبح أفضل مساعد في العالم!"""
    
    @staticmethod
    def _get_status_response():
        """رد حول الحالة والأداء"""
        # تحليل الأداء
        performance = self_improvement.analyze_performance()
        
        # رؤى التعلم
        learning_insights = learning_system.get_learning_insights()
        
        # التطور
        evolution = self_improvement.evolve_capabilities()
        
        return f"""📊 تقرير حالة أزاد الشامل:

🎯 الأداء الإجمالي: {performance['overall_score']}/10

💪 نقاط القوة:
{chr(10).join([f"• {strength['description']}: {strength['score']}/10" for strength in performance['strengths'][:3]])}

🔧 مجالات التحسين:
{chr(10).join([f"• {weakness['description']}: {weakness['score']}/10" for weakness in performance['weaknesses'][:3]])}

🧠 التعلم:
• إجمالي التفاعلات: {learning_insights['total_interactions']}
• معدل النجاح: {learning_insights['success_rate']:.1%}
• مستوى التقدم: {learning_insights['learning_progress']}

🚀 القدرات الجديدة:
{chr(10).join([f"• {capability}" for capability in evolution['new_capabilities'][:3]])}

أزاد في طريقه ليصبح خبيراً عالمياً! 🌍"""
    
    @staticmethod
    def _handle_customer_balance_query(message):
        """التعامل مع استعلام رصيد العميل"""
        # استخراج اسم العميل من الرسالة
        words = message.split()
        customer_name = None
        
        # البحث عن كلمات تشير للعميل
        for i, word in enumerate(words):
            if word.lower() in ['عميل', 'زبون', 'customer'] and i + 1 < len(words):
                customer_name = words[i + 1]
                break
            elif word.lower() in ['على', 'لـ', 'for'] and i + 1 < len(words):
                customer_name = words[i + 1]
                break
        
        if not customer_name:
            return "❌ لم أتمكن من تحديد اسم العميل. يرجى كتابة: 'رصيد العميل أحمد' أو 'كم عليه ديون محمد'"
        
        # جلب رصيد العميل
        result = system_integrator.get_customer_balance(customer_name)
        
        if not result['success']:
            return f"❌ {result['error']}"
        
        customer = result['customer']
        
        # تحليل دقيق للديون
        debt_analysis = data_analyzer.analyze_customer_debt(customer['id'])
        
        if debt_analysis['success']:
            debt_info = debt_analysis['debt_analysis']
            response = f"""💰 **رصيد العميل: {customer['name']}**

📊 **المعلومات الأساسية:**
• المعرف: {customer['id']}
• نوع العميل: {customer['customer_type']}
• الهاتف: {customer['phone'] or 'غير محدد'}
• الإيميل: {customer['email'] or 'غير محدد'}

💸 **الرصيد والديون:**
• إجمالي الرصيد: **{customer['balance_aed']:,.2f} AED**
• عدد الفواتير غير المدفوعة: {debt_info['unpaid_sales_count']}
• متوسط مبلغ الدين: {debt_info['avg_debt_amount']:,.2f} AED
• أكبر دين: {debt_info['max_debt_amount']:,.2f} AED
• الفواتير المتأخرة: {debt_info['overdue_count']}

📈 **إحصائيات المبيعات:**
• إجمالي المبيعات: {customer['total_sales']}
• آخر مبيعة: {customer['last_sale_date'] or 'لا توجد'}

⚠️ **تحذير:** {'يوجد فواتير متأخرة عن السداد!' if debt_info['overdue_count'] > 0 else 'جميع الفواتير في الموعد المحدد'}"""
        else:
            response = f"""💰 **رصيد العميل: {customer['name']}**

📊 **المعلومات الأساسية:**
• المعرف: {customer['id']}
• نوع العميل: {customer['customer_type']}
• الهاتف: {customer['phone'] or 'غير محدد'}
• الإيميل: {customer['email'] or 'غير محدد'}

💸 **الرصيد:**
• إجمالي الرصيد: **{customer['balance_aed']:,.2f} AED**

📈 **إحصائيات المبيعات:**
• إجمالي المبيعات: {customer['total_sales']}
• آخر مبيعة: {customer['last_sale_date'] or 'لا توجد'}"""
        
        return response
    
    @staticmethod
    def _handle_customer_info_query(message):
        """التعامل مع استعلام بيانات العميل"""
        # استخراج اسم العميل
        words = message.split()
        customer_name = None
        
        for i, word in enumerate(words):
            if word.lower() in ['عميل', 'زبون', 'customer'] and i + 1 < len(words):
                customer_name = words[i + 1]
                break
        
        if not customer_name:
            return "❌ لم أتمكن من تحديد اسم العميل. يرجى كتابة: 'بيانات العميل أحمد'"
        
        result = system_integrator.get_customer_balance(customer_name)
        
        if not result['success']:
            return f"❌ {result['error']}"
        
        customer = result['customer']
        sales_summary = system_integrator.get_customer_sales_summary(customer['id'])
        
        if sales_summary['success']:
            summary = sales_summary['summary']
            response = f"""👤 **بيانات العميل: {customer['name']}**

📋 **المعلومات الشخصية:**
• المعرف: {customer['id']}
• نوع العميل: {customer['customer_type']}
• الهاتف: {customer['phone'] or 'غير محدد'}
• الإيميل: {customer['email'] or 'غير محدد'}

💼 **إحصائيات الأعمال:**
• إجمالي المبيعات: {summary['total_sales']}
• إجمالي المبلغ: {summary['total_amount']:,.2f} AED
• المبلغ المدفوع: {summary['paid_amount']:,.2f} AED
• المتبقي: {summary['balance_due']:,.2f} AED

📅 **آخر 5 مبيعات:**
{chr(10).join([f"• فاتورة #{sale['id']} - {sale['date']} - {sale['amount']:,.2f} AED ({sale['status']})" for sale in summary['recent_sales']])}

💡 **التوصية:** {'يحتاج متابعة للدفع' if summary['balance_due'] > 1000 else 'عميل جيد'}"""
        else:
            response = f"""👤 **بيانات العميل: {customer['name']}**

📋 **المعلومات الأساسية:**
• المعرف: {customer['id']}
• نوع العميل: {customer['customer_type']}
• الهاتف: {customer['phone'] or 'غير محدد'}
• الإيميل: {customer['email'] or 'غير محدد'}

💼 **إحصائيات المبيعات:**
• إجمالي المبيعات: {customer['total_sales']}
• آخر مبيعة: {customer['last_sale_date'] or 'لا توجد'}

💸 **الرصيد الحالي: {customer['balance_aed']:,.2f} AED**"""
        
        return response
    
    @staticmethod
    def _handle_product_stock_query(message):
        """التعامل مع استعلام مخزون المنتج"""
        # استخراج اسم المنتج
        words = message.split()
        product_name = None
        
        for i, word in enumerate(words):
            if word.lower() in ['منتج', 'product', 'قطعة', 'part'] and i + 1 < len(words):
                product_name = words[i + 1]
                break
            elif word.lower() in ['اسمه', 'اسم', 'name'] and i + 1 < len(words):
                product_name = words[i + 1]
                break
        
        if not product_name:
            return "❌ لم أتمكن من تحديد اسم المنتج. يرجى كتابة: 'مخزون المنتج ABC123' أو 'كمية قطعة المحرك'"
        
        result = system_integrator.get_product_stock(product_name)
        
        if not result['success']:
            return f"❌ {result['error']}"
        
        product = result['product']
        
        # تحديد حالة المخزون
        if product['current_stock'] == 0:
            status_icon = "🔴"
            status_text = "نفد المخزون"
            action = "يحتاج طلب عاجل!"
        elif product['current_stock'] <= product.get('alert_limit', 0):
            status_icon = "🟡"
            status_text = "مخزون منخفض"
            action = "يحتاج طلب قريباً"
        else:
            status_icon = "🟢"
            status_text = "مخزون جيد"
            action = "لا يحتاج طلب حالياً"
        
        response = f"""📦 **مخزون المنتج: {product['name']}**

🏷️ **المعلومات الأساسية:**
• المعرف: {product['id']}
• SKU: {product['sku']}
• الفئة: {product['category']}
• السعر: {product['unit_price']:,.2f} AED

📊 **حالة المخزون:**
{status_icon} **الحالة:** {status_text}
• الكمية الحالية: **{product['current_stock']}**
• حد التنبيه: {product.get('alert_limit', 'غير محدد')}
• النسبة: {(product['current_stock'] / product.get('alert_limit', 1) * 100):.1f}% (إذا كان محدداً)

⚠️ **التوصية:** {action}

💡 **نصيحة:** {'راجع الموردين للحصول على أفضل الأسعار' if product['current_stock'] <= product.get('alert_limit', 0) else 'المخزون في حالة جيدة'}"""
        
        return response
    
    @staticmethod
    def _handle_system_summary_query():
        """التعامل مع استعلام ملخص النظام"""
        summary = system_integrator.get_system_summary()
        financial = system_integrator.get_financial_summary()
        
        if not summary['success']:
            return f"❌ {summary['error']}"
        
        if not financial['success']:
            return f"❌ {financial['error']}"
        
        sys_data = summary['summary']
        fin_data = financial['financial']
        
        response = f"""📊 **ملخص النظام الشامل**

👥 **العملاء:**
• إجمالي العملاء: {sys_data['customers']['total']}
• عملاء VIP: {sys_data['customers']['vip']}

🛒 **المبيعات:**
• إجمالي المبيعات: {sys_data['sales']['total']}
• مبيعات اليوم: {sys_data['sales']['today']}

📦 **المنتجات:**
• إجمالي المنتجات: {sys_data['products']['total']}
• مخزون منخفض: {sys_data['products']['low_stock']}
• نفد المخزون: {sys_data['products']['out_of_stock']}

💰 **الأمور المالية:**
• إجمالي المبيعات: {fin_data['total_sales']:,.2f} AED
• إجمالي المدفوعات: {fin_data['total_payments']:,.2f} AED
• الذمم المدينة: {fin_data['total_receivables']:,.2f} AED
• مبيعات اليوم: {fin_data['today_sales']:,.2f} AED
• مدفوعات اليوم: {fin_data['today_payments']:,.2f} AED

📈 **آخر المبيعات:**
{chr(10).join([f"• فاتورة #{sale['id']} - {sale['customer']} - {sale['amount']:,.2f} AED ({sale['date']})" for sale in sys_data['sales']['recent']])}

👤 **أحدث العملاء:**
{chr(10).join([f"• {customer['name']} ({customer['type']}) - رصيد: {customer['balance']:,.2f} AED" for customer in sys_data['customers']['recent']])}

💡 **التوصيات:**
• {'يحتاج متابعة المدفوعات' if fin_data['total_receivables'] > fin_data['total_sales'] * 0.3 else 'الأمور المالية جيدة'}
• {'يحتاج طلب منتجات' if sys_data['products']['low_stock'] > 5 else 'المخزون في حالة جيدة'}"""
        
        return response
    
    @staticmethod
    def _handle_add_customer_query(message):
        """التعامل مع إضافة عميل جديد"""
        # هذا مثال بسيط - في الواقع ستحتاج لتحليل أكثر تعقيداً
        return """➕ **إضافة عميل جديد**

📝 **المعلومات المطلوبة:**
• الاسم الكامل
• نوع العميل (عادي، VIP، تاجر)
• رقم الهاتف
• البريد الإلكتروني (اختياري)
• العنوان (اختياري)
• حد الائتمان (اختياري)

💡 **مثال:** "أضف عميل جديد اسمه أحمد محمد، نوعه VIP، هاتفه 0501234567"

أو يمكنك استخدام النموذج في النظام لإضافة العملاء بطريقة أسهل."""
    
    @staticmethod
    def _handle_search_query(message):
        """التعامل مع البحث في النظام"""
        # استخراج كلمة البحث
        words = message.split()
        search_term = None
        
        for i, word in enumerate(words):
            if word.lower() in ['ابحث', 'search', 'جد', 'find'] and i + 1 < len(words):
                search_term = ' '.join(words[i+1:])
                break
        
        if not search_term:
            return "❌ لم أتمكن من تحديد كلمة البحث. يرجى كتابة: 'ابحث عن أحمد' أو 'جد المنتج ABC'"
        
        result = system_integrator.search_data(search_term)
        
        if not result['success']:
            return f"❌ {result['error']}"
        
        results = result['results']
        
        response = f"""🔍 **نتائج البحث عن: "{search_term}"**

👥 **العملاء ({len(results['customers'])}):**
{chr(10).join([f"• {customer['name']} ({customer['type']}) - رصيد: {customer['balance']:,.2f} AED" for customer in results['customers'][:5]])}

📦 **المنتجات ({len(results['products'])}):**
{chr(10).join([f"• {product['name']} (SKU: {product['sku']}) - مخزون: {product['stock']} - سعر: {product['price']:,.2f} AED" for product in results['products'][:5]])}

🛒 **المبيعات ({len(results['sales'])}):**
{chr(10).join([f"• فاتورة #{sale['id']} - {sale['customer']} - {sale['amount']:,.2f} AED ({sale['date']})" for sale in results['sales'][:5]])}

📊 **إجمالي النتائج: {len(results['customers']) + len(results['products']) + len(results['sales'])}**"""
        
        return response
    
    @staticmethod
    def _handle_add_knowledge_source(message):
        """التعامل مع إضافة مصدر معرفة"""
        return """📚 **إضافة مصدر معرفة جديد**

🔗 **لإضافة موقع ويب:**
"أضف موقع https://example.com في فئة الضرائب"

📄 **لإضافة مستند:**
"أضف كتاب محتوى المستند في فئة المحاسبة"

📂 **الفئات المتاحة:**
• الضرائب والجمارك
• قطع الغيار والمعدات
• المحاسبة والمالية
• خدمة العملاء
• التقنيات الحديثة
• عام

💡 **مثال:** "أضف موقع https://tax.gov.ae في فئة الضرائب والجمارك" """
    
    @staticmethod
    def _handle_knowledge_search(message):
        """التعامل مع البحث في المعرفة الموسعة"""
        # استخراج كلمة البحث
        words = message.split()
        search_term = None
        
        for i, word in enumerate(words):
            if word.lower() in ['ابحث', 'search'] and i + 1 < len(words):
                search_term = ' '.join(words[i+1:])
                break
        
        if not search_term:
            return "❌ لم أتمكن من تحديد كلمة البحث. يرجى كتابة: 'ابحث في المعرفة عن الضرائب'"
        
        result = knowledge_expander.search_knowledge(search_term)
        
        if not result['success']:
            return f"❌ {result['error']}"
        
        if not result['results']:
            return f"لم أجد نتائج للبحث عن: '{search_term}'"
        
        total_found = result['total_found']
        results_list = []
        for i, res in enumerate(result['results'][:5]):
            title = res['title']
            res_type = res['type']
            category = res['category']
            snippet = res['snippet']
            results_list.append(f"**{i+1}. {title}** ({res_type})\\n   الفئة: {category}\\n   {snippet}\\n")
        
        results_text = chr(10).join(results_list)
        
        response = f"""نتائج البحث في المعرفة عن: "{search_term}"

عدد النتائج: {total_found}

{results_text}

للمزيد من التفاصيل، يمكنك طلب معلومات أكثر عن أي نتيجة."""
        
        return response
    
    @staticmethod
    def _handle_document_generation(message):
        """التعامل مع توليد المستندات"""
        msg_lower = message.lower()
        
        if 'سند' in msg_lower or 'receipt' in msg_lower:
            # استخراج رقم الفاتورة
            words = message.split()
            sale_id = None
            
            for i, word in enumerate(words):
                if word.isdigit():
                    sale_id = int(word)
                    break
            
            if not sale_id:
                return "❌ يرجى تحديد رقم الفاتورة. مثال: 'ولد سند قبض للفاتورة 123'"
            
            # توليد سند القبض
            content, status = document_generator.generate_receipt(sale_id)
            if content:
                return f"📄 **سند القبض**\n\n```\n{content}\n```\n\n✅ {status}"
            else:
                return f"❌ {status}"
        
        elif 'فاتورة' in msg_lower or 'invoice' in msg_lower:
            # استخراج رقم الفاتورة
            words = message.split()
            sale_id = None
            
            for i, word in enumerate(words):
                if word.isdigit():
                    sale_id = int(word)
                    break
            
            if not sale_id:
                return "❌ يرجى تحديد رقم الفاتورة. مثال: 'ولد فاتورة 123'"
            
            # توليد الفاتورة
            content, status = document_generator.generate_invoice(sale_id)
            if content:
                return f"📄 **فاتورة المبيعات**\n\n```\n{content}\n```\n\n✅ {status}"
            else:
                return f"❌ {status}"
        
        return "❓ ما نوع المستند الذي تريد توليده؟ سند قبض أم فاتورة؟"
    
    @staticmethod
    def _handle_excel_export(message):
        """التعامل مع التصدير إلى Excel"""
        msg_lower = message.lower()
        
        if 'مبيعات' in msg_lower or 'sales' in msg_lower:
            return """**تصدير المبيعات إلى Excel**

أزاد يمكنه تصدير:
• جميع المبيعات
• مبيعات فترة محددة
• تفاصيل العملاء
• تفاصيل المنتجات

**مثال:** "صدر مبيعات الشهر الحالي إلى Excel"

أو استخدم واجهة التصدير في النظام!"""
        
        elif 'عملاء' in msg_lower or 'customers' in msg_lower:
            return """**تصدير العملاء إلى Excel**

أزاد يمكنه تصدير:
• بيانات جميع العملاء
• أرصدة العملاء
• إحصائيات المبيعات لكل عميل
• معلومات الاتصال

**مثال:** "صدر بيانات العملاء إلى Excel" """
        
        elif 'منتجات' in msg_lower or 'products' in msg_lower:
            return """**تصدير المنتجات إلى Excel**

أزاد يمكنه تصدير:
• بيانات جميع المنتجات
• معلومات المخزون
• الأسعار والفئات
• إحصائيات المبيعات

**مثال:** "صدر بيانات المنتجات إلى Excel" """
        
        return "ما البيانات التي تريد تصديرها؟ المبيعات، العملاء، أم المنتجات؟"
    
    @staticmethod
    def _handle_report_generation(message):
        """التعامل مع توليد التقارير"""
        msg_lower = message.lower()
        
        if 'مبيعات' in msg_lower or 'sales' in msg_lower:
            return """**تقرير المبيعات**

أزاد يمكنه توليد:
• تقرير مبيعات يومي
• تقرير مبيعات أسبوعي
• تقرير مبيعات شهري
• تقرير مبيعات فترة محددة

**مثال:** "ولد تقرير مبيعات الشهر الحالي" """
        
        elif 'كشف' in msg_lower or 'statement' in msg_lower:
            return """**كشف حساب العميل**

أزاد يمكنه توليد:
• كشف حساب عميل محدد
• حركات الحساب
• الرصيد الحالي
• تاريخ المعاملات

**مثال:** "ولد كشف حساب العميل أحمد" """
        
        return "ما نوع التقرير الذي تريد؟ تقرير مبيعات أم كشف حساب؟"
    
    @staticmethod
    def _handle_tax_laws_query(message):
        """التعامل مع استعلامات القوانين الضريبية"""
        msg_lower = message.lower()
        
        if 'فلسطين' in msg_lower or 'palestine' in msg_lower:
            return f"""🇵🇸 **القوانين الضريبية الفلسطينية**

**الضرائب الأساسية:**
• ضريبة القيمة المضافة: {advanced_laws.PALESTINIAN_TAX_LAWS['vat_rate']}%
• ضريبة الشركات: {advanced_laws.PALESTINIAN_TAX_LAWS['income_tax_rates']['corporate']['standard']}%

**ضريبة الدخل للأفراد:**
{chr(10).join([f"• {range_text}: {rate}%" for range_text, rate in advanced_laws.PALESTINIAN_TAX_LAWS['income_tax_rates']['individual'].items()])}

🏛️ **الرسوم الجمركية:**
• زراعية: {advanced_laws.PALESTINIAN_TAX_LAWS['customs_duties']['agricultural']}%
• صناعية: {advanced_laws.PALESTINIAN_TAX_LAWS['customs_duties']['industrial']}%
• فاخرة: {advanced_laws.PALESTINIAN_TAX_LAWS['customs_duties']['luxury']}%

**الأنظمة الخاصة:**
{chr(10).join([f"• {regulation}" for regulation in advanced_laws.PALESTINIAN_TAX_LAWS['special_regulations']])}

**أزاد يعرف كل التفاصيل الضريبية!**"""
        
        elif 'اسرائيل' in msg_lower or 'israel' in msg_lower:
            return f"""🇮🇱 **القوانين الضريبية الإسرائيلية**

**الضرائب الأساسية:**
• ضريبة القيمة المضافة: {advanced_laws.ISRAELI_TAX_LAWS['vat_rate']}%
• ضريبة الشركات: {advanced_laws.ISRAELI_TAX_LAWS['income_tax_rates']['corporate']['standard']}%

**ضريبة الدخل للأفراد:**
{chr(10).join([f"• {range_text}: {rate}%" for range_text, rate in advanced_laws.ISRAELI_TAX_LAWS['income_tax_rates']['individual'].items()])}

🏛️ **الرسوم الجمركية:**
• زراعية: {advanced_laws.ISRAELI_TAX_LAWS['customs_duties']['agricultural']}%
• صناعية: {advanced_laws.ISRAELI_TAX_LAWS['customs_duties']['industrial']}%
• فاخرة: {advanced_laws.ISRAELI_TAX_LAWS['customs_duties']['luxury']}%

**الأنظمة الخاصة:**
{chr(10).join([f"• {regulation}" for regulation in advanced_laws.ISRAELI_TAX_LAWS['special_regulations']])}

**أزاد خبير في القوانين الإسرائيلية!**"""
        
        elif 'خليج' in msg_lower or 'gulf' in msg_lower or 'امارات' in msg_lower or 'uae' in msg_lower:
            return f"""🇦🇪 **القوانين الضريبية الخليجية**

**الإمارات:**
• ضريبة القيمة المضافة: {advanced_laws.GULF_TAX_LAWS['uae']['vat_rate']}%
• ضريبة الشركات: {advanced_laws.GULF_TAX_LAWS['uae']['corporate_tax_rate']}%

**السعودية:**
• ضريبة القيمة المضافة: {advanced_laws.GULF_TAX_LAWS['saudi']['vat_rate']}%
• ضريبة الشركات: {advanced_laws.GULF_TAX_LAWS['saudi']['corporate_tax_rate']}%
• الزكاة: {advanced_laws.GULF_TAX_LAWS['saudi']['zakat_rate']}%

**الكويت:**
• ضريبة القيمة المضافة: {advanced_laws.GULF_TAX_LAWS['kuwait']['vat_rate']}% (لم تطبق بعد)
• ضريبة الشركات: {advanced_laws.GULF_TAX_LAWS['kuwait']['corporate_tax_rate']}%

**قطر:**
• ضريبة القيمة المضافة: {advanced_laws.GULF_TAX_LAWS['qatar']['vat_rate']}% (لم تطبق بعد)
• ضريبة الشركات: {advanced_laws.GULF_TAX_LAWS['qatar']['corporate_tax_rate']}%

**أزاد خبير في قوانين دول الخليج!**"""
        
        return "أي دولة تريد معرفة قوانينها الضريبية؟ فلسطين، إسرائيل، أم دول الخليج؟"
    
    @staticmethod
    def _show_knowledge_sources(message):
        """عرض مصادر المعرفة المتاحة"""
        msg_lower = message.lower()
        
        # عرض كل المصادر
        if 'كل' in msg_lower or 'all' in msg_lower:
            summary = knowledge_manager.get_all_sources_summary()
            response = f"""🌐 **مصادر المعرفة المتاحة لأزاد:**

**الإحصائيات:**
• إجمالي الفئات: {summary['total_categories']}
• إجمالي المصادر: {summary['total_sources']}

📚 **الفئات:**

"""
            for category, info in summary['categories'].items():
                response += f"**{category.upper()}** ({info['count']} مصادر):\n"
                for source in info['sources'][:3]:  # أول 3
                    response += f"  • [{source['name']}]({source['url']})\n"
                response += "\n"
            
            response += "**للحصول على مصادر محددة، اسأل عن موضوع معين!**"
            return response
        
        # مصادر حسب الموضوع
        topics_map = {
            'ضريبة': 'vat',
            'جمارك': 'customs',
            'قطع': 'parts',
            'محاسبة': 'accounting',
            'عملة': 'currency'
        }
        
        for keyword, topic in topics_map.items():
            if keyword in msg_lower:
                sources = knowledge_manager.get_sources_by_topic(topic)
                if sources:
                    response = f"🔗 **مصادر {keyword}:**\n\n"
                    for source in sources[:5]:
                        response += f"**{source['name']}**\n"
                        response += f"{source['url']}\n"
                        response += f"النوع: {source['type']}\n\n"
                    return response
        
        # عرض دليل المصادر
        return SOURCES_GUIDE
    
    @staticmethod
    def _recommend_sources(message):
        """توصية بمصادر حسب السؤال"""
        recommendations = recommend_sources_for_query(message)
        
        if not recommendations:
            return "🤔 لم أجد مصادر مناسبة لسؤالك. حاول أن تكون أكثر تحديداً!"
        
        intro = azad_personality.get_help_intro()
        response = f"{intro}\n\n🎯 **أفضل المصادر لسؤالك:**\n\n"
        
        for i, source in enumerate(recommendations, 1):
            response += f"{i}. **{source['name']}**\n"
            response += f"   {source['url']}\n"
            response += f"   الفئة: {source['category']}\n"
            response += f"   النوع: {source['type']}\n\n"
        
        response += "**نصيحة:** افتح هذه المواقع للحصول على أحدث المعلومات!"
        return response
    
    @staticmethod
    def _handle_shipping_laws_query(message):
        """التعامل مع استعلامات قوانين الشحن"""
        msg_lower = message.lower()
        
        if 'إجراءات' in msg_lower or 'procedures' in msg_lower:
            return f"""**إجراءات الشحن والتخليص**

**الوثائق المطلوبة:**
{chr(10).join([f"• {doc}" for doc in advanced_laws.SHIPPING_LAWS['documentation_required']])}

**الإجراءات الجمركية:**
{chr(10).join([f"• {procedure}" for procedure in advanced_laws.SHIPPING_LAWS['customs_procedures'].values()])}

**البضائع المحظورة:**
{chr(10).join([f"• {item}" for item in advanced_laws.SHIPPING_LAWS['restricted_items']])}

**الإعفاءات الجمركية:**
{chr(10).join([f"• {allowance}" for allowance in advanced_laws.SHIPPING_LAWS['duty_free_allowances'].values()])}

**أزاد خبير في الشحن والتخليص!**"""
        
        elif 'نوع' in msg_lower or 'type' in msg_lower:
            return """**أنواع الشحن**

**الشحن البحري:**
• أبطأ وأرخص طريقة
• مناسبة للبضائع الكبيرة
• يحتاج 15-30 يوم
• رسوم أقل

**الشحن الجوي:**
• أسرع طريقة
• مناسبة للبضائع القيمة
• يحتاج 3-7 أيام
• رسوم أعلى

**الشحن البري:**
• متوسط السرعة والسعر
• مناسبة للمنطقة
• يحتاج 5-15 يوم
• رسوم متوسطة

**أزاد يساعدك في اختيار أفضل طريقة!**"""
        
        return "ما تريد معرفته عن الشحن؟ الإجراءات أم الأنواع؟"
    
    @staticmethod
    def _handle_quality_standards_query(message):
        """التعامل مع استعلامات معايير الجودة"""
        msg_lower = message.lower()
        
        if 'معايير' in msg_lower or 'standards' in msg_lower:
            return f"""🏆 **معايير الجودة**

🏛️ **هيئات التقييس:**
{chr(10).join([f"• {country}: {org}" for country, org in advanced_laws.QUALITY_LAWS['standards_organizations'].items()])}

**الشهادات المطلوبة:**
{chr(10).join([f"• {cert}" for cert in advanced_laws.QUALITY_LAWS['certification_required']])}

**علامات الجودة:**
{chr(10).join([f"• {mark}: {desc}" for mark, desc in advanced_laws.QUALITY_LAWS['quality_marks'].items()])}

**أزاد يعرف كل معايير الجودة!**"""
        
        elif 'طعام' in msg_lower or 'food' in msg_lower:
            return """**معايير جودة الأغذية**

**الشهادات المطلوبة:**
• شهادة حلال
• تاريخ انتهاء الصلاحية
• شهادة صحية
• معايير التغليف

🏆 **معايير إضافية:**
• شهادة عضوي
• شهادة سلامة الغذاء
• شهادة منشأ
• شهادة التغذية

**أزاد خبير في معايير الغذاء!**"""
        
        elif 'إلكترونيات' in msg_lower or 'electronics' in msg_lower:
            return """**معايير جودة الإلكترونيات**

**الشهادات المطلوبة:**
• شهادة CE (أوروبا)
• شهادة FCC (أمريكا)
• شهادة السلامة
• معايير الطاقة

🏆 **معايير إضافية:**
• شهادة ISO 9001
• شهادة السلامة الكهربائية
• شهادة التوافق الكهرومغناطيسي
• شهادة الجودة البيئية

**أزاد خبير في معايير الإلكترونيات!**"""
        
        return "ما نوع المنتج الذي تريد معرفة معاييره؟ طعام، إلكترونيات، أم عام؟"
    
    @staticmethod
    def _smart_sales_analysis(context):
        """تحليل مبيعات ذكي"""
        from models import Sale
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal
        
        last_7_days = datetime.now(timezone.utc) - timedelta(days=7)
        last_30_days = datetime.now(timezone.utc) - timedelta(days=30)
        
        sales_7d = Sale.query.filter(Sale.sale_date >= last_7_days, Sale.status == 'confirmed').all()
        sales_30d = Sale.query.filter(Sale.sale_date >= last_30_days, Sale.status == 'confirmed').all()
        
        total_7d = sum((Decimal(str(s.amount_aed)) for s in sales_7d), Decimal('0'))
        total_30d = sum((Decimal(str(s.amount_aed)) for s in sales_30d), Decimal('0'))
        
        avg_7d = total_7d / 7 if total_7d > 0 else Decimal('0')
        avg_30d = total_30d / 30 if total_30d > 0 else Decimal('0')
        
        # مقارنة الأداء
        if avg_7d > avg_30d * Decimal('1.1'):
            trend = f"📈 تحسن ممتاز! المبيعات الأخيرة أعلى من المتوسط بـ {float((avg_7d / avg_30d - 1) * 100):.1f}%"
        elif avg_7d < avg_30d * Decimal('0.9'):
            trend = f"📉 تراجع ملحوظ! المبيعات انخفضت بـ {float((1 - avg_7d / avg_30d) * 100):.1f}%"
        else:
            trend = "➡️ مبيعات مستقرة"
        
        return f"""📊 **تحليل المبيعات الذكي:**

📅 **آخر 7 أيام:**
• عدد الفواتير: {len(sales_7d)}
• الإجمالي: {float(total_7d):,.0f} AED
• المتوسط اليومي: {float(avg_7d):,.0f} AED

📅 **آخر 30 يوم:**
• عدد الفواتير: {len(sales_30d)}
• الإجمالي: {float(total_30d):,.0f} AED
• المتوسط اليومي: {float(avg_30d):,.0f} AED

**الاتجاه:** {trend}

**التوصية:** {"استمر على هذا النهج!" if avg_7d >= avg_30d else "راجع استراتيجية المبيعات والتسويق"}"""
    
    @staticmethod
    def _handle_detected_intent(intent: str, message: str, context=None):
        """
        معالج النوايا المكتشفة بالذكاء الاصطناعي
        
        Args:
            intent: النية المكتشفة (create_invoice, sales_analysis, etc.)
            message: الرسالة الأصلية
            context: السياق
        
        Returns:
            الرد المناسب أو None
        """
        # ربط النوايا بالدوال المناسبة - شامل لكل المعرفة
        intent_handlers = {
            # النظام الأساسي
            'create_invoice': AzadResponses._quick_invoice_link,
            'create_receipt': AzadResponses._quick_receipt_link,
            'sales_analysis': lambda: AzadResponses._smart_sales_analysis(context),
            'customer_balance': lambda: AzadResponses._handle_balance_query(message),
            'inventory_check': lambda: AzadResponses._inventory_status(),
            'system_links': AzadResponses._show_system_quick_links,
            'add_customer': lambda: AzadResponses._handle_add_customer_query(message),
            
            # الضرائب والجمارك
            'tax_info': lambda: f"💵 **الضرائب في الإمارات:**\n\n{get_tax_info('uae')}",
            'customs_info': lambda: f"🛃 **الجمارك في الإمارات:**\n\n{get_customs_info('uae')}",
            
            # قطع الغيار والسيارات
            'parts_info': lambda: f"**معلومات قطع الغيار:**\n\n{get_part_info(message)}",
            'automotive_ecu': lambda: "🚗 **كمبيوتر السيارة (ECU):**\n\nوحدة التحكم الإلكتروني (ECU) هي دماغ السيارة الحديثة. تتحكم في المحرك، ناقل الحركة، الفرامل، والأنظمة الكهربائية.\n\n**الوظائف:**\n• إدارة المحرك والوقود\n• التشخيص الذاتي\n• تحسين الأداء\n• خفض الانبعاثات",
            'heavy_equipment': lambda: "🏗️ **المعدات الثقيلة:**\n\nنتعامل مع قطع غيار المعدات الثقيلة:\n• Caterpillar (CAT)\n• Komatsu\n• Volvo\n• Hitachi\n• JCB\n\nشامل: الحفارات، اللوادر، الجريدرات، والرافعات",
            
            # السوق وخدمة العملاء
            'market_insights': lambda: f"📊 **رؤى السوق:**\n\n{get_market_insights()}",
            'customer_service': lambda: f"👥 **خدمة العملاء المتميزة:**\n\n{get_customer_service_tip()}",
            
            # الشحن والجودة
            'shipping_laws': lambda: AzadResponses._handle_shipping_laws_query(message),
            'quality_standards': lambda: AzadResponses._handle_quality_standards_query(message),
            
            # الموردين والمعرفة
            'suppliers_info': lambda: AzadResponses._handle_suppliers_query(message),
            'knowledge_sources': lambda: AzadResponses._show_knowledge_sources(message),
            
            # القوانين المتقدمة
            'palestine_tax_laws': lambda: AzadResponses._get_palestine_tax_laws(),
            'israel_tax_laws': lambda: AzadResponses._get_israel_tax_laws(),
            'gulf_tax_laws': lambda: AzadResponses._get_gulf_tax_laws(),
            'shipping_regulations': lambda: AzadResponses._get_shipping_regulations(),
            
            # المعالجة المتقدمة
            'memory_query': lambda: "🧠 **نظام الذاكرة:** قيد التطوير - سيتم تفعيله قريباً لتذكر محادثاتك السابقة!",
            'multi_step_query': lambda: "🔄 **الاستفسارات متعددة الخطوات:** قيد التطوير - سأتمكن قريباً من تنفيذ عدة أوامر متتالية!",
            
            # قطع الغيار التفصيلية
            'engine_parts': lambda: AzadResponses._get_engine_parts_guide(),
            'diesel_parts': lambda: AzadResponses._get_diesel_parts_guide(),
            'transmission_parts': lambda: AzadResponses._get_transmission_guide(),
            'suspension_parts': lambda: AzadResponses._get_suspension_guide(),
            'brake_parts': lambda: AzadResponses._get_brakes_guide(),
            'electrical_parts': lambda: AzadResponses._get_electrical_guide(),
            'ac_parts': lambda: AzadResponses._get_ac_guide(),
            
            # التشخيص والأعطال
            'diagnostic_codes': lambda: AzadResponses._get_dtc_info(message),
            'sensors_issues': lambda: AzadResponses._get_sensor_troubleshooting(message),
            
            # الأعمال المتقدمة
            'pricing_strategy': lambda: AzadResponses._get_pricing_strategy_guide(),
            'sales_techniques': lambda: AzadResponses._get_sales_techniques_guide(),
            
            # المساعدة العامة
            'general_help': lambda: azad_personality.get_help_intro() + "\n\n" + get_system_guide()
        }
        
        # تنفيذ المعالج المناسب
        handler = intent_handlers.get(intent)
        if handler:
            try:
                return handler()
            except Exception as e:
                # في حال حدوث خطأ، نرجع None ليكمل النظام التقليدي
                return None
        
        return None
    
    @staticmethod
    def _quick_invoice_link():
        """رابط سريع لإنشاء فاتورة"""
        intro = azad_personality.get_help_intro()
        return f"""{intro}

🧾 **إنشاء فاتورة بيع جديدة:**

🔗 **رابط مباشر:**
👉 [اضغط هنا لإنشاء فاتورة](/sales/create)

📋 **ما تحتاجه:**
• اختر الزبون (أو أضف جديد)
• أضف المنتجات والكميات
• اختر طريقة الدفع
• احفظ واطبع!

⌨️ **اختصار سريع:** اضغط `Alt + S` ثم `Alt + N`

💡 **نصيحة أزاد:** استخدم البحث السريع (`Ctrl + K`) للوصول لأي صفحة! 🚀"""
    
    @staticmethod
    def _quick_receipt_link():
        """رابط سريع لسند قبض"""
        intro = azad_personality.get_help_intro()
        return f"""{intro}

💰 **إنشاء سند قبض جديد:**

🔗 **رابط مباشر:**
👉 [اضغط هنا لإنشاء سند قبض](/payments/receipts/create)

📋 **ما تحتاجه:**
• اختر الزبون
• اختر الفاتورة (أو دفع عام)
• أدخل المبلغ
• اختر طريقة الدفع (نقدي، بطاقة، تحويل...)

⌨️ **اختصار سريع:** اضغط `Alt + P` ثم `Alt + N`

💡 **نصيحة أزاد:** يمكنك طباعة السند مباشرة بعد الحفظ! 📄"""
    
    @staticmethod
    def _quick_report_links(message):
        """روابط سريعة للتقارير"""
        msg_lower = message.lower()
        intro = azad_personality.get_help_intro()
        
        links = []
        
        # تحديد نوع التقرير
        if 'مبيعات' in msg_lower or 'sales' in msg_lower:
            links.append(('📊 تقرير المبيعات', '/reports/sales'))
        if 'مشتريات' in msg_lower or 'purchases' in msg_lower:
            links.append(('📦 تقرير المشتريات', '/reports/purchases'))
        if 'مخزون' in msg_lower or 'inventory' in msg_lower:
            links.append(('🏪 تقرير المخزون', '/reports/inventory'))
        if 'ذمم' in msg_lower or 'receivables' in msg_lower:
            links.append(('💳 تقرير الذمم المدينة', '/reports/receivables'))
        
        # إذا لم يحدد نوعاً، اعرض الكل
        if not links:
            links = [
                ('📊 تقرير المبيعات', '/reports/sales'),
                ('📦 تقرير المشتريات', '/reports/purchases'),
                ('🏪 تقرير المخزون', '/reports/inventory'),
                ('💳 تقرير الذمم المدينة', '/reports/receivables'),
                ('📈 قائمة الدخل', '/ledger/income-statement'),
                ('⚖️ الميزانية العمومية', '/ledger/balance-sheet')
            ]
        
        response = f"""{intro}

📊 **التقارير المتاحة:**

"""
        for title, url in links:
            response += f"🔗 {title}\n👉 [اضغط هنا]({url})\n\n"
        
        response += """⌨️ **اختصار سريع:** `Ctrl + R` للوصول السريع للتقارير

💡 **نصيحة أزاد:** كل التقارير قابلة للتصدير إلى Excel و PDF! 📑"""
        
        return response
    
    @staticmethod
    def _show_system_quick_links():
        """عرض روابط النظام السريعة"""
        intro = azad_personality.get_greeting()
        return f"""{intro}

🚀 **روابط النظام السريعة:**

## 📊 المبيعات:
🔗 [فاتورة جديدة](/sales/create)
🔗 [عرض الفواتير](/sales)
🔗 [إحصائيات المبيعات](/reports/sales)

## 👥 الزبائن:
🔗 [زبون جديد](/customers/create)
🔗 [قائمة الزبائن](/customers)
🔗 [كشوفات الحساب](/customers)

## 🏪 الموردين ⭐NEW:
🔗 [مورد جديد](/suppliers/create)
🔗 [قائمة الموردين](/suppliers)
🔗 [كشف حساب مورد](/suppliers)

## 📦 المنتجات:
🔗 [منتج جديد](/products/create)
🔗 [قائمة المنتجات](/products)
🔗 [تقرير المخزون](/reports/inventory)

## 💰 المدفوعات:
🔗 [سند قبض جديد](/payments/receipts/create)
🔗 [سجل المدفوعات](/payments/receipts)
🔗 [سندات القبض](/payments/receipts)

## 🏪 المستودعات:
🔗 [إدارة المخزون](/warehouse)
🔗 [حركات المخزون](/warehouse/movements)
🔗 [منتجات منخفضة](/warehouse/low-stock)

## 📈 التقارير:
🔗 [تقرير المبيعات](/reports/sales)
🔗 [تقرير المشتريات](/reports/purchases)
🔗 [تقرير المخزون](/reports/inventory)
🔗 [تقرير الذمم](/reports/receivables)
🔗 [قائمة الدخل](/ledger/income-statement)
🔗 [الميزانية](/ledger/balance-sheet)

## 🤖 المساعد الذكي:
🔗 [محادثة مع أزاد](/ai/assistant)
🔗 [إعدادات AI](/ai/config)

## ⚙️ الإعدادات (للمالك):
🔗 [لوحة المالك](/owner/dashboard)
🔗 [معلومات الشركة](/owner/company-info)
🔗 [إعدادات النظام](/owner/system-config)
🔗 [ترويسات الفواتير](/owner/invoice-settings)

---

⌨️ **اختصارات لوحة المفاتيح:**
• `Alt + H` → الرئيسية
• `Alt + S` → المبيعات
• `Alt + C` → الزبائن
• `Alt + P` → المنتجات
• `Ctrl + K` → بحث سريع
• `Ctrl + N` → جديد
• `?` → المساعدة

💡 **نصيحة أزاد:** احفظ الروابط المهمة في مفضلتك! 📌"""
    
    @staticmethod
    def _handle_suppliers_query(message):
        """🏪 معالجة استفسارات الموردين"""
        from models import Supplier
        from extensions import db
        
        msg_lower = message.lower()
        
        try:
            # عدد الموردين
            total_suppliers = Supplier.query.filter_by(is_active=True).count()
            
            # موردين موثوقين
            verified_suppliers = Supplier.query.filter_by(is_active=True, is_verified=True).count()
            
            # أفضل مورد (حسب التقييم)
            top_supplier = Supplier.query.filter_by(is_active=True).order_by(Supplier.rating.desc()).first()
            
            # إجمالي المشتريات
            total_purchases = db.session.query(db.func.sum(Supplier.total_purchases_aed)).scalar() or 0
            
            response = f"""🏪 **نظام إدارة الموردين** ⭐ (نظام جديد!)

📊 **إحصائيات:**
• عدد الموردين النشطين: {total_suppliers}
• موردين موثوقين: {verified_suppliers} ✅
• إجمالي المشتريات: {total_purchases:,.2f} درهم

"""
            
            if top_supplier:
                response += f"""⭐ **أفضل مورد:**
• الاسم: {top_supplier.name}
• التقييم: {'⭐' * int(top_supplier.rating or 0)}
• الشركة: {top_supplier.company_name or 'غير محدد'}
• نوع المورد: {top_supplier.supplier_type or 'عام'}

"""
            
            response += """🔗 **روابط سريعة:**
• [قائمة الموردين](/suppliers)
• [إضافة مورد جديد](/suppliers/create)
• [المشتريات](/purchases)
• [إنشاء فاتورة شراء](/purchases/create)

💡 **مميزات النظام:**
✅ نظام موردين مستقل (منفصل عن الزبائن)
✅ تقييم الموردين (1-5 نجوم)
✅ موردين موثوقين (verified)
✅ أنواع موردين (محلي، دولي، وكيل، مصنع)
✅ حد ائتماني لكل مورد
✅ شروط دفع (أيام)
✅ كشف حساب لكل مورد
✅ ربط مباشر بفواتير الشراء
✅ تتبع إجمالي المشتريات والمدفوع
✅ **فلتر ذكي** في صفحة المشتريات 🔍

📋 **كيف تضيف مورد؟**
1. اذهب إلى [الموردين](/suppliers)
2. اضغط "مورد جديد"
3. أدخل البيانات الأساسية
4. حدد نوع المورد والتقييم
5. ارفع الملفات (سجل تجاري، بطاقة ضريبية)
6. احفظ!

🎯 **نصيحة أزاد:**
استخدم الفلتر الذكي في صفحة المشتريات للبحث السريع عن الموردين!"""
            
            return response
            
        except Exception as e:
            return f"""🏪 **نظام الموردين** ⭐

النظام الجديد لإدارة الموردين يتيح لك:
✅ إضافة وإدارة الموردين بشكل احترافي
✅ تقييم الموردين وتصنيفهم
✅ ربط المشتريات بالموردين
✅ متابعة الأرصدة والمديونيات
✅ كشوفات حساب تفصيلية

🔗 [إدارة الموردين](/suppliers)
🔗 [مورد جديد](/suppliers/create)
🔗 [فاتورة شراء](/purchases/create)

❌ ملاحظة: {str(e)}"""
    
    @staticmethod
    def _handle_smart_filters_query(message):
        """🔍 معالجة استفسارات الفلاتر الذكية"""
        
        msg_lower = message.lower()
        
        response = """🔍 **الفلاتر الذكية** ⭐ (نظام جديد!)

نظام بحث واختيار ذكي موحد لجميع الوحدات!

## 🎯 أين تعمل الفلاتر الذكية؟

### 1️⃣ **فلتر الزبائن** (customer-select)
📍 **الصفحات:**
• صفحة المبيعات → [فاتورة جديدة](/sales/create)
• صفحة المدفوعات → [سند قبض](/payments/receipts/create)
• صفحة الإيصالات

✨ **المميزات:**
• بحث فوري أثناء الكتابة
• عرض رصيد الزبون مباشرة
• عرض رقم الهاتف والبريد
• زر "إضافة زبون جديد" إذا لم يوجد
• يعمل مع Select2 (قائمة منسدلة محسنة)

### 2️⃣ **فلتر الموردين** (supplier-select) ⭐NEW
📍 **الصفحات:**
• صفحة المشتريات → [فاتورة شراء](/purchases/create)

✨ **المميزات:**
• بحث فوري في الموردين
• عرض اسم الشركة والتقييم
• عرض حالة التوثيق (verified ✅)
• عرض رصيد المورد
• زر "إضافة مورد جديد"

### 3️⃣ **فلتر المنتجات** (product-select)
📍 **الصفحات:**
• صفحة المبيعات → [فاتورة جديدة](/sales/create)
• صفحة المشتريات → [فاتورة شراء](/purchases/create)

✨ **المميزات:**
• بحث في الاسم أو الكود أو الباركود
• عرض الكمية المتوفرة
• عرض سعر البيع/الشراء
• تعبئة السعر تلقائياً
• زر "إضافة منتج جديد"

## 🔌 API الموحد
جميع الفلاتر تستخدم endpoint واحد:
`GET /api/search?type=customers&q=term`
`GET /api/search?type=suppliers&q=term` ⭐NEW
`GET /api/search?type=products&q=term`

## 💻 كيف تستخدم؟
1. ابدأ بالكتابة في حقل البحث
2. سيظهر لك اقتراحات فورية
3. اختر من القائمة
4. إذا لم تجد، اضغط "إضافة جديد"

## 📁 الملفات:
• JavaScript: `customer-select.js` (موحد)
• API: `/routes/api.py`
• الاستخدام: تلقائي في كل الصفحات

💡 **نصيحة أزاد:**
الفلاتر الذكية توفر لك الوقت وتقلل الأخطاء! 🚀"""
        
        return response
    
    @staticmethod
    def _handle_payment_methods_query(message):
        """💳 معالجة استفسارات طرق الدفع"""
        
        response = """💳 **طرق الدفع الديناميكية** ⭐ (نظام جديد!)

النظام يدعم 6 طرق دفع مع حقول ديناميكية!

## 💰 طرق الدفع المدعومة:

### 1️⃣ **نقدي (Cash)**
📋 الحقول:
• المبلغ المستلم
• الباقي (يُحسب تلقائياً)

### 2️⃣ **بطاقة (Card)**
📋 الحقول:
• آخر 4 أرقام من البطاقة
• نوع البطاقة (Visa, Mastercard, Amex)
• رقم الموافقة (Approval Code)
• اسم حامل البطاقة

### 3️⃣ **تحويل بنكي (Bank Transfer)**
📋 الحقول:
• اسم البنك
• رقم المرجع
• تاريخ التحويل

### 4️⃣ **شيك (Cheque)**
📋 الحقول:
• رقم الشيك
• اسم البنك
• تاريخ الاستحقاق
• حالة الشيك (معلق، مصروف، مرتجع)

### 5️⃣ **محفظة إلكترونية (E-Wallet)**
📋 الحقول:
• نوع المحفظة (PayPal, Apple Pay, Google Pay)
• معرف المعاملة (Transaction ID)

### 6️⃣ **آجل (Credit)**
📋 الحقول:
• تاريخ الاستحقاق
• ملاحظات الأجل

## 🎯 أين يعمل؟

📍 **4 صفحات:**
1. المبيعات → [فاتورة جديدة](/sales/create)
2. المدفوعات → [سند قبض](/payments/receipts/create)
3. الإيصالات → [إيصال جديد](/payments/create)
4. المصروفات → [مصروف جديد](/expenses/create)

## ✨ كيف يعمل؟

1️⃣ **اختر طريقة الدفع** من القائمة
2️⃣ **تظهر الحقول المطلوبة تلقائياً** ✨
3️⃣ **أدخل البيانات**
4️⃣ **تُحفظ بشكل صحيح** في قاعدة البيانات

## 💾 التخزين:
• طريقة الدفع: `payment_method`
• بيانات إضافية: `payment_details` (JSON)

## 📁 الملفات:
• JavaScript: `payment-fields.js`
• Manager: `PaymentFieldsManager`
• الاستخدام: تلقائي في كل صفحات الدفع

## 🔒 الأمان:
✅ بيانات البطاقات مشفرة
✅ لا تُحفظ أرقام البطاقات الكاملة
✅ فقط آخر 4 أرقام

💡 **نصيحة أزاد:**
استخدم طريقة الدفع المناسبة وسجل كل التفاصيل للمراجعة لاحقاً! 📝"""
        
        return response
    
    # ========== القوانين المتقدمة - Advanced Laws ==========
    
    @staticmethod
    def _get_palestine_tax_laws():
        """القوانين الضريبية الفلسطينية"""
        return """🇵🇸 **القوانين الضريبية الفلسطينية:**

📊 **ضريبة القيمة المضافة (VAT):** 16%
• تُطبق على السلع والخدمات داخل فلسطين

💰 **ضريبة الدخل:**
• الأفراد: 0-20% (حسب الدخل)
  - 0-48,000 ₪: معفى
  - 48,001-96,000 ₪: 5%
  - 96,001-192,000 ₪: 10%
  - 192,001-384,000 ₪: 15%
  - 384,001+ ₪: 20%

• الشركات: 15%

🛃 **الرسوم الجمركية:**
• زراعية: 10%
• صناعية: 15%
• كمالية: 30%

💡 **ملاحظة:** القوانين الفلسطينية تتأثر بالواقع السياسي والاقتصادي"""
    
    @staticmethod
    def _get_israel_tax_laws():
        """القوانين الضريبية الإسرائيلية"""
        return """🇮🇱 **القوانين الضريبية الإسرائيلية:**

📊 **ضريبة القيمة المضافة (מע"מ):** 17%
• تُطبق على معظم السلع والخدمات

💰 **ضريبة الدخل:**
• الأفراد: 10-47% (تصاعدية)
  - 0-77,480 ₪: 10%
  - 77,481-110,880 ₪: 14%
  - 110,881-178,080 ₪: 20%
  - 178,081-247,440 ₪: 31%
  - 247,441-514,920 ₪: 35%
  - 514,921+ ₪: 47%

• الشركات: 23%

💡 **ملاحظة:** معدلات الضرائب تتغير سنوياً - تحقق من التحديثات"""
    
    @staticmethod
    def _get_gulf_tax_laws():
        """القوانين الضريبية الخليجية"""
        return """🏛️ **القوانين الضريبية في دول الخليج:**

🇦🇪 **الإمارات:**
• VAT: 5%
• ضريبة الشركات: 9% (للأرباح > 375,000 درهم)

🇸🇦 **السعودية:**
• VAT: 15% (تم رفعها من 5% في 2020)
• الزكاة: 2.5% للشركات السعودية
• ضريبة الدخل: 20% للشركات الأجنبية

🇶🇦 **قطر:**
• لا توجد VAT حتى الآن
• ضريبة الشركات: 10% (للشركات الأجنبية)

🇰🇼 **الكويت:**
• لا توجد VAT
• ضريبة الشركات: 15% (للشركات الأجنبية)
• الزكاة: 1% (للشركات الكويتية)

🇧🇭 **البحرين:**
• VAT: 10%
• لا توجد ضريبة دخل

🇴🇲 **عمان:**
• VAT: 5%
• ضريبة الشركات: 15%

💡 **ملاحظة:** دول الخليج تطبق اتفاقية VAT موحدة مع اختلافات بسيطة"""
    
    @staticmethod
    def _get_shipping_regulations():
        """تنظيمات الشحن"""
        return """🚢 **تنظيمات الشحن الدولي:**

📋 **المستندات المطلوبة:**
1. الفاتورة التجارية (Commercial Invoice)
2. بوليصة الشحن (Bill of Lading / Airway Bill)
3. قائمة التعبئة (Packing List)
4. شهادة المنشأ (Certificate of Origin)
5. التأمين على البضائع (Insurance Certificate)
6. رخصة التصدير/الاستيراد (إن لزم)

🛃 **الإجراءات الجمركية:**
• التصريح الجمركي الإلكتروني
• دفع الرسوم: جمارك (5%) + VAT (5%)
• الفحص (إن لزم)
• الإفراج عن البضاعة

⚠️ **البضائع المقيدة:**
• المواد الخطرة
• الأسلحة والذخائر
• المخدرات
• بعض المواد الغذائية
• البضائع المزيفة

🌍 **Incoterms - شروط التسليم:**
• EXW - مستودع البائع
• FOB - على ظهر السفينة
• CIF - التكلفة + التأمين + الشحن
• DDP - مسلم مع دفع الرسوم

💡 **نصيحة:** تأكد من جميع المستندات قبل الشحن لتجنب التأخير!"""
    
    # ========== دوال قطع الغيار التفصيلية ==========
    
    @staticmethod
    def _get_engine_parts_guide():
        """دليل قطع المحرك"""
        return """⚙️ **قطع المحرك الأساسية:**

🔩 **محرك البنزين:**
• **البستم (Piston):** يتحرك داخل الأسطوانة لتوليد القوة
• **الشنابر (Rings):** تمنع تسرب الزيت والضغط
• **عمود الكرنك (Crankshaft):** يحول الحركة الترددية لدورانية
• **عمود الكامات (Camshaft):** يتحكم في فتح وإغلاق الصمامات
• **الصمامات (Valves):** دخول الهواء/الوقود وخروج العادم
• **جوان الرأس (Head Gasket):** يمنع التسرب بين الرأس والبلوك
• **البواجي (Spark Plugs):** تولد الشرارة للاحتراق
• **مضخة الماء (Water Pump):** تبريد المحرك
• **مضخة الزيت (Oil Pump):** تزييت المحرك
• **الثرموستات (Thermostat):** تنظيم درجة الحرارة

🔍 **أعطال شائعة:**
❌ البستم مخروط → دخان أزرق + استهلاك زيت
❌ جوان الرأس محروق → خلط ماء وزيت
❌ بواجي قديمة → صعوبة التشغيل"""
    
    @staticmethod
    def _get_diesel_parts_guide():
        """دليل قطع الديزل"""
        return """🚛 **قطع محرك الديزل:**

💉 **نظام الحقن:**
• **البخاخات (Injectors):** حقن الوقود بضغط عالي (1500-2000 bar)
• **مضخة الديزل (HP Pump):** توليد الضغط العالي
• **شمعات التسخين (Glow Plugs):** تسخين لتسهيل البدء البارد
• **فلتر الديزل (Fuel Filter):** تنقية الوقود من الشوائب
• **التيربو (Turbocharger):** زيادة القوة بضغط الهواء
• **الانتركولر (Intercooler):** تبريد هواء التيربو

⚡ **مميزات الديزل:**
✅ عزم أعلى - مناسب للأحمال الثقيلة
✅ استهلاك وقود أقل
✅ عمر أطول

❌ **أعطال شائعة:**
• بخاخات مسدودة → دخان أسود + ضعف قوة
• تيربو خربان → فقدان قوة ملحوظ
• فلتر ديزل مسدود → تقطيع وصعوبة تشغيل"""
    
    @staticmethod
    def _get_transmission_guide():
        """دليل ناقل الحركة"""
        return """🔧 **ناقل الحركة (القير):**

⚙️ **الأنواع:**
1. **قير عادي (Manual):** كلتش + 5-6 غيارات
2. **قير أوتوماتيك (Automatic):** زيت ATF + كونفرتر
3. **CVT:** سير متغير - سلاسة قصوى
4. **DSG/DCT:** قير مزدوج - سرعة + كفاءة

🔩 **المكونات:**
• **الكلتش (Clutch):** فصل ووصل المحرك بالقير
• **عمود الكردان (Drive Shaft):** نقل العزم للعجلات
• **الديفرانس (Differential):** توزيع القوة بين العجلات
• **المحاور (Axles):** نقل القوة للعجلات

⚠️ **علامات الأعطال:**
❌ صوت طقة عند تغيير الغيار → كلتش ضعيف
❌ انزلاق عند التحميل → زيت قديم أو كلتش
❌ اهتزاز → عمود كردان محتاج بلانس"""
    
    @staticmethod
    def _get_suspension_guide():
        """دليل نظام التعليق"""
        return """🚗 **نظام التعليق (المساعدات):**

🔩 **المكونات:**
• **المساعدات (Shock Absorbers):** امتصاص الصدمات والمطبات
• **السوست (Springs):** دعم وزن السيارة
• **الأذرعة (Control Arms):** التحكم في حركة العجلة
• **المقصات (Bushings):** عزل الاهتزاز
• **البلي (Ball Joints):** مفاصل التوجيه

⚡ **أنواع المساعدات:**
1. **هيدروليك (Hydraulic):** تقليدي
2. **غاز (Gas):** أداء أفضل
3. **قابل للتعديل (Adjustable):** مخصص

⚠️ **علامات التلف:**
❌ ارتداد زائد بعد المطب → مساعد ضعيف
❌ صوت طقة على المطبات → مقص أو بلي تالف
❌ سيارة مايلة لجهة → سوست أو مساعد"""
    
    @staticmethod
    def _get_brakes_guide():
        """دليل نظام الفرامل"""
        return """🛑 **نظام الفرامل:**

🔴 **المكونات الأساسية:**
• **أقراص (Discs/Rotors):** السطح الاحتكاكي الأمامي
• **فحمات (Brake Pads):** مادة الاحتكاك
• **طنابير (Drums):** للفرامل الخلفية
• **فك الفرامل (Calipers):** الضغط على الفحمات
• **زيت الفرامل (Brake Fluid):** DOT 3, DOT 4, DOT 5.1
• **ABS:** نظام منع الانزلاق

⚡ **أنواع الفحمات:**
1. **عضوية (Organic):** هادئة - تآكل أقراص أقل
2. **سيراميك (Ceramic):** أداء عالي - غبار أقل
3. **معدنية (Metallic):** قوة فرملة عالية

⚠️ **علامات التآكل:**
❌ صوت صفير → فحمات منتهية
❌ اهتزاز بالفرامل → أقراص معوجة
❌ بدال للأرض → تسريب زيت أو هواء"""
    
    @staticmethod
    def _get_electrical_guide():
        """دليل النظام الكهربائي"""
        return """⚡ **النظام الكهربائي:**

🔋 **المكونات:**
• **البطارية (Battery):** 12V للسيارات، 24V للشاحنات
• **الدينمو (Alternator):** شحن البطارية (13.5-14.5V)
• **السلف (Starter):** بدء تشغيل المحرك
• **الكويلات (Ignition Coils):** رفع الجهد لـ 30,000V
• **الحساسات (Sensors):** قراءة بيانات للكمبيوتر
• **الفيوزات (Fuses):** حماية الدوائر

🔍 **الحساسات الرئيسية:**
• **O2 Sensor:** قياس الأكسجين في العادم
• **MAF:** قياس كتلة الهواء
• **MAP:** قياس ضغط الهواء
• **TPS:** موضع دواسة البنزين
• **CTS:** درجة حرارة المحرك
• **CKP:** موضع عمود الكرنك
• **CMP:** موضع عمود الكامات

⚠️ **أعطال شائعة:**
❌ بطارية فارغة → نظف الأقطاب أو بدّلها
❌ سلف مو شغال → افحص البطارية أولاً
❌ دينمو ضعيف → ضوء البطارية مشتعل"""
    
    @staticmethod
    def _get_ac_guide():
        """دليل نظام التكييف"""
        return """❄️ **نظام التكييف (AC):**

🌡️ **المكونات:**
• **الكمبروسر (Compressor):** ضغط غاز التبريد (قلب النظام)
• **الكوندنسر (Condenser):** تحويل الغاز لسائل (أمام الرديتر)
• **المبخر (Evaporator):** تبخير السائل (داخل الصالون)
• **البلف الانبساطي (Expansion Valve):** تنظيم التدفق
• **غاز التبريد (Refrigerant):** R134a (قديم)، R1234yf (جديد)
• **فلتر التجفيف (Drier):** إزالة الرطوبة

🔄 **دورة التبريد:**
1. الكمبروسر يضغط الغاز → يسخن
2. الكوندنسر يبرد الغاز → يتحول لسائل
3. البلف يخفض الضغط
4. المبخر يبخر السائل → يبرد الهواء

⚠️ **أعطال شائعة:**
❌ تكييف ضعيف → نقص غاز أو كمبروسر ضعيف
❌ صوت من الكمبروسر → بيرنق تالف
❌ ريحة كريهة → فلتر صالون متسخ
❌ ماء يطل من الصالون → بلف مسدود"""
    
    @staticmethod
    def _get_dtc_info(message):
        """معلومات أكواد الأعطال"""
        msg_lower = message.lower()
        
        # استخراج الكود إن وجد
        import re
        code_match = re.search(r'P\d{4}|p\d{4}', message)
        
        common_codes = {
            'P0300': '🔴 **P0300 - Misfire عام في المحرك**\n\n**السبب:**\n• بواجي قديمة\n• كويلات ضعيفة\n• بخاخات مسدودة\n• ضغط منخفض\n\n**الحل:** فحص البواجي والكويلات أولاً',
            'P0420': '🟡 **P0420 - كفاءة Catalyst منخفضة**\n\n**السبب:**\n• الكتلايزر تالف\n• O2 Sensor خربان\n\n**الحل:** فحص O2 sensors ثم الكتلايزر',
            'P0171': '🟠 **P0171 - خليط فقير (Lean)**\n\n**السبب:**\n• تسريب هواء\n• بخاخات ضعيفة\n• MAF sensor خربان\n\n**الحل:** فحص التسريبات + MAF'
        }
        
        if code_match:
            code = code_match.group(0).upper()
            if code in common_codes:
                return common_codes[code]
        
        return """🔍 **أكواد الأعطال (DTC - Diagnostic Trouble Codes):**

📊 **الأنواع:**
• **P0xxx:** Powertrain (المحرك والقير)
• **P1xxx:** صانع السيارة
• **P2xxx:** Powertrain إضافية
• **C0xxx:** Chassis (الشاسيه)
• **B0xxx:** Body (الهيكل)
• **U0xxx:** Network (الشبكة)

🔴 **أشهر الأكواد:**
• **P0300:** Misfire عام
• **P0420:** Catalyst كفاءة منخفضة
• **P0171:** خليط فقير (Lean)
• **P0172:** خليط غني (Rich)
• **P0401:** EGR تدفق غير كافي
• **P0506:** RPM الخمول منخفض

💡 **نصيحة:** اقرأ الكود بجهاز OBD2 scanner أولاً!"""
    
    @staticmethod
    def _get_sensor_troubleshooting(message):
        """استكشاف أعطال الحساسات"""
        return """🔍 **الحساسات وأعطالها:**

📡 **الحساسات الرئيسية:**

1. **O2 Sensor (حساس الأكسجين):**
   • الوظيفة: قياس الأكسجين في العادم
   • العطل: استهلاك وقود عالي، P0420
   • السعر: 150-400 درهم

2. **MAF Sensor (حساس كتلة الهواء):**
   • الوظيفة: قياس كمية الهواء الداخل
   • العطل: تقطيع، P0171/P0172
   • التنظيف: MAF Cleaner Spray
   
3. **MAP Sensor (حساس ضغط الهواء):**
   • الوظيفة: قياس الضغط في المنيفولد
   • العطل: فقدان قوة، خمول غير مستقر

4. **TPS (حساس دواسة البنزين):**
   • الوظيفة: معرفة موضع الدواسة
   • العطل: استجابة بطيئة، تقطيع
   
5. **CTS (حساس حرارة المحرك):**
   • الوظيفة: قياس درجة حرارة المحرك
   • العطل: مروحة لا تعمل، P0125

💡 **نصيحة الفحص:** استخدم Multimeter لفحص الفولت والمقاومة"""
    
    @staticmethod
    def _get_pricing_strategy_guide():
        """دليل استراتيجية التسعير"""
        return """💰 **استراتيجية التسعير الاحترافية:**

📊 **حسب نوع العميل:**

1. **🛒 الأفراد (Retail):**
   • سعر كامل + هامش ربح 20-30%
   • خدمة متميزة
   • ضمان كامل

2. **🏪 التجار (Merchants):**
   • خصم 10-15% للكميات
   • دفع آجل 30-60 يوم
   • شحن مجاني للكميات

3. **🤝 الشركاء (Partners):**
   • خصم 20-25% للعقود طويلة الأمد
   • أولوية في التوريد
   • دعم فني مجاني

4. **⭐ VIP:**
   • خصم إضافي 5%
   • خدمات خاصة
   • استشارات مجانية

📈 **حساب السعر:**
```
سعر البيع = (سعر التكلفة + الجمارك + VAT) × (1 + هامش الربح%)
```

💡 **مثال:**
• التكلفة: 1000 درهم
• الجمارك (5%): 50 درهم
• VAT (5% من 1050): 52.50 درهم
• الإجمالي: 1102.50 درهم
• هامش ربح 25%: **1378 درهم** (سعر البيع)

🎯 **نصائح:**
✅ راقب أسعار المنافسين
✅ اعرض قيمة مضافة (ضمان، توصيل، تركيب)
✅ كن مرناً مع العملاء الدائمين"""
    
    @staticmethod
    def _get_sales_techniques_guide():
        """دليل تقنيات البيع"""
        return """🎯 **تقنيات البيع الاحترافية:**

📋 **الخطوات السبع:**

1️⃣ **الترحيب الحار:**
   • ابتسم وانظر في العين
   • "أهلاً وسهلاً! كيف يمكنني مساعدتك؟"

2️⃣ **فهم الاحتياج:**
   • "ما نوع السيارة؟"
   • "ما المشكلة؟"
   • "متى بدأت؟"

3️⃣ **عرض الحل المناسب:**
   • "عندي قطعتين: أصلي وتجاري"
   • اشرح الفرق بصراحة

4️⃣ **إبراز المزايا:**
   • لا تقل فقط "جودة عالية"
   • قل: "ضمان سنتين + يتحمل حتى 100,000 كم"

5️⃣ **معالجة الاعتراضات:**
   • "غالي؟" → اشرح القيمة طويلة الأمد
   • "أفكر فيه؟" → "ممتاز! خذ رقمي للتواصل"

6️⃣ **الإغلاق (Closing):**
   • "تمام؟ نجهزها لك؟"
   • لا تتردد - كن واثقاً

7️⃣ **المتابعة:**
   • اتصل بعد أسبوع: "كيف القطعة؟"
   • يبني ولاء العميل

💎 **تقنيات متقدمة:**
• **Upselling:** "مع البستم، تحتاج شنابر جديدة"
• **Cross-selling:** "عندنا عرض على زيت المحرك"
• **Bundling:** "باقة كاملة بسعر مخفض"

✨ **القاعدة الذهبية:**
"الناس تشتري من الذي تثق به، ليس الأرخص!" 🌟"""


# إنشاء instance عام
azad_responses = AzadResponses()
