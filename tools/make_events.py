"""Events from a list of ids: one CloudEvents line per id (standard library only).

Web without DPC: the DPC part would publish "a copy was returned" for a hold. Write such events
for your holds and send them to the topic your worker reads. Run from the project root:

    python tools/make_events.py --type library.copy.returned.v1 --id-field hold_id \\
        --fields '{"branch_id": "central"}' h_1 h_2 h_3 > returns.jsonl
    uv run tools/jsonl_to_kafka.py returns.jsonl domain-events --key subject --pace-ms 200

The envelope follows the CloudEvent schema of asyncapi.example.yaml; the id is also `subject`, the
message key. The same arguments give the same event ids, so a repeated send is a duplicate delivery
that the handler must apply once.
"""

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="+", help="ids of the entities the events are about")
    parser.add_argument("--type", required=True, help="event type with its version, e.g. library.copy.returned.v1")
    parser.add_argument("--id-field", default="id", help="name of the id in data")
    parser.add_argument("--source", default="/imitated-part")
    parser.add_argument("--fields", default="{}", help="JSON object of constant fields added to data")
    parser.add_argument("--start", default=datetime.now(UTC).isoformat(timespec="seconds"))
    parser.add_argument("--step-s", type=float, default=1.0, help="seconds between event times")
    args = parser.parse_args()

    try:
        extra = json.loads(args.fields)
        start = datetime.fromisoformat(args.start)
    except ValueError as error:
        parser.error(f"--fields must be a JSON object and --start an ISO 8601 time: {error}")
    if not isinstance(extra, dict):
        parser.error("--fields must be a JSON object")
    if start.tzinfo is None:
        parser.error("--start needs a time zone, e.g. 2026-10-12T08:00:00+00:00")

    for number, entity in enumerate(args.ids):
        moment = start + timedelta(seconds=number * args.step_s)
        event = {
            "specversion": "1.0",
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{args.type}/{entity}")),
            "source": args.source,
            "type": args.type,
            "subject": entity,
            "time": moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "datacontenttype": "application/json",
            "data": {args.id_field: entity, **extra},
        }
        sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
