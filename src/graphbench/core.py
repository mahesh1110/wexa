from __future__ import annotations

import json
import math
import os
import platform
import socket
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class NodeRow:
    user_id: int
    name: str
    country: str
    age: int


@dataclass(frozen=True)
class EdgeRow:
    src: int
    dst: int
    weight: float


@dataclass(frozen=True)
class Sample:
    workload: str
    database: str
    started_at: str
    duration_ms: float
    ok: bool
    error: str | None = None
    concurrency: int | None = None


@dataclass
class BenchmarkRun:
    database: str
    started_at: str
    finished_at: str
    host: dict[str, Any]
    platform: dict[str, Any]
    dataset: dict[str, Any]
    settings: dict[str, Any]
    samples: list[Sample]
    notes: list[str]

    def write_json(self, path: str | Path) -> None:
        payload = asdict(self)
        payload["samples"] = [asdict(s) for s in self.samples]
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_fingerprint() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }


def percentiles(values: Iterable[float]) -> dict[str, float | None]:
    xs = sorted(float(v) for v in values)
    if not xs:
        return {"count": 0, "min": None, "p50": None, "p95": None, "p99": None, "max": None, "mean": None}

    def nearest_rank(q: float) -> float:
        index = max(0, min(len(xs) - 1, math.ceil(q * len(xs)) - 1))
        return xs[index]

    return {
        "count": len(xs),
        "min": xs[0],
        "p50": nearest_rank(0.50),
        "p95": nearest_rank(0.95),
        "p99": nearest_rank(0.99),
        "max": xs[-1],
        "mean": statistics.fmean(xs),
    }


def timed_call(fn: Callable[[], Any]) -> tuple[Any, float]:
    start = time.perf_counter_ns()
    value = fn()
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    return value, elapsed_ms


def choose_start_ids(nodes: list[NodeRow], count: int, seed: int) -> list[int]:
    # A small local deterministic PRNG avoids adding a dependency and makes the sample auditable.
    state = seed & 0x7FFFFFFF
    chosen: list[int] = []
    for _ in range(min(count, len(nodes))):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        chosen.append(nodes[state % len(nodes)].user_id)
    return chosen
