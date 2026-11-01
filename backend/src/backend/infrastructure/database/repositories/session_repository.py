"""Save/Load for one game: assembles a GameState from runtime tables and writes back the diff.

Every write path runs inside the caller's transaction after locking the game_session row.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.domain.evidence import fixed_review
from backend.domain.models import (
    Accusation,
    AccusationDraft,
    Case,
    CriterionResult,
    GameState,
    LieStage,
    NPCState,
    Phase,
    StepEvidenceLink,
    Verdict,
)
from backend.domain.rules import FIXED_EXPLANATIONS, RULE_EXECUTION_VERSION
from backend.infrastructure.database.models import Accusation as AccusationRow
from backend.infrastructure.database.models import (
    ActionRequest,
    CaseTemplate,
    Conversation,
    ConversationMessage,
    GameEventLog,
    GameSession,
    LlmAttempt,
    NpcState,
    PlayerEvidence,
    RuleEffect,
    Visitor,
)

SNAPSHOT_SCHEMA_VERSION = 2
CATEGORY_CODES = {"正确": "CORRECT", "部分正确": "PARTIALLY_CORRECT", "错误": "INCORRECT"}
CATEGORY_LABELS = {code: label for label, code in CATEGORY_CODES.items()}
EMPTY_DRAFT = {
    "suspect_character_id": None,
    "weapon_option_id": None,
    "motive_option_id": None,
    "ordered_process_step_ids": [],
    "cited_evidence_ids": [],
    "step_evidence_links": [],
    "explanation": "",
}


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


@dataclass(frozen=True)
class ConversationInput:
    action: ActionRequest
    character_id: str
    interaction_type: str
    source_state_version: int
    fixed_reply: str
    player_message: str
    npc_message: str
    now: datetime


def comparable(state: GameState) -> GameState:
    """Business state without bookkeeping fields, for deciding whether anything changed."""
    return GameState(
        npcs=state.npcs,
        phase=state.phase,
        active_npc_id=state.active_npc_id,
        evidence_ids=state.evidence_ids,
        completed_actions=state.completed_actions,
        disclosed_knowledge=state.disclosed_knowledge,
        consumed_effects=state.consumed_effects,
        deep_unlocked=state.deep_unlocked,
        draft=state.draft,
        verdict=state.verdict,
    )


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
        """Insert a new independent game with its initial events and NPC rows, then switch entry."""
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
                scene.id: {"visited": False, "completed_action_ids": []} for scene in case.scenes
            },
            "scene_unlock_event_ids": {scene.id: str(event.event_id) for scene in case.scenes},
            "known_information": {
                "KNOWLEDGE": {
                    k.id: self._known(event, now)
                    for k in case.knowledge
                    if k.disclosure == "PUBLIC"
                }
            },
            "accusation_draft": None,
        }
        for character in case.characters:
            if not character.interrogatable:
                continue
            self._db.add(
                NpcState(
                    session_id=row.session_id,
                    template_id=row.template_id,
                    character_id=character.id,
                    pressure=character.initial_pressure,
                    trust=character.initial_trust,
                    irrelevant_streak=0,
                    lies_json={
                        lie_id: self._lie_progress(LieStage.UNBROKEN, [], None, None)
                        for chain in (c for c in case.lie_chains if c.npc_id == character.id)
                        for lie_id in chain.lie_ids
                    },
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
            self._db.scalars(
                select(NpcState)
                .where(NpcState.session_id == row.session_id)
                .order_by(NpcState.character_id)
            )
        )
        wanted = sorted(c.id for c in case.characters if c.interrogatable)
        if sorted(n.character_id for n in npc_rows) != wanted:
            raise SaveIntegrityError("NPC 状态缺失或不属于本案件。")
        presented: dict[str, frozenset[str]] = {}
        for npc_row in npc_rows:
            presented[npc_row.character_id] = frozenset(
                self._db.scalars(
                    select(GameEventLog.presented_evidence_id).where(
                        GameEventLog.session_id == row.session_id,
                        GameEventLog.event_type == "PRESENT_EVIDENCE",
                        GameEventLog.target_character_id == npc_row.character_id,
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
        progress = row.state_json["scene_progress"]
        known = row.state_json["known_information"]["KNOWLEDGE"]
        private = {k.id for k in case.knowledge if k.disclosure != "PUBLIC"}
        accusation = self._db.get(AccusationRow, row.session_id)
        phase = Phase(row.phase)
        if (accusation is not None) != (phase in {Phase.REVIEW, Phase.FINISHED}):
            raise SaveIntegrityError("结案阶段与正式指控记录不一致。")
        completed: set[str] = set()
        for scene in case.scenes:
            completed |= set(progress.get(scene.id, {}).get("completed_action_ids", []))
        npcs: dict[str, NPCState] = {}
        for npc_row in npc_rows:
            stages = {
                lie_id: LieStage(entry["stage"]) for lie_id, entry in npc_row.lies_json.items()
            }
            npcs[npc_row.character_id] = NPCState(
                pressure=npc_row.pressure,
                trust=npc_row.trust,
                lies=stages,
                presented=presented[npc_row.character_id],
                irrelevant_streak=npc_row.irrelevant_streak,
            )
        draft_json = row.state_json.get("accusation_draft")
        state = GameState(
            npcs=npcs,
            phase=phase,
            active_npc_id=row.active_npc_id,
            evidence_ids=frozenset(e.evidence_id for e in held),
            completed_actions=frozenset(completed),
            disclosed_knowledge=frozenset(k for k in known if k in private),
            consumed_effects=effects,
            deep_unlocked=row.deep_unlock_event_id is not None,
            draft=AccusationDraft.model_validate(draft_json, strict=False) if draft_json else None,
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

        for character in case.characters:
            if not character.interrogatable:
                continue
            after_npc = after.npcs[character.id]
            if after_npc == before.npcs.get(character.id):
                continue
            npc_row = self._db.get_one(NpcState, (row.session_id, character.id))
            lies_json = dict(npc_row.lies_json)
            for chain in (c for c in case.lie_chains if c.npc_id == character.id):
                for lie_id in chain.lie_ids:
                    old = lies_json.get(lie_id) or self._lie_progress(
                        LieStage.UNBROKEN, [], None, None
                    )
                    stage = after_npc.lies[lie_id]
                    lie = next(item for item in case.lies if item.id == lie_id)
                    refs = (
                        set(lie.counterevidence.all_of)
                        | set(lie.counterevidence.any_of)
                        | set(lie.admission_presented.all_of)
                        | set(lie.admission_presented.any_of)
                    )
                    verified = {e.id for e in case.evidence if e.credibility == "VERIFIED"}
                    matched = sorted(after_npc.presented & refs & verified)
                    lies_json[lie_id] = self._lie_progress(
                        stage,
                        matched,
                        old["broken_event_id"]
                        or (str(event.event_id) if stage != LieStage.UNBROKEN else None),
                        old["admitted_event_id"]
                        or (str(event.event_id) if stage == LieStage.ADMITTED else None),
                    )
            npc_row.pressure = after_npc.pressure
            npc_row.trust = after_npc.trust
            npc_row.irrelevant_streak = after_npc.irrelevant_streak
            npc_row.lies_json = lies_json
            npc_row.updated_at = now

        state_json = row.state_json
        progress = dict(state_json["scene_progress"])
        for scene in case.scenes:
            actions = {a.id for a in scene.actions}
            done = sorted(after.completed_actions & actions)
            entry = dict(progress.get(scene.id, {"visited": False, "completed_action_ids": []}))
            entry["completed_action_ids"] = done
            entry["visited"] = bool(done)
            progress[scene.id] = entry
        known = dict(state_json["known_information"]["KNOWLEDGE"])
        for knowledge_id in sorted(after.disclosed_knowledge - before.disclosed_knowledge):
            known[knowledge_id] = self._known(event, now)
        draft_json = after.draft.model_dump(mode="json") if after.draft else None
        # Assign a new object so SQLAlchemy writes the JSON column.
        row.state_json = {
            **state_json,
            "scene_progress": progress,
            "known_information": {**state_json["known_information"], "KNOWLEDGE": known},
            "accusation_draft": draft_json,
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

    # Conversation rounds

    def add_conversation(
        self,
        row: GameSession,
        case: Case,
        input: ConversationInput,
        *,
        fallback_reason: str = "GENERATION_DISABLED",
        pending_deadline: datetime | None = None,
    ) -> Conversation:
        """One interaction round. With a pending deadline it starts PREPARING with only
        the player message; otherwise it is terminal in the fixed mode."""
        last = self._db.scalar(
            select(func.max(Conversation.conversation_seq)).where(
                Conversation.session_id == row.session_id
            )
        )
        pending = pending_deadline is not None
        conversation = Conversation(
            conversation_id=uuid.uuid4(),
            session_id=row.session_id,
            template_id=row.template_id,
            action_id=input.action.action_id,
            conversation_seq=(last or 0) + 1,
            role="NPC",
            character_id=input.character_id,
            purpose_key=None,
            source_state_version=input.source_state_version,
            response_plan_json={},
            fixed_reply=input.fixed_reply,
            generation_status="PREPARING" if pending else "FALLBACK",
            active_attempt_id=None,
            generation_deadline_at=pending_deadline,
            fallback_reason=None if pending else fallback_reason,
            created_at=input.now,
            completed_at=None if pending else input.now,
        )
        self._db.add(conversation)
        self._db.flush()
        messages = [("PLAYER", "PLAYER", input.player_message)]
        if not pending:
            messages.append(("NPC", "FIXED", input.npc_message))
        for sequence, (speaker, origin, content) in enumerate(messages, start=1):
            self._db.add(
                ConversationMessage(
                    message_id=uuid.uuid4(),
                    session_id=row.session_id,
                    conversation_id=conversation.conversation_id,
                    sequence_no=sequence,
                    speaker=speaker,
                    content=content,
                    origin=origin,
                    validity="VALID",
                    created_at=input.now,
                    updated_at=input.now,
                )
            )
        self._db.flush()
        return conversation

    def pending_round(self, session_id: uuid.UUID) -> Conversation | None:
        """The at-most-one unexpired PREPARING/GENERATING round of this session."""
        return self._db.scalar(
            select(Conversation)
            .where(
                Conversation.session_id == session_id,
                Conversation.generation_status.in_(("PREPARING", "GENERATING")),
                Conversation.generation_deadline_at > datetime.now(UTC),
            )
            .order_by(Conversation.created_at)
        )

    def pending_summaries(self, session_id: uuid.UUID) -> list[dict]:
        rows = list(
            self._db.scalars(
                select(Conversation).where(
                    Conversation.session_id == session_id,
                    Conversation.generation_status.in_(("PREPARING", "GENERATING")),
                )
            )
        )
        now = datetime.now(UTC)
        return [
            {
                "conversation_id": str(row.conversation_id),
                "npc_id": row.character_id,
                "generation_status": row.generation_status,
                "generation_deadline_at": row.generation_deadline_at.isoformat().replace(
                    "+00:00", "Z"
                )
                if row.generation_deadline_at
                else None,
                "deadline_exceeded": bool(
                    row.generation_deadline_at and row.generation_deadline_at <= now
                ),
            }
            for row in rows
        ]

    def invalidate_pending(self, session_id: uuid.UUID, now: datetime) -> None:
        """Switching, leaving, accusation or restart: pending rounds become STALE in the
        same business transaction; late results may only settle usage later."""
        rounds = list(
            self._db.scalars(
                select(Conversation).where(
                    Conversation.session_id == session_id,
                    Conversation.generation_status.in_(("PREPARING", "GENERATING")),
                )
            )
        )
        for conversation in rounds:
            self._stale(conversation, now)

    def expire_pending(self, session_id: uuid.UUID, now: datetime) -> None:
        """Before accepting a new command: clear expired placeholders. Never resend."""
        rounds = list(
            self._db.scalars(
                select(Conversation).where(
                    Conversation.session_id == session_id,
                    Conversation.generation_status.in_(("PREPARING", "GENERATING")),
                    Conversation.generation_deadline_at <= now,
                )
            )
        )
        for conversation in rounds:
            attempt = (
                self._db.get_one(LlmAttempt, conversation.active_attempt_id)
                if conversation.active_attempt_id
                else None
            )
            if attempt is not None and attempt.status == "RESERVED":
                attempt.status = "CANCELLED_NOT_SENT"
                attempt.usage_status = "NOT_SENT"
                attempt.finished_at = now
            elif attempt is not None and attempt.status == "DISPATCHING":
                # It may have reached the provider; the reservation stays reserved.
                attempt.status = "UNKNOWN"
                attempt.usage_status = "UNKNOWN"
                attempt.finished_at = now
            conversation.generation_status = "FALLBACK"
            conversation.fallback_reason = "GENERATION_INTERRUPTED"
            conversation.completed_at = now
            self._write_fixed_reply(
                db=self._db, conversation=conversation, attempt_id=None, now=now
            )

    def _stale(self, conversation: Conversation, now: datetime) -> None:
        conversation.generation_status = "STALE"
        conversation.fallback_reason = "CONTEXT_CHANGED"
        conversation.completed_at = now
        self._write_fixed_reply(db=self._db, conversation=conversation, attempt_id=None, now=now)

    def _write_fixed_reply(
        self, db: Session, conversation: Conversation, attempt_id: uuid.UUID | None, now: datetime
    ) -> None:
        existing = self._db.scalar(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.conversation_id,
                ConversationMessage.sequence_no == 2,
            )
        )
        if existing is not None:
            existing.content = conversation.fixed_reply
            existing.origin = "FIXED"
            existing.attempt_id = attempt_id
            existing.updated_at = now
            return
        self._db.add(
            ConversationMessage(
                message_id=uuid.uuid4(),
                session_id=conversation.session_id,
                conversation_id=conversation.conversation_id,
                sequence_no=2,
                speaker="NPC",
                content=conversation.fixed_reply,
                origin="FIXED",
                validity="VALID",
                attempt_id=attempt_id,
                created_at=now,
                updated_at=now,
            )
        )
        self._db.flush()

    def history_rounds(self, session_id: uuid.UUID, character_id: str, before_seq: int) -> list:
        """Previous terminal rounds of this person, oldest first, for the model context."""
        rows = list(
            self._db.scalars(
                select(Conversation)
                .where(
                    Conversation.session_id == session_id,
                    Conversation.character_id == character_id,
                    Conversation.conversation_seq < before_seq,
                    Conversation.generation_status.in_(("COMPLETED", "FALLBACK")),
                )
                .order_by(Conversation.conversation_seq.desc())
                .limit(12)
            )
        )
        rounds = []
        for conversation in reversed(rows):
            messages = list(
                self._db.scalars(
                    select(ConversationMessage)
                    .where(ConversationMessage.conversation_id == conversation.conversation_id)
                    .order_by(ConversationMessage.sequence_no)
                )
            )
            player_text = next((m.content for m in messages if m.sequence_no == 1), "")
            npc_text = next((m.content for m in messages if m.sequence_no == 2), "")
            from backend.application.memory import HistoryRound

            rounds.append(
                HistoryRound(
                    conversation_seq=conversation.conversation_seq,
                    npc_id=conversation.character_id or "",
                    player_text=player_text,
                    npc_text=npc_text,
                    status=conversation.generation_status,
                )
            )
        return rounds

    def conversation_attempts(self, conversation_id: uuid.UUID) -> list[LlmAttempt]:
        return list(
            self._db.scalars(
                select(LlmAttempt)
                .where(LlmAttempt.conversation_id == conversation_id)
                .order_by(LlmAttempt.attempt_no)
            )
        )

    def has_other_pending(self, session_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        return (
            self._db.scalar(
                select(Conversation.conversation_id).where(
                    Conversation.session_id == session_id,
                    Conversation.conversation_id != conversation_id,
                    Conversation.generation_status.in_(("PREPARING", "GENERATING")),
                )
            )
            is not None
        )

    def conversation_view(
        self,
        conversation: Conversation,
        request: ActionRequest,
        state: GameState | None = None,
        is_current: bool = True,
    ) -> dict:
        messages = list(
            self._db.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation.conversation_id)
                .order_by(ConversationMessage.sequence_no)
            )
        )
        interaction = (
            "EVIDENCE_PRESENTATION" if request.command_type == "PRESENT_EVIDENCE" else "CHAT"
        )
        now = datetime.now(UTC)
        pending = conversation.generation_status in ("PREPARING", "GENERATING")
        deadline_exceeded = bool(
            pending
            and conversation.generation_deadline_at is not None
            and conversation.generation_deadline_at <= now
        )
        attempts = self.conversation_attempts(conversation.conversation_id)
        latest = attempts[-1] if attempts else None
        from backend.application.generation import can_retry_reply

        can_retry = can_retry_reply(
            conversation.generation_status,
            conversation.fallback_reason,
            latest.error_code if latest else None,
            (latest.usage_json or {}).get("retry_after_seconds") if latest else None,
            latest.finished_at if latest else None,
            len(attempts),
            state,
            is_current,
            conversation.character_id,
            conversation.source_state_version,
            now,
        ) and not self.has_other_pending(conversation.session_id, conversation.conversation_id)
        return {
            "conversation_id": str(conversation.conversation_id),
            "conversation_seq": conversation.conversation_seq,
            "session_id": str(conversation.session_id),
            "npc_id": conversation.character_id,
            "request_id": str(request.request_id),
            "interaction_type": interaction,
            "source_state_version": conversation.source_state_version,
            "generation_status": conversation.generation_status,
            "generation_deadline_at": conversation.generation_deadline_at.isoformat().replace(
                "+00:00", "Z"
            )
            if conversation.generation_deadline_at
            else None,
            "deadline_exceeded": deadline_exceeded,
            "fixed_reply": conversation.fixed_reply,
            "messages": [
                {
                    "message_id": str(message.message_id),
                    "sequence_no": message.sequence_no,
                    "speaker": message.speaker,
                    "content": message.content,
                    "origin": message.origin,
                    "validity": message.validity,
                    "created_at": message.created_at.isoformat().replace("+00:00", "Z"),
                    "updated_at": message.updated_at.isoformat().replace("+00:00", "Z"),
                }
                for message in messages
            ],
            "fallback_reason": conversation.fallback_reason,
            "can_retry_reply": can_retry,
            "created_at": conversation.created_at.isoformat().replace("+00:00", "Z"),
            "completed_at": conversation.completed_at.isoformat().replace("+00:00", "Z")
            if conversation.completed_at
            else None,
        }

    def find_conversation(
        self, session_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> tuple[Conversation, ActionRequest] | None:
        conversation = self._db.scalar(
            select(Conversation).where(
                Conversation.session_id == session_id,
                Conversation.conversation_id == conversation_id,
            )
        )
        if conversation is None:
            return None
        request = self._db.scalar(
            select(ActionRequest).where(
                ActionRequest.session_id == session_id,
                ActionRequest.action_id == conversation.action_id,
            )
        )
        return conversation, request

    def list_conversations(
        self,
        session_id: uuid.UUID,
        character_id: str,
        limit: int,
        before_seq: int | None,
    ) -> tuple[list[Conversation], int | None]:
        query = (
            select(Conversation)
            .where(
                Conversation.session_id == session_id,
                Conversation.character_id == character_id,
            )
            .order_by(Conversation.conversation_seq.desc())
        )
        if before_seq is not None:
            query = query.where(Conversation.conversation_seq < before_seq)
        rows = list(self._db.scalars(query.limit(limit + 1)))
        next_before_seq = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_before_seq = rows[-1].conversation_seq
        return rows, next_before_seq

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
                        "missing_evidence_ids": list(c.missing_evidence_ids),
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
            fixed_explanation=FIXED_EXPLANATIONS[CATEGORY_LABELS[row.verdict_category]],
            score=int(row.score),
            criteria=tuple(
                CriterionResult(
                    c["criterion_id"],
                    c["label"],
                    c["score"],
                    c["max_score"],
                    c["explanation"],
                    c.get("missing_evidence_ids", []),
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
