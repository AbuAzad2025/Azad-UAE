"""
📚 نظام التعلم من المصادر الخارجية - External Learning System
التعلم الذاتي من مكتبات ومصادر ضخمة

المصادر:
- Wikipedia (موسوعة)
- ArXiv (أبحاث علمية)
- GitHub (أكواد مفتوحة)
- Stack Overflow (حلول برمجية)
- YouTube (دروس فيديو)
- مواقع متخصصة في السيارات
- مواقع محاسبية
- قواعد بيانات ضرائب

شركة أزاد للأنظمة الذكية
"""

import logging
import json
from datetime import datetime
from typing import List
import os

logger = logging.getLogger(__name__)


class ExternalLearningSystem:
    """
    نظام التعلم من المصادر الخارجية

    يتعلم ذاتياً من:
    - مكتبات ضخمة
    - مواقع متخصصة
    - أبحاث علمية
    - مجتمعات برمجية
    """

    def __init__(self):
        self.learning_sources = self._initialize_sources()
        self.learned_data = self._load_learned_data()
        self.learning_log = []

        logger.info(
            "📚 External Learning System initialized with massive knowledge sources"
        )

    def _initialize_sources(self) -> dict:
        """تهيئة مصادر التعلم الضخمة"""
        return {
            # ========== موسوعات ومراجع عامة ==========
            "encyclopedias": {
                "wikipedia": {
                    "url": "https://ar.wikipedia.org",
                    "api": "https://ar.wikipedia.org/w/api.php",
                    "topics": [
                        "محاسبة",
                        "ضرائب",
                        "إدارة",
                        "مالية",
                        "هندسة",
                        "سيارات",
                        "إلكترونيات",
                    ],
                    "auto_learning": True,
                },
                "britannica": {
                    "url": "https://www.britannica.com",
                    "topics": ["accounting", "finance", "management", "engineering"],
                },
            },
            # ========== السيارات والميكانيكا ==========
            "automotive": {
                "mitchell1": {
                    "name": "Mitchell1 ProDemand",
                    "description": "قاعدة بيانات إصلاح السيارات الأضخم",
                    "content": [
                        "مخططات كهربائية",
                        "إجراءات الإصلاح",
                        "جداول الصيانة",
                        "TSB (نشرات فنية)",
                        "OBD-II Codes",
                        "مواصفات القطع",
                    ],
                },
                "alldata": {
                    "name": "ALLDATA",
                    "description": "معلومات فنية شاملة",
                    "coverage": "38,000+ نموذج سيارة",
                },
                "identifix": {
                    "name": "Identifix",
                    "description": "حلول الأعطال المباشرة",
                    "feature": "Real Fix - حلول من ميكانيكيين حقيقيين",
                },
                "obd_codes": {
                    "name": "OBD-Codes.com",
                    "url": "https://www.obd-codes.com",
                    "description": "قاعدة بيانات DTC codes كاملة",
                    "codes": "5,000+ كود",
                },
                "youtube_channels": {
                    "ScannerDanner": "تشخيص متقدم بالأوسلسكوب",
                    "ChrisFix": "إصلاحات DIY بالتفصيل",
                    "Engineering Explained": "شرح تقني عميق",
                    "South Main Auto": "تشخيص احترافي",
                },
            },
            # ========== المحاسبة والمالية ==========
            "accounting_finance": {
                "ifrs": {
                    "name": "IFRS Foundation",
                    "url": "https://www.ifrs.org",
                    "description": "المعايير الدولية للتقارير المالية",
                    "standards": "IFRS 1-17",
                    "topics": [
                        "Revenue Recognition (IFRS 15)",
                        "Leases (IFRS 16)",
                        "Financial Instruments (IFRS 9)",
                    ],
                },
                "gaap": {
                    "name": "US GAAP",
                    "description": "المبادئ المحاسبية الأمريكية",
                    "source": "FASB (مجلس معايير المحاسبة المالية)",
                },
                "aicpa": {
                    "name": "AICPA",
                    "url": "https://www.aicpa.org",
                    "description": "المعهد الأمريكي للمحاسبين القانونيين",
                    "resources": ["أدلة تدقيق", "معايير مهنية"],
                },
                "investopedia": {
                    "url": "https://www.investopedia.com",
                    "description": "موسوعة مالية شاملة",
                    "topics": [
                        "Financial Ratios",
                        "Investment Analysis",
                        "Corporate Finance",
                        "Accounting Principles",
                    ],
                },
            },
            # ========== الضرائب ==========
            "taxation": {
                "uae_fta": {
                    "name": "الهيئة الاتحادية للضرائب",
                    "url": "https://tax.gov.ae",
                    "description": "المصدر الرسمي للضرائب في الإمارات",
                    "content": [
                        "أدلة VAT",
                        "القرارات الوزارية",
                        "الأسئلة الشائعة",
                        "نماذج التسجيل",
                    ],
                },
                "gcc_vat": {
                    "name": "الاتفاقية الموحدة لضريبة القيمة المضافة لدول مجلس التعاون",
                    "countries": [
                        "الإمارات",
                        "السعودية",
                        "البحرين",
                        "عمان",
                        "قطر",
                        "الكويت",
                    ],
                    "rate": "5% (معظم الدول)",
                },
                "kpmg_tax": {
                    "name": "KPMG Tax",
                    "url": "https://home.kpmg/xx/en/home/services/tax.html",
                    "description": "أبحاث ضريبية عالمية",
                },
            },
            # ========== البرمجة والتقنية ==========
            "programming": {
                "github": {
                    "url": "https://github.com",
                    "description": "أكبر مستودع أكواد مفتوحة",
                    "repositories": {
                        "flask": "https://github.com/pallets/flask",
                        "sqlalchemy": "https://github.com/sqlalchemy/sqlalchemy",
                        "scikit-learn": "https://github.com/scikit-learn/scikit-learn",
                        "transformers": "https://github.com/huggingface/transformers",
                    },
                },
                "stackoverflow": {
                    "url": "https://stackoverflow.com",
                    "description": "50+ مليون سؤال وجواب برمجي",
                    "tags": ["python", "sql", "flask", "machine-learning"],
                },
                "arxiv": {
                    "url": "https://arxiv.org",
                    "description": "أبحاث علمية في AI/ML",
                    "categories": [
                        "cs.AI (Artificial Intelligence)",
                        "cs.LG (Machine Learning)",
                        "cs.CL (Computational Linguistics)",
                    ],
                },
                "papers_with_code": {
                    "url": "https://paperswithcode.com",
                    "description": "أبحاث مع تطبيقات عملية",
                },
            },
            # ========== AI/ML ==========
            "ai_ml": {
                "huggingface": {
                    "url": "https://huggingface.co",
                    "description": "أضخم مكتبة نماذج AI",
                    "models": "200,000+ نموذج مدرب",
                    "datasets": "30,000+ dataset",
                    "spaces": "تطبيقات AI جاهزة",
                },
                "openai_docs": {
                    "url": "https://platform.openai.com/docs",
                    "description": "توثيق OpenAI",
                    "models": ["GPT-4", "GPT-3.5", "DALL-E"],
                },
                "anthropic": {
                    "url": "https://www.anthropic.com",
                    "description": "توثيق Claude AI",
                },
                "google_ai": {
                    "url": "https://ai.google",
                    "description": "Google AI - Gemini, BERT, T5",
                },
            },
            # ========== قواعد بيانات متخصصة ==========
            "databases": {
                "automotive_databases": {
                    "carmd": "CarMD - أكواد الأعطال",
                    "autozone": "AutoZone Repair Guides",
                    "rockauto": "RockAuto - كتالوج قطع",
                    "epc": "Electronic Parts Catalog - كتالوجات المصانع",
                },
                "accounting_databases": {
                    "fasb_codification": "FASB Accounting Standards Codification",
                    "sec_edgar": "SEC EDGAR - تقارير الشركات",
                    "bloomberg": "Bloomberg Terminal - بيانات مالية",
                },
                "tax_databases": {
                    "tax_foundation": "Tax Foundation",
                    "oecd_tax": "OECD Tax Database",
                    "gcc_tax": "GCC Tax Authorities",
                },
            },
            # ========== كورسات ودورات ==========
            "courses": {
                "coursera": {
                    "url": "https://www.coursera.org",
                    "courses": [
                        "Machine Learning by Andrew Ng",
                        "Deep Learning Specialization",
                        "Financial Accounting",
                        "Corporate Finance",
                    ],
                },
                "udemy": {
                    "url": "https://www.udemy.com",
                    "categories": ["AI/ML", "Accounting", "Automotive"],
                },
                "edx": {
                    "url": "https://www.edx.org",
                    "universities": ["MIT", "Harvard", "Berkeley"],
                },
            },
            # ========== مجتمعات ومنتديات ==========
            "communities": {
                "reddit": {
                    "subreddits": [
                        "r/MachineLearning",
                        "r/accounting",
                        "r/mechanicadvice",
                        "r/Justrolledintotheshop",
                        "r/CarHacking",
                        "r/askcarguys",
                    ]
                },
                "forums": {
                    "bimmerfest": "BMW",
                    "fordforums": "Ford",
                    "toyotanation": "Toyota",
                    "accounting_coach": "محاسبة",
                },
            },
        }

    def _load_learned_data(self) -> dict:
        """تحميل البيانات المتعلمة"""
        from ai_knowledge import get_knowledge_path

        learned_file = get_knowledge_path("external_learned_data.json")

        if os.path.exists(learned_file):
            try:
                with open(learned_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Could not load external learned data: %s", exc)

        return {
            "articles": [],
            "code_snippets": [],
            "solutions": [],
            "tutorials": [],
            "research_papers": [],
            "metadata": {"created": datetime.now().isoformat(), "total_learned": 0},
        }

    def learn_from_source(self, source_type: str, topic: str, content: str) -> dict:
        """
        التعلم من مصدر خارجي

        Args:
            source_type: نوع المصدر (wikipedia, stackoverflow, etc)
            topic: الموضوع
            content: المحتوى

        Returns:
            {success: bool, learned_items: int}
        """
        try:
            # استخراج المعلومات المهمة
            extracted = self._extract_knowledge(content, topic)

            # حفظ في قاعدة المعرفة
            if source_type == "wikipedia":
                self.learned_data["articles"].append(
                    {
                        "topic": topic,
                        "content": extracted,
                        "source": "wikipedia",
                        "learned_at": datetime.now().isoformat(),
                    }
                )

            elif source_type == "stackoverflow":
                self.learned_data["solutions"].append(
                    {
                        "problem": topic,
                        "solution": extracted,
                        "source": "stackoverflow",
                        "learned_at": datetime.now().isoformat(),
                    }
                )

            elif source_type == "github":
                self.learned_data["code_snippets"].append(
                    {
                        "topic": topic,
                        "code": extracted,
                        "source": "github",
                        "learned_at": datetime.now().isoformat(),
                    }
                )

            # حفظ
            self._save_learned_data()

            # تسجيل
            self.learning_log.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "source": source_type,
                    "topic": topic,
                    "success": True,
                }
            )

            logger.info(f"📚 Learned from {source_type}: {topic}")

            return {"success": True, "learned_items": 1}

        except Exception as e:
            logger.error(f"Learning failed: {e}")
            return {"success": False, "error": str(e)}

    def _extract_knowledge(self, content: str, _topic: str) -> str:
        """استخراج المعرفة المهمة من المحتوى"""
        # استخراج ذكي (يمكن تطويره)
        # للآن، نأخذ أول 500 حرف
        return content[:500] if len(content) > 500 else content

    def _save_learned_data(self):
        """حفظ البيانات المتعلمة"""
        from ai_knowledge import get_knowledge_path

        learned_file = get_knowledge_path("external_learned_data.json")

        try:
            self.learned_data["metadata"]["total_learned"] = (
                len(self.learned_data["articles"])
                + len(self.learned_data["solutions"])
                + len(self.learned_data["code_snippets"])
                + len(self.learned_data["tutorials"])
                + len(self.learned_data["research_papers"])
            )
            self.learned_data["metadata"]["last_updated"] = datetime.now().isoformat()

            with open(learned_file, "w", encoding="utf-8") as f:
                json.dump(self.learned_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Failed to save learned data: {e}")

    def get_knowledge_sources_list(self) -> List[dict]:
        """الحصول على قائمة المصادر المتاحة"""
        sources_list = []

        for category, sources in self.learning_sources.items():
            for source_name, source_data in sources.items():
                if isinstance(source_data, dict):
                    sources_list.append(
                        {
                            "category": category,
                            "name": source_name,
                            "description": source_data.get(
                                "description", source_data.get("name", "")
                            ),
                            "url": source_data.get("url", ""),
                            "auto_learning": source_data.get("auto_learning", False),
                        }
                    )

        return sources_list

    def get_automotive_resources(self) -> dict:
        """الحصول على موارد السيارات"""
        return self.learning_sources.get("automotive", {})

    def get_accounting_resources(self) -> dict:
        """الحصول على موارد المحاسبة"""
        return self.learning_sources.get("accounting_finance", {})

    def get_statistics(self) -> dict:
        """إحصائيات التعلم"""
        return {
            "total_sources": len(self.get_knowledge_sources_list()),
            "learned_articles": len(self.learned_data["articles"]),
            "learned_solutions": len(self.learned_data["solutions"]),
            "learned_code": len(self.learned_data["code_snippets"]),
            "total_learned": self.learned_data["metadata"].get("total_learned", 0),
            "last_updated": self.learned_data["metadata"].get("last_updated", "Never"),
        }


# ============================================================================
# قاموس المصادر الجاهز للعرض
# ============================================================================

LEARNING_SOURCES_CATALOG = """
📚 كتالوج مصادر التعلم الضخمة

═══════════════════════════════════════════════════════════════

🚗 **السيارات والميكانيكا:**

1. Mitchell1 ProDemand
   └─ قاعدة البيانات الأضخم للإصلاح
   └─ 38,000+ نموذج سيارة
   └─ مخططات كهربائية كاملة

2. ALLDATA
   └─ معلومات فنية شاملة
   └─ TSB نشرات فنية
   └─ OBD-II Codes

3. Identifix Real Fix
   └─ حلول حقيقية من ميكانيكيين
   └─ أعطال شائعة وحلولها

4. OBD-Codes.com
   └─ 5,000+ DTC code
   └─ شرح تفصيلي لكل كود

5. قنوات يوتيوب:
   └─ ScannerDanner (تشخيص متقدم)
   └─ ChrisFix (إصلاحات DIY)
   └─ Engineering Explained (شرح تقني)

═══════════════════════════════════════════════════════════════

📊 **المحاسبة والمالية:**

1. IFRS Foundation
   └─ المعايير الدولية
   └─ IFRS 1-17

2. US GAAP
   └─ المبادئ الأمريكية
   └─ FASB Standards

3. AICPA
   └─ المعهد الأمريكي للمحاسبين
   └─ أدلة التدقيق

4. Investopedia
   └─ موسوعة مالية شاملة
   └─ شرح مبسط لكل شيء

═══════════════════════════════════════════════════════════════

💰 **الضرائب:**

1. الهيئة الاتحادية للضرائب (UAE)
   └─ tax.gov.ae
   └─ المصدر الرسمي

2. GCC VAT Agreement
   └─ الاتفاقية الموحدة
   └─ 6 دول خليجية

3. KPMG Tax
   └─ أبحاث ضريبية عالمية

═══════════════════════════════════════════════════════════════

💻 **البرمجة و AI:**

1. GitHub
   └─ 200+ مليون repository
   └─ أكواد مفتوحة لكل شيء

2. Stack Overflow
   └─ 50+ مليون سؤال وجواب

3. ArXiv
   └─ أبحاث AI/ML علمية

4. HuggingFace
   └─ 200,000+ نموذج AI مدرب
   └─ 30,000+ dataset

═══════════════════════════════════════════════════════════════

📖 **كورسات ودورات:**

1. Coursera
   └─ جامعات عالمية
   └─ Machine Learning by Andrew Ng

2. Udemy
   └─ 200,000+ دورة

3. edX
   └─ MIT + Harvard + Berkeley

═══════════════════════════════════════════════════════════════

المجموع: 30+ مصدر ضخم للتعلم الذاتي!

"""


# ============================================================================
# Singleton
# ============================================================================

_external_learning_instance = None


def get_external_learning():
    """الحصول على نظام التعلم الخارجي"""
    global _external_learning_instance
    if _external_learning_instance is None:
        _external_learning_instance = ExternalLearningSystem()
    return _external_learning_instance
