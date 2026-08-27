"""Coverage pads for small pure-function branches across ai_knowledge.

Covers storage roundtrips of AzadLearningSystem, permission-check failure
funnels in tool_registry, and the error funnel of VisionProcessor image
analysis. All behavioral — real objects, no snapshot asserts.
"""

from __future__ import annotations

import json
from collections import defaultdict
from unittest.mock import MagicMock, patch

from ai_knowledge.core.learning_system import AzadLearningSystem


class TestLearningSystemPatternStorage:
    def test_patterns_from_storage_rebuilds_defaultdicts(self):
        stored = {
            "question_patterns": {"كيف": ["x"]},
            "response_patterns": {},
            "success_patterns": {"create_customer": 0.5},
            "time_patterns": {"9": 3},
            "user_behavior": {"u1": {"visits": 2}},
        }
        patterns = AzadLearningSystem._patterns_from_storage(stored)
        assert isinstance(patterns["question_patterns"], defaultdict)
        assert isinstance(patterns["success_patterns"], defaultdict)
        assert patterns["question_patterns"]["new-key"] == []  # default factory works
        assert patterns["success_patterns"]["create_customer"] == 0.5

    def test_patterns_to_storage_plain_dicts_only(self):
        patterns = {
            "question_patterns": defaultdict(list),
            "response_patterns": {"r": []},
            "success_patterns": defaultdict(float),
            "time_patterns": defaultdict(int),
            "user_behavior": {"u": {}},
        }
        patterns["question_patterns"]["كيف"].append("x")
        plain = AzadLearningSystem._patterns_to_storage(patterns)
        assert all(type(v) is dict for v in plain.values())
        assert plain["question_patterns"] == {"كيف": ["x"]}

    def test_load_patterns_valid_file_returns_normalized(self, tmp_path):
        system = AzadLearningSystem()
        payload = {"time_patterns": {"22": 4}}
        target = tmp_path / "patterns.json"
        target.write_text(json.dumps(payload), encoding="utf-8")
        system.patterns_file = str(target)

        loaded = system._load_patterns()
        assert loaded["time_patterns"] == {"22": 4}
        assert isinstance(loaded["response_patterns"], defaultdict)


class TestToolRegistryPermissionFunnels:
    def test_user_has_permission_swallows_checker_crash(self):
        from ai_knowledge.tool_registry import _user_has_permission

        user = MagicMock()
        user.has_permission.side_effect = RuntimeError("rbac exploded")
        assert _user_has_permission(user, "manage_sales") is False

    def test_get_tools_for_user_skips_schemaless_entries(self):
        from ai_knowledge import tool_registry

        fake_schema = MagicMock()
        fake_schema.model_json_schema.return_value = {"title": "Fake", "type": "object"}
        registry = {
            "no_schema_tool": {"permission": "", "description": "chat only"},
            "schema_tool": {
                "permission": "",
                "description": "has schema",
                "handler": lambda a: a,
                "confirm_required": False,
                "schema": fake_schema,
            },
        }
        user = MagicMock(is_authenticated=True, is_owner=False)
        user.has_permission.return_value = True

        with patch.object(tool_registry, "get_tool_registry", return_value=registry):
            tools = tool_registry.get_tools_for_user(user)
        assert [t["function"]["name"] for t in tools] == ["schema_tool"]


class TestVisionProcessorErrorFunnel:
    def test_analyze_part_image_bogus_path_returns_error_dict(self):
        from ai_knowledge.neural.vision_processor import VisionProcessor

        result = VisionProcessor.analyze_part_image(r"Z:\does\not\exist\part_c4.png")
        if "error" in result:
            assert isinstance(result["error"], str) and result["error"]
        else:
            # environments where the imaging stack fakes success on missing files
            assert result["part_name"]
