"""Detailed coverage tests for AzadLearningSystem — fills all missing code paths."""
import json
import os
import pytest
from datetime import datetime
from collections import defaultdict, Counter


class TestAzadLearningSystemDetailed:

    def _make_system(self, app, tmp_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem
        from collections import defaultdict
        import os
        system = AzadLearningSystem.__new__(AzadLearningSystem)
        system.knowledge_file = os.path.join(tmp_path, "learned_knowledge.json")
        system.interactions_file = os.path.join(tmp_path, "interactions_log.json")
        system.patterns_file = os.path.join(tmp_path, "patterns.pkl")
        system.feedback_file = os.path.join(tmp_path, "feedback_log.json")
        system.learned_knowledge = {
            'new_terms': {},
            'customer_preferences': {},
            'market_trends': {},
            'successful_responses': {},
            'failed_responses': {},
            'expertise_areas': defaultdict(int),
            'learning_stats': {
                'total_interactions': 0, 'successful_answers': 0,
                'learning_rate': 0.0, 'last_updated': None,
            },
        }
        system.interactions = []
        system.patterns = {
            'question_patterns': defaultdict(list),
            'response_patterns': defaultdict(list),
            'success_patterns': defaultdict(float),
            'time_patterns': defaultdict(int),
            'user_behavior': defaultdict(dict),
        }
        system.feedback_log = []
        return system

    # ------------------------------------------------------------------
    # _load_learned_knowledge — lines 57-59 (corrupt file → default)
    # ------------------------------------------------------------------
    def test_load_learned_knowledge_corrupt_file(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            with open(system.knowledge_file, 'w', encoding='utf-8') as f:
                f.write('{invalid json')
            result = system._load_learned_knowledge()
            assert result['new_terms'] == {}
            assert result['learning_stats']['total_interactions'] == 0

    # ------------------------------------------------------------------
    # _load_interactions — line 80 (corrupt file → [])
    # ------------------------------------------------------------------
    def test_load_interactions_corrupt_file(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            with open(system.interactions_file, 'w', encoding='utf-8') as f:
                f.write('{invalid json')
            result = system._load_interactions()
            assert result == []

    # ------------------------------------------------------------------
    # _load_feedback — lines 100-103 (success + exception paths)
    # ------------------------------------------------------------------
    def test_load_feedback_success(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            feedback_data = [{"question": "test", "rating": 5}]
            with open(system.feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedback_data, f)
            result = system._load_feedback()
            assert result == feedback_data

    def test_load_feedback_corrupt_file(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            with open(system.feedback_file, 'w', encoding='utf-8') as f:
                f.write('not json')
            result = system._load_feedback()
            assert result == []

    # ------------------------------------------------------------------
    # _classify_question — lines 186, 188, 192, 194, 196, 198
    # ------------------------------------------------------------------
    def test_classify_tax_question(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            assert system._classify_question("ما هي نسبة الضريبة") == 'tax_question'
            assert system._classify_question("vat calculation") == 'tax_question'
            assert system._classify_question("tax report") == 'tax_question'

    def test_classify_customs_question(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            assert system._classify_question("اجراءات الجمارك") == 'customs_question'
            assert system._classify_question("customs clearance") == 'customs_question'
            assert system._classify_question("استيراد بضائع") == 'customs_question'

    def test_classify_inventory_question(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            assert system._classify_question("المخزون الحالي") == 'inventory_question'
            assert system._classify_question("stock count") == 'inventory_question'
            assert system._classify_question("inventory report") == 'inventory_question'

    def test_classify_sales_question(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            assert system._classify_question("تحليل المبيعات") == 'sales_question'
            assert system._classify_question("sales report") == 'sales_question'

    def test_classify_customer_question(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            assert system._classify_question("خدمة العملاء") == 'customer_question'
            assert system._classify_question("customer data") == 'customer_question'

    def test_classify_prediction_question(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            assert system._classify_question("توقع المستقبل") == 'prediction_question'
            assert system._classify_question("predict revenue") == 'prediction_question'
            assert system._classify_question("forecast demand") == 'prediction_question'

    # ------------------------------------------------------------------
    # _update_knowledge — line 221 (missing failed_responses key)
    # ------------------------------------------------------------------
    def test_update_knowledge_failed_missing_key(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            del system.learned_knowledge['failed_responses']
            system._update_knowledge("test question", "test response", success=False)
            assert 'failed_responses' in system.learned_knowledge
            assert len(system.learned_knowledge['failed_responses']) == 1
            assert system.learned_knowledge['failed_responses'][0]['question'] == "test question"

    # ------------------------------------------------------------------
    # _save_data — lines 237-238 (expertise_areas dict() failure)
    #            — lines 251-252 (outer save error)
    # ------------------------------------------------------------------
    def test_save_data_expertise_dict_conversion_error(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)

            class BadIterable:
                def __iter__(self):
                    raise TypeError("cannot convert")
            system.learned_knowledge['expertise_areas'] = BadIterable()
            system._save_data()
            assert os.path.exists(system.knowledge_file)

    def test_save_data_write_error(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.knowledge_file = os.path.join(tmp_path, "nonexistent_dir", "file.json")
            system._save_data()

    # ------------------------------------------------------------------
    # _calculate_learning_progress — lines 293-298
    # ------------------------------------------------------------------
    def test_calculate_learning_progress_intermediate(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            for i in range(10):
                system.interactions.append({'question': f'q{i}', 'success': True})
            assert system._calculate_learning_progress() == "متوسط - يتعلم بسرعة"

    def test_calculate_learning_progress_advanced(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            for i in range(50):
                system.interactions.append({'question': f'q{i}', 'success': True})
            assert system._calculate_learning_progress() == "متقدم - خبرة جيدة"

    def test_calculate_learning_progress_expert(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            for i in range(200):
                system.interactions.append({'question': f'q{i}', 'success': True})
            assert system._calculate_learning_progress() == "خبير - مستوى عالمي"

    # ------------------------------------------------------------------
    # _get_learning_recommendations — line 318 (low-success areas)
    # ------------------------------------------------------------------
    def test_get_learning_recommendations_low_success(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.patterns['success_patterns']['tax_question'] = 0.5
            system.patterns['success_patterns']['general_question'] = 0.9
            recommendations = system._get_learning_recommendations()
            assert any("حسّن الأداء في" in r for r in recommendations)

    # ------------------------------------------------------------------
    # evolve_knowledge — lines 330-341
    # ------------------------------------------------------------------
    def test_evolve_knowledge(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            for i in range(60):
                system.interactions.append({
                    'question': 'check ecm and abs system',
                    'response': 'ECM and ABS are working fine',
                    'success': True,
                    'context': f'tenant_1_user_{i}',
                    'timestamp': datetime.now().isoformat()
                })
            result = system.evolve_knowledge()
            assert result['new_terms_discovered'] > 0
            assert result['strategies_updated'] is True
            assert result['context_improved'] is True

    # ------------------------------------------------------------------
    # _discover_new_terms — lines 350-371
    # ------------------------------------------------------------------
    def test_discover_new_terms(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            interactions = [
                {'question': 'check ecm and abs system', 'response': '', 'success': True},
                {'question': 'dpf and egr issues', 'response': '', 'success': True},
                {'question': 'adblue level low', 'response': '', 'success': True},
            ]
            result = system._discover_new_terms(interactions)
            assert 'ecm' in result
            assert 'abs' in result
            assert 'dpf' in result
            assert 'egr' in result
            assert 'adblue' in result

    def test_discover_new_terms_skips_existing(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.learned_knowledge['new_terms']['ecm'] = {'first_seen': '2025-01-01'}
            interactions = [
                {'question': 'ecm failure', 'response': '', 'success': True},
            ]
            result = system._discover_new_terms(interactions)
            assert 'ecm' not in result

    # ------------------------------------------------------------------
    # _update_response_strategies — lines 376-387
    # ------------------------------------------------------------------
    def test_update_response_strategies(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.learned_knowledge['successful_responses']['tax_question'] = [
                {'response': f'thank you! ✅ info {i}', 'question': f'vat q{i}'}
                for i in range(6)
            ]
            system.learned_knowledge['failed_responses'] = [{'response': 'bad', 'question': 'q'}]
            system._update_response_strategies()
            assert 'response_strategies' in system.learned_knowledge
            assert 'tax_question' in system.learned_knowledge['response_strategies']

    def test_update_response_strategies_few_responses(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.learned_knowledge['successful_responses']['tax_question'] = [
                {'response': 'ok', 'question': 'q'}
                for _ in range(3)
            ]
            system._update_response_strategies()
            assert 'response_strategies' not in system.learned_knowledge

    # ------------------------------------------------------------------
    # _find_common_elements — lines 395-418
    # ------------------------------------------------------------------
    def test_find_common_elements(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            responses = [
                {'response': 'Hello! ✅ Check your email now'},
                {'response': 'Welcome! ✅ Verify account please'},
                {'response': 'Done! ⚠️ Review required'},
            ]
            result = system._find_common_elements(responses)
            assert 'emojis_used' in result
            assert result['emojis_used']['✅'] >= 2
            assert 'keywords_used' in result
            assert len(result['response_length']) == 3

    # ------------------------------------------------------------------
    # _improve_context_understanding — lines 423-437
    # ------------------------------------------------------------------
    def test_improve_context_understanding(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            for i in range(5):
                system.interactions.append({
                    'question': 'vat calculation',
                    'response': 'tax response',
                    'success': True,
                    'context': f'tenant_1_user_{i}',
                })
            system._improve_context_understanding()
            assert 'context_understanding' in system.learned_knowledge
            assert 'tax_question' in system.learned_knowledge['context_understanding']

    def test_improve_context_understanding_insufficient_contexts(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            for i in range(2):
                system.interactions.append({
                    'question': 'vat calculation',
                    'response': 'tax response',
                    'success': True,
                    'context': f'tenant_1',
                })
            system._improve_context_understanding()
            assert 'context_understanding' in system.learned_knowledge
            assert 'tax_question' not in system.learned_knowledge['context_understanding']

    # ------------------------------------------------------------------
    # get_enhanced_response — lines 445-456
    # ------------------------------------------------------------------
    def test_get_enhanced_response_with_strategies(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.learned_knowledge['response_strategies'] = {
                'tax_question': {
                    'common_elements': {
                        'emojis_used': Counter(['✅', '📋']),
                        'response_length': [50, 60, 70],
                        'keywords_used': Counter(),
                    },
                    'success_rate': 0.9,
                    'last_updated': datetime.now().isoformat(),
                }
            }
            result = system.get_enhanced_response("what is vat rate?", "The vat rate is 5%")
            assert result == "The vat rate is 5%"

    def test_get_enhanced_response_no_strategies(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            result = system.get_enhanced_response("hello", "hi there")
            assert result == "hi there"

    # ------------------------------------------------------------------
    # _apply_response_strategies — lines 460-475
    # ------------------------------------------------------------------
    def test_apply_response_strategies_with_emojis(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            strategies = {
                'common_elements': {
                    'emojis_used': Counter(['✅', '📋', '⚠️']),
                    'response_length': [100, 120, 130],
                    'keywords_used': Counter(),
                },
                'success_rate': 0.9,
            }
            result = system._apply_response_strategies("Short response", strategies)
            assert result == "Short response"

    def test_apply_response_strategies_no_common_elements(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            result = system._apply_response_strategies("Plain response", {})
            assert result == "Plain response"

    # ------------------------------------------------------------------
    # learn_from_groq_feedback — lines 479-503
    # ------------------------------------------------------------------
    def test_learn_from_groq_feedback(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            learning_data = {
                'question': 'what is vat?',
                'local_answer': 'vat is tax',
                'improved_answer': 'VAT (Value Added Tax) is 5% in UAE',
                'timestamp': datetime.now().isoformat(),
            }
            system.learn_from_groq_feedback(learning_data)
            assert hasattr(system, 'groq_training_log')
            assert len(system.groq_training_log) == 1
            assert system.groq_training_log[0]['question'] == 'what is vat?'

    def test_learn_from_groq_feedback_truncates_log(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            for i in range(105):
                system.learn_from_groq_feedback({
                    'question': f'q{i}',
                    'local_answer': f'local{i}',
                    'improved_answer': f'groq{i}',
                    'timestamp': datetime.now().isoformat(),
                })
            assert len(system.groq_training_log) == 100

    def test_learn_from_groq_feedback_error(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.learn_from_groq_feedback({})

    # ------------------------------------------------------------------
    # _analyze_improvements — lines 507-518
    # ------------------------------------------------------------------
    def test_analyze_improvements_normal(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            result = system._analyze_improvements("short", "longer and better answer with details")
            assert result['length_diff'] > 0
            assert result['quality_improved'] is True

    def test_analyze_improvements_none_inputs(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            result = system._analyze_improvements(None, None)
            assert 'timestamp' in result
            assert result['length_diff'] == 0

    def test_analyze_improvements_shorter_groq(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            result = system._analyze_improvements("long local answer here with many words", "short")
            assert result['length_diff'] < 0
            assert result['quality_improved'] is False

    def test_analyze_improvements_exception(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)

            class BadStr:
                def __str__(self):
                    raise RuntimeError("str failed")

            result = system._analyze_improvements(BadStr(), "ok")
            assert 'timestamp' in result

    # ------------------------------------------------------------------
    # _load_patterns — line 89 (successful pickle load)
    # ------------------------------------------------------------------
    def test_load_patterns_fallback_default(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            result = system._load_patterns()
            assert isinstance(result['question_patterns'], defaultdict)
            assert isinstance(result['success_patterns'], defaultdict)

    def test_load_patterns_successful_pickle(self, app, tmp_path):
        import pickle
        from collections import defaultdict
        with app.app_context():
            system = self._make_system(app, tmp_path)
            patterns_data = {
                'question_patterns': defaultdict(list, {'vat': [{'q': 'test'}]}),
                'response_patterns': defaultdict(list),
                'success_patterns': defaultdict(float, {'tax': 0.9}),
                'time_patterns': defaultdict(int),
                'user_behavior': defaultdict(dict),
            }
            with open(system.patterns_file, 'wb') as f:
                pickle.dump(patterns_data, f)
            result = system._load_patterns()
            assert result['question_patterns']['vat'][0]['q'] == 'test'
            assert result['success_patterns']['tax'] == 0.9
