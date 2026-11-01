"""Player-visible response models. They restate the allowlist so nothing else can leak."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Phase = Literal[
    "INVESTIGATION", "INTERROGATION", "DEEP_INVESTIGATION", "ACCUSATION", "REVIEW", "FINISHED"
]
Credibility = Literal["UNVERIFIED", "VERIFIED", "DISPUTED", "REFUTED"]
EvidenceKind = Literal["PHYSICAL", "DOCUMENT", "TESTIMONY", "DIGITAL"]


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
    # Whether the session budget still allows a model call; the page hints at fixed
    # replies when this turns false.
    generation_available: bool = True


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


class SceneList(BaseModel):
    items: list[SceneView]


class PublicSource(BaseModel):
    kind: Literal["SCENE", "NPC", "EVIDENCE", "PUBLIC"]
    id: str | None
    label: str


class InformationRef(BaseModel):
    kind: Literal["EVIDENCE", "KNOWLEDGE", "RELATIONSHIP", "TIMELINE_EVENT"]
    id: str


class EvidenceView(BaseModel):
    evidence_id: str
    name: str
    kind: EvidenceKind
    content: str
    source: PublicSource
    credibility: Credibility
    discovered_at: datetime | None
    key_badge: bool
    known_conflicts: list[InformationRef]
    links: list[dict]


class EvidenceList(BaseModel):
    items: list[EvidenceView]


class KnownInformation(BaseModel):
    information_ref: InformationRef
    content: str
    assertion_kind: Literal["FACT", "TESTIMONY"]
    source: PublicSource
    credibility: Credibility
    discovered_at: datetime | None
    known_conflicts: list[InformationRef]


class TopicView(BaseModel):
    topic_id: str
    label: str
    asked: bool


class NpcView(BaseModel):
    npc_id: str
    name: str
    public_identity: str
    is_contactable: bool
    is_active: bool
    is_evading: bool
    emotion: Literal["CALM", "DEFENSIVE", "NERVOUS", "PRESSURED"]
    admission_progress: Literal["NONE", "PARTIAL_CONFESSION", "CONFESSION"]
    display_state: str
    fixed_statement: str | None
    presented_evidence_ids: list[str]
    known_statements: list[KnownInformation]
    topics: list[TopicView]


class NpcList(BaseModel):
    items: list[NpcView]


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


class RelationshipNode(BaseModel):
    character_id: str
    name: str
    role: str
    public_identity: str


class RelationshipEdge(BaseModel):
    relationship_id: str
    from_character_id: str
    to_character_id: str
    relationship_type: str
    directed: bool
    description: str
    assertion_kind: Literal["FACT", "TESTIMONY"]
    source: PublicSource
    credibility: Credibility
    discovered_at: datetime | None
    known_conflicts: list[InformationRef]


class RelationshipGraph(BaseModel):
    nodes: list[RelationshipNode]
    edges: list[RelationshipEdge]


class TimelineItem(BaseModel):
    timeline_event_id: str
    title: str
    description: str
    scene_id: str | None
    participant_ids: list[str]
    time_precision: Literal["EXACT", "RANGE", "UNKNOWN"]
    time_start_minutes: int | None
    time_end_minutes: int | None
    time_label: str
    assertion_kind: Literal["FACT", "TESTIMONY"]
    source: PublicSource
    credibility: Credibility
    discovered_at: datetime | None
    known_conflicts: list[InformationRef]


class TimelineView(BaseModel):
    origin_label: str
    items: list[TimelineItem]


class StepEvidenceLink(BaseModel):
    step_id: str
    evidence_id: str


class AccusationContent(BaseModel):
    suspect_character_id: str | None
    weapon_option_id: str | None
    motive_option_id: str | None
    ordered_process_step_ids: list[str]
    cited_evidence_ids: list[str]
    step_evidence_links: list[StepEvidenceLink]
    explanation: str


class DraftResult(BaseModel):
    content: AccusationContent


class SessionView(BaseModel):
    session: SessionSummary
    intro_text: str
    scenes: list[SceneView]
    evidence: list[EvidenceView]
    npcs: list[NpcView]
    known_information: list[KnownInformation]
    relationships: RelationshipGraph
    timeline: TimelineView
    accusation_options: AccusationOptions
    accusation_draft: AccusationContent
    pending_conversations: list[dict]


class CurrentSessionView(BaseModel):
    current_session_id: UUID | None
    session: SessionView | None


class PlayerOutcome(BaseModel):
    reason_code: str
    summary: str
    new_evidence: list[EvidenceView]
    updated_evidence: list[EvidenceView]
    disclosed_information: list[KnownInformation]
    unlocked_scenes: list[SceneView]
    relationships_changed: bool
    timeline_changed: bool
    npc: NpcView | None


class InvestigationResult(BaseModel):
    scene_id: str
    action_id: str
    outcome: PlayerOutcome


class ChatResult(BaseModel):
    """The chat receipt per spec 5.2: only the new round's identity."""

    conversation_id: str


class QuestionResult(BaseModel):
    npc_id: str
    topic_id: str
    fixed_reply: str
    outcome: PlayerOutcome


class PresentationResult(BaseModel):
    npc_id: str
    evidence_id: str
    fixed_reply: str
    outcome: PlayerOutcome


class ContradictionResult(BaseModel):
    npc_id: str
    knowledge_id: str
    evidence_id: str
    fixed_reply: str
    outcome: PlayerOutcome


class MessageView(BaseModel):
    message_id: str
    sequence_no: int
    speaker: Literal["PLAYER", "NPC", "HOST", "REVIEW"]
    content: str
    origin: Literal["PLAYER", "LLM", "FIXED"]
    validity: Literal["VALID", "STALE"]
    created_at: datetime
    updated_at: datetime


class ConversationView(BaseModel):
    conversation_id: str
    conversation_seq: int
    session_id: UUID
    npc_id: str | None
    request_id: str
    interaction_type: Literal["CHAT", "EVIDENCE_PRESENTATION"]
    source_state_version: int
    generation_status: str
    generation_deadline_at: datetime | None
    deadline_exceeded: bool
    fixed_reply: str
    messages: list[MessageView]
    fallback_reason: str | None
    can_retry_reply: bool
    created_at: datetime
    completed_at: datetime | None


class ConversationPage(BaseModel):
    items: list[ConversationView]
    next_before_seq: int | None


class CriterionResult(BaseModel):
    criterion_id: str
    label: str
    matched: bool
    score: str
    max_score: str
    explanation: str
    missing_evidence_ids: list[str]


class Verdict(BaseModel):
    category: Literal["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"]
    score: str
    max_score: str
    fixed_explanation: str
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
    conversation: ConversationView | None = None


class RequestRecord(BaseModel):
    request_id: UUID
    status: Literal["COMMITTED", "NOOP", "REJECTED"]
    original_http_status: int
    result: dict | None
    error: ApiError | None
