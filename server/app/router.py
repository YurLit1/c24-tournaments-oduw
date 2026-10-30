"""Addressed routing (D5.1), a separate process: `python -m app.router` (service router).

Stub: starts and waits. Yours: the registry "user -> gateway" with a lease (cache.client()) and
sending a notification only to the gateways that hold connections of its user.
"""

import asyncio

from . import background
from .jsonlog import log


async def main(stop: asyncio.Event) -> None:
    log("todo", item="D5.1", what="addressed routing")
    await stop.wait()


if __name__ == "__main__":
    background.run(main)
