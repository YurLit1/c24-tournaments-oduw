"""Service routes that are the same for every topic: GET /health and GET /ready."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import config, db, lifecycle

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process answers. No database call, so it stays fast under load."""
    return {"status": "ok", "instance": config.INSTANCE}


@router.get("/ready")
async def ready() -> JSONResponse:
    """Readiness: this instance may receive requests (database reachable, not shutting down)."""
    if lifecycle.is_draining():
        return JSONResponse({"status": "draining"}, status_code=503, headers={"Retry-After": "1"})
    if not await db.ping():
        return JSONResponse({"status": "database unavailable"}, status_code=503, headers={"Retry-After": "1"})
    return JSONResponse({"status": "ready", "instance": config.INSTANCE})
