"""Runtime tables: visitor, game save, idempotent requests, events, effects and verdicts."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CHAR, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database import Base
from backend.infrastructure.database.models.case import CREDIBILITY, RESTRICT

PHASES = (
    "'INVESTIGATION', 'INTERROGATION', 'DEEP_INVESTIGATION', 'ACCUSATION', 'REVIEW', 'FINISHED'"
)
EVENT_TYPES = (
    "'SESSION_CREATED', 'INVESTIGATE', 'SET_INTERROGATION', 'END_INTERROGATION',"
    " 'PRESENT_EVIDENCE', 'OPEN_ACCUSATION', 'CANCEL_ACCUSATION', 'SUBMIT_ACCUSATION',"
    " 'FINISH_REVIEW'"
)


def session_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["session_id", "template_id"],
        ["game_session.session_id", "game_session.template_id"],
        **RESTRICT,
    )


class Visitor(Base):
    __tablename__ = "visitor"
    __table_args__ = (
        # Circular with game_session.visitor_id; created after both tables exist.
        ForeignKeyConstraint(
            ["visitor_id", "current_session_id"],
            ["game_session.visitor_id", "game_session.session_id"],
            use_alter=True,
            **RESTRICT,
        ),
    )

    visitor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    current_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GameSession(Base):
    __tablename__ = "game_session"
    __table_args__ = (
        UniqueConstraint("session_id", "template_id"),
        UniqueConstraint("visitor_id", "session_id"),
        ForeignKeyConstraint(
            ["template_id", "active_npc_id"],
            ["character.template_id", "character.character_id"],
            **RESTRICT,
        ),
        ForeignKeyConstraint(
            ["session_id", "deep_unlock_event_id"],
            ["game_event_log.session_id", "game_event_log.event_id"],
            use_alter=True,
            **RESTRICT,
        ),
        CheckConstraint(f"phase IN ({PHASES})", name="phase"),
        CheckConstraint(
            "(phase = 'INTERROGATION') = (active_npc_id IS NOT NULL)", name="active_npc"
        ),
        CheckConstraint(
            "phase <> 'DEEP_INVESTIGATION' OR deep_unlock_event_id IS NOT NULL",
            name="deep_unlock",
        ),
        CheckConstraint(
            "(phase IN ('REVIEW', 'FINISHED')) = (closed_at IS NOT NULL)", name="closed_at"
        ),
        CheckConstraint(
            "(phase = 'FINISHED') = (finished_at IS NOT NULL) AND finished_at >= closed_at",
            name="finished_at",
        ),
        CheckConstraint("state_version > 0", name="state_version"),
        CheckConstraint("snapshot_schema_version > 0", name="snapshot_schema_version"),
        CheckConstraint("jsonb_typeof(state_json) = 'object'", name="state_json"),
        Index("ix_game_session_visitor_saved", "visitor_id", "saved_at"),
        Index("ix_game_session_template", "template_id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visitor.visitor_id", **RESTRICT)
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_template.template_id", **RESTRICT)
    )
    phase: Mapped[str] = mapped_column(String(24))
    active_npc_id: Mapped[str | None] = mapped_column(String(64))
    deep_unlock_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    state_version: Mapped[int] = mapped_column(BigInteger)
    snapshot_schema_version: Mapped[int] = mapped_column(Integer)
    state_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionRequest(Base):
    __tablename__ = "action_request"
    __table_args__ = (
        UniqueConstraint("visitor_id", "request_id"),
        UniqueConstraint("session_id", "action_id"),
        ForeignKeyConstraint(
            ["visitor_id", "session_id"],
            ["game_session.visitor_id", "game_session.session_id"],
            **RESTRICT,
        ),
        CheckConstraint("status IN ('COMMITTED', 'NOOP', 'REJECTED')", name="status"),
        CheckConstraint("http_status BETWEEN 200 AND 599", name="http_status"),
        CheckConstraint("expected_state_version > 0", name="expected_state_version"),
        CheckConstraint("jsonb_typeof(input_json) = 'object'", name="input_json"),
        CheckConstraint("jsonb_typeof(result_json) = 'object'", name="result_json"),
        Index("ix_action_request_session_created", "session_id", "created_at", "action_id"),
    )

    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visitor.visitor_id", **RESTRICT)
    )
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    command_type: Mapped[str] = mapped_column(String(40))
    expected_state_version: Mapped[int | None] = mapped_column(BigInteger)
    input_hash: Mapped[str] = mapped_column(CHAR(64))
    input_json: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    http_status: Mapped[int] = mapped_column(SmallInteger)
    result_state_version: Mapped[int | None] = mapped_column(BigInteger)
    result_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GameEventLog(Base):
    __tablename__ = "game_event_log"
    __table_args__ = (
        UniqueConstraint("session_id", "event_seq"),
        UniqueConstraint("session_id", "action_id"),
        UniqueConstraint("session_id", "event_id"),
        session_fk(),
        ForeignKeyConstraint(
            ["session_id", "action_id"],
            ["action_request.session_id", "action_request.action_id"],
            **RESTRICT,
        ),
        ForeignKeyConstraint(
            ["template_id", "target_character_id"],
            ["character.template_id", "character.character_id"],
            **RESTRICT,
        ),
        ForeignKeyConstraint(
            ["template_id", "presented_evidence_id"],
            ["evidence.template_id", "evidence.evidence_id"],
            **RESTRICT,
        ),
        CheckConstraint(f"event_type IN ({EVENT_TYPES})", name="event_type"),
        CheckConstraint("event_seq > 0", name="event_seq"),
        CheckConstraint(
            "state_version_after IN (state_version_before, state_version_before + 1)",
            name="state_version_step",
        ),
        CheckConstraint(
            "(event_type = 'PRESENT_EVIDENCE') = (presented_evidence_id IS NOT NULL)",
            name="presented_evidence",
        ),
        CheckConstraint("jsonb_typeof(input_json) = 'object'", name="input_json"),
        CheckConstraint("jsonb_typeof(outcome_json) = 'object'", name="outcome_json"),
        Index(
            "ix_game_event_log_presented",
            "session_id",
            "target_character_id",
            "event_type",
            "presented_evidence_id",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_seq: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(40))
    target_character_id: Mapped[str | None] = mapped_column(String(64))
    presented_evidence_id: Mapped[str | None] = mapped_column(String(64))
    state_version_before: Mapped[int] = mapped_column(BigInteger)
    state_version_after: Mapped[int] = mapped_column(BigInteger)
    rules_version: Mapped[str] = mapped_column(String(32))
    rule_execution_version: Mapped[str] = mapped_column(String(32))
    input_json: Mapped[dict] = mapped_column(JSONB)
    outcome_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerEvidence(Base):
    __tablename__ = "player_evidence"
    __table_args__ = (
        session_fk(),
        ForeignKeyConstraint(
            ["template_id", "evidence_id"],
            ["evidence.template_id", "evidence.evidence_id"],
            **RESTRICT,
        ),
        ForeignKeyConstraint(
            ["session_id", "acquired_event_id"],
            ["game_event_log.session_id", "game_event_log.event_id"],
            **RESTRICT,
        ),
        CheckConstraint(f"credibility IN ({CREDIBILITY})", name="credibility"),
        Index("ix_player_evidence_definition", "template_id", "evidence_id"),
        Index("ix_player_evidence_acquired", "session_id", "acquired_event_id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acquired_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    credibility: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NpcState(Base):
    __tablename__ = "npc_state"
    __table_args__ = (
        session_fk(),
        ForeignKeyConstraint(
            ["template_id", "character_id"],
            ["character.template_id", "character.character_id"],
            **RESTRICT,
        ),
        CheckConstraint("pressure BETWEEN 0 AND 100", name="pressure"),
        CheckConstraint("trust BETWEEN 0 AND 100", name="trust"),
        CheckConstraint("jsonb_typeof(lies_json) = 'object'", name="lies_json"),
        Index("ix_npc_state_definition", "template_id", "character_id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    character_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pressure: Mapped[int] = mapped_column(SmallInteger)
    trust: Mapped[int] = mapped_column(SmallInteger)
    lies_json: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RuleEffect(Base):
    __tablename__ = "rule_effect"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "event_id"],
            ["game_event_log.session_id", "game_event_log.event_id"],
            **RESTRICT,
        ),
        Index("ix_rule_effect_event", "session_id", "event_id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("game_session.session_id", **RESTRICT),
        primary_key=True,
    )
    effect_key: Mapped[str] = mapped_column(String(384), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))


class Accusation(Base):
    __tablename__ = "accusation"
    __table_args__ = (
        session_fk(),
        ForeignKeyConstraint(
            ["session_id", "action_id"],
            ["action_request.session_id", "action_request.action_id"],
            **RESTRICT,
        ),
        ForeignKeyConstraint(
            ["template_id", "suspect_character_id"],
            ["character.template_id", "character.character_id"],
            **RESTRICT,
        ),
        CheckConstraint(
            "verdict_category IN ('CORRECT', 'PARTIALLY_CORRECT', 'INCORRECT')",
            name="verdict_category",
        ),
        CheckConstraint("score >= 0 AND score <= max_score", name="score"),
        CheckConstraint("submitted_state_version > 0", name="submitted_state_version"),
        CheckConstraint(
            "jsonb_typeof(ordered_process_step_ids_json) = 'array'"
            " AND jsonb_array_length(ordered_process_step_ids_json) > 0",
            name="ordered_process_step_ids_json",
        ),
        CheckConstraint(
            "jsonb_typeof(cited_evidence_ids_json) = 'array'", name="cited_evidence_ids_json"
        ),
        CheckConstraint(
            "jsonb_typeof(step_evidence_links_json) = 'array'", name="step_evidence_links_json"
        ),
        CheckConstraint("jsonb_typeof(grading_input_json) = 'object'", name="grading_input_json"),
        CheckConstraint(
            "jsonb_typeof(criteria_results_json) = 'array'", name="criteria_results_json"
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    submitted_state_version: Mapped[int] = mapped_column(BigInteger)
    rules_version: Mapped[str] = mapped_column(String(32))
    rule_execution_version: Mapped[str] = mapped_column(String(32))
    suspect_character_id: Mapped[str] = mapped_column(String(64))
    weapon_option_id: Mapped[str] = mapped_column(String(64))
    motive_option_id: Mapped[str] = mapped_column(String(64))
    ordered_process_step_ids_json: Mapped[list] = mapped_column(JSONB)
    cited_evidence_ids_json: Mapped[list] = mapped_column(JSONB)
    step_evidence_links_json: Mapped[list] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text)
    grading_input_json: Mapped[dict] = mapped_column(JSONB)
    verdict_category: Mapped[str] = mapped_column(String(20))
    score: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_score: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    criteria_results_json: Mapped[list] = mapped_column(JSONB)
    fixed_review: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
