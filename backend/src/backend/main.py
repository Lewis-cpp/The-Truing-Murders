import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from backend.api.errors import error_response, install_error_handlers
from backend.api.routes import cases, sessions, visitors
from backend.application.errors import ApiProblem
from backend.application.generation import (
    GenerationConfig,
    GenerationRuntime,
    ThreadDispatcher,
)
from backend.application.sessions import GameService
from backend.config import Settings
from backend.infrastructure.llm_client import LLMGateway

MAX_BODY_BYTES = 64 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A nested client re-enters this lifespan while the outer one is still running;
    # that re-entry keeps the running gateway, dispatcher and any test replacements.
    # Sequential starts (a new client after the previous one closed) initialize again.
    depth = getattr(app.state, "_lifespan_depth", 0)
    app.state._lifespan_depth = depth + 1
    try:
        if depth > 0:
            yield
            return
        settings = Settings()
        engine = create_engine(
            str(settings.database_url), pool_pre_ping=True, connect_args={"connect_timeout": 3}
        )
        app.state.settings = settings
        app.state.engine = engine
        # Injection points (spec 6.1): the gateway exists only when generation is enabled;
        # both live on app.state and are read per request, so tests may replace them.
        app.state.llm_gateway = LLMGateway(settings) if settings.llm_enabled else None
        app.state.llm_config = GenerationConfig.from_settings(settings)
        dispatcher = ThreadDispatcher(max_workers=settings.llm_concurrency)
        app.state.generation_dispatcher = dispatcher
        # Case import is an explicit offline step; startup never writes definitions.
        app.state.service = GameService(
            sessionmaker(engine, expire_on_commit=False),
            generation=lambda: GenerationRuntime(
                app.state.llm_config, app.state.llm_gateway, app.state.generation_dispatcher
            ),
        )
        try:
            yield
        finally:
            dispatcher.shutdown()
            engine.dispose()
    finally:
        app.state._lifespan_depth = depth


app = FastAPI(title="The Truing Murders", version="0.2.0", lifespan=lifespan)
install_error_handlers(app)
app.include_router(visitors.router)
app.include_router(cases.router)
app.include_router(sessions.router)


@app.middleware("http")
async def protocol_guard(request: Request, call_next):
    request.state.trace_id = str(uuid.uuid4())
    # shortcut: chunked bodies carry no Content-Length and skip both checks; fine while the
    # server binds 127.0.0.1, enforce the limit on the read body before any public deployment.
    length = request.headers.get("content-length")
    problem = None
    if length and length.isdecimal() and int(length) > MAX_BODY_BYTES:
        problem = ApiProblem("PAYLOAD_TOO_LARGE", "请求体超过 64 KiB。")
    elif (
        request.method in {"POST", "PUT", "PATCH"}
        and length not in (None, "0")
        and request.headers.get("content-type", "").split(";")[0].strip() != "application/json"
    ):
        problem = ApiProblem("UNSUPPORTED_MEDIA_TYPE", "请求体必须是 application/json。")
    response = error_response(request, problem) if problem else await call_next(request)
    response.headers["X-Trace-ID"] = request.state.trace_id
    # Saves and verdicts are private to one visitor; never let a shared cache keep them.
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/ready")
def ready(request: Request) -> JSONResponse:
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            {"status": "unavailable", "database": "unavailable"},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse({"status": "ok", "database": "ok"}, headers={"Cache-Control": "no-store"})
