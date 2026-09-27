import hashlib
import json
import logging
from functools import wraps

from flask import current_app, g, has_request_context, request

from extensions import cache

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


def _visibility_cache_salt() -> str:
    """Salt covering everything a cached view is allowed to vary by.

    The tenant id alone is not sufficient. Two more dimensions change what a
    tenant-scoped view may return, and both were missing from the key:

    * **Branch scope** — a tenant-wide user (``branch_id IS NULL``) and a
      branch-5 manager share a tenant, so a tenant-wide response was served to
      the branch manager, exposing rows the branch restriction exists to hide.
    * **The query string** — endpoints such as ``/api/analytics/top-customers``
      read ``?limit=`` / ``?page=`` / ``?days=`` from ``request.args`` inside the
      view body rather than as view arguments, so ``args``/``kwargs`` in the
      decorator are ``()`` and every variant collided on one entry. Callers
      silently received whichever variant happened to be cached first.
    """
    if not has_request_context():
        return _tenant_cache_salt()

    from flask_login import current_user

    from utils.branching import branch_scope_id_for

    try:
        branch = branch_scope_id_for(current_user)
    except Exception:  # pragma: no cover - anonymous/edge sessions
        branch = None

    query_string = request.query_string.decode("utf-8", "replace")
    return f"{_tenant_cache_salt()}|b={branch}|q={query_string}"


def cached_query(timeout=300, key_prefix=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            salt = _visibility_cache_salt()
            raw_key = json.dumps(str(args) + str(kwargs) + salt, ensure_ascii=False)
            digest = hashlib.sha256(raw_key.encode(), usedforsecurity=False).hexdigest()
            prefix = key_prefix or f.__name__
            cache_key = f"{prefix}:{digest}"

            try:
                result = cache.get(cache_key)
            except Exception as e:
                # Cache backend down (e.g. Redis refused) must never 500 a page —
                # treat as a miss and serve from source (mirrors the set() guard below).
                current_app.logger.warning(f"Cache get failed for key {cache_key}: {str(e)}")
                result = None
            if result is not None:
                return result

            result = f(*args, **kwargs)
            try:
                cache.set(cache_key, result, timeout=timeout)
            except Exception as e:
                # If caching fails (e.g. UnboundLocalError in cachelib), log it but don't crash
                current_app.logger.warning(f"Cache set failed for key {cache_key}: {str(e)}")
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
