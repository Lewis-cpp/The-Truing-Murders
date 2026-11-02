"""The full-case contract (schema 3); fixed structures agreed with the v0.3 tests."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=4000)]
Level = Annotated[int, Field(ge=0, le=100)]
Delta = Annotated[int, Field(ge=-100, le=100)]


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Phase(StrEnum):
    INIT = "INIT"
    INTRO = "INTRO"
    INVESTIGATION = "INVESTIGATION"
    INTERROGATION = "INTERROGATION"
    DEEP_INVESTIGATION = "DEEP_INVESTIGATION"
    ACCUSATION = "ACCUSATION"
    JUDGEMENT = "JUDGEMENT"
    REVIEW = "REVIEW"
    FINISHED = "FINISHED"


class LieStage(StrEnum):
    UNBROKEN = "UNBROKEN"
    BROKEN = "BROKEN"
    ADMITTED = "ADMITTED"


class Dependency(Definition):
    all_of: tuple[Text, ...]
    any_of: tuple[Text, ...]

    def satisfied(self, held: frozenset[str]) -> bool:
        return set(self.all_of) <= held and (not self.any_of or bool(set(self.any_of) & held))


class Choice(Definition):
    id: Text
    label: Text


class Evidence(Definition):
    id: Text
    title: Text
    kind: Literal["PHYSICAL", "DOCUMENT", "TESTIMONY", "DIGITAL"]
    content: Text
    source: Text
    credibility: Literal["VERIFIED", "UNVERIFIED"]
    is_key: bool


class Investigation(Definition):
    id: Text
    label: Text
    evidence_id: Text
    requires: Dependency


class Scene(Definition):
    id: Text
    name: Text
    description: Text
    unlock: Dependency
    actions: tuple[Investigation, ...]


class Character(Definition):
    id: Text
    name: Text
    role: Text
    public_identity: Text
    personality: Text | None
    speech_style: Text | None
    interrogatable: bool
    initial_pressure: Level | None
    initial_trust: Level | None
    core_lie_ids: tuple[Text, ...]
    default_reply: Text | None


class Knowledge(Definition):
    id: Text
    content: Text
    known_by: tuple[Text, ...]
    # ADMITTED is disclosed by a lie admission; ASKED records an NPC's answer to a fixed topic.
    disclosure: Literal["PUBLIC", "ADMITTED", "ASKED"]


class PresentEffect(Definition):
    evidence_id: Text
    pressure: Delta
    trust: Delta


class Statements(Definition):
    unbroken: Text
    broken: Text
    admitted: Text


class Lie(Definition):
    id: Text
    npc_id: Text
    counterevidence: Dependency
    admission_presented: Dependency
    admission_pressure_min: Level | None
    admission_trust_min: Level | None
    statements: Statements
    admitted_knowledge_id: Text
    effects: tuple[PresentEffect, ...]


class LieChain(Definition):
    """Groups one NPC's layers; the order of lie_ids is the layer order."""

    id: Text
    npc_id: Text
    lie_ids: tuple[Text, ...]


class Topic(Definition):
    """A fixed question. Asking records the NPC's fixed answer as unverified testimony."""

    id: Text
    npc_id: Text
    label: Text
    reply: Text
    knowledge_id: Text


class Contradiction(Definition):
    """A preset pairing of an NPC's recorded testimony with the evidence that refutes it."""

    id: Text
    npc_id: Text
    knowledge_id: Text
    evidence_id: Text
    pressure: Annotated[int, Field(ge=0, le=100)]
    trust: Delta
    reply: Text
    explanation: Text


class Interrogation(Definition):
    """Costs of irrelevant moves, and the fixed topics and contradictions of the case."""

    irrelevant_trust: Annotated[int, Field(ge=-100, le=0)]
    evade_after: Annotated[int, Field(ge=1, le=10)]
    irrelevant_reply: Text
    evade_reply: Text
    topics: tuple[Topic, ...]
    contradictions: tuple[Contradiction, ...]


class Relationship(Definition):
    id: Text
    from_id: Text
    to_id: Text
    type: Text
    directed: bool
    description: Text
    assertion_kind: Literal["FACT", "TESTIMONY"]
    credibility: Literal["VERIFIED", "UNVERIFIED"]
    source_kind: Literal["PUBLIC", "EVIDENCE", "NPC"]
    source_id: Text | None
    reveal_evidence_ids: tuple[Text, ...]
    reveal_knowledge_ids: tuple[Text, ...]


class TimelineEvent(Definition):
    id: Text
    title: Text
    description: Text
    scene_id: Text | None
    participant_ids: tuple[Text, ...]
    precision: Literal["EXACT", "RANGE", "UNKNOWN"]
    start_minutes: int | None
    end_minutes: int | None
    time_label: Text
    assertion_kind: Literal["FACT", "TESTIMONY"]
    credibility: Literal["VERIFIED", "UNVERIFIED"]
    source_kind: Literal["PUBLIC", "EVIDENCE", "NPC"]
    source_id: Text | None
    reveal_evidence_ids: tuple[Text, ...]
    reveal_knowledge_ids: tuple[Text, ...]
    conflicts_with: tuple[Text, ...]


class Truth(Definition):
    culprit: Text
    weapon: Text
    motive: Text
    steps: tuple[Text, ...]
    explanation: Text


class Criterion(Definition):
    id: Text
    label: Text
    kind: Literal["culprit", "weapon", "motive", "process", "support"]
    points: Annotated[int, Field(gt=0, le=100)]
    step_id: Text | None
    evidence_ids: tuple[Text, ...]
    explanation: Text


class Scoring(Definition):
    correct_min: Annotated[int, Field(gt=0, le=100)]
    partial_min: Annotated[int, Field(gt=0, le=100)]
    wrong_culprit_is_wrong: bool
    process_order: Literal["exact"]
    criteria: tuple[Criterion, ...]


class Case(Definition):
    schema_version: Literal[3]
    scope: Literal["full_case"]
    case_id: Text
    version: Text
    rules_version: Text
    title: Text
    synopsis: Text
    introduction: Text
    review_status: Literal["pending_human_review", "approved"]
    timeline_origin_label: Text
    show_key_badges: bool
    characters: tuple[Character, ...]
    scenes: tuple[Scene, ...]
    evidence: tuple[Evidence, ...]
    knowledge: tuple[Knowledge, ...]
    lies: tuple[Lie, ...]
    lie_chains: tuple[LieChain, ...]
    interrogation: Interrogation
    deep_unlock: Dependency
    relationships: tuple[Relationship, ...]
    timeline: tuple[TimelineEvent, ...]
    suspects: tuple[Choice, ...]
    weapons: tuple[Choice, ...]
    motives: tuple[Choice, ...]
    process_steps: tuple[Choice, ...]
    truth: Truth
    scoring: Scoring


class StepEvidenceLink(Definition):
    step_id: Text
    evidence_id: Text


class Accusation(Definition):
    culprit: Text
    weapon: Text
    motive: Text
    steps: tuple[Text, ...]
    cited_evidence_ids: tuple[Text, ...]
    evidence_links: tuple[StepEvidenceLink, ...]
    explanation: Annotated[str, Field(max_length=4000)] = ""


class AccusationDraft(Definition):
    """A saveable partial accusation; the three choices may stay open and steps may be empty."""

    culprit: Text | None
    weapon: Text | None
    motive: Text | None
    steps: tuple[Text, ...]
    cited_evidence_ids: tuple[Text, ...]
    evidence_links: tuple[StepEvidenceLink, ...]
    explanation: Annotated[str, Field(max_length=4000)] = ""


@dataclass(frozen=True)
class NPCState:
    pressure: int
    trust: int
    lies: Mapping[str, LieStage]  # every layer of this NPC, initially UNBROKEN
    presented: frozenset[str] = frozenset()
    # Consecutive irrelevant moves in the current interrogation; leaving resets it.
    irrelevant_streak: int = 0


@dataclass(frozen=True)
class CriterionResult:
    id: str
    label: str
    points: int
    maximum: int
    explanation: str
    missing_evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Verdict:
    category: str
    score: int
    criteria: tuple[CriterionResult, ...]
    accusation: Accusation
    evidence_snapshot: frozenset[str]
    case_version: str
    rules_version: str
    fixed_explanation: str = ""


@dataclass(frozen=True)
class GameState:
    npcs: Mapping[str, NPCState]  # one entry per interrogatable character
    phase: Phase = Phase.INVESTIGATION
    active_npc_id: str | None = None
    evidence_ids: frozenset[str] = frozenset()
    completed_actions: frozenset[str] = frozenset()
    disclosed_knowledge: frozenset[str] = frozenset()
    consumed_effects: frozenset[str] = frozenset()
    deep_unlocked: bool = False
    draft: AccusationDraft | None = None
    verdict: Verdict | None = None
    version: int = 1


class GameError(ValueError):
    """A safe message for a rejected player action, with a stable machine-readable code."""

    def __init__(self, message: str, code: str = "ACTION_NOT_ALLOWED"):
        super().__init__(message)
        self.code = code
