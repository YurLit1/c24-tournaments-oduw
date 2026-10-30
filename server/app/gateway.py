"""WebSocket gateway skeleton (lab 5): `uvicorn app.gateway:app --host 0.0.0.0 --port 8000`.

Two instances run (gateway-a, gateway-b) behind nginx `location = /v1/ws`. Given: the process,
the database pool, the log, /health, the WebSocket endpoint and a place for the broker reader.
Yours (the TODO marks): the ticket and Origin check (O5.1), which connections this instance
holds and how a message reaches them from the other instance (O5.2), the feed and recovery
(O5.3), heartbeat (D5.5) and the slow client (D5.6).
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiokafka.structs import ConsumerRecord
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from . import broker, config, db, metrics, middleware, problems, service, telemetry
from .jsonlog import log


async def on_message(record: ConsumerRecord) -> None:
    """TODO (O5.2): deliver the notification to the connections of its user held here."""
    log("gateway.message", topic=record.topic, partition=record.partition, offset=record.offset)


async def _read_forever(topic: str, group_id: str) -> None:
    """Keep reading even if the broker is not up yet or restarts."""
    while True:
        try:
            await broker.consume(topic, group_id, on_message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the reader must survive any error and retry
            log("gateway.reader_error", error=type(exc).__name__)
            await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await db.open_pool(size=4)
    # GROUP_ID is gateway-a / gateway-b in compose.yaml: every gateway reads every message (O5.2)
    reader = asyncio.create_task(_read_forever("notifications", config.GROUP_ID))
    log("gateway.started")

    yield

    reader.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await reader
    await db.close_pool()
    log("gateway.stopped")


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
middleware.install(app)
problems.install(app)
app.include_router(service.router)
app.include_router(metrics.router)
telemetry.install(app)


@app.websocket("/v1/ws")
async def notifications(socket: WebSocket) -> None:
    # TODO (O5.1): before accept() check the Origin header (only CLIENT_ORIGIN) and the
    # one-time ticket from ?ticket=; take the user from the ticket, never from the client.
    # On failure: await socket.close(code=1008); return
    user_id: str | None = None
    await socket.accept()

    # TODO (O5.2): remember (user_id -> this socket) so that on_message can find it.
    log("ws.opened", user_id=user_id)

    try:
        while True:
            await socket.receive_text()  # TODO (O5.3): the client may report its last applied position
    except WebSocketDisconnect:
        pass
    finally:
        # TODO (O5.2): forget this socket.
        log("ws.closed", user_id=user_id)
