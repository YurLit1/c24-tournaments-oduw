"""Readiness state of the process, shared by /ready and your shutdown code.

The flag only exists here. What happens on SIGTERM - stop accepting new work (503 with
Retry-After), let started requests finish, close WebSocket connections - is item O6.3.
"""

_draining = False


def start_draining() -> None:
    """TODO (O6.3): call it when the process receives SIGTERM, before it stops serving."""
    global _draining
    _draining = True


def is_draining() -> bool:
    return _draining
