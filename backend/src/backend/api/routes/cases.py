from fastapi import APIRouter

from backend.api.dependencies import Game
from backend.api.schemas.responses import CaseList

router = APIRouter(prefix="/api/v1", tags=["cases"])


@router.get("/cases", response_model=CaseList)
def list_cases(game: Game) -> dict:
    return game.list_cases()
