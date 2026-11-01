"""Game use cases over the database. One short transaction per command, under the session lock.

Order for every write: idempotent replay → ownership → current entry → version → phase → target.
Business rules stay in the pure domain functions; this module only loads, decides and saves.
"""

import hashlib
import json
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from backend.application import views
from backend.application.catalog import CaseCatalog, is_supported
from backend.application.errors import ApiProblem
from backend.application.generation import (
    GenerationRuntime,
    can_retry_reply,
    run_generation_task,
    usage_of,
)
from backend.domain import rules
from backend.domain.evidence import current_statement, outcome_text
from backend.domain.models import (
    Accusation,
    AccusationDraft,
    Case,
    GameError,
    GameState,
    Phase,
    StepEvidenceLink,
)
from backend.domain.rules import open_scenes
from backend.domain.state_machine import guard, transition
from backend.infrastructure.database.models import ActionRequest, CaseTemplate, Visitor
from backend.infrastructure.database.repositories.case_repository import CaseRepository
from backend.infrastructure.database.repositories.session_repository import (
    ConversationInput,
    EventInput,
    SavedGame,
    SessionRepository,
    comparable,
)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Command:
    """One client operation. The same request_id must always carry the same input."""

    request_id: uuid.UUID
    method: str
    path: str
    payload: dict
    expected_version: int | None = None

    @property
    def input_json(self) -> dict:
        return {
            "method": self.method,
            "path": self.path,
            "expected_state_version": self.expected_version,
            "payload": self.payload,
        }

    @property
    def input_hash(self) -> str:
        text = json.dumps(
            self.input_json, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class CommandResponse:
    status_code: int
    body: dict
    location: str | None = None
    # Set only when a PREPARING round was created; submitted after the commit.
    task: Callable[[], None] | None = None


@dataclass
class Decision:
    """What a handler decided; data is projected after saving, inside the same transaction.

    `conversation` optionally creates a fixed interaction round after the state is saved; it
    receives the case, the stored request, the reloaded game and the projected data dict.
    `conversation_data` may replace the response data once the round exists (the chat receipt).
    """

    after: GameState
    event_type: str
    data: Callable[[SavedGame, SavedGame, CaseTemplate], dict]
    status_code: int = 201
    target_character_id: str | None = None
    presented_evidence_id: str | None = None
    location: str | None = None
    input_json: dict = field(default_factory=dict)
    conversation: Callable[[Case, ActionRequest, SavedGame, dict], ConversationInput] | None = None
    conversation_data: Callable[[dict, dict], dict] | None = None
    # When set, the interaction round may go to the model for this NPC (v0.4: NPC01).
    generation_npc: str | None = None


@dataclass(frozen=True)
class VisitorAccess:
    visitor_id: uuid.UUID
    current_session_id: uuid.UUID | None
    new_token: str | None


def _rejection(error: GameError) -> ApiProblem:
    return ApiProblem(error.code, str(error))


def _public(code: str) -> str:
    """EVASION_STARTED is an internal refinement; clients only ever see NPC_EVADING."""
    return "NPC_EVADING" if code == "EVASION_STARTED" else code


# Commands that may start a generation: they clean expired placeholders first and
# answer 409 GENERATION_BUSY while another pending round holds the session.
GENERATION_ACCEPTING = {"CHAT", "PRESENT_EVIDENCE"}
# Commands that make the pending context invalid in the same business transaction.
INVALIDATING = {"SET_INTERROGATION", "END_INTERROGATION", "OPEN_ACCUSATION"}


class GameService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        catalog: CaseCatalog | None = None,
        generation: Callable[[], GenerationRuntime | None] | None = None,
    ):
        self._sessions = sessions
        self._catalog = catalog or CaseCatalog()
        # Read per request from app.state; never captured at startup.
        self._generation_provider = generation

    def _generation(self) -> GenerationRuntime | None:
        return self._generation_provider() if self._generation_provider else None

    def _submit_task(self, response: CommandResponse) -> CommandResponse:
        if response.task is not None:
            runtime = self._generation()
            if runtime is not None and runtime.dispatcher is not None:
                runtime.dispatcher.submit(response.task)
        return response

    # Visitors

    def ensure_visitor(self, token: str | None) -> VisitorAccess:
        now = datetime.now(UTC)
        with self._sessions() as db, db.begin():
            repository = SessionRepository(db)
            visitor = repository.find_visitor(hash_token(token)) if token else None
            if visitor is not None:
                visitor.last_seen_at = now
                return VisitorAccess(visitor.visitor_id, visitor.current_session_id, None)
            new_token = secrets.token_urlsafe(32)
            visitor = repository.add_visitor(hash_token(new_token), now)
            return VisitorAccess(visitor.visitor_id, None, new_token)

    def authenticate(self, token: str | None) -> uuid.UUID:
        if token:
            with self._sessions() as db:
                visitor = SessionRepository(db).find_visitor(hash_token(token))
                if visitor is not None:
                    return visitor.visitor_id
        raise ApiProblem("VISITOR_AUTH_REQUIRED", "访问凭据缺失或已失效，请刷新页面。")

    # Reads use one REPEATABLE READ snapshot so a view never mixes two commits.

    def _read(self):
        db = self._sessions()
        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return db

    def list_cases(self) -> dict:
        with self._read() as db:
            return {
                "items": [
                    {
                        "case_id": t.case_id,
                        "case_version": t.version,
                        "title": t.title,
                        "synopsis": t.synopsis,
                    }
                    for t in CaseRepository(db).list_published()
                    if is_supported(t)
                ]
            }

    def _load_owned(self, db: Session, visitor_id: uuid.UUID, session_id: uuid.UUID, lock=False):
        repository = SessionRepository(db)
        row = repository.get_session(visitor_id, session_id, lock=lock)
        if row is None:
            raise ApiProblem("SESSION_NOT_FOUND", "找不到该游戏存档。")
        template = repository.template(row)
        if not is_supported(template):
            # Kept as stored; the details let the client offer a new game that replaces it.
            raise ApiProblem(
                "SAVE_VERSION_UNSUPPORTED",
                "当前版本暂时无法读取此存档。存档已保留，可以返回大厅开始新的一局。",
                {"session_id": str(row.session_id), "state_version": row.state_version},
            )
        case = self._catalog.load(db, template)
        return repository, row, template, case, repository.load(row, case)

    @staticmethod
    def _is_current(db: Session, visitor_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        return db.get_one(Visitor, visitor_id).current_session_id == session_id

    def session_view(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            repository, row, template, case, saved = self._load_owned(db, visitor_id, session_id)
            return views.session_view(
                case,
                template,
                saved,
                self._is_current(db, visitor_id, row.session_id),
                repository.pending_summaries(session_id),
            )

    def current_session(self, visitor_id: uuid.UUID) -> dict:
        with self._read() as db:
            current = db.get_one(Visitor, visitor_id).current_session_id
            if current is None:
                return {"current_session_id": None, "session": None}
            repository, _, template, case, saved = self._load_owned(db, visitor_id, current)
            return {
                "current_session_id": str(current),
                "session": views.session_view(
                    case, template, saved, True, repository.pending_summaries(current)
                ),
            }

    def closed_view(self, visitor_id: uuid.UUID, session_id: uuid.UUID, review: bool) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            if saved.state.verdict is None:
                raise ApiProblem("REVIEW_NOT_AVAILABLE", "正式结案后才能查看判定与复盘。")
            data = views.review_view(case, saved) if review else views.accusation_view(saved)
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": data,
            }

    def request_record(self, visitor_id: uuid.UUID, request_id: uuid.UUID) -> dict:
        with self._read() as db:
            request = SessionRepository(db).find_request(visitor_id, request_id)
            if request is None:
                raise ApiProblem(
                    "REQUEST_NOT_FOUND", "没有找到该操作；若刚刚断线，请用原键原内容重试。"
                )
            rejected = request.status == "REJECTED"
            return {
                "request_id": str(request.request_id),
                "status": request.status,
                "original_http_status": request.http_status,
                "result": None
                if rejected
                else {k: v for k, v in request.result_json.items() if k != "_location"},
                "error": request.result_json.get("error") if rejected else None,
            }

    # Read-only game resources; every GET is projection-only and never writes.

    def scene_views(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            open_ids = set(open_scenes(case, saved.state))
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": {
                    "items": [
                        views.scene_view(case, saved, scene)
                        for scene in case.scenes
                        if scene.id in open_ids
                    ]
                },
            }

    def scene_detail(self, visitor_id: uuid.UUID, session_id: uuid.UUID, scene_id: str) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            scene = next((s for s in case.scenes if s.id == scene_id), None)
            if scene is None or scene.id not in set(open_scenes(case, saved.state)):
                raise ApiProblem("SCENE_NOT_FOUND", "场景不存在或尚未开放。")
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": views.scene_view(case, saved, scene),
            }

    def evidence_views(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": {
                    "items": [
                        views.evidence_view(case, saved, e.id)
                        for e in case.evidence
                        if e.id in saved.state.evidence_ids
                    ]
                },
            }

    def evidence_detail(
        self, visitor_id: uuid.UUID, session_id: uuid.UUID, evidence_id: str
    ) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            if evidence_id not in saved.state.evidence_ids:
                raise ApiProblem("EVIDENCE_NOT_FOUND", "没有找到该证据。")
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": views.evidence_view(case, saved, evidence_id),
            }

    def npc_views(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": {
                    "items": [
                        views.npc_view(case, saved, c.id)
                        for c in case.characters
                        if c.interrogatable
                    ]
                },
            }

    def npc_detail(self, visitor_id: uuid.UUID, session_id: uuid.UUID, npc_id: str) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            # The read model only knows the interrogatable people; anyone else is hidden.
            if npc_id not in {c.id for c in case.characters if c.interrogatable}:
                raise ApiProblem("NPC_NOT_FOUND", "找不到该角色。")
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": views.npc_view(case, saved, npc_id),
            }

    def relationship_graph(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": views.relationship_graph(case, saved),
            }

    def timeline_view(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": views.timeline_view(case, saved),
            }

    def accusation_options_view(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            _, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": views.accusation_options(case),
            }

    def accusation_draft_view(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            _, _, _, _, saved = self._load_owned(db, visitor_id, session_id)
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": views.draft_view(saved),
            }

    def conversation_page(
        self,
        visitor_id: uuid.UUID,
        session_id: uuid.UUID,
        npc_id: str,
        limit: int,
        before_seq: int | None,
    ) -> dict:
        with self._read() as db:
            repository, _, _, case, saved = self._load_owned(db, visitor_id, session_id)
            self._check_npc(case, npc_id)
            rows, next_before_seq = repository.list_conversations(
                session_id, npc_id, limit, before_seq
            )
            items = []
            for row in rows:
                conversation, request = repository.find_conversation(
                    session_id, row.conversation_id
                )
                items.append(
                    repository.conversation_view(
                        conversation,
                        request,
                        saved.state,
                        self._is_current(db, visitor_id, session_id),
                    )
                )
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": {"items": items, "next_before_seq": next_before_seq},
            }

    def conversation_detail(
        self, visitor_id: uuid.UUID, session_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> dict:
        with self._read() as db:
            repository, _, _, _, saved = self._load_owned(db, visitor_id, session_id)
            found = repository.find_conversation(session_id, conversation_id)
            if found is None:
                raise ApiProblem("CONVERSATION_NOT_FOUND", "没有找到该对话轮次。")
            conversation, request = found
            return {
                "session_id": str(session_id),
                "state_version": saved.state.version,
                "data": repository.conversation_view(
                    conversation,
                    request,
                    saved.state,
                    self._is_current(db, visitor_id, session_id),
                ),
            }

    # Idempotency helpers

    @staticmethod
    def _replay(repository: SessionRepository, visitor_id, command: Command):
        existing = repository.find_request(visitor_id, command.request_id)
        if existing is None:
            return None
        if existing.input_hash != command.input_hash:
            raise ApiProblem(
                "IDEMPOTENCY_KEY_CONFLICT", "该操作键已用于另一项请求；新操作请使用新的键。"
            )
        return CommandResponse(
            existing.http_status, existing.result_json, existing.result_json.get("_location")
        )

    @staticmethod
    def _new_request(visitor_id, command: Command, command_type: str, session_id, now):
        return ActionRequest(
            action_id=uuid.uuid4(),
            visitor_id=visitor_id,
            request_id=command.request_id,
            session_id=session_id,
            command_type=command_type,
            expected_state_version=command.expected_version,
            input_hash=command.input_hash,
            input_json=command.input_json,
            status="REJECTED",
            http_status=500,
            result_json={},
            created_at=now,
            completed_at=now,
        )

    @staticmethod
    def _reject(repository, request: ActionRequest, problem: ApiProblem) -> CommandResponse:
        """Store a business rejection so the same key replays the same answer."""
        request.status = "REJECTED"
        request.http_status = problem.status
        request.result_json = {"error": problem.to_dict()}
        repository.add_request(request)
        return CommandResponse(problem.status, request.result_json)

    @staticmethod
    def _action_result(command, request, before: SavedGame, after: SavedGame, data) -> dict:
        return {
            "request_id": str(command.request_id),
            "session_id": str(after.session_id),
            "business_status": request.status,
            "state_changed": after.state.version != before.state.version,
            "state_version_before": before.state.version,
            "result_state_version": after.state.version,
            "phase_after": after.state.phase.value,
            "active_npc_id_after": after.state.active_npc_id,
            "saved_at": views.iso(after.saved_at),
            "data": data,
            "conversation": None,
        }

    # Session creation and restart

    def create_session(
        self,
        visitor_id: uuid.UUID,
        command: Command,
        case_id: str,
        case_version: str,
        replaces_session_id: uuid.UUID | None,
        confirm_restart: bool,
    ) -> CommandResponse:
        now = datetime.now(UTC)
        with self._sessions() as db, db.begin():
            repository = SessionRepository(db)
            replay = self._replay(repository, visitor_id, command)
            if replay:
                return replay
            visitor = repository.lock_visitor(visitor_id)
            replay = self._replay(repository, visitor_id, command)
            if replay:
                return replay
            request = self._new_request(visitor_id, command, "CREATE_SESSION", None, now)
            current = visitor.current_session_id
            if current is None and command.expected_version is not None:
                raise ApiProblem("INVALID_STATE_VERSION_HEADER", "首次开局不应携带旧局版本。")
            if current is not None and replaces_session_id is not None:
                if command.expected_version is None:
                    raise ApiProblem("STATE_VERSION_REQUIRED", "重开需要提供旧局的预期版本。")
            try:
                if current is None and replaces_session_id is not None:
                    raise ApiProblem("CURRENT_SESSION_CONFLICT", "要替换的游戏已不是当前存档。")
                if current is not None:
                    if replaces_session_id is None:
                        raise ApiProblem(
                            "CURRENT_SESSION_EXISTS", "已有进行中的存档；重开需要明确确认。"
                        )
                    if replaces_session_id != current:
                        raise ApiProblem("CURRENT_SESSION_CONFLICT", "要替换的游戏已不是当前存档。")
                    if not confirm_restart:
                        raise ApiProblem("CONFIRMATION_REQUIRED", "请确认重开；旧局会保留为只读。")
                    old = repository.get_session(visitor_id, current, lock=True)
                    if old.state_version != command.expected_version:
                        raise ApiProblem(
                            "STATE_VERSION_CONFLICT",
                            "游戏进度已更新，请刷新后重试。",
                            {"current_state_version": old.state_version},
                        )
                template = CaseRepository(db).find(case_id, case_version)
                if template is None or template.status == "DRAFT":
                    raise ApiProblem("CASE_NOT_FOUND", "没有可开始的案件版本。")
                if template.status != "PUBLISHED" or not is_supported(template):
                    raise ApiProblem("CASE_UNAVAILABLE", "该案件版本已下架，请重新选择。")
            except ApiProblem as problem:
                return self._reject(repository, request, problem)
            case = self._catalog.load(db, template)
            request.status = "COMMITTED"
            request.http_status = 201
            row = repository.create(visitor, template, case, request, now)
            saved = repository.load(row, case)
            empty = replace(saved, state=replace(saved.state, version=0))
            result = self._action_result(
                command, request, empty, saved, views.session_view(case, template, saved, True)
            )
            result["state_changed"] = True
            return self._finish(request, result, saved, f"/api/v1/sessions/{row.session_id}")

    @staticmethod
    def _finish(request: ActionRequest, result: dict, saved: SavedGame, location, task=None):
        if location:
            result["_location"] = location
        request.result_json = result
        request.result_state_version = saved.state.version
        request.completed_at = datetime.now(UTC)
        return CommandResponse(request.http_status, result, location, task)

    # Generic command execution

    def _execute(
        self,
        visitor_id: uuid.UUID,
        session_id: uuid.UUID,
        command: Command,
        command_type: str,
        handler: Callable[[Case, SavedGame, ActionRequest], Decision],
    ) -> CommandResponse:
        if command.expected_version is None:
            raise ApiProblem("STATE_VERSION_REQUIRED", "缺少 X-Expected-State-Version 请求头。")
        now = datetime.now(UTC)
        with self._sessions() as db, db.begin():
            repository = SessionRepository(db)
            replay = self._replay(repository, visitor_id, command)
            if replay:
                return replay
            # Lock before reading any mutable child table used as rule input.
            repository, row, template, case, before = self._load_owned(
                db, visitor_id, session_id, lock=True
            )
            replay = self._replay(repository, visitor_id, command)
            if replay:
                return replay
            request = self._new_request(visitor_id, command, command_type, session_id, now)
            try:
                if not self._is_current(db, visitor_id, session_id):
                    raise ApiProblem("SESSION_NOT_CURRENT", "这是已被替换的旧局，只能查看。")
                if row.state_version != command.expected_version:
                    raise ApiProblem(
                        "STATE_VERSION_CONFLICT",
                        "游戏进度已更新，请刷新后重试。",
                        {
                            "expected_state_version": command.expected_version,
                            "current_state_version": row.state_version,
                        },
                    )
                if command_type in GENERATION_ACCEPTING:
                    repository.expire_pending(session_id, now)
                    pending = repository.pending_round(session_id)
                    if pending is not None:
                        raise ApiProblem(
                            "GENERATION_BUSY",
                            "上一条回复还在生成中，等它完成或失效后再继续。",
                            {"conversation_id": str(pending.conversation_id)},
                        )
                try:
                    decision = handler(case, before, request)
                except GameError as error:
                    raise _rejection(error) from error
            except ApiProblem as problem:
                return self._reject(repository, request, problem)

            changed = comparable(decision.after) != comparable(before.state)
            request.status = "COMMITTED" if changed else "NOOP"
            request.http_status = decision.status_code
            repository.add_request(request)
            if changed:
                repository.save(
                    row,
                    case,
                    before.state,
                    decision.after,
                    EventInput(
                        request,
                        decision.event_type,
                        decision.input_json,
                        decision.target_character_id,
                        decision.presented_evidence_id,
                    ),
                    self._outcome(before.state, decision.after),
                    now,
                )
            if command_type in INVALIDATING:
                # Switching, leaving or accusation: pending rounds go STALE here, so a
                # late model answer can only settle usage, never write a reply.
                repository.invalidate_pending(session_id, now)
            after = repository.load(row, case)
            data = decision.data(before, after, template)
            conversation_view = None
            task = None
            if decision.conversation is not None:
                runtime = self._generation()
                mode = runtime.mode_for(decision.generation_npc) if runtime else "DISABLED"
                fallback_reason = "GENERATION_DISABLED"
                pending_deadline = None
                if mode == "READY" and runtime is not None:
                    calls, tokens = usage_of(db, row.session_id)
                    config = runtime.config
                    if calls >= config.call_limit or tokens >= config.token_limit:
                        mode = "DISABLED"
                        fallback_reason = "GENERATION_BUDGET_EXHAUSTED"
                    else:
                        pending_deadline = now + timedelta(seconds=config.timeout_seconds)
                conversation_input = decision.conversation(case, request, after, data)
                conversation = repository.add_conversation(
                    row,
                    case,
                    conversation_input,
                    fallback_reason=fallback_reason,
                    pending_deadline=pending_deadline,
                )
                conversation_view = repository.conversation_view(
                    conversation, request, after.state, True
                )
                request.status = "COMMITTED"
                if decision.conversation_data is not None:
                    data = decision.conversation_data(conversation_view, data)
                if pending_deadline is not None:
                    task = _generation_task(
                        self._sessions,
                        self._catalog,
                        uuid.UUID(conversation_view["conversation_id"]),
                        runtime.gateway,
                        request.action_id,
                    )
            result = self._action_result(command, request, before, after, data)
            result["conversation"] = conversation_view
            if conversation_view is not None:
                conversation_id = conversation_view["conversation_id"]
                location = f"/api/v1/sessions/{session_id}/conversations/{conversation_id}"
            else:
                location = decision.location or f"/api/v1/requests/{command.request_id}"
            return self._finish(request, result, after, location, task)

    @staticmethod
    def _outcome(before: GameState, after: GameState) -> dict:
        npcs = {}
        for npc_id, npc in after.npcs.items():
            old = before.npcs.get(npc_id)
            if npc == old:
                continue
            npcs[npc_id] = {
                "pressure": [old.pressure if old else None, npc.pressure],
                "trust": [old.trust if old else None, npc.trust],
                "irrelevant_streak": [
                    old.irrelevant_streak if old else None,
                    npc.irrelevant_streak,
                ],
                "lies": {
                    lie_id: [old.lies.get(lie_id).value if old else None, stage.value]
                    for lie_id, stage in npc.lies.items()
                },
            }
        return {
            "phase": [before.phase.value, after.phase.value],
            "active_npc_id": [before.active_npc_id, after.active_npc_id],
            "new_evidence_ids": sorted(after.evidence_ids - before.evidence_ids),
            "completed_action_ids": sorted(after.completed_actions - before.completed_actions),
            "disclosed_knowledge_ids": sorted(
                after.disclosed_knowledge - before.disclosed_knowledge
            ),
            "consumed_effect_keys": sorted(after.consumed_effects - before.consumed_effects),
            "npc_states": npcs,
        }

    @staticmethod
    def _summary(_before: SavedGame, after: SavedGame, template: CaseTemplate) -> dict:
        return views.session_summary(template, after, True)

    # Commands

    def investigate(self, visitor_id, session_id, command: Command, scene_id: str, action_id: str):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            scene = next((s for s in case.scenes if s.id == scene_id), None)
            if scene is None or scene.id not in set(open_scenes(case, saved.state)):
                raise ApiProblem("SCENE_NOT_FOUND", "场景不存在或尚未开放。")
            if next((a for a in scene.actions if a.id == action_id), None) is None:
                raise ApiProblem("INVALID_ACTION_REFERENCE", "该调查点不属于这个场景。")
            after = rules.investigate(case, saved.state, action_id)

            def data(before: SavedGame, done: SavedGame, _template) -> dict:
                gained = sorted(done.state.evidence_ids - before.state.evidence_ids)
                if action_id in before.state.completed_actions:
                    reason, summary = "ALREADY_COMPLETED", "这里已经调查过，证据仍在背包中。"
                elif gained:
                    evidence = next(e for e in case.evidence if e.id == gained[0])
                    reason, summary = "PROGRESS_UPDATED", f"获得 {evidence.id} · {evidence.title}"
                else:
                    reason = "NO_NEW_INFORMATION"
                    summary = "调查已完成，该证据已经在背包中，没有重复发放。"
                before_open = set(open_scenes(case, before.state))
                after_open = set(open_scenes(case, done.state))
                return {
                    "scene_id": scene_id,
                    "action_id": action_id,
                    "outcome": {
                        "reason_code": reason,
                        "summary": summary,
                        "new_evidence": [views.evidence_view(case, done, e) for e in gained],
                        "updated_evidence": [],
                        "disclosed_information": [],
                        "unlocked_scenes": [
                            views.scene_view(case, done, scene)
                            for scene in case.scenes
                            if scene.id in after_open - before_open
                        ],
                        "relationships_changed": views.visible_relationship_ids(case, done.state)
                        != views.visible_relationship_ids(case, before.state),
                        "timeline_changed": views.visible_timeline_ids(case, done.state)
                        != views.visible_timeline_ids(case, before.state),
                        "npc": None,
                    },
                }

            return Decision(after, "INVESTIGATE", data, input_json={"action_id": action_id})

        return self._execute(visitor_id, session_id, command, "INVESTIGATE", handler)

    @staticmethod
    def _check_npc(case: Case, npc_id: str) -> None:
        character = next((c for c in case.characters if c.id == npc_id), None)
        if character is None:
            raise ApiProblem("NPC_NOT_FOUND", "找不到该角色。")
        if not character.interrogatable:
            raise ApiProblem("NPC_UNAVAILABLE", "该角色本版本不可审讯。")

    def set_interrogation(self, visitor_id, session_id, command: Command, npc_id: str):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            guard(saved.state, "talk")
            self._check_npc(case, npc_id)
            entering = saved.state.phase != Phase.INTERROGATION
            after = transition(saved.state, "talk", npc_id)
            return Decision(
                after,
                "SET_INTERROGATION",
                self._summary,
                status_code=201 if entering else 200,
                target_character_id=npc_id,
                location=f"/api/v1/sessions/{session_id}/interrogation" if entering else None,
                input_json={"npc_id": npc_id},
            )

        return self._execute(visitor_id, session_id, command, "SET_INTERROGATION", handler)

    def end_interrogation(self, visitor_id, session_id, command: Command):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            state = saved.state
            if state.phase == Phase.ACCUSATION:
                raise GameError(f"当前阶段 {state.phase.value} 不能执行此操作。")
            after = state if state.phase in views.INVESTIGATING else transition(state, "back")
            return Decision(after, "END_INTERROGATION", self._summary, 200)

        return self._execute(visitor_id, session_id, command, "END_INTERROGATION", handler)

    def chat(self, visitor_id, session_id, command: Command, npc_id: str, message: str):
        def handler(case: Case, saved: SavedGame, request: ActionRequest) -> Decision:
            guard(saved.state, "ask")
            self._check_npc(case, npc_id)
            if saved.state.active_npc_id != npc_id:
                raise ApiProblem("ACTIVE_NPC_MISMATCH", "只能与当前审讯的角色对话。")
            reply = current_statement(case, saved.state, npc_id)

            def conversation(
                _case: Case, stored: ActionRequest, after: SavedGame, data: dict
            ) -> ConversationInput:
                return ConversationInput(
                    action=stored,
                    character_id=npc_id,
                    interaction_type="CHAT",
                    source_state_version=after.state.version,
                    fixed_reply=data["fixed_reply"],
                    player_message=message,
                    npc_message=data["fixed_reply"],
                    now=datetime.now(UTC),
                )

            return Decision(
                saved.state,
                "CHAT",
                lambda *_: {"npc_id": npc_id, "fixed_reply": reply},
                conversation=conversation,
                conversation_data=lambda view, _data: {"conversation_id": view["conversation_id"]},
                generation_npc=npc_id,
            )

        return self._submit_task(self._execute(visitor_id, session_id, command, "CHAT", handler))

    def reply_retry(self, visitor_id, session_id, command: Command, conversation_id: uuid.UUID):
        return self._submit_task(
            self._reply_retry(visitor_id, session_id, command, conversation_id)
        )

    def _reply_retry(self, visitor_id, session_id, command: Command, conversation_id: uuid.UUID):
        """Explicit retry (spec 6.5): re-queue one failed round; rules stay untouched."""
        runtime = self._generation()
        now = datetime.now(UTC)
        with self._sessions() as db, db.begin():
            repository = SessionRepository(db)
            replay = self._replay(repository, visitor_id, command)
            if replay:
                return replay
            repository, row, template, case, saved = self._load_owned(
                db, visitor_id, session_id, lock=True
            )
            replay = self._replay(repository, visitor_id, command)
            if replay:
                return replay
            request = self._new_request(visitor_id, command, "REPLY_RETRY", session_id, now)
            try:
                if not self._is_current(db, visitor_id, session_id):
                    raise ApiProblem("SESSION_NOT_CURRENT", "这是已被替换的旧局，只能查看。")
                if row.state_version != command.expected_version:
                    raise ApiProblem(
                        "STATE_VERSION_CONFLICT",
                        "游戏进度已更新，请刷新后重试。",
                        {
                            "expected_state_version": command.expected_version,
                            "current_state_version": row.state_version,
                        },
                    )
                found = repository.find_conversation(session_id, conversation_id)
                if found is None:
                    raise ApiProblem("CONVERSATION_NOT_FOUND", "没有找到该对话轮次。")
                conversation, _ = found
                repository.expire_pending(session_id, now)
                attempts = repository.conversation_attempts(conversation_id)
                latest = attempts[-1] if attempts else None
                retry_ok = can_retry_reply(
                    conversation.generation_status,
                    conversation.fallback_reason,
                    latest.error_code if latest else None,
                    (latest.usage_json or {}).get("retry_after_seconds") if latest else None,
                    latest.finished_at if latest else None,
                    len(attempts),
                    saved.state,
                    True,
                    conversation.character_id,
                    conversation.source_state_version,
                    now,
                )
                if not retry_ok:
                    raise ApiProblem("REPLY_RETRY_NOT_ALLOWED", "该轮回复当前不能重试。")
                if repository.has_other_pending(session_id, conversation_id):
                    pending = repository.pending_round(session_id)
                    raise ApiProblem(
                        "GENERATION_BUSY",
                        "上一条回复还在生成中，等它完成或失效后再继续。",
                        {"conversation_id": str(pending.conversation_id)} if pending else None,
                    )
                config = runtime.config if runtime else None
                if config is None or runtime.gateway is None:
                    raise ApiProblem("REPLY_RETRY_NOT_ALLOWED", "当前没有可用的生成通道。")
                calls, tokens = usage_of(db, session_id)
                if calls >= config.call_limit or tokens >= config.token_limit:
                    raise ApiProblem(
                        "GENERATION_BUDGET_EXHAUSTED",
                        "本局的生成额度已用完，只能使用固定回复。",
                        retryable=True,
                    )
                conversation.generation_status = "PREPARING"
                conversation.generation_deadline_at = now + timedelta(
                    seconds=config.timeout_seconds
                )
                conversation.fallback_reason = None
                conversation.completed_at = None
                conversation.active_attempt_id = None
                request.status = "COMMITTED"
                request.http_status = 201
                repository.add_request(request)
                after = repository.load(row, case)
                result = self._action_result(
                    command, request, saved, after, {"conversation_id": str(conversation_id)}
                )
                result["conversation"] = repository.conversation_view(
                    conversation, request, after.state, True
                )
                result["state_changed"] = False
                return self._finish(
                    request,
                    result,
                    after,
                    f"/api/v1/requests/{command.request_id}",
                    _generation_task(
                        self._sessions,
                        self._catalog,
                        conversation_id,
                        runtime.gateway,
                        request.action_id,
                    ),
                )
            except ApiProblem as problem:
                return self._reject(repository, request, problem)

    @staticmethod
    def _interrogation_data(
        case: Case, done: SavedGame, before: SavedGame, code: str, label: str, reply: str
    ):
        reason, summary, reply = outcome_text(
            case, code, before.state, done.state, label, reply, _npc_name(case, done)
        )
        disclosed = sorted(done.state.disclosed_knowledge - before.state.disclosed_knowledge)
        active = done.state.active_npc_id
        return reply, {
            "reason_code": _public(reason),
            "summary": summary,
            "new_evidence": [],
            "updated_evidence": [],
            "disclosed_information": [views.known_information(case, done, k) for k in disclosed],
            "unlocked_scenes": [],
            "relationships_changed": False,
            "timeline_changed": False,
            "npc": views.npc_view(case, done, active) if active else None,
        }

    def ask_topic(self, visitor_id, session_id, command: Command, npc_id: str, topic_id: str):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            guard(saved.state, "topic")
            self._check_npc(case, npc_id)
            after = rules.ask_topic(case, saved.state, npc_id, topic_id)

            def data(before: SavedGame, done: SavedGame, _template) -> dict:
                topic = next(t for t in case.interrogation.topics if t.id == topic_id)
                code = rules.topic_outcome(case, before.state, topic.knowledge_id)
                reply, result = self._interrogation_data(case, done, before, code, "", topic.reply)
                return {
                    "npc_id": npc_id,
                    "topic_id": topic_id,
                    "fixed_reply": reply,
                    "outcome": result,
                }

            return Decision(
                after,
                "ASK_TOPIC",
                data,
                target_character_id=npc_id,
                input_json={"npc_id": npc_id, "topic_id": topic_id},
            )

        return self._execute(visitor_id, session_id, command, "ASK_TOPIC", handler)

    def present(
        self, visitor_id, session_id, command: Command, npc_id: str, evidence_id: str, comment
    ):
        def handler(case: Case, saved: SavedGame, request: ActionRequest) -> Decision:
            guard(saved.state, "present")
            self._check_npc(case, npc_id)
            after = rules.present(case, saved.state, npc_id, evidence_id)

            def data(before: SavedGame, done: SavedGame, _template) -> dict:
                code = rules.present_outcome(case, before.state, done.state, npc_id, evidence_id)
                label = f"这份材料和{_npc_name(case, done)}现在的说法无关。"
                reply, result = self._interrogation_data(
                    case, done, before, code, label, current_statement(case, done.state, npc_id)
                )
                return {
                    "npc_id": npc_id,
                    "evidence_id": evidence_id,
                    "fixed_reply": reply,
                    "outcome": result,
                }

            def conversation(
                conv_case: Case, stored: ActionRequest, done: SavedGame, conv_data: dict
            ) -> ConversationInput:
                evidence = next(e for e in conv_case.evidence if e.id == evidence_id)
                lines = [f"出示证据：{evidence.id} {evidence.title}"]
                if comment:
                    lines.append(f"附言：{comment}")
                return ConversationInput(
                    action=stored,
                    character_id=npc_id,
                    interaction_type="EVIDENCE_PRESENTATION",
                    source_state_version=done.state.version,
                    fixed_reply=conv_data["fixed_reply"],
                    player_message="\n".join(lines),
                    npc_message=conv_data["fixed_reply"],
                    now=datetime.now(UTC),
                )

            return Decision(
                after,
                "PRESENT_EVIDENCE",
                data,
                target_character_id=npc_id,
                presented_evidence_id=evidence_id,
                input_json={"npc_id": npc_id, "evidence_id": evidence_id},
                conversation=conversation,
                generation_npc=npc_id,
            )

        return self._submit_task(
            self._execute(visitor_id, session_id, command, "PRESENT_EVIDENCE", handler)
        )

    def point_contradiction(
        self,
        visitor_id,
        session_id,
        command: Command,
        npc_id: str,
        knowledge_id: str,
        evidence_id: str,
    ):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            guard(saved.state, "contradict")
            self._check_npc(case, npc_id)
            after = rules.contradict(case, saved.state, npc_id, knowledge_id, evidence_id)

            def data(before: SavedGame, done: SavedGame, _template) -> dict:
                match = rules.find_contradiction(case, npc_id, knowledge_id, evidence_id)
                code = rules.contradiction_outcome(
                    case, before.state, done.state, match is not None
                )
                label = f"矛盾成立：{match.explanation}" if match else "这两项之间看不出矛盾。"
                reply, result = self._interrogation_data(
                    case, done, before, code, label, match.reply if match else ""
                )
                return {
                    "npc_id": npc_id,
                    "knowledge_id": knowledge_id,
                    "evidence_id": evidence_id,
                    "fixed_reply": reply,
                    "outcome": result,
                }

            return Decision(
                after,
                "POINT_CONTRADICTION",
                data,
                target_character_id=npc_id,
                input_json={
                    "npc_id": npc_id,
                    "knowledge_id": knowledge_id,
                    "evidence_id": evidence_id,
                },
            )

        return self._execute(visitor_id, session_id, command, "POINT_CONTRADICTION", handler)

    def save_draft(self, visitor_id, session_id, command: Command, content: dict):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            draft = AccusationDraft(
                culprit=content["suspect_character_id"],
                weapon=content["weapon_option_id"],
                motive=content["motive_option_id"],
                steps=tuple(content["ordered_process_step_ids"]),
                cited_evidence_ids=tuple(content["cited_evidence_ids"]),
                evidence_links=tuple(
                    StepEvidenceLink(step_id=link["step_id"], evidence_id=link["evidence_id"])
                    for link in content["step_evidence_links"]
                ),
                explanation=content["explanation"],
            )
            after = rules.save_draft(case, saved.state, draft)
            return Decision(
                after,
                "SAVE_ACCUSATION_DRAFT",
                lambda _before, done, _template: views.draft_view(done),
                status_code=200,
                input_json={"draft_culprit": draft.culprit},
            )

        return self._execute(visitor_id, session_id, command, "SAVE_ACCUSATION_DRAFT", handler)

    def open_accusation(self, visitor_id, session_id, command: Command):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            if saved.state.phase == Phase.ACCUSATION:
                return Decision(saved.state, "OPEN_ACCUSATION", self._summary, 200)
            after = transition(saved.state, "accuse")
            return Decision(
                after,
                "OPEN_ACCUSATION",
                self._summary,
                location=f"/api/v1/sessions/{session_id}/accusation-preparation",
            )

        return self._execute(visitor_id, session_id, command, "OPEN_ACCUSATION", handler)

    def cancel_accusation(self, visitor_id, session_id, command: Command):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            state = saved.state
            if state.phase == Phase.INTERROGATION:
                raise GameError(f"当前阶段 {state.phase.value} 不能执行此操作。")
            after = state if state.phase in views.INVESTIGATING else transition(state, "back")
            return Decision(after, "CANCEL_ACCUSATION", self._summary, 200)

        return self._execute(visitor_id, session_id, command, "CANCEL_ACCUSATION", handler)

    def submit_accusation(
        self, visitor_id, session_id, command: Command, content: dict, confirm: bool
    ):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            if saved.state.verdict is not None:
                raise ApiProblem("ACCUSATION_ALREADY_SUBMITTED", "本局已经正式结案，不能再次指控。")
            guard(saved.state, "submit")
            if not confirm:
                raise ApiProblem("CONFIRMATION_REQUIRED", "正式提交前需要明确确认。")
            complete = (
                content["suspect_character_id"] is not None
                and content["weapon_option_id"] is not None
                and content["motive_option_id"] is not None
                and len(content["ordered_process_step_ids"]) > 0
            )
            if not complete:
                raise ApiProblem(
                    "ACCUSATION_INCOMPLETE", "正式指控必须填写凶手、凶器、动机和至少一个过程步骤。"
                )
            accusation = Accusation(
                culprit=content["suspect_character_id"],
                weapon=content["weapon_option_id"],
                motive=content["motive_option_id"],
                steps=tuple(content["ordered_process_step_ids"]),
                cited_evidence_ids=tuple(content["cited_evidence_ids"]),
                evidence_links=tuple(
                    StepEvidenceLink(step_id=link["step_id"], evidence_id=link["evidence_id"])
                    for link in content["step_evidence_links"]
                ),
                explanation=content["explanation"],
            )
            after = rules.judge(case, saved.state, accusation)
            return Decision(
                after,
                "SUBMIT_ACCUSATION",
                lambda _before, done, _template: views.accusation_view(done),
                location=f"/api/v1/sessions/{session_id}/accusation",
                input_json={"suspect_character_id": accusation.culprit},
            )

        return self._execute(visitor_id, session_id, command, "SUBMIT_ACCUSATION", handler)

    def finish_review(self, visitor_id, session_id, command: Command):
        def handler(case: Case, saved: SavedGame, _request) -> Decision:
            if saved.state.phase == Phase.FINISHED:
                return Decision(saved.state, "FINISH_REVIEW", self._summary, 200)
            after = transition(saved.state, "finish")
            return Decision(
                after,
                "FINISH_REVIEW",
                self._summary,
                location=f"/api/v1/sessions/{session_id}/review-completion",
            )

        return self._execute(visitor_id, session_id, command, "FINISH_REVIEW", handler)


def _npc_name(case: Case, saved: SavedGame) -> str:
    npc_id = saved.state.active_npc_id
    return next((c.name for c in case.characters if c.id == npc_id), npc_id or "")


def _generation_task(
    sessions: sessionmaker[Session],
    catalog: CaseCatalog,
    conversation_id: uuid.UUID,
    gateway,
    request_action_id: uuid.UUID,
) -> Callable[[], None]:
    def task() -> None:
        run_generation_task(sessions, catalog, conversation_id, gateway, request_action_id)

    return task
