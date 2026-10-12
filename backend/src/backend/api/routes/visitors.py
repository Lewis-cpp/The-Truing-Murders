from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.api.dependencies import COOKIE_NAME, Game, Origin
from backend.api.schemas.requests import EmptyRequest
from backend.api.schemas.responses import VisitorView

router = APIRouter(prefix="/api/v1", tags=["visitors"])


@router.post(
    "/visitors",
    response_model=VisitorView,
    status_code=201,
    dependencies=[Origin],
    responses={200: {"model": VisitorView, "description": "已有凭据，复用访问者"}},
)
def ensure_visitor(request: Request, game: Game, _body: EmptyRequest) -> JSONResponse:
    access = game.ensure_visitor(request.cookies.get(COOKIE_NAME))
    view = VisitorView(current_session_id=access.current_session_id).model_dump(mode="json")
    response = JSONResponse(view, status_code=200 if access.new_token is None else 201)
    if access.new_token is not None:
        response.set_cookie(
            COOKIE_NAME,
            access.new_token,
            httponly=True,
            secure=request.app.state.settings.cookie_secure,
            samesite="lax",
            path="/",
            max_age=60 * 60 * 24 * 365,
        )
    return response
