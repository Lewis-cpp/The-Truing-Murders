"""Authentication, Origin and request-header checks shared by the routes."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request

from backend.application.errors import ApiProblem
from backend.application.sessions import Command, GameService

COOKIE_NAME = "visitor_token"


def service(request: Request) -> GameService:
    return request.app.state.service


def require_origin(request: Request) -> None:
    if request.headers.get("origin") not in request.app.state.settings.allowed_origins:
        raise ApiProblem("ORIGIN_NOT_ALLOWED", "请求来源不被允许。")


def visitor_id(request: Request, game: Annotated[GameService, Depends(service)]) -> UUID:
    return game.authenticate(request.cookies.get(COOKIE_NAME))


def idempotency_key(key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> UUID:
    if key is None:
        raise ApiProblem("IDEMPOTENCY_KEY_REQUIRED", "缺少 Idempotency-Key 请求头。")
    try:
        return UUID(key)
    except ValueError as error:
        raise ApiProblem("INVALID_IDEMPOTENCY_KEY", "Idempotency-Key 必须是 UUID。") from error


def expected_version(
    value: Annotated[str | None, Header(alias="X-Expected-State-Version")] = None,
) -> int | None:
    if value is None:
        return None
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise ApiProblem("INVALID_STATE_VERSION_HEADER", "版本头必须是正整数。")
    return int(value)


def command_factory(
    request: Request,
    key: Annotated[UUID, Depends(idempotency_key)],
    version: Annotated[int | None, Depends(expected_version)],
):
    def build(payload: dict | None = None) -> Command:
        return Command(key, request.method, request.url.path, payload or {}, version)

    return build


Visitor = Annotated[UUID, Depends(visitor_id)]
Game = Annotated[GameService, Depends(service)]
Origin = Depends(require_origin)
