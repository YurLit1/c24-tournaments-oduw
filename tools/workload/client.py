"""The `ctx` object a scenario receives: HTTP calls, expectations, waiting and polling.

No domain rules and no hidden retries: what is expected, repeated or sent as a key is decided
by the scenario. Used by run.py; a scenario never imports this module itself.
"""

import http.client
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from results import Results

MAX_BODY_BYTES = 1024 * 1024


class CheckFailed(Exception):
    """An expectation of the scenario was not met (an unexpected status or ctx.check)."""


class TransportFailed(Exception):
    """No complete HTTP response was received."""


class ScenarioStopped(Exception):
    """The scenario deadline expired or the operator stopped the run."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Return redirects to the scenario instead of forwarding credentials to another URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]  # names in lower case
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


class Context:
    """One scenario run: its own random generator, deadline and sequence of HTTP calls."""

    def __init__(
        self,
        index: int,
        *,
        bases: Mapping[str, str],
        settings: Mapping[str, str],
        seed: int,
        timeout: float,
        scenario_timeout: float,
        pause: float,
        stop: threading.Event,
        results: Results,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> None:
        self.index = index
        self.bases = dict(bases)
        self.settings = dict(settings)
        self.random = random.Random(f"{seed}:{index}")
        self.timeout = timeout
        self.deadline = time.monotonic() + scenario_timeout
        self.pause = pause
        self.stop = stop
        self.results = results
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def remaining(self) -> float:
        """Seconds left for this run; raises ScenarioStopped when none are left."""
        if self.stop.is_set():
            raise ScenarioStopped("run stopped")

        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ScenarioStopped("scenario deadline exceeded")
        return remaining

    def wait(self, seconds: float) -> None:
        """Pause, but no longer than the deadline allows and not after the run is stopped."""
        seconds = max(0.0, seconds)
        remaining = self.remaining()
        if self.stop.wait(min(seconds, remaining)) or seconds >= remaining:
            raise ScenarioStopped("scenario stopped while waiting")

    def check(self, condition: bool, message: str = "scenario expectation failed") -> None:
        if not condition:
            raise CheckFailed(message)

    def request(
        self,
        method: str,
        path: str,
        *,
        service: str = "api",
        body: Any = None,
        headers: Mapping[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
        label: str = "request",
    ) -> Response:
        """One HTTP call. A status not listed in `expected` fails the scenario."""
        remaining = self.remaining()
        url = self._url(service, path)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        outgoing = {"Accept": "application/json", **(headers or {})}
        if body is not None:
            outgoing.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=payload, headers=outgoing, method=method)

        started = time.monotonic()
        status, outcome = 0, "transport_error"  # recorded as such unless a response arrives
        try:
            result = self._send(request, min(self.timeout, remaining))
            status = result.status
            outcome = "expected" if status in expected else "unexpected_status"
        finally:
            self.results.request(
                self.index, label, method, service, status, time.monotonic() - started, outcome
            )

        if outcome != "expected":
            raise CheckFailed(f"{label}: unexpected HTTP {status}")

        self.remaining()
        if self.pause:
            self.wait(self.pause)
        return result

    def poll(
        self, path: str, done: Callable[[Response], bool], *, interval: float = 0.5, **kwargs: Any
    ) -> Response:
        """GET `path` until `done(response)` is true or the scenario deadline expires."""
        if interval <= 0:
            raise ValueError("poll interval must be positive")

        while True:
            response = self.request("GET", path, **kwargs)
            if done(response):
                return response
            self.wait(interval)

    def _url(self, service: str, path: str) -> str:
        """Join the base of a service and an absolute path; other hosts are refused."""
        parsed = urllib.parse.urlsplit(path)
        if not path.startswith("/") or path.startswith("//") or parsed.scheme or parsed.netloc:
            raise ValueError("request path must be an absolute path within the selected service")
        if parsed.fragment:
            raise ValueError("request path must not contain a fragment")
        return self.bases[service].rstrip("/") + path

    def _send(self, request: urllib.request.Request, timeout: float) -> Response:
        try:
            try:
                response = self.opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                response = error  # a 4xx/5xx answer is still an answer for the scenario

            with response:
                raw = response.read(MAX_BODY_BYTES + 1)
                if len(raw) > MAX_BODY_BYTES:
                    raise TransportFailed("response exceeds 1 MiB")
                headers = {name.lower(): value for name, value in response.headers.items()}

                length = headers.get("content-length")
                if (
                    request.get_method() != "HEAD"
                    and response.code not in (204, 304)
                    and not 100 <= response.code < 200
                    and "transfer-encoding" not in headers
                    and length is not None
                ):
                    try:
                        expected_length = int(length)
                    except ValueError as error:
                        raise TransportFailed("invalid Content-Length") from error
                    if expected_length < 0 or len(raw) != expected_length:
                        raise TransportFailed("incomplete response body")

                return Response(response.code, headers, raw)
        except (OSError, http.client.HTTPException) as error:
            raise TransportFailed(type(error).__name__) from error
