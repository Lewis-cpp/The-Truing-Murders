"""Local session for the command line. Commit immutable candidates only after validation."""

from dataclasses import replace

from backend.domain import rules
from backend.domain.evidence import (
    current_statement,
    fixed_review,
    knowledge_speaker,
    outcome_text,
    validate_accusation,
)
from backend.domain.models import (
    Accusation,
    Case,
    GameError,
    GameState,
    Phase,
)
from backend.domain.state_machine import evading, guard, transition


class Game:
    def __init__(self, case: Case):
        from backend.application.case import validate_case

        validate_case(case)
        self._case = case
        self._state = rules.new_game(case)

    @property
    def state(self) -> GameState:
        return self._state

    @property
    def case(self) -> Case:
        return self._case

    @property
    def evading(self) -> bool:
        npc = self._state.npcs.get(self._state.active_npc_id) if self._state.active_npc_id else None
        return npc is not None and evading(self._case, npc)

    def view(self) -> dict:
        """An allowlist for the terminal, never a serialization of the case or its rules."""
        state = self._state
        case = self._case
        open_ids = set(rules.open_scenes(case, state))
        npc_id = state.active_npc_id
        from backend.domain.state_machine import display_state

        view = {
            "title": case.title,
            "introduction": case.introduction,
            "phase": state.phase.value,
            "scenes": [
                {
                    "id": scene.id,
                    "name": scene.name,
                    "text": scene.description,
                    "actions": [{"id": a.id, "label": a.label} for a in scene.actions],
                }
                for scene in case.scenes
                if scene.id in open_ids
            ],
            "npcs": [
                {
                    "id": c.id,
                    "name": c.name,
                    "role": c.public_identity,
                    "state": display_state(case, state, c.id),
                    "statement": current_statement(case, state, c.id) if c.id == npc_id else None,
                }
                for c in case.characters
                if c.interrogatable
            ],
            "evidence": [
                {
                    "id": e.id,
                    "title": e.title,
                    "content": e.content,
                    "source": e.source,
                    "credibility": e.credibility,
                    "kind": e.kind,
                    "key_badge": case.show_key_badges and e.is_key,
                }
                for e in case.evidence
                if e.id in state.evidence_ids
            ],
            "knowledge": [
                {
                    "id": k.id,
                    "content": k.content,
                    "credibility": "UNVERIFIED",
                    "source": "案件公开信息"
                    if k.disclosure == "PUBLIC"
                    else next(
                        c.name for c in case.characters if c.id == knowledge_speaker(case, k.id)
                    ),
                }
                for k in case.knowledge
                if k.disclosure == "PUBLIC" or k.id in state.disclosed_knowledge
            ],
            "topics": [
                {"id": t.id, "label": t.label, "asked": t.knowledge_id in state.disclosed_knowledge}
                for t in case.interrogation.topics
                if npc_id is not None and t.npc_id == npc_id
            ],
            "choices": {
                name: [choice.model_dump() for choice in getattr(case, name)]
                for name in ("suspects", "weapons", "motives", "process_steps")
            },
        }
        if state.verdict is not None and state.phase in {Phase.REVIEW, Phase.FINISHED}:
            view["truth"] = case.truth.explanation
        return view

    def _commit(self, candidate: GameState) -> bool:
        if candidate == self._state:
            return False
        self._state = replace(candidate, version=self._state.version + 1)
        return True

    def _active_name(self) -> str:
        npc_id = self._state.active_npc_id
        return next(c.name for c in self._case.characters if c.id == npc_id)

    def inspect(self, action_id: str) -> str:
        before = self._state.evidence_ids
        changed = self._commit(rules.investigate(self._case, self._state, action_id))
        if not changed:
            return "这里已经调查过，证据仍在背包中。"
        gained = self._state.evidence_ids - before
        if not gained:
            return "调查已完成，该证据已经在背包中，没有重复发放。"
        evidence = next(e for e in self._case.evidence if e.id in gained)
        return f"获得 {evidence.id} · {evidence.title}\n{evidence.content}"

    def talk(self, npc_id: str) -> str:
        guard(self._state, "talk")
        character = next((c for c in self._case.characters if c.id == npc_id), None)
        if character is None or not character.interrogatable:
            raise GameError("该角色不在本版本可审讯范围内。", "NPC_NOT_FOUND")
        self._commit(transition(self._state, "talk", npc_id))
        return current_statement(self._case, self._state, npc_id)

    def ask(self, text: str) -> str:
        guard(self._state, "ask")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise GameError("请输入 1 至 4000 字的问题。")
        npc_id = self._state.active_npc_id
        return current_statement(self._case, self._state, npc_id)

    def topic(self, topic_id: str) -> str:
        before = self._state
        npc_id = before.active_npc_id
        self._commit(rules.ask_topic(self._case, before, npc_id, topic_id))
        topic = next(t for t in self._case.interrogation.topics if t.id == topic_id)
        code = rules.topic_outcome(self._case, before, topic.knowledge_id)
        if code == "TESTIMONY_RECORDED":
            return f"证词已记录（未经核验），编号 {topic.knowledge_id}。\n{topic.reply}"
        return self._say(code, before, "", topic.reply)

    def present(self, npc_id: str, evidence_id: str) -> str:
        before = self._state
        self._commit(rules.present(self._case, before, npc_id, evidence_id))
        code = rules.present_outcome(self._case, before, self._state, npc_id, evidence_id)
        label = f"这份材料和{self._active_name()}现在的说法无关。"
        return self._say(code, before, label, current_statement(self._case, self._state, npc_id))

    def contradict(self, knowledge_id: str, evidence_id: str) -> str:
        before = self._state
        npc_id = before.active_npc_id
        self._commit(rules.contradict(self._case, before, npc_id, knowledge_id, evidence_id))
        match = rules.find_contradiction(self._case, npc_id, knowledge_id, evidence_id)
        code = rules.contradiction_outcome(self._case, before, self._state, match is not None)
        if match is None:
            return self._say(code, before, "这两项之间看不出矛盾。", "")
        return self._say(code, before, f"矛盾成立：{match.explanation}", match.reply)

    def _say(self, code: str, before: GameState, label: str, reply: str) -> str:
        _, summary, reply = outcome_text(
            self._case,
            code,
            before,
            self._state,
            label,
            reply,
            self._active_name(),
            leave="back 结束审讯",
        )
        return f"{summary}\n{reply}"

    def back(self) -> None:
        self._commit(transition(self._state, "back"))

    def accuse(self) -> None:
        self._commit(transition(self._state, "accuse"))

    def submit(self, accusation: Accusation) -> None:
        self._commit(rules.judge(self._case, self._state, accusation))

    def check_accusation(self, accusation: Accusation) -> None:
        guard(self._state, "submit")
        validate_accusation(self._case, self._state, accusation)

    def review(self) -> str:
        if self._state.phase not in {Phase.REVIEW, Phase.FINISHED} or self._state.verdict is None:
            raise GameError("正式结案后才能查看复盘。")
        return fixed_review(self._case, self._state.verdict)

    def finish(self) -> None:
        self._commit(transition(self._state, "finish"))
