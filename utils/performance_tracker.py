import time
import logging
from functools import wraps
from flask import g, request

logger = logging.getLogger(__name__)


def track_performance(threshold_ms=1000):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            start_time = time.time()
            
            result = f(*args, **kwargs)
            
            elapsed_time = (time.time() - start_time) * 1000
            
            if elapsed_time > threshold_ms:
                logger.warning(
                    f"Slow operation: {f.__name__} took {elapsed_time:.2f}ms "
                    f"(threshold: {threshold_ms}ms)"
                )
            else:
                logger.debug(f"{f.__name__} completed in {elapsed_time:.2f}ms")
            
            if hasattr(g, 'performance_metrics'):
                g.performance_metrics[f.__name__] = elapsed_time
            else:
                g.performance_metrics = {f.__name__: elapsed_time}
            
            return result
        
        return decorated_function
    return decorator


class PerformanceContext:
    def __init__(self, operation_name):
        self.operation_name = operation_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (time.time() - self.start_time) * 1000
        logger.info(f"{self.operation_name} took {elapsed:.2f}ms")


def log_slow_queries(app):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    
    @event.listens_for(Engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault('query_start_time', []).append(time.time())
    
    @event.listens_for(Engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total = time.time() - conn.info['query_start_time'].pop()
        
        if total > 0.1:
            logger.warning(f"Slow query ({total:.3f}s): {statement[:100]}")

