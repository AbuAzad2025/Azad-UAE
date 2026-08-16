"""Optional Redis pub/sub backplane for SSE fan-out across Gunicorn workers.

In-process subscriber lists (e.g. KDS/CFD queues) only reach clients connected
to the same worker. When Redis is reachable, every publish is additionally
fanned out through a tenant-scoped channel so any worker can forward it to its
own SSE clients. When Redis is absent (tests, single-worker dev), the module
degrades silently to in-process delivery only.

Pure transport — no tenant data is stored, only ephemeral channel messages.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading

logger = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()
_client_failed = False


def _redis_client():
    """Lazy singleton Redis client; None when unreachable (never raises)."""
    global _client, _client_failed
    if _client is not None or _client_failed:
        return _client
    with _client_lock:
        if _client is not None or _client_failed:
            return _client
        try:
            import redis
        except ImportError:
            _client_failed = True
            return None
        try:
            url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            candidate = redis.Redis.from_url(
                url,
                socket_timeout=1.5,
                socket_connect_timeout=1.5,
                health_check_interval=30,
                protocol=2,
            )
            candidate.ping()
            _client = candidate
        except Exception:
            logger.warning("SSE backplane Redis connection failed", exc_info=True)
            _client_failed = True
            return None
    return _client


def publish(channel: str, payload: dict) -> bool:
    """Publish a JSON payload to a channel. Returns False when Redis is down."""
    client = _redis_client()
    if client is None:
        return False
    try:
        client.publish(channel, json.dumps(payload, ensure_ascii=False, default=str))
        return True
    except Exception as exc:
        logger.warning("SSE backplane publish failed on %s: %s", channel, exc)
        return False


def subscribe(channel: str, target_queue: queue.Queue):
    """Feed messages from a Redis channel into a local queue.

    Returns an unsubscribe callable, or None when Redis is unavailable — the
    caller keeps relying on its in-process fan-out in that case.
    """
    client = _redis_client()
    if client is None:
        return None
    try:
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel)
    except Exception as exc:
        logger.warning("SSE backplane subscribe failed on %s: %s", channel, exc)
        return None

    stop_event = threading.Event()

    def _reader():
        try:
            while not stop_event.is_set():
                message = pubsub.get_message(timeout=1.0)
                if not message or message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                try:
                    payload = json.loads(data)
                except (ValueError, TypeError):
                    payload = {"type": "refresh", "raw": data}
                try:
                    target_queue.put_nowait(payload)
                except queue.Full:
                    break
        except Exception as exc:
            logger.warning("SSE backplane reader stopped on %s: %s", channel, exc)
        finally:
            try:
                pubsub.close()
            except Exception:
                logger.debug("SSE pubsub close failed", exc_info=True)

    thread = threading.Thread(target=_reader, name=f"sse-backplane-{channel}", daemon=True)
    thread.start()

    def _unsubscribe():
        stop_event.set()

    return _unsubscribe


def reset_client_for_tests() -> None:
    """Drop the cached client so tests can exercise both availability states."""
    global _client, _client_failed
    with _client_lock:
        _client = None
        _client_failed = False
