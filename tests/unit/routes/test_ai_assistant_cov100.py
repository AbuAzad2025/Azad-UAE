"""Gap100 for routes/ai_routes/assistant.py — disallowed page reason (41) +
excel error-cap arcs (280-281)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestAssistantPageDisallowed:
    def test_disallowed_sets_disable_reason(self, ai_client):
        with (
            patch(
                "routes.ai_routes.assistant.get_ai_access_state",
                return_value={
                    "allowed": False,
                    "global_enabled": True,
                    "tenant_enabled": True,
                    "reason": "quota-exhausted",
                },
            ),
            patch("routes.ai_routes.assistant.render_template", return_value="page") as rt,
            patch("utils.branching.get_accessible_warehouses", return_value=[]),
        ):
            resp = ai_client.get("/ai/assistant")
        assert resp.status_code == 200
        assert rt.call_args.kwargs["ai_disable_reason"] == "quota-exhausted"
        assert rt.call_args.kwargs["ai_enabled"] is False


class TestExcelErrorCap:
    def test_error_cap_message_after_fifty_failures(self, app):
        from routes.ai_routes import assistant as assistant_mod

        class _Row:
            def __getitem__(self, key):
                if key == "pr":
                    return "not-a-number"
                return "x"

        class _FakeDF:
            def __len__(self):
                return 60

            def iterrows(self):
                for i in range(60):
                    yield i, _Row()

        mapping = {"name": "n", "part_number": "p", "price": "pr"}
        user = MagicMock(id=7)
        atomic = MagicMock()
        atomic.__enter__ = MagicMock()
        atomic.__exit__ = MagicMock(return_value=False)
        with (
            app.test_request_context("/"),
            patch("routes.ai_routes.assistant.pd.read_excel", return_value=_FakeDF()),
            patch(
                "routes.ai_routes.assistant._intelligent_column_detector",
                return_value=mapping,
            ),
            patch("routes.ai_routes.assistant.get_active_tenant_id", return_value=1),
            patch(
                "routes.ai_routes.assistant.PlatformQueryService.warehouse_in_tenant",
                return_value=MagicMock(id=3),
            ),
            patch("routes.ai_routes.assistant.atomic_transaction", return_value=atomic),
            patch("routes.ai_routes.assistant._train_ai_from_excel"),
        ):
            result = assistant_mod._process_excel_intelligently(MagicMock(), 3, user)
        assert result["success"] is True
        assert "الحد الأقصى للعرض" in result["message"]
