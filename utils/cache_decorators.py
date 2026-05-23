from functools import wraps
from flask import current_app
from extensions import cache
import hashlib
import json


def cached_query(timeout=300, key_prefix=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if key_prefix:
                cache_key = f"{key_prefix}:{hashlib.md5(json.dumps(str(args) + str(kwargs)).encode()).hexdigest()}"
            else:
                cache_key = f"{f.__name__}:{hashlib.md5(json.dumps(str(args) + str(kwargs)).encode()).hexdigest()}"
            
            result = cache.get(cache_key)
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
        if hasattr(cache, 'delete_many'):
            cache.delete_many(key_pattern)
        elif hasattr(cache, 'delete'):
            cache.delete(key_pattern)
    except Exception:
        pass

