"""Add testimony topics and evasion

Revision ID: 0002
Revises: 0001

The 2-slice rules record an NPC's answer to a fixed topic as testimony, let the player point
out a contradiction, and make an NPC evade after repeated irrelevant moves. Private knowledge
now says how it is disclosed, NPC state keeps the irrelevant streak, and the event log accepts
the two new commands. Existing rows keep their meaning: every earlier secret was an admission.
Topics name every asked secret, so upgrading again after a downgrade restores them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_EVENT_TYPES = "event_type IN ('SESSION_CREATED', 'INVESTIGATE', 'SET_INTERROGATION', 'END_INTERROGATION', 'PRESENT_EVIDENCE', 'OPEN_ACCUSATION', 'CANCEL_ACCUSATION', 'SUBMIT_ACCUSATION', 'FINISH_REVIEW')"
NEW_EVENT_TYPES = "event_type IN ('SESSION_CREATED', 'INVESTIGATE', 'SET_INTERROGATION', 'END_INTERROGATION', 'PRESENT_EVIDENCE', 'OPEN_ACCUSATION', 'CANCEL_ACCUSATION', 'SUBMIT_ACCUSATION', 'FINISH_REVIEW', 'ASK_TOPIC', 'POINT_CONTRADICTION')"


def upgrade() -> None:
    op.add_column(
        "character_secret",
        sa.Column(
            "disclosure", sa.String(length=16), server_default=sa.text("'ADMITTED'"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_character_secret_disclosure"),
        "character_secret",
        "disclosure IN ('ADMITTED', 'ASKED')",
    )
    op.execute(
        """
        UPDATE character_secret AS s SET disclosure = 'ASKED'
        FROM case_template AS t,
            jsonb_array_elements(t.rules_json -> 'interrogation' -> 'topics') AS topic
        WHERE s.template_id = t.template_id AND s.secret_id = topic ->> 'knowledge_id'
        """
    )
    op.add_column(
        "npc_state",
        sa.Column(
            "irrelevant_streak", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_npc_state_irrelevant_streak"), "npc_state", "irrelevant_streak >= 0"
    )
    op.drop_constraint(op.f("ck_game_event_log_event_type"), "game_event_log", type_="check")
    op.create_check_constraint(
        op.f("ck_game_event_log_event_type"), "game_event_log", NEW_EVENT_TYPES
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_game_event_log_event_type"), "game_event_log", type_="check")
    # Events of the new commands may exist; keep them and check only rows written afterwards.
    op.create_check_constraint(
        op.f("ck_game_event_log_event_type"),
        "game_event_log",
        OLD_EVENT_TYPES,
        postgresql_not_valid=True,
    )
    op.drop_constraint(op.f("ck_npc_state_irrelevant_streak"), "npc_state", type_="check")
    op.drop_column("npc_state", "irrelevant_streak")
    op.drop_constraint(op.f("ck_character_secret_disclosure"), "character_secret", type_="check")
    op.drop_column("character_secret", "disclosure")
