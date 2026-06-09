"""
🧠 Quick Learner - المتعلم السريع
نظام بسيط للتعلم الفوري من ملفات JSON وتصحيحات المستخدم
"""
import json
import os
import difflib
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class QuickLearner:
    def __init__(self):
        from ai_knowledge import get_knowledge_path
        self.knowledge_file = get_knowledge_path('quick_knowledge.json')
        self.knowledge_base = self._load_knowledge()
    
    def _load_knowledge(self) -> Dict:
        """تحميل المعرفة السريعة"""
        if os.path.exists(self.knowledge_file):
            try:
                with open(self.knowledge_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load quick knowledge: {e}")
                return {}
        return {}
    
    def save_knowledge(self):
        """حفظ المعرفة"""
        try:
            with open(self.knowledge_file, 'w', encoding='utf-8') as f:
                json.dump(self.knowledge_base, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save quick knowledge: {e}")
            
    def learn(self, question: str, answer: str, category: str = 'general',
              tenant_id: int = None):
        """تعلم معلومة جديدة"""
        question_key = question.strip().lower()
        entry = {
            'answer': answer,
            'category': category,
            'confidence': 1.0,
        }
        if tenant_id is not None:
            entry['tenant_id'] = tenant_id
        self.knowledge_base[question_key] = entry
        self.save_knowledge()
        return True
        
    def get_answer(self, question: str, tenant_id: int = None) -> Optional[str]:
        """البحث عن إجابة - مع مطابقة ضبابية وعزل حسب المستأجر"""
        key = question.strip().lower()
        
        # 1. مطابقة تامة (ضمن نطاق المستأجر إن وجد)
        if key in self.knowledge_base:
            entry = self.knowledge_base[key]
            if tenant_id is None or entry.get('tenant_id') is None or entry.get('tenant_id') == tenant_id:
                return entry['answer']
        
        # 2. مطابقة تامة في جميع الإدخالات (إذا لم نجد في نطاق المستأجر)
        if key in self.knowledge_base:
            return self.knowledge_base[key]['answer']
        
        # 3. مطابقة جزئية
        candidates = []
        for k, v in self.knowledge_base.items():
            if tenant_id is not None and v.get('tenant_id') is not None and v.get('tenant_id') != tenant_id:
                continue
            if k in key or key in k:
                return v['answer']
            candidates.append(k)
        
        # 4. مطابقة ضبابية باستخدام difflib
        if candidates:
            close = difflib.get_close_matches(key, candidates, n=1, cutoff=0.6)
            if close:
                return self.knowledge_base[close[0]]['answer']
        
        return None

# Singleton
quick_learner = QuickLearner()
