"""Add memory epochs and per-character summary cache

Revision ID: 0005
Revises: 0004

v0.5 lets all four interrogatable characters share the v0.4 generation path and
gives each of them a bounded memory: npc_state.memory_epoch marks the current
authorization segment (advanced whenever the fingerprint of what a person may
say or see changes), and npc_memory_summary caches one extractive summary per
(session, character) with an optimistic revision used for invalidation
(doc 12, section 6.2). Existing rows start in epoch 0 with no cached summary;
conversation rows written before this migration carry no memory_epoch in their
response plan and therefore stay visible to the player but never re-enter a
model context. Downgrade drops both.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "npc_state",
        sa.Column("memory_epoch", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(op.f("ck_npc_state_memory_epoch"), "npc_state", "memory_epoch >= 0")
    op.create_table(
        "npc_memory_summary",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("memory_epoch", sa.Integer(), nullable=False),
        sa.Column("summary_revision", sa.Integer(), nullable=False),
        sa.Column("covered_through_seq", sa.BigInteger(), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Cleared summaries may be the SQL NULL or the JSON null the driver binds
        # for None; both mean "no content" and must pass the shape check.
        sa.CheckConstraint(
            "summary_json IS NULL OR jsonb_typeof(summary_json) IN ('object', 'null')",
            name=op.f("ck_npc_memory_summary_summary_json"),
        ),
        sa.CheckConstraint(
            "memory_epoch >= 0 AND summary_revision >= 0 AND covered_through_seq >= 0",
            name=op.f("ck_npc_memory_summary_counters"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "template_id"],
            ["game_session.session_id", "game_session.template_id"],
            name=op.f("fk_npc_memory_summary_session_id_template_id_game_session"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id", "character_id", name=op.f("pk_npc_memory_summary")),
    )


def downgrade() -> None:
    op.drop_table("npc_memory_summary")
    op.drop_constraint(op.f("ck_npc_state_memory_epoch"), "npc_state", type_="check")
    op.drop_column("npc_state", "memory_epoch")
