from __future__ import annotations

from unittest.mock import patch

import pytest

from services.notification_service import NotificationService, SecurityService


@pytest.fixture(autouse=True)
def _reset_stores():
    NotificationService._notifications = []
    SecurityService._blacklist = set()
    SecurityService._failed_attempts = {}
    yield
    NotificationService._notifications = []
    SecurityService._blacklist = set()
    SecurityService._failed_attempts = {}


class TestNotificationService:
    def test_send_notification_assigns_id_and_defaults(self):
        with patch("services.notification_service.logger") as log:
            n = NotificationService.send_notification("Title", "Body")
        assert n["id"] == 1
        assert n["title"] == "Title"
        assert n["type"] == "info"
        assert n["data"] == {}
        assert n["read"] is False
        log.info.assert_called_once()

    def test_get_recent_notifications_limits(self):
        for i in range(15):
            NotificationService.send_notification(f"T{i}", "m")
        recent = NotificationService.get_recent_notifications(limit=5)
        assert len(recent) == 5
        assert recent[0]["title"] == "T10"

    def test_mark_as_read(self):
        n = NotificationService.send_notification("T", "m")
        NotificationService.mark_as_read(n["id"])
        assert NotificationService._notifications[0]["read"] is True

    def test_notify_payment_received(self):
        n = NotificationService.notify_payment_received(100, "Ali", "cash")
        assert n["type"] == "success"
        assert n["data"]["amount"] == 100

    def test_notify_security_alert(self):
        n = NotificationService.notify_security_alert("Brute force", "5 fails")
        assert n["type"] == "danger"

    def test_notify_purchase_activated(self):
        n = NotificationService.notify_purchase_activated("Gold", "Sara")
        assert "Gold" in n["message"]

    def test_notify_auto_approval(self):
        n = NotificationService.notify_auto_approval(3, 500)
        assert n["data"]["count"] == 3


class TestSecurityService:
    def test_blacklisted_ip_is_suspicious(self):
        SecurityService._blacklist.add("1.2.3.4")
        with patch.object(NotificationService, "notify_security_alert") as alert:
            result = SecurityService.detect_suspicious_activity("1.2.3.4", "Mozilla", "login")
        assert result["suspicious"] is True
        assert result["reason"] == "blacklisted_ip"
        alert.assert_called_once()

    def test_too_many_failed_attempts_blacklists(self):
        ip = "9.9.9.9"
        SecurityService._failed_attempts[ip] = {
            "count": 5,
            "first_attempt": None,
            "last_attempt": None,
        }
        with patch.object(NotificationService, "notify_security_alert"):
            result = SecurityService.detect_suspicious_activity(ip, "Mozilla", "login")
        assert result["reason"] == "too_many_failed_attempts"
        assert ip in SecurityService._blacklist

    def test_suspicious_user_agent(self):
        with patch.object(NotificationService, "notify_security_alert"):
            result = SecurityService.detect_suspicious_activity("8.8.8.8", "Googlebot crawler", "scan")
        assert result["reason"] == "suspicious_user_agent"

    def test_clean_activity(self):
        result = SecurityService.detect_suspicious_activity("8.8.8.8", "Mozilla/5.0", "login")
        assert result == {"suspicious": False}

    def test_log_and_reset_failed_attempts(self):
        SecurityService.log_failed_attempt("1.1.1.1")
        SecurityService.log_failed_attempt("1.1.1.1")
        assert SecurityService._failed_attempts["1.1.1.1"]["count"] == 2
        SecurityService.reset_failed_attempts("1.1.1.1")
        assert "1.1.1.1" not in SecurityService._failed_attempts

    def test_get_security_status_levels(self):
        SecurityService._blacklist = {"a", "b", "c", "d", "e", "f"}
        SecurityService._failed_attempts = {f"ip{i}": {"count": 1} for i in range(12)}
        status = SecurityService.get_security_status()
        assert status["blacklisted_ips"] == 6
        assert status["security_level"] == "medium"
        SecurityService._blacklist = set(f"ip{i}" for i in range(15))
        assert SecurityService.get_security_status()["security_level"] == "low"

    def test_security_level_high(self):
        SecurityService._blacklist = set()
        SecurityService._failed_attempts = {}
        assert SecurityService.get_security_status()["security_level"] == "high"
