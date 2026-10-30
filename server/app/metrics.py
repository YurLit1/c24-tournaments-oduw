"""GET /metrics in the Prometheus text format: requests by route and status, response time.

Prometheus (configs/prometheus) reads it; Grafana shows the dashboard "Web project".
"""

import threading
from collections import Counter

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_lock = threading.Lock()
_requests: Counter[tuple[str, str, int]] = Counter()
_buckets: Counter[tuple[str, float]] = Counter()
_sum: Counter[str] = Counter()
_count: Counter[str] = Counter()

router = APIRouter()


def observe(method: str, route: str, status: int, seconds: float) -> None:
    with _lock:
        _requests[(method, route, status)] += 1
        _sum[route] += seconds
        _count[route] += 1
        for bound in BUCKETS:
            if seconds <= bound:
                _buckets[(route, bound)] += 1


def _label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def render() -> str:
    lines = ["# TYPE http_requests_total counter"]
    with _lock:
        for (method, route, status), n in sorted(_requests.items()):
            lines.append(f'http_requests_total{{method="{method}",route="{_label(route)}",status="{status}"}} {n}')

        lines.append("# TYPE http_request_duration_seconds histogram")
        for route in sorted(_count):
            r = _label(route)
            for bound in BUCKETS:
                lines.append(
                    f'http_request_duration_seconds_bucket{{route="{r}",le="{bound}"}} {_buckets[(route, bound)]}'
                )
            lines.append(f'http_request_duration_seconds_bucket{{route="{r}",le="+Inf"}} {_count[route]}')
            lines.append(f'http_request_duration_seconds_sum{{route="{r}"}} {_sum[route]:.6f}')
            lines.append(f'http_request_duration_seconds_count{{route="{r}"}} {_count[route]}')

    return "\n".join(lines) + "\n"


@router.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(render(), media_type="text/plain; version=0.0.4")
