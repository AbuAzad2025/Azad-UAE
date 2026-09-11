"""Broad coverage for ai_knowledge/core/learning_system.py remaining arcs."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from unittest.mock import patch

import pytest

from ai_knowledge.core.learning_system import AzadLearningSystem


@pytest.fixture
def cov4_knowledge_path(tmp_path):
    with patch("ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)):
        yield tmp_path


def _fresh_ls():
    return AzadLearningSystem()


class TestCov4LearningLoads:
    def test_load_knowledge_corrupt_json_falls_back(self, cov4_knowledge_path):
        (cov4_knowledge_path / "learned_knowledge.json").write_text("{broken", encoding="utf-8")
        ls = _fresh_ls()
        assert ls.learned_knowledge["learning_stats"]["total_interactions"] == 0

    def test_load_knowledge_unreadable_falls_back(self, cov4_knowledge_path):
        (cov4_knowledge_path / "learned_knowledge.json").mkdir()
        ls = _fresh_ls()
        assert ls.learned_knowledge["new_terms"] == {}

    def test_load_knowledge_valid_normalizes_expertise(self, cov4_knowledge_path):
        (cov4_knowledge_path / "learned_knowledge.json").write_text(
            json.dumps({"expertise_areas": {"ضريبة": 2}}), encoding="utf-8"
        )
        ls = _fresh_ls()
        assert isinstance(ls.learned_knowledge["expertise_areas"], defaultdict)
        assert ls.learned_knowledge["expertise_areas"]["ضريبة"] == 2

    def test_load_interactions_valid_and_corrupt(self, cov4_knowledge_path):
        (cov4_knowledge_path / "interactions_log.json").write_text(json.dumps([{"question": "q"}]), encoding="utf-8")
        assert _fresh_ls().interactions == [{"question": "q"}]
        (cov4_knowledge_path / "interactions_log.json").write_text("oops{", encoding="utf-8")
        assert _fresh_ls().interactions == []

    def test_load_feedback_valid_and_corrupt(self, cov4_knowledge_path):
        (cov4_knowledge_path / "feedback_log.json").write_text(json.dumps([{"r": 5}]), encoding="utf-8")
        assert _fresh_ls().feedback_log == [{"r": 5}]
        (cov4_knowledge_path / "feedback_log.json").write_text("oops{", encoding="utf-8")
        assert _fresh_ls().feedback_log == []

    def test_load_patterns_non_dict_result_falls_back(self, cov4_knowledge_path):
        (cov4_knowledge_path / "patterns.json").write_text("{}", encoding="utf-8")

        class _Cov4NonDictPatterns(AzadLearningSystem):
            @staticmethod
            def _patterns_from_storage(data):
                return ["not", "a", "dict"]

        assert _Cov4NonDictPatterns().patterns["question_patterns"] == {}

    def test_load_patterns_valid_and_corrupt(self, cov4_knowledge_path):
        stored = {
            "question_patterns": {"ضريبة": [{"question": "q"}]},
            "success_patterns": {"tax_question": 0.8},
        }
        (cov4_knowledge_path / "patterns.json").write_text(json.dumps(stored), encoding="utf-8")
        ls = _fresh_ls()
        assert ls.patterns["question_patterns"]["ضريبة"] == [{"question": "q"}]
        assert ls.patterns["success_patterns"]["tax_question"] == 0.8
        (cov4_knowledge_path / "patterns.json").write_text("oops{", encoding="utf-8")
        assert _fresh_ls().patterns["question_patterns"] == {}


class TestCov4NormalizeAndStorage:
    def test_normalize_repairs_every_malformed_field(self):
        data = {
            "expertise_areas": ["not", "a", "dict"],
            "failed_responses": {},
            "successful_responses": [],
            "customer_preferences": [],
            "new_terms": [],
            "market_trends": "oops",
        }
        result = AzadLearningSystem._normalize_loaded_data(data)
        assert isinstance(result["expertise_areas"], defaultdict)
        assert result["failed_responses"] == []
        assert result["successful_responses"] == {}
        assert result["customer_preferences"] == {}
        assert result["new_terms"] == {}
        assert result["market_trends"] == {}
        assert result["learning_stats"]["total_interactions"] == 0

    def test_normalize_non_dict_returns_defaults(self):
        assert AzadLearningSystem._normalize_loaded_data([1, 2])["failed_responses"] == []

    def test_normalize_all_valid_keeps_values(self):
        data = {
            "expertise_areas": defaultdict(int, {"a": 1}),
            "failed_responses": [],
            "successful_responses": {},
            "customer_preferences": {},
            "new_terms": {"t": 1},
            "market_trends": {"m": 1},
            "learning_stats": {"total_interactions": 5},
        }
        result = AzadLearningSystem._normalize_loaded_data(data)
        assert result["expertise_areas"]["a"] == 1
        assert result["learning_stats"]["total_interactions"] == 5

    def test_patterns_storage_roundtrip(self):
        patterns = AzadLearningSystem._empty_patterns()
        patterns["question_patterns"]["ضريبة"].append({"question": "q"})
        plain = AzadLearningSystem._patterns_to_storage(patterns)
        assert plain["question_patterns"] == {"ضريبة": [{"question": "q"}]}
        assert set(plain) == {
            "question_patterns",
            "response_patterns",
            "success_patterns",
            "time_patterns",
            "user_behavior",
        }

    def test_patterns_from_storage_skips_non_dict_values(self):
        patterns = AzadLearningSystem._patterns_from_storage({"question_patterns": [1, 2], "oops": 1})
        assert patterns["question_patterns"] == {}
        assert patterns["success_patterns"] == {}

    def test_tenant_path_variants(self, cov4_knowledge_path):
        assert AzadLearningSystem._tenant_path("a.json").endswith("a.json")
        assert AzadLearningSystem._tenant_path("interactions_log.json", 9).endswith("interactions_log_tenant_9.json")

    def test_default_knowledge_shape(self):
        assert AzadLearningSystem._default_knowledge()["learning_stats"]["learning_rate"] == 0.0


class TestCov4LearnFromInteraction:
    def test_learn_with_tenant_persists_files(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learn_from_interaction("ما هي ضريبة VAT؟", "الضريبة 5%", tenant_id=11)
        assert (cov4_knowledge_path / "interactions_log_tenant_11.json").exists()
        assert (cov4_knowledge_path / "learned_knowledge_tenant_11.json").exists()
        prefs = ls.learned_knowledge["customer_preferences"]["11"]
        assert prefs["last_question"] == "ما هي ضريبة VAT؟"
        assert ls.learned_knowledge["learning_stats"]["total_interactions"] == 1

    def test_learn_without_tenant_writes_nothing(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learn_from_interaction("مرحبا", "أهلا بك")
        assert list(cov4_knowledge_path.iterdir()) == []
        assert ls.learned_knowledge["learning_stats"]["successful_answers"] == 1

    def test_learn_failure_records_failed_response(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learn_from_interaction("سؤال صعب", "جواب ضعيف", user_feedback=2)
        assert len(ls.learned_knowledge["failed_responses"]) == 1
        assert ls.learned_knowledge["learning_stats"]["successful_answers"] == 0

    def test_failed_responses_repaired_when_malformed(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learned_knowledge["failed_responses"] = {}
        ls.learn_from_interaction("سؤال", "جواب", user_feedback=1)
        assert isinstance(ls.learned_knowledge["failed_responses"], list)

    def test_success_rate_updates_existing_entry(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learn_from_interaction("ما هي ضريبة VAT؟", "جواب")
        assert ls.patterns["success_patterns"]["tax_question"] == 1.0
        ls.learn_from_interaction("ما هي ضريبة VAT؟", "جواب سيئ", user_feedback=1)
        assert ls.patterns["success_patterns"]["tax_question"] == pytest.approx(0.9)

    def test_second_success_appends_to_existing_type(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learn_from_interaction("ما هي ضريبة VAT؟", "جواب أول")
        ls.learn_from_interaction("كم ضريبة VAT المستحقة؟", "جواب ثان")
        assert len(ls.learned_knowledge["successful_responses"]["tax_question"]) == 2


class TestCov4ClassifyExtract:
    def test_classify_every_branch(self):
        cases = {
            "ما هي ضريبة VAT؟": "tax_question",
            "رسوم customs والاستيراد؟": "customs_question",
            "أحتاج قطعة محرك engine؟": "parts_question",
            "كم مخزون stock لدينا؟": "inventory_question",
            "تحليل مبيعات sales؟": "sales_question",
            "خدمة عميل customer؟": "customer_question",
            "توقع predict الطلب؟": "prediction_question",
            "مرحبا كيف حالك؟": "general_question",
        }
        for text, expected in cases.items():
            assert AzadLearningSystem._classify_question(text.lower()) == expected

    def test_extract_keywords_match_and_empty(self):
        assert "ضريبة" in AzadLearningSystem._extract_keywords("ما هي ضريبة المبيعات")
        assert AzadLearningSystem._extract_keywords("مرحبا يا صديقي") == []


class TestCov4SaveTenantData:
    def test_expertise_dict_error_falls_back(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learned_knowledge["expertise_areas"] = 5
        ls._save_tenant_data(7)
        saved = json.loads((cov4_knowledge_path / "learned_knowledge_tenant_7.json").read_text(encoding="utf-8"))
        assert saved["expertise_areas"] == {}

    def test_non_dict_prefs_skipped(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learned_knowledge["customer_preferences"] = ["oops"]
        ls._save_tenant_data(7)
        saved = json.loads((cov4_knowledge_path / "learned_knowledge_tenant_7.json").read_text(encoding="utf-8"))
        assert saved["customer_preferences"] == ["oops"]

    def test_unserializable_interaction_warns_without_raise(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.interactions.append({"context": {"tenant_id": 9}, "blob": object()})
        ls._save_tenant_data(9)

    def test_save_data_is_noop(self, cov4_knowledge_path):
        assert _fresh_ls()._save_data() is None


class TestCov4StatsInsights:
    def test_update_stats_empty(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls._update_stats()
        assert ls.learned_knowledge["learning_stats"]["learning_rate"] == 0

    def test_insights_tenant_filter(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.interactions = [
            {"success": True, "context": {"tenant_id": 1}},
            {"success": False, "context": {"tenant_id": 2}},
            {"success": True, "context": {}},
        ]
        scoped = ls.get_learning_insights(tenant_id=1)
        assert scoped["total_interactions"] == 1
        assert scoped["success_rate"] == 1.0
        assert ls.get_learning_insights()["total_interactions"] == 3

    def test_progress_tiers(self, cov4_knowledge_path):
        ls = _fresh_ls()
        for count, word in ((0, "مبتدئ"), (10, "متوسط"), (50, "متقدم"), (200, "خبير")):
            ls.interactions = [{}] * count
            assert word in ls._calculate_learning_progress()

    def test_recommendations_full(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learned_knowledge["expertise_areas"] = defaultdict(int, {"a": 1, "b": 5})
        ls.patterns["success_patterns"] = defaultdict(float, {"a": 0.5, "c": 0.9})
        ls.interactions = [{}, {}, {}]
        recs = ls._get_learning_recommendations()
        assert len(recs) == 3

    def test_recommendations_empty(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.interactions = [{}] * 150
        assert ls._get_learning_recommendations() == []

    def test_recommendations_no_weak_or_low_areas(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.patterns["success_patterns"] = defaultdict(float, {"a": 0.9, "b": 0.8})
        ls.interactions = [{}] * 150
        assert ls._get_learning_recommendations() == []

    def test_recommendations_empty_weak_list_skipped(self, cov4_knowledge_path):
        class _Cov4NoWeakItems(dict):
            def items(self):
                return []

        ls = _fresh_ls()
        ls.learned_knowledge["expertise_areas"] = _Cov4NoWeakItems({"a": 1})
        ls.interactions = [{}] * 150
        assert ls._get_learning_recommendations() == []


class TestCov4Evolve:
    def test_discover_new_terms_then_skip_known(self, cov4_knowledge_path):
        ls = _fresh_ls()
        found = ls._discover_new_terms([{"question": "What is ecm fault?"}])
        assert found == {"ecm"}
        assert ls._discover_new_terms([{"question": "ecm again"}]) == set()

    def test_update_strategies_builds_and_reuses(self, cov4_knowledge_path):
        ls = _fresh_ls()
        responses = [{"question": "q", "response": "رد ناجح مفصل 😊", "timestamp": "t"} for _ in range(6)]
        ls.learned_knowledge["successful_responses"] = {"tax_question": list(responses)}
        ls._update_response_strategies()
        assert "tax_question" in ls.learned_knowledge["response_strategies"]
        ls._update_response_strategies()
        assert ls.learned_knowledge["response_strategies"]["tax_question"]["success_rate"] == pytest.approx(1.0)

    def test_update_strategies_skips_small_samples(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learned_knowledge["successful_responses"] = {
            "tax_question": [{"question": "q", "response": "r", "timestamp": "t"}]
        }
        ls._update_response_strategies()
        assert "response_strategies" not in ls.learned_knowledge

    def test_find_common_elements(self):
        elements = AzadLearningSystem._find_common_elements(
            [{"response": "تقرير مبيعات ممتاز 😊"}, {"response": "تقرير مبيعات مفصل جدا"}]
        )
        assert elements["response_length"] == [len("تقرير مبيعات ممتاز 😊"), len("تقرير مبيعات مفصل جدا")]
        assert "مبيعات" in elements["keywords_used"]

    def test_improve_context_understanding_few_contexts(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.interactions = [
            {"question": "ما الضريبة؟", "context": {"a": 1}},
            {"question": "مرحبا", "context": {}},
            {"question": "مرحبا", "other": 1},
        ]
        ls._improve_context_understanding()
        assert ls.learned_knowledge.get("context_understanding", {}) == {}

    def test_improve_context_understanding_many_contexts(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.interactions = [{"question": f"ضريبة رقم {i}؟", "context": f"ctx-{i}"} for i in range(4)]
        ls._improve_context_understanding()
        entry = ls.learned_knowledge["context_understanding"]["tax_question"]
        assert entry["context_count"] == 4
        ls._improve_context_understanding()
        assert ls.learned_knowledge["context_understanding"]["tax_question"]["context_count"] == 4

    def test_evolve_knowledge_summary(self, cov4_knowledge_path):
        ls = _fresh_ls()
        result = ls.evolve_knowledge()
        assert result["strategies_updated"] is True
        assert result["context_improved"] is True


class TestCov4EnhancedResponse:
    def test_no_strategies_returns_base(self, cov4_knowledge_path):
        assert _fresh_ls().get_enhanced_response("مرحبا", "أهلا") == "أهلا"

    def test_unknown_type_returns_base(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learned_knowledge["response_strategies"] = {"tax_question": {"common_elements": {}}}
        assert ls.get_enhanced_response("مرحبا", "أهلا") == "أهلا"

    def test_matching_strategy_returns_response(self, cov4_knowledge_path):
        ls = _fresh_ls()
        ls.learned_knowledge["response_strategies"] = {
            "tax_question": {
                "common_elements": {
                    "emojis_used": Counter({"😊": 3}),
                    "response_length": [100, 120],
                }
            }
        }
        assert ls.get_enhanced_response("ما هي ضريبة VAT؟", "الضريبة 5%") == "الضريبة 5%"

    def test_apply_strategies_branches(self):
        short = AzadLearningSystem._apply_response_strategies(
            "hi", {"common_elements": {"emojis_used": Counter({"😊": 2}), "response_length": [100, 120]}}
        )
        assert short == "hi"
        long_text = "x" * 500
        assert AzadLearningSystem._apply_response_strategies(long_text, {"common_elements": {}}) == long_text

    def test_apply_strategies_long_response_skips_extension(self):
        long_text = "x" * 500
        strategies = {"common_elements": {"response_length": [100, 120]}}
        assert AzadLearningSystem._apply_response_strategies(long_text, strategies) == long_text


class TestCov4GroqLearning:
    def test_feedback_success_trims_log(self, cov4_knowledge_path, capsys):
        ls = _fresh_ls()
        ls.groq_training_log = [{"q": i} for i in range(100)]
        ls.learn_from_groq_feedback(
            {
                "question": "ما الضريبة؟",
                "local_answer": "لا أعرف",
                "improved_answer": "الضريبة 5%",
                "timestamp": "2026-01-01",
            }
        )
        assert len(ls.groq_training_log) == 100
        assert "Groq training error" in capsys.readouterr().out

    def test_feedback_missing_keys_prints_error(self, cov4_knowledge_path, capsys):
        _fresh_ls().learn_from_groq_feedback({})
        assert "Groq training error" in capsys.readouterr().out

    def test_feedback_short_log_skips_trim(self, cov4_knowledge_path, capsys):
        ls = _fresh_ls()
        ls.learn_from_groq_feedback(
            {
                "question": "ما الضريبة؟",
                "local_answer": "لا أعرف",
                "improved_answer": "الضريبة 5%",
                "timestamp": "2026-01-01",
            }
        )
        assert len(ls.groq_training_log) == 1
        assert "Groq training error" in capsys.readouterr().out

    def test_analyze_improvements_with_nones(self):
        result = AzadLearningSystem._analyze_improvements(None, None)
        assert result["length_diff"] == 0
        assert result["quality_improved"] is False
