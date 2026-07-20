"""Inventory reconciliation — PWC vs movements vs GL variance."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestDateBounds:
    """_date_bound / _date_bounds — UI filter normalization."""

    @pytest.mark.parametrize(
        "value,end_of_day,expected_hour",
        [
            (None, False, None),
            ("", True, None),
            ("2025-06-15", False, 0),
            ("2025-06-15", True, 23),
            (datetime(2025, 6, 15, 14, 30), False, 14),
            ("not-a-date", False, None),
        ],
    )
    def test_date_bound_parsing(self, value, end_of_day, expected_hour):
        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        result = InventoryReconciliationService._date_bound(value, end_of_day=end_of_day)
        if expected_hour is None:
            assert result is None
        elif isinstance(value, datetime):
            assert result.hour == expected_hour
        else:
            assert result.hour == expected_hour

    def test_date_bounds_pair(self):
        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        start, end = InventoryReconciliationService._date_bounds("2025-01-01", "2025-01-31")
        assert start.day == 1 and start.hour == 0
        assert end.day == 31 and end.hour == 23

    def test_date_bound_date_object(self):
        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        result = InventoryReconciliationService._date_bound(date(2025, 3, 15), end_of_day=True)
        assert result.hour == 23 and result.day == 15

    def test_date_bound_iso_datetime_string(self):
        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        result = InventoryReconciliationService._date_bound("2025-03-15T08:30:00", end_of_day=False)
        assert result.hour == 8


class TestGLInventoryBalance:
    """_gl_inventory_balance — debit minus credit with filters."""

    @staticmethod
    def _mock_scalars(mocker, debit, credit):
        debit_q = MagicMock()
        debit_q.filter.return_value = debit_q
        debit_q.join.return_value = debit_q
        debit_q.scalar.return_value = debit

        credit_q = MagicMock()
        credit_q.filter.return_value = credit_q
        credit_q.join.return_value = credit_q
        credit_q.scalar.return_value = credit

        session = mocker.patch("services.inventory_reconciliation_service.db.session")
        session.query.side_effect = [debit_q, credit_q]
        return debit_q

    def test_balance_debit_minus_credit(self, mocker):
        self._mock_scalars(mocker, "15000", "4000")
        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        bal = InventoryReconciliationService._gl_inventory_balance(
            account_id=5,
            tenant_id=1,
            branch_id=2,
            warehouse_id=3,
            date_from="2025-01-01",
            date_to="2025-06-30",
        )
        assert bal == Decimal("11000")

    def test_no_filters_zero_balance(self, mocker):
        self._mock_scalars(mocker, None, None)
        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        bal = InventoryReconciliationService._gl_inventory_balance(
            account_id=1,
            tenant_id=None,
            branch_id=None,
            warehouse_id=None,
        )
        assert bal == Decimal("0")


class TestMovementNetQty:
    """_movement_net_qty — raw SQL quantity sum."""

    def test_executes_with_branch_and_dates(self, mocker, app):
        mock_exec = mocker.patch("services.inventory_reconciliation_service.db.session")
        mock_exec.execute.return_value.scalar.return_value = Decimal("42.5")

        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        with app.app_context():
            qty = InventoryReconciliationService._movement_net_qty(
                tenant_id=1,
                product_id=2,
                warehouse_id=3,
                branch_id=4,
                date_from="2025-01-01",
                date_to="2025-01-31",
            )
        assert qty == Decimal("42.5")
        sql = mock_exec.execute.call_args[0][0].text
        assert "stock_movements" in sql
        assert "branch_id" in sql


class TestBuildReport:
    """build_report — physical vs system qty variance per product."""

    def test_qty_variance_matched_within_tolerance(self, mocker):
        pwc = MagicMock(
            tenant_id=1,
            product_id=10,
            warehouse_id=20,
            total_quantity=Decimal("100"),
            total_value=Decimal("5000"),
            average_cost=Decimal("50"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value = pwc_q
        pwc_q.all.return_value = [pwc]
        mocker.patch.object(
            __import__("models", fromlist=["ProductWarehouseCost"]).ProductWarehouseCost,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=pwc_q,
        )

        product = MagicMock()
        product.name = "SKU-A"
        warehouse = MagicMock()
        warehouse.name = "Main WH"

        def _session_get(model, pk):
            if getattr(model, "__name__", model) == "Product":
                return product
            if getattr(model, "__name__", model) == "Warehouse":
                return warehouse
            return None

        mocker.patch(
            "services.inventory_reconciliation_service.db.session.get",
            side_effect=_session_get,
        )
        mocker.patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService._movement_net_qty",
            return_value=Decimal("100.005"),
        )

        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        report = InventoryReconciliationService.build_report(tenant_id=1)
        row = report["rows"][0]
        assert row["matched_qty"] is True
        assert row["product_name"] == "SKU-A"
        assert report["summary"]["all_matched"] is True

    def test_branch_id_joins_warehouse(self, mocker):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value = pwc_q
        pwc_q.join.return_value = pwc_q
        pwc_q.filter.return_value = pwc_q
        pwc_q.all.return_value = []
        mocker.patch.object(
            __import__("models", fromlist=["ProductWarehouseCost"]).ProductWarehouseCost,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=pwc_q,
        )
        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        report = InventoryReconciliationService.build_report(tenant_id=1, branch_id=5)
        assert report["rows"] == []
        pwc_q.join.assert_called_once()

    def test_variance_outside_tolerance_flags_mismatch(self, mocker):
        pwc = MagicMock(
            tenant_id=1,
            product_id=11,
            warehouse_id=21,
            total_quantity=Decimal("50"),
            total_value=Decimal("2500"),
            average_cost=Decimal("50"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value = pwc_q
        pwc_q.all.return_value = [pwc]
        mocker.patch.object(
            __import__("models", fromlist=["ProductWarehouseCost"]).ProductWarehouseCost,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=pwc_q,
        )
        mocker.patch(
            "services.inventory_reconciliation_service.db.session.get",
            return_value=None,
        )
        mocker.patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService._movement_net_qty",
            return_value=Decimal("40"),
        )

        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        report = InventoryReconciliationService.build_report(tenant_id=1)
        assert report["rows"][0]["matched_qty"] is False
        assert report["rows"][0]["product_name"] == "#11"
        assert report["summary"]["all_matched"] is False


class TestWarehouseSummary:
    """build_warehouse_summary — GL value diff and unallocated write-off trigger."""

    def test_warehouse_value_matched_when_gl_aligns(self, mocker):
        base_report = {
            "rows": [
                {
                    "warehouse_id": 5,
                    "warehouse_name": "WH-5",
                    "pwc_qty": 10.0,
                    "movement_qty": 10.0,
                    "pwc_value": 1000.0,
                }
            ],
            "summary": {"record_count": 1},
        }
        mocker.patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService.build_report",
            return_value=base_report,
        )
        inv_acc = MagicMock(id=77)
        acc_q = MagicMock()
        acc_q.filter_by.return_value = acc_q
        acc_q.first.return_value = inv_acc
        mocker.patch.object(
            __import__("models", fromlist=["GLAccount"]).GLAccount,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=acc_q,
        )
        mocker.patch(
            "services.inventory_reconciliation_service.scope_gl_accounts",
            return_value=acc_q,
        )
        mocker.patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService._gl_inventory_balance",
            side_effect=[Decimal("1000"), Decimal("1000")],
        )

        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        report = InventoryReconciliationService.build_warehouse_summary(tenant_id=1)
        wh = report["warehouse_summary"][0]
        assert wh["matched_value"] is True
        assert report["summary"]["all_matched_value"] is True
        assert report["summary"]["has_unallocated_gl"] is False

    def test_unallocated_gl_marks_write_off_on_single_warehouse(self, mocker):
        base_report = {
            "rows": [
                {
                    "warehouse_id": 8,
                    "warehouse_name": "WH-8",
                    "pwc_qty": 5.0,
                    "movement_qty": 5.0,
                    "pwc_value": 800.0,
                }
            ],
            "summary": {},
        }
        mocker.patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService.build_report",
            return_value=base_report,
        )
        inv_acc = MagicMock(id=88)
        acc_q = MagicMock()
        acc_q.filter_by.return_value = acc_q
        acc_q.first.return_value = inv_acc
        mocker.patch.object(
            __import__("models", fromlist=["GLAccount"]).GLAccount,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=acc_q,
        )
        mocker.patch(
            "services.inventory_reconciliation_service.scope_gl_accounts",
            return_value=acc_q,
        )
        mocker.patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService._gl_inventory_balance",
            side_effect=[Decimal("500"), Decimal("600")],
        )

        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        report = InventoryReconciliationService.build_warehouse_summary(tenant_id=1)
        wh = report["warehouse_summary"][0]
        assert wh["gl_untagged"] is True
        assert wh["unallocated_gl_value"] == pytest.approx(100.0)
        assert wh["matched_value"] is False
        assert report["summary"]["has_unallocated_gl"] is True
        assert report["summary"]["all_matched"] is False

    def test_empty_report_zero_totals(self, mocker):
        mocker.patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService.build_report",
            return_value={"rows": [], "summary": {}},
        )
        acc_q = MagicMock()
        acc_q.filter_by.return_value = acc_q
        acc_q.first.return_value = None
        mocker.patch.object(
            __import__("models", fromlist=["GLAccount"]).GLAccount,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=acc_q,
        )
        mocker.patch(
            "services.inventory_reconciliation_service.scope_gl_accounts",
            return_value=acc_q,
        )

        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
        )

        report = InventoryReconciliationService.build_warehouse_summary(tenant_id=1)
        assert report["warehouse_summary"] == []
        assert report["summary"]["all_matched_qty"] is True
