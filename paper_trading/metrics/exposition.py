"""Lightweight Prometheus-format metrics exposition.

Provides a MetricsRegistry that accumulates counters, gauges, and histograms
and renders them in Prometheus text format — no external dependency required.
"""

from __future__ import annotations

import threading
from collections import defaultdict


class _Metric:
    __slots__ = ("name", "documentation", "type_name", "_lock")

    def __init__(self, name: str, documentation: str, type_name: str):
        self.name = name
        self.documentation = documentation
        self.type_name = type_name
        self._lock = threading.Lock()


class Counter(_Metric):
    """Monotonically increasing counter."""

    def __init__(self, name: str, documentation: str):
        super().__init__(name, documentation, "counter")
        self._values: dict[tuple, float] = defaultdict(float)

    def inc(self, value: float = 1.0, **labels: str) -> None:
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._values[key] += value

    def _format(self) -> list[str]:
        lines: list[str] = []
        with self._lock:
            for key, val in self._values.items():
                labels_str = ",".join(f'{k}="{v}"' for k, v in key)
                if labels_str:
                    labels_str = "{" + labels_str + "}"
                lines.append(f"{self.name}{labels_str} {val}")
        return lines


class Gauge(_Metric):
    """Single numeric value that can go up or down."""

    def __init__(self, name: str, documentation: str):
        super().__init__(name, documentation, "gauge")
        self._values: dict[tuple, float] = {}

    def set(self, value: float, **labels: str) -> None:
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._values[key] = value

    def inc(self, value: float = 1.0, **labels: str) -> None:
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._values[key] = self._values.get(key, 0.0) + value

    def _format(self) -> list[str]:
        lines: list[str] = []
        with self._lock:
            for key, val in self._values.items():
                labels_str = ",".join(f'{k}="{v}"' for k, v in key)
                if labels_str:
                    labels_str = "{" + labels_str + "}"
                lines.append(f"{self.name}{labels_str} {val}")
        return lines


class Histogram(_Metric):
    """Histogram with configurable buckets (count + sum + per-bucket)."""

    def __init__(self, name: str, documentation: str, buckets: list[float] | None = None):
        super().__init__(name, documentation, "histogram")
        if buckets is None:
            buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._buckets = sorted(buckets)
        self._counts: dict[tuple, list[int]] = defaultdict(lambda: [0] * (len(self._buckets) + 1))
        self._sums: dict[tuple, float] = defaultdict(float)

    def observe(self, value: float, **labels: str) -> None:
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._sums[key] += value
            for i, b in enumerate(self._buckets):
                if value <= b:
                    self._counts[key][i] += 1
            self._counts[key][len(self._buckets)] += 1  # +Inf bucket

    def _format(self) -> list[str]:
        lines: list[str] = []
        with self._lock:
            for key, count_list in self._counts.items():
                labels_str = ",".join(f'{k}="{v}"' for k, v in key)
                if labels_str:
                    labels_str = "{" + labels_str + "}"
                total = count_list[-1]
                for i, b in enumerate(self._buckets):
                    lines.append(f'{self.name}_bucket{labels_str}{{le="{b}"}} {count_list[i]}')
                lines.append(f'{self.name}_bucket{labels_str}{{le="+Inf"}} {total}')
                lines.append(f"{self.name}_count{labels_str} {total}")
                lines.append(f"{self.name}_sum{labels_str} {self._sums.get(key, 0.0)}")
        return lines


class MetricsRegistry:
    """Thread-safe registry of Prometheus metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(self, name: str, documentation: str) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, documentation)
            return self._counters[name]

    def gauge(self, name: str, documentation: str) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, documentation)
            return self._gauges[name]

    def histogram(self, name: str, documentation: str, buckets: list[float] | None = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, documentation, buckets)
            return self._histograms[name]

    def render(self) -> str:
        """Render all metrics in Prometheus text format."""
        lines: list[str] = []
        with self._lock:
            for registry in (self._counters, self._gauges, self._histograms):
                for metric in registry.values():
                    lines.append(f"# HELP {metric.name} {metric.documentation}")
                    lines.append(f"# TYPE {metric.name} {metric.type_name}")
                    lines.extend(metric._format())
        # Prometheus expects a trailing newline
        lines.append("")
        return "\n".join(lines)


# Global registry shared across the application
_registry_lock = threading.Lock()
_registry: MetricsRegistry | None = None


def global_registry() -> MetricsRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = MetricsRegistry()
    return _registry


def _reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    with _registry_lock:
        _registry = None
