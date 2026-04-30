import os
import time
from urllib.parse import urlparse


class ApiRateLimiter:
    """
    Redis-backed API rate limiter driven by integrations.SystemConfig key `api_rate_limits`.

    Expected config format (flat):
    {
      "scope": "auth",
      "default": { "requests": 60, "per_seconds": 60, "mode": "wait" },
      "rules": [
        { "match": { "host": "www.virustotal.com" }, "requests": 4, "per_seconds": 60, "mode": "wait" }
      ]
    }
    """

    _redis_client = None
    _redis_init_failed = False
    _config_cache = None
    _config_cached_at = 0.0
    _config_ttl_seconds = 5.0

    def __init__(self, log_func=None):
        self._log_func = log_func

    def _log(self, msg):
        if self._log_func:
            self._log_func(msg)

    @classmethod
    def _get_redis(cls):
        if cls._redis_client is not None:
            return cls._redis_client
        if cls._redis_init_failed:
            return None

        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
            client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
            client.ping()
            cls._redis_client = client
            return cls._redis_client
        except Exception:
            cls._redis_init_failed = True
            return None

    @classmethod
    def _load_config(cls):
        now = time.time()
        if cls._config_cache is not None and (now - cls._config_cached_at) < cls._config_ttl_seconds:
            return cls._config_cache

        try:
            from integrations.models import SystemConfig
            cfg_obj = SystemConfig.objects.filter(key='api_rate_limits').first()
            cfg = cfg_obj.value if cfg_obj and isinstance(cfg_obj.value, dict) else {}
        except Exception:
            cfg = {}

        cls._config_cache = cfg
        cls._config_cached_at = now
        return cls._config_cache

    @staticmethod
    def _extract_host(url):
        try:
            return (urlparse(url).hostname or '').lower()
        except Exception:
            return ''

    @staticmethod
    def _norm_scope(scope):
        val = str(scope or 'auth').lower().replace(' ', '')
        if val in ('host+auth', 'auth+host'):
            return 'host+auth'
        if val == 'host':
            return 'host'
        return 'auth'

    def _resolve_rule(self, host):
        cfg = self._load_config() or {}

        default = cfg.get('default') if isinstance(cfg.get('default'), dict) else {}
        global_scope = self._norm_scope(cfg.get('scope', 'auth'))

        selected = {
            'requests': int(default.get('requests', 60)),
            'per_seconds': int(default.get('per_seconds', 60)),
            'mode': str(default.get('mode', 'wait')).lower(),
            'scope': global_scope,
        }

        rules = cfg.get('rules') if isinstance(cfg.get('rules'), list) else []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            match = rule.get('match') if isinstance(rule.get('match'), dict) else {}
            rule_host = str(match.get('host', '')).strip().lower()
            if rule_host and rule_host != host:
                continue

            selected['requests'] = int(rule.get('requests', selected['requests']))
            selected['per_seconds'] = int(rule.get('per_seconds', selected['per_seconds']))
            selected['mode'] = str(rule.get('mode', selected['mode'])).lower()
            selected['scope'] = self._norm_scope(rule.get('scope', selected['scope']))
            break

        if selected['requests'] <= 0 or selected['per_seconds'] <= 0:
            return None
        return selected

    @staticmethod
    def _build_scope_key(scope, host, auth_obj):
        auth_part = 'none'
        if auth_obj is not None:
            auth_pk = getattr(auth_obj, 'pk', None)
            auth_part = str(auth_pk) if auth_pk is not None else 'none'

        if scope == 'host':
            return f"host:{host or 'unknown'}"
        if scope == 'host+auth':
            return f"host:{host or 'unknown'}:auth:{auth_part}"
        return f"auth:{auth_part}"

    def acquire(self, url, auth_obj=None):
        client = self._get_redis()
        if not client:
            # Fail-open until Redis is configured/reachable.
            return

        host = self._extract_host(url)
        rule = self._resolve_rule(host)
        if not rule:
            return

        requests_limit = rule['requests']
        per_seconds = rule['per_seconds']
        mode = rule['mode']
        scope_key = self._build_scope_key(rule['scope'], host, auth_obj)

        waited_total = 0.0
        while True:
            now = int(time.time())
            window_start = now - (now % per_seconds)
            redis_key = f"api_rate_limit:{scope_key}:w{window_start}"

            count = client.incr(redis_key)
            if count == 1:
                # Keep key just beyond current window.
                client.expire(redis_key, per_seconds + 1)

            if count <= requests_limit:
                if waited_total > 0:
                    self._log(
                        f"Rate limit window released for {scope_key}. "
                        f"Waited {waited_total:.1f}s; proceeding."
                    )
                return

            ttl = client.ttl(redis_key)
            wait_seconds = max(int(ttl), 1) if ttl is not None else 1

            if mode == 'wait':
                self._log(
                    f"Rate limit reached for {scope_key} ({requests_limit}/{per_seconds}s). "
                    f"Waiting {wait_seconds}s."
                )
                time.sleep(wait_seconds)
                waited_total += float(wait_seconds)
                continue

            raise Exception(
                f"API rate limit exceeded for {scope_key}: "
                f"{requests_limit} requests / {per_seconds}s (mode={mode})."
            )

