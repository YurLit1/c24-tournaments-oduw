import json
import sys
from datetime import UTC, datetime

from . import config


def log(event: str, **fields: object) -> None:
    line = {
        "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "instance": config.INSTANCE,
        "event": event,
    }
    line.update(fields)
    sys.stdout.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
