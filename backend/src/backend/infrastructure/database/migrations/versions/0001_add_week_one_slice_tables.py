"""Add week one slice tables

Revision ID: 0001
Revises:

Only the static definitions and runtime records the W1 slice uses: case version, characters,
private knowledge, scenes, evidence and dependencies, lie layers, visitors, game sessions,
held evidence, NPC state, idempotent requests, the event log, one-time effects and the single
formal accusation. Conversations, model attempts, relationships and timelines arrive later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "case_template",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("synopsis", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("definition_schema_version", sa.Integer(), nullable=False),
        sa.Column("definition_scope", sa.String(length=32), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("rule_execution_version", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=True),
        sa.Column("truth_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "accusation_options_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("scoring_policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("public_knowledge_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "jsonb_typeof(accusation_options_json) = 'object'",
            name=op.f("ck_case_template_accusation_options_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(public_knowledge_json) = 'array'",
            name=op.f("ck_case_template_public_knowledge_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(rules_json) = 'object'", name=op.f("ck_case_template_rules_json")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(scoring_policy_json) = 'object'",
            name=op.f("ck_case_template_scoring_policy_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(truth_json) = 'object'", name=op.f("ck_case_template_truth_json")
        ),
        sa.CheckConstraint(
            "status <> 'RETIRED' OR retired_at IS NOT NULL",
            name=op.f("ck_case_template_retired_at"),
        ),
        sa.CheckConstraint(
            "status = 'DRAFT' OR (content_hash IS NOT NULL AND published_at IS NOT NULL)",
            name=op.f("ck_case_template_published_identity"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'RETIRED')", name=op.f("ck_case_template_status")
        ),
        sa.CheckConstraint(
            "definition_schema_version > 0", name=op.f("ck_case_template_schema_version")
        ),
        sa.PrimaryKeyConstraint("template_id", name=op.f("pk_case_template")),
        sa.UniqueConstraint("case_id", "version", name=op.f("uq_case_template_case_id_version")),
    )
    op.create_index(
        "ix_case_template_status_published_at",
        "case_template",
        ["status", "published_at"],
        unique=False,
    )
    op.create_table(
        "visitor",
        sa.Column("visitor_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("current_session_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("visitor_id", name=op.f("pk_visitor")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_visitor_token_hash")),
    )
    op.create_table(
        "character",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("public_identity", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_interrogatable", sa.Boolean(), nullable=False),
        sa.Column("initial_pressure", sa.SmallInteger(), nullable=True),
        sa.Column("initial_trust", sa.SmallInteger(), nullable=True),
        sa.CheckConstraint(
            "role IN ('SUSPECT', 'VICTIM', 'WITNESS')", name=op.f("ck_character_role")
        ),
        sa.CheckConstraint(
            "(is_interrogatable AND initial_pressure IS NOT NULL AND initial_trust IS NOT NULL) OR (NOT is_interrogatable AND initial_pressure IS NULL AND initial_trust IS NULL)",
            name=op.f("ck_character_initial_values"),
        ),
        sa.CheckConstraint(
            "initial_pressure BETWEEN 0 AND 100", name=op.f("ck_character_initial_pressure")
        ),
        sa.CheckConstraint(
            "initial_trust BETWEEN 0 AND 100", name=op.f("ck_character_initial_trust")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_character_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("template_id", "character_id", name=op.f("pk_character")),
    )
    op.create_table(
        "scene",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("scene_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(actions_json) = 'array'", name=op.f("ck_scene_actions_json")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_scene_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("template_id", "scene_id", name=op.f("pk_scene")),
    )
    op.create_table(
        "character_secret",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("secret_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("known_by_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assertion_kind", sa.String(length=16), nullable=False),
        sa.Column("initial_credibility", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "assertion_kind IN ('FACT', 'TESTIMONY')",
            name=op.f("ck_character_secret_assertion_kind"),
        ),
        sa.CheckConstraint(
            "initial_credibility IN ('UNVERIFIED', 'VERIFIED', 'DISPUTED', 'REFUTED')",
            name=op.f("ck_character_secret_initial_credibility"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(known_by_json) = 'array' AND jsonb_array_length(known_by_json) > 0",
            name=op.f("ck_character_secret_known_by_json"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_character_secret_template_id_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_character_secret_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("template_id", "secret_id", name=op.f("pk_character_secret")),
    )
    op.create_index(
        "ix_character_secret_owner",
        "character_secret",
        ["template_id", "character_id", "secret_id"],
        unique=False,
    )
    op.create_table(
        "evidence",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_label", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=8), nullable=False),
        sa.Column("source_scene_id", sa.String(length=64), nullable=True),
        sa.Column("source_character_id", sa.String(length=64), nullable=True),
        sa.Column("initial_credibility", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(source_type = 'SCENE' AND source_scene_id IS NOT NULL AND source_character_id IS NULL) OR (source_type = 'NPC' AND source_character_id IS NOT NULL AND source_scene_id IS NULL)",
            name=op.f("ck_evidence_source"),
        ),
        sa.CheckConstraint(
            "initial_credibility IN ('UNVERIFIED', 'VERIFIED', 'DISPUTED', 'REFUTED')",
            name=op.f("ck_evidence_initial_credibility"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "source_character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_evidence_template_id_source_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "source_scene_id"],
            ["scene.template_id", "scene.scene_id"],
            name=op.f("fk_evidence_template_id_source_scene_id_scene"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_evidence_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("template_id", "evidence_id", name=op.f("pk_evidence")),
    )
    op.create_table(
        "game_session",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("visitor_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("phase", sa.String(length=24), nullable=False),
        sa.Column("active_npc_id", sa.String(length=64), nullable=True),
        sa.Column("deep_unlock_event_id", sa.UUID(), nullable=True),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_schema_version", sa.Integer(), nullable=False),
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(phase = 'FINISHED') = (finished_at IS NOT NULL) AND finished_at >= closed_at",
            name=op.f("ck_game_session_finished_at"),
        ),
        sa.CheckConstraint(
            "(phase = 'INTERROGATION') = (active_npc_id IS NOT NULL)",
            name=op.f("ck_game_session_active_npc"),
        ),
        sa.CheckConstraint(
            "(phase IN ('REVIEW', 'FINISHED')) = (closed_at IS NOT NULL)",
            name=op.f("ck_game_session_closed_at"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(state_json) = 'object'", name=op.f("ck_game_session_state_json")
        ),
        sa.CheckConstraint(
            "phase <> 'DEEP_INVESTIGATION' OR deep_unlock_event_id IS NOT NULL",
            name=op.f("ck_game_session_deep_unlock"),
        ),
        sa.CheckConstraint(
            "phase IN ('INVESTIGATION', 'INTERROGATION', 'DEEP_INVESTIGATION', 'ACCUSATION', 'REVIEW', 'FINISHED')",
            name=op.f("ck_game_session_phase"),
        ),
        sa.CheckConstraint(
            "snapshot_schema_version > 0", name=op.f("ck_game_session_snapshot_schema_version")
        ),
        sa.CheckConstraint("state_version > 0", name=op.f("ck_game_session_state_version")),
        sa.ForeignKeyConstraint(
            ["template_id", "active_npc_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_game_session_template_id_active_npc_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_game_session_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["visitor_id"],
            ["visitor.visitor_id"],
            name=op.f("fk_game_session_visitor_id_visitor"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_game_session")),
        sa.UniqueConstraint(
            "session_id", "template_id", name=op.f("uq_game_session_session_id_template_id")
        ),
        sa.UniqueConstraint(
            "visitor_id", "session_id", name=op.f("uq_game_session_visitor_id_session_id")
        ),
    )
    op.create_index("ix_game_session_template", "game_session", ["template_id"], unique=False)
    op.create_index(
        "ix_game_session_visitor_saved", "game_session", ["visitor_id", "saved_at"], unique=False
    )
    op.create_table(
        "lie_rule",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("lie_rule_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("statements_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("counterevidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "admission_condition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("on_admitted_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(admission_condition_json) = 'object'",
            name=op.f("ck_lie_rule_admission_condition_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(counterevidence_json) = 'object'",
            name=op.f("ck_lie_rule_counterevidence_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(on_admitted_json) = 'object'", name=op.f("ck_lie_rule_on_admitted_json")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(statements_json) = 'object'", name=op.f("ck_lie_rule_statements_json")
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_lie_rule_template_id_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["case_template.template_id"],
            name=op.f("fk_lie_rule_template_id_case_template"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("template_id", "lie_rule_id", name=op.f("pk_lie_rule")),
    )
    op.create_index(
        "ix_lie_rule_character",
        "lie_rule",
        ["template_id", "character_id", "priority", "lie_rule_id"],
        unique=False,
    )
    op.create_table(
        "action_request",
        sa.Column("action_id", sa.UUID(), nullable=False),
        sa.Column("visitor_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("command_type", sa.String(length=40), nullable=False),
        sa.Column("expected_state_version", sa.BigInteger(), nullable=True),
        sa.Column("input_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=False),
        sa.Column("result_state_version", sa.BigInteger(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(input_json) = 'object'", name=op.f("ck_action_request_input_json")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(result_json) = 'object'", name=op.f("ck_action_request_result_json")
        ),
        sa.CheckConstraint(
            "status IN ('COMMITTED', 'NOOP', 'REJECTED')", name=op.f("ck_action_request_status")
        ),
        sa.CheckConstraint(
            "expected_state_version > 0", name=op.f("ck_action_request_expected_state_version")
        ),
        sa.CheckConstraint(
            "http_status BETWEEN 200 AND 599", name=op.f("ck_action_request_http_status")
        ),
        sa.ForeignKeyConstraint(
            ["visitor_id", "session_id"],
            ["game_session.visitor_id", "game_session.session_id"],
            name=op.f("fk_action_request_visitor_id_session_id_game_session"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["visitor_id"],
            ["visitor.visitor_id"],
            name=op.f("fk_action_request_visitor_id_visitor"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("action_id", name=op.f("pk_action_request")),
        sa.UniqueConstraint(
            "session_id", "action_id", name=op.f("uq_action_request_session_id_action_id")
        ),
        sa.UniqueConstraint(
            "visitor_id", "request_id", name=op.f("uq_action_request_visitor_id_request_id")
        ),
    )
    op.create_index(
        "ix_action_request_session_created",
        "action_request",
        ["session_id", "created_at", "action_id"],
        unique=False,
    )
    op.create_table(
        "evidence_dependency",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("dependency_mode", sa.String(length=8), nullable=False),
        sa.Column("required_evidence_id", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "dependency_mode IN ('ALL', 'ANY')", name=op.f("ck_evidence_dependency_dependency_mode")
        ),
        sa.CheckConstraint(
            "evidence_id <> required_evidence_id",
            name=op.f("ck_evidence_dependency_no_self_dependency"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "evidence_id"],
            ["evidence.template_id", "evidence.evidence_id"],
            name=op.f("fk_evidence_dependency_template_id_evidence_id_evidence"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "required_evidence_id"],
            ["evidence.template_id", "evidence.evidence_id"],
            name=op.f("fk_evidence_dependency_template_id_required_evidence_id_evidence"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "template_id",
            "evidence_id",
            "dependency_mode",
            "required_evidence_id",
            name=op.f("pk_evidence_dependency"),
        ),
    )
    op.create_index(
        "ix_evidence_dependency_required",
        "evidence_dependency",
        ["template_id", "required_evidence_id"],
        unique=False,
    )
    op.create_table(
        "npc_state",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("pressure", sa.SmallInteger(), nullable=False),
        sa.Column("trust", sa.SmallInteger(), nullable=False),
        sa.Column("lies_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(lies_json) = 'object'", name=op.f("ck_npc_state_lies_json")
        ),
        sa.CheckConstraint("pressure BETWEEN 0 AND 100", name=op.f("ck_npc_state_pressure")),
        sa.CheckConstraint("trust BETWEEN 0 AND 100", name=op.f("ck_npc_state_trust")),
        sa.ForeignKeyConstraint(
            ["session_id", "template_id"],
            ["game_session.session_id", "game_session.template_id"],
            name=op.f("fk_npc_state_session_id_template_id_game_session"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_npc_state_template_id_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id", "character_id", name=op.f("pk_npc_state")),
    )
    op.create_index(
        "ix_npc_state_definition", "npc_state", ["template_id", "character_id"], unique=False
    )
    op.create_table(
        "accusation",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("action_id", sa.UUID(), nullable=False),
        sa.Column("submitted_state_version", sa.BigInteger(), nullable=False),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("rule_execution_version", sa.String(length=32), nullable=False),
        sa.Column("suspect_character_id", sa.String(length=64), nullable=False),
        sa.Column("weapon_option_id", sa.String(length=64), nullable=False),
        sa.Column("motive_option_id", sa.String(length=64), nullable=False),
        sa.Column(
            "ordered_process_step_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "cited_evidence_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "step_evidence_links_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("grading_input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verdict_category", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("max_score", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("criteria_results_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fixed_review", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(cited_evidence_ids_json) = 'array'",
            name=op.f("ck_accusation_cited_evidence_ids_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(criteria_results_json) = 'array'",
            name=op.f("ck_accusation_criteria_results_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(grading_input_json) = 'object'",
            name=op.f("ck_accusation_grading_input_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(ordered_process_step_ids_json) = 'array' AND jsonb_array_length(ordered_process_step_ids_json) > 0",
            name=op.f("ck_accusation_ordered_process_step_ids_json"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(step_evidence_links_json) = 'array'",
            name=op.f("ck_accusation_step_evidence_links_json"),
        ),
        sa.CheckConstraint(
            "verdict_category IN ('CORRECT', 'PARTIALLY_CORRECT', 'INCORRECT')",
            name=op.f("ck_accusation_verdict_category"),
        ),
        sa.CheckConstraint("score >= 0 AND score <= max_score", name=op.f("ck_accusation_score")),
        sa.CheckConstraint(
            "submitted_state_version > 0", name=op.f("ck_accusation_submitted_state_version")
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "action_id"],
            ["action_request.session_id", "action_request.action_id"],
            name=op.f("fk_accusation_session_id_action_id_action_request"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "template_id"],
            ["game_session.session_id", "game_session.template_id"],
            name=op.f("fk_accusation_session_id_template_id_game_session"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "suspect_character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_accusation_template_id_suspect_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_accusation")),
        sa.UniqueConstraint("action_id", name=op.f("uq_accusation_action_id")),
    )
    op.create_table(
        "game_event_log",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("action_id", sa.UUID(), nullable=False),
        sa.Column("event_seq", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("target_character_id", sa.String(length=64), nullable=True),
        sa.Column("presented_evidence_id", sa.String(length=64), nullable=True),
        sa.Column("state_version_before", sa.BigInteger(), nullable=False),
        sa.Column("state_version_after", sa.BigInteger(), nullable=False),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("rule_execution_version", sa.String(length=32), nullable=False),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outcome_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(event_type = 'PRESENT_EVIDENCE') = (presented_evidence_id IS NOT NULL)",
            name=op.f("ck_game_event_log_presented_evidence"),
        ),
        sa.CheckConstraint(
            "event_type IN ('SESSION_CREATED', 'INVESTIGATE', 'SET_INTERROGATION', 'END_INTERROGATION', 'PRESENT_EVIDENCE', 'OPEN_ACCUSATION', 'CANCEL_ACCUSATION', 'SUBMIT_ACCUSATION', 'FINISH_REVIEW')",
            name=op.f("ck_game_event_log_event_type"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(input_json) = 'object'", name=op.f("ck_game_event_log_input_json")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(outcome_json) = 'object'", name=op.f("ck_game_event_log_outcome_json")
        ),
        sa.CheckConstraint("event_seq > 0", name=op.f("ck_game_event_log_event_seq")),
        sa.CheckConstraint(
            "state_version_after IN (state_version_before, state_version_before + 1)",
            name=op.f("ck_game_event_log_state_version_step"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "action_id"],
            ["action_request.session_id", "action_request.action_id"],
            name=op.f("fk_game_event_log_session_id_action_id_action_request"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "template_id"],
            ["game_session.session_id", "game_session.template_id"],
            name=op.f("fk_game_event_log_session_id_template_id_game_session"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "presented_evidence_id"],
            ["evidence.template_id", "evidence.evidence_id"],
            name=op.f("fk_game_event_log_template_id_presented_evidence_id_evidence"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "target_character_id"],
            ["character.template_id", "character.character_id"],
            name=op.f("fk_game_event_log_template_id_target_character_id_character"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_game_event_log")),
        sa.UniqueConstraint(
            "session_id", "action_id", name=op.f("uq_game_event_log_session_id_action_id")
        ),
        sa.UniqueConstraint(
            "session_id", "event_id", name=op.f("uq_game_event_log_session_id_event_id")
        ),
        sa.UniqueConstraint(
            "session_id", "event_seq", name=op.f("uq_game_event_log_session_id_event_seq")
        ),
    )
    op.create_index(
        "ix_game_event_log_presented",
        "game_event_log",
        ["session_id", "target_character_id", "event_type", "presented_evidence_id"],
        unique=False,
    )
    op.create_table(
        "player_evidence",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acquired_event_id", sa.UUID(), nullable=False),
        sa.Column("credibility", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "credibility IN ('UNVERIFIED', 'VERIFIED', 'DISPUTED', 'REFUTED')",
            name=op.f("ck_player_evidence_credibility"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "acquired_event_id"],
            ["game_event_log.session_id", "game_event_log.event_id"],
            name=op.f("fk_player_evidence_session_id_acquired_event_id_game_event_log"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "template_id"],
            ["game_session.session_id", "game_session.template_id"],
            name=op.f("fk_player_evidence_session_id_template_id_game_session"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "evidence_id"],
            ["evidence.template_id", "evidence.evidence_id"],
            name=op.f("fk_player_evidence_template_id_evidence_id_evidence"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id", "evidence_id", name=op.f("pk_player_evidence")),
    )
    op.create_index(
        "ix_player_evidence_acquired",
        "player_evidence",
        ["session_id", "acquired_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_evidence_definition",
        "player_evidence",
        ["template_id", "evidence_id"],
        unique=False,
    )
    op.create_table(
        "rule_effect",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("effect_key", sa.String(length=384), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "event_id"],
            ["game_event_log.session_id", "game_event_log.event_id"],
            name=op.f("fk_rule_effect_session_id_event_id_game_event_log"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_session.session_id"],
            name=op.f("fk_rule_effect_session_id_game_session"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id", "effect_key", name=op.f("pk_rule_effect")),
    )
    op.create_index("ix_rule_effect_event", "rule_effect", ["session_id", "event_id"], unique=False)
    # Circular references are added after both sides exist.
    op.create_foreign_key(
        op.f("fk_visitor_visitor_id_current_session_id_game_session"),
        "visitor",
        "game_session",
        ["visitor_id", "current_session_id"],
        ["visitor_id", "session_id"],
        onupdate="RESTRICT",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_game_session_session_id_deep_unlock_event_id_game_event_log"),
        "game_session",
        "game_event_log",
        ["session_id", "deep_unlock_event_id"],
        ["session_id", "event_id"],
        onupdate="RESTRICT",
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_game_session_session_id_deep_unlock_event_id_game_event_log"),
        "game_session",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_visitor_visitor_id_current_session_id_game_session"),
        "visitor",
        type_="foreignkey",
    )
    op.drop_index("ix_rule_effect_event", table_name="rule_effect")
    op.drop_table("rule_effect")
    op.drop_index("ix_player_evidence_definition", table_name="player_evidence")
    op.drop_index("ix_player_evidence_acquired", table_name="player_evidence")
    op.drop_table("player_evidence")
    op.drop_index("ix_game_event_log_presented", table_name="game_event_log")
    op.drop_table("game_event_log")
    op.drop_table("accusation")
    op.drop_index("ix_npc_state_definition", table_name="npc_state")
    op.drop_table("npc_state")
    op.drop_index("ix_evidence_dependency_required", table_name="evidence_dependency")
    op.drop_table("evidence_dependency")
    op.drop_index("ix_action_request_session_created", table_name="action_request")
    op.drop_table("action_request")
    op.drop_index("ix_lie_rule_character", table_name="lie_rule")
    op.drop_table("lie_rule")
    op.drop_index("ix_game_session_visitor_saved", table_name="game_session")
    op.drop_index("ix_game_session_template", table_name="game_session")
    op.drop_table("game_session")
    op.drop_table("evidence")
    op.drop_index("ix_character_secret_owner", table_name="character_secret")
    op.drop_table("character_secret")
    op.drop_table("scene")
    op.drop_table("character")
    op.drop_table("visitor")
    op.drop_index("ix_case_template_status_published_at", table_name="case_template")
    op.drop_table("case_template")
