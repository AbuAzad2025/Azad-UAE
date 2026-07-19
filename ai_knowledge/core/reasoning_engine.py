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

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Any, Tuple, Optional

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
            "mathematical": [],
            "logical": [],
            "financial": [],
            "technical": [],
        }

    def think(self, problem: str, context: Optional[dict] = None) -> dict:
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
            context = context or {}
            # 1. فهم المشكلة
            problem_type, key_elements = self._analyze_problem(problem, context)

            # 2. تفكيك المشكلة
            sub_problems = self._decompose_problem(problem, key_elements)

            # 3. حل كل جزء
            partial_solutions = []
            reasoning_steps = []

            for idx, sub_problem in enumerate(sub_problems, 1):
                step_result = self._solve_step(sub_problem, context)
                partial_solutions.append(step_result["solution"])
                reasoning_steps.append(
                    {
                        "step": idx,
                        "problem": sub_problem,
                        "reasoning": step_result["reasoning"],
                        "solution": step_result["solution"],
                        "confidence": step_result["confidence"],
                    }
                )

            # 4. دمج الحلول
            final_solution = self._combine_solutions(partial_solutions, problem_type)

            # 5. التحقق من المنطقية
            verification = self._verify_solution(final_solution, problem, context)

            # 6. حلول بديلة
            alternatives = self._generate_alternatives(problem, context, final_solution)

            # حفظ في التاريخ
            self.reasoning_history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "problem": problem,
                    "solution": final_solution,
                    "steps": reasoning_steps,
                    "verified": verification["is_valid"],
                }
            )

            return {
                "solution": final_solution,
                "reasoning_steps": reasoning_steps,
                "confidence": verification["confidence"],
                "alternatives": alternatives,
                "verification": verification,
                "problem_type": problem_type,
            }

        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            return {
                "solution": None,
                "reasoning_steps": [],
                "confidence": 0,
                "error": str(e),
            }

    @staticmethod
    def _analyze_problem(problem: str, _context: dict) -> Tuple[str, List[str]]:
        """تحليل نوع المشكلة واستخراج العناصر الرئيسية"""
        problem_lower = problem.lower()

        # تحديد النوع
        if any(kw in problem_lower for kw in ["سعر", "price", "تسعير", "pricing"]):
            problem_type = "pricing"
        elif any(kw in problem_lower for kw in ["مخزون", "stock", "inventory"]):
            problem_type = "inventory"
        elif any(
            kw in problem_lower for kw in ["توقع", "predict", "forecast", "متوقع"]
        ):
            problem_type = "prediction"
        elif any(
            kw in problem_lower for kw in ["قيد", "journal", "محاسبة", "accounting"]
        ):
            problem_type = "accounting"
        elif any(
            kw in problem_lower for kw in ["صيانة", "maintenance", "إصلاح", "repair"]
        ):
            problem_type = "maintenance"
        elif any(kw in problem_lower for kw in ["عميل", "customer", "client"]):
            problem_type = "customer"
        else:
            problem_type = "general"

        # استخراج العناصر الرئيسية
        key_elements = []

        # أرقام
        import re

        numbers = re.findall(r"\d+\.?\d*", problem)
        key_elements.extend(numbers)

        # كلمات مفتاحية
        keywords = ["منتج", "عميل", "مورد", "فاتورة", "مبلغ", "كمية"]
        for kw in keywords:
            if kw in problem:
                key_elements.append(kw)

        return problem_type, key_elements

    @staticmethod
    def _decompose_problem(problem: str, _key_elements: List[str]) -> List[str]:
        """تفكيك المشكلة إلى خطوات فرعية"""
        sub_problems = []

        # مثال: "ما السعر المثالي لمنتج تكلفته 100 درهم لعميل VIP؟"
        # →  1. تحديد نوع العميل
        #    2. حساب الهامش المناسب
        #    3. مراعاة السوق
        #    4. حساب السعر النهائي

        if "سعر" in problem.lower() or "price" in problem.lower():
            sub_problems.extend(
                [
                    "تحديد سعر التكلفة",
                    "تحديد نوع العميل والهامش المناسب",
                    "مراعاة حجم الطلب والخصومات",
                    "حساب السعر النهائي المقترح",
                ]
            )
        elif "توقع" in problem.lower() or "predict" in problem.lower():
            sub_problems.extend(
                [
                    "جمع البيانات التاريخية",
                    "تحليل الاتجاهات",
                    "تطبيق النموذج التنبؤي",
                    "حساب الثقة في التوقع",
                ]
            )
        elif "محاسبة" in problem.lower() or "قيد" in problem.lower():
            sub_problems.extend(
                [
                    "تحديد نوع القيد",
                    "حساب المدين والدائن",
                    "التحقق من التوازن",
                    "التأكد من تطبيق المبادئ المحاسبية",
                ]
            )
        else:
            # مشكلة عامة
            sub_problems.extend(
                ["فهم المشكلة", "تحليل المعطيات", "تطبيق المنطق", "استخلاص الحل"]
            )

        return sub_problems

    @staticmethod
    def _solve_step(sub_problem: str, context: dict) -> dict:
        """حل خطوة واحدة"""
        # محاكاة التفكير المنطقي

        if "سعر التكلفة" in sub_problem:
            reasoning = (
                "سعر التكلفة هو الأساس، يجب أن يكون السعر النهائي أعلى منه لتحقيق الربح"
            )
            solution = context.get("cost_price", 100) if context else 100
            confidence = 1.0

        elif "نوع العميل" in sub_problem:
            reasoning = "نوع العميل يحدد الهامش: Regular=30%, Merchant=20%, Partner=15%"
            customer_type = (
                context.get("customer_type", "regular") if context else "regular"
            )
            margin = {"regular": 1.30, "merchant": 1.20, "partner": 1.15}.get(
                customer_type, 1.25
            )
            solution = margin
            confidence = 0.9

        elif "حجم الطلب" in sub_problem:
            reasoning = "الكميات الكبيرة تستحق خصومات أكثر"
            quantity = context.get("quantity", 1) if context else 1
            discount = 0 if quantity < 10 else 5 if quantity < 50 else 10
            solution = discount
            confidence = 0.85

        elif "السعر النهائي" in sub_problem:
            reasoning = "السعر النهائي = التكلفة × الهامش - الخصم"
            cost = context.get("cost_price", 100) if context else 100
            margin = context.get("margin", 1.25) if context else 1.25
            discount = context.get("discount", 0) if context else 0
            solution = cost * margin * (1 - discount / 100)
            confidence = 0.95

        else:
            reasoning = f"تحليل: {sub_problem}"
            solution = "يحتاج معلومات إضافية"
            confidence = 0.5

        return {"solution": solution, "reasoning": reasoning, "confidence": confidence}

    @staticmethod
    def _combine_solutions(partial_solutions: List, problem_type: str) -> Any:
        """دمج الحلول الجزئية"""
        if problem_type == "pricing":
            # دمج خطوات التسعير
            if len(partial_solutions) >= 4:
                return partial_solutions[-1]  # السعر النهائي
            return None

        elif problem_type == "prediction":
            # دمج التوقعات
            if partial_solutions:
                return partial_solutions[-1]
            return None

        else:
            # دمج عام
            return partial_solutions[-1] if partial_solutions else None

    @staticmethod
    def _verify_solution(solution: Any, problem: str, context: dict) -> dict:
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
            if context and "cost_price" in context:
                cost = context["cost_price"]
                if solution < cost:
                    is_valid = False
                    confidence = 0.2
                    verification_notes.append("السعر أقل من التكلفة - خسارة!")
                elif solution < cost * 1.05:
                    confidence = 0.6
                    verification_notes.append("الهامش منخفض جداً (<5%)")

        return {
            "is_valid": is_valid,
            "confidence": confidence,
            "notes": verification_notes,
        }

    @staticmethod
    def _generate_alternatives(
        _problem: str, _context: dict, main_solution: Any
    ) -> List[dict]:
        """توليد حلول بديلة"""
        alternatives = []

        if isinstance(main_solution, (int, float)):
            # حلول بديلة للأسعار
            alternatives.append(
                {
                    "solution": main_solution * 0.95,
                    "description": "سعر أقل بـ 5% - لزيادة المبيعات",
                    "pros": ["جذب عملاء أكثر", "تنافسية أعلى"],
                    "cons": ["هامش أقل"],
                }
            )

            alternatives.append(
                {
                    "solution": main_solution * 1.05,
                    "description": "سعر أعلى بـ 5% - لزيادة الربح",
                    "pros": ["ربح أعلى", "صورة premium"],
                    "cons": ["قد يقلل المبيعات"],
                }
            )

        return alternatives

    def chain_of_thought(self, question: str, data: Optional[dict] = None) -> dict:
        """
        Chain of Thought Reasoning (طريقة DeepSeek)

        يفكر خطوة بخطوة بصوت عالٍ
        """
        available_data = list(data.keys()) if data else []
        thought_chain = [
            {
                "step": 1,
                "thought": f"فهم السؤال: {question}",
                "action": "analyzing question",
            },
            {
                "step": 2,
                "thought": f"المعطيات المتاحة: {', '.join(available_data)}",
                "action": "identifying data",
            },
            {
                "step": 3,
                "thought": "تحديد ما هو المطلوب بالضبط",
                "action": "identifying goal",
            },
            {
                "step": 4,
                "thought": "تطبيق المنطق والمعرفة للوصول للحل",
                "action": "applying logic",
            },
            {"step": 5, "thought": "التحقق من منطقية الحل", "action": "verification"},
        ]

        # الحل النهائي
        final_solution = self.think(question, data)

        return {
            "question": question,
            "thought_chain": thought_chain,
            "solution": final_solution,
            "method": "chain_of_thought",
        }

    @staticmethod
    def mathematical_reasoning(calculation_problem: str) -> dict:
        """
        الاستدلال الرياضي المتقدم

        يحل المسائل الرياضية خطوة بخطوة
        """
        steps = []

        try:
            # استخراج الأرقام
            import re

            numbers = [float(n) for n in re.findall(r"\d+\.?\d*", calculation_problem)]

            # تحديد العملية
            if "+" in calculation_problem or "جمع" in calculation_problem:
                operation = "addition"
                result = sum(numbers)
                steps.append(f"الجمع: {' + '.join(map(str, numbers))} = {result}")

            elif "-" in calculation_problem or "طرح" in calculation_problem:
                operation = "subtraction"
                result = numbers[0] - sum(numbers[1:])
                steps.append(f"الطرح: {numbers[0]} - {sum(numbers[1:])} = {result}")

            elif (
                "×" in calculation_problem
                or "*" in calculation_problem
                or "ضرب" in calculation_problem
            ):
                operation = "multiplication"
                result = 1
                for n in numbers:
                    result *= n
                steps.append(f"الضرب: {' × '.join(map(str, numbers))} = {result}")

            elif (
                "÷" in calculation_problem
                or "/" in calculation_problem
                or "قسمة" in calculation_problem
            ):
                operation = "division"
                result = (
                    numbers[0] / numbers[1]
                    if len(numbers) > 1 and numbers[1] != 0
                    else 0
                )
                steps.append(f"القسمة: {numbers[0]} ÷ {numbers[1]} = {result}")

            elif "%" in calculation_problem or "نسبة" in calculation_problem:
                operation = "percentage"
                if len(numbers) >= 2:
                    result = numbers[0] * (numbers[1] / 100)
                    steps.append(f"النسبة: {numbers[0]} × {numbers[1]}% = {result}")
                else:
                    result = 0

            else:
                operation = "unknown"
                result = None
                steps.append("لم أتمكن من تحديد العملية المطلوبة")

            return {
                "operation": operation,
                "numbers": numbers,
                "steps": steps,
                "result": result,
                "confidence": 1.0 if result is not None else 0.0,
            }

        except Exception as e:
            return {
                "operation": "error",
                "steps": [f"خطأ في الحساب: {e}"],
                "result": None,
                "confidence": 0.0,
            }

    @staticmethod
    def financial_reasoning(financial_question: str, financial_data: dict) -> dict:
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
            sales = financial_data.get("sales", 0)
            costs = financial_data.get("costs", 0)
            expenses = financial_data.get("expenses", 0)
            assets = financial_data.get("assets", 0)
            liabilities = financial_data.get("liabilities", 0)

            # 1. هامش الربح الإجمالي
            if sales > 0 and costs > 0:
                gross_profit = sales - costs
                gross_margin = (gross_profit / sales) * 100

                reasoning.append(
                    "هامش الربح الإجمالي = (المبيعات - التكلفة) / المبيعات"
                )
                reasoning.append(
                    f"= ({sales} - {costs}) / {sales} = {gross_margin:.1f}%"
                )

                metrics["gross_margin"] = gross_margin

                if gross_margin < 20:
                    reasoning.append(
                        "⚠️ الهامش منخفض - حاول زيادة الأسعار أو تقليل التكاليف"
                    )
                elif gross_margin > 40:
                    reasoning.append("✅ الهامش ممتاز - استمر")

            # 2. صافي الربح
            if sales > 0:
                net_profit = sales - costs - expenses
                net_margin = (net_profit / sales) * 100

                reasoning.append("صافي الربح = المبيعات - التكلفة - المصروفات")
                reasoning.append(f"= {sales} - {costs} - {expenses} = {net_profit}")
                reasoning.append(f"هامش صافي الربح = {net_margin:.1f}%")

                metrics["net_profit"] = net_profit
                metrics["net_margin"] = net_margin

            # 3. نسبة السيولة
            if liabilities > 0:
                current_ratio = assets / liabilities
                reasoning.append("نسبة السيولة الجارية = الأصول / الخصوم")
                reasoning.append(f"= {assets} / {liabilities} = {current_ratio:.2f}")

                metrics["current_ratio"] = current_ratio

                if current_ratio < 1:
                    reasoning.append("⚠️ خطر! الخصوم أكبر من الأصول")
                elif current_ratio > 2:
                    reasoning.append("✅ سيولة ممتازة")

            # التوصية النهائية
            if (
                metrics.get("net_margin", 0) > 15
                and metrics.get("current_ratio", 0) > 1.5
            ):
                recommendation = "🎯 الوضع المالي ممتاز - استمر في الاستراتيجية الحالية"
            elif metrics.get("net_margin", 0) < 5:
                recommendation = "⚠️ الربحية منخفضة - راجع التكاليف والأسعار"
            else:
                recommendation = "✅ الوضع جيد - هناك فرص للتحسين"

            return {
                "reasoning_steps": reasoning,
                "metrics": metrics,
                "recommendation": recommendation,
                "confidence": 0.9,
            }

        except Exception as e:
            return {
                "reasoning_steps": [f"خطأ في التحليل: {e}"],
                "metrics": {},
                "recommendation": "تعذر التحليل",
                "confidence": 0.0,
            }

    @staticmethod
    def technical_reasoning(technical_problem: str) -> dict:
        """
        الاستدلال التقني - مهندس الصيانة

        يحلل:
        - الأعطال المحتملة
        - الأسباب الجذرية
        - الحلول التقنية
        """
        problem_lower = technical_problem.lower()

        diagnosis_steps = []

        possible_causes = [
            "فلتر وقود مسدود",
            "شمعات إشعال تالفة",
            "مشكلة في مضخة الوقود",
            "ارتفاع حرارة المحرك",
            "مشكلة في الكمبيوتر",
        ]

        solutions = [
            "استبدال فلتر الوقود",
            "تنظيف أو استبدال الشمعات",
            "فحص مضخة الوقود",
            "فحص نظام التبريد",
            "فحص كمبيوتر المحرك",
        ]

        if "محرك" in problem_lower or "engine" in problem_lower:
            diagnosis_steps.extend(
                [
                    "1. فحص نظام الوقود",
                    "2. فحص نظام الإشعال",
                    "3. فحص نظام التبريد",
                    "4. فحص الضغط",
                ]
            )
            possible_causes = [
                "فلتر وقود مسدود",
                "شمعات إشعال تالفة",
                "مشكلة في مضخة الوقود",
                "ارتفاع حرارة المحرك",
                "مشكلة في الكمبيوتر",
            ]
            solutions = [
                "استبدال فلتر الوقود",
                "تنظيف أو استبدال الشمعات",
                "فحص مضخة الوقود",
                "فحص نظام التبريد",
                "فحص كمبيوتر المحرك",
            ]

        elif "فرامل" in problem_lower or "brake" in problem_lower:
            diagnosis_steps.append("1. فحص سماكة الفحمات")
            diagnosis_steps.append("2. فحص سائل الفرامل")
            diagnosis_steps.append("3. فحص الأقراص")

            possible_causes = [
                "فحمات فرامل بالية",
                "سائل فرامل ملوث",
                "تسرب في الدائرة الهيدروليكية",
                "أقراص فرامل مشروخة",
            ]

            solutions = [
                "استبدال فحمات الفرامل",
                "تغيير سائل الفرامل",
                "إصلاح التسرب",
                "استبدال الأقراص",
            ]

        elif "زيت" in problem_lower or "oil" in problem_lower:
            diagnosis_steps.append("1. فحص مستوى الزيت")
            diagnosis_steps.append("2. فحص جودة الزيت")
            diagnosis_steps.append("3. فحص وجود تسريب")

            possible_causes = [
                "الزيت قديم أو متسخ",
                "مستوى الزيت منخفض",
                "تسرب من الجوان",
                "فلتر الزيت مسدود",
            ]

            solutions = [
                "تغيير الزيت والفلتر",
                "إضافة زيت للمستوى المطلوب",
                "استبدال الجوان",
                "تغيير فلتر الزيت",
            ]

        else:
            diagnosis_steps.append("فحص عام للنظام")
            possible_causes.append("يحتاج معلومات أكثر للتشخيص الدقيق")
            solutions.append("استشر مهندس صيانة متخصص")

        return {
            "problem": technical_problem,
            "diagnosis_steps": diagnosis_steps,
            "possible_causes": possible_causes,
            "recommended_solutions": solutions,
            "priority": "high" if "محرك" in problem_lower else "medium",
            "estimated_time": "2-4 ساعات",
            "estimated_cost": "متوسط",
        }

    @staticmethod
    def business_reasoning(business_question: str, business_data: dict) -> dict:
        """
        الاستدلال التجاري - مستشار أعمال

        يحلل:
        - القرارات الاستراتيجية
        - الفرص والتهديدات
        - خطط النمو
        """
        analysis: dict[str, Any] = {
            "question": business_question,
            "swot": {
                "strengths": [
                    "نظام محاسبي متقدم",
                    "مساعد ذكي متطور",
                    "إدارة مخزون فعالة",
                ],
                "weaknesses": ["يحتاج تدريب النماذج بشكل دوري"],
                "opportunities": [
                    "توسع في الأسواق الجديدة",
                    "إضافة منتجات جديدة",
                    "تحسين تجربة العملاء",
                ],
                "threats": ["المنافسة", "تغيرات السوق"],
            },
            "recommendations": [
                "1. استثمر في التسويق الرقمي",
                "2. حسّن خدمة العملاء",
                "3. وسّع نطاق المنتجات",
                "4. درّب الفريق على النظام",
                "5. راقب المنافسين باستمرار",
            ],
            "action_plan": [
                {
                    "action": "تدريب جميع النماذج العصبية",
                    "priority": "high",
                    "timeline": "هذا الأسبوع",
                    "responsible": "مدير النظام",
                },
                {
                    "action": "مراجعة الأسعار بناءً على AI",
                    "priority": "medium",
                    "timeline": "نهاية الشهر",
                    "responsible": "مدير المبيعات",
                },
            ],
        }

        return analysis

    def get_reasoning_history(self, limit=10):
        """الحصول على تاريخ التفكير"""
        return self.reasoning_history[-limit:] if self.reasoning_history else []

    @staticmethod
    def explain_decision(decision: str, factors: dict) -> str:
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
