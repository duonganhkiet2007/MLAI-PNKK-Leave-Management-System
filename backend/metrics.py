"""
metrics.py
Lightweight monotonic timing and concurrency instrumentation for SQLite transactions,
VLM inferences, and leave submission lifecycles.
Thread-safe. Never logs PII, confidential medical data, or raw documents.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional


class PerformanceMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.lock_waits: List[float] = []       # lock acquisition wait time (seconds)
        self.tx_durations: List[float] = []     # write transaction duration (seconds)
        self.vlm_durations: List[float] = []    # VLM inference duration (seconds)
        self.submit_durations: List[float] = [] # leave submission duration (seconds)
        self.e2e_durations: List[float] = []    # end-to-end processing duration (seconds)
        self.vlm_calls_count: int = 0
        self.vlm_cache_hits_count: int = 0
        self.submissions_count: int = 0
        self.submissions_202_count: int = 0
        self.submissions_200_count: int = 0

    def record_lock_wait(self, duration_sec: float) -> None:
        with self._lock:
            self.lock_waits.append(duration_sec)
            if len(self.lock_waits) > 2000:
                self.lock_waits = self.lock_waits[-1000:]

    def record_tx_duration(self, duration_sec: float) -> None:
        with self._lock:
            self.tx_durations.append(duration_sec)
            if len(self.tx_durations) > 2000:
                self.tx_durations = self.tx_durations[-1000:]

    def record_vlm_duration(self, duration_sec: float) -> None:
        with self._lock:
            self.vlm_durations.append(duration_sec)
            if len(self.vlm_durations) > 2000:
                self.vlm_durations = self.vlm_durations[-1000:]

    def record_vlm_call(self, is_cache_hit: bool = False) -> None:
        with self._lock:
            self.vlm_calls_count += 1
            if is_cache_hit:
                self.vlm_cache_hits_count += 1

    def record_submission(self, duration_sec: float, status_code: int = 200) -> None:
        with self._lock:
            self.submissions_count += 1
            if status_code == 202:
                self.submissions_202_count += 1
            else:
                self.submissions_200_count += 1
            self.submit_durations.append(duration_sec)
            if len(self.submit_durations) > 2000:
                self.submit_durations = self.submit_durations[-1000:]

    def record_e2e_duration(self, duration_sec: float) -> None:
        with self._lock:
            self.e2e_durations.append(duration_sec)
            if len(self.e2e_durations) > 2000:
                self.e2e_durations = self.e2e_durations[-1000:]

    def reset(self) -> None:
        with self._lock:
            self.lock_waits.clear()
            self.tx_durations.clear()
            self.vlm_durations.clear()
            self.submit_durations.clear()
            self.e2e_durations.clear()
            self.vlm_calls_count = 0
            self.vlm_cache_hits_count = 0
            self.submissions_count = 0
            self.submissions_202_count = 0
            self.submissions_200_count = 0

    @staticmethod
    def _stats(arr: List[float]) -> Dict[str, float]:
        if not arr:
            return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "avg_ms": 0.0, "max_ms": 0.0}
        s = sorted(arr)
        n = len(s)
        p50 = s[int(n * 0.50)] * 1000.0
        p95 = s[min(n - 1, int(n * 0.95))] * 1000.0
        p99 = s[min(n - 1, int(n * 0.99))] * 1000.0
        avg = (sum(s) / n) * 1000.0
        mx = s[-1] * 1000.0
        return {
            "count": n,
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "avg_ms": round(avg, 2),
            "max_ms": round(mx, 2),
        }

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sqlite_lock_wait": self._stats(self.lock_waits),
                "sqlite_tx_duration": self._stats(self.tx_durations),
                "vlm_inference_duration": self._stats(self.vlm_durations),
                "submission_acknowledgment": self._stats(self.submit_durations),
                "e2e_completion": self._stats(self.e2e_durations),
                "vlm_calls_total": self.vlm_calls_count,
                "vlm_cache_hits_total": self.vlm_cache_hits_count,
                "submissions_total": self.submissions_count,
                "submissions_200_total": self.submissions_200_count,
                "submissions_202_total": self.submissions_202_count,
            }


# Global singleton instance
GLOBAL_METRICS = PerformanceMetrics()
