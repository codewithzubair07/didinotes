import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.limit = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
