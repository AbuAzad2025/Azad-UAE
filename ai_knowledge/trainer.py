"""
trainer.py - Local AI training pipeline.
Seeds, learns, and improves the local assistant from real interactions.
"""
import json
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# SEED KNOWLEDGE - Essential Q&A the assistant must know
# ============================================================

SEED_QA = [
    # System overview
    ("ملخص النظام", "هذا نظام أزاد لإدارة كراجات وورش المعدات الثقيلة.\n"
     "يدير: العملاء، الموردين، المنتجات، فواتير البيع والشراء، "
     "المصروفات، المدفوعات، الشيكات، حسابات الموظفين.\n"
     "يعمل بنظام التينانت (tenant) المتعدد مع صلاحيات أدوار."),
    ("ماذا يمكنك أن تفعل؟", "أستطيع:\n"
     "• تحليل البيانات وإنشاء تقارير\n"
     "• إنشاء عملاء، فواتير، ومنتجات\n"
     "• المساعدة في الضرائب والجمارك\n"
     "• تقديم نصائح محاسبية\n"
     "• الإجابة عن استفسارات النظام"),
    ("ما هي قدراتك؟", "أنا مساعد ذكي متكامل:\n"
     "- تحليل مبيعات وأرباح\n"
     "- تنبؤ بالطلب والمخزون\n"
     "- إنشاء فواتير وعملاء\n"
     "- استشارات ضريبية وجمركية\n"
     "- خبرة في قطع غيار المعدات الثقيلة"),

    # Role info
    ("ما هي الأدوار في النظام؟", "الأدوار المتاحة:\n"
     "• owner - مالك المنصة (صلاحيات كاملة)\n"
     "• super_admin - مدير عام\n"
     "• manager - مدير\n"
     "• accountant - محاسب\n"
     "• seller - بائع\n"
     "• viewer - مشاهد فقط\n"
     "• developer - مطوّر"),
    ("ما هي صلاحياتي؟", "يمكنك معرفة صلاحياتك من صفحة المستخدم أو بسؤالي عن صلاحية معينة."),

    # Commands
    ("كيف أضيف عميلاً؟", "لإضافة عميل جديد استخدم الأمر:\n"
     "`عميل: الاسم، الهاتف، العنوان`\n"
     "مثال: عميل: أحمد محمد، 0561234567، دبي"),
    ("كيف أضيف منتجاً؟", "لإضافة منتج جديد:\n"
     "`منتج: الاسم، رقم القطعة، السعر، الكمية`\n"
     "مثال: منتج: فلتر زيت كاتربلر، 1R0716، 50، 100"),
    ("كيف أبيع منتجاً؟", "لإنشاء فاتورة بيع:\n"
     "`فاتورة: اسم العميل، اسم المنتج، الكمية`\n"
     "مثال: فاتورة: محمد، فلتر زيت، 2"),
    ("كيف أستلم دفعة؟", "لتسجيل دفعة:\n"
     "`استلام: اسم العميل، المبلغ، طريقة الدفع`\n"
     "مثال: استلام: أحمد، 500، كاش"),

    # Sales analysis
    ("حلل المبيعات", "لتحليل المبيعات أحتاج إلى:\n"
     "- إجمالي المبيعات\n"
     "- عدد الفواتير\n"
     "- أفضل العملاء\n"
     "- المنتجات الأكثر مبيعاً\n"
     "اكتب طلباً محدداً مثل 'أفضل 5 عملاء' أو 'مبيعات اليوم'."),
    ("أفضل العملاء", "يمكنني عرض العملاء حسب إجمالي مشترياتهم. أكتب:\n"
     "`ملخص المبيعات` لعرض التقرير الكامل."),
    ("منتجات منخفضة الربح", "يمكنني تحليل هوامش الربح لكل منتج. أكتب:\n"
     "`هوامش الربح` لتحليل تفصيلي."),
    ("مبيعات اليوم", "للاستعلام عن مبيعات اليوم، استخدم:\n"
     "`ملخص المبيعات` في قائمة التقارير."),

    # Inventory
    ("صحة المخزون", "يمكنني تقييم المخزون عبر:\n"
     "- المنتجات تحت حد الطلب\n"
     "- المنتجات الراكدة\n"
     "- قيمة المخزون الإجمالية\n"
     "استخدم الأمر `check_stock` لتفاصيل محددة."),
    ("المخزون", "يمكنني الإجابة عن:\n"
     "- كمية منتج معين في المخزون\n"
     "- المنتجات التي تحتاج إعادة طلب\n"
     "- إجمالي قيمة المخزون"),

    # General ERP
    ("الضرائب في الإمارات", "ضريبة القيمة المضافة في الإمارات 5%.\n"
     "- التسجيل الإلزامي إذا تجاوزت الإيرادات 375,000 درهم\n"
     "- التسجيل الاختياري إذا تجاوزت 187,500 درهم\n"
     "- يتم تطبيق الضريبة على معظم السلع والخدمات"),
    ("الجمارك", "الجمارك في الإمارات:\n"
     "- رسوم جمركية 5% على معظم البضائع المستوردة\n"
     "- إعفاءات للمعدات الثقيلة المستعملة في بعض الحالات\n"
     "- تحتاج شهادة منشأ وفاتورة تجارية"),

    # Finance
    ("الأرباح", "لتحليل الأرباح استخدم:\n"
     "`ملخص الأرباح` أو اسأل 'ما هي أرباح هذا الشهر؟'"),
    ("التدفق النقدي", "يمكنني توقع التدفق النقدي بناءً على:\n"
     "- المبيعات المسجلة\n"
     "- المصروفات\n"
     "- المدفوعات المستحقة\n"
     "اسأل: 'توقع التدفق النقدي'"),

    # Technical
    ("المعدات الثقيلة", "لدي خبرة في:\n"
     "- قطع غيار كاتربلر (CAT)، كوماتسو، هيتاشي\n"
     "- أنظمة ECU و OBD-II\n"
     "- برامج الصيانة الدورية\n"
     "- التشخيص الميكانيكي والكهربائي"),
    ("كمبيوترات السيارات", "ECU (وحدة التحكم الإلكترونية):\n"
     "- تتحكم بعمل المحرك وناقل الحركة\n"
     "- تتصل عبر OBD-II للتشخيص\n"
     "- تقرأ رموز الأعطال (DTC)\n"
     "- تدعم إعادة البرمجة (Tuning)"),

    # Purchases
    ("كيف أضيف فاتورة مشتريات؟", "لإضافة فاتورة شراء:\n"
     "`فاتورة شراء: اسم المورد، اسم المنتج، الكمية، السعر`\n"
     "مثال: فاتورة شراء: شركة الخليج، فلتر زيت كاتربلر، 50، 25"),
    ("كيف أسجل مورداً جديداً؟", "لإضافة مورد جديد:\n"
     "`مورد: الاسم، الهاتف، العنوان`\n"
     "مثال: مورد: شركة دبي للمعدات، 0567890123، المنطقة الصناعية دبي"),
    ("المشتريات", "يمكنني مساعدتك في:\n"
     "- تسجيل فواتير المشتريات\n"
     "- عرض المشتريات حسب التاريخ\n"
     "- تحليل المشتريات حسب المورد\n"
     "- مقارنة أسعار الموردين"),

    # Payments
    ("المدفوعات", "يمكنني إدارة المدفوعات:\n"
     "- تسجيل دفعة مستلمة من عميل\n"
     "- تسجيل دفعة صادرة لمورد\n"
     "- عرض المدفوعات حسب التاريخ\n"
     "- تتبع المدفوعات المستحقة"),
    ("طرق الدفع المتاحة", "طرق الدفع المدعومة:\n"
     "• كاش (Cash)\n"
     "• بنك (Bank Transfer)\n"
     "• شيك (Cheque)\n"
     "• بطاقة (Card)\n"
     "• محفظة إلكترونية (Wallet)"),

    # Cheques
    ("الشيكات", "يمكنني مساعدتك في إدارة الشيكات:\n"
     "- تسجيل شيك وارد أو صادر\n"
     "- متابعة حالة الشيك (قيد التحصيل، مقبوض، مرتجَع)\n"
     "- عرض الشيكات المستحقة\n"
     "- تقارير الشيكات حسب البنك والحالة"),
    ("كيف أسجل شيكاً؟", "لتسجيل شيك:\n"
     "`شيك: الاسم، المبلغ، تاريخ الاستحقاق، البنك`\n"
     "مثال: شيك: أحمد محمد، 5000، 2025-06-15، بنك دبي الإسلامي"),
    ("حالات الشيك", "حالات الشيك:\n"
     "• pending - قيد التحصيل\n"
     "• collected - مقبوض\n"
     "• bounced - مرتجَع\n"
     "• forwarded - معاد توجيهه\n"
     "يمكنك تحديث الحالة من صفحة الشيكات"),

    # Payroll
    ("الرواتب", "يمكنني مساعدتك في:\n"
     "- عرض رواتب الموظفين\n"
     "- إضافة مكافأة أو خصم\n"
     "- تقارير الرواتب الشهرية\n"
     "- احتساب المستحقات"),
    ("كيف أضيف راتب موظف؟", "لإضافة راتب:\n"
     "`راتب: اسم الموظف، الراتب الأساسي، المكافآت، الخصومات`\n"
     "مثال: راتب: محمد علي، 5000، 500، 200"),

    # Reports
    ("التقارير", "التقارير المتاحة:\n"
     "• ملخص المبيعات (Sales Summary)\n"
     "• ملخص الأرباح (Profit Summary)\n"
     "• الذمم المدينة (Receivables)\n"
     "• الذمم الدائنة (Payables)\n"
     "• المخزون (Inventory)\n"
     "• حركة المستودع (Warehouse Movements)\n"
     "• الحسابات (Ledger)\n"
     "• مصروفات (Expenses)"),
    ("الذمم المدينة", "الذمم المدينة (Receivables):\n"
     "تظهر المبالغ المستحقة للشركة من العملاء.\n"
     "يمكنك عرضها من قائمة التقارير > الذمم المدينة\n"
     "أو اسأل: 'كم المبالغ المستحقة للشركة؟'"),
    ("الذمم الدائنة", "الذمم الدائنة (Payables):\n"
     "تظهر المبالغ المستحقة على الشركة للموردين.\n"
     "يمكنك عرضها من قائمة التقارير > الذمم الدائنة\n"
     "أو اسأل: 'كم المبالغ المستحقة على الشركة؟'"),
    ("التقارير المالية", "التقارير المالية المتاحة:\n"
     "• كشف حساب عميل\n"
     "• كشف حساب مورد\n"
     "• دفتر الأستاذ (Ledger)\n"
     "• قيود اليومية (Journal Entries)\n"
     "• تقارير الخزينة (Treasury)"),

    # Warehouse / Inventory
    ("المستودعات", "يمكنني مساعدتك في:\n"
     "- عرض المخزون في كل مستودع\n"
     "- تحويل منتجات بين المستودعات\n"
     "- تتبع حركة المستودع\n"
     "- معرفة المنتجات منخفضة المخزون"),
    ("التحويل بين المستودعات", "لتحويل منتجات بين المستودعات:\n"
     "اذهب إلى قائمة المستودعات > حركة المخزون\n"
     "أو اسأل عن منتج معين لأعرف مكان توافره"),
    ("المنتجات منخفضة المخزون", "يمكنك عرض المنتجات منخفضة المخزون من:\n"
     "- قائمة المستودعات > المنتجات منخفضة\n"
     "- أو اسأل: 'ما هي المنتجات التي تحتاج إعادة طلب؟'"),

    # Returns
    ("المرتجعات", "يمكنني مساعدتك في:\n"
     "- تسجيل مرتجع بيع (من عميل)\n"
     "- تسجيل مرتجع شراء (لمورد)\n"
     "- عرض سجل المرتجعات"),
    ("كيف أسجل مرتجع بيع؟", "لتسجيل مرتجع بيع:\n"
     "`مرتجع بيع: رقم الفاتورة، اسم المنتج، الكمية، السبب`\n"
     "مثال: مرتجع بيع: INV-001، فلتر زيت، 1، خطأ في القطعة"),

    # Expenses
    ("المصروفات", "يمكنني مساعدتك في:\n"
     "- تسجيل مصروف جديد\n"
     "- تصنيف المصروفات (إيجار، رواتب، صيانة، ...)\n"
     "- تقارير المصروفات الشهرية\n"
     "- تحليل المصروفات حسب النوع"),
    ("كيف أسجل مصروفاً؟", "لتسجيل مصروف:\n"
     "`مصروف: النوع، المبلغ، التاريخ، البيان`\n"
     "مثال: مصروف: إيجار، 10000، 2025-06-01، إيجار يونيو"),

    # Users
    ("إدارة المستخدمين", "لإدارة المستخدمين يمكنك:\n"
     "- إضافة مستخدم جديد\n"
     "- تعديل صلاحيات مستخدم\n"
     "- تعطيل أو تفعيل مستخدم\n"
     "- تغيير كلمة المرور"),
    ("كيف أضيف مستخدماً؟", "لإضافة مستخدم جديد:\n"
     "اذهب إلى قائمة الإعدادات > المستخدمين > إضافة مستخدم\n"
     "أو اسأل عن الأدوار المتاحة لاختيار الصلاحية المناسبة"),

    # Support
    ("كيف أتواصل مع الدعم؟", "لديك عدة خيارات:\n"
     "- صفحة الدعم الفني في النظام\n"
     "- يمكنك إرسال تذكرة دعم من قائمة المساعدة\n"
     "- البريد الإلكتروني: support@azad.com (مثال افتراضي)"),
    ("تبليغ مشكلة", "للتبليغ عن مشكلة:\n"
     "استخدم صفحة الدعم في النظام\n"
     "أو أرسل لي وصف المشكلة وسأوجهك للحل المناسب"),

    # Settings
    ("الإعدادات", "يمكنك تعديل:\n"
     "• إعدادات الشركة (الاسم، الشعار، الألوان)\n"
     "• إعدادات الفاتورة (اللون، التنسيق)\n"
     "• إعدادات المستودع\n"
     "• إعدادات النظام من لوحة المالك"),

    # Useful shortcuts
    ("الأوامر السريعة", "الأوامر النصية المختصرة:\n"
     "• `عميل:` - إضافة عميل\n"
     "• `فاتورة:` - إنشاء فاتورة\n"
     "• `منتج:` - إضافة منتج\n"
     "• `مورد:` - إضافة مورد\n"
     "• `شيك:` - تسجيل شيك\n"
     "• `مصروف:` - تسجيل مصروف\n"
     "• `راتب:` - إضافة راتب\n"
     "• `مرتجع بيع:` - تسجيل مرتجع\n"
     "• `مبيعات:` - عرض تقرير المبيعات"),
    ("مساعدتي في التقارير", "لطلب تقرير:\n"
     "اكتب نوع التقرير المطلوب مثل:\n"
     "'عرض تقرير المبيعات'\n"
     "'كم مبيعات هذا الأسبوع؟'\n"
     "'أظهر المخزون'\n"
     "'ما هي المصروفات هذا الشهر؟'"),
]

# ============================================================
# TRAINER
# ============================================================

class Trainer:
    """Local AI training pipeline. Seeds + learns from interactions."""

    def __init__(self):
        self.quick_learner = None
        self._seeded = False

    def _get_ql(self):
        if self.quick_learner is None:
            try:
                from ai_knowledge.learning_engine import quick_learner
                self.quick_learner = quick_learner
            except Exception:
                from ai_knowledge.learning.quick_learner import quick_learner as ql
                self.quick_learner = ql
        return self.quick_learner

    def seed(self):
        """Seed quick_learner with essential knowledge + expertise files."""
        if self._seeded:
            return
        ql = self._get_ql()
        count = 0
        for question, answer in SEED_QA:
            existing = ql.get_answer(question)
            if existing is None:
                ql.learn(question, answer, category='system')
                count += 1
        # Also seed from expertise JSON files
        try:
            import glob, json, os
            training_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai_training')
            for path in glob.glob(os.path.join(training_dir, 'GLOBAL', 'expertise', '*.json')):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                areas = data.get('expertise_areas', []) if isinstance(data, dict) else data
                for area in areas:
                    topic = area.get('topic', '')
                    knowledge = area.get('knowledge', '')
                    if topic and knowledge:
                        existing = ql.get_answer(topic)
                        if existing is None:
                            ql.learn(topic, knowledge, category='expertise')
                            count += 1
        except Exception as e:
            logger.debug(f"Trainer: expertise seed skipped ({e})")
        self._seeded = True
        if count > 0:
            logger.info(f"Trainer: seeded {count} new Q&A pairs")

    def learn_from_interaction(self, question: str, answer: str, user_id: int = None,
                                success: bool = True, feedback: Optional[str] = None):
        """Learn from a real user interaction."""
        if not question or not answer:
            return

        # Seed first if needed
        self.seed()

        # Save to quick_learner for instant recall
        ql = self._get_ql()
        existing = ql.get_answer(question)
        if existing is None and success:
            ql.learn(question, answer, category='learned')

        # Save to AzadLearningSystem for pattern analysis
        try:
            from ai_knowledge.core.learning_system import learning_system
            learning_system.learn_from_interaction(
                question=question,
                response=answer,
                user_feedback=feedback or ("success" if success else "failure"),
                context={"user_id": user_id, "source": "trainer"}
            )
        except Exception as e:
            logger.debug(f"Trainer: learning_system error (non-critical): {e}")

    def train_from_feedback(self, question: str, correct_answer: str, user_id: int = None):
        """Train from explicit correction by user."""
        ql = self._get_ql()
        ql.learn(question, correct_answer, category='corrected')
        logger.info(f"Trainer: corrected answer for '{question[:50]}'")
        try:
            from ai_knowledge.core.learning_system import learning_system
            learning_system.learn_from_interaction(
                question=question,
                response=correct_answer,
                user_feedback="correction",
                context={"user_id": user_id, "source": "feedback"}
            )
        except Exception:
            pass

    def get_stats(self) -> dict:
        """Return training statistics."""
        ql = self._get_ql()
        kb = getattr(ql, 'knowledge_base', {})
        categories = {}
        for k, v in kb.items():
            cat = v.get('category', 'unknown')
            categories[cat] = categories.get(cat, 0) + 1
        return {
            "total_qa": len(kb),
            "categories": categories,
            "seeded": self._seeded,
        }


trainer = Trainer()
