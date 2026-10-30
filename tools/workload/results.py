"""Results of a run: every HTTP attempt streamed to requests.csv, a summary in summary.json.

URLs, bodies and credentials are never written. Used by run.py and client.py.
"""

import csv
import json
import math
import threading
from collections import Counter, deque
from pathlib import Path
from typing import Any

LATENCY_SAMPLES = 10_000
CSV_HEADER = ["scenario", "label", "method", "service", "status", "seconds", "outcome"]
PERCENTILES = (("p50", 0.50), ("p95", 0.95), ("p99", 0.99))


class Results:
    """Thread-safe collector; keeps the latest LATENCY_SAMPLES latencies for the percentiles."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)  # a new folder: old results are never overwritten
        self.file = (self.folder / "requests.csv").open("w", encoding="utf-8", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow(CSV_HEADER)

        self.lock = threading.Lock()
        self.statuses: Counter[str] = Counter()
        self.outcomes: Counter[str] = Counter()
        self.scenarios: Counter[str] = Counter()
        self.samples: deque[float] = deque(maxlen=LATENCY_SAMPLES)

    def request(
        self, index: int, label: str, method: str, service: str, status: int, seconds: float, outcome: str
    ) -> None:
        with self.lock:
            self.writer.writerow([index, label, method, service, status, f"{seconds:.6f}", outcome])
            self.statuses[str(status)] += 1
            self.outcomes[outcome] += 1
            self.samples.append(seconds)

    def scenario(self, outcome: str) -> None:
        with self.lock:
            self.scenarios[outcome] += 1

    def finish(self, elapsed: float, skipped: int, interrupted: bool) -> dict[str, Any]:
        """Close the CSV and write the summary; call only after all scenarios have stopped."""
        self.file.close()

        ordered = sorted(self.samples)
        percentiles = {
            name: ordered[max(0, math.ceil(len(ordered) * share) - 1)] if ordered else None
            for name, share in PERCENTILES
        }

        summary = {
            "elapsed_seconds": elapsed,
            "requests": sum(self.statuses.values()),
            "http_statuses": dict(self.statuses),
            "request_outcomes": dict(self.outcomes),
            "scenarios": dict(self.scenarios),
            "skipped_starts": skipped,
            "interrupted": interrupted,
            "request_latency_seconds": percentiles,
            "latency_sample_count": len(ordered),
            "latency_sample_policy": f"last {LATENCY_SAMPLES} completed HTTP attempts",
        }

        (self.folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return summary
