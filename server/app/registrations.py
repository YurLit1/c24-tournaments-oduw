import json
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg import AsyncConnection, errors
from pydantic import BaseModel, Field

from . import db, idempotency
from .problems import Problem

HOLD_MINUTES = 15
OPERATION = "create-registration"

REG_COLUMNS = "id, tournament_id, nickname, status, version, created_at, expires_at"

router = APIRouter()


class RegistrationCreate(BaseModel):
    tournament_id: str = Field(min_length=1, max_length=64)
    nickname: str = Field(min_length=3, max_length=32)


@router.get("/v1/tournaments")
async def list_tournaments() -> JSONResponse:
    async with db.connection() as conn:
        cur = await conn.execute(
            "SELECT id, game, starts_at, time_zone, slots, available, fee_minor, currency, registration_open "
            "FROM tournament ORDER BY starts_at, id")
        rows = await cur.fetchall()
    return JSONResponse(jsonable_encoder({"items": rows}))


async def register(conn: AsyncConnection, user_id: str, body: RegistrationCreate) -> dict[str, Any]:
    cur = await conn.execute(
        "UPDATE tournament SET available = available - 1 "
        "WHERE id = %s AND registration_open AND available > 0 AND starts_at > now() "
        "RETURNING id", (body.tournament_id,))
    if await cur.fetchone() is None:
        cur = await conn.execute("SELECT 1 FROM tournament WHERE id = %s", (body.tournament_id,))
        if await cur.fetchone() is None:
            raise Problem(404, "tournament-not-found", "Tournament not found",
                          f"No tournament {body.tournament_id}")
        raise Problem(409, "no-free-slots", "No free slots",
                      "Registration is closed or all slots are taken")
    try:
        cur = await conn.execute(
            "INSERT INTO registration (user_id, tournament_id, nickname, status, expires_at) "
            "VALUES (%s, %s, %s, 'held', now() + make_interval(mins => %s)) "
            f"RETURNING {REG_COLUMNS}",
            (user_id, body.tournament_id, body.nickname, HOLD_MINUTES))
        return await cur.fetchone()
    except errors.UniqueViolation:
        raise Problem(409, "already-registered", "Already registered",
                      "Active registration of this player or this nickname already exists")
    except errors.CheckViolation:
        raise Problem(422, "invalid-request", "Invalid request data",
                      "Registration violates a data constraint")


@router.post("/v1/registrations", status_code=201)
async def create_registration(request: Request, body: RegistrationCreate,
                              x_user_id: str = Header(),
                              idempotency_key: str | None = Header(default=None)) -> JSONResponse:
    key = idempotency.check_key(idempotency_key)
    request_hash = idempotency.fingerprint(body.model_dump())
    async with db.connection() as conn:
        async with conn.transaction():
            try:
                saved = await idempotency.claim(conn, x_user_id, OPERATION, key, request_hash)
            except errors.ForeignKeyViolation:
                raise Problem(422, "unknown-user", "Unknown user", "X-User-Id does not match an existing user")
            if saved is not None:
                return idempotency.reply(saved["status_code"], saved["location"], saved["response"], True)
            try:
                async with conn.transaction():
                    reg = await register(conn, x_user_id, body)
                status_code, location, response = 201, f"/v1/registrations/{reg['id']}", jsonable_encoder(reg)
            except Problem as problem:
                status_code, location = problem.status, None
                response = json.loads(problem.response(request.url.path).body)
            await idempotency.finish(conn, x_user_id, OPERATION, key, status_code, location, response)
    return idempotency.reply(status_code, location, response, False)


@router.get("/v1/registrations/{registration_id}")
async def get_registration(registration_id: str, x_user_id: str = Header()) -> JSONResponse:
    async with db.connection() as conn:
        cur = await conn.execute(
            f"SELECT {REG_COLUMNS} FROM registration WHERE id = %s AND user_id = %s",
            (registration_id, x_user_id))
        reg = await cur.fetchone()
    if reg is None:
        raise Problem(404, "registration-not-found", "Registration not found",
                      f"No registration {registration_id}")
    return JSONResponse(jsonable_encoder(reg))
