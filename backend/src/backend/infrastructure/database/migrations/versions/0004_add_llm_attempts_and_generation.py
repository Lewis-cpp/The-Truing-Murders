"""Add llm attempts and generation columns

Revision ID: 0004
Revises: 0003

v0.4 gives NPC01 model-generated replies outside the business transaction. The
llm_attempt table records every generation try with its budget reservation and
settleable usage (doc 09, section 6.6); conversation gains the active attempt
pointer and a partial unique index so one session holds at most one pending
round; game_session gains the per-game llm budget frozen at game start. Existing
sessions are backfilled with the default budget so they keep playing. Downgrade
removes the columns and the table; conversations written by v0.4 keep their
stored fixed replies but lose the attempt bookkeeping (the spec only requires a
clean downgrade).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_BUDGET = (
    '{"session_call_limit": 60, "session_token_limit": 200000,'
    ' "max_input_tokens": 4000, "max_output_tokens": 400, "timeout_seconds": 30.0}'
)


def upgrade() -> None:
    op.create_table(
        "llm_attempt",
        sa.Column("attempt_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("request_action_id", sa.UUID(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("usage_status", sa.String(length=16), nullable=False),
        sa.Column("validation_status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("context_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("context_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False),
        sa.Column("count_is_exact", sa.Boolean(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_tokens", sa.BigInteger(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("billable_tokens", sa.BigInteger(), nullable=True),
        sa.Column("usage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "pricing_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempt_no > 0",
            name=op.f("ck_llm_attempt_attempt_no"),
        ),
        sa.CheckConstraint(
            "context_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_llm_attempt_context_digest"),
        ),
        sa.CheckConstraint(
            "estimated_input_tokens >= 0", name=op.f("ck_llm_attempt_estimated_input_tokens")
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name=op.f("ck_llm_attempt_input_tokens")
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name=op.f("ck_llm_attempt_output_tokens"),
        ),
        sa.CheckConstraint(
            "reserved_tokens >= 0", name=op.f("ck_llm_attempt_reserved_tokens")
        ),
        sa.CheckConstraint(
            "status IN ('RESERVED', 'DISPATCHING', 'SUCCEEDED', 'FAILED', 'UNKNOWN',"
            " 'CANCELLED_NOT_SENT')",
            name=op.f("ck_llm_attempt_status"),
        ),
        sa.CheckConstraint(
            "usage_status IN ('RESERVED', 'KNOWN', 'UNKNOWN', 'NOT_SENT')",
            name=op.f("ck_llm_attempt_usage_status"),
        ),
        sa.CheckConstraint(
            "validation_status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'STALE',"
            " 'NOT_APPLICABLE')",
            name=op.f("ck_llm_attempt_validation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "conversation_id"],
            ["conversation.session_id", "conversation.conversation_id"],
            name=op.f("fk_llm_attempt_session_id_conversation_id_conversation"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "request_action_id"],
            ["action_request.session_id", "action_request.action_id"],
            name=op.f("fk_llm_attempt_session_id_request_action_id_action_request"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_llm_attempt")),
        sa.UniqueConstraint(
            "conversation_id",
            "attempt_no",
            name=op.f("uq_llm_attempt_conversation_id_attempt_no"),
        ),
        sa.UniqueConstraint(
            "request_action_id", name=op.f("uq_llm_attempt_request_action_id")
        ),
        sa.UniqueConstraint(
            "session_id",
            "conversation_id",
            "attempt_id",
            name=op.f("uq_llm_attempt_session_id_conversation_id_attempt_id"),
        ),
    )
    op.create_index(
        "ix_llm_attempt_session", "llm_attempt", ["session_id"], unique=False
    )
    op.add_column(
        "conversation",
        sa.Column("active_attempt_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_conversation_session_id_conversation_id_active_attempt_id_llm_attempt"),
        "conversation",
        "llm_attempt",
        ["session_id", "conversation_id", "active_attempt_id"],
        ["session_id", "conversation_id", "attempt_id"],
        onupdate="RESTRICT",
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_conversation_session_pending",
        "conversation",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("generation_status IN ('PREPARING', 'GENERATING')"),
    )
    op.add_column(
        "game_session",
        sa.Column("llm_budget_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(f"UPDATE game_session SET llm_budget_json = '{DEFAULT_BUDGET}'::jsonb")
    op.create_check_constraint(
        op.f("ck_game_session_llm_budget_json"),
        "game_session",
        "llm_budget_json IS NULL OR jsonb_typeof(llm_budget_json) = 'object'",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_game_session_llm_budget_json"), "game_session", type_="check"
    )
    op.drop_column("game_session", "llm_budget_json")
    op.drop_index("uq_conversation_session_pending", table_name="conversation")
    op.drop_constraint(
        op.f("fk_conversation_session_id_conversation_id_active_attempt_id_llm_attempt"),
        "conversation",
        type_="foreignkey",
    )
    op.drop_column("conversation", "active_attempt_id")
    op.drop_index("ix_llm_attempt_session", table_name="llm_attempt")
    op.drop_table("llm_attempt")
