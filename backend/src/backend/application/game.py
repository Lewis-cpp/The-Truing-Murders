from dataclasses import replace

from backend.application.case import validate_case
from backend.domain import rules
from backend.domain.evidence import (
    current_statement,
    fixed_review,
    outcome_text,
    player_view,
    validate_accusation,
)
from backend.domain.models import (
    Accusation,
    Case,
    GameError,
    GameState,
    NPCState,
    Phase,
)
from backend.domain.state_machine import evading, guard, transition


class Game:
    """One local session. Commit immutable candidates only after all validation succeeds."""

    def __init__(self, case: Case):
        validate_case(case)
        self._case = case
        self._state = GameState(npc=NPCState(case.npc.initial_pressure, case.npc.initial_trust))

    @property
    def state(self) -> GameState:
        return self._state

    @property
    def evading(self) -> bool:
        return evading(self._case, self._state.npc)

    def view(self) -> dict:
        return player_view(self._case, self._state)

    def _commit(self, candidate: GameState) -> bool:
        if candidate == self._state:
            return False
        self._state = replace(candidate, version=self._state.version + 1)
        return True

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
        if npc_id != self._case.npc.id:
            raise GameError("该角色不在本周可审讯范围内。")
        self._commit(transition(self._state, "talk", npc_id))
        return current_statement(self._case, self._state.npc)

    def ask(self, text: str) -> str:
        guard(self._state, "ask")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise GameError("请输入 1 至 4000 字的问题。")
        return current_statement(self._case, self._state.npc)

    def topic(self, topic_id: str) -> str:
        before = self._state
        npc_id = before.active_npc_id or ""
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
        label = f"这份材料和{self._case.npc.name}现在的说法无关。"
        return self._say(code, before, label, current_statement(self._case, self._state.npc))

    def contradict(self, knowledge_id: str, evidence_id: str) -> str:
        before = self._state
        npc_id = before.active_npc_id or ""
        self._commit(rules.contradict(self._case, before, npc_id, knowledge_id, evidence_id))
        match = rules.find_contradiction(self._case, npc_id, knowledge_id, evidence_id)
        code = rules.contradiction_outcome(self._case, before, self._state, match is not None)
        if match is None:
            return self._say(code, before, "这两项之间看不出矛盾。", "")
        return self._say(code, before, f"矛盾成立：{match.explanation}", match.reply)

    def _say(self, code: str, before: GameState, label: str, reply: str) -> str:
        _, summary, reply = outcome_text(
            self._case, code, before, self._state, label, reply, leave="back 结束审讯"
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
