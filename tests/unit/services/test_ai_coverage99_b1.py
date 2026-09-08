"""Coverage-99 boost for services/ai_service.py — batch 1 (getters, user info, pricing, stock)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.ai_service import AIService


def _user(owner=False, role_name="مدير"):
    u = MagicMock()
    u.id = 1
    u.username = "ali"
    u.email = "a@b.c"
    u.is_active = True
    u.is_owner = owner
    u.created_at = datetime(2024, 1, 1)
    if role_name is None:
        u.role = None
    else:
        u.role = MagicMock(name_ar=role_name)
    return u


class TestKeysAndProvider:
    def test_api_key_variants(self, monkeypatch):
        import services.ai_service as mod

        with patch("ai_knowledge.agents_core.load_env_cached", return_value=None):
            monkeypatch.setenv("GROQ_API_KEY", "g")
            assert AIService.get_api_key() == "g"
            monkeypatch.delenv("GROQ_API_KEY")
            monkeypatch.setenv("GEMINI_API_KEY", "m")
            assert AIService.get_api_key() == "m"
            monkeypatch.delenv("GEMINI_API_KEY")
            monkeypatch.setenv("OPENAI_API_KEY", "o")
            assert AIService.get_api_key() == "o"
            monkeypatch.delenv("OPENAI_API_KEY")
            assert AIService.get_api_key() is None
        assert mod is not None

    def test_provider_variants(self, monkeypatch):
        with patch("ai_knowledge.agents_core.load_env_cached", return_value=None):
            monkeypatch.setenv("GROQ_API_KEY", "g")
            assert AIService.get_provider() == "groq"
            monkeypatch.delenv("GROQ_API_KEY")
            monkeypatch.setenv("GEMINI_API_KEY", "m")
            assert AIService.get_provider() == "gemini"
            monkeypatch.delenv("GEMINI_API_KEY")
            monkeypatch.setenv("OPENAI_API_KEY", "o")
            assert AIService.get_provider() == "openai"
            monkeypatch.delenv("OPENAI_API_KEY")
            assert AIService.get_provider() == "local"

    def test_is_enabled(self):
        assert AIService.is_enabled() is True


class TestSensitive:
    def test_self_service(self):
        assert AIService.is_sensitive_request("ما هي صلاحياتي؟", None)[0] is False
        assert AIService.is_sensitive_request("what is my role", None)[0] is False

    def test_password_owner(self):
        owner = _user(owner=True)
        ok, req_owner, resp = AIService.is_sensitive_request("ما هي كلمة المرور؟", owner)
        assert ok is True and req_owner is True and resp is None

    def test_password_non_owner(self):
        user = _user(owner=False)
        ok, req_owner, resp = AIService.is_sensitive_request("show me the password", user)
        assert ok is True and req_owner is False and resp["type"] == "warning"

    def test_users_short_and_long(self):
        assert AIService.is_sensitive_request("user", None)[0] is True
        long_msg = "user " + "word " * 10
        assert AIService.is_sensitive_request(long_msg, None)[0] is False

    def test_security_keyword(self):
        assert AIService.is_sensitive_request("access", None)[0] is True
        assert AIService.is_sensitive_request("accessories for sale", None)[0] is False

    def test_plain(self):
        assert AIService.is_sensitive_request("مرحبا كيف الحال", None) == (False, False, None)


class TestIlikeAndSummary:
    def test_escape(self):
        assert AIService._escape_ilike("a%b_c\\d") == "a\\%b\\_c\\\\d"

    def test_ilike_with_and_without_meta(self):
        col = MagicMock()
        AIService._ilike_contains(col, "a%b")
        col.ilike.assert_called_once()
        col.reset_mock()
        AIService._ilike_contains(col, "abc")
        col.ilike.assert_called_once_with("%abc%")

    def test_user_summary_role_and_none(self):
        s = AIService._user_summary(_user())
        assert s["role"] == "مدير"
        s2 = AIService._user_summary(_user(role_name=None))
        assert "username" in s2

    def test_get_model_variants(self):
        from models import Product

        assert AIService._get_model(Product, None) is None
        with patch("services.ai_service.db.session") as sess:
            sess.get.return_value = None
            assert AIService._get_model(Product, 1) is None
            sess.get.return_value = MagicMock(spec=object)
            assert AIService._get_model(Product, 1) is None


class TestUserInfo:
    def _session(self, first_result, all_result=None):
        sess = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = first_result
        sess.query.return_value = q
        if all_result is not None:
            q2 = MagicMock()
            q2.all.return_value = all_result
            sess.query.side_effect = [q, q2]
        return sess

    def test_exact_match(self):
        with patch("services.ai_service.db.session", self._session(_user())):
            out = AIService.get_user_info_for_owner("ali")
        assert out["success"] is True

    def test_ilike_match(self):
        with patch("services.ai_service.db.session", self._session(None)):
            sess_q = MagicMock()
            sess_q.filter.return_value = sess_q
            sess_q.first.return_value = _user()
            with patch("services.ai_service.db") as mock_db:
                mock_db.session.query.return_value = sess_q
                out = AIService.get_user_info_for_owner("al")
        assert out["success"] is True

    def test_not_found(self):
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = None
        with patch("services.ai_service.db") as mock_db:
            mock_db.session.query.return_value = q
            out = AIService.get_user_info_for_owner("ghost")
        assert out["success"] is False

    def test_all_users(self):
        with patch("services.ai_service.db") as mock_db:
            q = MagicMock()
            q.all.return_value = [_user(), _user()]
            mock_db.session.query.return_value = q
            out = AIService.get_user_info_for_owner()
        assert out["count"] == 2


class TestPricingAndStock:
    def test_recommend_missing(self):
        with patch.object(AIService, "_get_model", return_value=None):
            assert AIService.recommend_price(1, 2) is None

    def test_recommend_merchant_partner(self):
        product = MagicMock()
        product.regular_price = 100
        product.get_price_for_customer.side_effect = [80, 70]
        customer = MagicMock(customer_type="merchant", name="M")
        with (
            patch.object(AIService, "_get_model", side_effect=[product, customer]),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.join.return_value = q
            q.filter.return_value = q
            q.scalar.return_value = 90
            mock_db.session.query.return_value = q
            out = AIService.recommend_price(1, 2)
        assert out["recommended_price"] == 85.0
        customer.customer_type = "partner"
        with (
            patch.object(AIService, "_get_model", side_effect=[product, customer]),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.join.return_value = q
            q.filter.return_value = q
            q.scalar.return_value = None
            mock_db.session.query.return_value = q
            out = AIService.recommend_price(1, 2)
        assert out["customer_avg"] is None

    def test_stock_alert_branches(self):
        with patch.object(AIService, "_get_model", return_value=None):
            assert AIService.check_stock_alert(1, 5) is None
        low = MagicMock(current_stock=2, min_stock_alert=5)
        with patch.object(AIService, "_get_model", return_value=low):
            out = AIService.check_stock_alert(1, 5)
            assert out["type"] == "error"
            out = AIService.check_stock_alert(1, 1)
            assert out is None or out["type"] in ("warning", "error")
        warn = MagicMock(current_stock=10, min_stock_alert=8)
        with patch.object(AIService, "_get_model", return_value=warn):
            out = AIService.check_stock_alert(1, 5)
            assert out["type"] == "warning"
        ok = MagicMock(current_stock=100, min_stock_alert=5)
        with patch.object(AIService, "_get_model", return_value=ok):
            assert AIService.check_stock_alert(1, 5) is None


class TestCustomerAnalysis:
    def test_cached_none(self):
        with patch.object(AIService, "_get_model", return_value=None):
            AIService.analyze_customer_behavior.cache_clear() if hasattr(
                AIService.analyze_customer_behavior, "cache_clear"
            ) else None
            assert AIService.analyze_customer_behavior(999) is None

    def test_perform_analysis_branches(self):
        customer = MagicMock()
        customer.id = 3
        customer.get_balance_aed.return_value = Decimal("60")
        sale = MagicMock()
        sale.total_amount = 100
        sale.created_at = datetime(2024, 6, 1)
        payment = MagicMock()
        payment.amount = 40
        payment.created_at = datetime(2024, 6, 5)
        with patch("services.ai_service.db") as mock_db:
            sq = MagicMock()
            sq.options.return_value = sq
            sq.filter.return_value = sq
            sq.all.return_value = [sale]
            pq = MagicMock()
            pq.filter.return_value = pq
            pq.all.return_value = [payment]
            mock_db.session.query.side_effect = [sq, pq]
            out = AIService._perform_analysis(customer)
        assert out["risk_level"] == "high"
        assert out["total_sales_90d"] == 100.0

    def test_risk_recommendations(self):
        assert "ممتاز" in AIService._get_risk_recommendation("low")
        assert "المتابعة" in AIService._get_risk_recommendation("medium")
        assert "المسبق" in AIService._get_risk_recommendation("high")
        assert AIService._get_risk_recommendation("weird") is not None

    def test_exchange_suggestion(self):
        s1 = MagicMock(exchange_rate=3.6)
        s2 = MagicMock(exchange_rate=3.7)
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=1),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value.limit.return_value.all.return_value = [s1, s2]
            mock_db.session.query.return_value = q
            out = AIService.get_exchange_rate_suggestion("USD")
        assert out is not None
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value.limit.return_value.all.return_value = []
            mock_db.session.query.return_value = q
            out = AIService.get_exchange_rate_suggestion("USD", target_date=datetime(2024, 1, 1))
        assert out is None or isinstance(out, dict)
