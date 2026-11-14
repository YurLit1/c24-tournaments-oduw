import asyncio
import hashlib
import json
from typing import Any

import psycopg
from fastapi.responses import JSONResponse
from psycopg import AsyncConnection, errors
from psycopg.types.json import Json

from . import db
from .jsonlog import log
from .problems import MEDIA_TYPE, Problem

TTL_HOURS = 24
WAIT_MS = 500
CLEANUP_BATCH = 500
CLEANUP_PERIOD_S = 30


def check_key(key: str | None) -> str:
    if key is None:
        raise Problem(400, "idempotency-key-required", "Idempotency-Key header is required")
    if not 8 <= len(key) <= 128:
        raise Problem(400, "idempotency-key-invalid", "Idempotency-Key must be 8 to 128 characters long")
    return key


def fingerprint(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def claim(conn: AsyncConnection, user_id: str, operation: str, key: str,
                request_hash: str) -> dict[str, Any] | None:
    await conn.execute(f"SET LOCAL lock_timeout = '{WAIT_MS}ms'")
    try:
        cur = await conn.execute(
            "INSERT INTO idempotency_key (user_id, operation, key, request_hash, state, expires_at) "
            "VALUES (%s, %s, %s, %s, 'processing', now() + make_interval(hours => %s)) "
            "ON CONFLICT (user_id, operation, key) DO UPDATE SET "
            "request_hash = EXCLUDED.request_hash, state = 'processing', status_code = NULL, "
            "location = NULL, response = NULL, created_at = now(), expires_at = EXCLUDED.expires_at "
            "WHERE idempotency_key.expires_at <= now() "
            "RETURNING key", (user_id, operation, key, request_hash, TTL_HOURS))
        mine = await cur.fetchone()
    except errors.LockNotAvailable:
        raise Problem(409, "request-in-progress", "Request in progress",
                      "A request with this Idempotency-Key is still being processed",
                      headers={"Retry-After": "1"})
    await conn.execute("SET LOCAL lock_timeout = 0")
    if mine is not None:
        return None
    cur = await conn.execute(
        "SELECT request_hash, status_code, location, response FROM idempotency_key "
        "WHERE user_id = %s AND operation = %s AND key = %s", (user_id, operation, key))
    saved = await cur.fetchone()
    if saved["request_hash"] != request_hash:
        raise Problem(422, "idempotency-key-reused", "Idempotency-Key reused",
                      "This Idempotency-Key was used with a different request body")
    return saved


async def finish(conn: AsyncConnection, user_id: str, operation: str, key: str,
                 status_code: int, location: str | None, response: Any) -> None:
    await conn.execute(
        "UPDATE idempotency_key SET state = 'done', status_code = %s, location = %s, response = %s "
        "WHERE user_id = %s AND operation = %s AND key = %s",
        (status_code, location, Json(response), user_id, operation, key))


def reply(status_code: int, location: str | None, response: Any, replayed: bool) -> JSONResponse:
    headers = {}
    if location:
        headers["Location"] = location
    if replayed:
        headers["Idempotent-Replayed"] = "true"
    media_type = MEDIA_TYPE if status_code >= 400 else "application/json"
    return JSONResponse(response, status_code=status_code, headers=headers, media_type=media_type)


async def cleanup() -> int:
    total = 0
    while True:
        async with db.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM idempotency_key WHERE (user_id, operation, key) IN ("
                "SELECT user_id, operation, key FROM idempotency_key WHERE expires_at <= now() "
                "ORDER BY expires_at LIMIT %s FOR UPDATE SKIP LOCKED)", (CLEANUP_BATCH,))
            deleted = cur.rowcount
        total += deleted
        if deleted < CLEANUP_BATCH:
            return total


async def cleanup_loop() -> None:
    while True:
        try:
            deleted = await cleanup()
            if deleted:
                log("idempotency.cleanup", deleted=deleted)
        except (psycopg.Error, OSError) as exc:
            log("idempotency.cleanup_failed", error=type(exc).__name__)
        await asyncio.sleep(CLEANUP_PERIOD_S)
