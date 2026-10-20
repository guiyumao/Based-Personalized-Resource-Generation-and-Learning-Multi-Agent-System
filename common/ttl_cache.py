"""A small thread-safe TTL + capacity bounded cache.

Used for expensive, *deterministic* derived data such as the knowledge-graph
visualization payload. Design constraints that matter for that use case:

* thread-safe — FastAPI runs sync endpoints in a worker thread pool, so several
  requests can hit the same cache concurrently;
* bounded — both by TTL and by a maximum entry count, so a long-running process
  cannot grow without limit;
* explicit success/failure — callers must only ``set`` values they consider
  complete; this cache never stores exceptions, and ``get`` never raises;
* no cross-user leakage by construction — the caller owns the key, so callers
  must include every input that changes the value.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CacheStats:
    """Point-in-time counters for one cache instance."""

    hits: int
    misses: int
    sets: int
    evictions: int
    expirations: int
    entries: int


class TTLCache:
    """Least-recently-used cache with per-entry expiry."""

    def __init__(
        self, *, ttl_seconds: float, max_entries: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._clock = clock
        self._lock = threading.RLock()
        self._entries: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._evictions = 0
        self._expirations = 0

    # ------------------------------------------------------------------ public
    def get(self, key: Hashable) -> Any | None:
        """Return the cached value, or ``None`` when absent/expired."""

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            expires_at, value = entry
            if self._clock() >= expires_at:
                del self._entries[key]
                self._expirations += 1
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: Hashable, value: Any) -> None:
        """Store ``value`` under ``key``, evicting the LRU entry when full."""

        with self._lock:
            self._entries[key] = (self._clock() + self._ttl, value)
            self._entries.move_to_end(key)
            self._sets += 1
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
                self._evictions += 1

    def get_or_set(self, key: Hashable, factory: Callable[[], Any]) -> tuple[Any, bool]:
        """Return ``(value, from_cache)``.

        ``factory`` runs outside the lock, so a slow (or failing) factory never
        blocks readers of other keys. The factory's value is cached only when it
        is not ``None``; exceptions propagate without poisoning the cache.
        """

        cached = self.get(key)
        if cached is not None:
            return cached, True
        value = factory()
        if value is not None:
            self.set(key, value)
        return value, False

    def invalidate(self, key: Hashable) -> bool:
        """Drop one entry; returns whether it existed."""

        with self._lock:
            return self._entries.pop(key, None) is not None

    def clear(self) -> None:
        """Drop every entry (counters are preserved)."""

        with self._lock:
            self._entries.clear()

    def stats(self) -> CacheStats:
        """Snapshot the counters."""

        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                sets=self._sets,
                evictions=self._evictions,
                expirations=self._expirations,
                entries=len(self._entries),
            )
