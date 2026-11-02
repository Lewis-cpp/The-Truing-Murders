"""Generation orchestration for NPC01: reserve, dispatch, settle, fall back.

The business transaction commits the fixed result and the PREPARING round first;
the model is called outside any transaction and its output has no write path
into game state. Every task step re-checks that the round is still the current
one before writing (v0.4 spec section 6).
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.application.catalog import CaseCatalog
from backend.application.conversation import check_reply, load_guard
from backend.application.memory import (
    ContextBudget,
    ContextOverBudget,
    build_context,
    summarize,
    summary_from_json,
    summary_is_valid,
    summary_to_json,
)
from backend.config import Settings
from backend.domain.models import Case, GameState, Phase
from backend.infrastructure.database.models import (
    CaseTemplate,
    Conversation,
    ConversationMessage,
    GameSession,
    LlmAttempt,
    NpcState,
    Visitor,
)
from backend.infrastructure.database.repositories.session_repository import SessionRepository
from backend.infrastructure.llm_client import LLMCall

# Public fallback reasons; internal codes stay on llm_attempt.error_code.
FALLBACK_REASONS = {
    "TIMEOUT": "MODEL_TIMEOUT",
    "RATE_LIMITED": "MODEL_RATE_LIMITED",
    "UNAVAILABLE": "MODEL_UNAVAILABLE",
    "AUTH_FAILED": "MODEL_UNAVAILABLE",
    "CONTEXT_TOO_LONG": "CONTEXT_BUDGET_EXCEEDED",
    "PROTOCOL_INVALID": "MODEL_OUTPUT_REJECTED",
    "REFUSED": "MODEL_OUTPUT_REJECTED",
    "TRUNCATED": "MODEL_OUTPUT_REJECTED",
    "CONTEXT_BUDGET_EXCEEDED": "CONTEXT_BUDGET_EXCEEDED",
    "GENERATION_INTERRUPTED": "GENERATION_INTERRUPTED",
    "GENERATION_DISABLED": "GENERATION_DISABLED",
    "GENERATION_BUDGET_EXHAUSTED": "GENERATION_BUDGET_EXHAUSTED",
}

# Rounds with these public reasons may be retried explicitly; MODEL_OUTPUT_REJECTED
# is retryable only when the internal code is a format problem, not a content one.
RETRYABLE_REASONS = {"MODEL_TIMEOUT", "MODEL_UNAVAILABLE", "MODEL_RATE_LIMITED"}
RETRYABLE_INTERNAL = {"PROTOCOL_INVALID", "TRUNCATED"}
MAX_ATTEMPTS = 3

PENDING_STATUSES = ("PREPARING", "GENERATING")


@dataclass(frozen=True)
class GenerationConfig:
    enabled_npcs: frozenset[str]
    timeout_seconds: float
    max_input_tokens: int
    max_output_tokens: int
    call_limit: int
    token_limit: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "GenerationConfig":
        return cls(
            enabled_npcs=frozenset(settings.llm_enabled_npcs),
            timeout_seconds=settings.llm_timeout_seconds,
            max_input_tokens=settings.llm_max_input_tokens,
            max_output_tokens=settings.llm_max_output_tokens,
            call_limit=settings.llm_session_call_limit,
            token_limit=settings.llm_session_token_limit,
        )


@dataclass(frozen=True)
class GenerationRuntime:
    """What one request may use; read from app.state per request, never captured at startup."""

    config: GenerationConfig
    gateway: object | None
    dispatcher: object | None

    def mode_for(self, npc_id: str) -> str:
        """DISABLED keeps the v0.3 fixed mode; READY rounds go through the gateway."""
        if self.gateway is None or npc_id not in self.config.enabled_npcs:
            return "DISABLED"
        return "READY"


class ThreadDispatcher:
    """Bounded in-process dispatcher; tests replace it with a manual one."""

    def __init__(self, max_workers: int):
        from concurrent.futures import ThreadPoolExecutor

        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="llm"
        )

    def submit(self, task: Callable[[], None]) -> None:
        self._executor.submit(task)

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def budget_payload(config: GenerationConfig | None) -> dict:
    """The frozen per-game budget written at game start; spec defaults when unknown."""
    c = config or GenerationConfig(
        enabled_npcs=frozenset(),
        timeout_seconds=30.0,
        max_input_tokens=4000,
        max_output_tokens=400,
        call_limit=60,
        token_limit=200000,
    )
    return {
        "session_call_limit": c.call_limit,
        "session_token_limit": c.token_limit,
        "max_input_tokens": c.max_input_tokens,
        "max_output_tokens": c.max_output_tokens,
        "timeout_seconds": c.timeout_seconds,
    }


def budget_of(db: Session, row: GameSession) -> dict:
    budget = row.llm_budget_json or {}
    return budget if isinstance(budget, dict) else {}


def usage_of(db: Session, session_id: uuid.UUID) -> tuple[int, int]:
    """(calls, tokens): calls are attempts not known to be unsent; tokens are KNOWN
    billable plus RESERVED/UNKNOWN reservations (doc 09 section 6.6)."""
    calls = 0
    tokens = 0
    for attempt in db.scalars(select(LlmAttempt).where(LlmAttempt.session_id == session_id)):
        if attempt.usage_status != "NOT_SENT":
            calls += 1
        if attempt.usage_status == "KNOWN" and attempt.billable_tokens is not None:
            tokens += attempt.billable_tokens
        elif attempt.usage_status in ("RESERVED", "UNKNOWN"):
            tokens += attempt.reserved_tokens
    return calls, tokens


def _conditions_hold(db: Session, conversation: Conversation) -> bool:
    """Step 2/6 guard: the round is still the current, in-phase one (the deadline is
    checked by the caller: an expired round in an unchanged context stays retryable)."""
    if conversation.generation_status != "GENERATING":
        return False
    row = db.get_one(GameSession, conversation.session_id)
    if row.phase != Phase.INTERROGATION or row.active_npc_id != conversation.character_id:
        return False
    if row.state_version != conversation.source_state_version:
        return False
    visitor = db.get_one(Visitor, row.visitor_id)
    return visitor is not None and visitor.current_session_id == row.session_id


def _write_fixed_reply(
    db: Session, conversation: Conversation, attempt_id: uuid.UUID | None, now: datetime
) -> None:
    existing = db.scalar(
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
    db.add(
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


def _fallback_round(
    db: Session,
    conversation: Conversation,
    reason: str,
    attempt_id: uuid.UUID | None,
    now: datetime,
) -> None:
    conversation.generation_status = "FALLBACK"
    conversation.fallback_reason = reason
    conversation.completed_at = now
    _write_fixed_reply(db, conversation, attempt_id, now)


def _stale_round(db: Session, conversation: Conversation, now: datetime) -> None:
    conversation.generation_status = "STALE"
    conversation.fallback_reason = "CONTEXT_CHANGED"
    conversation.completed_at = now
    _write_fixed_reply(db, conversation, conversation.active_attempt_id, now)


@dataclass(frozen=True)
class _Plan:
    case: Case
    state: GameState
    npc_id: str
    messages: tuple[dict, ...]
    digest: str
    refs: tuple[str, ...]
    estimated_input_tokens: int
    max_output_tokens: int
    deadline_at: datetime
    memory_epoch: int
    # The rebuilt summary to cache in npc_memory_summary during the reserve step.
    summary_write: dict | None
    expected_revision: int


def _build_plan(db: Session, catalog: CaseCatalog, conversation: Conversation) -> _Plan:
    """Step 1: read committed state and assemble the authorized context. Read-only."""
    row = db.get_one(GameSession, conversation.session_id)
    template = db.get_one(CaseTemplate, row.template_id)
    case = catalog.load(db, template)
    repository = SessionRepository(db)
    saved = repository.load(row, case)
    npc_row = db.get_one(NpcState, (row.session_id, conversation.character_id))
    memory_epoch = npc_row.memory_epoch if npc_row else 0
    history = repository.history_rounds(
        conversation.session_id,
        conversation.character_id,
        conversation.conversation_seq,
        memory_epoch,
    )
    player_message = db.scalar(
        select(ConversationMessage.content).where(
            ConversationMessage.conversation_id == conversation.conversation_id,
            ConversationMessage.sequence_no == 1,
        )
    )
    budget = budget_of(db, row)
    # The stored summary is used only when it re-derives exactly from the current
    # messages; otherwise it is rebuilt now and cached during the reserve step.
    summary = None
    summary_write = None
    expected_revision = 0
    try:
        summary_row = repository.find_memory_summary(row.session_id, conversation.character_id)
    except Exception:  # noqa: BLE001 - a broken cache must not block generation
        summary_row = None
    if summary_row is not None:
        expected_revision = summary_row.summary_revision
        stored = summary_from_json(summary_row.summary_json)
        if stored is not None and summary_is_valid(
            stored, str(row.session_id), conversation.character_id, memory_epoch, history
        ):
            summary = stored
    if summary is None:
        summary = summarize(str(row.session_id), conversation.character_id, memory_epoch, history)
        summary_write = summary_to_json(summary) if summary is not None else None
    context = build_context(
        case,
        saved.state,
        conversation.character_id,
        history,
        player_message or "",
        conversation.fixed_reply,
        ContextBudget(
            max_input_tokens=int(budget.get("max_input_tokens", 4000)),
            max_output_tokens=int(budget.get("max_output_tokens", 400)),
        ),
        memory_epoch=memory_epoch,
        summary=summary,
    )
    return _Plan(
        case=case,
        state=saved.state,
        npc_id=conversation.character_id,
        messages=context.messages,
        digest=context.context_digest,
        refs=context.included_refs,
        estimated_input_tokens=context.estimated_input_tokens,
        max_output_tokens=int(budget.get("max_output_tokens", 400)),
        deadline_at=conversation.generation_deadline_at or _utcnow(),
        memory_epoch=memory_epoch,
        summary_write=summary_write,
        expected_revision=expected_revision,
    )


def run_generation_task(
    sessions: sessionmaker[Session],
    catalog: CaseCatalog,
    conversation_id: uuid.UUID,
    gateway,
    request_action_id: uuid.UUID,
) -> None:
    """The whole task: build, reserve, dispatch once, settle. Never raises.

    `request_action_id` is the command that triggered this attempt (the original
    chat/presentation or the explicit retry); llm_attempt records it uniquely.
    """
    try:
        with sessions() as db:
            conversation = db.get_one(Conversation, conversation_id)
            if conversation is None or conversation.generation_status != "PREPARING":
                return
            try:
                plan = _build_plan(db, catalog, conversation)
            except ContextOverBudget:
                plan = None
            status = conversation.generation_status
        if plan is None:
            if status == "PREPARING":
                _degrade_without_attempt(sessions, conversation_id, "CONTEXT_BUDGET_EXCEEDED")
            return
        reservation = _reserve(sessions, conversation_id, plan, request_action_id)
        if reservation is None:
            return
        attempt_id, deadline_at = reservation
        if not _mark_dispatched(sessions, attempt_id):
            return
        result = gateway.generate(
            LLMCall(
                messages=plan.messages,
                max_output_tokens=plan.max_output_tokens,
                deadline=time.monotonic() + max(0.0, (deadline_at - _utcnow()).total_seconds()),
            )
        )
        _settle(sessions, catalog, conversation_id, attempt_id, plan, result)
    except Exception:  # noqa: BLE001 - a task must never take the process down
        return


def _degrade_without_attempt(sessions: sessionmaker[Session], conversation_id, reason: str) -> None:
    """Step 1 failure: fall back with the fixed reply, no attempt, no call."""
    with sessions() as db, db.begin():
        conversation = db.get_one(Conversation, conversation_id)
        if conversation is not None and conversation.generation_status == "PREPARING":
            _fallback_round(db, conversation, reason, None, _utcnow())


def _reserve(
    sessions: sessionmaker[Session],
    conversation_id: uuid.UUID,
    plan: _Plan,
    request_action_id: uuid.UUID,
) -> tuple[uuid.UUID, datetime] | None:
    """Step 2: re-verify under the session lock, reserve budget, mark GENERATING."""
    now = _utcnow()
    with sessions() as db, db.begin():
        repository = SessionRepository(db)
        conversation = db.get_one(Conversation, conversation_id)
        if conversation is None or conversation.generation_status != "PREPARING":
            return None
        if conversation.generation_deadline_at is not None and now >= (
            conversation.generation_deadline_at
        ):
            _stale_round(db, conversation, now)
            return None
        row = db.get_one(GameSession, conversation.session_id)
        visitor = db.get_one(Visitor, row.visitor_id)
        if (
            row.phase != Phase.INTERROGATION
            or row.active_npc_id != conversation.character_id
            or row.state_version != conversation.source_state_version
            or visitor is None
            or visitor.current_session_id != row.session_id
        ):
            _stale_round(db, conversation, now)
            return None
        budget = budget_of(db, row)
        calls, tokens = usage_of(db, row.session_id)
        reserved = plan.estimated_input_tokens + plan.max_output_tokens
        if calls >= int(budget.get("session_call_limit", 60)) or tokens + reserved > int(
            budget.get("session_token_limit", 200000)
        ):
            _fallback_round(db, conversation, "GENERATION_BUDGET_EXHAUSTED", None, now)
            return None
        highest = db.scalar(
            select(LlmAttempt.attempt_no)
            .where(LlmAttempt.conversation_id == conversation_id)
            .order_by(LlmAttempt.attempt_no.desc())
            .limit(1)
        )
        attempt = LlmAttempt(
            attempt_id=uuid.uuid4(),
            session_id=conversation.session_id,
            conversation_id=conversation_id,
            request_action_id=request_action_id,
            attempt_no=(highest or 0) + 1,
            status="RESERVED",
            usage_status="RESERVED",
            validation_status="PENDING",
            provider="openai-compatible",
            model=_configured_model(),
            prompt_version="npc-1",
            context_digest=plan.digest,
            context_refs_json={"included_refs": list(plan.refs)},
            estimated_input_tokens=plan.estimated_input_tokens,
            count_is_exact=False,
            max_output_tokens=plan.max_output_tokens,
            reserved_tokens=reserved,
            created_at=now,
            deadline_at=conversation.generation_deadline_at or now,
        )
        if plan.summary_write is not None:
            try:
                repository.store_memory_summary(
                    row.session_id,
                    row.template_id,
                    conversation.character_id,
                    plan.memory_epoch,
                    plan.summary_write,
                    plan.expected_revision,
                    now,
                )
            except Exception:  # noqa: BLE001 - the summary is a cache, never a requirement
                pass
        db.add(attempt)
        db.flush()
        conversation.generation_status = "GENERATING"
        conversation.active_attempt_id = attempt.attempt_id
        return attempt.attempt_id, conversation.generation_deadline_at or now


def _configured_model() -> str:
    try:
        return Settings().llm_model or "unknown"
    except Exception:  # noqa: BLE001 - the attempt row needs a value either way
        return "unknown"


def _mark_dispatched(sessions: sessionmaker[Session], attempt_id: uuid.UUID) -> bool:
    """Step 3: only the winner of the conditional update may call the provider."""
    with sessions() as db, db.begin():
        attempt = db.get_one(LlmAttempt, attempt_id)
        if attempt is None or attempt.status != "RESERVED":
            return False
        attempt.status = "DISPATCHING"
        attempt.dispatch_started_at = _utcnow()
        return True


def _settle(
    sessions: sessionmaker[Session],
    catalog: CaseCatalog,
    conversation_id: uuid.UUID,
    attempt_id: uuid.UUID,
    plan: _Plan,
    result,
) -> None:
    """Steps 5+6: settle usage first, then decide COMPLETED / FALLBACK / STALE."""
    now = _utcnow()
    with sessions() as db, db.begin():
        conversation = db.get_one(Conversation, conversation_id)
        attempt = db.get_one(LlmAttempt, attempt_id)
        if conversation is None or attempt is None:
            return
        if result.usage is not None:
            attempt.usage_status = "KNOWN"
            attempt.input_tokens = result.usage.input_tokens
            attempt.output_tokens = result.usage.output_tokens
            attempt.billable_tokens = result.usage.input_tokens + result.usage.output_tokens
        elif result.sent:
            attempt.usage_status = "UNKNOWN"
        else:
            attempt.usage_status = "NOT_SENT"
        attempt.latency_ms = result.latency_ms
        attempt.finished_at = now
        if result.retry_after is not None:
            # The supplier's cooldown hint is kept with the attempt it came from.
            attempt.usage_json = {"retry_after_seconds": result.retry_after}

        still_valid = conversation.active_attempt_id == attempt_id and _conditions_hold(
            db, conversation
        )
        rejection = (
            check_reply(plan.case, plan.state, plan.npc_id, result.text, load_guard())
            if result.text is not None
            else None
        )
        expired = conversation.generation_deadline_at is not None and now >= (
            conversation.generation_deadline_at
        )
        if still_valid and not expired and result.text is not None and rejection is None:
            attempt.status = "SUCCEEDED"
            attempt.validation_status = "ACCEPTED"
            attempt.error_code = None
            message = db.scalar(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.sequence_no == 2,
                )
            )
            if message is not None:
                message.content = result.text
                message.origin = "LLM"
                message.attempt_id = attempt_id
                message.updated_at = now
            else:
                db.add(
                    ConversationMessage(
                        message_id=uuid.uuid4(),
                        session_id=conversation.session_id,
                        conversation_id=conversation_id,
                        sequence_no=2,
                        speaker="NPC",
                        content=result.text,
                        origin="LLM",
                        validity="VALID",
                        attempt_id=attempt_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
            conversation.generation_status = "COMPLETED"
            conversation.fallback_reason = None
            conversation.completed_at = now
            return
        if still_valid:
            # The call finished but the candidate is unusable: the fixed reply wins.
            internal = rejection or result.error_code or ("TIMEOUT" if expired else None)
            attempt.status = "FAILED" if result.error_code is not None else "SUCCEEDED"
            attempt.validation_status = "REJECTED" if rejection is not None else "NOT_APPLICABLE"
            attempt.error_code = internal
            _fallback_round(
                db,
                conversation,
                FALLBACK_REASONS.get(internal or "", "MODEL_OUTPUT_REJECTED"),
                attempt_id,
                now,
            )
            return
        # The round is no longer the current one: usage is kept, the text is not.
        attempt.status = "SUCCEEDED" if result.error_code is None else "FAILED"
        attempt.validation_status = "STALE"
        attempt.error_code = attempt.error_code or result.error_code
        if conversation.generation_status in PENDING_STATUSES:
            _stale_round(db, conversation, now)


def can_retry_reply(
    status: str,
    fallback_reason: str | None,
    internal_code: str | None,
    retry_after_seconds: float | None,
    finished_at: datetime | None,
    attempt_count: int,
    state: GameState | None,
    is_current: bool,
    npc_id: str | None,
    source_state_version: int,
    now: datetime,
) -> bool:
    if status != "FALLBACK" or attempt_count >= MAX_ATTEMPTS:
        return False
    retryable = fallback_reason in RETRYABLE_REASONS or (
        fallback_reason == "MODEL_OUTPUT_REJECTED" and internal_code in RETRYABLE_INTERNAL
    )
    if not retryable:
        return False
    if state is None or not is_current:
        return False
    if state.phase != Phase.INTERROGATION or state.active_npc_id != npc_id:
        return False
    if state.version != source_state_version:
        return False
    if retry_after_seconds and finished_at is not None:
        if now < finished_at + timedelta(seconds=retry_after_seconds):
            return False
    return True
