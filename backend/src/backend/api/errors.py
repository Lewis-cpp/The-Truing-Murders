"""Uniform {"error": ApiError} responses for every 4xx/5xx, with no internals."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException

from backend.application.catalog import CaseIntegrityError
from backend.application.errors import ApiProblem
from backend.infrastructure.database.repositories.session_repository import SaveIntegrityError

logger = logging.getLogger(__name__)

FIELD_MESSAGES = {
    "missing": "缺少必填字段。",
    "extra_forbidden": "不支持该字段。",
    "string_too_long": "内容过长。",
    "string_too_short": "内容不能为空。",
    "string_pattern_mismatch": "格式不正确。",
}


def error_response(request: Request, problem: ApiProblem, headers: dict | None = None):
    body = {"error": {**problem.to_dict(), "trace_id": getattr(request.state, "trace_id", None)}}
    return JSONResponse(body, status_code=problem.status, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def api_problem(request: Request, problem: ApiProblem):
        return error_response(request, problem)

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, error: RequestValidationError):
        errors = error.errors()
        if any(e["type"] == "json_invalid" for e in errors):
            return error_response(request, ApiProblem("MALFORMED_JSON", "请求不是合法的 JSON。"))
        fields = [
            {
                "path": ".".join(str(part) for part in e["loc"]),
                "code": e["type"].upper(),
                "message": FIELD_MESSAGES.get(e["type"], "字段值无效。"),
            }
            for e in errors
        ]
        problem = ApiProblem("VALIDATION_ERROR", "请求字段无效。", {"fields": fields})
        return error_response(request, problem)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        if error.status_code == 405:
            problem = ApiProblem("METHOD_NOT_ALLOWED", "不支持该请求方法。")
            return error_response(request, problem, error.headers)
        return error_response(request, ApiProblem("ROUTE_NOT_FOUND", "接口不存在。"))

    # Connection and timeout failures only; constraint violations are bugs and stay 500.
    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def persistence(request: Request, error: OperationalError):
        logger.warning("Database unavailable: %s", type(error.orig).__name__)
        problem = ApiProblem(
            "PERSISTENCE_UNAVAILABLE",
            "存档服务暂不可用，本次操作未确认保存。请稍后用原操作重试。",
            retryable=True,
        )
        return error_response(request, problem)

    @app.exception_handler(CaseIntegrityError)
    async def case_integrity(request: Request, error: CaseIntegrityError):
        return error_response(request, ApiProblem("CASE_CONFIGURATION_ERROR", "案件配置不可用。"))

    @app.exception_handler(SaveIntegrityError)
    async def save_integrity(request: Request, error: SaveIntegrityError):
        return error_response(request, ApiProblem("SAVE_INTEGRITY_ERROR", "存档记录不一致。"))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception):
        logger.exception("Unhandled error", exc_info=error)
        return error_response(request, ApiProblem("INTERNAL_ERROR", "服务器内部错误。"))
