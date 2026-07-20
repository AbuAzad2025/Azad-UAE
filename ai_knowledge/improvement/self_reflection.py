"""
🔮 محرك التأمل الذاتي - Self-Reflection Engine
المساعد يراجع نفسه ويحسن أداءه

القدرات:
- تقييم الأداء الذاتي
- اكتشاف نقاط الضعف
- التحسين المستمر
- التعلم من الأخطاء
- تطوير القدرات
"""

import logging
from datetime import datetime
from collections import defaultdict
from typing import Any, List

logger = logging.getLogger(__name__)


class SelfReflectionEngine:
    """
    محرك التأمل الذاتي

    يراجع:
    - دقة التوقعات
    - جودة الردود
    - مستوى الرضا
    - الأخطاء المتكررة
    - فرص التحسين
    """

    def __init__(self) -> None:
        self.performance_log: list[dict[str, Any]] = []
        self.errors_log: list[dict[str, Any]] = []
        self.improvements_log: list[dict[str, Any]] = []
        self.self_assessment: dict[str, Any] = {}

    def reflect_on_performance(self) -> dict:
        """
        التأمل في الأداء العام

        Returns:
            {
                'overall_score': التقييم الإجمالي,
                'strengths': نقاط القوة,
                'weaknesses': نقاط الضعف,
                'improvements_needed': التحسينات المطلوبة
            }
        """
        assessment: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "overall_score": 0,
            "strengths": [],
            "weaknesses": [],
            "improvements_needed": [],
        }

        # تقييم الدقة
        if self.performance_log:
            recent_performance = self.performance_log[-100:]  # آخر 100 عملية

            accuracy_scores = [p.get("accuracy", 0) for p in recent_performance if "accuracy" in p]

            if accuracy_scores:
                avg_accuracy = sum(accuracy_scores) / len(accuracy_scores)
                assessment["overall_score"] = avg_accuracy

                if avg_accuracy > 0.9:
                    assessment["strengths"].append(f"دقة عالية جداً: {avg_accuracy:.0%}")
                elif avg_accuracy > 0.7:
                    assessment["strengths"].append(f"دقة جيدة: {avg_accuracy:.0%}")
                else:
                    assessment["weaknesses"].append(f"الدقة منخفضة: {avg_accuracy:.0%}")
                    assessment["improvements_needed"].append("زيادة البيانات التدريبية")

        # تحليل الأخطاء
        if self.errors_log:
            recent_errors = self.errors_log[-50:]

            # تجميع الأخطاء المتشابهة
            error_types: dict[str, int] = defaultdict(int)
            for error in recent_errors:
                error_type = error.get("type", "unknown")
                error_types[error_type] += 1

            # أكثر الأخطاء تكراراً
            if error_types:
                most_common = max(error_types, key=lambda k: error_types[k])
                count = error_types[most_common]

                assessment["weaknesses"].append(f"خطأ متكرر: {most_common} ({count} مرة)")
                assessment["improvements_needed"].append(f"إصلاح: {most_common}")

        # التحسينات السابقة
        if self.improvements_log:
            recent_improvements = self.improvements_log[-10:]
            assessment["recent_improvements"] = [imp.get("improvement", "") for imp in recent_improvements]

        # حفظ التقييم
        self.self_assessment = assessment

        logger.info(f"🔮 Self-reflection complete: Overall score {assessment['overall_score']:.0%}")

        return assessment

    def log_performance(self, task: str, accuracy: float, details: dict | None = None) -> None:
        """تسجيل الأداء"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "accuracy": accuracy,
            "details": details or {},
        }

        self.performance_log.append(entry)

        # الاحتفاظ بآخر 1000 فقط
        if len(self.performance_log) > 1000:
            self.performance_log = self.performance_log[-1000:]

    def log_error(self, error_type: str, error_message: str, context: dict | None = None) -> None:
        """تسجيل خطأ للتعلم منه"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": error_type,
            "message": error_message,
            "context": context or {},
        }

        self.errors_log.append(entry)

        # الاحتفاظ بآخر 500
        if len(self.errors_log) > 500:
            self.errors_log = self.errors_log[-500:]

        logger.warning(f"🔴 Error logged: {error_type} - {error_message[:50]}")

    def suggest_improvements(self) -> List[str]:
        """
        اقتراح تحسينات بناءً على التأمل

        Returns:
            قائمة بالتحسينات المقترحة
        """
        suggestions = []

        # التحليل الذاتي
        assessment = self.reflect_on_performance()

        # اقتراحات بناءً على نقاط الضعف
        for weakness in assessment["weaknesses"]:
            if "دقة منخفضة" in weakness:
                suggestions.append("💡 زيادة البيانات التدريبية للنماذج")
                suggestions.append("💡 إعادة تدريب النماذج بشكل دوري")

            if "خطأ متكرر" in weakness:
                suggestions.append("💡 إضافة معالجة أخطاء أفضل")
                suggestions.append("💡 مراجعة المنطق في الكود")

        # اقتراحات عامة
        if assessment["overall_score"] < 0.8:
            suggestions.append("💡 مراجعة شاملة للنظام")

        return suggestions

    def plan_self_improvement(self) -> dict:
        """
        خطة التحسين الذاتي

        Returns:
            خطة عمل للتحسين
        """
        suggestions: list[str] = self.suggest_improvements()

        plan = {
            "timestamp": datetime.now().isoformat(),
            "current_performance": self.self_assessment.get("overall_score", 0),
            "target_performance": 0.95,
            "improvements": suggestions,
            "action_items": [],
        }

        # تحويل الاقتراحات لإجراءات
        for suggestion in suggestions:
            plan["action_items"].append(
                {
                    "action": suggestion,
                    "priority": "high",
                    "estimated_time": "1-2 أيام",
                    "status": "pending",
                }
            )

        return plan

    def celebrate_success(self, achievement: str) -> None:
        """
        الاحتفال بالإنجازات

        تعزيز إيجابي للتعلم
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "achievement": achievement,
            "type": "success",
        }

        self.improvements_log.append(entry)

        logger.info(f"🎉 Achievement unlocked: {achievement}")

    def learn_from_mistake(self, mistake: str, lesson: str) -> None:
        """
        التعلم من الأخطاء

        "الفشل معلم عظيم"
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "mistake": mistake,
            "lesson": lesson,
            "type": "learning",
        }

        self.improvements_log.append(entry)

        logger.info(f"📚 Learned from mistake: {lesson[:50]}")


# ============================================================================
# Singleton
# ============================================================================

_reflection_engine_instance = None


def get_reflection_engine():
    """الحصول على محرك التأمل"""
    global _reflection_engine_instance
    if _reflection_engine_instance is None:
        _reflection_engine_instance = SelfReflectionEngine()
    return _reflection_engine_instance
