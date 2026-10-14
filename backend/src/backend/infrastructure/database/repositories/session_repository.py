"""Save/Load for one game: assembles a GameState from runtime tables and writes back the diff.

Every write path runs inside the caller's transaction after locking the game_session row.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.domain.models import (
    Accusation,
    Case,
    CriterionResult,
    GameState,
    LieStage,
    NPCState,
    Phase,
    StepEvidenceLink,
    Verdict,
)
from backend.domain.rules import RULE_EXECUTION_VERSION
from backend.infrastructure.database.models import Accusation as AccusationRow
from backend.infrastructure.database.models import (
    ActionRequest,
    CaseTemplate,
    GameEventLog,
    GameSession,
    NpcState,
    PlayerEvidence,
    RuleEffect,
    Visitor,
)

SNAPSHOT_SCHEMA_VERSION = 1
CATEGORY_CODES = {"正确": "CORRECT", "部分正确": "PARTIALLY_CORRECT", "错误": "INCORRECT"}
CATEGORY_LABELS = {code: label for label, code in CATEGORY_CODES.items()}


class SaveIntegrityError(RuntimeError):
    """Stored records are inconsistent; never guess a repair or reveal the truth."""


@dataclass(frozen=True)
class SavedGame:
    session_id: uuid.UUID
    visitor_id: uuid.UUID
    template_id: uuid.UUID
    state: GameState
    created_at: datetime
    saved_at: datetime
    closed_at: datetime | None
    finished_at: datetime | None
    evidence_discovered_at: dict[str, datetime]
    knowledge_discovered_at: dict[str, datetime]
    submitted_at: datetime | None = None
    submitted_state_version: int | None = None
    fixed_review: str | None = None


@dataclass(frozen=True)
class EventInput:
    action: ActionRequest
    event_type: str
    input_json: dict
    target_character_id: str | None = None
    presented_evidence_id: str | None = None


def comparable(state: GameState) -> GameState:
    """Business state without bookkeeping fields, for deciding whether anything changed."""
    return GameState(
        npc=state.npc,
        phase=state.phase,
        active_npc_id=state.active_npc_id,
        evidence_ids=state.evidence_ids,
        completed_actions=state.completed_actions,
        disclosed_knowledge=state.disclosed_knowledge,
        consumed_effects=state.consumed_effects,
        deep_unlocked=state.deep_unlocked,
        verdict=state.verdict,
    )


def fixed_review(case: Case, verdict: Verdict) -> str:
    lines = [f"结案：{verdict.category} · {verdict.score}/100"]
    lines.extend(f"{c.label} {c.points}/{c.maximum}：{c.explanation}" for c in verdict.criteria)
    lines.extend(["案情复盘", case.truth.explanation])
    lines.append("复盘不会补发遗漏证据，证词与调查记录已经冻结。")
    return "\n".join(lines)


class SessionRepository:
    def __init__(self, db: Session):
        self._db = db

    # Visitors and idempotent requests

    def find_visitor(self, token_hash: str) -> Visitor | None:
        return self._db.scalar(select(Visitor).where(Visitor.token_hash == token_hash))

    def lock_visitor(self, visitor_id: uuid.UUID) -> Visitor:
        return self._db.scalars(
            select(Visitor).where(Visitor.visitor_id == visitor_id).with_for_update()
        ).one()

    def add_visitor(self, token_hash: str, now: datetime) -> Visitor:
        visitor = Visitor(
            visitor_id=uuid.uuid4(), token_hash=token_hash, created_at=now, last_seen_at=now
        )
        self._db.add(visitor)
        self._db.flush()
        return visitor

    def find_request(self, visitor_id: uuid.UUID, request_id: uuid.UUID) -> ActionRequest | None:
        return self._db.scalar(
            select(ActionRequest).where(
                ActionRequest.visitor_id == visitor_id, ActionRequest.request_id == request_id
            )
        )

    def add_request(self, request: ActionRequest) -> ActionRequest:
        self._db.add(request)
        self._db.flush()
        return request

    # Sessions

    def get_session(
        self, visitor_id: uuid.UUID, session_id: uuid.UUID, *, lock: bool = False
    ) -> GameSession | None:
        query = select(GameSession).where(
            GameSession.session_id == session_id, GameSession.visitor_id == visitor_id
        )
        return self._db.scalar(query.with_for_update() if lock else query)

    def template(self, row: GameSession) -> CaseTemplate:
        return self._db.get_one(CaseTemplate, row.template_id)

    def create(
        self, visitor: Visitor, template: CaseTemplate, case: Case, action: ActionRequest, now
    ) -> GameSession:
        """Insert a new independent game with its initial event and NPC rows, then switch entry."""
        row = GameSession(
            session_id=uuid.uuid4(),
            visitor_id=visitor.visitor_id,
            template_id=template.template_id,
            phase=Phase.INVESTIGATION.value,
            state_version=1,
            snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
            state_json={},
            created_at=now,
            saved_at=now,
        )
        self._db.add(row)
        self._db.flush()
        action.session_id = row.session_id
        self.add_request(action)
        event = self._add_event(
            row,
            case,
            EventInput(action, "SESSION_CREATED", {"case_id": case.case_id}),
            before=0,
            after=1,
            outcome={"phase_after": row.phase},
            now=now,
        )
        row.state_json = {
            "scene_progress": {
                case.scene.id: {
                    "visited": False,
                    "unlock_event_id": str(event.event_id),
                    "completed_action_ids": [],
                }
            },
            "known_information": {
                "KNOWLEDGE": {
                    k.id: self._known(event, now)
                    for k in case.knowledge
                    if k.disclosure == "PUBLIC"
                }
            },
            "accusation_draft": None,
        }
        self._db.add(
            NpcState(
                session_id=row.session_id,
                template_id=row.template_id,
                character_id=case.npc.id,
                pressure=case.npc.initial_pressure,
                trust=case.npc.initial_trust,
                irrelevant_streak=0,
                lies_json={case.lie.id: self._lie_progress(LieStage.UNBROKEN, [], None, None)},
                updated_at=now,
            )
        )
        visitor.current_session_id = row.session_id
        self._db.flush()
        return row

    def load(self, row: GameSession, case: Case) -> SavedGame:
        if row.snapshot_schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise SaveIntegrityError("存档结构版本不受支持。")
        npc_rows = list(
            self._db.scalars(select(NpcState).where(NpcState.session_id == row.session_id))
        )
        if [n.character_id for n in npc_rows] != [case.npc.id]:
            raise SaveIntegrityError("NPC 状态缺失或不属于本案件。")
        npc_row = npc_rows[0]
        progress = npc_row.lies_json.get(case.lie.id)
        if progress is None or set(npc_row.lies_json) != {case.lie.id}:
            raise SaveIntegrityError("谎言进度与案件定义不一致。")
        presented = frozenset(
            self._db.scalars(
                select(GameEventLog.presented_evidence_id).where(
                    GameEventLog.session_id == row.session_id,
                    GameEventLog.event_type == "PRESENT_EVIDENCE",
                    GameEventLog.target_character_id == case.npc.id,
                )
            )
        )
        held = list(
            self._db.scalars(
                select(PlayerEvidence).where(PlayerEvidence.session_id == row.session_id)
            )
        )
        effects = frozenset(
            self._db.scalars(
                select(RuleEffect.effect_key).where(RuleEffect.session_id == row.session_id)
            )
        )
        scene = row.state_json["scene_progress"][case.scene.id]
        known = row.state_json["known_information"]["KNOWLEDGE"]
        private = {k.id for k in case.knowledge if k.disclosure != "PUBLIC"}
        accusation = self._db.get(AccusationRow, row.session_id)
        phase = Phase(row.phase)
        if (accusation is not None) != (phase in {Phase.REVIEW, Phase.FINISHED}):
            raise SaveIntegrityError("结案阶段与正式指控记录不一致。")
        state = GameState(
            npc=NPCState(
                pressure=npc_row.pressure,
                trust=npc_row.trust,
                lie_stage=LieStage(progress["stage"]),
                presented=presented,
                irrelevant_streak=npc_row.irrelevant_streak,
            ),
            phase=phase,
            active_npc_id=row.active_npc_id,
            evidence_ids=frozenset(e.evidence_id for e in held),
            completed_actions=frozenset(scene["completed_action_ids"]),
            disclosed_knowledge=frozenset(k for k in known if k in private),
            consumed_effects=effects,
            deep_unlocked=row.deep_unlock_event_id is not None,
            verdict=self._verdict(accusation) if accusation else None,
            version=row.state_version,
        )
        return SavedGame(
            session_id=row.session_id,
            visitor_id=row.visitor_id,
            template_id=row.template_id,
            state=state,
            created_at=row.created_at,
            saved_at=row.saved_at,
            closed_at=row.closed_at,
            finished_at=row.finished_at,
            evidence_discovered_at={e.evidence_id: e.discovered_at for e in held},
            knowledge_discovered_at={
                k: datetime.fromisoformat(v["discovered_at"]) for k, v in known.items()
            },
            submitted_at=accusation.submitted_at if accusation else None,
            submitted_state_version=accusation.submitted_state_version if accusation else None,
            fixed_review=accusation.fixed_review if accusation else None,
        )

    def save(
        self,
        row: GameSession,
        case: Case,
        before: GameState,
        after: GameState,
        event_input: EventInput,
        outcome: dict,
        now: datetime,
    ) -> GameEventLog:
        """Persist one state-changing action. The caller has verified that state changed."""
        version = row.state_version
        event = self._add_event(row, case, event_input, version, version + 1, outcome, now)

        for evidence_id in sorted(after.evidence_ids - before.evidence_ids):
            definition = next(e for e in case.evidence if e.id == evidence_id)
            self._db.add(
                PlayerEvidence(
                    session_id=row.session_id,
                    template_id=row.template_id,
                    evidence_id=evidence_id,
                    discovered_at=now,
                    acquired_event_id=event.event_id,
                    credibility=definition.credibility,
                    updated_at=now,
                )
            )
        self._db.flush()
        self._add_effects(row, sorted(after.consumed_effects - before.consumed_effects), event)

        if after.npc != before.npc:
            npc_row = self._db.get_one(NpcState, (row.session_id, case.npc.id))
            old = npc_row.lies_json[case.lie.id]
            stage = after.npc.lie_stage
            refs = set(case.lie.counterevidence.all_of) | set(case.lie.counterevidence.any_of)
            verified = {e.id for e in case.evidence if e.credibility == "VERIFIED"}
            npc_row.pressure = after.npc.pressure
            npc_row.trust = after.npc.trust
            npc_row.irrelevant_streak = after.npc.irrelevant_streak
            npc_row.lies_json = {
                case.lie.id: self._lie_progress(
                    stage,
                    sorted(after.npc.presented & refs & verified),
                    old["broken_event_id"]
                    or (str(event.event_id) if stage != LieStage.UNBROKEN else None),
                    old["admitted_event_id"]
                    or (str(event.event_id) if stage == LieStage.ADMITTED else None),
                )
            }
            npc_row.updated_at = now

        state_json = row.state_json
        scene = dict(state_json["scene_progress"][case.scene.id])
        scene["completed_action_ids"] = sorted(after.completed_actions)
        scene["visited"] = bool(after.completed_actions)
        known = dict(state_json["known_information"]["KNOWLEDGE"])
        for knowledge_id in sorted(after.disclosed_knowledge - before.disclosed_knowledge):
            known[knowledge_id] = self._known(event, now)
        # Assign a new object so SQLAlchemy writes the JSON column.
        row.state_json = {
            **state_json,
            "scene_progress": {**state_json["scene_progress"], case.scene.id: scene},
            "known_information": {**state_json["known_information"], "KNOWLEDGE": known},
        }

        row.phase = after.phase.value
        row.active_npc_id = after.active_npc_id
        if after.deep_unlocked and row.deep_unlock_event_id is None:
            row.deep_unlock_event_id = event.event_id
        if after.verdict is not None and before.verdict is None:
            row.closed_at = now
            self._add_accusation(row, case, after.verdict, event_input.action, now)
        if after.phase == Phase.FINISHED and row.finished_at is None:
            row.finished_at = now
        row.state_version = version + 1
        row.saved_at = now
        self._db.flush()
        return event

    # Internals

    @staticmethod
    def _known(event: GameEventLog, now: datetime) -> dict:
        return {
            "discovered_at": now.isoformat(),
            "source_event_ids": [str(event.event_id)],
            "credibility": "UNVERIFIED",
        }

    @staticmethod
    def _lie_progress(stage: LieStage, matched: list[str], broken, admitted) -> dict:
        return {
            "stage": stage.value,
            "matched_evidence_ids": matched,
            "broken_event_id": broken,
            "admitted_event_id": admitted,
        }

    def _add_event(
        self,
        row: GameSession,
        case: Case,
        event_input: EventInput,
        before: int,
        after: int,
        outcome: dict,
        now: datetime,
    ) -> GameEventLog:
        last = self._db.scalar(
            select(func.max(GameEventLog.event_seq)).where(
                GameEventLog.session_id == row.session_id
            )
        )
        event = GameEventLog(
            event_id=uuid.uuid4(),
            session_id=row.session_id,
            template_id=row.template_id,
            action_id=event_input.action.action_id,
            event_seq=(last or 0) + 1,
            event_type=event_input.event_type,
            target_character_id=event_input.target_character_id,
            presented_evidence_id=event_input.presented_evidence_id,
            state_version_before=before,
            state_version_after=after,
            rules_version=case.rules_version,
            rule_execution_version=RULE_EXECUTION_VERSION,
            input_json=event_input.input_json,
            outcome_json=outcome,
            created_at=now,
        )
        self._db.add(event)
        self._db.flush()
        return event

    def _add_effects(self, row: GameSession, keys: list[str], event: GameEventLog) -> None:
        for key in keys:
            self._db.add(
                RuleEffect(session_id=row.session_id, effect_key=key, event_id=event.event_id)
            )
        self._db.flush()

    def _add_accusation(
        self,
        row: GameSession,
        case: Case,
        verdict: Verdict,
        action: ActionRequest,
        now: datetime,
    ) -> None:
        accusation = verdict.accusation
        credibility = {e.id: e.credibility for e in case.evidence}
        self._db.add(
            AccusationRow(
                session_id=row.session_id,
                template_id=row.template_id,
                action_id=action.action_id,
                submitted_state_version=row.state_version,  # still the pre-submit version
                rules_version=verdict.rules_version,
                rule_execution_version=RULE_EXECUTION_VERSION,
                suspect_character_id=accusation.culprit,
                weapon_option_id=accusation.weapon,
                motive_option_id=accusation.motive,
                ordered_process_step_ids_json=list(accusation.steps),
                cited_evidence_ids_json=list(accusation.cited_evidence_ids),
                step_evidence_links_json=[
                    link.model_dump(mode="json") for link in accusation.evidence_links
                ],
                explanation=accusation.explanation,
                grading_input_json={
                    "case_version": verdict.case_version,
                    "held_evidence": {
                        evidence_id: credibility[evidence_id]
                        for evidence_id in sorted(verdict.evidence_snapshot)
                    },
                },
                verdict_category=CATEGORY_CODES[verdict.category],
                score=Decimal(verdict.score),
                max_score=Decimal(sum(c.maximum for c in verdict.criteria)),
                criteria_results_json=[
                    {
                        "criterion_id": c.id,
                        "label": c.label,
                        "score": c.points,
                        "max_score": c.maximum,
                        "explanation": c.explanation,
                    }
                    for c in verdict.criteria
                ],
                fixed_review=fixed_review(case, verdict),
                submitted_at=now,
            )
        )
        self._db.flush()

    @staticmethod
    def _verdict(row: AccusationRow) -> Verdict:
        if row.rule_execution_version != RULE_EXECUTION_VERSION:
            raise SaveIntegrityError("正式指控的规则执行版本不受支持。")
        return Verdict(
            category=CATEGORY_LABELS[row.verdict_category],
            score=int(row.score),
            criteria=tuple(
                CriterionResult(
                    c["criterion_id"], c["label"], c["score"], c["max_score"], c["explanation"]
                )
                for c in row.criteria_results_json
            ),
            accusation=Accusation(
                culprit=row.suspect_character_id,
                weapon=row.weapon_option_id,
                motive=row.motive_option_id,
                steps=tuple(row.ordered_process_step_ids_json),
                cited_evidence_ids=tuple(row.cited_evidence_ids_json),
                evidence_links=tuple(
                    StepEvidenceLink(**link) for link in row.step_evidence_links_json
                ),
                explanation=row.explanation,
            ),
            evidence_snapshot=frozenset(row.grading_input_json["held_evidence"]),
            case_version=row.grading_input_json["case_version"],
            rules_version=row.rules_version,
        )
