import hashlib
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db
from .problems import Problem

TOKEN_TTL_HOURS = 8

router = APIRouter()


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _unauthorized(detail: str) -> Problem:
    return Problem(401, "unauthorized", "Unauthorized", detail, headers={"WWW-Authenticate": "Bearer"})


def _token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("Authorization: Bearer <token> is required")
    return token.strip()


async def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = _token(authorization)
    async with db.connection() as conn:
        cur = await conn.execute(
            "SELECT u.id, u.name, u.role FROM session s JOIN app_user u ON u.id = s.user_id "
            "WHERE s.token_hash = %s AND s.expires_at > now()", (_hash(token),))
        user = await cur.fetchone()
    if user is None:
        raise _unauthorized("Token is unknown or expired")
    return user


async def staff(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "staff":
        raise Problem(403, "forbidden", "Forbidden", "This action requires the staff role")
    return user


@router.post("/v1/auth/login")
async def login(body: LoginIn) -> JSONResponse:
    token = secrets.token_urlsafe(32)
    async with db.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT id FROM app_user WHERE login = %s AND password_hash = crypt(%s, password_hash)",
                (body.login, body.password))
            user = await cur.fetchone()
            if user is None:
                raise _unauthorized("Wrong login or password")
            await conn.execute("DELETE FROM session WHERE user_id = %s AND expires_at <= now()", (user["id"],))
            cur = await conn.execute(
                "INSERT INTO session (token_hash, user_id, expires_at) "
                "VALUES (%s, %s, now() + make_interval(hours => %s)) RETURNING expires_at",
                (_hash(token), user["id"], TOKEN_TTL_HOURS))
            session = await cur.fetchone()
    return JSONResponse(jsonable_encoder(
        {"access_token": token, "token_type": "Bearer", "expires_at": session["expires_at"]}),
        headers={"Cache-Control": "no-store"})


@router.post("/v1/auth/logout", status_code=204)
async def logout(authorization: str | None = Header(default=None),
                 _: dict[str, Any] = Depends(current_user)) -> Response:
    async with db.connection() as conn:
        await conn.execute("DELETE FROM session WHERE token_hash = %s", (_hash(_token(authorization)),))
    return Response(status_code=204)


@router.get("/v1/me")
async def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user
