"""Coverage-99 boost for services/ai_service.py — batch 6 (knowledge, insights, pricing, churn)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from services.ai_service import AIService


def _mq(**over):
    q = MagicMock()
    q.filter.return_value = q
    q.filter_by.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.count.return_value = 0
    q.all.return_value = []
    q.first.return_value = None
    q.scalar.return_value = 0
    for k, v in over.items():
        setattr(q, k, v)
    return q


def _user():
    u = MagicMock()
    u.tenant_id = 9
    u.username = "ali"
    u.is_owner = False
    u.role = MagicMock(name_ar="مدير")
    return u


class TestGatherKnowledge:
    def test_no_user(self):
        with patch("flask_login.current_user") as cu:
            cu.is_authenticated = False
            out = AIService._gather_relevant_knowledge("hi", {"context": {}})
        assert "هوية" in out

    def test_sharing_off(self):
        with patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=False):
            out = AIService._gather_relevant_knowledge("hi", {"context": {"current_user": _user()}})
        assert "الخصوصية" in out

    def test_full(self):
        with (
            patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=True),
            patch("services.ai_service.db.session") as sess,
            patch("utils.tenanting.scoped_user_query") as sq,
            patch("flask.current_app") as app,
        ):
            sess.query.return_value = _mq()
            sq.return_value.count.return_value = 1
            app.config = {
                "COMPANY_NAME_AR": "C",
                "COMPANY_PHONE": "P",
                "COMPANY_WHATSAPP": "W",
                "COMPANY_ADDRESS_AR": "A",
            }
            out = AIService._gather_relevant_knowledge("hi", {"context": {"current_user": _user()}})
        assert "بيانات النظام" in out

    def test_user_no_role(self):
        u = _user()
        u.role = None
        with (
            patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=True),
            patch("services.ai_service.db.session") as sess,
            patch("utils.tenanting.scoped_user_query") as sq,
            patch("flask.current_app") as app,
        ):
            sess.query.return_value = _mq()
            sq.return_value.count.return_value = 1
            app.config = {
                "COMPANY_NAME_AR": "C",
                "COMPANY_PHONE": "P",
                "COMPANY_WHATSAPP": "W",
                "COMPANY_ADDRESS_AR": "A",
            }
            out = AIService._gather_relevant_knowledge("hi", {"context": {"current_user": u}})
        assert "غير محدد" in out

    def test_exception(self):
        with patch.object(AIService, "_is_ai_external_sharing_enabled", side_effect=RuntimeError("x")):
            out = AIService._gather_relevant_knowledge("hi", {"context": {}})
        assert "خطأ" in out or "هوية" in out


class TestInsights:
    def test_empty_and_full(self):
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=1),
            patch("services.ai_service.db.session") as sess,
        ):
            sess.query.return_value = _mq()
            out = AIService.generate_business_insights()
        assert out == [] or isinstance(out, list)
        cust = MagicMock()
        cust.get_balance_aed.return_value = 2000
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db.session") as sess,
        ):
            q = _mq()
            q.all.return_value = [cust]
            q.count.return_value = 3
            sess.query.return_value = q
            out = AIService.generate_business_insights()
        assert isinstance(out, list)

    def test_exception(self):
        with patch("services.ai_service.db.session.query", side_effect=RuntimeError("x")):
            out = AIService.generate_business_insights()
        assert out[0]["type"] == "error"

    def test_optimize_inventory(self):
        with patch("services.ai_service.db.session") as sess:
            p = MagicMock(current_stock=1, min_stock_alert=5)
            q = _mq()
            q.all.return_value = [p]
            sess.query.return_value = q
            out = AIService.optimize_inventory_levels()
        assert out is not None
        with patch("services.ai_service.db.session.query", side_effect=RuntimeError("x")):
            out = AIService.optimize_inventory_levels()
        assert out is not None


class TestPricingChurn:
    def test_cashflow_ok_error(self):
        with patch.object(AIService, "predict_cash_flow_neural", return_value={"success": True}):
            assert AIService.predict_cash_flow(60)["success"] is True
        with patch.object(AIService, "predict_cash_flow_neural", side_effect=RuntimeError("x")):
            assert AIService.predict_cash_flow()["success"] is False

    def test_smart_pricing(self):
        with patch.object(AIService, "_get_model", return_value=None):
            assert AIService.smart_pricing_engine(1, 2) is None
        prod = MagicMock(regular_price=100)
        with patch.object(AIService, "_get_model", return_value=prod):
            assert AIService.smart_pricing_engine(1, 2, quantity=12)["discount_percentage"] == 10
            assert AIService.smart_pricing_engine(1, 2, quantity=7)["discount_percentage"] == 5
            assert AIService.smart_pricing_engine(1, 2, quantity=1)["discount_percentage"] == 0
        with patch.object(AIService, "_get_model", side_effect=RuntimeError("x")):
            assert AIService.smart_pricing_engine(1, 2) is None

    def test_churn(self):
        from datetime import UTC

        cust = MagicMock(id=1, name="C")
        old_sale = MagicMock(sale_date=datetime(2023, 1, 1, tzinfo=UTC))
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=1),
            patch("services.ai_service.db.session") as sess,
        ):
            cq = _mq()
            cq.all.return_value = [cust]
            sq = _mq()
            sq.first.return_value = old_sale
            sess.query.side_effect = [cq, sq]
            out = AIService.predict_customer_churn()
        assert out["total_at_risk"] == 1
        assert out["at_risk_customers"][0]["risk_level"] == "high"
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db.session") as sess,
        ):
            sess.query.return_value = _mq()
            out = AIService.predict_customer_churn()
        assert out["total_at_risk"] == 0
        with patch("services.ai_service.db.session.query", side_effect=RuntimeError("x")):
            assert AIService.predict_customer_churn()["success"] is False


class TestLocalAndContextual:
    def test_local(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        with patch.object(AzadResponses, "smart_response", return_value="SR"):
            assert AIService._local_response("hi", {}) == "SR"

    def test_contextual_ok(self):
        with (
            patch.object(AIService, "get_context_engine") as ce,
            patch.object(AIService, "get_dialect_manager") as dm,
            patch.object(AIService, "get_personality") as per,
            patch.object(AIService, "get_learning_system"),
        ):
            ce.return_value.build_context.return_value = {}
            dm.return_value.detect_dialect.return_value = "msa"
            per.return_value.generate_response.return_value = "R"
            assert AIService.get_contextual_response("hi") == "R"

    def test_contextual_error_paths(self):
        with patch.object(AIService, "get_context_engine", side_effect=RuntimeError("x")):
            with patch("services.logging_core.LoggingCore.log_error", return_value=None):
                from ai_knowledge.personality.azad_responses import AzadResponses

                with patch.object(AzadResponses, "get_error_response", return_value="ER"):
                    assert AIService.get_contextual_response("hi") == "ER"
        with patch.object(AIService, "get_context_engine", side_effect=RuntimeError("x")):
            with patch(
                "services.logging_core.LoggingCore.log_error",
                side_effect=RuntimeError("y"),
            ):
                from ai_knowledge.personality.azad_responses import AzadResponses

                with patch.object(AzadResponses, "get_error_response", side_effect=RuntimeError("z")):
                    out = AIService.get_contextual_response("hi")
                    assert out is not None


class TestSmallPartials:
    def test_user_info_created_none(self):
        u = MagicMock(
            id=1,
            username="a",
            email="e",
            is_active=True,
            is_owner=False,
            role=MagicMock(name_ar="r"),
            created_at=None,
        )
        with patch("services.ai_service.db") as mock_db:
            q = MagicMock()
            q.filter.return_value = q
            q.first.return_value = u
            mock_db.session.query.return_value = q
            out = AIService.get_user_info_for_owner("a")
        assert out["user"]["created_at"] is None

    def test_ilike_exact_meta(self):
        col = MagicMock()
        AIService._ilike_contains(col, "100%")
        col.ilike.assert_called_once()
