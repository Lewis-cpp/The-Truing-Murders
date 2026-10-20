from backend.domain.models import (
    Accusation,
    Case,
    GameError,
    GameState,
    NPCState,
    Phase,
    Verdict,
)
from backend.domain.state_machine import evading


def require_held(state: GameState, evidence_id: str) -> None:
    if evidence_id not in state.evidence_ids:
        raise GameError("只能出示或引用已经取得的证据。", "EVIDENCE_NOT_OWNED")


def validate_accusation(case: Case, state: GameState, accusation: Accusation) -> None:
    for name, choices in (
        ("culprit", case.suspects),
        ("weapon", case.weapons),
        ("motive", case.motives),
    ):
        if getattr(accusation, name) not in {choice.id for choice in choices}:
            raise GameError("请选择候选列表中的凶手、凶器和动机。", "INVALID_ACCUSATION_OPTION")
    if not accusation.steps or not set(accusation.steps) <= {c.id for c in case.process_steps}:
        raise GameError("至少选择一个有效的过程步骤。", "INVALID_ACCUSATION_OPTION")
    for values in (accusation.steps, accusation.cited_evidence_ids):
        if len(values) != len(set(values)):
            raise GameError("步骤和引用证据不能重复。", "INVALID_ACCUSATION_OPTION")
    for evidence_id in accusation.cited_evidence_ids:
        require_held(state, evidence_id)
    pairs = [(link.step_id, link.evidence_id) for link in accusation.evidence_links]
    if len(pairs) != len(set(pairs)):
        raise GameError("步骤与证据的关联不能重复。", "INVALID_ACCUSATION_OPTION")
    for step_id, evidence_id in pairs:
        if step_id not in accusation.steps or evidence_id not in accusation.cited_evidence_ids:
            raise GameError(
                "关联只能使用本次选择的步骤和本次引用的证据。", "INVALID_ACCUSATION_OPTION"
            )


def player_view(case: Case, state: GameState) -> dict:
    """An allowlist, never a serialization of the case or its rules."""
    result = {
        "title": case.title,
        "introduction": case.introduction,
        "phase": state.phase.value,
        "scene": {"id": case.scene.id, "name": case.scene.name, "text": case.scene.description},
        "actions": [{"id": a.id, "label": a.label} for a in case.scene.actions],
        "npc": {"id": case.npc.id, "name": case.npc.name, "role": case.npc.role},
        "evidence": [e.model_dump() for e in case.evidence if e.id in state.evidence_ids],
        "knowledge": [
            {"id": k.id, "content": k.content, "credibility": "UNVERIFIED", "source": case.npc.name}
            for k in case.knowledge
            if k.disclosure == "PUBLIC" or k.id in state.disclosed_knowledge
        ],
        "topics": [
            {"id": t.id, "label": t.label, "asked": t.knowledge_id in state.disclosed_knowledge}
            for t in case.interrogation.topics
        ],
        "choices": {
            name: [choice.model_dump() for choice in getattr(case, name)]
            for name in ("suspects", "weapons", "motives", "process_steps")
        },
    }
    if state.verdict is not None and state.phase in {Phase.REVIEW, Phase.FINISHED}:
        result["truth"] = case.truth.explanation
    return result


def current_statement(case: Case, npc: NPCState) -> str:
    """What the NPC says now: the evasion line while evading, else the lie stage's statement."""
    if evading(case, npc):
        return case.interrogation.evade_reply
    return getattr(case.lie.statements, npc.lie_stage.value.lower())


FIXED_SUMMARIES = {
    "TOPIC_ALREADY_ASKED": "这个问题已经问过，证词仍在记录中。",
    "TESTIMONY_RECORDED": "证词已记录（未经核验）。",
    "ADMISSION_RECORDED": "承认已记录（未经独立核验的证词）。",
    "LIE_BROKEN": "谎言已击破。",
    "ALREADY_PRESENTED": "已经出示过，未重复增加收益。",
    "EVIDENCE_RECORDED": "出示已记录。",
    "CONTRADICTION_ALREADY_POINTED": "这个矛盾已经指出过，不会重复产生效果。",
}


def outcome_text(
    case: Case,
    code: str,
    before: GameState,
    after: GameState,
    label: str,
    reply: str,
    leave: str = "结束审讯",
) -> tuple[str, str, str]:
    """(reason code, summary, reply) for an outcome code. `label` is the move's own words for
    codes without a fixed summary. Costs are described, never shown as numbers."""
    name, policy = case.npc.name, case.interrogation
    if code == "NPC_EVADING":
        return code, f"{name}在回避，暂时问不出什么；{leave}后再来。", policy.evade_reply
    if code == "EVASION_STARTED":
        summary = f"{label}连续的无关操作让{name}开始回避；{leave}后再来。"
        return "NPC_EVADING", summary, policy.evade_reply
    if code == "IRRELEVANT_MOVE":
        if after.npc.trust < before.npc.trust:
            label += f"{name}对你更戒备了。"
        return code, label, policy.irrelevant_reply
    return code, FIXED_SUMMARIES.get(code, label), reply


def fixed_review(case: Case, verdict: Verdict) -> str:
    lines = [f"结案：{verdict.category} · {verdict.score}/100"]
    lines.extend(f"{c.label} {c.points}/{c.maximum}：{c.explanation}" for c in verdict.criteria)
    lines.extend(["案情复盘", case.truth.explanation])
    lines.append("复盘不会补发遗漏证据，证词与调查记录已经冻结。")
    return "\n".join(lines)


def npc_view(case: Case, state: GameState, npc_id: str) -> dict:
    """Fixed dialogue projection only; no Agent or model context is created."""
    if npc_id != case.npc.id or state.active_npc_id != npc_id:
        raise GameError("请先进入该角色的审讯。", "ACTIVE_NPC_MISMATCH")
    statement = current_statement(case, state.npc)
    return {
        "name": case.npc.name,
        "statement": statement,
        "knowledge": [
            k.content
            for k in case.knowledge
            if npc_id in k.known_by
            and (k.disclosure == "PUBLIC" or k.id in state.disclosed_knowledge)
        ],
        "presented": [e.model_dump() for e in case.evidence if e.id in state.npc.presented],
    }
