"""Write request bodies. Unknown fields are rejected, including any attempt to patch state."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

LocalId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
CaseVersion = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{1,32}$")]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyRequest(Request):
    pass


class CreateSessionRequest(Request):
    case_id: LocalId
    case_version: CaseVersion
    replaces_session_id: Annotated[UUID | None, Field(strict=False)] = None
    confirm_restart: bool = False


class InvestigateRequest(Request):
    action_id: LocalId


class SetInterrogationRequest(Request):
    npc_id: LocalId


class ChatRequest(Request):
    message: Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=r"\S")]


class PresentEvidenceRequest(Request):
    evidence_id: LocalId
    comment: Annotated[str, Field(max_length=1000)] = ""


class StepEvidenceLink(Request):
    step_id: LocalId
    evidence_id: LocalId


class AccusationContent(Request):
    suspect_character_id: LocalId
    weapon_option_id: LocalId
    motive_option_id: LocalId
    ordered_process_step_ids: Annotated[list[LocalId], Field(min_length=1, max_length=50)]
    cited_evidence_ids: Annotated[list[LocalId], Field(max_length=50)]
    step_evidence_links: Annotated[list[StepEvidenceLink], Field(max_length=100)]
    explanation: Annotated[str, Field(max_length=4000)] = ""


class SubmitAccusationRequest(Request):
    content: AccusationContent
    confirm: bool = False
