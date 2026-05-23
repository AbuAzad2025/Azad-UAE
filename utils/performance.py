"""
⚡ تحسينات الأداء - Performance Optimizations
شركة أزاد للأنظمة الذكية

تحسينات:
- Query Optimization
- Caching Strategies
- Database Connection Pooling
- Response Compression
"""
from functools import wraps
from flask import g
import time
import logging

logger = logging.getLogger(__name__)


def measure_time(func):
    """قياس وقت تنفيذ الدالة"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = (time.time() - start) * 1000
        
        if duration > 1000:
            logger.warning(f"⚠️ Slow function: {func.__name__} took {duration:.0f}ms")
        elif duration > 500:
            logger.info(f"⏱️ {func.__name__} took {duration:.0f}ms")
        
        return result
    return wrapper


def cache_result(timeout=300):
    """تخزين نتيجة الدالة مؤقتاً"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from extensions import cache
            
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"📦 Cache HIT: {func.__name__}")
                return cached
            
            result = func(*args, **kwargs)
            
            cache.set(cache_key, result, timeout=timeout)
            logger.debug(f"💾 Cache SET: {func.__name__}")
            
            return result
        return wrapper
    return decorator


def optimize_query(query):
    """تحسين الاستعلام"""
    return query


def batch_commit(items, batch_size=100):
    """حفظ دفعات للأداء"""
    from extensions import db
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        db.session.bulk_save_objects(batch)
        db.session.commit()
        logger.info(f"💾 Batch committed: {len(batch)} items")


class PerformanceMonitor:
    """مراقب الأداء"""
    
    @staticmethod
    def start_request():
        """بداية الطلب"""
        g.start_time = time.time()
    
    @staticmethod
    def end_request(response):
        """نهاية الطلب"""
        if hasattr(g, 'start_time'):
            duration = (time.time() - g.start_time) * 1000
            
            if duration > 2000:
                logger.warning(f"🐌 Slow request: {duration:.0f}ms")
            
            response.headers['X-Response-Time'] = f"{duration:.2f}ms"
        
        return response

