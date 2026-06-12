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
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Could not load history: {e}")
        
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
# Self-test integration — delegates to consolidated learning_engine
# =====================

from ai_knowledge.learning_engine import evaluate_and_learn  # noqa: F401


# إنشاء instance عام
continuous_learner = ContinuousLearner()

