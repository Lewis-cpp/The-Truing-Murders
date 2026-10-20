"""Static, versioned case definition tables. Published rows are never updated."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CHAR, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database import Base

RESTRICT = {"ondelete": "RESTRICT", "onupdate": "RESTRICT"}
CREDIBILITY = "'UNVERIFIED', 'VERIFIED', 'DISPUTED', 'REFUTED'"


def template_fk() -> ForeignKey:
    return ForeignKey("case_template.template_id", **RESTRICT)


class CaseTemplate(Base):
    __tablename__ = "case_template"
    __table_args__ = (
        UniqueConstraint("case_id", "version"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'RETIRED')", name="status"),
        CheckConstraint(
            "status = 'DRAFT' OR (content_hash IS NOT NULL AND published_at IS NOT NULL)",
            name="published_identity",
        ),
        CheckConstraint("status <> 'RETIRED' OR retired_at IS NOT NULL", name="retired_at"),
        CheckConstraint("definition_schema_version > 0", name="schema_version"),
        CheckConstraint("jsonb_typeof(truth_json) = 'object'", name="truth_json"),
        CheckConstraint(
            "jsonb_typeof(accusation_options_json) = 'object'", name="accusation_options_json"
        ),
        CheckConstraint("jsonb_typeof(scoring_policy_json) = 'object'", name="scoring_policy_json"),
        CheckConstraint("jsonb_typeof(rules_json) = 'object'", name="rules_json"),
        CheckConstraint(
            "jsonb_typeof(public_knowledge_json) = 'array'", name="public_knowledge_json"
        ),
        Index("ix_case_template_status_published_at", "status", "published_at"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    synopsis: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    definition_schema_version: Mapped[int] = mapped_column(Integer)
    definition_scope: Mapped[str] = mapped_column(String(32))
    review_status: Mapped[str] = mapped_column(String(32))
    rules_version: Mapped[str] = mapped_column(String(32))
    rule_execution_version: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str | None] = mapped_column(CHAR(64))
    truth_json: Mapped[dict] = mapped_column(JSONB)
    accusation_options_json: Mapped[dict] = mapped_column(JSONB)
    scoring_policy_json: Mapped[dict] = mapped_column(JSONB)
    rules_json: Mapped[dict] = mapped_column(JSONB)
    public_knowledge_json: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Character(Base):
    __tablename__ = "character"
    __table_args__ = (
        CheckConstraint("role IN ('SUSPECT', 'VICTIM', 'WITNESS')", name="role"),
        CheckConstraint(
            "(is_interrogatable AND initial_pressure IS NOT NULL AND initial_trust IS NOT NULL)"
            " OR (NOT is_interrogatable AND initial_pressure IS NULL AND initial_trust IS NULL)",
            name="initial_values",
        ),
        CheckConstraint("initial_pressure BETWEEN 0 AND 100", name="initial_pressure"),
        CheckConstraint("initial_trust BETWEEN 0 AND 100", name="initial_trust"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), template_fk(), primary_key=True
    )
    character_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(24))
    public_identity: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer)
    is_interrogatable: Mapped[bool] = mapped_column(Boolean)
    initial_pressure: Mapped[int | None] = mapped_column(SmallInteger)
    initial_trust: Mapped[int | None] = mapped_column(SmallInteger)


class CharacterSecret(Base):
    __tablename__ = "character_secret"
    __table_args__ = (
        ForeignKeyConstraint(
            ["template_id", "character_id"],
            ["character.template_id", "character.character_id"],
            **RESTRICT,
        ),
        CheckConstraint("assertion_kind IN ('FACT', 'TESTIMONY')", name="assertion_kind"),
        CheckConstraint(f"initial_credibility IN ({CREDIBILITY})", name="initial_credibility"),
        CheckConstraint(
            "jsonb_typeof(known_by_json) = 'array' AND jsonb_array_length(known_by_json) > 0",
            name="known_by_json",
        ),
        CheckConstraint("disclosure IN ('ADMITTED', 'ASKED')", name="disclosure"),
        Index("ix_character_secret_owner", "template_id", "character_id", "secret_id"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), template_fk(), primary_key=True
    )
    secret_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    known_by_json: Mapped[list] = mapped_column(JSONB)
    assertion_kind: Mapped[str] = mapped_column(String(16))
    initial_credibility: Mapped[str] = mapped_column(String(16))
    # How the entry reaches the player: a lie admission, or the answer to a fixed topic.
    disclosure: Mapped[str] = mapped_column(String(16), server_default=text("'ADMITTED'"))


class Scene(Base):
    __tablename__ = "scene"
    __table_args__ = (CheckConstraint("jsonb_typeof(actions_json) = 'array'", name="actions_json"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), template_fk(), primary_key=True
    )
    scene_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer)
    actions_json: Mapped[list] = mapped_column(JSONB)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["template_id", "source_scene_id"], ["scene.template_id", "scene.scene_id"], **RESTRICT
        ),
        ForeignKeyConstraint(
            ["template_id", "source_character_id"],
            ["character.template_id", "character.character_id"],
            **RESTRICT,
        ),
        CheckConstraint(
            "(source_type = 'SCENE' AND source_scene_id IS NOT NULL"
            " AND source_character_id IS NULL)"
            " OR (source_type = 'NPC' AND source_character_id IS NOT NULL"
            " AND source_scene_id IS NULL)",
            name="source",
        ),
        CheckConstraint(f"initial_credibility IN ({CREDIBILITY})", name="initial_credibility"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), template_fk(), primary_key=True
    )
    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    source_label: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(8))
    source_scene_id: Mapped[str | None] = mapped_column(String(64))
    source_character_id: Mapped[str | None] = mapped_column(String(64))
    initial_credibility: Mapped[str] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(Integer)


class EvidenceDependency(Base):
    __tablename__ = "evidence_dependency"
    __table_args__ = (
        ForeignKeyConstraint(
            ["template_id", "evidence_id"],
            ["evidence.template_id", "evidence.evidence_id"],
            **RESTRICT,
        ),
        ForeignKeyConstraint(
            ["template_id", "required_evidence_id"],
            ["evidence.template_id", "evidence.evidence_id"],
            **RESTRICT,
        ),
        CheckConstraint("dependency_mode IN ('ALL', 'ANY')", name="dependency_mode"),
        CheckConstraint("evidence_id <> required_evidence_id", name="no_self_dependency"),
        Index("ix_evidence_dependency_required", "template_id", "required_evidence_id"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dependency_mode: Mapped[str] = mapped_column(String(8), primary_key=True)
    required_evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class LieRule(Base):
    __tablename__ = "lie_rule"
    __table_args__ = (
        ForeignKeyConstraint(
            ["template_id", "character_id"],
            ["character.template_id", "character.character_id"],
            **RESTRICT,
        ),
        CheckConstraint("jsonb_typeof(statements_json) = 'object'", name="statements_json"),
        CheckConstraint(
            "jsonb_typeof(counterevidence_json) = 'object'", name="counterevidence_json"
        ),
        CheckConstraint(
            "jsonb_typeof(admission_condition_json) = 'object'", name="admission_condition_json"
        ),
        CheckConstraint("jsonb_typeof(on_admitted_json) = 'object'", name="on_admitted_json"),
        Index("ix_lie_rule_character", "template_id", "character_id", "priority", "lie_rule_id"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), template_fk(), primary_key=True
    )
    lie_rule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer)
    statements_json: Mapped[dict] = mapped_column(JSONB)
    counterevidence_json: Mapped[dict] = mapped_column(JSONB)
    admission_condition_json: Mapped[dict] = mapped_column(JSONB)
    on_admitted_json: Mapped[dict] = mapped_column(JSONB)
