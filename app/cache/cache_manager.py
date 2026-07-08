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
    logger.info("redis not installed — using in-memory cache (install redis to enable persistence)")


class CacheManager:
    def __init__(self, host="localhost", port=6379, ttl=86400):
        self.ttl = ttl
        self.redis_client = None
        self._memory_cache = {}
        self._cache_stats = {"hits": 0, "misses": 0}

        if REDIS_AVAILABLE:
            try:
                client = redis.Redis(host=host, port=port, db=0, decode_responses=True)
                client.ping()                          # confirms server is actually up
                self.redis_client = client
                logger.info(f"Connected to Redis at {host}:{port}")
            except Exception as e:
                logger.warning(f"Redis not reachable ({e}) — falling back to in-memory cache")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_key(self, prefix: str, params: dict) -> str:
        param_str = json.dumps(params, sort_keys=True)
        hash_val = hashlib.md5(param_str.encode()).hexdigest()[:12]
        return f"wb:{prefix}:{hash_val}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, prefix: str, params: dict):
        key = self._make_key(prefix, params)

        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    self._cache_stats["hits"] += 1
                    logger.debug(f"Cache HIT (redis): {key}")
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        else:
            entry = self._memory_cache.get(key)
            if entry:
                if time.time() - entry["timestamp"] < self.ttl:
                    self._cache_stats["hits"] += 1
                    logger.debug(f"Cache HIT (memory): {key}")
                    return entry["data"]
                del self._memory_cache[key]

        self._cache_stats["misses"] += 1
        return None

    def set(self, prefix: str, params: dict, data) -> None:
        key = self._make_key(prefix, params)

        if self.redis_client:
            try:
                self.redis_client.setex(key, self.ttl, json.dumps(data))
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
        else:
            self._memory_cache[key] = {"data": data, "timestamp": time.time()}

    def get_stats(self) -> dict:
        total = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (self._cache_stats["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "hit_rate_percent": round(hit_rate, 1),
            "backend": "redis" if self.redis_client else "in-memory",
        }
