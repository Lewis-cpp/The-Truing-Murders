"""Player-visible response models. They restate the allowlist so nothing else can leak."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Phase = Literal[
    "INVESTIGATION", "INTERROGATION", "DEEP_INVESTIGATION", "ACCUSATION", "REVIEW", "FINISHED"
]
Credibility = Literal["UNVERIFIED", "VERIFIED", "DISPUTED", "REFUTED"]


class ApiError(BaseModel):
    code: str
    message: str
    details: dict
    retryable: bool
    trace_id: str | None = None


class ErrorResponse(BaseModel):
    error: ApiError


class VisitorView(BaseModel):
    current_session_id: UUID | None


class CaseSummary(BaseModel):
    case_id: str
    case_version: str
    title: str
    synopsis: str


class CaseList(BaseModel):
    items: list[CaseSummary]


class SessionSummary(BaseModel):
    session_id: UUID
    case_id: str
    case_version: str
    title: str
    phase: Phase
    state_version: int
    active_npc_id: str | None
    is_current: bool
    created_at: datetime
    saved_at: datetime
    closed_at: datetime | None
    finished_at: datetime | None
    available_actions: list[str]


class InvestigationOption(BaseModel):
    action_id: str
    label: str
    completed: bool
    enabled: bool
    disabled_reason: str | None


class SceneView(BaseModel):
    scene_id: str
    name: str
    description: str
    visited: bool
    actions: list[InvestigationOption]


class PublicSource(BaseModel):
    kind: Literal["SCENE", "NPC", "EVIDENCE", "PUBLIC"]
    id: str | None
    label: str


class EvidenceView(BaseModel):
    evidence_id: str
    name: str
    content: str
    source: PublicSource
    credibility: Credibility
    discovered_at: datetime


class InformationRef(BaseModel):
    kind: Literal["KNOWLEDGE"]
    id: str


class KnownInformation(BaseModel):
    information_ref: InformationRef
    content: str
    assertion_kind: Literal["FACT", "TESTIMONY"]
    source: PublicSource
    credibility: Credibility
    discovered_at: datetime | None


class NpcView(BaseModel):
    npc_id: str
    name: str
    public_identity: str
    is_contactable: bool
    is_active: bool
    emotion: Literal["CALM", "DEFENSIVE", "NERVOUS", "PRESSURED"]
    admission_progress: Literal["NONE", "PARTIAL_CONFESSION", "CONFESSION"]
    display_state: str
    fixed_statement: str | None
    presented_evidence_ids: list[str]


class Option(BaseModel):
    id: str
    label: str


class ProcessConstraints(BaseModel):
    min_steps: int
    max_steps: int
    allow_repeated_steps: bool


class AccusationOptions(BaseModel):
    suspects: list[Option]
    weapons: list[Option]
    motives: list[Option]
    process_steps: list[Option]
    process_constraints: ProcessConstraints


class SessionView(BaseModel):
    session: SessionSummary
    intro_text: str
    scenes: list[SceneView]
    evidence: list[EvidenceView]
    npcs: list[NpcView]
    known_information: list[KnownInformation]
    accusation_options: AccusationOptions


class CurrentSessionView(BaseModel):
    current_session_id: UUID | None
    session: SessionView | None


class PlayerOutcome(BaseModel):
    reason_code: str
    summary: str
    new_evidence: list[EvidenceView]
    disclosed_information: list[KnownInformation]
    npc: NpcView | None


class InvestigationResult(BaseModel):
    scene_id: str
    action_id: str
    outcome: PlayerOutcome


class ChatResult(BaseModel):
    npc_id: str
    fixed_reply: str


class PresentationResult(BaseModel):
    npc_id: str
    evidence_id: str
    fixed_reply: str
    outcome: PlayerOutcome


class StepEvidenceLink(BaseModel):
    step_id: str
    evidence_id: str


class AccusationContent(BaseModel):
    suspect_character_id: str
    weapon_option_id: str
    motive_option_id: str
    ordered_process_step_ids: list[str]
    cited_evidence_ids: list[str]
    step_evidence_links: list[StepEvidenceLink]
    explanation: str


class CriterionResult(BaseModel):
    criterion_id: str
    label: str
    matched: bool
    score: str
    max_score: str
    explanation: str


class Verdict(BaseModel):
    category: Literal["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"]
    score: str
    max_score: str
    criteria: list[CriterionResult]


class AccusationView(BaseModel):
    content: AccusationContent
    submitted_at: datetime
    submitted_state_version: int
    case_version: str
    rules_version: str
    verdict: Verdict


class TruthReview(BaseModel):
    suspect_character_id: str
    weapon_option_id: str
    motive_option_id: str
    ordered_process_step_ids: list[str]
    labels: dict[str, str]
    explanation: str


class ReviewEvidence(BaseModel):
    evidence_id: str
    name: str
    content: str
    source: PublicSource
    was_discovered: bool


class ReviewView(BaseModel):
    accusation: AccusationView
    truth: TruthReview
    evidence_chain: list[ReviewEvidence]
    missed_evidence: list[ReviewEvidence]
    fixed_review: str


class View[T](BaseModel):
    session_id: UUID
    state_version: int
    data: T


class ActionResult[T](BaseModel):
    request_id: UUID
    session_id: UUID
    business_status: Literal["COMMITTED", "NOOP"]
    state_changed: bool
    state_version_before: int
    result_state_version: int
    phase_after: Phase
    active_npc_id_after: str | None
    saved_at: datetime
    data: T
    conversation: None = None


class RequestRecord(BaseModel):
    request_id: UUID
    status: Literal["COMMITTED", "NOOP", "REJECTED"]
    original_http_status: int
    result: dict | None
    error: ApiError | None
