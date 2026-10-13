"""登录固定时间窗限流；Redis add/incr 避免并发读写计数丢失。"""
import hashlib
import time

from django.core.cache import cache
from rest_framework.throttling import BaseThrottle


class LoginRateThrottle(BaseThrottle):
    def allow_request(self, request, view):
        now = time.time()
        window = int(now // 60)
        self.retry_after = 60 - now % 60
        username = str(request.data.get('username', '')).strip().casefold()
        identities = [('ip', self.get_ident(request), 10)]
        if username:
            identities.append(('username', username, 5))
        allowed = True
        for scope, identity, limit in identities:
            digest = hashlib.sha256(identity.encode()).hexdigest()
            key = f'login:{scope}:{digest}:{window}'
            if cache.add(key, 1, timeout=120):
                count = 1
            else:
                count = cache.incr(key)
            allowed = allowed and count <= limit
        return allowed

    def wait(self):
        return self.retry_after
