"""Controlled failures (see docs/FAULTS.md).

Put `fault("after_commit_before_response")` exactly where the failure must happen. With
FAULTS=on and the file /faults/<place> present the process removes the file, writes the
log line `fault.hit` and dies at once: no finally blocks, no graceful shutdown. Docker
restarts it (restart: unless-stopped). Where to put each call is part of the lab.

The file is taken by removing it, one atomic operation: of several processes that reach the
place together only one succeeds, the others go on. A separate "exists?" check before the
removal would let two of them pass it and both die.
"""

import os
from pathlib import Path

from . import config
from .jsonlog import log


def fault(place: str) -> None:
    if not config.FAULTS:
        return
    try:
        (Path(config.FAULT_DIR) / place).unlink()  # once: after the restart the system works normally
    except FileNotFoundError:
        return  # not armed, or another process took it first
    log("fault.hit", place=place)
    os._exit(1)
