"""
Consolidated module: learning_engine.py
Merged: learning/quick_learner.py, learning/auto_retraining.py, learning/continuous_learner.py, learning/external_learning.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: learning/quick_learner.py =====
"""
QuickLearner - delegates to DB-backed learning/quick_learner.py
"""
import logging

logger = logging.getLogger(__name__)

class QuickLearner:
    """Delegates DB operations to the AiMemory-backed version in learning/quick_learner.py."""

    _klass = None

    def _impl(self):
        if QuickLearner._klass is None:
            from ai_knowledge.learning.quick_learner import QuickLearner as _QL
            QuickLearner._klass = _QL
        return QuickLearner._klass()

    def learn(self, question: str, answer: str, category: str = 'general',
              tenant_id: int = None):
        return self._impl().learn(question, answer, category, tenant_id)

    def get_answer(self, question: str, tenant_id: int = None):
        return self._impl().get_answer(question, tenant_id)

    def save_knowledge(self):
        pass  # DB-backed — no-op

    @property
    def knowledge_base(self):
        return self._impl().knowledge_base

# Singleton
quick_learner = QuickLearner()


# ===== Consolidated from: learning/auto_retraining.py =====
from datetime import datetime, timedelta
import logging
import json
import os

logger = logging.getLogger(__name__)


class AutoRetrainingScheduler:
    
    from ai_knowledge import get_knowledge_path
    TRAINING_LOG_FILE = get_knowledge_path('training_history.json')
    
    @staticmethod
    def should_retrain() -> bool:
        from models import Sale
        from extensions import db
        
        current_count = Sale.query.filter_by(status='confirmed').count()
        
        last_training = AutoRetrainingScheduler.get_last_training_info()
        if not last_training:
            return current_count >= 100
        
        last_count = last_training.get('sales_count', 0)
        last_date = datetime.fromisoformat(last_training.get('timestamp', '2020-01-01'))
        
        days_since = (datetime.now() - last_date).days
        
        if current_count >= last_count + 100:
            return True
        
        if days_since >= 7 and current_count >= last_count + 50:
            return True
        
        return False
    
    @staticmethod
    def trigger_retraining():
        from models import Sale
        
        try:
            logger.info("🧠 Auto-retraining triggered...")
            
            from ai_knowledge.neural.neural_engine import get_neural_engine
            neural = get_neural_engine()
            
            results = neural.train_all_models()
            
            sales_count = Sale.query.filter_by(status='confirmed').count()
            AutoRetrainingScheduler.log_training(sales_count, results)
            
            logger.info(f"✅ Auto-retraining completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"❌ Auto-retraining failed: {e}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_last_training_info():
        try:
            if os.path.exists(AutoRetrainingScheduler.TRAINING_LOG_FILE):
                with open(AutoRetrainingScheduler.TRAINING_LOG_FILE, 'r') as f:
                    history = json.load(f)
                    if history:
                        return history[-1]
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug('Could not load training log: %s', exc)
        return None
    
    @staticmethod
    def log_training(sales_count: int, results: dict):
        try:
            history = []
            if os.path.exists(AutoRetrainingScheduler.TRAINING_LOG_FILE):
                with open(AutoRetrainingScheduler.TRAINING_LOG_FILE, 'r') as f:
                    history = json.load(f)
            
            history.append({
                'timestamp': datetime.now().isoformat(),
                'sales_count': sales_count,
                'results': results
            })
            
            history = history[-20:]
            
            with open(AutoRetrainingScheduler.TRAINING_LOG_FILE, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to log training: {e}")
    
    @staticmethod
    def check_and_train_if_needed():
        if AutoRetrainingScheduler.should_retrain():
            logger.info("📊 Training threshold reached - initiating auto-retraining")
            return AutoRetrainingScheduler.trigger_retraining()
        return {'message': 'No retraining needed'}


# إنشاء instance عام
auto_retraining = AutoRetrainingScheduler()



# ===== Consolidated from: learning/continuous_learner.py =====
"""
🎓 نظام التعلم المستمر - Continuous Learning System
التعلم الذاتي المستمر من المصادر الخارجية

الميزات:
- التعلم في الخلفية (Background Learning)
- جدولة التعلم اليومية
- تحديث المعرفة تلقائياً
- التكيف المستمر
- التعلم من الأخطاء

شركة أزاد للأنظمة الذكية
"""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import quote

logger = logging.getLogger(__name__)


class ContinuousLearner:
    """
    نظام التعلم المستمر
    
    يتعلم تلقائياً كل يوم من مصادر متعددة
    """
    
    def __init__(self):
        from ai_knowledge import get_knowledge_path
        self.knowledge_dir = get_knowledge_path('learned_knowledge')
        self.ensure_knowledge_dir()
        
        # إعدادات الطلبات
        self.session = self._create_session()
        
        # سجل التعلم
        self.learning_history = self._load_history()
        
        # المعرفة المتراكمة
        self.accumulated_knowledge = {
            'wikipedia': {},
            'obd_codes': {},
            'github': {},
            'arxiv': {},
            'stackoverflow': {},
            'total_items': 0
        }
        
        logger.info("🎓 Continuous Learner initialized")
    
    def ensure_knowledge_dir(self):
        """التأكد من وجود مجلد المعرفة"""
        if not os.path.exists(self.knowledge_dir):
            os.makedirs(self.knowledge_dir)
    
    def _create_session(self):
        """إنشاء session مع إعادة محاولة تلقائية"""
        session = requests.Session()
        
        # استراتيجية إعادة المحاولة
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # Headers
        session.headers.update({
            'User-Agent': 'AzadAI/3.0 (Educational Purpose; +https://azad-systems.com)'
        })
        
        return session
    
    def _load_history(self) -> List[dict]:
        """تحميل سجل التعلم"""
        history_file = os.path.join(self.knowledge_dir, 'learning_history.json')
        
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug('Could not load learning history: %s', exc)
        
        return []
    
    def _save_history(self):
        """حفظ سجل التعلم"""
        history_file = os.path.join(self.knowledge_dir, 'learning_history.json')
        
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(self.learning_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    def learn_from_wikipedia(self, topic: str, lang: str = 'ar') -> dict:
        """
        التعلم من Wikipedia
        
        Args:
            topic: الموضوع
            lang: اللغة (ar أو en)
        
        Returns:
            {success: bool, content: str}
        """
        try:
            topic_encoded = quote(topic.replace(' ', '_'), safe='')
            url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{topic_encoded}"
            
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                extract = data.get('extract', '')
                
                if extract:
                    # حفظ
                    self.accumulated_knowledge['wikipedia'][topic] = {
                        'content': extract,
                        'url': data.get('content_urls', {}).get('desktop', {}).get('page', ''),
                        'learned_at': datetime.now().isoformat(),
                        'lang': lang
                    }
                    
                    self.accumulated_knowledge['total_items'] += 1
                    
                    # تسجيل النجاح
                    self.learning_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'source': 'wikipedia',
                        'topic': topic,
                        'lang': lang,
                        'status': 'success',
                        'size': len(extract)
                    })
                    
                    self._save_history()
                    
                    logger.info(f"📚 Learned from Wikipedia: {topic} ({len(extract)} chars)")
                    
                    return {'success': True, 'content': extract, 'size': len(extract)}
            
            return {'success': False, 'error': f'Status {response.status_code}'}
        
        except Exception as e:
            logger.error(f"Wikipedia learning failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def learn_arxiv_papers(self, query: str, max_results: int = 5) -> dict:
        """
        التعلم من أبحاث ArXiv
        
        Args:
            query: استعلام البحث
            max_results: عدد الأبحاث
        
        Returns:
            {success: bool, papers: int}
        """
        try:
            url = f"http://export.arxiv.org/api/query"
            params = {
                'search_query': f'all:{query}',
                'max_results': max_results
            }
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                # عد الأبحاث
                papers_count = response.text.count('<entry>')
                
                if papers_count > 0:
                    # حفظ
                    if query not in self.accumulated_knowledge['arxiv']:
                        self.accumulated_knowledge['arxiv'][query] = []
                    
                    self.accumulated_knowledge['arxiv'][query].append({
                        'papers_count': papers_count,
                        'learned_at': datetime.now().isoformat()
                    })
                    
                    self.accumulated_knowledge['total_items'] += papers_count
                    
                    logger.info(f"📄 Learned from ArXiv: {query} ({papers_count} papers)")
                    
                    return {'success': True, 'papers': papers_count}
            
            return {'success': False, 'error': f'Status {response.status_code}'}
        
        except Exception as e:
            logger.error(f"ArXiv learning failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_learning_stats(self) -> dict:
        """إحصائيات التعلم"""
        return {
            'total_items_learned': self.accumulated_knowledge['total_items'],
            'wikipedia_articles': len(self.accumulated_knowledge['wikipedia']),
            'obd_codes': len(self.accumulated_knowledge['obd_codes']),
            'github_repos': len(self.accumulated_knowledge['github']),
            'arxiv_papers': sum(
                sum(item['papers_count'] for item in items if isinstance(item, dict))
                for items in self.accumulated_knowledge['arxiv'].values()
                if isinstance(items, list)
            ),
            'learning_sessions': len(self.learning_history),
            'last_learning': self.learning_history[-1]['timestamp'] if self.learning_history else 'Never'
        }
    
    def daily_learning_routine(self) -> dict:
        """
        روتين التعلم اليومي
        
        يتعلم من جميع المصادر تلقائياً
        """
        results = {
            'started_at': datetime.now().isoformat(),
            'sources_accessed': 0,
            'items_learned': 0,
            'errors': []
        }
        
        # 1. Wikipedia
        topics = ['المحاسبة المالية', 'إدارة المخزون', 'نظام مانع الانغلاق']
        for topic in topics:
            result = self.learn_from_wikipedia(topic, 'ar')
            results['sources_accessed'] += 1
            if result['success']:
                results['items_learned'] += 1
            else:
                results['errors'].append(f"Wikipedia: {topic}")
        
        # 2. ArXiv
        queries = ['machine learning', 'neural networks']
        for query in queries:
            result = self.learn_arxiv_papers(query, max_results=3)
            results['sources_accessed'] += 1
            if result['success']:
                results['items_learned'] += result.get('papers', 0)
        
        results['completed_at'] = datetime.now().isoformat()
        results['success_rate'] = f"{(results['items_learned'] / results['sources_accessed'] * 100):.1f}%" if results['sources_accessed'] > 0 else "0%"
        
        logger.info(f"🎓 Daily learning completed: {results['items_learned']} items learned")
        
        return results


# ============================================================================
# Singleton
# ============================================================================

_continuous_learner_instance = None

def get_continuous_learner():
    """الحصول على نظام التعلم المستمر"""
    global _continuous_learner_instance
    if _continuous_learner_instance is None:
        _continuous_learner_instance = ContinuousLearner()
    return _continuous_learner_instance


# =====================
# Self-test integration
# =====================

def evaluate_and_learn(qa_tests: list, ai_service=None):
    """Run QA tests, evaluate by keyword heuristics, and learn from outcomes.
    qa_tests: list of dicts: {"question": str, "expected_keywords": [str], "context": dict}
    ai_service: optional AIService-like with ask_genius and get_learning_system
    Returns: results list with success flags and scores
    """
    try:
        from services.ai_service import AIService as DefaultAI
    except ImportError:
        DefaultAI = None
    svc = ai_service or DefaultAI
    results = []
    if not svc:
        return results
    memory = None
    try:
        memory = svc.get_learning_system()
    except Exception as e:
        logger.debug(f"Cannot get learning system: {e}")
        memory = None
    for test in qa_tests:
        q = test.get("question", "").strip()
        expected = [k.lower() for k in (test.get("expected_keywords") or [])]
        context = test.get("context") or {}
        if not q:
            continue
        try:
            ans = svc.ask_genius(q, context=context)
            text = "" if ans is None else (ans.get("answer") if isinstance(ans, dict) else str(ans))
            text_l = (text or "").lower()
            hits = sum(1 for k in expected if k in text_l)
            score = 0.0 if not expected else hits / len(expected)
            success = score >= 0.6 or (hits >= 2 and len(expected) >= 3)
            results.append({
                "question": q,
                "expected": expected,
                "answer": text,
                "hits": hits,
                "score": round(score, 3),
                "success": success,
            })
            if memory:
                try:
                    memory.learn_from_interaction(
                        question=q,
                        response=text,
                        user_feedback=5 if success else 2,
                        context={"expected": expected, "score": score}
                    )
                except Exception as learn_e:
                    logger.debug(f"Feedback learn failed: {learn_e}")
        except Exception as e:
            results.append({
                "question": q,
                "expected": expected,
                "answer": f"ERROR: {e}",
                "hits": 0,
                "score": 0.0,
                "success": False,
            })
            if memory:
                try:
                    memory.learn_from_interaction(
                        question=q,
                        response=str(e),
                        user_feedback=1,
                        context={"expected": expected, "error": True}
                    )
                except Exception as inner_e:
                    logger.debug(f"Error feedback learn failed: {inner_e}")
    return results


# إنشاء instance عام
continuous_learner = ContinuousLearner()



# ===== Consolidated from: learning/external_learning.py =====
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
from typing import Dict, List, Optional
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
        
        logger.info("📚 External Learning System initialized with massive knowledge sources")
    
    def _initialize_sources(self) -> dict:
        """تهيئة مصادر التعلم الضخمة"""
        return {
            # ========== موسوعات ومراجع عامة ==========
            'encyclopedias': {
                'wikipedia': {
                    'url': 'https://ar.wikipedia.org',
                    'api': 'https://ar.wikipedia.org/w/api.php',
                    'topics': [
                        'محاسبة', 'ضرائب', 'إدارة', 'مالية',
                        'هندسة', 'سيارات', 'إلكترونيات'
                    ],
                    'auto_learning': True
                },
                'britannica': {
                    'url': 'https://www.britannica.com',
                    'topics': ['accounting', 'finance', 'management', 'engineering']
                }
            },
            
            # ========== السيارات والميكانيكا ==========
            'automotive': {
                'mitchell1': {
                    'name': 'Mitchell1 ProDemand',
                    'description': 'قاعدة بيانات إصلاح السيارات الأضخم',
                    'content': [
                        'مخططات كهربائية',
                        'إجراءات الإصلاح',
                        'جداول الصيانة',
                        'TSB (نشرات فنية)',
                        'OBD-II Codes',
                        'مواصفات القطع'
                    ]
                },
                'alldata': {
                    'name': 'ALLDATA',
                    'description': 'معلومات فنية شاملة',
                    'coverage': '38,000+ نموذج سيارة'
                },
                'identifix': {
                    'name': 'Identifix',
                    'description': 'حلول الأعطال المباشرة',
                    'feature': 'Real Fix - حلول من ميكانيكيين حقيقيين'
                },
                'obd_codes': {
                    'name': 'OBD-Codes.com',
                    'url': 'https://www.obd-codes.com',
                    'description': 'قاعدة بيانات DTC codes كاملة',
                    'codes': '5,000+ كود'
                },
                'youtube_channels': {
                    'ScannerDanner': 'تشخيص متقدم بالأوسلسكوب',
                    'ChrisFix': 'إصلاحات DIY بالتفصيل',
                    'Engineering Explained': 'شرح تقني عميق',
                    'South Main Auto': 'تشخيص احترافي'
                }
            },
            
            # ========== المحاسبة والمالية ==========
            'accounting_finance': {
                'ifrs': {
                    'name': 'IFRS Foundation',
                    'url': 'https://www.ifrs.org',
                    'description': 'المعايير الدولية للتقارير المالية',
                    'standards': 'IFRS 1-17',
                    'topics': [
                        'Revenue Recognition (IFRS 15)',
                        'Leases (IFRS 16)',
                        'Financial Instruments (IFRS 9)'
                    ]
                },
                'gaap': {
                    'name': 'US GAAP',
                    'description': 'المبادئ المحاسبية الأمريكية',
                    'source': 'FASB (مجلس معايير المحاسبة المالية)'
                },
                'aicpa': {
                    'name': 'AICPA',
                    'url': 'https://www.aicpa.org',
                    'description': 'المعهد الأمريكي للمحاسبين القانونيين',
                    'resources': ['أدلة تدقيق', 'معايير مهنية']
                },
                'investopedia': {
                    'url': 'https://www.investopedia.com',
                    'description': 'موسوعة مالية شاملة',
                    'topics': [
                        'Financial Ratios',
                        'Investment Analysis',
                        'Corporate Finance',
                        'Accounting Principles'
                    ]
                }
            },
            
            # ========== الضرائب ==========
            'taxation': {
                'uae_fta': {
                    'name': 'الهيئة الاتحادية للضرائب',
                    'url': 'https://tax.gov.ae',
                    'description': 'المصدر الرسمي للضرائب في الإمارات',
                    'content': [
                        'أدلة VAT',
                        'القرارات الوزارية',
                        'الأسئلة الشائعة',
                        'نماذج التسجيل'
                    ]
                },
                'gcc_vat': {
                    'name': 'الاتفاقية الموحدة لضريبة القيمة المضافة لدول مجلس التعاون',
                    'countries': ['الإمارات', 'السعودية', 'البحرين', 'عمان', 'قطر', 'الكويت'],
                    'rate': '5% (معظم الدول)'
                },
                'kpmg_tax': {
                    'name': 'KPMG Tax',
                    'url': 'https://home.kpmg/xx/en/home/services/tax.html',
                    'description': 'أبحاث ضريبية عالمية'
                }
            },
            
            # ========== البرمجة والتقنية ==========
            'programming': {
                'github': {
                    'url': 'https://github.com',
                    'description': 'أكبر مستودع أكواد مفتوحة',
                    'repositories': {
                        'flask': 'https://github.com/pallets/flask',
                        'sqlalchemy': 'https://github.com/sqlalchemy/sqlalchemy',
                        'scikit-learn': 'https://github.com/scikit-learn/scikit-learn',
                        'transformers': 'https://github.com/huggingface/transformers'
                    }
                },
                'stackoverflow': {
                    'url': 'https://stackoverflow.com',
                    'description': '50+ مليون سؤال وجواب برمجي',
                    'tags': ['python', 'sql', 'flask', 'machine-learning']
                },
                'arxiv': {
                    'url': 'https://arxiv.org',
                    'description': 'أبحاث علمية في AI/ML',
                    'categories': [
                        'cs.AI (Artificial Intelligence)',
                        'cs.LG (Machine Learning)',
                        'cs.CL (Computational Linguistics)'
                    ]
                },
                'papers_with_code': {
                    'url': 'https://paperswithcode.com',
                    'description': 'أبحاث مع تطبيقات عملية'
                }
            },
            
            # ========== AI/ML ==========
            'ai_ml': {
                'huggingface': {
                    'url': 'https://huggingface.co',
                    'description': 'أضخم مكتبة نماذج AI',
                    'models': '200,000+ نموذج مدرب',
                    'datasets': '30,000+ dataset',
                    'spaces': 'تطبيقات AI جاهزة'
                },
                'openai_docs': {
                    'url': 'https://platform.openai.com/docs',
                    'description': 'توثيق OpenAI',
                    'models': ['GPT-4', 'GPT-3.5', 'DALL-E']
                },
                'anthropic': {
                    'url': 'https://www.anthropic.com',
                    'description': 'توثيق Claude AI'
                },
                'google_ai': {
                    'url': 'https://ai.google',
                    'description': 'Google AI - Gemini, BERT, T5'
                }
            },
            
            # ========== قواعد بيانات متخصصة ==========
            'databases': {
                'automotive_databases': {
                    'carmd': 'CarMD - أكواد الأعطال',
                    'autozone': 'AutoZone Repair Guides',
                    'rockauto': 'RockAuto - كتالوج قطع',
                    'epc': 'Electronic Parts Catalog - كتالوجات المصانع'
                },
                'accounting_databases': {
                    'fasb_codification': 'FASB Accounting Standards Codification',
                    'sec_edgar': 'SEC EDGAR - تقارير الشركات',
                    'bloomberg': 'Bloomberg Terminal - بيانات مالية'
                },
                'tax_databases': {
                    'tax_foundation': 'Tax Foundation',
                    'oecd_tax': 'OECD Tax Database',
                    'gcc_tax': 'GCC Tax Authorities'
                }
            },
            
            # ========== كورسات ودورات ==========
            'courses': {
                'coursera': {
                    'url': 'https://www.coursera.org',
                    'courses': [
                        'Machine Learning by Andrew Ng',
                        'Deep Learning Specialization',
                        'Financial Accounting',
                        'Corporate Finance'
                    ]
                },
                'udemy': {
                    'url': 'https://www.udemy.com',
                    'categories': ['AI/ML', 'Accounting', 'Automotive']
                },
                'edx': {
                    'url': 'https://www.edx.org',
                    'universities': ['MIT', 'Harvard', 'Berkeley']
                }
            },
            
            # ========== مجتمعات ومنتديات ==========
            'communities': {
                'reddit': {
                    'subreddits': [
                        'r/MachineLearning',
                        'r/accounting',
                        'r/mechanicadvice',
                        'r/Justrolledintotheshop',
                        'r/CarHacking',
                        'r/askcarguys'
                    ]
                },
                'forums': {
                    'bimmerfest': 'BMW',
                    'fordforums': 'Ford',
                    'toyotanation': 'Toyota',
                    'accounting_coach': 'محاسبة'
                }
            }
        }
    
    def _load_learned_data(self) -> dict:
        """تحميل البيانات المتعلمة"""
        from ai_knowledge import get_knowledge_path
        learned_file = get_knowledge_path('external_learned_data.json')
        
        if os.path.exists(learned_file):
            try:
                with open(learned_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug('Could not load learning history: %s', exc)
        
        return {
            'articles': [],
            'code_snippets': [],
            'solutions': [],
            'tutorials': [],
            'research_papers': [],
            'metadata': {
                'created': datetime.now().isoformat(),
                'total_learned': 0
            }
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
            if source_type == 'wikipedia':
                self.learned_data['articles'].append({
                    'topic': topic,
                    'content': extracted,
                    'source': 'wikipedia',
                    'learned_at': datetime.now().isoformat()
                })
            
            elif source_type == 'stackoverflow':
                self.learned_data['solutions'].append({
                    'problem': topic,
                    'solution': extracted,
                    'source': 'stackoverflow',
                    'learned_at': datetime.now().isoformat()
                })
            
            elif source_type == 'github':
                self.learned_data['code_snippets'].append({
                    'topic': topic,
                    'code': extracted,
                    'source': 'github',
                    'learned_at': datetime.now().isoformat()
                })
            
            # حفظ
            self._save_learned_data()
            
            # تسجيل
            self.learning_log.append({
                'timestamp': datetime.now().isoformat(),
                'source': source_type,
                'topic': topic,
                'success': True
            })
            
            logger.info(f"📚 Learned from {source_type}: {topic}")
            
            return {'success': True, 'learned_items': 1}
        
        except Exception as e:
            logger.error(f"Learning failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _extract_knowledge(self, content: str, topic: str) -> str:
        """استخراج المعرفة المهمة من المحتوى"""
        # استخراج ذكي (يمكن تطويره)
        # للآن، نأخذ أول 500 حرف
        return content[:500] if len(content) > 500 else content
    
    def _save_learned_data(self):
        """حفظ البيانات المتعلمة"""
        from ai_knowledge import get_knowledge_path
        learned_file = get_knowledge_path('external_learned_data.json')
        
        try:
            self.learned_data['metadata']['total_learned'] = (
                len(self.learned_data['articles']) +
                len(self.learned_data['solutions']) +
                len(self.learned_data['code_snippets']) +
                len(self.learned_data['tutorials']) +
                len(self.learned_data['research_papers'])
            )
            self.learned_data['metadata']['last_updated'] = datetime.now().isoformat()
            
            with open(learned_file, 'w', encoding='utf-8') as f:
                json.dump(self.learned_data, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"Failed to save learned data: {e}")
    
    def get_knowledge_sources_list(self) -> List[dict]:
        """الحصول على قائمة المصادر المتاحة"""
        sources_list = []
        
        for category, sources in self.learning_sources.items():
            for source_name, source_data in sources.items():
                if isinstance(source_data, dict):
                    sources_list.append({
                        'category': category,
                        'name': source_name,
                        'description': source_data.get('description', source_data.get('name', '')),
                        'url': source_data.get('url', ''),
                        'auto_learning': source_data.get('auto_learning', False)
                    })
        
        return sources_list
    
    def get_automotive_resources(self) -> dict:
        """الحصول على موارد السيارات"""
        return self.learning_sources.get('automotive', {})
    
    def get_accounting_resources(self) -> dict:
        """الحصول على موارد المحاسبة"""
        return self.learning_sources.get('accounting_finance', {})
    
    def get_statistics(self) -> dict:
        """إحصائيات التعلم"""
        return {
            'total_sources': len(self.get_knowledge_sources_list()),
            'learned_articles': len(self.learned_data['articles']),
            'learned_solutions': len(self.learned_data['solutions']),
            'learned_code': len(self.learned_data['code_snippets']),
            'total_learned': self.learned_data['metadata'].get('total_learned', 0),
            'last_updated': self.learned_data['metadata'].get('last_updated', 'Never')
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

