"""Statistics accumulators — the KPI layer.

Two kinds, following the industry-converged split (salabim/kalasim monitors,
Arena's tally vs time-persistent statistics):

- :class:`TallyMonitor` — observation-based (wait time, time in system).
- :class:`LevelMonitor` — a value that persists over time (queue length, WIP,
  utilization); all statistics are duration-weighted.

Both support a warm-up ``reset(t)`` that discards everything observed so far
(re-basing the time origin for level monitors, keeping the current value).
"""

from __future__ import annotations

import math

import numpy as np


def _percentile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Weighted percentile (q in [0, 100]) by cumulative weight."""
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    target = q / 100.0 * cw[-1]
    idx = int(np.searchsorted(cw, target))
    return float(v[min(idx, len(v) - 1)])


class TallyMonitor:
    """Observation-based statistics."""

    def __init__(self, name: str):
        self.name = name
        self._values: list[float] = []

    def observe(self, value: float) -> None:
        self._values.append(float(value))

    def reset(self, t: float = 0.0) -> None:
        self._values.clear()

    # -- statistics ------------------------------------------------------

    @property
    def n(self) -> int:
        return len(self._values)

    def values(self) -> np.ndarray:
        return np.asarray(self._values, dtype=float)

    def mean(self) -> float:
        return float(np.mean(self._values)) if self._values else math.nan

    def std(self) -> float:
        return float(np.std(self._values, ddof=1)) if len(self._values) > 1 else math.nan

    def minimum(self) -> float:
        return float(np.min(self._values)) if self._values else math.nan

    def maximum(self) -> float:
        return float(np.max(self._values)) if self._values else math.nan

    def median(self) -> float:
        return self.percentile(50)

    def percentile(self, q: float) -> float:
        return float(np.percentile(self._values, q)) if self._values else math.nan

    def histogram(self, bins: int = 20) -> tuple[list[float], list[float]]:
        if not self._values:
            return [], []
        counts, edges = np.histogram(self._values, bins=bins)
        return counts.tolist(), edges.tolist()

    def summary(self) -> dict:
        return {
            "kind": "tally",
            "name": self.name,
            "n": self.n,
            "mean": self.mean(),
            "std": self.std(),
            "min": self.minimum(),
            "p50": self.median(),
            "p95": self.percentile(95) if self._values else math.nan,
            "max": self.maximum(),
        }


class LevelMonitor:
    """Duration-weighted statistics for a value that persists over time.

    Call ``set(value, t)`` at every change; call ``finalize(t_end)`` once at
    the end of the run so the last segment is counted.
    """

    def __init__(self, name: str, initial: float = 0.0, t: float = 0.0):
        self.name = name
        self._value = float(initial)
        self._last_t = float(t)
        self._segments_v: list[float] = []
        self._segments_w: list[float] = []
        # (t, value) step series kept for warm-up plots / Welch analysis.
        self._series: list[tuple[float, float]] = [(float(t), float(initial))]

    @property
    def value(self) -> float:
        return self._value

    def set(self, value: float, t: float) -> None:
        if t < self._last_t:
            raise ValueError(f"LevelMonitor {self.name}: time went backwards ({t} < {self._last_t})")
        if t > self._last_t:
            self._segments_v.append(self._value)
            self._segments_w.append(t - self._last_t)
            self._last_t = t
        self._value = float(value)
        self._series.append((float(t), float(value)))

    def increment(self, delta: float, t: float) -> None:
        self.set(self._value + delta, t)

    def finalize(self, t_end: float) -> None:
        if t_end > self._last_t:
            self._segments_v.append(self._value)
            self._segments_w.append(t_end - self._last_t)
            self._last_t = t_end

    def reset(self, t: float) -> None:
        """Warm-up reset: discard history, keep the current value, re-base time."""
        self._segments_v.clear()
        self._segments_w.clear()
        self._last_t = float(t)
        self._series = [(float(t), self._value)]

    # -- statistics (all duration-weighted) ------------------------------

    def duration(self) -> float:
        return float(sum(self._segments_w))

    def mean(self) -> float:
        w = self.duration()
        if w == 0:
            return math.nan
        return float(np.dot(self._segments_v, self._segments_w) / w)

    def std(self) -> float:
        w = self.duration()
        if w == 0:
            return math.nan
        m = self.mean()
        var = float(
            np.dot((np.asarray(self._segments_v) - m) ** 2, self._segments_w) / w
        )
        return math.sqrt(max(var, 0.0))

    def minimum(self) -> float:
        return float(np.min(self._segments_v)) if self._segments_v else math.nan

    def maximum(self) -> float:
        return float(np.max(self._segments_v)) if self._segments_v else math.nan

    def percentile(self, q: float) -> float:
        if not self._segments_v:
            return math.nan
        return _percentile(
            np.asarray(self._segments_v), np.asarray(self._segments_w), q
        )

    def series(self) -> list[tuple[float, float]]:
        """The (t, value) step series — drives time charts and Welch plots."""
        return list(self._series)

    def summary(self) -> dict:
        return {
            "kind": "level",
            "name": self.name,
            "duration": self.duration(),
            "mean": self.mean(),
            "std": self.std(),
            "min": self.minimum(),
            "p50": self.percentile(50),
            "p95": self.percentile(95),
            "max": self.maximum(),
        }
