"""Row generator for the query-plan experiment (Web lab 2, D2.7): 10^5 rows and more.

Writes CSV to stdout from a small JSON description of the columns. The seed is fixed, so the
plan "before" and "after" the index is measured on the same data. Standard library only.

Run from the project root (the example schema; docs/ENVIRONMENT.md, D2.7):

    python tools/generator/generate.py tools/generator/spec.example.json 100000 > rows.csv
    docker compose exec -T postgres psql -U app \\
      -c "\\copy hold (id, user_id, branch_id, book_id, status, created_at, expires_at) FROM STDIN CSV" < rows.csv

Column kinds:
  {"kind": "seq", "prefix": "h_"}                              h_0000001, h_0000002, ...
  {"kind": "choice", "values": ["a", "b"], "weights": [9, 1]}
  {"kind": "int", "min": 1, "max": 6}
  {"kind": "timestamp", "from": "2025-01-01T00:00:00+00:00", "days": 600}
  {"kind": "const", "value": "x"}
  {"kind": "ref", "prefix": "user", "count": 500}              user000 ... user499 (rows that exist!)

Rows must respect your constraints: generate closed objects (cancelled, finished) if
counters of active objects would be broken otherwise.
"""

import argparse
import csv
import itertools
import json
import random
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

type Column = Callable[[], Any]


def make_column(spec: dict[str, Any], rnd: random.Random) -> Column:
    """Turn one column description into a function that returns the next value."""
    kind = spec["kind"]

    if kind == "seq":
        prefix, counter = spec.get("prefix", ""), itertools.count(1)
        return lambda: f"{prefix}{next(counter):07d}"

    if kind == "choice":
        values, weights = spec["values"], spec.get("weights")
        return lambda: rnd.choices(values, weights)[0]

    if kind == "int":
        low, high = spec["min"], spec["max"]
        return lambda: rnd.randint(low, high)

    if kind == "timestamp":
        start, span_s = datetime.fromisoformat(spec["from"]), int(spec.get("days", 365) * 86400)
        return lambda: (start + timedelta(seconds=rnd.randint(0, span_s))).isoformat()

    if kind == "const":
        value = spec["value"]
        return lambda: value

    if kind == "ref":
        prefix, count = spec["prefix"], spec["count"]
        width = len(str(count - 1))
        return lambda: f"{prefix}{rnd.randrange(count):0{width}d}"

    raise ValueError(f"unknown column kind {kind!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", type=Path, help="JSON description of the columns")
    parser.add_argument("rows", type=int, nargs="?", default=100_000)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    rnd = random.Random(spec.get("seed", 42))
    columns = {name: make_column(column, rnd) for name, column in spec["columns"].items()}

    out = csv.writer(sys.stdout, lineterminator="\n")
    for _ in range(args.rows):
        out.writerow([make() for make in columns.values()])

    print(f"-- {args.rows} rows of ({', '.join(columns)})", file=sys.stderr)


if __name__ == "__main__":
    main()
