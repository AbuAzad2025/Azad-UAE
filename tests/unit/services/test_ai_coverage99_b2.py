"""Coverage-99 boost for services/ai_service.py — batch 2 (trends, margins, patterns, inventory, telemetry)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from services.ai_service import AIService


def _sale(day, amount):
    s = MagicMock()
    s.sale_date = datetime(2024, 3, day, 10, 0)
    s.amount_aed = amount
    return s


class TestSalesTrend:
    def test_no_sales(self):
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=1),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = []
            mock_db.session.query.return_value = q
            out = AIService.predict_sales_trend()
        assert out["prediction"] is None

    def test_few_days(self):
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = [_sale(1, 10), _sale(2, 20)]
            mock_db.session.query.return_value = q
            out = AIService.predict_sales_trend()
        assert "7 أيام" in out["message"]

    def test_full_up_and_flat(self):
        sales = [_sale(d, 10 + d) for d in range(1, 10)]
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=1),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = sales
            mock_db.session.query.return_value = q
            out = AIService.predict_sales_trend(days_ahead=3)
        assert out["confidence"] >= 0
        assert len(out["prediction"]["predictions"]) == 3
        flat = [_sale(d, 50) for d in range(1, 10)]
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = flat
            mock_db.session.query.return_value = q
            out = AIService.predict_sales_trend()
        assert out["trend"]["direction"] is not None


class TestMargins:
    def test_no_sales(self):
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=1),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = []
            mock_db.session.query.return_value = q
            out = AIService.analyze_profit_margins()
        assert out["success"] is False

    def test_with_lines(self):
        line1 = MagicMock(product_id=1, cost_price=5, quantity=2, line_total=30, product=MagicMock(name="P1"))
        line2 = MagicMock(product_id=1, cost_price=5, quantity=1, line_total=0, product=None)
        line3 = MagicMock(product_id=2, cost_price=1, quantity=1, line_total=10, product=MagicMock(name="P2"))
        s = MagicMock(amount_aed=40, exchange_rate=1, lines=[line1, line2, line3])
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = [s]
            mock_db.session.query.return_value = q
            out = AIService.analyze_profit_margins()
        assert out["success"] is True
        assert out["overall"]["revenue"] == 40.0


class TestPatterns:
    def test_few(self):
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=1),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = [_sale(1, 10)]
            mock_db.session.query.return_value = q
            out = AIService.detect_sales_patterns()
        assert out["success"] is False

    def test_full(self):
        sales = [_sale((d % 28) + 1, 10 + d) for d in range(12)]
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = sales
            mock_db.session.query.return_value = q
            out = AIService.detect_sales_patterns()
        assert out["success"] is True
        assert "best_day" in out


class TestInventoryHealth:
    def _products(self, stocks):
        out = []
        for cur, low in stocks:
            p = MagicMock(current_stock=cur, min_stock_alert=low)
            out.append(p)
        return out

    def test_empty(self):
        with patch("services.ai_service.db") as mock_db:
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = []
            mock_db.session.query.return_value = q
            out = AIService.analyze_inventory_health(tenant_id=2)
        assert out["success"] is False

    def test_ratings(self):
        with patch("services.ai_service.db") as mock_db:
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = self._products([(10, 5)] * 9 + [(0, 5)])
            mock_db.session.query.return_value = q
            assert AIService.analyze_inventory_health()["rating"] is not None
        with patch("services.ai_service.db") as mock_db:
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = self._products([(10, 5)] * 6 + [(0, 5)] * 4)
            mock_db.session.query.return_value = q
            assert AIService.analyze_inventory_health()["health_score"] == 60
        with patch("services.ai_service.db") as mock_db:
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = self._products([(10, 5)] * 4 + [(0, 5)] * 6)
            mock_db.session.query.return_value = q
            assert AIService.analyze_inventory_health()["health_score"] == 40
        with patch("services.ai_service.db") as mock_db:
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = self._products([(1, 5)] * 3 + [(0, 5)] * 7)
            mock_db.session.query.return_value = q
            out = AIService.analyze_inventory_health()
            assert out["summary"]["low"] == 3


class TestStructuredAndTelemetry:
    def test_structured_match_nomatch(self):
        assert AIService._is_structured_command("عميل: أحمد") is True
        assert AIService._is_structured_command("مرحبا") is False
        assert AIService._is_structured_command(None) is False

    def test_structured_exception(self):
        with patch("services.ai_service.re.match", side_effect=RuntimeError("x")):
            assert AIService._is_structured_command("عميل: س") is False

    def test_telemetry_variants(self):
        assert AIService._record_telemetry(None) == {}
        pipe = {}
        out = AIService._record_telemetry(pipe, tool_names=["a", "", None], fallback_path="f", confidence=0.9)
        assert out["tool_names"] == "a"
        assert pipe["telemetry"]["fallback_path"] == "f"
        pipe2 = {"telemetry": {"x": 1}, "context": {"ai_telemetry": {"y": 2}}}
        AIService._record_telemetry(pipe2, tool_names=["b"])
        assert pipe2["telemetry"]["x"] == 1
        pipe3 = {"telemetry": "s", "context": {"ai_telemetry": "s"}}
        AIService._record_telemetry(pipe3, confidence=0.5)
        assert isinstance(pipe3["context"]["ai_telemetry"], dict)
        pipe4 = {"context": "not-dict"}
        AIService._record_telemetry(pipe4, tool_names=["c"])
        with patch("services.ai_service.logger.debug", side_effect=RuntimeError("x")):
            AIService._record_telemetry(None, tool_names=["z"])


class TestRecentHistory:
    def test_no_identity(self):
        assert AIService._get_recent_history(None, 1) == []
        assert AIService._get_recent_history(1, None) == []
        assert AIService._get_recent_history(1, 1, limit=0) == []

    def test_rows_and_empty(self):
        r1 = MagicMock(query="q1", response="r1")
        r2 = MagicMock(query="", response="")
        r3 = MagicMock(query="q3", response=None)
        with patch("services.ai_service.db") as mock_db:
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value.limit.return_value.all.return_value = [r1, r2, r3]
            mock_db.session.query.return_value = q
            out = AIService._get_recent_history(1, 1, limit=5)
        assert {"q": "q1", "r": "r1"} in out
        assert len(out) == 2

    def test_exception(self):
        with patch("services.ai_service.db.session.query", side_effect=RuntimeError("x")):
            assert AIService._get_recent_history(1, 1) == []
