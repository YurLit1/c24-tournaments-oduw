"""Sustained load for the example domain "Міська бібліотека": hold, read, cancel (O6.4).

Every run takes the next token of tokens.txt (one access token per line), holds book_id with a
new Idempotency-Key, reads the hold and cancels it. 429 and 503 are repeated with THE SAME key
after Retry-After, at most `attempts` tries (default 3). 409 is a refusal by the rules (this
reader already holds the book) and ends the run without a failure. From the project root, while
tools/rolling-update.sh replaces the instances in another terminal:

    uv run --no-project --python 3.14 python tools/workload/run.py tools/workload/load.example.py \\
        --base api=http://localhost:8080 --set tokens_file=tokens.txt --set book_id=b01 \\
        --duration 90 --rate 10 --concurrency 10 --out runs/update-01

requests.csv and summary.json keep the status and the label of every attempt; the rule for
counting errors in O6.4 is yours. If your API also answers 409 while the same key is still being
processed, tell the two cases apart by the problem type.
"""

from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

REPEAT = (429, 503)
_tokens = []


def validate(bases, settings):
    global _tokens
    if "api" not in bases or not settings.get("tokens_file") or not settings.get("book_id"):
        raise ValueError("supply --base api=..., --set tokens_file=..., --set book_id=...")
    if int(settings.get("attempts", "3")) < 1:
        raise ValueError("attempts must be at least 1")

    _tokens = Path(settings["tokens_file"]).read_text(encoding="utf-8").split()
    if not _tokens:
        raise ValueError("tokens_file must contain at least one access token")


def retry_after(response):
    try:
        return float(response.headers.get("retry-after", "1"))
    except ValueError:
        return 1.0  # an HTTP date instead of seconds


def call(ctx, method, path, *, headers, label, final, body=None):
    """One operation: 429 and 503 are sent again with the same headers, so with the same key."""
    attempts = int(ctx.settings.get("attempts", "3"))
    for attempt in range(1, attempts + 1):
        response = ctx.request(
            method, path, body=body, headers=headers, expected=(*final, *REPEAT), label=label
        )
        if response.status not in REPEAT:
            return response
        if attempt < attempts:
            ctx.wait(retry_after(response))

    ctx.check(False, f"{label}: no final answer after {attempts} attempts")


def scenario(ctx):
    auth = {"Authorization": f"Bearer {_tokens[ctx.index % len(_tokens)]}"}

    created = call(
        ctx,
        "POST",
        "/v1/holds",
        body={"book_id": ctx.settings["book_id"], "branch_id": ctx.settings.get("branch_id", "central")},
        headers={**auth, "Idempotency-Key": str(uuid4())},
        label="create",
        final=(201, 409),
    )
    if created.status == 409:
        return

    path = f"/v1/holds/{quote(str(created.json()['id']), safe='')}"
    call(ctx, "GET", path, headers=auth, label="read", final=(200,))

    cancelled = call(ctx, "POST", f"{path}/cancel", headers=auth, label="cancel", final=(200,))
    ctx.check(cancelled.json()["status"] == "cancelled", "cancel: the hold is not cancelled")
