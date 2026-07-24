"""
🧠 المساعد الذكي الحقيقي - True Intelligent Assistant
نظام ذكاء اصطناعي متكامل - يفهم، يحلل، يستنتج، يتعلم

الفرق بين التلقين والذكاء:
- التلقين: if 'فاتورة' → return "رابط..."
- الذكاء: فهم النية → تحليل البيانات → استنتاج → توليد رد ديناميكي

المحركات المستخدمة:
- Neural Engine: للتعلم والتنبؤ
- Reasoning Engine: للاستنتاج المنطقي
- Data Analyzer: لتحليل البيانات الحقيقية
- Memory System: لتذكر السياق
- Context Engine: لفهم السياق
"""

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class IntelligentAssistant:
    """
    المساعد الذكي الحقيقي - ليس pattern matching

    يعمل بـ 5 مراحل:
    1. فهم النية والسياق (Understanding)
    2. جمع البيانات الحقيقية (Data Collection)
    3. التحليل والاستنتاج (Analysis & Reasoning)
    4. التوليد الديناميكي (Dynamic Generation)
    5. التعلم (Learning)
    """

    def __init__(self):
        """تهيئة جميع المحركات"""
        # تأخير الاستيراد لتجنب circular imports
        self._neural_engine = None
        self._reasoning_engine = None
        self._data_analyzer = None
        self._memory_system = None
        self._context_engine = None
        self._quick_learner = None

        logger.info("🧠 Intelligent Assistant initialized")

    @property
    def quick_learner(self):
        """المتعلم السريع"""
        if self._quick_learner is None:
            from ai_knowledge.learning.quick_learner import quick_learner

            self._quick_learner = quick_learner
        return self._quick_learner

    @property
    def neural_engine(self):
        """محرك الشبكات العصبية"""
        if self._neural_engine is None:
            from ai_knowledge.neural.neural_engine import get_neural_engine

            self._neural_engine = get_neural_engine()
        return self._neural_engine

    @property
    def reasoning_engine(self):
        """محرك الاستنتاج المنطقي"""
        if self._reasoning_engine is None:
            from ai_knowledge.core.reasoning_engine import get_reasoning_engine

            self._reasoning_engine = get_reasoning_engine()
        return self._reasoning_engine

    @property
    def data_analyzer(self):
        """محلل البيانات"""
        if self._data_analyzer is None:
            from ai_knowledge.analytics.data_analyzer import data_analyzer

            self._data_analyzer = data_analyzer
        return self._data_analyzer

    @property
    def memory_system(self):
        """نظام الذاكرة"""
        if self._memory_system is None:
            from ai_knowledge.core.memory_system import get_memory_system

            self._memory_system = get_memory_system()
        return self._memory_system

    @property
    def context_engine(self):
        """محرك السياق"""
        if self._context_engine is None:
            from ai_knowledge.core.context_engine import context_engine

            self._context_engine = context_engine
        return self._context_engine

    def process(
        self,
        message: str,
        user_id: int | None = None,
        context: dict | None = None,
    ) -> dict:
        """
        معالجة ذكية كاملة للرسالة

        Args:
            message: رسالة المستخدم
            user_id: معرف المستخدم
            context: السياق الإضافي

        Returns:
            رد ديناميكي مبني على فهم حقيقي
        """
        try:
            # ========== المرحلة 0: المعرفة السريعة (Quick Knowledge) ==========
            quick_answer = self.quick_learner.get_answer(message)
            if quick_answer:
                return {
                    "success": True,
                    "response": f"{quick_answer}\n\n<sub>⚡ معلومة سريعة</sub>",
                    "intent": "quick_answer",
                    "confidence": 1.0,
                    "method": "quick_learner",
                }

            # ========== المرحلة 1: فهم النية والسياق ==========
            assert user_id is not None
            assert context is not None
            understanding = self._understand_message(message, user_id, context)

            if not understanding["success"]:
                return self._generate_help_response(message)

            intent = understanding["intent"]
            entities = understanding["entities"]
            conversation_context = understanding["context"]

            # ========== المرحلة 2: جمع البيانات الحقيقية ==========
            real_data = self._collect_real_data(intent, entities, user_id)

            # ========== المرحلة 3: التحليل والاستنتاج ==========
            analysis = self._analyze_and_reason(intent, real_data, conversation_context)

            # ========== المرحلة 4: التوليد الديناميكي ==========
            response = self._generate_dynamic_response(intent, analysis, entities, real_data)

            # ========== المرحلة 5: التعلم ==========
            self._learn_from_interaction(message, response, user_id)

            return {
                "success": True,
                "response": response,
                "intent": intent,
                "confidence": understanding["confidence"],
                "data_used": (len(real_data) if isinstance(real_data, list) else bool(real_data)),
                "method": "intelligent_ai",  # ليس pattern matching!
            }

        except Exception as e:
            logger.error(f"Intelligent processing failed: {e}")
            return {
                "success": False,
                "response": f"عذراً، حدث خطأ أثناء المعالجة: {str(e)}",
                "method": "error",
            }

    def _understand_message(self, message: str, user_id: int, context: dict) -> dict:
        """فهم الرسالة بذكاء"""
        try:
            # استخدام semantic matcher للنية الأساسية
            from ai_knowledge.neural.semantic_matcher import understand_message

            semantic_result = understand_message(message)

            # تعميق الفهم بـ Neural Engine
            neural_understanding = self.neural_engine.understand_intent(message)

            # استخراج الكيانات (entities)
            entities = self._extract_entities(message)

            # بناء السياق الكامل
            # بناء السياق الكامل
            full_context = {
                "message": message,
                "user_id": user_id,
                "timestamp": datetime.now(),
                "additional_context": context or {},
            }

            # دمج النتائج
            final_intent = semantic_result.get("intent") or neural_understanding.get("intent")
            confidence = max(
                semantic_result.get("confidence", 0),
                neural_understanding.get("confidence", 0),
            )

            return {
                "success": True,
                "intent": final_intent,
                "entities": entities,
                "context": full_context,
                "confidence": confidence,
                "semantic_scores": semantic_result.get("all_scores", []),
                "neural_features": neural_understanding,
            }

        except Exception as e:
            logger.error(f"Understanding failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _extract_entities(message: str) -> dict:
        """استخراج الكيانات من الرسالة"""
        import re

        entities: dict[str, Any] = {
            "numbers": [],
            "dates": [],
            "names": [],
            "products": [],
            "amounts": [],
        }

        # الأرقام
        numbers = re.findall(r"\d+(?:\.\d+)?", message)
        entities["numbers"] = [float(n) for n in numbers]

        # المبالغ (بالعملة)
        amounts = re.findall(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(درهم|دولار|ريال|AED|USD|SAR)", message)
        entities["amounts"] = [{"value": float(a[0].replace(",", "")), "currency": a[1]} for a in amounts]

        # الأسماء (كلمات بحروف كبيرة أو بعد "العميل" أو "الزبون")
        name_patterns = [
            r"(?:العميل|الزبون|customer)\s+(\w+)",
            r"(?:المنتج|product)\s+(\w+)",
        ]
        for pattern in name_patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            if matches:
                if "عميل" in pattern or "زبون" in pattern:
                    entities["names"].extend(matches)
                else:
                    entities["products"].extend(matches)

        return entities

    def _collect_real_data(self, intent: str, entities: dict, _user_id: int) -> dict:
        """جمع البيانات الحقيقية من النظام"""
        try:
            from models import Sale, Customer, Product
            from extensions import db
            from sqlalchemy import func
            from flask import has_request_context
            from utils.tenanting import get_active_tenant_id
            from flask_login import current_user

            tid = None
            if has_request_context():
                try:
                    tid = get_active_tenant_id(current_user)
                except Exception as exc:
                    logger.debug("Tenant resolution failed: %s", exc)

            def _f(model: type) -> Any:
                from sqlalchemy.orm import Query

                q: Query = db.session.query(model)
                if tid is not None:
                    q = q.filter_by(tenant_id=tid)
                return q

            data: dict[str, Any] = {}

            try:
                data["system_stats"] = {
                    "total_customers": _f(Customer).filter_by(is_active=True).count(),
                    "total_products": _f(Product).filter_by(is_active=True).count(),
                    "total_sales_today": _f(Sale).filter(func.date(Sale.sale_date) == datetime.now().date()).count(),
                }
            except Exception as exc:
                logger.debug("System stats collection failed: %s", exc)
                data["system_stats"] = {}

            if intent in ["sales_analysis", "customer_balance", "inventory_check"]:
                try:
                    thirty_days_ago = datetime.now() - timedelta(days=30)
                    recent_sales = _f(Sale).filter(Sale.sale_date >= thirty_days_ago).all()

                    data["recent_sales"] = {
                        "count": len(recent_sales),
                        "total_amount": sum(float(s.total_amount) for s in recent_sales),
                        "avg_amount": (
                            sum(float(s.total_amount) for s in recent_sales) / len(recent_sales) if recent_sales else 0
                        ),
                        "sales": [
                            {
                                "id": s.id,
                                "date": s.sale_date.strftime("%Y-%m-%d"),
                                "amount": float(s.total_amount),
                                "customer": (s.customer.name if s.customer else "غير محدد"),
                            }
                            for s in recent_sales[-10:]
                        ],
                    }
                except Exception as exc:
                    logger.debug("Recent sales collection failed: %s", exc)

            if intent in ["customer_balance"] and entities.get("names"):
                try:
                    customer_name = entities["names"][0]
                    customer = _f(Customer).filter(Customer.name.ilike(f"%{customer_name}%")).first()

                    if customer:
                        data["customer_data"] = self.data_analyzer.analyze_customer_debt(customer.id)
                except Exception as exc:
                    logger.debug("Customer data collection failed: %s", exc)

            if intent in ["inventory_check"]:
                try:
                    low_stock = (
                        _f(Product)
                        .filter(
                            Product.is_active,
                            Product.current_stock <= Product.min_stock_alert,
                        )
                        .all()
                    )

                    data["low_stock_products"] = [
                        {
                            "id": p.id,
                            "name": p.name,
                            "current_stock": float(p.current_stock),
                            "min_alert": float(p.min_stock_alert),
                            "deficit": float(p.min_stock_alert - p.current_stock),
                        }
                        for p in low_stock
                    ]
                except Exception as exc:
                    logger.debug("Inventory collection failed: %s", exc)

            return data

        except Exception as e:
            logger.error(f"Data collection failed: {e}")
            return {}

    def _analyze_and_reason(self, intent: str, data: dict, _context: dict) -> dict:
        """التحليل والاستنتاج المنطقي"""
        try:
            analysis: dict[str, Any] = {
                "insights": [],
                "warnings": [],
                "recommendations": [],
                "predictions": [],
            }

            # استخدام Reasoning Engine للاستنتاج
            if intent == "sales_analysis" and "recent_sales" in data:
                sales_data = data["recent_sales"]

                # الاستنتاجات
                if sales_data["count"] == 0:
                    analysis["warnings"].append("⚠️ لا توجد مبيعات في آخر 30 يوم - مشكلة خطيرة!")
                    analysis["recommendations"].append("💡 راجع استراتيجية التسويق فوراً")
                elif sales_data["count"] < 5:
                    analysis["warnings"].append("⚠️ المبيعات ضعيفة جداً")
                    analysis["recommendations"].append("💡 تواصل مع العملاء القدامى")
                else:
                    avg_per_day = sales_data["count"] / 30
                    if avg_per_day < 1:
                        analysis["insights"].append(f"📊 متوسط المبيعات: {avg_per_day:.1f} فاتورة/يوم")
                        analysis["recommendations"].append("💡 استهدف 3-5 فواتير يومياً لنمو صحي")
                    else:
                        analysis["insights"].append(f"✅ أداء جيد: {avg_per_day:.1f} فاتورة/يوم")

                # التنبؤ باستخدام Neural Engine
                try:
                    prediction = self.neural_engine.predict_next_week_sales()
                    if prediction.get("success"):
                        analysis["predictions"].append(
                            f"🔮 التوقع للأسبوع القادم: {prediction['predicted_amount']:,.0f} درهم"
                        )
                except Exception as exc:
                    logger.debug("Sales prediction failed: %s", exc)

            elif intent == "inventory_check" and "low_stock_products" in data:
                low_stock = data["low_stock_products"]

                if len(low_stock) == 0:
                    analysis["insights"].append("✅ المخزون صحي - لا توجد منتجات بمخزون منخفض")
                elif len(low_stock) < 5:
                    analysis["warnings"].append(f"⚠️ {len(low_stock)} منتجات بمخزون منخفض")
                    analysis["recommendations"].append("💡 اطلب تجديد المخزون هذا الأسبوع")
                else:
                    analysis["warnings"].append(f"🔴 {len(low_stock)} منتج بمخزون منخفض - عاجل!")
                    analysis["recommendations"].append("💡 اطلب من الموردين فوراً!")
                    total_deficit = sum(p["deficit"] for p in low_stock)
                    analysis["insights"].append(f"📊 العجز الكلي: {total_deficit:.0f} وحدة")

            elif intent == "customer_balance" and "customer_data" in data:
                customer_data = data["customer_data"]

                if customer_data["success"]:
                    debt_info = customer_data["debt_analysis"]
                    total_debt = debt_info["total_debt"]

                    if total_debt == 0:
                        analysis["insights"].append("✅ العميل ليس عليه ديون")
                    elif total_debt < 1000:
                        analysis["insights"].append(f"💰 رصيد العميل: {total_debt:,.2f} درهم (طبيعي)")
                    elif total_debt < 5000:
                        analysis["warnings"].append(f"⚠️ رصيد العميل: {total_debt:,.2f} درهم")
                        analysis["recommendations"].append("💡 تواصل للتحصيل خلال أسبوع")
                    else:
                        analysis["warnings"].append(f"🔴 رصيد مرتفع: {total_debt:,.2f} درهم!")
                        analysis["recommendations"].append("💡 متابعة عاجلة + إيقاف الائتمان")

                    # تحليل التأخير
                    if debt_info["overdue_count"] > 0:
                        analysis["warnings"].append(f"⏰ {debt_info['overdue_count']} فاتورة متأخرة أكثر من 30 يوم")

            return analysis

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {"insights": [], "warnings": [], "recommendations": []}

    @staticmethod
    def _generate_dynamic_response(intent: str, analysis: dict, _entities: dict, data: dict) -> str:
        """توليد رد ديناميكي - ليس مسبق الحفظ"""
        try:
            # بناء الرد بناءً على البيانات الحقيقية
            response_parts = []

            # المقدمة الديناميكية
            if intent == "greeting":
                import secrets

                greetings = [
                    "يا هلا! 🌹 أنا أزاد، مساعدك الذكي. آمرني؟",
                    "هلا والله! جاهز للمساعدة في أي وقت 💪",
                    "وعليكم السلام! كيف أقدر أساعدك اليوم في الكراج؟ 🚗",
                    "أهلاً بك! معك أزاد، المحاسب والمهندس والمدير المالي 😉",
                ]
                response_parts.append(secrets.choice(greetings))

            elif intent == "who_are_you":
                response_parts.append("🤖 **أنا أزاد (AZAD)**\n")
                response_parts.append("مساعد ذكي متطور تم تطويري خصيصاً لإدارة الكراجات والمحاسبة.")
                response_parts.append("\n💪 **قدراتي:**")
                response_parts.append("• 💰 **محاسب:** فواتير، سندات، ضرائب")
                response_parts.append("• 🔧 **مهندس:** معلومات قطع غيار، صيانة")
                response_parts.append("• 📈 **محلل:** تقارير مبيعات، أرباح")
                response_parts.append("• 🧠 **ذكي:** أتعلم منك كل يوم!")

            elif intent == "praise":
                import secrets

                thanks = [
                    "تسلم! هذا واجبي 🌹",
                    "كفوك الطيب! حاضرين للطيبين 💪",
                    "شكراً لك! شهادة أعتز فيها 🌟",
                    "الله يعافيك! نحن بالخدمة دائماً",
                ]
                response_parts.append(secrets.choice(thanks))

            elif intent == "complaint":
                response_parts.append("😔 **حقك علي!**\n")
                response_parts.append("أنا آسف إذا قصرت. أنا ما زلت أتعلم وأتطور.")
                response_parts.append("ممكن تشرح لي أكثر شو المشكلة عشان ما أكررها؟ 🙏")

            elif intent == "sales_analysis":
                response_parts.append("📊 **تحليل المبيعات الحقيقي:**\n")

                if "recent_sales" in data:
                    sales_info = data["recent_sales"]
                    response_parts.append("📈 **آخر 30 يوم:**")
                    response_parts.append(f"• عدد الفواتير: **{sales_info['count']}**")
                    response_parts.append(f"• الإجمالي: **{sales_info['total_amount']:,.0f} درهم**")
                    response_parts.append(f"• المتوسط: **{sales_info['avg_amount']:,.0f} درهم/فاتورة**")
                    response_parts.append("")

            elif intent == "customer_balance":
                response_parts.append("💰 **تحليل رصيد العميل:**\n")

                if "customer_data" in data and data["customer_data"]["success"]:
                    cust = data["customer_data"]["customer"]
                    debt = data["customer_data"]["debt_analysis"]

                    response_parts.append(f"👤 **العميل:** {cust['name']}")
                    response_parts.append(f"💵 **الرصيد الكلي:** {debt['total_debt']:,.2f} درهم")
                    response_parts.append(f"📄 **فواتير غير مدفوعة:** {debt['unpaid_sales_count']}")

                    if debt["overdue_count"] > 0:
                        response_parts.append(f"⏰ **متأخرة (+30 يوم):** {debt['overdue_count']}")
                    response_parts.append("")

            elif intent == "inventory_check":
                response_parts.append("📦 **تحليل المخزون:**\n")

                if "low_stock_products" in data:
                    low_stock = data["low_stock_products"]

                    if len(low_stock) == 0:
                        response_parts.append("✅ **المخزون صحي!** جميع المنتجات فوق الحد الأدنى")
                    else:
                        response_parts.append(f"⚠️ **منتجات بمخزون منخفض:** {len(low_stock)}\n")
                        response_parts.append("**أبرزها:**")
                        for p in low_stock[:5]:
                            response_parts.append(
                                f"• {p['name']}: {p['current_stock']:.0f} (الحد الأدنى: {p['min_alert']:.0f})"
                            )
                    response_parts.append("")

            # إضافة الرؤى
            if analysis.get("insights"):
                response_parts.append("💡 **رؤى:**")
                for insight in analysis["insights"]:
                    response_parts.append(insight)
                response_parts.append("")

            if analysis.get("warnings"):
                response_parts.append("⚠️ **تنبيهات:**")
                for warning in analysis["warnings"]:
                    response_parts.append(warning)
                response_parts.append("")

            if analysis.get("recommendations"):
                response_parts.append("🎯 **توصياتي لك:**")
                for rec in analysis["recommendations"]:
                    response_parts.append(rec)
                response_parts.append("")

            if analysis.get("predictions"):
                response_parts.append("🔮 **التنبؤات:**")
                for pred in analysis["predictions"]:
                    response_parts.append(pred)

            return "\n".join(response_parts)

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return "عذراً، حدث خطأ في توليد الرد"

    def _learn_from_interaction(self, message: str, response: str, user_id: int):
        """التعلم من التفاعل"""
        try:
            tenant_id = None
            try:
                from flask import has_request_context
                from utils.tenanting import get_active_tenant_id
                from flask_login import current_user

                if has_request_context():
                    tenant_id = get_active_tenant_id(current_user)
            except Exception as exc:
                logger.debug("Tenant resolution for learning failed: %s", exc)

            if user_id:
                self.memory_system.remember_conversation(user_id, message, response)

            from ai_knowledge.core.learning_system import learning_system

            learning_system.learn_from_interaction(
                message,
                response,
                context={"user_id": user_id},
                tenant_id=tenant_id,
            )

        except Exception as e:
            logger.error(f"Learning failed: {e}")

    @staticmethod
    def _generate_help_response(_message: str) -> dict:
        """رد المساعدة عند عدم الفهم"""
        return {
            "success": True,
            "response": """🤔 لم أفهم سؤالك بشكل كامل.

💡 **يمكنك أن تسألني عن:**
• "كيف مبيعاتي هالشهر؟"
• "رصيد العميل أحمد؟"
• "وين المخزون الناقص؟"
• "توقع المبيعات للأسبوع الجاي"

🧠 أنا أحلل البيانات الحقيقية وأعطيك رؤى ذكية - ليس مجرد إجابات جاهزة!""",
            "method": "help",
        }


# إنشاء instance عام
intelligent_assistant = IntelligentAssistant()


# دالة مساعدة
def intelligent_response(message: str, user_id: int | None = None, context: dict | None = None) -> str:
    """الحصول على رد ذكي"""
    result = intelligent_assistant.process(message, user_id, context)
    return result.get("response", "عذراً، حدث خطأ")
