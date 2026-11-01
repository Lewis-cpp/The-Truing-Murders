"""Session resources. Writes carry Idempotency-Key and expected versions; GETs never write."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.api.dependencies import Game, Origin, Visitor, command_factory
from backend.api.schemas import requests as rq
from backend.api.schemas import responses as rs
from backend.application.errors import ApiProblem
from backend.application.sessions import Command, CommandResponse

router = APIRouter(prefix="/api/v1", tags=["sessions"])
Commands = Annotated[Callable[..., Command], Depends(command_factory)]
WRITE = {"dependencies": [Origin], "responses": {"default": {"model": rs.ErrorResponse}}}


def respond(result: CommandResponse, model: type[BaseModel]) -> JSONResponse:
    """Re-validate even replayed results through the response allowlist."""
    if "error" in result.body:
        error = result.body["error"]
        raise ApiProblem(error["code"], error["message"], error["details"], error["retryable"])
    body = model.model_validate(result.body).model_dump(mode="json")
    headers = {"Location": result.location} if result.location else None
    return JSONResponse(body, status_code=result.status_code, headers=headers)


@router.post("/sessions", response_model=rs.ActionResult[rs.SessionView], status_code=201, **WRITE)
def create_session(
    body: rq.CreateSessionRequest, visitor: Visitor, game: Game, commands: Commands
) -> JSONResponse:
    command = commands(body.model_dump(mode="json"))
    result = game.create_session(
        visitor,
        command,
        body.case_id,
        body.case_version,
        body.replaces_session_id,
        body.confirm_restart,
    )
    return respond(result, rs.ActionResult[rs.SessionView])


@router.get("/sessions/current", response_model=rs.CurrentSessionView)
def current_session(visitor: Visitor, game: Game) -> dict:
    return game.current_session(visitor)


@router.get("/sessions/{session_id}", response_model=rs.SessionView)
def load_session(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.session_view(visitor, session_id)


@router.get("/requests/{request_id}", response_model=rs.RequestRecord)
def request_record(request_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.request_record(visitor, request_id)


# Read-only game resources; every GET is a projection and never writes.


@router.get("/sessions/{session_id}/scenes", response_model=rs.View[rs.SceneList])
def list_scenes(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.scene_views(visitor, session_id)


@router.get("/sessions/{session_id}/scenes/{scene_id}", response_model=rs.View[rs.SceneView])
def scene_detail(session_id: UUID, scene_id: str, visitor: Visitor, game: Game) -> dict:
    return game.scene_detail(visitor, session_id, scene_id)


@router.get("/sessions/{session_id}/evidence", response_model=rs.View[rs.EvidenceList])
def list_evidence(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.evidence_views(visitor, session_id)


@router.get(
    "/sessions/{session_id}/evidence/{evidence_id}", response_model=rs.View[rs.EvidenceView]
)
def evidence_detail(session_id: UUID, evidence_id: str, visitor: Visitor, game: Game) -> dict:
    return game.evidence_detail(visitor, session_id, evidence_id)


@router.get("/sessions/{session_id}/npcs", response_model=rs.View[rs.NpcList])
def list_npcs(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.npc_views(visitor, session_id)


@router.get("/sessions/{session_id}/npcs/{npc_id}", response_model=rs.View[rs.NpcView])
def npc_detail(session_id: UUID, npc_id: str, visitor: Visitor, game: Game) -> dict:
    return game.npc_detail(visitor, session_id, npc_id)


@router.get("/sessions/{session_id}/relationships", response_model=rs.View[rs.RelationshipGraph])
def relationships(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.relationship_graph(visitor, session_id)


@router.get("/sessions/{session_id}/timeline", response_model=rs.View[rs.TimelineView])
def timeline(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.timeline_view(visitor, session_id)


@router.get(
    "/sessions/{session_id}/accusation-options", response_model=rs.View[rs.AccusationOptions]
)
def accusation_options(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.accusation_options_view(visitor, session_id)


@router.get("/sessions/{session_id}/accusation-draft", response_model=rs.View[rs.DraftResult])
def get_accusation_draft(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.accusation_draft_view(visitor, session_id)


@router.get(
    "/sessions/{session_id}/npcs/{npc_id}/conversations",
    response_model=rs.View[rs.ConversationPage],
)
def conversation_history(
    session_id: UUID,
    npc_id: str,
    visitor: Visitor,
    game: Game,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
) -> dict:
    return game.conversation_page(visitor, session_id, npc_id, limit, before_seq)


@router.get(
    "/sessions/{session_id}/conversations/{conversation_id}",
    response_model=rs.View[rs.ConversationView],
)
def conversation_detail(
    session_id: UUID, conversation_id: UUID, visitor: Visitor, game: Game
) -> dict:
    return game.conversation_detail(visitor, session_id, conversation_id)


# Writes


@router.post(
    "/sessions/{session_id}/scenes/{scene_id}/investigations",
    response_model=rs.ActionResult[rs.InvestigationResult],
    status_code=201,
    **WRITE,
)
def investigate(
    session_id: UUID,
    scene_id: str,
    body: rq.InvestigateRequest,
    visitor: Visitor,
    game: Game,
    commands: Commands,
) -> JSONResponse:
    command = commands(body.model_dump(mode="json"))
    result = game.investigate(visitor, session_id, command, scene_id, body.action_id)
    return respond(result, rs.ActionResult[rs.InvestigationResult])


@router.put(
    "/sessions/{session_id}/interrogation",
    response_model=rs.ActionResult[rs.SessionSummary],
    status_code=201,
    **WRITE,
)
def set_interrogation(
    session_id: UUID,
    body: rq.SetInterrogationRequest,
    visitor: Visitor,
    game: Game,
    commands: Commands,
) -> JSONResponse:
    command = commands(body.model_dump(mode="json"))
    result = game.set_interrogation(visitor, session_id, command, body.npc_id)
    return respond(result, rs.ActionResult[rs.SessionSummary])


@router.delete(
    "/sessions/{session_id}/interrogation",
    response_model=rs.ActionResult[rs.SessionSummary],
    **WRITE,
)
def end_interrogation(
    session_id: UUID, visitor: Visitor, game: Game, commands: Commands
) -> JSONResponse:
    result = game.end_interrogation(visitor, session_id, commands())
    return respond(result, rs.ActionResult[rs.SessionSummary])


@router.post(
    "/sessions/{session_id}/npcs/{npc_id}/conversations",
    response_model=rs.ActionResult[rs.ChatResult],
    status_code=201,
    **WRITE,
)
def chat(
    session_id: UUID,
    npc_id: str,
    body: rq.ChatRequest,
    visitor: Visitor,
    game: Game,
    commands: Commands,
) -> JSONResponse:
    command = commands(body.model_dump(mode="json"))
    result = game.chat(visitor, session_id, command, npc_id, body.message)
    return respond(result, rs.ActionResult[rs.ChatResult])


@router.post(
    "/sessions/{session_id}/npcs/{npc_id}/questions",
    response_model=rs.ActionResult[rs.QuestionResult],
    status_code=201,
    **WRITE,
)
def ask_topic(
    session_id: UUID,
    npc_id: str,
    body: rq.AskTopicRequest,
    visitor: Visitor,
    game: Game,
    commands: Commands,
) -> JSONResponse:
    command = commands(body.model_dump(mode="json"))
    result = game.ask_topic(visitor, session_id, command, npc_id, body.topic_id)
    return respond(result, rs.ActionResult[rs.QuestionResult])


@router.post(
    "/sessions/{session_id}/npcs/{npc_id}/evidence-presentations",
    response_model=rs.ActionResult[rs.PresentationResult],
    status_code=201,
    **WRITE,
)
def present_evidence(
    session_id: UUID,
    npc_id: str,
    body: rq.PresentEvidenceRequest,
    visitor: Visitor,
    game: Game,
    commands: Commands,
) -> JSONResponse:
    command = commands(body.model_dump(mode="json"))
    result = game.present(
        visitor, session_id, command, npc_id, body.evidence_id, body.comment or None
    )
    return respond(result, rs.ActionResult[rs.PresentationResult])


@router.post(
    "/sessions/{session_id}/npcs/{npc_id}/contradictions",
    response_model=rs.ActionResult[rs.ContradictionResult],
    status_code=201,
    **WRITE,
)
def point_contradiction(
    session_id: UUID,
    npc_id: str,
    body: rq.PointContradictionRequest,
    visitor: Visitor,
    game: Game,
    commands: Commands,
) -> JSONResponse:
    command = commands(body.model_dump(mode="json"))
    result = game.point_contradiction(
        visitor, session_id, command, npc_id, body.knowledge_id, body.evidence_id
    )
    return respond(result, rs.ActionResult[rs.ContradictionResult])


@router.put(
    "/sessions/{session_id}/accusation-draft",
    response_model=rs.ActionResult[rs.DraftResult],
    **WRITE,
)
def save_accusation_draft(
    session_id: UUID,
    body: rq.SaveDraftRequest,
    visitor: Visitor,
    game: Game,
    commands: Commands,
) -> JSONResponse:
    command = commands(body.model_dump(mode="json"))
    result = game.save_draft(visitor, session_id, command, body.model_dump(mode="json")["content"])
    return respond(result, rs.ActionResult[rs.DraftResult])


@router.put(
    "/sessions/{session_id}/accusation-preparation",
    response_model=rs.ActionResult[rs.SessionSummary],
    status_code=201,
    **WRITE,
)
def open_accusation(
    session_id: UUID, body: rq.EmptyRequest, visitor: Visitor, game: Game, commands: Commands
) -> JSONResponse:
    result = game.open_accusation(visitor, session_id, commands(body.model_dump()))
    return respond(result, rs.ActionResult[rs.SessionSummary])


@router.delete(
    "/sessions/{session_id}/accusation-preparation",
    response_model=rs.ActionResult[rs.SessionSummary],
    **WRITE,
)
def cancel_accusation(
    session_id: UUID, visitor: Visitor, game: Game, commands: Commands
) -> JSONResponse:
    result = game.cancel_accusation(visitor, session_id, commands())
    return respond(result, rs.ActionResult[rs.SessionSummary])


@router.post(
    "/sessions/{session_id}/accusation",
    response_model=rs.ActionResult[rs.AccusationView],
    status_code=201,
    **WRITE,
)
def submit_accusation(
    session_id: UUID,
    body: rq.SubmitAccusationRequest,
    visitor: Visitor,
    game: Game,
    commands: Commands,
) -> JSONResponse:
    payload = body.model_dump(mode="json")
    result = game.submit_accusation(
        visitor, session_id, commands(payload), payload["content"], body.confirm
    )
    return respond(result, rs.ActionResult[rs.AccusationView])


@router.get("/sessions/{session_id}/accusation", response_model=rs.View[rs.AccusationView])
def get_accusation(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.closed_view(visitor, session_id, review=False)


@router.get("/sessions/{session_id}/review", response_model=rs.View[rs.ReviewView])
def get_review(session_id: UUID, visitor: Visitor, game: Game) -> dict:
    return game.closed_view(visitor, session_id, review=True)


@router.put(
    "/sessions/{session_id}/review-completion",
    response_model=rs.ActionResult[rs.SessionSummary],
    status_code=201,
    **WRITE,
)
def finish_review(
    session_id: UUID, body: rq.EmptyRequest, visitor: Visitor, game: Game, commands: Commands
) -> JSONResponse:
    result = game.finish_review(visitor, session_id, commands(body.model_dump()))
    return respond(result, rs.ActionResult[rs.SessionSummary])
