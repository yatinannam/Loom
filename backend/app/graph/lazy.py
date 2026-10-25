"""Graph store proxy that connects on first use, so the API can start while Neo4j is
down and recover once it comes up."""

import threading
import time
from collections.abc import Callable

from app.graph.store import GraphStore, GraphUnavailable

RETRY_COOLDOWN_S = 10.0


class LazyGraph:
    def __init__(self, factory: Callable[[], GraphStore]):
        self._factory = factory
        self._store: GraphStore | None = None
        self._lock = threading.Lock()
        self._failed_at = 0.0
        self.last_error: str | None = None

    def get(self) -> GraphStore:
        if self._store is not None:
            return self._store
        with self._lock:
            if self._store is None:
                # Fail fast between attempts instead of waiting on a connect timeout per request.
                if self.last_error and time.monotonic() - self._failed_at < RETRY_COOLDOWN_S:
                    raise GraphUnavailable(self.last_error)
                try:
                    self._store = self._factory()
                    self.last_error = None
                except GraphUnavailable as exc:
                    self._failed_at = time.monotonic()
                    self.last_error = str(exc)
                    raise
        return self._store

    def available(self) -> bool:
        try:
            self.get()
            return True
        except GraphUnavailable:
            return False

    def __getattr__(self, name):
        return getattr(self.get(), name)
