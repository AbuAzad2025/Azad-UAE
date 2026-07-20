"""Auto-approval service — donation/purchase threshold gates and fallbacks."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest


class TestApprovePendingDonations:
    """approve_pending_donations — hour threshold and audit trail."""

    @staticmethod
    def _donation(amount=100.0, hours_ago=2):
        d = MagicMock()
        d.id = 1
        d.amount_usd = amount
        d.status = "pending"
        d.created_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        return d

    def test_approves_donations_past_threshold(self, app, mocker):
        donation = self._donation()
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [donation]
        mocker.patch("services.auto_approval_service.Donation.query", mock_q)
        mocker.patch("services.auto_approval_service.LoggingCore.log_audit")
        mocker.patch("services.auto_approval_service.db.session")

        from services.auto_approval_service import AutoApprovalService

        with app.app_context():
            result = AutoApprovalService.approve_pending_donations(hours_threshold=1)

        assert result["success"] is True
        assert result["approved_count"] == 1
        assert result["approved_amount"] == 100.0
        assert donation.status == "completed"
        assert donation.completed_at is not None

    @pytest.mark.parametrize(
        "hours_threshold,hours_ago,expected_count",
        [
            (1, 2, 1),
            (3, 2, 0),
            (24, 25, 1),
        ],
    )
    def test_threshold_limits_auto_approval(self, app, mocker, hours_threshold, hours_ago, expected_count):
        donations = [self._donation(hours_ago=hours_ago)] if hours_ago >= hours_threshold else []
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = donations
        mocker.patch("services.auto_approval_service.Donation.query", mock_q)
        mocker.patch("services.auto_approval_service.LoggingCore.log_audit")
        mocker.patch("services.auto_approval_service.db.session")

        from services.auto_approval_service import AutoApprovalService

        with app.app_context():
            result = AutoApprovalService.approve_pending_donations(hours_threshold=hours_threshold)

        assert result["approved_count"] == expected_count

    def test_commit_failure_rolls_back(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [self._donation()]
        mocker.patch("services.auto_approval_service.Donation.query", mock_q)
        mocker.patch("services.auto_approval_service.LoggingCore.log_audit")
        mock_session = mocker.patch("services.auto_approval_service.db.session")
        mock_session.commit.side_effect = RuntimeError("db error")

        from services.auto_approval_service import AutoApprovalService

        with app.app_context():
            result = AutoApprovalService.approve_pending_donations()
        assert result["success"] is False
        assert "db error" in result["error"]
        mock_session.rollback.assert_called()

    def test_query_failure_returns_rejection_fallback(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter.side_effect = Exception("query failed")
        mocker.patch("services.auto_approval_service.Donation.query", mock_q)
        mock_session = mocker.patch("services.auto_approval_service.db.session")

        from services.auto_approval_service import AutoApprovalService

        with app.app_context():
            result = AutoApprovalService.approve_pending_donations()
        assert result["success"] is False
        assert "query failed" in result["error"]
        mock_session.flush.assert_not_called()


class TestApprovePendingPurchases:
    """approve_pending_purchases — activation and linked donation override."""

    def test_approves_purchase_and_related_donation(self, app, mocker):
        purchase = MagicMock()
        purchase.id = 10
        purchase.amount_paid = 250.0
        purchase.customer_email = "buyer@test.com"
        purchase.package.slug = "gold"
        purchase.package.name_ar = "ذهبي"
        purchase.payment_status = "pending"
        purchase.created_at = datetime.now(timezone.utc) - timedelta(hours=2)

        related = MagicMock()
        related.status = "pending"

        pp_q = MagicMock()
        pp_q.filter.return_value.all.return_value = [purchase]
        don_q = MagicMock()
        don_q.filter.return_value.first.return_value = related

        mocker.patch("services.auto_approval_service.PackagePurchase.query", pp_q)
        mocker.patch("services.auto_approval_service.Donation.query", don_q)
        mocker.patch("services.auto_approval_service.LoggingCore.log_audit")
        mocker.patch("services.auto_approval_service.db.session")

        from services.auto_approval_service import AutoApprovalService

        with app.app_context():
            result = AutoApprovalService.approve_pending_purchases(hours_threshold=1)

        assert result["success"] is True
        assert result["approved_count"] == 1
        assert purchase.activation_status == "activated"
        assert related.status == "completed"

    def test_skips_when_no_pending_purchases(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = []
        mocker.patch("services.auto_approval_service.PackagePurchase.query", mock_q)
        mocker.patch("services.auto_approval_service.db.session")

        from services.auto_approval_service import AutoApprovalService

        with app.app_context():
            result = AutoApprovalService.approve_pending_purchases()
        assert result["approved_count"] == 0


class TestRunAutoApproval:
    """run_auto_approval — orchestrates donations + purchases."""

    def test_aggregates_totals(self, mocker):
        mocker.patch(
            "services.auto_approval_service.AutoApprovalService.approve_pending_donations",
            return_value={"approved_count": 2, "approved_amount": 50.0},
        )
        mocker.patch(
            "services.auto_approval_service.AutoApprovalService.approve_pending_purchases",
            return_value={"approved_count": 1, "approved_amount": 100.0},
        )
        from services.auto_approval_service import AutoApprovalService

        result = AutoApprovalService.run_auto_approval()
        assert result["total_approved"] == 3
        assert result["total_amount"] == 150.0


class TestScheduleAutoApproval:
    def test_starts_daemon_thread(self, mocker):
        mock_thread = mocker.patch("threading.Thread")
        mock_thread.return_value.start = MagicMock()
        app = MagicMock()
        from services.auto_approval_service import schedule_auto_approval

        schedule_auto_approval(app)
        mock_thread.assert_called_once()
        assert mock_thread.call_args.kwargs.get("daemon") is True
        mock_thread.return_value.start.assert_called_once()

    def test_purchase_commit_failure(self, app, mocker):
        purchase = MagicMock()
        purchase.amount_paid = 100.0
        purchase.package = MagicMock(slug="gold", name_ar="Gold")
        purchase.customer_email = "a@test.com"
        purchase.payment_status = "pending"
        purchase.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [purchase]
        mocker.patch("services.auto_approval_service.PackagePurchase.query", mock_q)
        mocker.patch("services.auto_approval_service.Donation.query")
        mocker.patch("services.auto_approval_service.LoggingCore.log_audit")
        mock_session = mocker.patch("services.auto_approval_service.db.session")
        mock_session.commit.side_effect = RuntimeError("db error")

        from services.auto_approval_service import AutoApprovalService

        with app.app_context():
            result = AutoApprovalService.approve_pending_purchases()
        assert result["success"] is False
        assert "db error" in result["error"]

    def test_empty_donations_success(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = []
        mocker.patch("services.auto_approval_service.Donation.query", mock_q)
        mocker.patch("services.auto_approval_service.db.session")
        from services.auto_approval_service import AutoApprovalService

        with app.app_context():
            result = AutoApprovalService.approve_pending_donations()
        assert result["approved_count"] == 0

    def test_scheduler_task_runs_once(self, app, mocker):
        mocker.patch(
            "services.auto_approval_service.AutoApprovalService.run_auto_approval",
            return_value={"total_approved": 0},
        )
        mocker.patch("time.sleep", side_effect=InterruptedError("stop"))
        captured = {}

        def fake_thread(target=None, daemon=None):
            captured["target"] = target
            return MagicMock(start=lambda: None)

        mocker.patch("threading.Thread", side_effect=fake_thread)
        from services.auto_approval_service import schedule_auto_approval

        schedule_auto_approval(app)
        with app.app_context():
            with pytest.raises(InterruptedError):
                captured["target"]()

    def test_scheduler_logs_errors(self, app, mocker):
        mocker.patch(
            "services.auto_approval_service.AutoApprovalService.run_auto_approval",
            side_effect=RuntimeError("boom"),
        )
        mocker.patch("time.sleep", side_effect=InterruptedError("stop"))
        captured = {}

        def fake_thread(target=None, daemon=None):
            captured["target"] = target
            return MagicMock(start=lambda: None)

        mocker.patch("threading.Thread", side_effect=fake_thread)
        from services.auto_approval_service import schedule_auto_approval

        schedule_auto_approval(app)
        with app.app_context():
            with pytest.raises(InterruptedError):
                captured["target"]()
