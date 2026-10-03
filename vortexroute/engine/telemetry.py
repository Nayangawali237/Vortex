import time
from collections import deque
from threading import Lock
from typing import Dict, List, Optional
import numpy as np


class TelemetryWindow:
    """Sliding-window telemetry tracker using a deque for time-decayed observation."""

    def __init__(self, window_seconds: float = 30.0):
        self.window_seconds = window_seconds
        self.lock = Lock()
        # Stores tuples: (timestamp, latency_ms, is_success)
        self.events: deque = deque()

    def record(self, latency_ms: float, success: bool) -> None:
        now = time.time()
        with self.lock:
            self.events.append((now, latency_ms, success))
            self._evict_stale(now)

    def _evict_stale(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()

    def get_metrics(self) -> Dict[str, float]:
        now = time.time()
        with self.lock:
            self._evict_stale(now)
            if not self.events:
                return {
                    "count": 0,
                    "success_rate": 1.0,
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                }

            latencies = [e[1] for e in self.events]
            successes = [1 if e[2] else 0 for e in self.events]

            return {
                "count": len(latencies),
                "success_rate": float(np.mean(successes)),
                "p50_ms": float(np.percentile(latencies, 50)),
                "p95_ms": float(np.percentile(latencies, 95)),
                "p99_ms": float(np.percentile(latencies, 99)),
            }