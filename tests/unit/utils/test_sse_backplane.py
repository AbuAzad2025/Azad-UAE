"""Behavioral tests for utils.sse_backplane (fake Redis transport, no network)."""

import json
import logging
import queue
import sys
import threading
import time
import types
from datetime import UTC, datetime

import pytest

import utils.sse_backplane as sse_backplane
from utils.sse_backplane import publish, reset_client_for_tests, subscribe


class FakePubSub:
    """Stand-in for redis PubSub: replays scripted messages, then idles cheaply."""

    def __init__(self, messages=()):
        self.messages = list(messages)
        self.channels = []
        self.closed = False
        self.close_should_fail = False
        self.raise_on_get = False
        self._lock = threading.Lock()

    def subscribe(self, channel):
        self.channels.append(channel)

    def get_message(self, timeout=1.0):
        if self.raise_on_get:
            raise RuntimeError("connection reset")
        with self._lock:
            if self.messages:
                return self.messages.pop(0)
        time.sleep(0.001)
        return None

    def close(self):
        if self.close_should_fail:
            raise RuntimeError("close boom")
        self.closed = True


class FakeRedisClient:
    def __init__(self):
        self.published = []
        self.pubsub_to_return = None
        self.raise_on_pubsub = False
        self.ping_should_fail = False
        self.publish_should_fail = False
        self.pubsub_kwargs = None

    def ping(self):
        if self.ping_should_fail:
            raise ConnectionError("redis unreachable")
        return True

    def publish(self, channel, body):
        if self.publish_should_fail:
            raise ConnectionError("broken pipe")
        self.published.append((channel, body))
        return len(self.published)

    def pubsub(self, **kwargs):
        if self.raise_on_pubsub:
            raise RuntimeError("pubsub unavailable")
        self.pubsub_kwargs = kwargs
        assert self.pubsub_to_return is not None, "test must set pubsub_to_return"
        return self.pubsub_to_return


@pytest.fixture
def redis_env(monkeypatch):
    """Install a fake `redis` module and reset the backplane singleton."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    container = {}

    def _install(*, fail_ping=False):
        client = FakeRedisClient()
        client.ping_should_fail = fail_ping
        calls = {}

        fake_module = types.ModuleType("redis")

        def _from_url(url, **kwargs):
            calls.setdefault("attempts", []).append(url)
            calls["url"] = url
            calls["kwargs"] = kwargs
            return client

        fake_module.Redis = types.SimpleNamespace(from_url=_from_url)
        monkeypatch.setitem(sys.modules, "redis", fake_module)
        reset_client_for_tests()
        container["client"] = client
        container["calls"] = calls
        return client, calls

    yield _install
    reset_client_for_tests()


def _find_thread(name):
    for thread in threading.enumerate():
        if thread.name == name:
            return thread
    return None


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestRedisClientLifecycle:
    def test_client_created_once_and_cached(self, redis_env):
        client, calls = redis_env()
        first = sse_backplane._redis_client()
        second = sse_backplane._redis_client()

        assert first is client
        assert second is first
        assert calls["url"] == "redis://localhost:6379/0"
        kwargs = calls["kwargs"]
        assert kwargs["socket_timeout"] == 1.5
        assert kwargs["socket_connect_timeout"] == 1.5
        assert kwargs["health_check_interval"] == 30
        assert kwargs["protocol"] == 2

    def test_redis_url_env_var_is_honoured(self, redis_env, monkeypatch):
        _, calls = redis_env()
        monkeypatch.setenv("REDIS_URL", "redis://example.test:6380/3")

        sse_backplane._redis_client()

        assert calls["url"] == "redis://example.test:6380/3"

    def test_ping_failure_disables_backplane_without_retrying(self, redis_env, caplog):
        _, calls = redis_env(fail_ping=True)

        with caplog.at_level(logging.WARNING, logger="utils.sse_backplane"):
            assert sse_backplane._redis_client() is None
            assert sse_backplane._redis_client() is None

        assert len(calls["attempts"]) == 1  # failure flag prevents reconnect storms
        assert sse_backplane._client_failed is True
        assert any("SSE backplane Redis connection failed" in r.message for r in caplog.records)

    def test_missing_redis_library_disables_backplane(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "redis", None)
        reset_client_for_tests()
        try:
            assert sse_backplane._redis_client() is None
            assert sse_backplane._client_failed is True
            assert publish("chan", {"a": 1}) is False
        finally:
            reset_client_for_tests()

    def test_concurrent_callers_share_one_client(self, redis_env):
        """Two threads racing initialization must both get the same client."""
        client, calls = redis_env()
        original_ping = client.ping

        def slow_ping():
            time.sleep(0.4)
            return original_ping()

        client.ping = slow_ping
        results = []

        def caller():
            results.append(sse_backplane._redis_client())

        first = threading.Thread(target=caller, name="sse-race-a")
        first.start()
        time.sleep(0.15)  # first thread is inside ping, second blocks on the lock
        second = threading.Thread(target=caller, name="sse-race-b")
        second.start()
        first.join(timeout=5)
        second.join(timeout=5)

        assert results == [client, client]
        assert len(calls["attempts"]) == 1


class TestPublish:
    def test_publish_serializes_payload_and_returns_true(self, redis_env):
        client, _ = redis_env()
        ts = datetime(2026, 8, 26, 10, 30, 0, tzinfo=UTC)

        result = publish("kds:42", {"type": "refresh", "note": "تحديث الطلب", "ts": ts})

        assert result is True
        channel, body = client.published[0]
        assert channel == "kds:42"
        decoded = json.loads(body)
        assert decoded["type"] == "refresh"
        assert decoded["note"] == "تحديث الطلب"
        assert "تحديث الطلب" in body  # ensure_ascii=False kept the Arabic literal
        assert decoded["ts"] == str(ts)  # default=str handled non-JSON types

    def test_publish_returns_false_when_unavailable(self, redis_env):
        redis_env(fail_ping=True)
        assert publish("kds:42", {"type": "refresh"}) is False

    def test_publish_failure_is_swallowed_and_logged(self, redis_env, caplog):
        client, _ = redis_env()
        client.publish_should_fail = True

        with caplog.at_level(logging.WARNING, logger="utils.sse_backplane"):
            result = publish("kds:7", {"type": "refresh"})

        assert result is False
        assert any("SSE backplane publish failed on kds:7" in r.message for r in caplog.records)


class TestSubscribeFanout:
    def test_messages_fan_out_to_subscriber_queue_and_unsubscribe_stops_reader(self, redis_env):
        client, _ = redis_env()
        messages = [
            {"type": "message", "data": json.dumps({"type": "refresh", "order": 1}).encode("utf-8")},
            {"type": "message", "data": b"not-json{{"},
            {"type": "subscribe", "data": b"ignored-non-message"},
            {"type": "message", "data": ["raw", "list"]},
            {"type": "message", "data": '{"type": "refresh", "order": 2}'},
        ]
        pubsub = FakePubSub(messages)
        client.pubsub_to_return = pubsub

        target = queue.Queue(maxsize=16)
        unsubscribe = subscribe("tenant-9:kds", target)

        assert callable(unsubscribe)
        assert pubsub.channels == ["tenant-9:kds"]
        assert client.pubsub_kwargs["ignore_subscribe_messages"] is True

        # bytes JSON payload is decoded and parsed
        assert target.get(timeout=5) == {"type": "refresh", "order": 1}
        # undecodable JSON becomes a refresh envelope carrying the raw data
        raw = target.get(timeout=5)
        assert raw == {"type": "refresh", "raw": "not-json{{"}
        # non-bytes data failing json.loads falls back to a raw envelope
        fallback = target.get(timeout=5)
        assert fallback["type"] == "refresh"
        assert fallback["raw"] == ["raw", "list"]
        # non-message types are filtered out; str JSON still parses
        assert target.get(timeout=5) == {"type": "refresh", "order": 2}

        unsubscribe()
        thread = _find_thread("sse-backplane-tenant-9:kds")
        assert thread is not None
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert pubsub.closed is True

    def test_queue_full_stops_reader_and_closes_pubsub(self, redis_env):
        client, _ = redis_env()
        pubsub = FakePubSub(
            [{"type": "message", "data": json.dumps({"type": "refresh", "n": 1}).encode("utf-8")}]
        )
        client.pubsub_to_return = pubsub

        target = queue.Queue(maxsize=1)
        target.put({"seed": "already-full"})

        subscribe("tenant-8:kds", target)

        # reader hits Full on the first delivery and exits without draining
        assert _wait_until(lambda: pubsub.closed)
        assert target.get_nowait() == {"seed": "already-full"}
        assert target.qsize() == 0  # overflow message was dropped

    def test_reader_crash_closes_pubsub_and_logs_warning(self, redis_env, caplog):
        client, _ = redis_env()
        pubsub = FakePubSub()
        pubsub.raise_on_get = True
        client.pubsub_to_return = pubsub

        with caplog.at_level(logging.WARNING, logger="utils.sse_backplane"):
            subscribe("tenant-7:kds", queue.Queue(maxsize=4))

        thread = _find_thread("sse-backplane-tenant-7:kds")
        assert _wait_until(lambda: pubsub.closed and not thread.is_alive())
        assert any("SSE backplane reader stopped on tenant-7:kds" in r.message for r in caplog.records)

    def test_pubsub_close_failure_is_swallowed_at_debug_level(self, redis_env):
        client, _ = redis_env()
        pubsub = FakePubSub(
            [{"type": "message", "data": json.dumps({"ok": True}).encode("utf-8")}]
        )
        pubsub.close_should_fail = True
        client.pubsub_to_return = pubsub
        target = queue.Queue(maxsize=4)

        debug_records = []
        probe = logging.getLogger("utils.sse_backplane")

        class _Probe(logging.Handler):
            def emit(self, record):
                debug_records.append(record.getMessage())

        handler = _Probe(level=logging.DEBUG)
        old_level, old_propagate = probe.level, probe.propagate
        probe.addHandler(handler)
        probe.setLevel(logging.DEBUG)
        try:
            unsubscribe = subscribe("tenant-6:kds", target)
            assert target.get(timeout=5) == {"ok": True}
            unsubscribe()
            thread = _find_thread("sse-backplane-tenant-6:kds")
            assert thread is not None
            assert _wait_until(lambda: not thread.is_alive())
        finally:
            probe.removeHandler(handler)
            probe.setLevel(old_level)
            probe.propagate = old_propagate

        assert any("SSE pubsub close failed" in message for message in debug_records)

    def test_subscribe_returns_none_when_redis_down(self, redis_env):
        redis_env(fail_ping=True)
        assert subscribe("tenant-5:kds", queue.Queue()) is None

    def test_subscribe_failure_returns_none_and_logs(self, redis_env, caplog):
        client, _ = redis_env()
        client.raise_on_pubsub = True

        with caplog.at_level(logging.WARNING, logger="utils.sse_backplane"):
            result = subscribe("tenant-4:kds", queue.Queue())

        assert result is None
        assert any("SSE backplane subscribe failed on tenant-4:kds" in r.message for r in caplog.records)


class TestResetForTests:
    def test_reset_clears_cached_client_and_failure_flag(self, redis_env):
        client, _ = redis_env(fail_ping=True)
        assert sse_backplane._redis_client() is None
        assert sse_backplane._client_failed is True

        reset_client_for_tests()

        assert sse_backplane._client is None
        assert sse_backplane._client_failed is False
