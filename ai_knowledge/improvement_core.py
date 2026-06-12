"""
Consolidated module: improvement.py
Merged: improvement/self_reflection.py, improvement/self_improvement.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: improvement/self_reflection.py =====
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

import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List

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
    
    def __init__(self):
        self.performance_log = []
        self.errors_log = []
        self.improvements_log = []
        self.self_assessment = {}
    
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
        assessment = {
            'timestamp': datetime.now().isoformat(),
            'overall_score': 0,
            'strengths': [],
            'weaknesses': [],
            'improvements_needed': []
        }
        
        # تقييم الدقة
        if self.performance_log:
            recent_performance = self.performance_log[-100:]  # آخر 100 عملية
            
            accuracy_scores = [p.get('accuracy', 0) for p in recent_performance if 'accuracy' in p]
            
            if accuracy_scores:
                avg_accuracy = sum(accuracy_scores) / len(accuracy_scores)
                assessment['overall_score'] = avg_accuracy
                
                if avg_accuracy > 0.9:
                    assessment['strengths'].append(f"دقة عالية جداً: {avg_accuracy:.0%}")
                elif avg_accuracy > 0.7:
                    assessment['strengths'].append(f"دقة جيدة: {avg_accuracy:.0%}")
                else:
                    assessment['weaknesses'].append(f"الدقة منخفضة: {avg_accuracy:.0%}")
                    assessment['improvements_needed'].append("زيادة البيانات التدريبية")
        
        # تحليل الأخطاء
        if self.errors_log:
            recent_errors = self.errors_log[-50:]
            
            # تجميع الأخطاء المتشابهة
            error_types = defaultdict(int)
            for error in recent_errors:
                error_type = error.get('type', 'unknown')
                error_types[error_type] += 1
            
            # أكثر الأخطاء تكراراً
            if error_types:
                most_common = max(error_types, key=error_types.get)
                count = error_types[most_common]
                
                assessment['weaknesses'].append(f"خطأ متكرر: {most_common} ({count} مرة)")
                assessment['improvements_needed'].append(f"إصلاح: {most_common}")
        
        # التحسينات السابقة
        if self.improvements_log:
            recent_improvements = self.improvements_log[-10:]
            assessment['recent_improvements'] = [
                imp.get('improvement', '') for imp in recent_improvements
            ]
        
        # حفظ التقييم
        self.self_assessment = assessment
        
        logger.info(f"🔮 Self-reflection complete: Overall score {assessment['overall_score']:.0%}")
        
        return assessment
    
    def log_performance(self, task: str, accuracy: float, details: dict = None):
        """تسجيل الأداء"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'task': task,
            'accuracy': accuracy,
            'details': details or {}
        }
        
        self.performance_log.append(entry)
        
        # الاحتفاظ بآخر 1000 فقط
        if len(self.performance_log) > 1000:
            self.performance_log = self.performance_log[-1000:]
    
    def log_error(self, error_type: str, error_message: str, context: dict = None):
        """تسجيل خطأ للتعلم منه"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': error_type,
            'message': error_message,
            'context': context or {}
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
        for weakness in assessment['weaknesses']:
            if 'دقة منخفضة' in weakness:
                suggestions.append("💡 زيادة البيانات التدريبية للنماذج")
                suggestions.append("💡 إعادة تدريب النماذج بشكل دوري")
            
            if 'خطأ متكرر' in weakness:
                suggestions.append("💡 إضافة معالجة أخطاء أفضل")
                suggestions.append("💡 مراجعة المنطق في الكود")
        
        # اقتراحات عامة
        if assessment['overall_score'] < 0.8:
            suggestions.append("💡 مراجعة شاملة للنظام")
        
        return suggestions
    
    def plan_self_improvement(self) -> dict:
        """
        خطة التحسين الذاتي
        
        Returns:
            خطة عمل للتحسين
        """
        suggestions = self.suggest_improvements()
        
        plan = {
            'timestamp': datetime.now().isoformat(),
            'current_performance': self.self_assessment.get('overall_score', 0),
            'target_performance': 0.95,
            'improvements': suggestions,
            'action_items': []
        }
        
        # تحويل الاقتراحات لإجراءات
        for suggestion in suggestions:
            plan['action_items'].append({
                'action': suggestion,
                'priority': 'high',
                'estimated_time': '1-2 أيام',
                'status': 'pending'
            })
        
        return plan
    
    def celebrate_success(self, achievement: str):
        """
        الاحتفال بالإنجازات
        
        تعزيز إيجابي للتعلم
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'achievement': achievement,
            'type': 'success'
        }
        
        self.improvements_log.append(entry)
        
        logger.info(f"🎉 Achievement unlocked: {achievement}")
    
    def learn_from_mistake(self, mistake: str, lesson: str):
        """
        التعلم من الأخطاء
        
        "الفشل معلم عظيم"
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'mistake': mistake,
            'lesson': lesson,
            'type': 'learning'
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



# ===== Consolidated from: improvement/self_improvement.py =====
"""
🚀 نظام التحسين الذاتي - Self-Improvement System
أزاد يحسن نفسه تلقائياً ويطور قدراته
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict


class AzadSelfImprovement:
    """نظام التحسين الذاتي لأزاد"""
    
    def __init__(self):
        from ai_knowledge import get_knowledge_path
        self.improvement_file = get_knowledge_path('self_improvement.json')
        self.performance_file = get_knowledge_path('performance_metrics.json')
        self.goals_file = get_knowledge_path('improvement_goals.json')
        
        # تحميل البيانات
        self.improvement_data = self._load_improvement_data()
        self.performance_metrics = self._load_performance_metrics()
        self.improvement_goals = self._load_improvement_goals()
        
        # مجالات التحسين
        self.improvement_areas = {
            'response_quality': {
                'current_score': 7.5,
                'target_score': 9.5,
                'improvement_rate': 0.1,
                'last_improvement': None
            },
            'knowledge_depth': {
                'current_score': 8.0,
                'target_score': 9.8,
                'improvement_rate': 0.15,
                'last_improvement': None
            },
            'prediction_accuracy': {
                'current_score': 6.5,
                'target_score': 9.0,
                'improvement_rate': 0.2,
                'last_improvement': None
            },
            'customer_satisfaction': {
                'current_score': 8.2,
                'target_score': 9.7,
                'improvement_rate': 0.12,
                'last_improvement': None
            },
            'response_speed': {
                'current_score': 9.0,
                'target_score': 9.9,
                'improvement_rate': 0.05,
                'last_improvement': None
            }
        }
    
    def _load_improvement_data(self):
        """تحميل بيانات التحسين"""
        if os.path.exists(self.improvement_file):
            try:
                with open(self.improvement_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            'total_improvements': 0,
            'last_improvement_date': None,
            'improvement_history': [],
            'current_version': '1.0.0',
            'next_version': '1.1.0'
        }
    
    def _load_performance_metrics(self):
        """تحميل مقاييس الأداء"""
        if os.path.exists(self.performance_file):
            try:
                with open(self.performance_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            'daily_metrics': {},
            'weekly_metrics': {},
            'monthly_metrics': {},
            'overall_performance': 8.0
        }
    
    def _load_improvement_goals(self):
        """تحميل أهداف التحسين"""
        if os.path.exists(self.goals_file):
            try:
                with open(self.goals_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            'short_term_goals': [
                'تحسين دقة التنبؤات إلى 90%',
                'زيادة سرعة الرد إلى أقل من ثانيتين',
                'تطوير فهم أفضل للسياق'
            ],
            'long_term_goals': [
                'الوصول لمستوى خبير عالمي في جميع المجالات',
                'تطوير قدرات تنبؤية خارقة',
                'إتقان جميع جوانب الأعمال'
            ],
            'achieved_goals': [],
            'current_focus': 'تحسين دقة التنبؤات'
        }
    
    def analyze_performance(self):
        """تحليل الأداء الحالي"""
        analysis = {
            'overall_score': self._calculate_overall_score(),
            'strengths': self._identify_strengths(),
            'weaknesses': self._identify_weaknesses(),
            'improvement_opportunities': self._identify_opportunities(),
            'recommendations': self._generate_recommendations()
        }
        
        return analysis
    
    def _calculate_overall_score(self):
        """حساب النقاط الإجمالية"""
        total_score = 0
        total_weight = 0
        
        weights = {
            'response_quality': 0.25,
            'knowledge_depth': 0.25,
            'prediction_accuracy': 0.20,
            'customer_satisfaction': 0.20,
            'response_speed': 0.10
        }
        
        for area, config in self.improvement_areas.items():
            weight = weights.get(area, 0.2)
            total_score += config['current_score'] * weight
            total_weight += weight
        
        return round(total_score / total_weight, 2) if total_weight > 0 else 0
    
    def _identify_strengths(self):
        """تحديد نقاط القوة"""
        strengths = []
        
        for area, config in self.improvement_areas.items():
            if config['current_score'] >= 8.5:
                strengths.append({
                    'area': area,
                    'score': config['current_score'],
                    'description': self._get_area_description(area)
                })
        
        return strengths
    
    def _identify_weaknesses(self):
        """تحديد نقاط الضعف"""
        weaknesses = []
        
        for area, config in self.improvement_areas.items():
            if config['current_score'] < 7.0:
                weaknesses.append({
                    'area': area,
                    'score': config['current_score'],
                    'target_score': config['target_score'],
                    'improvement_needed': config['target_score'] - config['current_score'],
                    'description': self._get_area_description(area)
                })
        
        return weaknesses
    
    def _identify_opportunities(self):
        """تحديد فرص التحسين"""
        opportunities = []
        
        for area, config in self.improvement_areas.items():
            if 7.0 <= config['current_score'] < 8.5:
                opportunities.append({
                    'area': area,
                    'current_score': config['current_score'],
                    'potential_score': config['target_score'],
                    'improvement_potential': config['target_score'] - config['current_score'],
                    'description': self._get_area_description(area)
                })
        
        return opportunities
    
    def _get_area_description(self, area):
        """الحصول على وصف المجال"""
        descriptions = {
            'response_quality': 'جودة الردود ودقتها',
            'knowledge_depth': 'عمق المعرفة والخبرة',
            'prediction_accuracy': 'دقة التنبؤات والتحليلات',
            'customer_satisfaction': 'رضا العملاء',
            'response_speed': 'سرعة الاستجابة'
        }
        return descriptions.get(area, 'مجال غير محدد')
    
    def _generate_recommendations(self):
        """توليد توصيات التحسين"""
        recommendations = []
        
        # توصيات بناءً على نقاط الضعف
        weaknesses = self._identify_weaknesses()
        for weakness in weaknesses:
            recommendations.append({
                'type': 'urgent',
                'area': weakness['area'],
                'action': f"تحسين {weakness['description']} من {weakness['score']} إلى {weakness['target_score']}",
                'priority': 'عالي'
            })
        
        # توصيات بناءً على الفرص
        opportunities = self._identify_opportunities()
        for opportunity in opportunities:
            recommendations.append({
                'type': 'opportunity',
                'area': opportunity['area'],
                'action': f"تطوير {opportunity['description']} لتحقيق إمكانات كاملة",
                'priority': 'متوسط'
            })
        
        return recommendations
    
    def _refresh_scores_from_db(self):
        """Refresh scores from actual DB metrics instead of random simulation."""
        try:
            from extensions import db
            from sqlalchemy import text as sql_text
            # response_quality: ratio of successful interactions
            row = db.session.execute(
                sql_text("SELECT COUNT(*) FILTER (WHERE was_successful = true) AS ok, COUNT(*) AS total FROM ai_interactions")
            ).fetchone()
            total = row.total if row else 0
            ok = row.ok if row else 0
            if total > 0:
                self.improvement_areas['response_quality']['current_score'] = round(ok / total * 10, 2)

            # knowledge_depth: based on number of ai_memories
            mem_count = db.session.execute(sql_text("SELECT COUNT(*) FROM ai_memories")).scalar() or 0
            score = min(10.0, 5.0 + mem_count / 200.0)
            self.improvement_areas['knowledge_depth']['current_score'] = round(score, 2)

            # customer_satisfaction: same as response quality (proxy)
            if total > 0:
                self.improvement_areas['customer_satisfaction']['current_score'] = round(ok / total * 10, 2)
        except Exception as e:
            logger.debug(f"Could not refresh scores from DB: {e}")

    def implement_improvement(self, area, improvement_type='automatic'):
        """تطبيق التحسين — sets score from real DB data, not random."""
        if area not in self.improvement_areas:
            return {'success': False, 'error': 'المجال غير موجود'}
        self._refresh_scores_from_db()
        config = self.improvement_areas[area]
        new_score = config['current_score']
        improvement_record = {
            'area': area,
            'new_score': new_score,
            'type': improvement_type,
            'timestamp': datetime.now().isoformat()
        }
        self.improvement_data['improvement_history'].append(improvement_record)
        self.improvement_data['total_improvements'] += 1
        self.improvement_data['last_improvement_date'] = datetime.now().isoformat()
        self._save_data()
        return {
            'success': True,
            'area': area,
            'new_score': new_score,
            'timestamp': datetime.now().isoformat()
        }
    
    def auto_improve(self):
        """التحسين التلقائي — refresh all scores from DB metrics."""
        self._refresh_scores_from_db()
        self._save_data()
        return {
            'improvements_made': 1,
            'details': [{'area': k, 'score': v['current_score']} for k, v in self.improvement_areas.items()],
            'timestamp': datetime.now().isoformat()
        }
    
    def set_improvement_goal(self, area, target_score, timeframe='30_days'):
        """تعيين هدف تحسين"""
        if area not in self.improvement_areas:
            return {'success': False, 'error': 'المجال غير موجود'}
        
        goal = {
            'area': area,
            'current_score': self.improvement_areas[area]['current_score'],
            'target_score': target_score,
            'timeframe': timeframe,
            'created_at': datetime.now().isoformat(),
            'status': 'active'
        }
        
        # إضافة للقائمة
        if 'active_goals' not in self.improvement_goals:
            self.improvement_goals['active_goals'] = []
        
        self.improvement_goals['active_goals'].append(goal)
        
        # تحديث الهدف في المجال
        self.improvement_areas[area]['target_score'] = target_score
        
        # حفظ البيانات
        self._save_data()
        
        return {
            'success': True,
            'goal': goal,
            'message': f"تم تعيين هدف تحسين {area} إلى {target_score} خلال {timeframe}"
        }
    
    def track_progress(self):
        """تتبع التقدم"""
        progress_report = {
            'overall_progress': self._calculate_overall_progress(),
            'area_progress': {},
            'goals_progress': self._track_goals_progress(),
            'improvement_trend': self._calculate_improvement_trend(),
            'next_milestones': self._get_next_milestones()
        }
        
        # تقدم كل مجال
        for area, config in self.improvement_areas.items():
            progress_report['area_progress'][area] = {
                'current_score': config['current_score'],
                'target_score': config['target_score'],
                'progress_percentage': round((config['current_score'] / config['target_score']) * 100, 1),
                'remaining': round(config['target_score'] - config['current_score'], 2)
            }
        
        return progress_report
    
    def _calculate_overall_progress(self):
        """حساب التقدم الإجمالي"""
        total_progress = 0
        total_areas = len(self.improvement_areas)
        
        for area, config in self.improvement_areas.items():
            progress = (config['current_score'] / config['target_score']) * 100
            total_progress += progress
        
        return round(total_progress / total_areas, 1) if total_areas > 0 else 0
    
    def _track_goals_progress(self):
        """تتبع تقدم الأهداف"""
        if 'active_goals' not in self.improvement_goals:
            return []
        
        goals_progress = []
        for goal in self.improvement_goals['active_goals']:
            if goal['status'] == 'active':
                area = goal['area']
                current_score = self.improvement_areas[area]['current_score']
                target_score = goal['target_score']
                initial_score = goal['current_score']
                
                progress = ((current_score - initial_score) / (target_score - initial_score)) * 100
                
                goals_progress.append({
                    'area': area,
                    'initial_score': initial_score,
                    'current_score': current_score,
                    'target_score': target_score,
                    'progress_percentage': round(progress, 1),
                    'created_at': goal['created_at']
                })
        
        return goals_progress
    
    def _calculate_improvement_trend(self):
        """حساب اتجاه التحسين"""
        history = self.improvement_data.get('improvement_history', [])
        
        if len(history) < 2:
            return 'غير محدد'
        
        # تحليل آخر 10 تحسينات
        recent_improvements = history[-10:]
        total_improvement = sum(imp['improvement'] for imp in recent_improvements)
        
        if total_improvement > 0.5:
            return 'تحسن سريع'
        elif total_improvement > 0.2:
            return 'تحسن مستقر'
        elif total_improvement > 0:
            return 'تحسن بطيء'
        else:
            return 'ثابت'
    
    def _get_next_milestones(self):
        """الحصول على المعالم التالية"""
        milestones = []
        
        for area, config in self.improvement_areas.items():
            current_score = config['current_score']
            target_score = config['target_score']
            
            # المعالم القريبة
            if current_score < 8.0:
                milestones.append({
                    'area': area,
                    'milestone': '8.0',
                    'description': f'تحقيق مستوى جيد في {self._get_area_description(area)}',
                    'priority': 'عالي'
                })
            elif current_score < 9.0:
                milestones.append({
                    'area': area,
                    'milestone': '9.0',
                    'description': f'تحقيق مستوى ممتاز في {self._get_area_description(area)}',
                    'priority': 'متوسط'
                })
            elif current_score < target_score:
                milestones.append({
                    'area': area,
                    'milestone': str(target_score),
                    'description': f'تحقيق الهدف النهائي في {self._get_area_description(area)}',
                    'priority': 'منخفض'
                })
        
        return milestones
    
    def evolve_capabilities(self):
        """تطوير القدرات"""
        evolution_report = {
            'new_capabilities': [],
            'enhanced_capabilities': [],
            'evolution_timestamp': datetime.now().isoformat()
        }
        
        # تطوير قدرات جديدة بناءً على الأداء
        overall_score = self._calculate_overall_score()
        
        if overall_score >= 8.5:
            # مستوى عالي - إضافة قدرات متقدمة
            evolution_report['new_capabilities'].extend([
                'تحليل تنبؤي متقدم',
                'توصيات ذكية مخصصة',
                'تحليل سلوك العملاء',
                'توقع الاتجاهات المستقبلية'
            ])
        
        if overall_score >= 9.0:
            # مستوى خبير - إضافة قدرات خارقة
            evolution_report['new_capabilities'].extend([
                'تحليل ذكي للأسواق',
                'توصيات استراتيجية',
                'تحليل المخاطر المتقدم',
                'تخطيط الأعمال الذكي'
            ])
        
        # تحسين القدرات الموجودة
        for area, config in self.improvement_areas.items():
            if config['current_score'] >= 8.0:
                evolution_report['enhanced_capabilities'].append({
                    'area': area,
                    'enhancement': f'تحسين {self._get_area_description(area)}',
                    'level': 'متقدم'
                })
        
        return evolution_report
    
    def _save_data(self):
        """حفظ البيانات"""
        try:
            # حفظ بيانات التحسين
            with open(self.improvement_file, 'w', encoding='utf-8') as f:
                json.dump(self.improvement_data, f, ensure_ascii=False, indent=2)
            
            # حفظ مقاييس الأداء
            with open(self.performance_file, 'w', encoding='utf-8') as f:
                json.dump(self.performance_metrics, f, ensure_ascii=False, indent=2)
            
            # حفظ أهداف التحسين
            with open(self.goals_file, 'w', encoding='utf-8') as f:
                json.dump(self.improvement_goals, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Error saving improvement data: {e}")
    
    def get_improvement_status(self):
        """الحصول على حالة التحسين"""
        return {
            'current_version': self.improvement_data['current_version'],
            'next_version': self.improvement_data['next_version'],
            'total_improvements': self.improvement_data['total_improvements'],
            'last_improvement': self.improvement_data['last_improvement_date'],
            'overall_score': self._calculate_overall_score(),
            'improvement_areas': self.improvement_areas,
            'active_goals': len(self.improvement_goals.get('active_goals', [])),
            'status': 'نشط ومتطور باستمرار'
        }


# إنشاء مثيل عالمي لنظام التحسين الذاتي
self_improvement = AzadSelfImprovement()
