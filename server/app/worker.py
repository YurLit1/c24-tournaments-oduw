"""Event handler (O4.3), a separate process: `python -m app.worker` (service worker, GROUP_ID=worker).

Stub: starts and waits. Yours: broker.consume("domain-events", config.GROUP_ID, handle), where
handle calls the simulator (EXTERNAL_URL) and commits the result in one transaction;
fault("after_external_before_commit"); retries and the quarantine domain-events.dlq (D4.4).
"""

import asyncio

from . import background
from .jsonlog import log


async def main(stop: asyncio.Event) -> None:
    log("todo", item="O4.3", what="event handler")
    await stop.wait()


if __name__ == "__main__":
    background.run(main)
