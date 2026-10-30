"""Errors as Problem Details (RFC 9457): application/problem+json with type, title, status, detail.

Raise `Problem(409, "no-copies", "No copies available", detail)` anywhere in a route; the
handlers below also turn 404 of unknown routes, invalid input and unexpected errors into
the same format. Which statuses and types your API uses is part of your contract (O1.3).
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from . import config
from .jsonlog import log

MEDIA_TYPE = "application/problem+json"


class Problem(Exception):
    def __init__(
        self,
        status: int,
        slug: str,
        title: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(title)
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail
        self.headers = headers or {}
        self.extra = extra

    def response(self, instance: str) -> JSONResponse:
        body: dict[str, Any] = {
            "type": config.PROBLEM_BASE + self.slug,
            "title": self.title,
            "status": self.status,
        }
        if self.detail:
            body["detail"] = self.detail
        body["instance"] = instance
        body.update(self.extra)

        return JSONResponse(body, status_code=self.status, headers=self.headers, media_type=MEDIA_TYPE)


def install(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def on_problem(request: Request, exc: Problem) -> JSONResponse:
        return exc.response(request.url.path)

    @app.exception_handler(HTTPException)
    async def on_http(request: Request, exc: HTTPException) -> JSONResponse:
        slug = {404: "not-found", 405: "method-not-allowed"}.get(exc.status_code, "http-error")
        problem = Problem(exc.status_code, slug, str(exc.detail), headers=dict(exc.headers or {}))
        return problem.response(request.url.path)

    @app.exception_handler(RequestValidationError)
    async def on_invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Body that is not JSON at all -> 400; JSON with wrong fields or values -> 422."""
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", ())), "message": e.get("msg", "")} for e in exc.errors()
        ]

        if any(e.get("type") == "json_invalid" for e in exc.errors()):
            problem = Problem(400, "malformed-json", "Request body is not valid JSON", errors=errors)
        else:
            problem = Problem(422, "invalid-request", "Invalid request data", errors=errors)
        return problem.response(request.url.path)

    @app.exception_handler(Exception)
    async def on_crash(request: Request, exc: Exception) -> JSONResponse:
        return crash(request, exc)


def crash(request: Request, exc: Exception) -> JSONResponse:
    """500 for an unexpected error. The middleware calls it itself: the handler of Exception
    runs outside all middleware, and its answer would have no X-Request-ID."""
    log("request.crash", error=type(exc).__name__)  # the type only: messages may contain data
    return Problem(500, "internal-error", "Internal server error").response(request.url.path)
