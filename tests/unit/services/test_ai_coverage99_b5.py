"""Coverage-99 boost for services/ai_service.py — batch 5 (native tools, train, sharing, RAG)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.ai_service import AIService


def _result(**flags):
    res = MagicMock(message="m", **flags)
    for k in ("needs_confirmation", "needs_permission", "success"):
        if k not in flags:
            setattr(res, k, False)
    return res


class TestNativeTools:
    def _call(self, calls):
        from ai_knowledge.action_dispatcher import ActionDispatcher

        with (
            patch.object(ActionDispatcher, "dispatch", return_value=_result(success=True)),
            patch(
                "ai_knowledge.tool_schemas.validate_tool_args_safe",
                return_value=({}, None),
            ),
        ):
            return AIService._execute_native_tool_calls(calls, 1)

    def test_empty_and_no_name(self):
        assert "لم يتم" in AIService._execute_native_tool_calls([], 1)
        assert "لم يتم" in self._call([{}, {"function": {}}, None])

    def test_bad_json(self):
        out = self._call([{"function": {"name": "help", "arguments": "{bad"}}])
        assert "غير قابلة" in out

    def test_validation_error(self):
        from ai_knowledge.action_dispatcher import ActionDispatcher

        with (
            patch.object(ActionDispatcher, "dispatch"),
            patch(
                "ai_knowledge.tool_schemas.validate_tool_args_safe",
                return_value=({}, "need x"),
            ),
        ):
            out = AIService._execute_native_tool_calls([{"function": {"name": "help", "arguments": "{}"}}], 1)
        assert "need x" in out

    def test_dispatch_variants(self):
        from ai_knowledge.action_dispatcher import ActionDispatcher

        for flags, needle in [
            ({"needs_confirmation": True}, "⚠️"),
            ({"needs_permission": True}, "🚫"),
            ({"success": True}, "m"),
            ({}, "⚠️"),
        ]:
            with (
                patch.object(ActionDispatcher, "dispatch", return_value=_result(**flags)),
                patch(
                    "ai_knowledge.tool_schemas.validate_tool_args_safe",
                    return_value=({"a": 1}, None),
                ),
            ):
                out = AIService._execute_native_tool_calls([{"function": {"name": "help", "arguments": {"a": 1}}}], 1)
            assert needle in out

    def test_outer_exception(self):
        with patch(
            "ai_knowledge.tool_schemas.validate_tool_args_safe",
            side_effect=RuntimeError("x"),
        ):
            out = AIService._execute_native_tool_calls([{"function": {"name": "help", "arguments": "{}"}}], 1)
        assert "خطأ" in out


class TestTrain:
    def test_ok_and_error(self):
        from ai_knowledge.core.learning_system import learning_system

        with patch.object(learning_system, "learn_from_groq_feedback", return_value=None):
            AIService._train_local_from_groq("q", "l", "g", 1, tenant_id=2)
        with patch.object(learning_system, "learn_from_groq_feedback", side_effect=RuntimeError("x")):
            AIService._train_local_from_groq("q", "l", "g", 1)


class TestSharing:
    def test_no_tid(self):
        assert AIService._is_ai_external_sharing_enabled(MagicMock(tenant_id=None)) is True
        assert AIService._is_ai_external_sharing_enabled(MagicMock(tenant_id="x")) is True
        assert AIService._is_ai_external_sharing_enabled(None) is True

    def test_tenant_variants(self):
        with patch("services.ai_service.db.session") as sess:
            sess.get.return_value = None
            assert AIService._is_ai_external_sharing_enabled(MagicMock(tenant_id=3)) is True
            sess.get.return_value = MagicMock(ai_external_sharing_enabled=False)
            assert AIService._is_ai_external_sharing_enabled(MagicMock(tenant_id=3)) is False
            sess.get.return_value = MagicMock(ai_external_sharing_enabled=True)
            assert AIService._is_ai_external_sharing_enabled(MagicMock(tenant_id=3)) is True

    def test_exception(self):
        with patch("services.ai_service.db.session.get", side_effect=RuntimeError("x")):
            assert AIService._is_ai_external_sharing_enabled(MagicMock(tenant_id=3)) is True


class TestRagIntent:
    def test_each(self):
        assert AIService._detect_rag_intent("فاتورة بيع") == "sales"
        assert AIService._detect_rag_intent("مخزون المنتجات") == "inventory"
        assert AIService._detect_rag_intent("رصيد العميل") == "customer"
        assert AIService._detect_rag_intent("تقرير الأرباح") == "finance"
        assert AIService._detect_rag_intent("مرحبا") == "overview"

    def test_exception(self):
        assert AIService._detect_rag_intent(None) == "overview"


class TestGatherIntent:
    def _user(self):
        u = MagicMock()
        u.tenant_id = 9
        u.username = "ali"
        u.role = MagicMock(name_ar="مدير")
        return u

    def _db(self):
        sess = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.filter_by.return_value = q
        q.count.return_value = 2
        q.scalar.return_value = 50
        sess.query.return_value = q
        return sess

    def test_no_user(self):
        with patch("flask_login.current_user") as cu:
            cu.is_authenticated = False
            out = AIService._gather_intent_knowledge("مرحبا", {"context": {}})
        assert "هوية" in out

    def test_sharing_disabled(self):
        with patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=False):
            out = AIService._gather_intent_knowledge("مرحبا", {"context": {"current_user": self._user()}})
        assert "الخصوصية" in out

    def test_each_intent(self):
        for msg in ["فاتورة بيع", "مخزون", "عميل", "مصروف", "مرحبا"]:
            with (
                patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=True),
                patch("services.ai_service.db.session", self._db()),
                patch("utils.tenanting.scoped_user_query") as sq,
                patch("flask.current_app") as app,
            ):
                sq.return_value.count.return_value = 1
                app.config = {"COMPANY_NAME_AR": "C", "COMPANY_PHONE": "P"}
                out = AIService._gather_intent_knowledge(msg, {"context": {"current_user": self._user()}})
            assert "نطاق" in out

    def test_user_no_role(self):
        u = self._user()
        u.role = None
        with (
            patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=True),
            patch("services.ai_service.db.session", self._db()),
            patch("utils.tenanting.scoped_user_query") as sq,
            patch("flask.current_app") as app,
        ):
            sq.return_value.count.return_value = 1
            app.config = {"COMPANY_NAME_AR": "C", "COMPANY_PHONE": "P"}
            out = AIService._gather_intent_knowledge("مرحبا", {"context": {"current_user": u}})
        assert "غير محدد" in out

    def test_exception(self):
        with patch.object(AIService, "_is_ai_external_sharing_enabled", side_effect=RuntimeError("x")):
            out = AIService._gather_intent_knowledge("مرحبا", {"context": {}})
        assert "خطأ" in out or "هوية" in out
