"""Race through both instances (O2.1) for the example domain "Міська бібліотека".

One pair holds b-one (one available copy) through app-a and app-b. tokens.txt contains
two access tokens for TWO DIFFERENT readers, one per line; neither has an active hold.
From the project root:

    uv run --no-project --python 3.14 python tools/workload/run.py tools/workload/scenario.example.py \\
        --base a=http://localhost:8001 --base b=http://localhost:8002 \\
        --set tokens_file=tokens.txt --set book_id=b-one --runs 2 --rate 100 \\
        --concurrency 2 --out runs/race-01

Use exactly two runs and two workers. A barrier aligns client sends; server-side overlap
still needs traces or an instrumented pause in the tested critical section. Check exactly
one 201, one 409 and one active hold in the database. Reset data before the next pair.
This is not a sustained-load scenario.
"""

from pathlib import Path
from threading import Barrier
from uuid import uuid4

_tokens = []
_barrier = None


def validate(bases, settings):
    global _tokens, _barrier
    if not {"a", "b"} <= set(bases) or not settings.get("tokens_file") or not settings.get("book_id"):
        raise ValueError("supply --base a=..., --base b=..., --set tokens_file=..., --set book_id=...")

    _tokens = Path(settings["tokens_file"]).read_text(encoding="utf-8").split()
    if len(_tokens) != 2 or len(set(_tokens)) != 2:
        raise ValueError("tokens_file must contain two distinct tokens for different readers")

    _barrier = Barrier(2, timeout=5)


def scenario(ctx):
    ctx.check(ctx.index < 2, "use exactly --runs 2 --concurrency 2")
    _barrier.wait(timeout=min(5, ctx.remaining()))

    ctx.request(
        "POST",
        "/v1/holds",
        service="a" if ctx.index % 2 == 0 else "b",
        body={
            "book_id": ctx.settings["book_id"],
            "branch_id": ctx.settings.get("branch_id", "central"),
        },
        headers={
            "Authorization": f"Bearer {_tokens[ctx.index]}",
            "Idempotency-Key": str(uuid4()),
        },
        expected=(201, 409),
        label="hold",
    )
