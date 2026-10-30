"""The API process (app-a, app-b): `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Your work goes into new modules that you include below. Where each lab plugs in:
  TODO (O1.4, O1.5) routers of your topic: the main operation and the list with a cursor
  TODO (O2.1-O2.3)  invariant under concurrency, idempotency keys, fault("after_commit_before_response")
  TODO (O3.1-O3.3)  login and logout, access to objects, staff function, CORS for CLIENT_ORIGIN
  TODO (O4.1-O4.4)  long operation, outbox in the same transaction (publisher and handler are
                    separate processes: app/publisher.py, app/worker.py)
  TODO (O5.1)       POST /v1/ws-tickets; the gateway itself is app/gateway.py
  TODO (O6.3)       SIGTERM: lifecycle.start_draining(), finish started requests
The contract of all routes is your openapi.yaml (start from openapi.example.yaml).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import cache, db, metrics, middleware, problems, service, telemetry
from .jsonlog import log


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await db.open_pool()

    log("app.started")
    yield

    await cache.close()
    await db.close_pool()

    log("app.stopped")


# The contract is openapi.yaml of your repository, so the generated schema routes are off.
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
middleware.install(app)
problems.install(app)
app.include_router(service.router)
app.include_router(metrics.router)
telemetry.install(app)
# app.include_router(your_module.router)
