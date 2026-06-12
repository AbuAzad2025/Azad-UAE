"""Tests for ai_knowledge/agents_core.py"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import datetime as dt


class TestAgentsCore:
    """Test intelligent_response, _check_llm_availability, _get_llm_response, _build_system_prompt."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _mock_datetime_utcnow(self, monkeypatch, hour):
        mock_dt = Mock(wraps=dt.datetime)
        mock_dt.utcnow = Mock(return_value=Mock(hour=hour))
        monkeypatch.setattr("datetime.datetime", mock_dt)

    def _mock_dispatcher(self, monkeypatch, parse_result=None, dispatch_result=None, help_text=""):
        mock_disp = Mock()
        if isinstance(parse_result, Mock):
            mock_disp.parse_chat_action = parse_result
        else:
            mock_disp.parse_chat_action = Mock(return_value=parse_result)
        if dispatch_result is not None:
            mock_disp.dispatch = Mock(return_value=dispatch_result)
        mock_disp.format_help = Mock(return_value=help_text)
        monkeypatch.setattr("ai_knowledge.action_dispatcher.action_dispatcher", mock_disp)
        return mock_disp

    def _stub_trainer(self, monkeypatch):
        mock_tr = Mock()
        mock_tr.seed = Mock()
        mock_tr.learn_from_interaction = Mock()
        monkeypatch.setattr("ai_knowledge.trainer.trainer", mock_tr)
        return mock_tr

    # ------------------------------------------------------------------
    # intelligent_response
    # ------------------------------------------------------------------

    def test_intelligent_response_greeting_morning(self, app, monkeypatch):
        from ai_knowledge.agents_core import intelligent_response
        self._mock_datetime_utcnow(monkeypatch, 8)
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(monkeypatch, parse_result=("greeting", {"name": "Ahmed"}), help_text="مساعدة")

        with app.app_context():
            result = intelligent_response("hello", user_id=1)

        assert "صباح الخير" in result
        assert "أنا أزاد" in result
        assert "Ahmed" in result

    def test_intelligent_response_greeting_evening(self, app, monkeypatch):
        from ai_knowledge.agents_core import intelligent_response
        self._mock_datetime_utcnow(monkeypatch, 15)
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(monkeypatch, parse_result=("greeting", {"name": ""}), help_text="مساعدة")

        with app.app_context():
            result = intelligent_response("hello", user_id=1)

        assert "مساء الخير" in result
        assert "أنا أزاد" in result

    def test_intelligent_response_greeting_night(self, app, monkeypatch):
        from ai_knowledge.agents_core import intelligent_response
        self._mock_datetime_utcnow(monkeypatch, 20)
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(monkeypatch, parse_result=("greeting", {"name": ""}), help_text="مساعدة")

        with app.app_context():
            result = intelligent_response("hello", user_id=1)

        assert "مساء النور" in result

    def test_intelligent_response_help(self, app, monkeypatch):
        from ai_knowledge.agents_core import intelligent_response
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(monkeypatch, parse_result=("help", {}), help_text="قائمة المساعدة")

        with app.app_context():
            result = intelligent_response("help", user_id=1)

        assert result == "قائمة المساعدة"

    def test_intelligent_response_dispatch_success(self, app, monkeypatch):
        from ai_knowledge.agents_core import intelligent_response
        from ai_knowledge.action_dispatcher import ActionResult
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(
            monkeypatch,
            parse_result=("search_customer", {"name": "test"}),
            dispatch_result=ActionResult(True, "تم العثور على العميل"),
        )

        with app.app_context():
            result = intelligent_response("ابحث عن عميل test", user_id=1)

        assert "تم العثور على العميل" in result

    def test_intelligent_response_needs_permission(self, app, monkeypatch):
        from ai_knowledge.agents_core import intelligent_response
        from ai_knowledge.action_dispatcher import ActionResult
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(
            monkeypatch,
            parse_result=("delete_product", {"id": 5}),
            dispatch_result=ActionResult(False, "تحتاج صلاحية admin", needs_permission="admin"),
        )

        with app.app_context():
            result = intelligent_response("احذف المنتج 5", user_id=1)

        assert "⚠️" in result

    def test_intelligent_response_dispatch_failure_no_permission(self, app, monkeypatch):
        from ai_knowledge.agents_core import intelligent_response
        from ai_knowledge.action_dispatcher import ActionResult
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(
            monkeypatch,
            parse_result=("some_action", {}),
            dispatch_result=ActionResult(False, "فشلت العملية", needs_permission=""),
        )

        with app.app_context():
            result = intelligent_response("do something", user_id=1)

        assert result == "فشلت العملية"

    def test_intelligent_response_fallback_to_assistant(self, app, monkeypatch):
        import ai_knowledge.agents_core as ac_core
        from ai_knowledge.agents_core import intelligent_response
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(monkeypatch, parse_result=None)

        mock_assistant = Mock()
        mock_assistant.process = Mock(return_value={"response": "رد من المساعد"})
        monkeypatch.setattr(ac_core, "intelligent_assistant", mock_assistant)

        with app.app_context():
            result = intelligent_response("كيف حالك؟", user_id=1)

        assert result == "رد من المساعد"

    def test_intelligent_response_fallback_no_response_key(self, app, monkeypatch):
        import ai_knowledge.agents_core as ac_core
        from ai_knowledge.agents_core import intelligent_response
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(monkeypatch, parse_result=None)

        mock_assistant = Mock()
        mock_assistant.process = Mock(return_value={})
        monkeypatch.setattr(ac_core, "intelligent_assistant", mock_assistant)

        with app.app_context():
            result = intelligent_response("test", user_id=1)

        assert "عذراً، حدث خطأ" in result

    def test_intelligent_response_error_handling(self, app, monkeypatch):
        from ai_knowledge.agents_core import intelligent_response
        self._stub_trainer(monkeypatch)
        self._mock_dispatcher(monkeypatch, parse_result=Mock(side_effect=ValueError("test error")))
        monkeypatch.setattr("ai_knowledge.action_dispatcher._log_ai_error", Mock())

        with app.app_context():
            result = intelligent_response("hello", user_id=1)

        assert "عذراً، حدث خطأ أثناء المعالجة" in result

    # ------------------------------------------------------------------
    # _check_llm_availability
    # ------------------------------------------------------------------

    def test_check_llm_availability_with_groq(self, app, monkeypatch):
        from ai_knowledge.agents_core import _check_llm_availability
        monkeypatch.setattr("ai_knowledge.agents_core._llm_available", None)
        monkeypatch.setattr("os.environ.get", lambda k, d=None: "sk-groq-xxx" if k == "GROQ_API_KEY" else d)

        with app.app_context():
            result = _check_llm_availability()
        assert result is True

    def test_check_llm_availability_with_gemini(self, app, monkeypatch):
        from ai_knowledge.agents_core import _check_llm_availability
        monkeypatch.setattr("ai_knowledge.agents_core._llm_available", None)
        monkeypatch.setattr("os.environ.get", lambda k, d=None: "AIza-xxx" if k == "GEMINI_API_KEY" else d)

        with app.app_context():
            result = _check_llm_availability()
        assert result is True

    def test_check_llm_availability_with_openai(self, app, monkeypatch):
        from ai_knowledge.agents_core import _check_llm_availability
        monkeypatch.setattr("ai_knowledge.agents_core._llm_available", None)
        monkeypatch.setattr("os.environ.get", lambda k, d=None: "sk-openai-xxx" if k == "OPENAI_API_KEY" else d)

        with app.app_context():
            result = _check_llm_availability()
        assert result is True

    def test_check_llm_availability_no_keys(self, app, monkeypatch):
        from ai_knowledge.agents_core import _check_llm_availability
        monkeypatch.setattr("ai_knowledge.agents_core._llm_available", None)
        monkeypatch.setattr("os.environ.get", lambda k, d=None: None)

        with app.app_context():
            result = _check_llm_availability()
        assert result is False

    def test_check_llm_availability_cached(self, app, monkeypatch):
        from ai_knowledge.agents_core import _check_llm_availability
        monkeypatch.setattr("ai_knowledge.agents_core._llm_available", True)
        env_get = Mock()
        monkeypatch.setattr("os.environ.get", env_get)

        with app.app_context():
            result = _check_llm_availability()

        assert result is True
        env_get.assert_not_called()

    # ------------------------------------------------------------------
    # _get_llm_response
    # ------------------------------------------------------------------

    def test_get_llm_response_groq_success(self, app, monkeypatch):
        from ai_knowledge.agents_core import _get_llm_response
        monkeypatch.setattr("os.environ.get", lambda k, d=None: "sk-groq-xxx" if k == "GROQ_API_KEY" else d)

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "رد من Groq"}}]}
        monkeypatch.setattr("requests.post", Mock(return_value=mock_resp))

        with app.app_context():
            result = _get_llm_response("system prompt", "user message")
        assert result == "رد من Groq"

    def test_get_llm_response_groq_fails_gemini_success(self, app, monkeypatch):
        from ai_knowledge.agents_core import _get_llm_response

        def env_get(key, default=None):
            vals = {"GROQ_API_KEY": "sk-groq-xxx", "GEMINI_API_KEY": "AIza-xxx"}
            return vals.get(key, default)

        monkeypatch.setattr("os.environ.get", env_get)

        mock_groq_resp = Mock()
        mock_groq_resp.status_code = 400
        mock_gemini_resp = Mock()
        mock_gemini_resp.status_code = 200
        mock_gemini_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "رد من Gemini"}]}}]
        }

        def mock_post(url, **kwargs):
            if "groq" in url:
                return mock_groq_resp
            return mock_gemini_resp

        monkeypatch.setattr("requests.post", mock_post)

        with app.app_context():
            result = _get_llm_response("system prompt", "user message")
        assert result == "رد من Gemini"

    def test_get_llm_response_all_fail(self, app, monkeypatch):
        from ai_knowledge.agents_core import _get_llm_response
        monkeypatch.setattr("os.environ.get", lambda k, d=None: "sk-groq-xxx" if k == "GROQ_API_KEY" else d)

        mock_resp = Mock()
        mock_resp.status_code = 400
        monkeypatch.setattr("requests.post", Mock(return_value=mock_resp))

        with app.app_context():
            result = _get_llm_response("system prompt", "user message")
        assert result is None

    def test_get_llm_response_no_keys(self, app, monkeypatch):
        from ai_knowledge.agents_core import _get_llm_response
        monkeypatch.setattr("os.environ.get", lambda k, d=None: None)
        monkeypatch.setattr("requests.post", Mock(side_effect=Exception("should not be called")))

        with app.app_context():
            result = _get_llm_response("system prompt", "user message")
        assert result is None

    # ------------------------------------------------------------------
    # _build_system_prompt
    # ------------------------------------------------------------------

    def test_build_system_prompt_basic(self, app, monkeypatch):
        from ai_knowledge.agents_core import _build_system_prompt
        monkeypatch.setattr("ai_knowledge.system_knowledge.search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr("ai_knowledge.system_knowledge.SYSTEM_INFO", {
            "name_ar": "أزاديكسا",
            "version": "1.0"
        })
        monkeypatch.setattr("ai_knowledge.system_knowledge.ROLES", [])

        with app.app_context():
            result = _build_system_prompt("ما هو نظام المحاسبة؟")

        assert "أزاديكسا" in result
        assert "v1.0" in result
        assert "أجب باللغة العربية" in result

    def test_build_system_prompt_with_knowledge(self, app, monkeypatch):
        from ai_knowledge.agents_core import _build_system_prompt
        monkeypatch.setattr("ai_knowledge.system_knowledge.search_knowledge", Mock(return_value=[
            {"type": "model", "name": "Sale", "info": {"table": "sales"}},
            {"type": "permission", "code": "manage_sales", "info": {"name_ar": "إدارة المبيعات", "name": "Manage Sales"}},
            {"type": "feature", "name": "pos", "info": {"name_ar": "نقطة البيع", "description": "نظام نقاط البيع"}},
        ]))
        monkeypatch.setattr("ai_knowledge.system_knowledge.SYSTEM_INFO", {
            "name_ar": "أزاديكسا",
            "version": "2.0"
        })
        monkeypatch.setattr("ai_knowledge.system_knowledge.ROLES", [])

        with app.app_context():
            result = _build_system_prompt("المبيعات")

        assert "المعرفة المتعلقة بالسؤال" in result
        assert "Sale" in result
        assert "sales" in result
        assert "manage_sales" in result
        assert "إدارة المبيعات" in result
        assert "نقطة البيع" in result
        assert "v2.0" in result

    def test_build_system_prompt_with_role(self, app, monkeypatch):
        from ai_knowledge.agents_core import _build_system_prompt
        monkeypatch.setattr("ai_knowledge.system_knowledge.search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr("ai_knowledge.system_knowledge.SYSTEM_INFO", {
            "name_ar": "أزاديكسا",
            "version": "1.0"
        })
        monkeypatch.setattr("ai_knowledge.system_knowledge.ROLES", [
            {"slug": "admin", "name_ar": "مدير النظام"},
            {"slug": "accountant", "name_ar": "محاسب"},
        ])

        with app.app_context():
            result = _build_system_prompt("الراتب", user_role="accountant")

        assert "محاسب" in result
        assert "دور المستخدم" in result

    def test_build_system_prompt_role_not_found(self, app, monkeypatch):
        from ai_knowledge.agents_core import _build_system_prompt
        monkeypatch.setattr("ai_knowledge.system_knowledge.search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr("ai_knowledge.system_knowledge.SYSTEM_INFO", {
            "name_ar": "أزاديكسا",
            "version": "1.0"
        })
        monkeypatch.setattr("ai_knowledge.system_knowledge.ROLES", [
            {"slug": "admin", "name_ar": "مدير النظام"},
        ])

        with app.app_context():
            result = _build_system_prompt("test", user_role="nonexistent")

        assert "دور المستخدم" not in result

    def test_build_system_prompt_knowledge_limit_five(self, app, monkeypatch):
        from ai_knowledge.agents_core import _build_system_prompt
        monkeypatch.setattr("ai_knowledge.system_knowledge.search_knowledge", Mock(return_value=[
            {"type": "feature", "name": f"f{i}", "info": {"name_ar": f"ميزة {i}", "description": "test"}}
            for i in range(10)
        ]))
        monkeypatch.setattr("ai_knowledge.system_knowledge.SYSTEM_INFO", {
            "name_ar": "أزاديكسا",
            "version": "1.0"
        })
        monkeypatch.setattr("ai_knowledge.system_knowledge.ROLES", [])

        with app.app_context():
            result = _build_system_prompt("test")

        assert result.count("- ميزة") == 5

    # ------------------------------------------------------------------
    # ask_azad_enhanced (bonus - covers error, fallback, FAQ, LLM paths)
    # ------------------------------------------------------------------

    def test_ask_azad_enhanced_faq_match(self, app, monkeypatch):
        import ai_knowledge.system_knowledge as sys_know
        from ai_knowledge.agents_core import ask_azad_enhanced
        monkeypatch.setattr(sys_know, "search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr(sys_know, "FAQ", {
            "general": [
                {"q": "ما هو نظام أزاديكسا", "a": "نظام متكامل لإدارة الأعمال"}
            ]
        })
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock())

        with app.app_context():
            result = ask_azad_enhanced("أخبرني ما هو نظام أزاديكسا؟", user_id=1)

        assert result["answer"] == "نظام متكامل لإدارة الأعمال"
        assert result["source"] == "faq"

    def test_ask_azad_enhanced_knowledge_path(self, app, monkeypatch):
        import ai_knowledge.agents_core as ac_core
        import ai_knowledge.system_knowledge as sys_know
        from ai_knowledge.agents_core import ask_azad_enhanced
        monkeypatch.setattr(ac_core, "_check_llm_availability", Mock(return_value=False))
        monkeypatch.setattr(sys_know, "search_knowledge", Mock(return_value=[
            {"type": "model", "name": "Product", "info": {
                "table": "products",
                "fields": {"name": "string", "price": "decimal"}
            }}
        ]))
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock())

        with app.app_context():
            result = ask_azad_enhanced("منتجات", user_id=1)

        assert "مودل Product" in result["answer"]
        assert result["source"] == "system_knowledge"

    def test_ask_azad_enhanced_llm_path(self, app, monkeypatch):
        import ai_knowledge.agents_core as ac_core
        import ai_knowledge.system_knowledge as sys_know
        from ai_knowledge.agents_core import ask_azad_enhanced
        monkeypatch.setattr(sys_know, "search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr(ac_core, "_check_llm_availability", Mock(return_value=True))
        monkeypatch.setattr(ac_core, "_build_system_prompt", Mock(return_value="prompt"))
        monkeypatch.setattr(ac_core, "_get_llm_response", Mock(return_value="رد من الـ LLM"))
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock())

        with app.app_context():
            result = ask_azad_enhanced("سؤال معقد", user_id=1)

        assert result["answer"] == "رد من الـ LLM"
        assert result["source"] == "llm"

    def test_ask_azad_enhanced_no_llm_falls_to_master_brain(self, app, monkeypatch):
        import ai_knowledge.agents_core as ac_core
        import ai_knowledge.system_knowledge as sys_know
        from ai_knowledge.agents_core import ask_azad_enhanced
        monkeypatch.setattr(ac_core, "_check_llm_availability", Mock(return_value=False))
        monkeypatch.setattr(sys_know, "search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr(sys_know, "FAQ", {})
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock())
        mock_brain = Mock()
        mock_brain.ask = Mock(return_value={"answer": "رد من العقل المركزي"})
        monkeypatch.setattr(ac_core, "get_master_brain", Mock(return_value=mock_brain))

        with app.app_context():
            result = ask_azad_enhanced("ما هو النظام؟", user_id=1)

        assert result["answer"] == "رد من العقل المركزي"
        assert result["source"] == "master_brain"

    def test_ask_azad_enhanced_full_fallback_to_error(self, app, monkeypatch):
        import ai_knowledge.agents_core as ac_core
        import ai_knowledge.system_knowledge as sys_know
        from ai_knowledge.agents_core import ask_azad_enhanced
        monkeypatch.setattr(ac_core, "_check_llm_availability", Mock(return_value=False))
        monkeypatch.setattr(sys_know, "search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr(ac_core, "get_master_brain", Mock(side_effect=Exception("brain crashed")))
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock())

        with app.app_context():
            result = ask_azad_enhanced("أي سؤال", user_id=1)

        assert "عذراً، حدث خطأ" in result["answer"]

    # ------------------------------------------------------------------
    # Exception handler coverage (lines 29, 50-51, 65, 85, 99, 122, 141, 223-233, 246-247, 266-267)
    # ------------------------------------------------------------------

    def test_intelligent_response_seed_exception(self, app, monkeypatch):
        """Cover line 29: trainer.seed() except block."""
        import ai_knowledge.agents_core as ac_core
        from ai_knowledge.agents_core import intelligent_response
        monkeypatch.setattr("ai_knowledge.trainer.trainer.seed", Mock(side_effect=Exception("seed failed")))
        self._mock_dispatcher(monkeypatch, parse_result=None)
        mock_assistant = Mock()
        mock_assistant.process = Mock(return_value={"response": "fallback"})
        monkeypatch.setattr(ac_core, "intelligent_assistant", mock_assistant)

        with app.app_context():
            result = intelligent_response("hello", user_id=1)
        assert result == "fallback"

    def test_intelligent_response_learn_exception(self, app, monkeypatch):
        """Cover lines 50-51: trainer.learn_from_interaction() except block."""
        from ai_knowledge.agents_core import intelligent_response
        from ai_knowledge.action_dispatcher import ActionResult
        self._stub_trainer(monkeypatch)
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock(side_effect=Exception("learn failed")))
        self._mock_dispatcher(
            monkeypatch,
            parse_result=("search_customer", {"name": "test"}),
            dispatch_result=ActionResult(True, "success"),
        )

        with app.app_context():
            result = intelligent_response("search", user_id=1)
        assert result == "success"

    def test_intelligent_response_outer_error_handler(self, app, monkeypatch):
        """Cover line 65: outer error handler except block."""
        import ai_knowledge.agents_core as ac_core
        from ai_knowledge.agents_core import intelligent_response
        self._stub_trainer(monkeypatch)
        mock_disp = Mock()
        mock_disp.parse_chat_action = Mock(side_effect=Exception("dispatcher crash"))
        monkeypatch.setattr("ai_knowledge.action_dispatcher.action_dispatcher", mock_disp)
        monkeypatch.setattr("ai_knowledge.action_dispatcher._log_ai_error", Mock())

        with app.app_context():
            result = intelligent_response("hello", user_id=1)
        assert "عذراً، حدث خطأ أثناء المعالجة" in result

    def test_check_llm_availability_dotenv_exception(self, app, monkeypatch):
        """Cover line 85: dotenv.load_dotenv() except block."""
        import builtins
        from ai_knowledge.agents_core import _check_llm_availability
        monkeypatch.setattr("ai_knowledge.agents_core._llm_available", None)
        real_import = builtins.__import__
        def broken_import(name, *args, **kwargs):
            if name == 'dotenv':
                raise ImportError("no dotenv")
            return real_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", broken_import)
        monkeypatch.setattr("os.environ.get", lambda k, d=None: None)

        with app.app_context():
            result = _check_llm_availability()
        assert result is False

    def test_get_llm_response_dotenv_exception(self, app, monkeypatch):
        """Cover line 99: dotenv.load_dotenv() except block."""
        import builtins
        from ai_knowledge.agents_core import _get_llm_response
        real_import = builtins.__import__
        def broken_import(name, *args, **kwargs):
            if name == 'dotenv':
                raise ImportError("no dotenv")
            return real_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", broken_import)
        monkeypatch.setattr("os.environ.get", lambda k, d=None: None)

        with app.app_context():
            result = _get_llm_response("p", "m")
        assert result is None

    def test_get_llm_response_groq_exception(self, app, monkeypatch):
        """Cover line 122: Groq API except block."""
        from ai_knowledge.agents_core import _get_llm_response
        monkeypatch.setattr("os.environ.get", lambda k, d=None: "sk-groq-xxx" if k == "GROQ_API_KEY" else None)
        monkeypatch.setattr("requests.post", Mock(side_effect=Exception("connection error")))

        with app.app_context():
            result = _get_llm_response("p", "m")
        assert result is None

    def test_get_llm_response_gemini_exception(self, app, monkeypatch):
        """Cover line 141: Gemini API except block."""
        from ai_knowledge.agents_core import _get_llm_response
        monkeypatch.setattr("os.environ.get", lambda k, d=None: "AIza-xxx" if k == "GEMINI_API_KEY" else ("sk-groq-xxx" if k == "GROQ_API_KEY" else None))
        monkeypatch.setattr("requests.post", Mock(side_effect=Exception("connection error")))

        with app.app_context():
            result = _get_llm_response("p", "m")
        assert result is None

    def test_ask_azad_enhanced_knowledge_exception(self, app, monkeypatch):
        """Cover lines 223-233: search_knowledge except block."""
        import sys
        import ai_knowledge.agents_core as ac_core
        from ai_knowledge.agents_core import ask_azad_enhanced
        monkeypatch.setattr(ac_core, "_check_llm_availability", Mock(return_value=False))
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock())
        sys.modules.pop("ai_knowledge.system_knowledge", None)
        # Break import to trigger the except
        import builtins
        real_import = builtins.__import__
        def broken_import(name, *args, **kwargs):
            if name == "ai_knowledge.system_knowledge":
                raise ImportError("simulated import failure")
            return real_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", broken_import)
        mock_brain = Mock()
        mock_brain.ask = Mock(return_value={"answer": "brain answer"})
        monkeypatch.setattr(ac_core, "get_master_brain", Mock(return_value=mock_brain))

        with app.app_context():
            result = ask_azad_enhanced("test", user_id=1)
        assert result["answer"] == "brain answer"
        assert result["source"] == "master_brain"

    def test_ask_azad_enhanced_llm_exception(self, app, monkeypatch):
        """Cover lines 246-247: LLM except block."""
        import ai_knowledge.agents_core as ac_core
        import ai_knowledge.system_knowledge as sys_know
        from ai_knowledge.agents_core import ask_azad_enhanced
        monkeypatch.setattr(sys_know, "search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr(ac_core, "_check_llm_availability", Mock(return_value=True))
        monkeypatch.setattr(ac_core, "_build_system_prompt", Mock(side_effect=Exception("prompt error")))
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock())

        mock_brain = Mock()
        mock_brain.ask = Mock(return_value={"answer": "brain fallback"})
        monkeypatch.setattr(ac_core, "get_master_brain", Mock(return_value=mock_brain))

        with app.app_context():
            result = ask_azad_enhanced("test", user_id=1)
        assert "LLM error" in result["thinking_steps"][0]
        assert result["answer"] == "brain fallback"

    def test_ask_azad_enhanced_trainer_exception(self, app, monkeypatch):
        """Cover lines 266-267: trainer.learn_from_interaction() except block."""
        import ai_knowledge.agents_core as ac_core
        import ai_knowledge.system_knowledge as sys_know
        from ai_knowledge.agents_core import ask_azad_enhanced
        monkeypatch.setattr(sys_know, "search_knowledge", Mock(return_value=[]))
        monkeypatch.setattr(ac_core, "_check_llm_availability", Mock(return_value=True))
        monkeypatch.setattr(ac_core, "_build_system_prompt", Mock(return_value="prompt"))
        monkeypatch.setattr(ac_core, "_get_llm_response", Mock(return_value="llm answer"))
        monkeypatch.setattr("ai_knowledge.trainer.trainer.learn_from_interaction", Mock(side_effect=Exception("trainer error")))

        with app.app_context():
            result = ask_azad_enhanced("test", user_id=1)
        assert result["answer"] == "llm answer"
        assert result["source"] == "llm"
