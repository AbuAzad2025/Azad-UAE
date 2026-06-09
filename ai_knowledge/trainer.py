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
