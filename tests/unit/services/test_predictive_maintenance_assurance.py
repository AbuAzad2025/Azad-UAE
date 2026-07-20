"""Predictive maintenance — risk intervals, alerts, lifecycle telemetry."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


def _sale_line(product_id, sale_date, qty=1):
    sale = MagicMock()
    sale.sale_date = sale_date
    sale.status = "confirmed"
    line = MagicMock()
    line.product_id = product_id
    line.quantity = Decimal(str(qty))
    line.sale = sale
    return line


class TestPredictNextMaintenance:
    """predict_next_maintenance — interval math and confidence."""

    def test_insufficient_history_returns_none(self, mocker):
        session = mocker.patch("services.predictive_maintenance.db.session")
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = [_sale_line(1, datetime.now())]
        session.query.return_value = q

        from services.predictive_maintenance import PredictiveMaintenanceService

        assert PredictiveMaintenanceService.predict_next_maintenance(1) is None

    def test_calculates_avg_interval_and_days_until(self, mocker, frozen_time=None):
        now = datetime(2025, 6, 15, 12, 0, 0)
        lines = [
            _sale_line(5, now),
            _sale_line(5, now - timedelta(days=10)),
            _sale_line(5, now - timedelta(days=30)),
        ]
        session = mocker.patch("services.predictive_maintenance.db.session")
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = lines
        session.query.return_value = q

        from services.predictive_maintenance import PredictiveMaintenanceService

        result = PredictiveMaintenanceService.predict_next_maintenance(5)
        assert result is not None
        assert result["product_id"] == 5
        assert result["avg_interval_days"] == pytest.approx(15.0)
        assert result["confidence"] == pytest.approx(0.3)
        assert result["days_until"] >= 0


class TestMaintenanceAlerts:
    """get_maintenance_alerts — threshold filtering and urgency tiers."""

    def test_high_urgency_within_seven_days(self, mocker):
        product = MagicMock(id=1, name="Filter A", is_active=True)
        mocker.patch(
            "models.Product.query",
            new_callable=mocker.PropertyMock,
            return_value=MagicMock(filter_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[product])))),
        )
        mocker.patch(
            "services.predictive_maintenance.PredictiveMaintenanceService.predict_next_maintenance",
            return_value={
                "days_until": 3,
                "confidence": 0.8,
            },
        )

        from services.predictive_maintenance import PredictiveMaintenanceService

        alerts = PredictiveMaintenanceService.get_maintenance_alerts(threshold_days=30)
        assert len(alerts) == 1
        assert alerts[0]["urgency"] == "high"
        assert alerts[0]["days_until_maintenance"] == 3

    def test_alerts_sorted_by_days_until(self, mocker):
        p1, p2 = MagicMock(id=1, name="A"), MagicMock(id=2, name="B")
        mocker.patch(
            "models.Product.query",
            new_callable=mocker.PropertyMock,
            return_value=MagicMock(filter_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[p1, p2])))),
        )
        mocker.patch(
            "services.predictive_maintenance.PredictiveMaintenanceService.predict_next_maintenance",
            side_effect=[
                {"days_until": 20, "confidence": 0.5},
                {"days_until": 5, "confidence": 0.9},
            ],
        )

        from services.predictive_maintenance import PredictiveMaintenanceService

        alerts = PredictiveMaintenanceService.get_maintenance_alerts(threshold_days=30)
        assert alerts[0]["product_id"] == 2
        assert alerts[1]["product_id"] == 1

    def test_no_prediction_skips_ticket(self, mocker):
        product = MagicMock(id=9, name="Silent")
        mocker.patch(
            "models.Product.query",
            new_callable=mocker.PropertyMock,
            return_value=MagicMock(filter_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[product])))),
        )
        mocker.patch(
            "services.predictive_maintenance.PredictiveMaintenanceService.predict_next_maintenance",
            return_value=None,
        )

        from services.predictive_maintenance import PredictiveMaintenanceService

        assert PredictiveMaintenanceService.get_maintenance_alerts() == []


class TestProductLifecycle:
    """analyze_product_lifecycle / _determine_lifecycle_stage."""

    def test_no_sales_returns_no_data(self, mocker):
        session = mocker.patch("services.predictive_maintenance.db.session")
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = []
        session.query.return_value = q

        from services.predictive_maintenance import PredictiveMaintenanceService

        assert PredictiveMaintenanceService.analyze_product_lifecycle(1) == {"status": "no_data"}

    def test_lifecycle_metrics_computed(self, mocker):
        start = datetime(2025, 1, 1)
        lines = [_sale_line(3, start + timedelta(days=i * 5), qty=1) for i in range(12)]
        session = mocker.patch("services.predictive_maintenance.db.session")
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = lines
        session.query.return_value = q

        from services.predictive_maintenance import PredictiveMaintenanceService

        result = PredictiveMaintenanceService.analyze_product_lifecycle(3)
        assert result["total_sold"] == pytest.approx(12.0)
        assert result["total_transactions"] == 12
        assert result["lifecycle_stage"] == "growth"

    @pytest.mark.parametrize(
        "days,txns,stage",
        [
            (10, 2, "introduction"),
            (90, 15, "growth"),
            (200, 25, "maturity"),
            (200, 5, "decline"),
        ],
    )
    def test_lifecycle_stage_boundaries(self, days, txns, stage):
        from services.predictive_maintenance import PredictiveMaintenanceService

        assert PredictiveMaintenanceService._determine_lifecycle_stage(days, txns) == stage
