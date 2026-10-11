from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from backend.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    engine = create_engine(
        str(settings.database_url), pool_pre_ping=True, connect_args={"connect_timeout": 3}
    )
    app.state.engine = engine
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="The Truing Murders", version="0.1.0", lifespan=lifespan)


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
