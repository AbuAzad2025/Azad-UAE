from functools import wraps
from flask import request, jsonify
from flask_login import current_user
from extensions import cache
from datetime import datetime


def smart_rate_limit(max_requests: int, window_seconds: int = 60):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.is_authenticated and current_user.is_owner:
                return f(*args, **kwargs)

            key = f"rate_limit:{request.endpoint}:{request.remote_addr}"

            requests_made = cache.get(key) or []
            now = datetime.now()

            requests_made = [
                req_time
                for req_time in requests_made
                if (now - req_time).total_seconds() < window_seconds
            ]

            if len(requests_made) >= max_requests:
                return (
                    jsonify(
                        {"error": "Rate limit exceeded", "retry_after": window_seconds}
                    ),
                    429,
                )

            requests_made.append(now)
            cache.set(key, requests_made, timeout=window_seconds)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def adaptive_rate_limit(base_limit: int = 60):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.is_authenticated:
                if current_user.is_owner:
                    limit = base_limit * 100
                elif current_user.is_super_admin():
                    limit = base_limit * 10
                elif current_user.is_manager():
                    limit = base_limit * 5
                else:
                    limit = base_limit
            else:
                limit = base_limit // 2

            key = f"adaptive_limit:{request.endpoint}:{current_user.id if current_user.is_authenticated else request.remote_addr}"

            count = cache.get(key) or 0

            if count >= limit:
                return (
                    jsonify(
                        {
                            "error": "Rate limit exceeded",
                            "your_limit": limit,
                            "window": "60 seconds",
                        }
                    ),
                    429,
                )

            cache.set(key, count + 1, timeout=60)

            return f(*args, **kwargs)

        return decorated_function

    return decorator
