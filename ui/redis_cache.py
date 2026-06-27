import os
import json
import redis
from utils.logger import logger

class MockRedis:
    def __init__(self):
        self._data = {}
        self._lists = {}
        self._sets = {}
        
    def ping(self):
        return True
        
    def get(self, key):
        return self._data.get(key)
        
    def set(self, key, value, ex=None):
        self._data[key] = str(value)
        return True
        
    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                count += 1
            if k in self._lists:
                del self._lists[k]
                count += 1
            if k in self._sets:
                del self._sets[k]
                count += 1
        return count

    def hset(self, name, key=None, value=None, mapping=None):
        if name not in self._data:
            self._data[name] = {}
        if mapping:
            for k, v in mapping.items():
                self._data[name][k] = str(v)
            return len(mapping)
        else:
            self._data[name][key] = str(value)
            return 1
            
    def hget(self, name, key):
        return self._data.get(name, {}).get(key)
        
    def hgetall(self, name):
        return self._data.get(name, {})
        
    def rpush(self, name, *values):
        if name not in self._lists:
            self._lists[name] = []
        for val in values:
            self._lists[name].append(str(val))
        return len(self._lists[name])

    def lpop(self, name):
        if name in self._lists and self._lists[name]:
            return self._lists[name].pop(0)
        return None

    def sadd(self, name, *values):
        if name not in self._sets:
            self._sets[name] = set()
        count = 0
        for val in values:
            if str(val) not in self._sets[name]:
                self._sets[name].add(str(val))
                count += 1
        return count
        
    def srem(self, name, *values):
        if name not in self._sets:
            return 0
        count = 0
        for val in values:
            if str(val) in self._sets[name]:
                self._sets[name].remove(str(val))
                count += 1
        return count
        
    def smembers(self, name):
        return self._sets.get(name, set())

    def sismember(self, name, value):
        return str(value) in self._sets.get(name, set())

    def publish(self, channel, message):
        return 1


_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        logger.info(f"Connected to Redis at {redis_url}")
        _redis_client = client
    except Exception as e:
        logger.warning(f"Could not connect to Redis at {redis_url}: {e}. Falling back to in-memory MockRedis.")
        _redis_client = MockRedis()
    return _redis_client


class LiveSnapshotCache:
    @staticmethod
    def save_live_snapshot(symbol: str, data: dict):
        client = get_redis_client()
        client.hset("live_market_snapshot", symbol, json.dumps(data, default=str))

    @staticmethod
    def get_live_snapshot(symbol: str) -> dict | None:
        client = get_redis_client()
        val = client.hget("live_market_snapshot", symbol)
        if val:
            try:
                return json.loads(val)
            except Exception:
                return None
        return None

    @staticmethod
    def get_all_snapshots() -> dict:
        client = get_redis_client()
        raw = client.hgetall("live_market_snapshot")
        snapshots = {}
        for k, v in raw.items():
            try:
                snapshots[k] = json.loads(v)
            except Exception:
                continue
        return snapshots

    @staticmethod
    def queue_missing_symbol(symbol: str):
        client = get_redis_client()
        if not client.sismember("missing_symbol_set", symbol):
            client.sadd("missing_symbol_set", symbol)
            client.rpush("missing_symbol_queue", symbol)

    @staticmethod
    def pop_missing_symbol() -> str | None:
        client = get_redis_client()
        symbol = client.lpop("missing_symbol_queue")
        if symbol:
            client.srem("missing_symbol_set", symbol)
        return symbol

    @staticmethod
    def publish_delta(symbol: str, data: dict):
        client = get_redis_client()
        payload = json.dumps({"symbol": symbol, "data": data}, default=str)
        client.publish("market_deltas", payload)
