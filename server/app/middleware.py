"""Request id and one JSON log line per request.

X-Request-ID: taken from the request when it looks sane, otherwise a new one; returned in
the response. X-Instance tells the client which instance answered (useful in lab 1 and 2).
The log line has the route TEMPLATE (/v1/items/{id}), not the path with ids.
"""

import re
import time
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from . import config, metrics, problems
from .jsonlog import log

_SANE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


async def observe(request: Request, call_next: RequestResponseEndpoint) -> Response:
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _SANE_ID.match(incoming) else str(uuid.uuid4())
    request.state.request_id = request_id

    started = time.perf_counter()
    status = 500
    try:
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - the answer is built here, so it gets the headers below
            response = problems.crash(request, exc)
        status = response.status_code
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics.observe(request.method, _route_template(request), status, elapsed_ms / 1000)
        log(
            "http.request",
            request_id=request_id,
            method=request.method,
            route=_route_template(request),
            status=status,
            duration_ms=round(elapsed_ms, 1),
        )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Instance"] = config.INSTANCE
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    return response


def install(app: FastAPI) -> None:
    app.middleware("http")(observe)
