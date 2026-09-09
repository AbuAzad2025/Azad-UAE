"""Coverage tests for ai_knowledge/agents/master_brain.py uncovered arcs."""

from __future__ import annotations

from ai_knowledge.agents.master_brain import MasterBrain


class TestCovMasterBrainNeural:
    def test_classification_falls_through_469_476(self):
        result = MasterBrain._use_neural_if_needed("classification", {})
        assert result is None

    def test_pricing_without_product_falls_through_469_476(self):
        result = MasterBrain._use_neural_if_needed("pricing", {})
        assert result is None


class TestCovMasterBrainSynthesize:
    def test_sensors_no_match_519_518(self):
        brain = MasterBrain()
        knowledge = {
            "sensors": {
                "P0113": {"name_ar": "حساس حرارة", "function": "قياس", "testing": "افحص"},
                "P0123": {"name_ar": "حساس دواسة", "function": "قياس", "testing": "افحص"},
            }
        }
        result = brain._synthesize_answer("مرحبا كيف حالك", {"steps": []}, {}, knowledge, "question")
        assert "دعني أفكر" in result["text"] or "فهمت سؤالك" in result["text"]

    def test_sensor_match_without_testing_522_524(self):
        brain = MasterBrain()
        knowledge = {
            "sensors": {
                "ABC": {"name_ar": "حساس ABC", "function": "قياس الهواء"},
            }
        }
        result = brain._synthesize_answer("ما هو ABC؟", {"steps": []}, {}, knowledge, "question")
        assert "حساس ABC" in result["text"]
        assert "الفحص" not in result["text"]

    def test_sensor_match_with_testing(self):
        brain = MasterBrain()
        knowledge = {
            "sensors": {
                "XYZ": {"name_ar": "حساس XYZ", "function": "قياس", "testing": "افحص بالجهاز"},
            }
        }
        result = brain._synthesize_answer("أخبرني عن XYZ", {"steps": []}, {}, knowledge, "question")
        assert "افحص بالجهاز" in result["text"]


class TestCovMasterBrainExplain:
    def test_explain_skips_non_dict_domain_665_664(self):
        brain = MasterBrain()
        brain.knowledge_base = {
            "str_domain": "just a plain string, not a dict",
            "accounting": {"principles": {"accrual": "مبدأ الاستحقاق"}},
        }
        result = brain.explain("accrual")
        assert "الاستحقاق" in result

    def test_explain_skips_non_dict_value_667_666(self):
        brain = MasterBrain()
        brain.knowledge_base = {
            "test": {
                "simple_key": "simple string value",
                "nested": {"accrual": "مبدأ الاستحقاق - الشرح"},
            }
        }
        result = brain.explain("accrual")
        assert "الاستحقاق" in result
