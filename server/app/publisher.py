"""Outbox publisher (O4.2), a separate process: `python -m app.publisher` (service publisher).

Stub: starts and waits. Yours: read a batch of the outbox with FOR UPDATE SKIP LOCKED, send it
with broker.send() and mark it published after the broker confirmed; fault("publisher_before_send").
"""

import asyncio

from . import background
from .jsonlog import log


async def main(stop: asyncio.Event) -> None:
    log("todo", item="O4.2", what="outbox publisher")
    await stop.wait()


if __name__ == "__main__":
    background.run(main)
