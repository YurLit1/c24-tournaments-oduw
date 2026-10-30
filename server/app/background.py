"""Common start of the background processes (publisher, worker, router): log, wait, stop on SIGTERM."""

import asyncio
import signal
from collections.abc import Awaitable, Callable

from .jsonlog import log


def run(main: Callable[[asyncio.Event], Awaitable[None]]) -> None:
    async def wrapper() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

        log("process.started")
        await main(stop)
        log("process.stopped")

    asyncio.run(wrapper())
