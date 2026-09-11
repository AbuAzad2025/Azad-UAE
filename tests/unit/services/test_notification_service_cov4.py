"""Cov4: notification_service + SecurityService — all notify/detect/level arcs."""

from __future__ import annotations

import pytest

from services.notification_service import NotificationService, SecurityService


@pytest.fixture(autouse=True)
def _clean_state():
    NotificationService._notifications.clear()
    SecurityService._blacklist.clear()
    SecurityService._failed_attempts.clear()
    yield
    NotificationService._notifications.clear()
    SecurityService._blacklist.clear()
    SecurityService._failed_attempts.clear()


def test_send_and_recent_and_mark_read():
    n1 = NotificationService.send_notification("t1", "m1")
    n2 = NotificationService.send_notification("t2", "m2", notification_type="success", data={"k": 1})
    assert n1["id"] == 1 and n2["id"] == 2
    assert NotificationService.get_recent_notifications(limit=1) == [n2]
    NotificationService.mark_as_read(1)
    assert NotificationService._notifications[0]["read"] is True
    NotificationService.mark_as_read(999)  # no-match loop-exhausted branch


def test_notify_helpers():
    assert NotificationService.notify_payment_received(100, "Ali", "cash")["type"] == "success"
    assert NotificationService.notify_security_alert("X", "d")["type"] == "danger"
    assert NotificationService.notify_purchase_activated("P", "C")["type"] == "info"
    assert NotificationService.notify_auto_approval(3, 500)["type"] == "success"


def test_detect_blacklisted_ip():
    SecurityService._blacklist.add("1.2.3.4")
    out = SecurityService.detect_suspicious_activity("1.2.3.4", "Mozilla", "login")
    assert out == {"suspicious": True, "reason": "blacklisted_ip"}


def test_detect_too_many_failed_attempts():
    SecurityService._failed_attempts["5.6.7.8"] = {"count": 5, "first_attempt": None, "last_attempt": None}
    out = SecurityService.detect_suspicious_activity("5.6.7.8", "Mozilla", "login")
    assert out == {"suspicious": True, "reason": "too_many_failed_attempts"}
    assert "5.6.7.8" in SecurityService._blacklist


def test_detect_suspicious_agent_and_clean():
    out = SecurityService.detect_suspicious_activity("9.9.9.9", "GoogleBot crawler", "view")
    assert out == {"suspicious": True, "reason": "suspicious_user_agent"}
    out = SecurityService.detect_suspicious_activity("9.9.9.9", "Mozilla/5.0", "view")
    assert out == {"suspicious": False}
    # failed attempts below threshold -> not suspicious
    SecurityService._failed_attempts["2.2.2.2"] = {"count": 2, "first_attempt": None, "last_attempt": None}
    out = SecurityService.detect_suspicious_activity("2.2.2.2", "Mozilla", "view")
    assert out == {"suspicious": False}


def test_failed_attempt_lifecycle():
    SecurityService.log_failed_attempt("3.3.3.3")
    SecurityService.log_failed_attempt("3.3.3.3")
    assert SecurityService._failed_attempts["3.3.3.3"]["count"] == 2
    SecurityService.reset_failed_attempts("3.3.3.3")
    assert "3.3.3.3" not in SecurityService._failed_attempts
    SecurityService.reset_failed_attempts("missing")  # no-op branch


def test_security_status_and_levels():
    assert SecurityService.get_security_status()["security_level"] == "high"
    for i in range(11):
        SecurityService._failed_attempts[f"ip-{i}"] = {"count": 1}
    assert SecurityService.get_security_status()["security_level"] == "medium"
    assert SecurityService.get_security_status()["total_failed_count"] == 11
    for i in range(11, 25):
        SecurityService._failed_attempts[f"ip-{i}"] = {"count": 1}
    assert SecurityService._calculate_security_level() == "low"
    SecurityService._failed_attempts.clear()
    for i in range(11):
        SecurityService._blacklist.add(f"b-{i}")
    assert SecurityService._calculate_security_level() == "low"
