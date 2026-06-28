import json
import time
import hashlib
import logging
logger = logging.getLogger(__name__)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.info("redis not installed - using in-memory cache")
class CacheManager:
    def __init__(self, host="localhost", port=6379, ttl=86400):
        self.ttl = ttl
        self.redis_client = None
        self._memory_cache = {}
        self._cache_stats = {"hits": 0, "misses": 0}
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(host=host, port=port, db=0, decode_responses=True)
                self.redis_client.ping()
                logger.info("Connected to Redis cache")
            except Exception as e:
                logger.warning(f"Redis not available ({e}) - falling back to in-memory cache")
                self.redis_client = None
    def _make_key(self, prefix: str, params: dict) -> str:
        param_str = json.dumps(params, sort_keys=True)
        hash_val = hashlib.md5(param_str.encode()).hexdigest()[:12]
        return f"wb:{prefix}:{hash_val}"
    def get(self, prefix: str, params: dict):
        key = self._make_key(prefix, params)
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    self._cache_stats["hits"] += 1
                    logger.debug(f"Cache HIT: {key}")
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        else:
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if time.time() - entry["timestamp"] < self.ttl:
                    self._cache_stats["hits"] += 1
                    logger.debug(f"Memory cache HIT: {key}")
                    return entry["data"]
                else:
                    del self._memory_cache[key]
        self._cache_stats["misses"] += 1
        return None
    def set(self, prefix: str, params: dict, data):
        key = self._make_key(prefix, params)
        if self.redis_client:
            try:
                self.redis_client.setex(key, self.ttl, json.dumps(data))
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
        else:
            self._memory_cache[key] = {
                "data": data,
                "timestamp": time.time()
            }
    def get_stats(self) -> dict:
        total = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (self._cache_stats["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "hit_rate_percent": round(hit_rate, 1),
            "backend": "redis" if self.redis_client else "in-memory"
        }
