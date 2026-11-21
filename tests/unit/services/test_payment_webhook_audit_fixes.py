"""Audit fixes: raw-body IPN signatures, per-event webhook dedup, one-shot workers."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from unittest.mock import MagicMock

import pytest

from services.nowpayments_service import NOWPaymentsService


@pytest.fixture
def nowpayments_svc(app):
    svc = NOWPaymentsService()
    svc.ipn_secret = "ipn-secret"
    return svc


class TestIpnSignatureUsesRawBody:
    def test_raw_body_is_signed_with_sha512(self, nowpayments_svc):
        raw = b'{"payment_id":"np-1","payment_status":"finished"}'
        sig = hmac.new(b"ipn-secret", raw, hashlib.sha512).hexdigest()
        assert nowpayments_svc.verify_ipn(raw, sig) is True

    def test_tampered_raw_body_is_rejected(self, nowpayments_svc):
        signed = b'{"payment_id":"np-1"}'
        sent = b'{"payment_id":"np-2"}'
        sig = hmac.new(b"ipn-secret", signed, hashlib.sha512).hexdigest()
        assert nowpayments_svc.verify_ipn(sent, sig) is False

    def test_legacy_dict_callers_keep_verifying(self, nowpayments_svc):
        data = {"payment_id": "np-1"}
        sig = hmac.new(
            b"ipn-secret",
            json.dumps(data, sort_keys=True).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert nowpayments_svc.verify_ipn(data, sig) is True

    def test_missing_secret_fails_closed(self, nowpayments_svc):
        nowpayments_svc.ipn_secret = ""
        raw = b"{}"
        sig = hmac.new(b"", raw, hashlib.sha512).hexdigest()
        assert nowpayments_svc.verify_ipn(raw, sig) is False


class TestWebhookDedupIsPerEvent:
    def test_nowpayments_key_distinguishes_lifecycle_statuses(self):
        from routes.payment_vault import _webhook_event_id

        waiting = _webhook_event_id("nowpayments", {"payment_id": "p1", "payment_status": "waiting"})
        finished = _webhook_event_id("nowpayments", {"payment_id": "p1", "payment_status": "finished"})
        assert waiting is not None and waiting != finished
        assert "p1" in waiting and "waiting" in waiting
        assert "p1" in finished and "finished" in finished

    def test_nowpayments_key_missing_status_is_not_claimed(self):
        from routes.payment_vault import _webhook_event_id

        assert _webhook_event_id("nowpayments", {"payment_id": "p1"}) is None

    def test_stripe_uses_real_event_id(self):
        from routes.payment_vault import _webhook_event_id

        assert _webhook_event_id("stripe", {"id": "evt_1"}) == "evt_1"

    def test_cache_outage_is_fail_closed(self, mocker):
        from extensions import cache
        from routes.payment_vault import WebhookDedupUnavailable, _is_duplicate_webhook

        mocker.patch.object(cache, "get", side_effect=RuntimeError("redis down"))
        with pytest.raises(WebhookDedupUnavailable):
            _is_duplicate_webhook("nowpayments", "p1:finished", fail_closed=True)

    def test_marker_is_written_only_after_success(self, mocker):
        from extensions import cache
        from routes.payment_vault import _is_duplicate_webhook, _mark_webhook_processed

        set_marker = mocker.patch.object(cache, "set")
        mocker.patch.object(cache, "get", return_value=None)

        assert _is_duplicate_webhook("nowpayments", "p1:finished", fail_closed=True) is False
        set_marker.assert_not_called()

        _mark_webhook_processed("nowpayments", "p1:finished")
        set_marker.assert_called_once()
        assert "p1:finished" in set_marker.call_args.args[0]


class TestLegacyCallbackDedupCannotBePoisoned:
    def test_read_check_never_claims_key(self):
        from routes.auth import _is_duplicate_callback, _mark_callback_processed, _payment_callback_cache

        _payment_callback_cache.clear()
        assert _is_duplicate_callback("p1", "finished", claim=False) is False
        assert "p1:finished" not in _payment_callback_cache

        _mark_callback_processed("p1", "finished")
        assert _is_duplicate_callback("p1", "finished") is True
        _payment_callback_cache.clear()


class TestBackgroundWorkersAreOneShot:
    def test_auto_approval_reuses_handle_for_same_app(self, mocker):
        from services import auto_approval_service as module

        app = MagicMock()
        thread_cls = mocker.patch("threading.Thread")
        stop_event = threading.Event()

        first = module.schedule_auto_approval(app, stop_event=stop_event, skip_if_scheduled=True)
        second = module.schedule_auto_approval(app, stop_event=stop_event, skip_if_scheduled=True)

        assert first is second
        assert first["stop_event"] is stop_event
        assert thread_cls.call_count == 1

    def test_cleanup_scheduler_skips_second_call(self, mocker):
        from flask import Flask

        from services.logging_core import LoggingCore

        app = Flask("cleanup-one-shot-test")
        thread_cls = mocker.patch("threading.Thread")

        LoggingCore.schedule_cleanup(app, skip_if_scheduled=True)
        LoggingCore.schedule_cleanup(app, skip_if_scheduled=True)

        thread_cls.assert_called_once()

    def test_celery_process_detection(self, monkeypatch):
        from app.factory import _running_in_celery_process

        monkeypatch.setattr("sys.argv", ["celery", "worker", "-A", "wsgi:app"])
        assert _running_in_celery_process() is True
        monkeypatch.setattr("sys.argv", ["gunicorn", "wsgi:app"])
        assert _running_in_celery_process() is False
        monkeypatch.setattr("sys.argv", ["pytest"], raising=False)
        assert _running_in_celery_process() is False
