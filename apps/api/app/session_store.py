import threading
import time

from app.dialogue.manager import SessionState


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = ttl_seconds
        self._items: dict[str, tuple[float, SessionState]] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> SessionState:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(session_id)
            if item is None or item[0] < now:
                self._items.pop(session_id, None)
                return SessionState()
            return item[1]

    def put(self, session_id: str, state: SessionState) -> None:
        with self._lock:
            self._items[session_id] = (time.monotonic() + self.ttl, state)
