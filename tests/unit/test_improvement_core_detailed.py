"""Detailed tests for SelfReflectionEngine and AzadSelfImprovement covering all missing code paths."""
import json
import os
import pytest
from unittest.mock import patch


def _clean_artifact_files():
    from ai_knowledge import AI_KNOWLEDGE_DIR
    for name in ['self_improvement.json', 'performance_metrics.json', 'improvement_goals.json']:
        path = os.path.join(AI_KNOWLEDGE_DIR, name)
        if os.path.exists(path):
            os.remove(path)


class TestAzadSelfImprovementDetailed:

    def setup_method(self, method):
        _clean_artifact_files()

    # =========================================================================
    # SelfReflectionEngine — reflection core (lines 45-48, 62-118)
    # =========================================================================

    def test_reflection_init(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            assert engine.performance_log == []
            assert engine.errors_log == []
            assert engine.improvements_log == []
            assert engine.self_assessment == {}

    def test_reflect_on_performance_no_data(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            result = engine.reflect_on_performance()
            assert result['overall_score'] == 0
            assert result['strengths'] == []
            assert result['weaknesses'] == []
            assert result['improvements_needed'] == []

    def test_reflect_high_accuracy(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.performance_log = [{'accuracy': 0.95}, {'accuracy': 0.97}]
            result = engine.reflect_on_performance()
            assert result['overall_score'] > 0.9
            assert any('دقة عالية جداً' in s for s in result['strengths'])

    def test_reflect_medium_accuracy(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.performance_log = [{'accuracy': 0.75}, {'accuracy': 0.78}]
            result = engine.reflect_on_performance()
            assert 0.7 < result['overall_score'] <= 0.9
            assert any('دقة جيدة' in s for s in result['strengths'])

    def test_reflect_low_accuracy(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.performance_log = [{'accuracy': 0.5}, {'accuracy': 0.6}]
            result = engine.reflect_on_performance()
            assert result['overall_score'] <= 0.7
            assert any('الدقة منخفضة' in w for w in result['weaknesses'])
            assert 'زيادة البيانات التدريبية' in result['improvements_needed']

    def test_reflect_with_errors(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.errors_log = [
                {'type': 'timeout'}, {'type': 'timeout'}, {'type': 'parse_error'},
            ]
            result = engine.reflect_on_performance()
            assert any('timeout' in w for w in result['weaknesses'])

    def test_reflect_with_improvements_log(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.improvements_log = [{'improvement': 'speed boost'}]
            result = engine.reflect_on_performance()
            assert 'recent_improvements' in result
            assert 'speed boost' in result['recent_improvements']

    # =========================================================================
    # SelfReflectionEngine — log_performance (lines 122-133)
    # =========================================================================

    def test_log_performance_normal(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.log_performance('task_x', 0.9, {'detail': 'val'})
            assert len(engine.performance_log) == 1
            entry = engine.performance_log[0]
            assert entry['task'] == 'task_x'
            assert entry['accuracy'] == 0.9
            assert entry['details'] == {'detail': 'val'}

    def test_log_performance_default_details(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.log_performance('task_y', 0.8)
            assert engine.performance_log[0]['details'] == {}

    def test_log_performance_truncation(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            for i in range(1005):
                engine.log_performance(f't{i}', 0.5)
            assert len(engine.performance_log) == 1000

    # =========================================================================
    # SelfReflectionEngine — log_error (lines 137-150)
    # =========================================================================

    def test_log_error_normal(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.log_error('type_a', 'msg', {'ctx': 1})
            assert engine.errors_log[0]['type'] == 'type_a'
            assert engine.errors_log[0]['context'] == {'ctx': 1}

    def test_log_error_default_context(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.log_error('type_b', 'msg')
            assert engine.errors_log[0]['context'] == {}

    def test_log_error_truncation(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            for i in range(505):
                engine.log_error(f'e{i}', 'msg')
            assert len(engine.errors_log) == 500

    # =========================================================================
    # SelfReflectionEngine — suggest_improvements (lines 159-178)
    # =========================================================================

    def test_suggest_improvements_low_accuracy(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.performance_log = [{'accuracy': 0.5}]
            suggestions = engine.suggest_improvements()
            assert any('زيادة البيانات التدريبية' in s for s in suggestions)
            assert any('إعادة تدريب' in s for s in suggestions)

    def test_suggest_improvements_repeated_errors(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.errors_log = [{'type': 'timeout'}, {'type': 'timeout'}]
            suggestions = engine.suggest_improvements()
            assert any('إضافة معالجة أخطاء' in s for s in suggestions)
            assert any('مراجعة المنطق' in s for s in suggestions)

    def test_suggest_improvements_overall_below_80(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.performance_log = [{'accuracy': 0.5}]
            suggestions = engine.suggest_improvements()
            assert any('مراجعة شاملة' in s for s in suggestions)

    # =========================================================================
    # SelfReflectionEngine — plan_self_improvement (lines 187-206)
    # =========================================================================

    def test_plan_self_improvement(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.performance_log = [{'accuracy': 0.5}]
            plan = engine.plan_self_improvement()
            assert 'action_items' in plan
            assert 'improvements' in plan
            assert len(plan['action_items']) > 0
            assert plan['action_items'][0]['status'] == 'pending'
            assert plan['action_items'][0]['priority'] == 'high'

    # =========================================================================
    # SelfReflectionEngine — celebrate_success / learn_from_mistake
    # =========================================================================

    def test_celebrate_success(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.celebrate_success('hit 95% accuracy')
            assert len(engine.improvements_log) == 1
            assert engine.improvements_log[0]['achievement'] == 'hit 95% accuracy'
            assert engine.improvements_log[0]['type'] == 'success'

    def test_learn_from_mistake(self, app):
        from ai_knowledge.improvement_core import SelfReflectionEngine
        with app.app_context():
            engine = SelfReflectionEngine()
            engine.learn_from_mistake('wrong prediction', 'need more data')
            assert len(engine.improvements_log) == 1
            assert engine.improvements_log[0]['mistake'] == 'wrong prediction'
            assert engine.improvements_log[0]['lesson'] == 'need more data'
            assert engine.improvements_log[0]['type'] == 'learning'

    # =========================================================================
    # get_reflection_engine singleton (lines 251-253)
    # =========================================================================

    def test_get_reflection_engine_singleton(self, app):
        from ai_knowledge.improvement_core import get_reflection_engine
        with app.app_context():
            e1 = get_reflection_engine()
            e2 = get_reflection_engine()
            assert e1 is e2

    # =========================================================================
    # AzadSelfImprovement — JSON decode error paths (lines 323, 339, 354)
    # =========================================================================

    def test_load_improvement_data_json_decode_error(self, app, tmp_path, monkeypatch):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            f = tmp_path / 'self_improvement.json'
            f.write_text('{corrupt}')
            monkeypatch.setattr('ai_knowledge.get_knowledge_path', lambda n: str(tmp_path / n))
            improv = AzadSelfImprovement()
            assert improv.improvement_data['total_improvements'] == 0
            assert improv.improvement_data['current_version'] == '1.0.0'

    def test_load_performance_metrics_json_decode_error(self, app, tmp_path, monkeypatch):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            f = tmp_path / 'performance_metrics.json'
            f.write_text('{corrupt}')
            monkeypatch.setattr('ai_knowledge.get_knowledge_path', lambda n: str(tmp_path / n))
            improv = AzadSelfImprovement()
            assert improv.performance_metrics['overall_performance'] == 8.0

    def test_load_improvement_goals_json_decode_error(self, app, tmp_path, monkeypatch):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            f = tmp_path / 'improvement_goals.json'
            f.write_text('{corrupt}')
            monkeypatch.setattr('ai_knowledge.get_knowledge_path', lambda n: str(tmp_path / n))
            improv = AzadSelfImprovement()
            assert len(improv.improvement_goals['short_term_goals']) == 3

    # =========================================================================
    # _refresh_scores_from_db exception path (lines 508-509)
    # =========================================================================

    def test_refresh_scores_from_db_exception(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            with patch.object(improv, '_save_data'):
                with patch('extensions.db.session.execute') as mock_exec:
                    mock_exec.side_effect = Exception('db unavailable')
                    result = improv.implement_improvement('response_quality')
                    assert result['success'] is True

    # =========================================================================
    # set_improvement_goal (lines 547-571)
    # =========================================================================

    def test_set_goal_unknown_area(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            result = improv.set_improvement_goal('nonexistent', 9.0)
            assert result['success'] is False
            assert 'غير موجود' in result['error']

    def test_set_goal_creates_active_goals(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            if 'active_goals' in improv.improvement_goals:
                del improv.improvement_goals['active_goals']
            with patch.object(improv, '_save_data'):
                result = improv.set_improvement_goal('response_quality', 9.5)
                assert result['success'] is True
                assert 'active_goals' in improv.improvement_goals
                assert len(improv.improvement_goals['active_goals']) == 1

    def test_set_goal_appends_existing(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_goals['active_goals'] = [{'area': 'existing', 'status': 'active'}]
            with patch.object(improv, '_save_data'):
                result = improv.set_improvement_goal('knowledge_depth', 9.8)
                assert result['success'] is True
                assert len(improv.improvement_goals['active_goals']) == 2

    # =========================================================================
    # _track_goals_progress (lines 614-633)
    # =========================================================================

    def test_track_goals_progress_no_active_goals(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            if 'active_goals' in improv.improvement_goals:
                del improv.improvement_goals['active_goals']
            progress = improv.track_progress()
            assert progress['goals_progress'] == []

    def test_track_goals_progress_with_goal(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_goals['active_goals'] = [{
                'area': 'response_quality',
                'current_score': 7.0,
                'target_score': 9.0,
                'status': 'active',
                'created_at': '2025-01-01',
            }]
            improv.improvement_areas['response_quality']['current_score'] = 8.0
            gp = improv.track_progress()['goals_progress']
            assert len(gp) == 1
            assert gp[0]['area'] == 'response_quality'
            assert gp[0]['progress_percentage'] > 0

    # =========================================================================
    # _calculate_improvement_trend (lines 643-653)
    # =========================================================================

    def test_trend_insufficient_history(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_data['improvement_history'] = [{'improvement': 0.1}]
            assert improv.track_progress()['improvement_trend'] == 'غير محدد'

    def test_trend_fast(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_data['improvement_history'] = [
                {'improvement': 0.3}, {'improvement': 0.4},
            ]
            assert improv.track_progress()['improvement_trend'] == 'تحسن سريع'

    def test_trend_stable(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_data['improvement_history'] = [
                {'improvement': 0.15}, {'improvement': 0.1},
            ]
            assert improv.track_progress()['improvement_trend'] == 'تحسن مستقر'

    def test_trend_slow(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_data['improvement_history'] = [
                {'improvement': 0.05}, {'improvement': 0.05},
            ]
            assert improv.track_progress()['improvement_trend'] == 'تحسن بطيء'

    def test_trend_steady(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_data['improvement_history'] = [
                {'improvement': 0.0}, {'improvement': 0.0},
            ]
            assert improv.track_progress()['improvement_trend'] == 'ثابت'

    # =========================================================================
    # evolve_capabilities (lines 690-726)
    # =========================================================================

    def test_evolve_no_capabilities(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            for a in improv.improvement_areas:
                improv.improvement_areas[a]['current_score'] = 5.0
            r = improv.evolve_capabilities()
            assert r['new_capabilities'] == []
            assert r['enhanced_capabilities'] == []

    def test_evolve_advanced_capabilities(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            for a in improv.improvement_areas:
                improv.improvement_areas[a]['current_score'] = 8.5
            r = improv.evolve_capabilities()
            assert 'تحليل تنبؤي متقدم' in r['new_capabilities']
            assert 'تحليل ذكي للأسواق' not in r['new_capabilities']

    def test_evolve_expert_capabilities(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            for a in improv.improvement_areas:
                improv.improvement_areas[a]['current_score'] = 9.5
            r = improv.evolve_capabilities()
            assert 'تحليل تنبؤي متقدم' in r['new_capabilities']
            assert 'تحليل ذكي للأسواق' in r['new_capabilities']

    def test_evolve_enhanced_areas(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            for a in improv.improvement_areas:
                improv.improvement_areas[a]['current_score'] = 8.0
            r = improv.evolve_capabilities()
            assert len(r['enhanced_capabilities']) == len(improv.improvement_areas)

    # =========================================================================
    # _save_data exception path (lines 743-744)
    # =========================================================================

    def test_save_data_handles_oserror(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            with patch('builtins.open', side_effect=OSError('read-only')):
                try:
                    improv._save_data()
                except Exception:
                    pytest.fail('_save_data should not raise on OSError')

    # =========================================================================
    # get_improvement_status return dict (line 748)
    # =========================================================================

    def test_get_improvement_status(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            status = improv.get_improvement_status()
            assert status['current_version'] == '1.0.0'
            assert status['next_version'] == '1.1.0'
            assert 'overall_score' in status
            assert len(status['improvement_areas']) == 5
            assert 'active_goals' in status
            assert 'نشط' in status['status']

    # =========================================================================
    # Internal helpers — _identify_strengths, _identify_weaknesses, etc.
    # =========================================================================

    def test_identify_strengths_above_85(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_areas['response_quality']['current_score'] = 9.0
            improv.improvement_areas['knowledge_depth']['current_score'] = 7.0
            s = improv._identify_strengths()
            areas = [x['area'] for x in s]
            assert 'response_quality' in areas
            assert 'knowledge_depth' not in areas

    def test_identify_weaknesses_below_70(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_areas['prediction_accuracy']['current_score'] = 6.0
            w = improv._identify_weaknesses()
            assert any(x['area'] == 'prediction_accuracy' for x in w)

    def test_identify_opportunities_mid_range(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_areas['response_quality']['current_score'] = 7.5
            o = improv._identify_opportunities()
            assert any(x['area'] == 'response_quality' for x in o)

    def test_generate_recommendations(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            improv.improvement_areas['prediction_accuracy']['current_score'] = 6.0
            improv.improvement_areas['response_quality']['current_score'] = 7.5
            recs = improv._generate_recommendations()
            types = [r['type'] for r in recs]
            assert 'urgent' in types
            assert 'opportunity' in types

    def test_get_area_description_unknown(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            assert improv._get_area_description('bogus') == 'مجال غير محدد'
