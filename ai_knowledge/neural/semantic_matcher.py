"""
🧠 نظام التطابق الدلالي الذكي - Semantic Matcher
يفهم المعنى وليس فقط الكلمات المطابقة!

استخدامات:
- TF-IDF للتشابه الدلالي
- Fuzzy Matching للأخطاء الإملائية
- Intent Detection الذكي
"""

import re
from typing import List, Tuple, Dict
from collections import Counter
import math


class SemanticMatcher:
    """محرك التطابق الدلالي"""

    def __init__(self):
        """تهيئة النظام مع قاعدة النوايا"""
        self.intents_db = self._build_intents_database()
        self.vocabulary = self._build_vocabulary()
        self.idf_scores = self._calculate_idf()

    @staticmethod
    def _build_intents_database() -> Dict[str, List[str]]:
        """بناء قاعدة بيانات النوايا مع أمثلة متعددة - شاملة لكل المعرفة"""
        return {
            # === النظام الأساسي ===
            "create_invoice": [
                "فاتورة جديدة",
                "إنشاء فاتورة",
                "أريد إنشاء فاتورة",
                "سوي لي فاتورة",
                "أضف فاتورة",
                "اعمل فاتورة",
                "بدي أعمل invoice",
                "كيف أسوي بيل",
                "ممكن تساعدني أسوي فاتورة",
                "نو invoice جديد",
                "create new invoice",
                "make invoice",
                "new bill",
                "فاتوره جديده",
            ],
            "create_receipt": [
                "سند قبض جديد",
                "إنشاء سند قبض",
                "أريد سند قبض",
                "سوي سند",
                "اعمل receipt",
                "دفعة جديدة",
                "تسديد",
                "قبض مبلغ",
                "سند دفع",
            ],
            "sales_analysis": [
                "حلل المبيعات",
                "تحليل مبيعات",
                "كيف المبيعات",
                "analyze sales",
                "sales report",
                "تقرير المبيعات",
                "إحصائيات المبيعات",
                "أرقام المبيعات",
                "مبيعات اليوم",
                "مبيعات الشهر",
            ],
            "customer_balance": [
                "رصيد العميل",
                "كم رصيد الزبون",
                "ديون الزبون",
                "حساب العميل",
                "ذمم العميل",
                "customer balance",
                "كم عليه",
                "كم له",
                "حساب فلان",
            ],
            "inventory_check": [
                "فحص المخزون",
                "صحة المخزون",
                "حالة المخزون",
                "مخزون المنتجات",
                "inventory health",
                "stock status",
                "كم في المخزن",
                "مخزون قليل",
            ],
            "system_links": [
                "روابط النظام",
                "روابط سريعة",
                "quick links",
                "system links",
                "صفحات النظام",
                "أين أجد",
                "كيف أصل ل",
                "رابط صفحة",
            ],
            "add_customer": [
                "أضف عميل",
                "إنشاء عميل جديد",
                "سجل زبون",
                "add customer",
                "new customer",
                "عميل جديد",
                "زبون جديد",
            ],
            # === الضرائب والجمارك ===
            "tax_info": [
                "ضريبة القيمة المضافة",
                "الضريبة في الإمارات",
                "VAT",
                "tax rate",
                "كم الضريبة",
                "نسبة الضريبة",
                "ضريبة",
                "الضريبة المستحقة",
                "حساب الضريبة",
                "ضريبة الدخل",
                "ضريبة الشركات",
            ],
            "customs_info": [
                "جمارك",
                "customs",
                "تخليص جمركي",
                "رسوم جمركية",
                "الجمارك في الإمارات",
                "إجراءات جمركية",
                "استيراد",
                "تصدير",
                "بضائع جمركية",
                "تعريفة جمركية",
            ],
            # === قطع الغيار والسيارات - تفصيلية ===
            "engine_parts": [
                "البستم",
                "piston",
                "الشنابر",
                "rings",
                "عمود الكرنك",
                "crankshaft",
                "عمود الكامات",
                "camshaft",
                "الصمامات",
                "valves",
                "جوان الرأس",
                "head gasket",
                "البواجي",
                "spark plugs",
                "مضخة الماء",
                "water pump",
                "مضخة الزيت",
                "oil pump",
                "الثرموستات",
                "thermostat",
            ],
            "diesel_parts": [
                "البخاخات",
                "injectors",
                "مضخة الديزل",
                "fuel pump",
                "شمعات التسخين",
                "glow plugs",
                "فلتر الديزل",
                "fuel filter",
                "التيربو",
                "turbocharger",
                "الانتركولر",
                "intercooler",
            ],
            "transmission_parts": [
                "قير",
                "transmission",
                "الكلتش",
                "clutch",
                "عمود الكردان",
                "drive shaft",
                "الديفرانس",
                "differential",
                "المحاور",
                "axles",
                "قير أوتوماتيك",
                "automatic",
                "CVT",
                "DSG",
                "زيت القير",
                "ATF",
            ],
            "suspension_parts": [
                "المساعدات",
                "shock absorbers",
                "amortisseur",
                "السوست",
                "springs",
                "الأذرعة",
                "control arms",
                "المقصات",
                "bushings",
                "البلي",
                "ball joints",
                "التعليق",
                "suspension",
            ],
            "brake_parts": [
                "فرامل",
                "brakes",
                "أقراص",
                "discs",
                "rotors",
                "فحمات",
                "brake pads",
                "طنابير",
                "drums",
                "فك الفرامل",
                "calipers",
                "زيت الفرامل",
                "brake fluid",
                "ABS",
                "مانع الانزلاق",
            ],
            "electrical_parts": [
                "البطارية",
                "battery",
                "الدينمو",
                "alternator",
                "السلف",
                "starter",
                "الكويلات",
                "ignition coils",
                "الحساسات",
                "sensors",
                "الفيوزات",
                "fuses",
                "الكهرباء",
                "electrical",
            ],
            "ac_parts": [
                "التكييف",
                "AC",
                "الكمبروسر",
                "compressor",
                "الكوندنسر",
                "condenser",
                "المبخر",
                "evaporator",
                "غاز التبريد",
                "refrigerant",
                "R134a",
                "تكييف ضعيف",
                "تكييف مو شغال",
            ],
            "parts_info": [
                "قطعة غيار",
                "قطع غيار",
                "spare parts",
                "معلومات عن قطعة",
                "كيف أميز القطعة",
                "قطعة أصلية",
                "قطعة تقليد",
                "OEM",
                "aftermarket",
            ],
            "automotive_ecu": [
                "ECU",
                "كمبيوتر السيارة",
                "وحدة التحكم",
                "electronic control unit",
                "برمجة السيارة",
                "تشخيص السيارة",
                "أعطال السيارة",
                "رموز الأخطاء",
                "diagnostic codes",
                "فحص الكمبيوتر",
                "OBD2",
                "CAN bus",
            ],
            "diagnostic_codes": [
                "كود خطأ",
                "error code",
                "DTC",
                "P0300",
                "P0420",
                "P0171",
                "check engine",
                "لمبة المحرك",
                "فحص كود",
                "مسح الأكواد",
                "clear codes",
                "ما معنى الكود",
                "كود العطل",
            ],
            "sensors_issues": [
                "حساس",
                "sensor",
                "O2 sensor",
                "MAF",
                "MAP",
                "TPS",
                "CTS",
                "حساس الأكسجين",
                "حساس الهواء",
                "حساس الحرارة",
                "حساس البنزين",
                "حساس خربان",
                "sensor failure",
                "حساس عطلان",
            ],
            "heavy_equipment": [
                "معدات ثقيلة",
                "heavy equipment",
                "كاتربيلر",
                "CAT",
                "Komatsu",
                "Volvo",
                "حفارة",
                "excavator",
                "لودر",
                "loader",
                "جريدر",
                "grader",
                "بلدوزر",
                "bulldozer",
                "Hitachi",
                "JCB",
                "قطع CAT",
            ],
            # === السوق وخدمة العملاء ===
            "market_insights": [
                "رؤى السوق",
                "market insights",
                "اتجاهات السوق",
                "أسعار السوق",
                "المنافسة",
                "competition",
                "تحليل السوق",
                "فرص السوق",
                "المواسم",
                "موسم المبيعات",
                "ذروة المبيعات",
            ],
            "pricing_strategy": [
                "استراتيجية التسعير",
                "pricing strategy",
                "كيف أسعر",
                "هامش الربح",
                "profit margin",
                "سعر تنافسي",
                "خصم للتجار",
                "خصومات",
                "discounts",
                "كم أبيع",
                "سعر مناسب",
                "سعر جملة",
                "wholesale",
                "retail",
            ],
            "customer_service": [
                "خدمة العملاء",
                "customer service",
                "كيف أتعامل مع العميل",
                "نصائح للعملاء",
                "رضا العملاء",
                "شكاوى العملاء",
                "تحسين الخدمة",
                "عميل غاضب",
                "angry customer",
                "handling complaints",
            ],
            "sales_techniques": [
                "تقنيات البيع",
                "sales techniques",
                "كيف أبيع",
                "إقناع العميل",
                "closing sales",
                "إتمام البيع",
                "upselling",
                "cross selling",
                "زيادة المبيعات",
                "نصائح بيع",
            ],
            # === الشحن والجودة ===
            "shipping_laws": [
                "قوانين الشحن",
                "shipping laws",
                "إجراءات الشحن",
                "شحن دولي",
                "international shipping",
                "وثائق الشحن",
                "تأمين الشحن",
            ],
            "quality_standards": [
                "معايير الجودة",
                "quality standards",
                "شهادة جودة",
                "ISO",
                "مواصفات",
                "specifications",
                "اختبار الجودة",
                "quality control",
            ],
            # === الموردين والمشتريات ===
            "suppliers_info": [
                "موردين",
                "suppliers",
                "مورد جديد",
                "إضافة مورد",
                "الموردين",
                "شراء من مورد",
                "عروض الموردين",
                "تقييم المورد",
            ],
            # === المصادر والمعرفة ===
            "knowledge_sources": [
                "مصادر",
                "sources",
                "مصادر معلومات",
                "أين أجد معلومات",
                "مواقع مفيدة",
                "كتب",
                "مراجع",
                "توصيات للمصادر",
                "وين أتعلم",
            ],
            # === القوانين المتقدمة (فلسطين، إسرائيل، الخليج) ===
            "palestine_tax_laws": [
                "ضريبة فلسطين",
                "قانون ضريبي فلسطيني",
                "ضرائب فلسطينية",
                "palestinian tax",
                "ضريبة في فلسطين",
                "VAT فلسطين",
            ],
            "israel_tax_laws": [
                "ضريبة إسرائيل",
                "قانون ضريبي إسرائيلي",
                "ضرائب إسرائيلية",
                "israeli tax",
                "מס ישראל",
                "ضريبة في إسرائيل",
            ],
            "gulf_tax_laws": [
                "ضريبة الخليج",
                "ضرائب دول الخليج",
                "GCC tax",
                "ضريبة السعودية",
                "ضريبة قطر",
                "ضريبة الكويت",
                "ضريبة البحرين",
                "ضريبة عمان",
            ],
            "shipping_regulations": [
                "تنظيمات الشحن",
                "قوانين الشحن",
                "إجراءات الشحن",
                "shipping regulations",
                "import regulations",
                "export laws",
            ],
            # === المعالجة المتقدمة ===
            "memory_query": [
                "تذكر",
                "remember",
                "قلت لي",
                "you told me",
                "في محادثة سابقة",
                "previous conversation",
                "ما قلته",
                "what you said",
            ],
            "multi_step_query": [
                "ثم",
                "then",
                "بعدين",
                "وبعد ذلك",
                "after that",
                "خطوة بخطوة",
                "step by step",
            ],
            # === التفاعل الاجتماعي والشخصية ===
            "greeting": [
                "مرحبا",
                "هلا",
                "أهلا",
                "السلام عليكم",
                "سلام",
                "هاي",
                "hi",
                "hello",
                "صباح الخير",
                "مساء الخير",
                "كيفك",
                "شلونك",
                "أخبار",
                "شو الأخبار",
                "يا هلا",
                "مرحب",
                "هلا والله",
                "كيف الحال",
            ],
            "complaint": [
                "زعلان",
                "مو شغال",
                "خربان",
                "سيء",
                "ما يفهم",
                "غبي",
                "بطيء",
                "مشكلة",
                "في غلط",
                "مو صح",
                "خطأ",
                "ما عجبني",
                "تعبان",
                "قديم",
            ],
            "praise": [
                "كفو",
                "ممتاز",
                "شاطر",
                "وحش",
                "بطل",
                "عظيم",
                "رهيب",
                "فنان",
                "أحسنت",
                "شكرا",
                "مشكور",
                "يعطيك العافية",
                "تسلم",
                "ما قصرت",
                "ذكي",
                "عبقري",
            ],
            "who_are_you": [
                "مين انت",
                "من أنت",
                "عرف عن نفسك",
                "شو اسمك",
                "أنت مين",
                "who are you",
                "what is your name",
                "شو وظيفتك",
                "إيش تسوي",
            ],
            # === المساعدة والدليل ===
            "general_help": [
                "مساعدة",
                "help",
                "كيف أستخدم",
                "شرح لي",
                "explain",
                "ما هو",
                "what is",
                "دليل",
                "guide",
                "how to",
            ],
        }

    def _build_vocabulary(self) -> set:
        """بناء قاموس الكلمات"""
        vocab = set()
        for intent, examples in self.intents_db.items():
            for example in examples:
                words = self._tokenize(example)
                vocab.update(words)
        return vocab

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """تقسيم النص لكلمات"""
        # إزالة علامات الترقيم والتشكيل
        text = re.sub(r"[^\w\s]", " ", text)
        # تحويل لأحرف صغيرة
        text = text.lower()
        # تقسيم
        words = text.split()
        # إزالة الكلمات القصيرة جداً
        words = [w for w in words if len(w) > 1]
        return words

    @staticmethod
    def _calculate_tf(words: List[str]) -> Dict[str, float]:
        """حساب Term Frequency"""
        word_count = Counter(words)
        total_words = len(words)
        return {word: count / total_words for word, count in word_count.items()}

    def _calculate_idf(self) -> Dict[str, float]:
        """حساب Inverse Document Frequency"""
        # عدد الوثائق (الأمثلة) الكلي
        total_docs = sum(len(examples) for examples in self.intents_db.values())

        # حساب عدد الوثائق التي تحتوي على كل كلمة
        word_doc_count: Counter[str] = Counter()
        for intent, examples in self.intents_db.items():
            for example in examples:
                words = set(self._tokenize(example))
                word_doc_count.update(words)

        # حساب IDF
        idf = {}
        for word in self.vocabulary:
            if word in word_doc_count:
                idf[word] = math.log(total_docs / (1 + word_doc_count[word]))
            else:
                idf[word] = 0

        return idf

    def _calculate_tfidf(self, words: List[str]) -> Dict[str, float]:
        """حساب TF-IDF"""
        tf = self._calculate_tf(words)
        tfidf = {}
        for word in words:
            if word in self.idf_scores:
                tfidf[word] = tf[word] * self.idf_scores[word]
            else:
                tfidf[word] = tf[word] * 1.0  # IDF default
        return tfidf

    @staticmethod
    def _cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """حساب التشابه بين متجهين باستخدام Cosine Similarity"""
        # الكلمات المشتركة
        common_words = set(vec1.keys()) & set(vec2.keys())

        if not common_words:
            return 0.0

        # حساب الضرب النقطي
        dot_product = sum(vec1[word] * vec2[word] for word in common_words)

        # حساب المقادير
        magnitude1 = math.sqrt(sum(val**2 for val in vec1.values()))
        magnitude2 = math.sqrt(sum(val**2 for val in vec2.values()))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def find_best_intent(
        self, user_message: str, threshold: float = 0.3
    ) -> Tuple[str | None, float, List[Tuple[str, float]]]:
        """
        إيجاد أفضل نية (intent) للرسالة

        Args:
            user_message: رسالة المستخدم
            threshold: الحد الأدنى للثقة (0.3 = 30%)

        Returns:
            (intent_name, confidence, all_scores)
        """
        # تحليل رسالة المستخدم
        user_words = self._tokenize(user_message)
        user_tfidf = self._calculate_tfidf(user_words)

        # حساب التشابه مع كل نية
        intent_scores = {}

        for intent, examples in self.intents_db.items():
            max_similarity = 0.0

            # حساب التشابه مع كل مثال
            for example in examples:
                example_words = self._tokenize(example)
                example_tfidf = self._calculate_tfidf(example_words)

                similarity = self._cosine_similarity(user_tfidf, example_tfidf)
                max_similarity = max(max_similarity, similarity)

            intent_scores[intent] = max_similarity

        # ترتيب النوايا حسب الدرجة
        sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)

        # أفضل نية
        best_intent, best_score = sorted_intents[0] if sorted_intents else (None, 0.0)

        # إذا كانت الدرجة أقل من الحد الأدنى
        if best_score < threshold:
            return None, best_score, sorted_intents

        return best_intent, best_score, sorted_intents

    @staticmethod
    def fuzzy_match(word1: str, word2: str) -> float:
        """
        مطابقة تقريبية (Fuzzy) بين كلمتين
        تستخدم Levenshtein Distance

        Returns: نسبة التشابه (0-1)
        """
        # Levenshtein Distance بسيط
        len1, len2 = len(word1), len(word2)

        if len1 == 0:
            return 0.0 if len2 == 0 else 0.0

        if len2 == 0:
            return 0.0

        # بناء مصفوفة المسافات
        matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        for i in range(len1 + 1):
            matrix[i][0] = i
        for j in range(len2 + 1):
            matrix[0][j] = j

        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                if word1[i - 1] == word2[j - 1]:
                    cost = 0
                else:
                    cost = 1

                matrix[i][j] = min(
                    matrix[i - 1][j] + 1,  # deletion
                    matrix[i][j - 1] + 1,  # insertion
                    matrix[i - 1][j - 1] + cost,  # substitution
                )

        distance = matrix[len1][len2]
        max_len = max(len1, len2)

        # نسبة التشابه
        similarity = 1 - (distance / max_len)
        return similarity

    def smart_match(self, user_message: str) -> Dict:
        """
        مطابقة ذكية شاملة

        Returns:
            {
                'intent': النية المكتشفة,
                'confidence': مستوى الثقة,
                'method': طريقة الاكتشاف ('semantic', 'fuzzy', 'exact'),
                'all_scores': جميع النتائج,
                'suggestion': اقتراح إذا كانت الثقة منخفضة
            }
        """
        # 1. محاولة Semantic Matching أولاً
        intent, confidence, all_scores = self.find_best_intent(user_message, threshold=0.3)

        if intent and confidence > 0.5:
            return {
                "intent": intent,
                "confidence": confidence,
                "method": "semantic",
                "all_scores": all_scores[:3],
                "suggestion": None,
            }

        # 2. محاولة Fuzzy Matching للكلمات المفتاحية
        user_words = self._tokenize(user_message)
        best_fuzzy_match = None
        best_fuzzy_score = 0.0

        for word in user_words:
            for intent, examples in self.intents_db.items():
                for example in examples:
                    example_words = self._tokenize(example)
                    for ex_word in example_words:
                        fuzzy_score = self.fuzzy_match(word, ex_word)
                        if fuzzy_score > best_fuzzy_score and fuzzy_score > 0.8:
                            best_fuzzy_score = fuzzy_score
                            best_fuzzy_match = intent

        if best_fuzzy_match and best_fuzzy_score > 0.8:
            return {
                "intent": best_fuzzy_match,
                "confidence": best_fuzzy_score,
                "method": "fuzzy",
                "all_scores": [(best_fuzzy_match, best_fuzzy_score)],
                "suggestion": None,
            }

        # 3. لم يتم العثور على تطابق جيد
        suggestion = None
        if all_scores and all_scores[0][1] > 0.2:
            suggestion = f"هل تقصد: {self._get_intent_arabic_name(all_scores[0][0])}؟"

        return {
            "intent": intent if confidence > 0.2 else None,
            "confidence": confidence,
            "method": "low_confidence",
            "all_scores": all_scores[:3],
            "suggestion": suggestion,
        }

    @staticmethod
    def _get_intent_arabic_name(intent: str) -> str:
        """تحويل اسم النية للعربية"""
        names = {
            "create_invoice": "إنشاء فاتورة",
            "create_receipt": "إنشاء سند قبض",
            "sales_analysis": "تحليل المبيعات",
            "customer_balance": "رصيد العميل",
            "inventory_check": "فحص المخزون",
            "system_links": "روابط النظام",
            "add_customer": "إضافة عميل",
            "tax_info": "معلومات الضرائب",
            "customs_info": "معلومات الجمارك",
            "parts_info": "معلومات قطع الغيار",
            "automotive_ecu": "كمبيوتر السيارة ECU",
            "heavy_equipment": "المعدات الثقيلة",
            "market_insights": "رؤى السوق",
            "customer_service": "خدمة العملاء",
            "shipping_laws": "قوانين الشحن",
            "quality_standards": "معايير الجودة",
            "suppliers_info": "معلومات الموردين",
            "knowledge_sources": "مصادر المعرفة",
            "palestine_tax_laws": "القوانين الضريبية الفلسطينية",
            "israel_tax_laws": "القوانين الضريبية الإسرائيلية",
            "gulf_tax_laws": "القوانين الضريبية الخليجية",
            "shipping_regulations": "تنظيمات الشحن",
            "memory_query": "استرجاع من الذاكرة",
            "multi_step_query": "استفسار متعدد الخطوات",
            # النوايا الجديدة - قطع غيار تفصيلية
            "engine_parts": "قطع المحرك",
            "diesel_parts": "قطع الديزل",
            "transmission_parts": "قطع ناقل الحركة",
            "suspension_parts": "قطع التعليق",
            "brake_parts": "قطع الفرامل",
            "electrical_parts": "القطع الكهربائية",
            "ac_parts": "قطع التكييف",
            # نوايا متقدمة
            "diagnostic_codes": "أكواد الأعطال",
            "sensors_issues": "مشاكل الحساسات",
            "pricing_strategy": "استراتيجية التسعير",
            "sales_techniques": "تقنيات البيع",
            "general_help": "مساعدة عامة",
        }
        return names.get(intent, intent)


# إنشاء instance عام
semantic_matcher = SemanticMatcher()


# ===== دوال مساعدة سريعة =====


def understand_message(message: str) -> Dict:
    """فهم رسالة المستخدم بذكاء"""
    return semantic_matcher.smart_match(message)


def get_intent(message: str) -> str:
    """الحصول على النية فقط"""
    result = semantic_matcher.smart_match(message)
    return result["intent"]


def get_confidence(message: str) -> float:
    """الحصول على مستوى الثقة"""
    result = semantic_matcher.smart_match(message)
    return result["confidence"]
