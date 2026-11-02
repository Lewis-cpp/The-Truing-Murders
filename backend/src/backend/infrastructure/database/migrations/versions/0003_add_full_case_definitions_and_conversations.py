"""Add full case definitions and conversations

Revision ID: 0003
Revises: 0002

Schema 3 needs the relationship graph, the case timeline, lie chains, per-character
personality fields, evidence kinds and key flags, scene unlock conditions and the deep
unlock branch. Interaction rounds become rows in conversation and conversation_message;
no llm_attempt table exists yet, so every round is completed in the same transaction.
Slice rows (schema 2) keep NULL in the new static columns and stay stored but unsupported.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lie_chain",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("lie_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(lie_ids_json) = 'array'", name=op.f("ck_lie_chain_lie_ids_json")
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_lie_chain_template_id_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_lie_chain_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("template_id", "chain_id", name=op.f("pk_lie_chain")),
    )
    op.create_table(
        "relationship",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("relationship_id", sa.String(length=64), nullable=False),
        sa.Column("from_character_id", sa.String(length=64), nullable=False),
        sa.Column("to_character_id", sa.String(length=64), nullable=False),
        sa.Column("relationship_type", sa.String(length=100), nullable=False),
        sa.Column("directed", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assertion_kind", sa.String(length=16), nullable=False),
        sa.Column("credibility", sa.String(length=16), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column(
            "reveal_evidence_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "reveal_knowledge_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "assertion_kind IN ('FACT', 'TESTIMONY')", name=op.f("ck_relationship_assertion_kind")
        ),
        sa.CheckConstraint(
            "credibility IN ('UNVERIFIED', 'VERIFIED', 'DISPUTED', 'REFUTED')",
            name=op.f("ck_relationship_credibility"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reveal_evidence_ids_json) = 'array'",
            name=op.f("ck_relationship_reveal_evidence_ids_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reveal_knowledge_ids_json) = 'array'",
            name=op.f("ck_relationship_reveal_knowledge_ids_json"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('PUBLIC', 'EVIDENCE', 'NPC')",
            name=op.f("ck_relationship_source_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "from_character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_relationship_template_id_from_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "to_character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_relationship_template_id_to_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_relationship_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("template_id", "relationship_id", name=op.f("pk_relationship")),
    )
    op.create_table(
        "timeline_event",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("timeline_event_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("participant_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("precision", sa.String(length=8), nullable=False),
        sa.Column("start_minutes", sa.Integer(), nullable=True),
        sa.Column("end_minutes", sa.Integer(), nullable=True),
        sa.Column("time_label", sa.Text(), nullable=False),
        sa.Column("assertion_kind", sa.String(length=16), nullable=False),
        sa.Column("credibility", sa.String(length=16), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column(
            "reveal_evidence_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "reveal_knowledge_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("conflicts_with_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "assertion_kind IN ('FACT', 'TESTIMONY')", name=op.f("ck_timeline_event_assertion_kind")
        ),
        sa.CheckConstraint(
            "credibility IN ('UNVERIFIED', 'VERIFIED', 'DISPUTED', 'REFUTED')",
            name=op.f("ck_timeline_event_credibility"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(conflicts_with_json) = 'array'",
            name=op.f("ck_timeline_event_conflicts_with_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(participant_ids_json) = 'array'",
            name=op.f("ck_timeline_event_participant_ids_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reveal_evidence_ids_json) = 'array'",
            name=op.f("ck_timeline_event_reveal_evidence_ids_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reveal_knowledge_ids_json) = 'array'",
            name=op.f("ck_timeline_event_reveal_knowledge_ids_json"),
        ),
        sa.CheckConstraint(
            "precision IN ('EXACT', 'RANGE', 'UNKNOWN')",
            name=op.f("ck_timeline_event_precision"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('PUBLIC', 'EVIDENCE', 'NPC')",
            name=op.f("ck_timeline_event_source_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "scene_id"],
            ["scene.template_id", "scene.scene_id"],
            name=op.f("fk_timeline_event_template_id_scene_id_scene"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_timeline_event_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("template_id", "timeline_event_id", name=op.f("pk_timeline_event")),
    )
    op.create_table(
        "conversation",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("action_id", sa.UUID(), nullable=False),
        sa.Column("conversation_seq", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=8), server_default=sa.text("'NPC'"), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=True),
        sa.Column("purpose_key", sa.String(length=96), nullable=True),
        sa.Column("source_state_version", sa.BigInteger(), nullable=False),
        sa.Column("response_plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fixed_reply", sa.Text(), nullable=False),
        sa.Column("generation_status", sa.String(length=16), nullable=False),
        sa.Column("generation_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fallback_reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(role = 'NPC') = (character_id IS NOT NULL)", name=op.f("ck_conversation_character_id")
        ),
        sa.CheckConstraint(
            "generation_deadline_at IS NOT NULL"
            " OR generation_status NOT IN ('PREPARING', 'GENERATING')",
            name=op.f("ck_conversation_deadline"),
        ),
        sa.CheckConstraint(
            "generation_status IN ('PREPARING', 'GENERATING', 'COMPLETED', 'FALLBACK', 'STALE')",
            name=op.f("ck_conversation_generation_status"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(response_plan_json) = 'object'",
            name=op.f("ck_conversation_response_plan_json"),
        ),
        sa.CheckConstraint("role IN ('NPC', 'HOST', 'REVIEW')", name=op.f("ck_conversation_role")),
        sa.CheckConstraint("conversation_seq > 0", name=op.f("ck_conversation_conversation_seq")),
        sa.ForeignKeyConstraint(
            ["session_id", "action_id"],
            ["action_request.session_id", "action_request.action_id"],
            name=op.f("fk_conversation_session_id_action_id_action_request"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "template_id"],
            ["game_session.session_id", "game_session.template_id"],
            name=op.f("fk_conversation_session_id_template_id_game_session"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_conversation_template_id_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("conversation_id", name=op.f("pk_conversation")),
        sa.UniqueConstraint(
            "session_id", "action_id", name=op.f("uq_conversation_session_id_action_id")
        ),
        sa.UniqueConstraint(
            "session_id",
            "conversation_seq",
            name=op.f("uq_conversation_session_id_conversation_seq"),
        ),
        sa.UniqueConstraint(
            "session_id", "conversation_id", name=op.f("uq_conversation_session_id_conversation_id")
        ),
    )
    op.create_index(
        "ix_conversation_character_seq",
        "conversation",
        ["session_id", "character_id", "conversation_seq"],
        unique=False,
    )
    op.create_table(
        "conversation_message",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("sequence_no", sa.SmallInteger(), nullable=False),
        sa.Column("speaker", sa.String(length=8), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        sa.Column(
            "validity", sa.String(length=8), server_default=sa.text("'VALID'"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "origin IN ('PLAYER', 'LLM', 'FIXED')",
            name=op.f("ck_conversation_message_origin"),
        ),
        sa.CheckConstraint(
            "speaker IN ('PLAYER', 'NPC', 'HOST', 'REVIEW')",
            name=op.f("ck_conversation_message_speaker"),
        ),
        sa.CheckConstraint(
            "validity IN ('VALID', 'STALE')", name=op.f("ck_conversation_message_validity")
        ),
        sa.CheckConstraint(
            "sequence_no IN (1, 2)", name=op.f("ck_conversation_message_sequence_no")
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "conversation_id"],
            ["conversation.session_id", "conversation.conversation_id"],
            name=op.f("fk_conversation_message_session_id_conversation_id_conversation"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_conversation_message")),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence_no",
            name=op.f("uq_conversation_message_conversation_id_sequence_no"),
        ),
    )
    op.add_column("case_template", sa.Column("introduction", sa.Text(), nullable=True))
    op.add_column("case_template", sa.Column("timeline_origin_label", sa.Text(), nullable=True))
    op.add_column("case_template", sa.Column("show_key_badges", sa.Boolean(), nullable=True))
    op.add_column(
        "case_template",
        sa.Column("deep_unlock_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_case_template_deep_unlock_json"),
        "case_template",
        "deep_unlock_json IS NULL OR jsonb_typeof(deep_unlock_json) = 'object'",
    )
    op.add_column("character", sa.Column("role_label", sa.Text(), nullable=True))
    op.add_column("character", sa.Column("personality", sa.Text(), nullable=True))
    op.add_column("character", sa.Column("speech_style", sa.Text(), nullable=True))
    op.add_column("character", sa.Column("default_reply", sa.Text(), nullable=True))
    op.add_column(
        "character",
        sa.Column("core_lie_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_character_core_lie_ids_json"),
        "character",
        "core_lie_ids_json IS NULL OR jsonb_typeof(core_lie_ids_json) = 'array'",
    )
    op.add_column("evidence", sa.Column("kind", sa.String(length=16), nullable=True))
    op.create_check_constraint(
        op.f("ck_evidence_kind"),
        "evidence",
        "kind IS NULL OR kind IN ('PHYSICAL', 'DOCUMENT', 'TESTIMONY', 'DIGITAL')",
    )
    op.add_column("evidence", sa.Column("is_key", sa.Boolean(), nullable=True))
    op.add_column(
        "scene", sa.Column("unlock_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_scene_unlock_json"),
        "scene",
        "unlock_json IS NULL OR jsonb_typeof(unlock_json) = 'object'",
    )
    op.drop_constraint(op.f("ck_game_event_log_event_type"), "game_event_log", type_="check")
    op.create_check_constraint(
        op.f("ck_game_event_log_event_type"),
        "game_event_log",
        "event_type IN ('SESSION_CREATED', 'INVESTIGATE', 'SET_INTERROGATION',"
        " 'END_INTERROGATION', 'PRESENT_EVIDENCE', 'OPEN_ACCUSATION', 'CANCEL_ACCUSATION',"
        " 'SUBMIT_ACCUSATION', 'FINISH_REVIEW', 'ASK_TOPIC', 'POINT_CONTRADICTION',"
        " 'SAVE_ACCUSATION_DRAFT')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_game_event_log_event_type"), "game_event_log", type_="check")
    op.create_check_constraint(
        op.f("ck_game_event_log_event_type"),
        "game_event_log",
        "event_type IN ('SESSION_CREATED', 'INVESTIGATE', 'SET_INTERROGATION',"
        " 'END_INTERROGATION', 'PRESENT_EVIDENCE', 'OPEN_ACCUSATION', 'CANCEL_ACCUSATION',"
        " 'SUBMIT_ACCUSATION', 'FINISH_REVIEW', 'ASK_TOPIC', 'POINT_CONTRADICTION')",
        postgresql_not_valid=True,
    )
    op.drop_constraint(op.f("ck_scene_unlock_json"), "scene", type_="check")
    op.drop_column("scene", "unlock_json")
    op.drop_constraint(op.f("ck_evidence_kind"), "evidence", type_="check")
    op.drop_column("evidence", "is_key")
    op.drop_column("evidence", "kind")
    op.drop_constraint(op.f("ck_character_core_lie_ids_json"), "character", type_="check")
    op.drop_column("character", "core_lie_ids_json")
    op.drop_column("character", "default_reply")
    op.drop_column("character", "speech_style")
    op.drop_column("character", "personality")
    op.drop_column("character", "role_label")
    op.drop_constraint(op.f("ck_case_template_deep_unlock_json"), "case_template", type_="check")
    op.drop_column("case_template", "deep_unlock_json")
    op.drop_column("case_template", "show_key_badges")
    op.drop_column("case_template", "timeline_origin_label")
    op.drop_column("case_template", "introduction")
    op.drop_table("conversation_message")
    op.drop_index("ix_conversation_character_seq", table_name="conversation")
    op.drop_table("conversation")
    op.drop_table("timeline_event")
    op.drop_table("relationship")
    op.drop_table("lie_chain")
