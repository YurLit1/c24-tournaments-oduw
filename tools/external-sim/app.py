"""Simulator of a slow external provider (Web course, lab 4).

One process imitates the provider of your topic card: payment gateway, insurer, scooter
lock, courier service. It is configured with environment variables; the code is not changed.

It runs as the service external-sim of compose.yaml (port 8090); its settings are in .env.

Routes:
  POST {SIM_ROUTE}     Idempotency-Key header is required; any JSON body
      -> 200 {"status": "accepted", "effect_id": "...", "key": "..."}   effect done
      -> 200 {"status": "rejected", "reason": "...", "key": "..."}      refused by content
      -> 503 {"status": "unavailable"}                                  temporary, retry later
  GET  /effects?key=K1&key=K2     effects by key (each key must have at most one)
  GET  /effects                   all effects
  POST /admin/unavailable?seconds=N   every operation request gets 503, repeats included
  POST /admin/reset               forget everything; 409 while operations are in progress
  GET  /health

Rules the lab 4 experiments rely on:
  * a final result (accepted or rejected) is remembered by key: a repeat with the same key
    returns it and creates no second effect;
  * 503 is not remembered: a repeat with the same key may succeed;
  * concurrent requests with one key wait for each other: still one effect;
  * with SIM_SEED the outcome and the delay depend only on (seed, key, attempt number);
    effect ids and timestamps stay random, attempt counters restart with the process.
Run exactly one process: the memory of keys is local to it.

Environment:
  SIM_NAME            name in logs and responses (default "provider")
  SIM_ROUTE           POST route (default /operations)
  SIM_DELAY_MS        "1000-8000" random delay or "500" fixed
  SIM_REJECT_SHARE    share of final refusals (default 0.2)
  SIM_ERROR_SHARE     share of 503 answers (default 0.05)
  SIM_REJECT_REASONS  "reason one|reason two"
  SIM_SEED            integer for reproducible outcomes (empty = random)
  SIM_STATE_FILE      JSON-lines file: remembered results survive a restart
"""

import asyncio
import hashlib
import json
import os
import random
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

type Result = dict[str, Any]

NAME = os.environ.get("SIM_NAME", "provider")
ROUTE = os.environ.get("SIM_ROUTE", "/operations")
DELAY = os.environ.get("SIM_DELAY_MS", "1000-8000")
REJECT = float(os.environ.get("SIM_REJECT_SHARE", "0.2"))
ERROR = float(os.environ.get("SIM_ERROR_SHARE", "0.05"))
REASONS = [reason for reason in os.environ.get("SIM_REJECT_REASONS", "request rejected").split("|") if reason]
SEED = os.environ.get("SIM_SEED", "")
STATE_FILE = os.environ.get("SIM_STATE_FILE", "")

app = FastAPI(title=f"{NAME} simulator", docs_url=None, redoc_url=None)

results: dict[str, Result] = {}
effects: dict[str, list[str]] = {}
attempts: dict[str, int] = {}
locks: dict[str, asyncio.Lock] = {}
down_until = 0.0
in_progress = 0  # operation requests that entered and have not answered yet


def log(event: str, **fields: Any) -> None:
    line = {
        "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "sim": NAME,
        "event": event,
        **fields,
    }
    print(json.dumps(line, ensure_ascii=False), flush=True)


def _remember(key: str, result: Result) -> None:
    results[key] = result
    if result["status"] == "accepted":
        effects.setdefault(key, []).append(result["effect_id"])


def _load() -> None:
    """Restore remembered results from SIM_STATE_FILE (called at import, i.e. on start)."""
    if not STATE_FILE or not Path(STATE_FILE).exists():
        return
    with Path(STATE_FILE).open(encoding="utf-8") as lines:
        for line in lines:
            row = json.loads(line)
            _remember(row["key"], row["result"])


def _save(key: str, result: Result) -> None:
    """Persist a final result before publishing it in memory or returning it."""
    if not STATE_FILE:
        return
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with Path(STATE_FILE).open("a", encoding="utf-8") as lines:
        lines.write(json.dumps({"key": key, "result": result}, ensure_ascii=False) + "\n")


_load()


def _draw(key: str, attempt: int) -> float:
    """A number in [0, 1): reproducible from (seed, key, attempt) when SIM_SEED is set."""
    if not SEED:
        return random.random()
    digest = hashlib.sha256(f"{SEED}/{key}/{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _delay_s(key: str, attempt: int) -> float:
    if "-" not in DELAY:
        return int(DELAY) / 1000
    low, high = (int(bound) for bound in DELAY.split("-"))
    return (low + (high - low) * _draw(f"{key}/delay", attempt)) / 1000


def _final_result(key: str, attempt: int, draw: float) -> Result:
    if draw < ERROR + REJECT:
        reason = REASONS[int(_draw(f"{key}/reason", attempt) * len(REASONS))]
        return {"status": "rejected", "reason": reason, "key": key, "provider": NAME}

    effect_id = f"{NAME[:3]}-{uuid.uuid4().hex[:10]}"
    return {
        "status": "accepted",
        "effect_id": effect_id,
        "order_id": effect_id,
        "key": key,
        "provider": NAME,
        "done_at": datetime.now(UTC).isoformat(),
    }


def _unavailable(key: str, retry_after_s: int) -> JSONResponse:
    headers = {"Retry-After": str(retry_after_s)}
    return JSONResponse({"status": "unavailable", "key": key}, status_code=503, headers=headers)


@app.post(ROUTE, response_model=None)
async def operate(request: Request) -> Result | JSONResponse:
    """One operation; requests with the same key are serialised by a per-key lock."""
    key = request.headers.get("idempotency-key")
    if not key:
        return JSONResponse({"error": "Idempotency-Key header is required"}, status_code=400)

    try:
        body = await request.json()
    except ValueError:
        body = None

    global in_progress
    in_progress += 1  # counted while waiting for the lock too: reset must not drop a lock someone awaits
    try:
        async with locks.setdefault(key, asyncio.Lock()):
            if time.time() < down_until:
                return _unavailable(key, retry_after_s=2)

            if key in results:
                log("repeat", key=key, status=results[key]["status"])
                return results[key]

            attempts[key] = attempts.get(key, 0) + 1
            attempt = attempts[key]
            await asyncio.sleep(_delay_s(key, attempt))

            draw = _draw(key, attempt)
            if draw < ERROR:
                log("temporary_error", key=key, attempt=attempt)
                return _unavailable(key, retry_after_s=1)

            result = _final_result(key, attempt, draw)
            _save(key, result)
            _remember(key, result)
            log("final", key=key, attempt=attempt, status=result["status"], request=body)
            return result
    finally:
        in_progress -= 1


@app.get("/effects")
async def list_effects(request: Request) -> dict[str, Any]:
    chosen = request.query_params.getlist("key") or list(effects)
    by_key = {
        key: {
            "effects": len(effects.get(key, [])),
            "ids": effects.get(key, []),
            "result": results.get(key, {}).get("status"),
        }
        for key in chosen
    }
    return {
        "effects": by_key,
        "total_effects": sum(len(ids) for ids in effects.values()),
        "keys_with_duplicates": [key for key, ids in effects.items() if len(ids) > 1],
    }


@app.post("/admin/unavailable")
async def unavailable(seconds: float = 10) -> dict[str, float]:
    global down_until
    down_until = time.time() + seconds
    log("down", seconds=seconds)
    return {"unavailable_for_s": seconds}


@app.post("/admin/reset", response_model=None)
async def reset() -> dict[str, bool] | JSONResponse:
    """Forget everything; refused while any operation request is running or waiting for its key."""
    global down_until
    if in_progress:
        return JSONResponse({"error": "operations are active; retry reset after they finish"}, status_code=409)

    if STATE_FILE and Path(STATE_FILE).exists():
        Path(STATE_FILE).write_text("", encoding="utf-8")
    for memory in (results, effects, attempts, locks):
        memory.clear()
    down_until = 0.0

    log("reset")
    return {"reset": True}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "sim": NAME,
        "route": ROUTE,
        "keys": len(results),
        "total_effects": sum(len(ids) for ids in effects.values()),
    }
