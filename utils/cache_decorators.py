import logging
from functools import wraps
from flask import current_app, g, has_request_context
from extensions import cache
import hashlib
import json

logger = logging.getLogger(__name__)


def _tenant_cache_salt() -> str:
    """Return the active tenant id as a cache salt to prevent cross-tenant leakage.

    Replaces: None (new security fix — cross-tenant cache poisoning).
    """
    if has_request_context():
        tid = getattr(g, "active_tenant_id", None) or getattr(g, "tenant_id", None)
        if tid is not None:
            return str(tid)
    return ""


def cached_query(timeout=300, key_prefix=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            salt = _tenant_cache_salt()
            raw_key = json.dumps(str(args) + str(kwargs) + salt, ensure_ascii=False)
            digest = hashlib.sha256(raw_key.encode(), usedforsecurity=False).hexdigest()
            prefix = key_prefix or f.__name__
            cache_key = f"{prefix}:{digest}"

            result = cache.get(cache_key)
            if result is not None:
                return result

            result = f(*args, **kwargs)
            try:
                cache.set(cache_key, result, timeout=timeout)
            except Exception as e:
                # If caching fails (e.g. UnboundLocalError in cachelib), log it but don't crash
                current_app.logger.warning(
                    f"Cache set failed for key {cache_key}: {str(e)}"
                )
            return result

        return decorated_function

    return decorator


def invalidate_cache(key_pattern):
    try:
        from extensions import cache

        if hasattr(cache, "delete_many"):
            cache.delete_many(key_pattern)
        elif hasattr(cache, "delete"):
            cache.delete(key_pattern)
    except Exception:
        logger.warning("Failed to invalidate cache for pattern: %s", key_pattern, exc_info=True)
