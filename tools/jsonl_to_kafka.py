# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "confluent-kafka>=2.16",
# ]
# ///
"""Send the lines of a JSONL file to a Kafka topic in file order.

For debugging the handler and the gateways, and for a joint topic done without the DPC part: the
events that part would publish are written to a file and replayed. The message key is a field of
the event; within a partition the order of the file is kept.

Run from the project root (uv installs the dependency):

    uv run tools/jsonl_to_kafka.py events.jsonl domain-events --key subject --pace-ms 5
    uv run tools/jsonl_to_kafka.py events.jsonl domain-events --key subject --bootstrap localhost:9094

From the host, Kafka must advertise an external listener (port 9094 in the compose
template); otherwise run the tool inside the Compose network. Exit code 1 if any event was
not acknowledged.
"""

import argparse
import json
import math
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Delivery:
    """Broker acknowledgements, filled by the producer's delivery callback."""

    acknowledged: int = 0
    errors: list[str] = field(default_factory=list)

    def __call__(self, error: Any, _message: Any) -> None:
        if error is None:
            self.acknowledged += 1
        else:
            self.errors.append(str(error))


def read_events(path: Path, key_field: str) -> Iterator[tuple[str, str]]:
    """(key, line) for every non-empty line; a line without the key field is an error."""
    with path.open(encoding="utf-8") as lines:
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict) or event.get(key_field) is None:
                raise ValueError(f"line {number}: no key field {key_field!r}")
            yield str(event[key_field]), line.strip()


def produce(producer: Any, topic: str, key: str, value: str, delivery: Delivery, timeout: float) -> None:
    """Enqueue one message; while the local queue is full, serve callbacks and retry."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            producer.produce(topic, key=key, value=value, on_delivery=delivery)
            return
        except BufferError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("the producer queue stayed full") from None
            producer.poll(min(0.1, remaining))


def publish(producer: Any, path: Path, topic: str, key_field: str, pace_ms: float, timeout: float) -> int:
    """Send the file and report acknowledgements; returns the exit code (0 = all delivered)."""
    delivery = Delivery()
    queued = 0
    try:
        for key, value in read_events(path, key_field):
            produce(producer, topic, key, value, delivery, timeout)
            queued += 1
            producer.poll(0)
            if pace_ms:
                time.sleep(pace_ms / 1000)
    except (OSError, ValueError, TimeoutError) as error:
        delivery.errors.append(f"{type(error).__name__}: {error}")

    pending = producer.flush(timeout)
    print(f"queued {queued}; acknowledged {delivery.acknowledged}; pending {pending}; errors {len(delivery.errors)}")
    for error in delivery.errors[:10]:
        print("  ", error)

    return int(bool(delivery.errors) or pending > 0 or delivery.acknowledged != queued)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("topic")
    parser.add_argument("--key", required=True, help="field of the event used as the message key")
    parser.add_argument("--bootstrap", default="localhost:9094")
    parser.add_argument("--pace-ms", type=float, default=0, help="pause between messages")
    parser.add_argument("--timeout", type=float, default=30, help="seconds to wait for a full queue and for delivery")
    args = parser.parse_args()

    if not (math.isfinite(args.timeout) and args.timeout > 0 and math.isfinite(args.pace_ms) and args.pace_ms >= 0):
        parser.error("--timeout must be positive and --pace-ms not negative")

    from confluent_kafka import Producer  # imported here: the functions above work with any producer object

    producer = Producer({"bootstrap.servers": args.bootstrap, "acks": "all", "enable.idempotence": True})
    return publish(producer, args.file, args.topic, args.key, args.pace_ms, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
