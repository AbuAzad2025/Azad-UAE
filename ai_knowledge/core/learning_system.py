"""
🧠 نظام التعلم الذاتي - Self-Learning System
أزاد يتعلم ويطور نفسه ذاتياً
"""

import json
import logging
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)


class AzadLearningSystem:
    """نظام التعلم الذاتي لأزاد"""
    
    def __init__(self):
        from ai_knowledge import get_knowledge_path
        
        self.knowledge_file = get_knowledge_path('learned_knowledge.json')
        self.interactions_file = get_knowledge_path('interactions_log.json')
        self.patterns_file = get_knowledge_path('patterns.json')
        self.feedback_file = get_knowledge_path('feedback_log.json')
        
        # تحميل المعرفة المكتسبة
        self.learned_knowledge = self._load_learned_knowledge()
        self.interactions = self._load_interactions()
        self.patterns = self._load_patterns()
        self.feedback_log = self._load_feedback()

    @staticmethod
    def _empty_patterns():
        return {
            'question_patterns': defaultdict(list),
            'response_patterns': defaultdict(list),
            'success_patterns': defaultdict(float),
            'time_patterns': defaultdict(int),
            'user_behavior': defaultdict(dict),
        }

    @staticmethod
    def _patterns_from_storage(data: dict):
        patterns = AzadLearningSystem._empty_patterns()
        for key, factory in (
            ('question_patterns', list),
            ('response_patterns', list),
            ('success_patterns', float),
            ('time_patterns', int),
            ('user_behavior', dict),
        ):
            stored = data.get(key, {})
            if isinstance(stored, dict):
                patterns[key] = defaultdict(factory, stored)
        return patterns

    @staticmethod
    def _patterns_to_storage(patterns: dict) -> dict:
        return {key: dict(patterns.get(key, {})) for key in (
            'question_patterns', 'response_patterns', 'success_patterns',
            'time_patterns', 'user_behavior',
        )}

    def _load_learned_knowledge(self):
        """تحميل المعرفة المكتسبة"""
        if os.path.exists(self.knowledge_file):
            try:
                with open(self.knowledge_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    exp = data.get('expertise_areas', {})
                    if not isinstance(exp, defaultdict):
                        data['expertise_areas'] = defaultdict(int, exp)
                    return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug('Could not load knowledge file: %s', exc)
        return {
            'new_terms': {},
            'customer_preferences': {},
            'market_trends': {},
            'successful_responses': {},
            'failed_responses': {},
            'expertise_areas': defaultdict(int),
            'learning_stats': {
                'total_interactions': 0,
                'successful_answers': 0,
                'learning_rate': 0.0,
                'last_updated': None
            }
        }
    
    def _load_interactions(self):
        """تحميل سجل التفاعلات"""
        if os.path.exists(self.interactions_file):
            try:
                with open(self.interactions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug('Could not load interactions file: %s', exc)
        return []
    
    def _load_patterns(self):
        """تحميل الأنماط المكتشفة"""
        if os.path.exists(self.patterns_file):
            try:
                with open(self.patterns_file, 'r', encoding='utf-8') as f:
                    return self._patterns_from_storage(json.load(f))
            except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
                logger.debug('Could not load patterns.json: %s', exc)
        return self._empty_patterns()
    
    def _load_feedback(self):
        """تحميل سجل التقييمات"""
        if os.path.exists(self.feedback_file):
            try:
                with open(self.feedback_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug('Could not load feedback file: %s', exc)
        return []
    
    def learn_from_interaction(self, question, response, user_feedback=None, context=None,
                                tenant_id=None):
        """التعلم من كل تفاعل"""
        ctx = dict(context or {})
        if tenant_id is not None:
            ctx['tenant_id'] = tenant_id
        interaction = {
            'timestamp': datetime.now().isoformat(),
            'question': question,
            'response': response,
            'user_feedback': user_feedback,
            'context': ctx,
            'success': user_feedback is None or user_feedback > 3,  # افتراض نجاح إذا لم يكن هناك تقييم
        }
        
        # إضافة للتفاعلات
        self.interactions.append(interaction)
        
        # تحليل النمط
        self._analyze_patterns(question, response, interaction['success'])
        
        # تحديث المعرفة
        self._update_knowledge(question, response, interaction['success'])
        
        # حفظ البيانات
        self._save_data()
        
        # تحديث الإحصائيات
        self._update_stats()
    
    def _analyze_patterns(self, question, response, success):
        """تحليل الأنماط في الأسئلة والردود"""
        question_lower = question.lower()
        
        # تحليل كلمات مفتاحية
        keywords = self._extract_keywords(question_lower)
        for keyword in keywords:
            self.patterns['question_patterns'][keyword].append({
                'question': question,
                'success': success,
                'timestamp': datetime.now().isoformat()
            })
        
        # تحليل نوع السؤال
        question_type = self._classify_question(question_lower)
        self.patterns['response_patterns'][question_type].append({
            'response': response,
            'success': success,
            'timestamp': datetime.now().isoformat()
        })
        
        # تحديث معدل النجاح
        if question_type in self.patterns['success_patterns']:
            current_rate = self.patterns['success_patterns'][question_type]
            new_rate = (current_rate * 0.9) + (1.0 if success else 0.0) * 0.1
            self.patterns['success_patterns'][question_type] = new_rate
        else:
            self.patterns['success_patterns'][question_type] = 1.0 if success else 0.0
    
    def _extract_keywords(self, text):
        """استخراج الكلمات المفتاحية"""
        # قائمة الكلمات المهمة
        important_words = [
            'ضريبة', 'vat', 'جمارك', 'customs', 'محرك', 'engine',
            'فرامل', 'brake', 'هيدروليك', 'hydraulic', 'مخزون', 'stock',
            'مبيعات', 'sales', 'عميل', 'customer', 'سعر', 'price',
            'ربح', 'profit', 'توقع', 'predict', 'تحليل', 'analyze'
        ]
        
        keywords = []
        for word in important_words:
            if word in text:
                keywords.append(word)
        
        return keywords
    
    def _classify_question(self, question):
        """تصنيف نوع السؤال"""
        if any(kw in question for kw in ['ضريبة', 'vat', 'tax']):
            return 'tax_question'
        elif any(kw in question for kw in ['جمارك', 'customs', 'استيراد']):
            return 'customs_question'
        elif any(kw in question for kw in ['محرك', 'engine', 'قطعة', 'part']):
            return 'parts_question'
        elif any(kw in question for kw in ['مخزون', 'stock', 'inventory']):
            return 'inventory_question'
        elif any(kw in question for kw in ['مبيعات', 'sales', 'تحليل']):
            return 'sales_question'
        elif any(kw in question for kw in ['عميل', 'customer', 'خدمة']):
            return 'customer_question'
        elif any(kw in question for kw in ['توقع', 'predict', 'forecast']):
            return 'prediction_question'
        else:
            return 'general_question'
    
    def _update_knowledge(self, question, response, success):
        """تحديث المعرفة بناءً على التفاعل"""
        if success:
            # إضافة للمعرفة الناجحة
            question_type = self._classify_question(question.lower())
            if question_type not in self.learned_knowledge['successful_responses']:
                self.learned_knowledge['successful_responses'][question_type] = []
            
            self.learned_knowledge['successful_responses'][question_type].append({
                'question': question,
                'response': response,
                'timestamp': datetime.now().isoformat()
            })
            
            # تحديث مجالات الخبرة
            self.learned_knowledge['expertise_areas'][question_type] += 1
        else:
            # تسجيل الردود الفاشلة للتحسين
            if 'failed_responses' not in self.learned_knowledge:
                self.learned_knowledge['failed_responses'] = []
            
            self.learned_knowledge['failed_responses'].append({
                'question': question,
                'response': response,
                'timestamp': datetime.now().isoformat()
            })
    
    def _save_data(self):
        """حفظ البيانات"""
        try:
            # حفظ المعرفة المكتسبة
            to_save = dict(self.learned_knowledge)
            ea = self.learned_knowledge.get('expertise_areas', {})
            try:
                to_save['expertise_areas'] = dict(ea)
            except (TypeError, ValueError):
                to_save['expertise_areas'] = {}
            with open(self.knowledge_file, 'w', encoding='utf-8') as f:
                json.dump(to_save, f, ensure_ascii=False, indent=2)
            
            # حفظ التفاعلات (آخر 1000 تفاعل)
            recent_interactions = self.interactions[-1000:]
            with open(self.interactions_file, 'w', encoding='utf-8') as f:
                json.dump(recent_interactions, f, ensure_ascii=False, indent=2)
            
            # حفظ الأنماط
            with open(self.patterns_file, 'w', encoding='utf-8') as f:
                json.dump(self._patterns_to_storage(self.patterns), f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.warning('Error saving learning data: %s', e)
    
    def _update_stats(self):
        """تحديث الإحصائيات"""
        total_interactions = len(self.interactions)
        successful_answers = sum(1 for i in self.interactions if i.get('success', False))
        
        self.learned_knowledge['learning_stats'] = {
            'total_interactions': total_interactions,
            'successful_answers': successful_answers,
            'learning_rate': successful_answers / total_interactions if total_interactions > 0 else 0,
            'last_updated': datetime.now().isoformat()
        }
    
    def get_learning_insights(self):
        """الحصول على رؤى التعلم"""
        stats = self.learned_knowledge['learning_stats']
        expertise = self.learned_knowledge['expertise_areas']
        
        # ترتيب مجالات الخبرة
        top_expertise = sorted(expertise.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # تحليل الأنماط
        success_rates = self.patterns['success_patterns']
        best_areas = sorted(success_rates.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return {
            'total_interactions': stats['total_interactions'],
            'success_rate': stats['learning_rate'],
            'top_expertise_areas': top_expertise,
            'best_performing_areas': best_areas,
            'learning_progress': self._calculate_learning_progress(),
            'recommendations': self._get_learning_recommendations()
        }
    
    def _calculate_learning_progress(self):
        """حساب تقدم التعلم"""
        total_interactions = len(self.interactions)
        
        if total_interactions < 10:
            return "مبتدئ - يحتاج المزيد من التفاعلات"
        elif total_interactions < 50:
            return "متوسط - يتعلم بسرعة"
        elif total_interactions < 200:
            return "متقدم - خبرة جيدة"
        else:
            return "خبير - مستوى عالمي"
    
    def _get_learning_recommendations(self):
        """الحصول على توصيات للتعلم"""
        recommendations = []
        
        # تحليل مجالات الضعف
        expertise = self.learned_knowledge['expertise_areas']
        if expertise:
            min_expertise = min(expertise.values())
            weak_areas = [area for area, count in expertise.items() if count == min_expertise]
            
            if weak_areas:
                recommendations.append(f"ركز على تحسين: {', '.join(weak_areas)}")
        
        # تحليل معدلات النجاح
        success_rates = self.patterns['success_patterns']
        if success_rates:
            low_success = [area for area, rate in success_rates.items() if rate < 0.7]
            if low_success:
                recommendations.append(f"حسّن الأداء في: {', '.join(low_success)}")
        
        # توصيات عامة
        total_interactions = len(self.interactions)
        if total_interactions < 100:
            recommendations.append("استمر في التفاعل مع المستخدمين لزيادة الخبرة")
        
        return recommendations
    
    def evolve_knowledge(self):
        """تطوير المعرفة تلقائياً"""
        # تحليل الأنماط المتكررة
        recent_interactions = self.interactions[-50:]  # آخر 50 تفاعل
        
        # اكتشاف مصطلحات جديدة
        new_terms = self._discover_new_terms(recent_interactions)
        
        # تحديث استراتيجيات الرد
        self._update_response_strategies()
        
        # تحسين فهم السياق
        self._improve_context_understanding()
        
        return {
            'new_terms_discovered': len(new_terms),
            'strategies_updated': True,
            'context_improved': True,
            'evolution_timestamp': datetime.now().isoformat()
        }
    
    def _discover_new_terms(self, interactions):
        """اكتشاف مصطلحات جديدة"""
        new_terms = set()
        
        for interaction in interactions:
            question = interaction['question'].lower()
            
            # البحث عن مصطلحات تقنية جديدة
            technical_terms = [
                'ecm', 'ecu', 'abs', 'esp', 'tcs', 'dpf', 'egr', 'scr',
                'adblue', 'def', 'urea', 'diesel', 'petrol', 'hybrid',
                'electric', 'turbo', 'supercharger', 'intercooler'
            ]
            
            for term in technical_terms:
                if term in question and term not in self.learned_knowledge['new_terms']:
                    new_terms.add(term)
                    self.learned_knowledge['new_terms'][term] = {
                        'first_seen': datetime.now().isoformat(),
                        'context': question,
                        'frequency': 1
                    }
        
        return new_terms
    
    def _update_response_strategies(self):
        """تحديث استراتيجيات الرد"""
        # تحليل الردود الأكثر نجاحاً
        successful_responses = self.learned_knowledge['successful_responses']
        
        for question_type, responses in successful_responses.items():
            if len(responses) > 5:  # إذا كان هناك ردود كافية للتحليل
                # تحليل العناصر المشتركة في الردود الناجحة
                common_elements = self._find_common_elements(responses)
                
                # تحديث استراتيجية الرد لهذا النوع
                if 'response_strategies' not in self.learned_knowledge:
                    self.learned_knowledge['response_strategies'] = {}
                
                self.learned_knowledge['response_strategies'][question_type] = {
                    'common_elements': common_elements,
                    'success_rate': len(responses) / (len(responses) + len(self.learned_knowledge.get('failed_responses', []))),
                    'last_updated': datetime.now().isoformat()
                }
    
    def _find_common_elements(self, responses):
        """العثور على العناصر المشتركة في الردود الناجحة"""
        common_elements = {
            'emojis_used': Counter(),
            'keywords_used': Counter(),
            'response_length': [],
            'structure_patterns': []
        }
        
        for response in responses:
            response_text = response['response']
            
            # تحليل الرموز التعبيرية
            import re
            emojis = re.findall(r'[^\w\s]', response_text)
            common_elements['emojis_used'].update(emojis)
            
            # تحليل الكلمات المفتاحية
            words = response_text.lower().split()
            important_words = [w for w in words if len(w) > 3]
            common_elements['keywords_used'].update(important_words)
            
            # طول الرد
            common_elements['response_length'].append(len(response_text))
        
        return common_elements
    
    def _improve_context_understanding(self):
        """تحسين فهم السياق"""
        # تحليل السياقات المختلفة
        context_patterns = defaultdict(list)
        
        for interaction in self.interactions[-100:]:  # آخر 100 تفاعل
            if interaction.get('context'):
                context = interaction['context']
                question_type = self._classify_question(interaction['question'].lower())
                context_patterns[question_type].append(context)
        
        # تحديث فهم السياق
        if 'context_understanding' not in self.learned_knowledge:
            self.learned_knowledge['context_understanding'] = {}
        
        for question_type, contexts in context_patterns.items():
            if len(contexts) > 3:  # إذا كان هناك سياقات كافية
                self.learned_knowledge['context_understanding'][question_type] = {
                    'common_contexts': list(set(contexts)),
                    'context_count': len(contexts),
                    'last_updated': datetime.now().isoformat()
                }
    
    def get_enhanced_response(self, question, base_response):
        """الحصول على رد محسن بناءً على التعلم"""
        question_type = self._classify_question(question.lower())
        
        # تطبيق استراتيجيات الرد المكتسبة
        if 'response_strategies' in self.learned_knowledge:
            strategies = self.learned_knowledge['response_strategies'].get(question_type, {})
            
            if strategies:
                # تحسين الرد بناءً على الاستراتيجيات
                enhanced_response = self._apply_response_strategies(base_response, strategies)
                return enhanced_response
        
        return base_response
    
    def _apply_response_strategies(self, response, strategies):
        """تطبيق استراتيجيات الرد"""
        enhanced_response = response
        
        # إضافة الرموز التعبيرية الشائعة
        common_elements = strategies.get('common_elements', {})
        if common_elements.get('emojis_used'):
            top_emojis = common_elements['emojis_used'].most_common(3)
            # يمكن إضافة منطق لإدراج الرموز المناسبة
        
        # تحسين طول الرد
        if common_elements.get('response_length'):
            avg_length = sum(common_elements['response_length']) / len(common_elements['response_length'])
            if len(response) < avg_length * 0.5:
                # الرد قصير جداً - يمكن إضافة المزيد من التفاصيل
                pass
        
        return enhanced_response
    
    def learn_from_groq_feedback(self, learning_data):
        """تعلم من ردود Groq - Groq يدرب المحلي"""
        try:
            question = learning_data['question']
            local_answer = learning_data['local_answer']
            groq_answer = learning_data['improved_answer']
            
            comparison = {
                'question': question,
                'local_response': local_answer,
                'groq_response': groq_answer,
                'timestamp': learning_data['timestamp'],
                'improvements': self._analyze_improvements(local_answer, groq_answer)
            }
            
            if not hasattr(self, 'groq_training_log'):
                self.groq_training_log = []
            
            self.groq_training_log.append(comparison)
            
            if len(self.groq_training_log) > 100:
                self.groq_training_log = self.groq_training_log[-100:]
            
            self.learn_from_interaction(question, groq_answer, user_feedback='groq_improved')
            
        except Exception as e:
            print(f"Groq training error: {e}")
    
    def _analyze_improvements(self, local, groq):
        """تحليل التحسينات التي قدمها Groq"""
        try:
            local_str = str(local) if local else ""
            groq_str = str(groq) if groq else ""
            improvements = {
                'length_diff': len(groq_str) - len(local_str),
                'quality_improved': len(groq_str) > len(local_str),
                'timestamp': datetime.now().isoformat()
            }
            return improvements
        except Exception as e:
            logging.getLogger(__name__).debug(f"Improvement analysis failed: {e}")
            return {'timestamp': datetime.now().isoformat()}


# إنشاء مثيل عالمي لنظام التعلم
learning_system = AzadLearningSystem()
