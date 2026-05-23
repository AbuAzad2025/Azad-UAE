"""
🧠 Quick Learner - المتعلم السريع
نظام بسيط للتعلم الفوري من ملفات JSON وتصحيحات المستخدم
"""
import json
import os
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
            
    def learn(self, question: str, answer: str, category: str = 'general'):
        """تعلم معلومة جديدة"""
        question_key = question.strip().lower()
        self.knowledge_base[question_key] = {
            'answer': answer,
            'category': category,
            'confidence': 1.0  # تعلم مباشر
        }
        self.save_knowledge()
        return True
        
    def get_answer(self, question: str) -> Optional[str]:
        """البحث عن إجابة"""
        # مطابقة تامة
        key = question.strip().lower()
        if key in self.knowledge_base:
            return self.knowledge_base[key]['answer']
            
        # مطابقة جزئية
        for k, v in self.knowledge_base.items():
            if k in key or key in k:
                return v['answer']
                
        return None

# Singleton
quick_learner = QuickLearner()
