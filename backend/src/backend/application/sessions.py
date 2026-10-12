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
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from backend.application import views
from backend.application.catalog import CaseCatalog
from backend.application.errors import ApiProblem
from backend.domain import rules
from backend.domain.models import (
    Accusation,
    Case,
    GameError,
    GameState,
    LieStage,
    Phase,
    StepEvidenceLink,
)
from backend.domain.state_machine import guard, transition
from backend.infrastructure.database.models import ActionRequest, CaseTemplate, Visitor
from backend.infrastructure.database.repositories.case_repository import CaseRepository
from backend.infrastructure.database.repositories.session_repository import (
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


@dataclass
class Decision:
    """What a handler decided; data is projected after saving, inside the same transaction."""

    after: GameState
    event_type: str
    data: Callable[[SavedGame, SavedGame, CaseTemplate], dict]
    status_code: int = 201
    target_character_id: str | None = None
    presented_evidence_id: str | None = None
    location: str | None = None
    input_json: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VisitorAccess:
    visitor_id: uuid.UUID
    current_session_id: uuid.UUID | None
    new_token: str | None


def _rejection(error: GameError) -> ApiProblem:
    return ApiProblem(error.code, str(error))


class GameService:
    def __init__(self, sessions: sessionmaker[Session], catalog: CaseCatalog | None = None):
        self._sessions = sessions
        self._catalog = catalog or CaseCatalog()

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
                ]
            }

    def _load_owned(self, db: Session, visitor_id: uuid.UUID, session_id: uuid.UUID, lock=False):
        repository = SessionRepository(db)
        row = repository.get_session(visitor_id, session_id, lock=lock)
        if row is None:
            raise ApiProblem("SESSION_NOT_FOUND", "找不到该游戏存档。")
        template = repository.template(row)
        case = self._catalog.load(db, template)
        return repository, row, template, case, repository.load(row, case)

    @staticmethod
    def _is_current(db: Session, visitor_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        return db.get_one(Visitor, visitor_id).current_session_id == session_id

    def session_view(self, visitor_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        with self._read() as db:
            _, row, template, case, saved = self._load_owned(db, visitor_id, session_id)
            return views.session_view(
                case, template, saved, self._is_current(db, visitor_id, row.session_id)
            )

    def current_session(self, visitor_id: uuid.UUID) -> dict:
        with self._read() as db:
            current = db.get_one(Visitor, visitor_id).current_session_id
            if current is None:
                return {"current_session_id": None, "session": None}
            _, _, template, case, saved = self._load_owned(db, visitor_id, current)
            return {
                "current_session_id": str(current),
                "session": views.session_view(case, template, saved, True),
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
                if template.status != "PUBLISHED":
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
    def _finish(request: ActionRequest, result: dict, saved: SavedGame, location):
        if location:
            result["_location"] = location
        request.result_json = result
        request.result_state_version = saved.state.version
        request.completed_at = datetime.now(UTC)
        return CommandResponse(request.http_status, result, location)

    # Generic command execution

    def _execute(
        self,
        visitor_id: uuid.UUID,
        session_id: uuid.UUID,
        command: Command,
        command_type: str,
        handler: Callable[[Case, SavedGame], Decision],
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
                try:
                    decision = handler(case, before)
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
            after = repository.load(row, case)
            data = decision.data(before, after, template)
            result = self._action_result(command, request, before, after, data)
            location = decision.location or f"/api/v1/requests/{command.request_id}"
            return self._finish(request, result, after, location)

    @staticmethod
    def _outcome(before: GameState, after: GameState) -> dict:
        return {
            "phase": [before.phase.value, after.phase.value],
            "active_npc_id": [before.active_npc_id, after.active_npc_id],
            "new_evidence_ids": sorted(after.evidence_ids - before.evidence_ids),
            "completed_action_ids": sorted(after.completed_actions - before.completed_actions),
            "pressure": [before.npc.pressure, after.npc.pressure],
            "trust": [before.npc.trust, after.npc.trust],
            "lie_stage": [before.npc.lie_stage.value, after.npc.lie_stage.value],
            "disclosed_knowledge_ids": sorted(
                after.disclosed_knowledge - before.disclosed_knowledge
            ),
            "consumed_effect_keys": sorted(after.consumed_effects - before.consumed_effects),
        }

    @staticmethod
    def _summary(_before: SavedGame, after: SavedGame, template: CaseTemplate) -> dict:
        return views.session_summary(template, after, True)

    # Commands

    def investigate(self, visitor_id, session_id, command: Command, scene_id: str, action_id: str):
        def handler(case: Case, saved: SavedGame) -> Decision:
            if scene_id != case.scene.id:
                raise ApiProblem("SCENE_NOT_FOUND", "场景不存在或尚未开放。")
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
                return {
                    "scene_id": scene_id,
                    "action_id": action_id,
                    "outcome": {
                        "reason_code": reason,
                        "summary": summary,
                        "new_evidence": [views.evidence_view(case, done, e) for e in gained],
                        "disclosed_information": [],
                        "npc": None,
                    },
                }

            return Decision(after, "INVESTIGATE", data, input_json={"action_id": action_id})

        return self._execute(visitor_id, session_id, command, "INVESTIGATE", handler)

    def _check_npc(self, case: Case, npc_id: str) -> None:
        if npc_id == case.npc.id:
            return
        if npc_id in {c.id for c in case.suspects}:
            raise ApiProblem("NPC_UNAVAILABLE", "该角色本版本暂不可审讯。")
        raise ApiProblem("NPC_NOT_FOUND", "找不到该角色。")

    def set_interrogation(self, visitor_id, session_id, command: Command, npc_id: str):
        def handler(case: Case, saved: SavedGame) -> Decision:
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
        def handler(case: Case, saved: SavedGame) -> Decision:
            state = saved.state
            if state.phase == Phase.ACCUSATION:
                raise GameError(f"当前阶段 {state.phase.value} 不能执行此操作。")
            after = state if state.phase in views.INVESTIGATING else transition(state, "back")
            return Decision(after, "END_INTERROGATION", self._summary, 200)

        return self._execute(visitor_id, session_id, command, "END_INTERROGATION", handler)

    def chat(self, visitor_id, session_id, command: Command, npc_id: str):
        def handler(case: Case, saved: SavedGame) -> Decision:
            guard(saved.state, "ask")
            self._check_npc(case, npc_id)
            if saved.state.active_npc_id != npc_id:
                raise ApiProblem("ACTIVE_NPC_MISMATCH", "只能与当前审讯的角色对话。")
            reply = views.fixed_statement(case, saved.state.npc.lie_stage)
            return Decision(
                saved.state, "CHAT", lambda *_: {"npc_id": npc_id, "fixed_reply": reply}
            )

        return self._execute(visitor_id, session_id, command, "CHAT", handler)

    def present(self, visitor_id, session_id, command: Command, npc_id: str, evidence_id: str):
        def handler(case: Case, saved: SavedGame) -> Decision:
            guard(saved.state, "present")
            self._check_npc(case, npc_id)
            after = rules.present(case, saved.state, npc_id, evidence_id)

            def data(before: SavedGame, done: SavedGame, _template) -> dict:
                old_stage, new_stage = before.state.npc.lie_stage, done.state.npc.lie_stage
                if new_stage != old_stage and new_stage == LieStage.ADMITTED:
                    reason, summary = "ADMISSION_RECORDED", "承认已记录（未经独立核验的证词）。"
                elif new_stage != old_stage:
                    reason, summary = "LIE_BROKEN", "谎言已击破。"
                elif done.state.version != before.state.version:
                    reason, summary = "EVIDENCE_RECORDED", "出示已记录。"
                else:
                    reason, summary = "ALREADY_PRESENTED", "已经出示过，未重复增加收益。"
                disclosed = sorted(
                    done.state.disclosed_knowledge - before.state.disclosed_knowledge
                )
                return {
                    "npc_id": npc_id,
                    "evidence_id": evidence_id,
                    "fixed_reply": views.fixed_statement(case, new_stage),
                    "outcome": {
                        "reason_code": reason,
                        "summary": summary,
                        "new_evidence": [],
                        "disclosed_information": [
                            views.known_information(case, done, k) for k in disclosed
                        ],
                        "npc": views.npc_view(case, done),
                    },
                }

            return Decision(
                after,
                "PRESENT_EVIDENCE",
                data,
                target_character_id=npc_id,
                presented_evidence_id=evidence_id,
                input_json={"npc_id": npc_id, "evidence_id": evidence_id},
            )

        return self._execute(visitor_id, session_id, command, "PRESENT_EVIDENCE", handler)

    def open_accusation(self, visitor_id, session_id, command: Command):
        def handler(case: Case, saved: SavedGame) -> Decision:
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
        def handler(case: Case, saved: SavedGame) -> Decision:
            state = saved.state
            if state.phase == Phase.INTERROGATION:
                raise GameError(f"当前阶段 {state.phase.value} 不能执行此操作。")
            after = state if state.phase in views.INVESTIGATING else transition(state, "back")
            return Decision(after, "CANCEL_ACCUSATION", self._summary, 200)

        return self._execute(visitor_id, session_id, command, "CANCEL_ACCUSATION", handler)

    def submit_accusation(
        self, visitor_id, session_id, command: Command, content: dict, confirm: bool
    ):
        def handler(case: Case, saved: SavedGame) -> Decision:
            if saved.state.verdict is not None:
                raise ApiProblem("ACCUSATION_ALREADY_SUBMITTED", "本局已经正式结案，不能再次指控。")
            guard(saved.state, "submit")
            if not confirm:
                raise ApiProblem("CONFIRMATION_REQUIRED", "正式提交前需要明确确认。")
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
        def handler(case: Case, saved: SavedGame) -> Decision:
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
