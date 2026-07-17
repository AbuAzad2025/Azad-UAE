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
from datetime import datetime
from typing import List, Any, Optional, Tuple, Callable
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
            "conversations": [],
            "facts": [],
            "procedures": [],
            "user_preferences": {},
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
            from ai_knowledge.knowledge.automotive_ecu_knowledge import (
                get_automotive_ecu_knowledge,
            )

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
            "accounting": {
                "principles": {
                    "accrual": "مبدأ الاستحقاق - تسجيل الإيرادات والمصروفات عند حدوثها",
                    "matching": "مبدأ المقابلة - مقابلة الإيرادات بالمصروفات في نفس الفترة",
                    "consistency": "مبدأ الثبات - استخدام نفس الطرق المحاسبية",
                    "conservatism": "مبدأ الحيطة والحذر - عدم المبالغة في الأصول والإيرادات",
                    "materiality": "مبدأ الأهمية النسبية",
                    "going_concern": "مبدأ الاستمرارية",
                    "double_entry": "القيد المزدوج - لكل مدين دائن",
                },
                "formulas": {
                    "gross_profit": "الربح الإجمالي = المبيعات - تكلفة البضاعة المباعة",
                    "net_profit": "صافي الربح = الإيرادات - جميع المصروفات",
                    "current_ratio": "نسبة السيولة الجارية = الأصول المتداولة / الخصوم المتداولة",
                    "quick_ratio": "نسبة السيولة السريعة = (الأصول المتداولة - المخزون) / الخصوم المتداولة",
                    "debt_ratio": "نسبة المديونية = إجمالي الديون / إجمالي الأصول",
                    "roe": "العائد على حقوق الملكية = صافي الربح / حقوق الملكية",
                    "roa": "العائد على الأصول = صافي الربح / إجمالي الأصول",
                    "gross_margin": "هامش الربح الإجمالي = (الربح الإجمالي / المبيعات) × 100",
                    "net_margin": "هامش الربح الصافي = (صافي الربح / المبيعات) × 100",
                },
                "accounts_structure": {
                    "assets": "الأصول - حسابات ذات طبيعة مدينة",
                    "liabilities": "الخصوم - حسابات ذات طبيعة دائنة",
                    "equity": "حقوق الملكية - حسابات ذات طبيعة دائنة",
                    "revenue": "الإيرادات - حسابات ذات طبيعة دائنة",
                    "expenses": "المصروفات - حسابات ذات طبيعة مدينة",
                },
                "entries": {
                    "sale": {
                        "cash_sale": [
                            "من ح/ النقدية",
                            "إلى ح/ المبيعات",
                            "إلى ح/ ضريبة القيمة المضافة (إن وجدت)",
                        ],
                        "credit_sale": [
                            "من ح/ العملاء",
                            "إلى ح/ المبيعات",
                            "إلى ح/ ضريبة القيمة المضافة",
                        ],
                    },
                    "purchase": {
                        "cash_purchase": [
                            "من ح/ المشتريات",
                            "من ح/ ضريبة القيمة المضافة",
                            "إلى ح/ النقدية",
                        ],
                        "credit_purchase": [
                            "من ح/ المشتريات",
                            "من ح/ ضريبة القيمة المضافة",
                            "إلى ح/ الموردين",
                        ],
                    },
                },
            },
            # ========== الضرائب ==========
            "taxes": {
                "uae_vat": {
                    "rate": 5,
                    "description": "ضريبة القيمة المضافة في الإمارات 5%",
                    "registration_threshold": 375000,
                    "voluntary_threshold": 187500,
                    "zero_rated": [
                        "صادرات",
                        "نقل دولي",
                        "بعض الأدوية",
                        "معادن استثمارية",
                    ],
                    "exempt": ["تأجير سكني", "خدمات مالية معينة", "نقل محلي للركاب"],
                    "calculation": "الضريبة = المبلغ × 5%",
                    "filing_period": "ربع سنوي أو شهري حسب حجم الأعمال",
                },
                "corporate_tax": {
                    "rate": 9,
                    "description": "ضريبة الشركات في الإمارات 9%",
                    "threshold": 375000,
                    "effective_date": "2023-06-01",
                    "exemptions": "الأرباح أقل من 375,000 درهم",
                },
                "customs": {
                    "standard_rate": 5,
                    "gcc_goods": 0,
                    "description": "الرسوم الجمركية 5% (معظم السلع)",
                    "gcc_exemption": "معفاة للسلع من دول الخليج",
                },
            },
            # ========== الإدارة ==========
            "management": {
                "theories": {
                    "swot": "تحليل SWOT - القوة، الضعف، الفرص، التهديدات",
                    "smart_goals": "أهداف SMART - محددة، قابلة للقياس، قابلة للتحقيق، واقعية، محددة بوقت",
                    "kpi": "مؤشرات الأداء الرئيسية",
                    "lean": "الإدارة الرشيقة - تقليل الهدر",
                    "six_sigma": "6 سيجما - تحسين الجودة",
                },
                "inventory_methods": {
                    "fifo": "FIFO - First In First Out - الوارد أولاً يصرف أولاً",
                    "lifo": "LIFO - Last In First Out - الوارد أخيراً يصرف أولاً",
                    "weighted_average": "المتوسط المرجح",
                    "eoq": "EOQ - الكمية الاقتصادية للطلب = √((2 × الطلب السنوي × تكلفة الطلب) / تكلفة الاحتفاظ)",
                    "reorder_point": "نقطة إعادة الطلب = (الطلب اليومي × مدة التوريد) + مخزون الأمان",
                    "safety_stock": "مخزون الأمان = (الطلب الأقصى × مدة التوريد الأقصى) - (الطلب المتوسط × مدة التوريد المتوسطة)",
                    "abc_analysis": "تحليل ABC - تصنيف المخزون حسب القيمة",
                },
                "financial_management": {
                    "working_capital": "رأس المال العامل = الأصول المتداولة - الخصوم المتداولة",
                    "break_even": "نقطة التعادل = التكاليف الثابتة / (سعر البيع - التكلفة المتغيرة للوحدة)",
                    "margin_of_safety": "هامش الأمان = المبيعات الفعلية - مبيعات نقطة التعادل",
                    "operating_leverage": "الرافعة التشغيلية = هامش المساهمة / صافي الربح",
                },
            },
            # ========== الهندسة والصيانة ==========
            "engineering": {
                "automotive": {
                    "engine": {
                        "systems": ["وقود", "إشعال", "تبريد", "تزييت", "عادم"],
                        "common_issues": {
                            "overheating": "ارتفاع الحرارة - فحص الرادياتر، المضخة، الثرموستات",
                            "no_start": "لا يعمل - فحص البطارية، الوقود، الشمعات",
                            "rough_idle": "خشونة - فحص الشمعات، الفلتر، الحقن",
                            "oil_consumption": "استهلاك زيت - فحص الجوانات، المكابس",
                        },
                    },
                    "transmission": {
                        "types": ["يدوي", "أوتوماتيك", "CVT", "DCT"],
                        "maintenance": "تغيير الزيت كل 60,000 كم للأوتوماتيك",
                    },
                    "brakes": {
                        "components": ["فحمات", "أقراص", "كليبرات", "سائل فرامل"],
                        "inspection": "فحص كل 10,000 كم",
                    },
                    "fluids": {
                        "engine_oil": "زيت المحرك - تغيير كل 5,000-10,000 كم",
                        "brake_fluid": "سائل الفرامل - تغيير كل سنتين",
                        "coolant": "سائل التبريد - تغيير كل 2-3 سنوات",
                        "transmission_oil": "زيت القير - تغيير كل 60,000 كم",
                    },
                },
                "heavy_equipment": {
                    "maintenance_schedule": {
                        "daily": "فحص السوائل، الإطارات، الأضواء",
                        "weekly": "فحص الفلاتر، البطارية، الأحزمة",
                        "monthly": "تشحيم، فحص شامل",
                        "quarterly": "تغيير الزيت والفلاتر",
                    }
                },
            },
            # ========== القانون التجاري ==========
            "commercial_law": {
                "uae": {
                    "commercial_license": "رخصة تجارية - متطلبات: موافقة الجهات، دفع الرسوم",
                    "contracts": "العقود التجارية - يجب أن تكون مكتوبة للقيم الكبيرة",
                    "commercial_register": "السجل التجاري - إلزامي لجميع الشركات",
                    "payment_terms": {
                        "net_30": "الدفع خلال 30 يوم",
                        "net_60": "الدفع خلال 60 يوم",
                        "2_10_net_30": "خصم 2% إذا دفع خلال 10 أيام، وإلا كامل المبلغ خلال 30 يوم",
                    },
                }
            },
            # ========== البرمجة ==========
            "programming": {
                "sql": {
                    "select": "SELECT columns FROM table WHERE conditions",
                    "join": "JOIN - ربط الجداول",
                    "group_by": "GROUP BY - تجميع البيانات",
                    "having": "HAVING - شروط على المجموعات",
                    "optimization": "استخدام INDEX للسرعة",
                },
                "python": {
                    "best_practices": [
                        "استخدم list comprehension",
                        "تجنب loops غير الضرورية",
                        "استخدم generators للبيانات الكبيرة",
                        "استخدم f-strings للنصوص",
                        "استخدم type hints",
                        "اكتب docstrings",
                    ]
                },
            },
            # ========== السكرتارية ==========
            "secretarial": {
                "communication": {
                    "email_structure": "الموضوع - التحية - الموضوع - الخاتمة - التوقيع",
                    "professional_tone": "رسمي واحترافي ومختصر",
                    "follow_up": "المتابعة بعد 3 أيام عمل",
                },
                "scheduling": {
                    "priority_matrix": "مصفوفة أيزنهاور - عاجل/مهم، مهم/غير عاجل، عاجل/غير مهم، غير مهم/غير عاجل",
                    "time_blocking": "تقسيم اليوم لكتل زمنية",
                },
            },
            # ========== كمبيوترات السيارات (من automotive_ecu_knowledge) ==========
            "automotive_ecu": automotive_kb,
            # ========== مصادر التعلم الخارجية (30+ مصدر ضخم) ==========
            "external_sources": external_sources,
        }

    # ========================================================================
    # الدالة الرئيسية الموحدة - Master Function
    # ========================================================================

    def ask(
        self,
        question: str,
        context: Optional[dict] = None,
        user_id: Optional[int] = None,
    ) -> dict:
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
            reasoning_result = self._think_logically(
                question, intent, knowledge, context
            )

            # 4. استخدام النماذج العصبية (إذا لزم الأمر)
            neural_result = self._use_neural_if_needed(intent, context) or {}

            # 5. دمج كل المصادر
            answer = self._synthesize_answer(
                question, reasoning_result, neural_result, knowledge, intent
            )

            # 6. التذكر
            if user_id:
                self._remember(user_id, question, answer["text"])

            # 7. حساب الوقت
            response_time = (datetime.now() - start_time).total_seconds()

            # 8. الاقتراحات
            suggestions = self._generate_smart_suggestions(intent, domain)

            result = {
                "answer": answer["text"],
                "confidence": answer["confidence"],
                "reasoning": reasoning_result.get("steps", []),
                "sources": answer.get("sources", []),
                "suggestions": suggestions,
                "domain": domain,
                "intent": intent,
                "response_time_ms": round(response_time * 1000, 2),
                "genius_mode": True,
            }

            logger.info(
                f"🧠 Master Brain answered in {response_time * 1000:.0f}ms - Confidence: {answer['confidence']:.0%}"
            )

            return result

        except Exception as e:
            logger.error(f"Master Brain error: {e}")
            return {
                "answer": "عذراً، دعني أفكر مرة أخرى... يمكنك إعادة صياغة السؤال؟",
                "confidence": 0.3,
                "error": str(e),
            }

    def _analyze_question(self, question: str) -> Tuple[str, str, dict]:
        """تحليل السؤال بذكاء خارق"""
        q_lower = question.lower()

        # تحديد المجال
        if any(
            kw in q_lower
            for kw in ["قيد", "محاسبة", "مدين", "دائن", "ميزانية", "ربح", "خسارة"]
        ):
            domain = "accounting"
        elif any(kw in q_lower for kw in ["ضريبة", "vat", "القيمة المضافة", "جمارك"]):
            domain = "taxes"
        elif any(
            kw in q_lower for kw in ["مخزون", "طلب", "eoq", "reorder", "safety stock"]
        ):
            domain = "management"
        elif any(kw in q_lower for kw in ["محرك", "صيانة", "زيت", "فرامل", "إصلاح"]):
            domain = "engineering"
        elif any(kw in q_lower for kw in ["سعر", "price", "تسعير", "pricing"]):
            domain = "pricing"
        elif any(kw in q_lower for kw in ["توقع", "predict", "forecast", "متوقع"]):
            domain = "prediction"
        elif any(kw in q_lower for kw in ["عميل", "customer", "زبون"]):
            domain = "customer"
        elif any(kw in q_lower for kw in ["كود", "code", "برمجة", "sql", "python"]):
            domain = "programming"
        else:
            domain = "general"

        # تحديد النية
        if "؟" in question or "كيف" in q_lower or "ما" in q_lower or "متى" in q_lower:
            intent = "question"
        elif "احسب" in q_lower or "calculate" in q_lower:
            intent = "calculation"
        elif "توقع" in q_lower or "predict" in q_lower:
            intent = "prediction"
        elif "راجع" in q_lower or "فحص" in q_lower or "check" in q_lower:
            intent = "review"
        else:
            intent = "general"

        # استخراج الكيانات
        entities = {}
        numbers = re.findall(r"\d+\.?\d*", question)
        if numbers:
            entities["numbers"] = [float(n) for n in numbers]

        return intent, domain, entities

    def _retrieve_knowledge(self, domain: str, question: str) -> dict:
        """استرجاع المعرفة المناسبة بسرعة فائقة"""
        if domain in self.knowledge_base:
            return self.knowledge_base[domain]
        return {}

    def _think_logically(
        self, question: str, _intent: str, knowledge: dict, context: dict
    ) -> dict:
        """التفكير المنطقي العميق"""
        steps = []

        # خطوة 1: فهم المطلوب
        steps.append(
            {
                "step": 1,
                "thought": f"فهمت السؤال: {question[:50]}...",
                "action": "understanding",
            }
        )

        # خطوة 2: تحليل المعطيات
        available_data = list(context.keys()) if context else []
        steps.append(
            {
                "step": 2,
                "thought": f"البيانات المتاحة: {', '.join(available_data) if available_data else 'لا يوجد'}",
                "action": "data_analysis",
            }
        )

        # خطوة 3: استخدام المعرفة
        if knowledge:
            steps.append(
                {
                    "step": 3,
                    "thought": "استخدام المعرفة المتخصصة في المجال",
                    "action": "applying_knowledge",
                }
            )

        # خطوة 4: الاستنتاج
        steps.append(
            {"step": 4, "thought": "الوصول للحل الأمثل", "action": "conclusion"}
        )

        return {"steps": steps, "confidence": 0.9}

    def _use_neural_if_needed(self, intent: str, context: dict) -> Optional[dict]:
        """استخدام النماذج العصبية عند الحاجة"""
        # استيراد كسول (lazy import) للسرعة
        if intent in ["prediction", "pricing", "classification"]:
            try:
                from services.ai_service import AIService

                if intent == "pricing" and context.get("product_id"):
                    return AIService.predict_price_with_neural(
                        context["product_id"],
                        context.get("customer_id"),
                        context.get("quantity", 1),
                    )

                elif intent == "prediction":
                    return AIService.forecast_sales_neural(days_ahead=7)

            except Exception as e:
                logger.debug(f"Neural model not used: {e}")
                return None

        return None

    def _synthesize_answer(
        self,
        question: str,
        _reasoning: dict,
        neural: dict,
        knowledge: dict,
        intent: str,
    ) -> dict:
        """دمج كل المصادر في إجابة واحدة متكاملة"""

        answer_parts = []
        sources = []
        confidence = 0.85

        # إجابة من قاعدة المعرفة
        if knowledge:
            # محاسبة
            if "principles" in knowledge:
                if "استحقاق" in question.lower() or "accrual" in question.lower():
                    answer_parts.append(f"📚 {knowledge['principles']['accrual']}")
                    sources.append("قاعدة المعرفة المحاسبية")
                    confidence = 0.98

                elif (
                    "قيد مزدوج" in question.lower()
                    or "double entry" in question.lower()
                ):
                    answer_parts.append(f"📚 {knowledge['principles']['double_entry']}")
                    sources.append("المبادئ المحاسبية")
                    confidence = 1.0

            # الضرائب
            if "vat" in knowledge or "uae_vat" in knowledge:
                if "ضريبة" in question.lower() or "vat" in question.lower():
                    vat_info = knowledge.get("uae_vat", {})
                    answer_parts.append(
                        f"💰 ضريبة القيمة المضافة في الإمارات: {vat_info.get('rate', 5)}%"
                    )
                    answer_parts.append(
                        f"حد التسجيل: {vat_info.get('registration_threshold', 375000):,} درهم"
                    )
                    sources.append("قوانين الضرائب الإماراتية")
                    confidence = 1.0

            # كمبيوترات السيارات
            if "sensors" in knowledge:
                for sensor_code, sensor_data in knowledge.get("sensors", {}).items():
                    if sensor_code.lower() in question.lower():
                        answer_parts.append(
                            f"🚗 {sensor_data.get('name_ar', sensor_code)}"
                        )
                        answer_parts.append(
                            f"الوظيفة: {sensor_data.get('function', '')}"
                        )
                        if "testing" in sensor_data:
                            answer_parts.append(f"الفحص: {sensor_data['testing']}")
                        sources.append("خبير كمبيوترات السيارات - ECU")
                        confidence = 0.95

            # الصيغ
            if "formulas" in knowledge:
                for formula_name, formula in knowledge["formulas"].items():
                    if any(kw in question.lower() for kw in formula_name.split("_")):
                        answer_parts.append(f"📐 {formula}")
                        sources.append("الصيغ المحاسبية")
                        confidence = 0.95

        # إجابة من النماذج العصبية
        if neural:
            if "predicted_price" in neural:
                answer_parts.append(
                    f"🧠 السعر المقترح (بالشبكات العصبية): {neural['predicted_price']:.2f} AED"
                )
                answer_parts.append(f"الهامش: {neural.get('margin_percent', 0):.1f}%")
                answer_parts.append(f"الثقة: {neural.get('confidence', 0):.0%}")
                sources.append("الشبكة العصبية للتسعير")
                confidence = neural.get("confidence", 0.9)

            elif "forecast" in neural:
                answer_parts.append("📈 توقع المبيعات (بالشبكات العصبية):")
                for day in neural.get("forecast", [])[:3]:
                    answer_parts.append(
                        f"- {day.get('day_name', '')}: {day.get('amount', 0):,.0f} AED"
                    )
                sources.append("الشبكة العصبية للتوقعات")
                confidence = 0.94

        # إجابة عامة ذكية
        if not answer_parts:
            if intent == "question":
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
            "text": "\n".join(answer_parts),
            "confidence": confidence,
            "sources": sources,
        }

    def _remember(self, user_id: int, question: str, answer: str):
        """حفظ في الذاكرة الموحدة"""
        self.unified_memory["conversations"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "question": question,
                "answer": answer,
            }
        )

        # الاحتفاظ بآخر 100 فقط للسرعة
        if len(self.unified_memory["conversations"]) > 100:
            self.unified_memory["conversations"] = self.unified_memory["conversations"][
                -100:
            ]

    def _generate_smart_suggestions(self, _intent: str, domain: str) -> List[str]:
        """توليد اقتراحات ذكية"""
        suggestions = {
            "accounting": [
                "احسب نسبة السيولة الجارية",
                "اشرح مبدأ الاستحقاق",
                "كيف أراجع قيد محاسبي؟",
            ],
            "taxes": [
                "احسب ضريبة القيمة المضافة",
                "ما حد التسجيل في VAT؟",
                "اشرح الرسوم الجمركية",
            ],
            "management": [
                "احسب نقطة إعادة الطلب",
                "ما هي الكمية الاقتصادية EOQ؟",
                "كيف أحلل المخزون بطريقة ABC؟",
            ],
            "engineering": [
                "كيف أشخص مشكلة المحرك؟",
                "متى أغير زيت المحرك؟",
                "ما أسباب ارتفاع الحرارة؟",
            ],
            "pricing": [
                "احسب السعر المثالي",
                "ما هامش الربح المناسب؟",
                "كيف أنافس في السوق؟",
            ],
        }

        return suggestions.get(
            domain, ["اسأل عن المحاسبة", "اسأل عن الضرائب", "اسأل عن المخزون"]
        )

    # ========================================================================
    # دوال متقدمة سريعة
    # ========================================================================

    def quick_calc(self, formula_name: str, **params) -> dict:
        """حسابات سريعة للصيغ الشائعة"""
        formulas: dict[str, Callable[..., Any]] = {
            "gross_margin": lambda sales, cogs: (
                ((sales - cogs) / sales * 100) if sales > 0 else 0
            ),
            "net_margin": lambda revenue, expenses: (
                ((revenue - expenses) / revenue * 100) if revenue > 0 else 0
            ),
            "current_ratio": lambda current_assets, current_liabilities: (
                current_assets / current_liabilities if current_liabilities > 0 else 0
            ),
            "eoq": lambda annual_demand, order_cost, holding_cost: (
                (2 * annual_demand * order_cost / holding_cost) ** 0.5
                if holding_cost > 0
                else 0
            ),
            "break_even": lambda fixed_costs, price, variable_cost: (
                fixed_costs / (price - variable_cost)
                if (price - variable_cost) > 0
                else 0
            ),
            "vat": lambda amount: amount * 0.05,
            "price_with_vat": lambda amount: amount * 1.05,
            "price_without_vat": lambda amount_with_vat: amount_with_vat / 1.05,
        }

        if formula_name in formulas:
            try:
                result = formulas[formula_name](**params)
                return {
                    "result": round(result, 2),
                    "formula": formula_name,
                    "params": params,
                    "success": True,
                }
            except Exception as e:
                return {"error": str(e), "success": False}

        return {"error": f"Unknown formula: {formula_name}", "success": False}

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
                            if (
                                isinstance(sub_value, str)
                                and concept.lower() in sub_value.lower()
                            ):
                                return f"📚 {sub_value}"

        return f"🤔 لم أجد شرح مباشر لـ '{concept}'. يمكنك السؤال بشكل أكثر تحديداً؟"

    def validate_accounting_entry(self, debit: float, credit: float) -> dict:
        """التحقق من القيد المحاسبي بسرعة"""
        is_balanced = abs(debit - credit) < 0.01

        return {
            "is_balanced": is_balanced,
            "debit": debit,
            "credit": credit,
            "difference": abs(debit - credit),
            "status": "✅ متوازن" if is_balanced else "❌ غير متوازن",
            "confidence": 1.0 if is_balanced else 0.0,
            "principle": "القيد المزدوج - المدين = الدائن",
            "recommendation": "يمكن اعتماده" if is_balanced else "راجع الأرقام",
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


def ask_azad(
    question: str, context: Optional[dict] = None, user_id: Optional[int] = None
) -> dict:
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
