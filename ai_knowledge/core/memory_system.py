"""
🧠 نظام الذاكرة طويلة المدى - Long-term Memory System
ذاكرة متقدمة على طريقة ChatGPT

القدرات:
- تذكر المحادثات السابقة
- تذكر تفضيلات المستخدمين
- تذكر السياق طويل المدى
- الربط بين المعلومات
- الاسترجاع الذكي
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    نظام الذاكرة طويلة المدى

    أنواع الذاكرة:
    1. Episodic Memory (ذاكرة الأحداث) - المحادثات
    2. Semantic Memory (ذاكرة المعاني) - المعرفة العامة
    3. Procedural Memory (ذاكرة الإجراءات) - كيف تفعل الأشياء
    4. User Preferences (تفضيلات المستخدمين)
    """

    def __init__(self):
        from ai_knowledge import get_knowledge_path

        self.memory_dir = get_knowledge_path("memory")
        self.ensure_memory_dir()

        # أنواع الذاكرة
        self.episodic_memory = self._load_memory("episodic")  # المحادثات
        self.semantic_memory = self._load_memory("semantic")  # المعرفة
        self.procedural_memory = self._load_memory("procedural")  # الإجراءات
        self.user_preferences = self._load_memory("preferences")  # التفضيلات

        # فهرس للبحث السريع
        self.memory_index = defaultdict(list)
        self._build_index()

    def ensure_memory_dir(self):
        """التأكد من وجود مجلد الذاكرة"""
        if not os.path.exists(self.memory_dir):
            os.makedirs(self.memory_dir)

    def _load_memory(self, memory_type):
        """تحميل نوع محدد من الذاكرة"""
        file_path = os.path.join(self.memory_dir, f"{memory_type}_memory.json")
        default = {} if memory_type == "preferences" else {"memories": []}

        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if memory_type != "preferences" and not isinstance(
                    data.get("memories"), list
                ):
                    return default
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Could not load %s memory: %s", memory_type, exc)
        return default

    def _save_memory(self, memory_type, data):
        """حفظ الذاكرة"""
        file_path = os.path.join(self.memory_dir, f"{memory_type}_memory.json")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save {memory_type} memory: {e}")
            return False

    def remember_conversation(self, user_id, message, response, context=None):
        """
        تذكر محادثة (Episodic Memory)

        يحفظ:
        - من قال ماذا
        - متى
        - السياق
        - النتيجة
        """
        memory_entry = {
            "id": len(self.episodic_memory["memories"]) + 1,
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "user_message": message,
            "assistant_response": response,
            "context": context or {},
            "type": "conversation",
        }

        self.episodic_memory["memories"].append(memory_entry)

        # الاحتفاظ بآخر 1000 محادثة فقط
        if len(self.episodic_memory["memories"]) > 1000:
            self.episodic_memory["memories"] = self.episodic_memory["memories"][-1000:]

        # حفظ
        self._save_memory("episodic", self.episodic_memory)

        # تحديث الفهرس
        self._add_to_index(message, memory_entry["id"], "episodic")

        logger.info(f"💭 Remembered conversation for user {user_id}")

    def remember_fact(self, fact, category, source=None):
        """
        تذكر معلومة (Semantic Memory)

        معلومات عامة مثل:
        - "ضريبة القيمة المضافة في الإمارات 5%"
        - "قطعة X تتوافق مع محرك Y"
        """
        memory_entry = {
            "id": len(self.semantic_memory["memories"]) + 1,
            "timestamp": datetime.now().isoformat(),
            "fact": fact,
            "category": category,
            "source": source,
            "type": "fact",
        }

        self.semantic_memory["memories"].append(memory_entry)
        self._save_memory("semantic", self.semantic_memory)

        self._add_to_index(fact, memory_entry["id"], "semantic")

        logger.info(f"📚 Remembered fact: {fact[:50]}...")

    def remember_procedure(self, procedure_name, steps, category="general"):
        """
        تذكر إجراء (Procedural Memory)

        كيفية فعل الأشياء:
        - "كيف تنشئ فاتورة"
        - "كيف تصلح محرك"
        """
        memory_entry = {
            "id": len(self.procedural_memory["memories"]) + 1,
            "timestamp": datetime.now().isoformat(),
            "procedure": procedure_name,
            "steps": steps,
            "category": category,
            "type": "procedure",
        }

        self.procedural_memory["memories"].append(memory_entry)
        self._save_memory("procedural", self.procedural_memory)

        self._add_to_index(procedure_name, memory_entry["id"], "procedural")

        logger.info(f"📋 Remembered procedure: {procedure_name}")

    def remember_user_preference(self, user_id, preference_key, preference_value):
        """
        تذكر تفضيل مستخدم

        مثل:
        - اللغة المفضلة
        - اللهجة المفضلة
        - أسلوب الرد
        - المواضيع المهتم بها
        """
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {
                "user_id": user_id,
                "preferences": {},
                "created": datetime.now().isoformat(),
            }

        self.user_preferences[user_id]["preferences"][preference_key] = preference_value
        self.user_preferences[user_id]["updated"] = datetime.now().isoformat()

        self._save_memory("preferences", self.user_preferences)

        logger.info(f"⚙️ Remembered preference for user {user_id}: {preference_key}")

    def recall_conversations(self, user_id, limit=10):
        """
        استرجاع المحادثات السابقة مع مستخدم

        للحفاظ على السياق في المحادثات الطويلة
        """
        user_conversations = [
            mem
            for mem in self.episodic_memory["memories"]
            if mem.get("user_id") == user_id
        ]

        # الأحدث أولاً
        user_conversations.reverse()

        return user_conversations[:limit]

    def recall_similar_conversations(self, query, limit=5):
        """
        استرجاع محادثات مشابهة

        للتعلم من التجارب السابقة
        """
        # بحث بسيط في الكلمات المفتاحية
        query_lower = query.lower()
        query_words = set(query_lower.split())

        similar = []

        for memory in self.episodic_memory["memories"]:
            message = memory.get("user_message", "").lower()
            message_words = set(message.split())

            # حساب التشابه (Jaccard similarity)
            intersection = query_words & message_words
            union = query_words | message_words

            similarity = len(intersection) / len(union) if union else 0

            if similarity > 0.2:  # عتبة التشابه
                similar.append({"memory": memory, "similarity": similarity})

        # الترتيب حسب التشابه
        similar.sort(key=lambda x: x["similarity"], reverse=True)

        return [s["memory"] for s in similar[:limit]]

    def recall_fact(self, query, category=None):
        """
        استرجاع معلومة محفوظة
        """
        relevant_facts = []

        query_lower = query.lower()

        for memory in self.semantic_memory["memories"]:
            if category and memory.get("category") != category:
                continue

            fact = memory.get("fact", "").lower()

            if any(word in fact for word in query_lower.split()):
                relevant_facts.append(memory)

        return relevant_facts

    def recall_procedure(self, procedure_name):
        """
        استرجاع إجراء محفوظ

        "كيف أفعل X؟"
        """
        procedure_name_lower = procedure_name.lower()

        for memory in self.procedural_memory["memories"]:
            if procedure_name_lower in memory.get("procedure", "").lower():
                return memory

        return None

    def get_user_preferences(self, user_id):
        """الحصول على تفضيلات مستخدم"""
        return self.user_preferences.get(user_id, {}).get("preferences", {})

    def _build_index(self):
        """بناء فهرس للبحث السريع"""
        # فهرسة المحادثات
        for idx, memory in enumerate(self.episodic_memory["memories"]):
            message = memory.get("user_message", "")
            for word in message.lower().split():
                if len(word) > 3:  # تجاهل الكلمات القصيرة
                    self.memory_index[word].append(("episodic", idx))

        # فهرسة المعلومات
        for idx, memory in enumerate(self.semantic_memory["memories"]):
            fact = memory.get("fact", "")
            for word in fact.lower().split():
                if len(word) > 3:
                    self.memory_index[word].append(("semantic", idx))

    def _add_to_index(self, text, memory_id, memory_type):
        """إضافة إلى الفهرس"""
        for word in text.lower().split():
            if len(word) > 3:
                self.memory_index[word].append((memory_type, memory_id))

    def search_memory(self, query, limit=10):
        """
        بحث شامل في جميع أنواع الذاكرة

        Returns:
            {
                'conversations': [...],
                'facts': [...],
                'procedures': [...]
            }
        """
        results = {"conversations": [], "facts": [], "procedures": []}

        # البحث في المحادثات
        results["conversations"] = self.recall_similar_conversations(query, limit)

        # البحث في المعلومات
        results["facts"] = self.recall_fact(query)[:limit]

        # البحث في الإجراءات
        for memory in self.procedural_memory["memories"]:
            if query.lower() in memory.get("procedure", "").lower():
                results["procedures"].append(memory)

        results["procedures"] = results["procedures"][:limit]

        return results

    def forget_old_memories(self, days=365):
        """
        نسيان الذاكرة القديمة جداً

        للحفاظ على الأداء
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.isoformat()

        # تنظيف المحادثات القديمة
        original_count = len(self.episodic_memory["memories"])
        self.episodic_memory["memories"] = [
            mem
            for mem in self.episodic_memory["memories"]
            if mem.get("timestamp", "") > cutoff_str
        ]

        deleted = original_count - len(self.episodic_memory["memories"])

        if deleted > 0:
            self._save_memory("episodic", self.episodic_memory)
            logger.info(f"🗑️ Forgot {deleted} old conversations (>{days} days)")

        return {"deleted": deleted, "remaining": len(self.episodic_memory["memories"])}

    def consolidate_memories(self):
        """
        دمج الذاكرة المتشابهة

        للحفاظ على الكفاءة
        """
        # تجميع المحادثات المتشابهة
        # (يمكن تطويره لاحقاً باستخدام ML)

    def get_memory_stats(self):
        """إحصائيات الذاكرة"""
        return {
            "episodic": {
                "count": len(self.episodic_memory["memories"]),
                "oldest": (
                    self.episodic_memory["memories"][0]["timestamp"]
                    if self.episodic_memory["memories"]
                    else None
                ),
                "newest": (
                    self.episodic_memory["memories"][-1]["timestamp"]
                    if self.episodic_memory["memories"]
                    else None
                ),
            },
            "semantic": {"count": len(self.semantic_memory["memories"])},
            "procedural": {"count": len(self.procedural_memory["memories"])},
            "user_preferences": {"users_count": len(self.user_preferences)},
            "total_memories": (
                len(self.episodic_memory["memories"])
                + len(self.semantic_memory["memories"])
                + len(self.procedural_memory["memories"])
            ),
        }


# ============================================================================
# Singleton
# ============================================================================

_memory_instance = None


def get_memory_system():
    """الحصول على نظام الذاكرة"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = LongTermMemory()
    return _memory_instance
