from dataclasses import replace

from backend.application.case import validate_case
from backend.domain import rules
from backend.domain.evidence import npc_view, player_view, validate_accusation
from backend.domain.models import Accusation, Case, GameError, GameState, NPCState, Phase
from backend.domain.state_machine import guard, transition


class Game:
    """One local session. Commit immutable candidates only after all validation succeeds."""

    def __init__(self, case: Case):
        validate_case(case)
        self._case = case
        self._state = GameState(npc=NPCState(case.npc.initial_pressure, case.npc.initial_trust))

    @property
    def state(self) -> GameState:
        return self._state

    def view(self) -> dict:
        return player_view(self._case, self._state)

    def _commit(self, candidate: GameState, event: str) -> bool:
        if candidate == self._state:
            return False
        self._state = replace(
            candidate,
            version=self._state.version + 1,
            history=(*self._state.history, event),
        )
        return True

    def inspect(self, action_id: str) -> str:
        before = self._state.evidence_ids
        changed = self._commit(rules.investigate(self._case, self._state, action_id), action_id)
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
        self._commit(transition(self._state, "talk", npc_id), f"talk:{npc_id}")
        return npc_view(self._case, self._state, npc_id)["statement"]

    def ask(self, text: str) -> str:
        guard(self._state, "ask")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise GameError("请输入 1 至 4000 字的问题。")
        return npc_view(self._case, self._state, self._case.npc.id)["statement"]

    def present(self, npc_id: str, evidence_id: str) -> str:
        old_stage = self._state.npc.lie_stage
        changed = self._commit(
            rules.present(self._case, self._state, npc_id, evidence_id),
            f"present:{npc_id}:{evidence_id}",
        )
        reply = npc_view(self._case, self._state, npc_id)["statement"]
        if old_stage != self._state.npc.lie_stage:
            label = (
                "承认已记录（未经独立核验的证词）"
                if self._state.disclosed_knowledge
                else "谎言已击破"
            )
            return f"{label}。\n{reply}"
        prefix = "出示已记录。" if changed else "已经出示过，未重复增加收益。"
        return f"{prefix}\n{reply}"

    def back(self) -> None:
        self._commit(transition(self._state, "back"), "back")

    def accuse(self) -> None:
        self._commit(transition(self._state, "accuse"), "accuse")

    def submit(self, accusation: Accusation) -> None:
        self._commit(rules.judge(self._case, self._state, accusation), "submit")

    def check_accusation(self, accusation: Accusation) -> None:
        guard(self._state, "submit")
        validate_accusation(self._case, self._state, accusation)

    def review(self) -> str:
        if self._state.phase not in {Phase.REVIEW, Phase.FINISHED} or self._state.verdict is None:
            raise GameError("正式结案后才能查看复盘。")
        verdict = self._state.verdict
        lines = [f"结案：{verdict.category} · {verdict.score}/100"]
        lines.extend(f"{c.label} {c.points}/{c.maximum}：{c.explanation}" for c in verdict.criteria)
        lines.extend(["案情复盘", self._case.truth.explanation])
        lines.append("复盘不会补发遗漏证据，证词与调查记录已经冻结。")
        return "\n".join(lines)

    def finish(self) -> None:
        self._commit(transition(self._state, "finish"), "finish")
