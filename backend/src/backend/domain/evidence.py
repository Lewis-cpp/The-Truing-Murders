"""Domain-side presentation: validation, statements, and outcome wording."""

from backend.domain.models import (
    Accusation,
    AccusationDraft,
    Case,
    GameError,
    GameState,
    LieStage,
    Verdict,
)
from backend.domain.state_machine import evading


def require_held(state: GameState, evidence_id: str) -> None:
    if evidence_id not in state.evidence_ids:
        raise GameError("只能出示或引用已经取得的证据。", "EVIDENCE_NOT_OWNED")


def knowledge_speaker(case: Case, knowledge_id: str) -> str | None:
    """ASKED knowledge is spoken by its topic's NPC, ADMITTED by the layer that reveals it."""
    topic = next((t for t in case.interrogation.topics if t.knowledge_id == knowledge_id), None)
    if topic is not None:
        return topic.npc_id
    lie = next((lie for lie in case.lies if lie.admitted_knowledge_id == knowledge_id), None)
    if lie is not None:
        return lie.npc_id
    return None


_CANDIDATES = {"culprit": "suspects", "weapon": "weapons", "motive": "motives"}


def _check_choices(case: Case, holder, names) -> None:
    for name in names:
        value = getattr(holder, name)
        if value is None:
            continue
        choices = getattr(case, _CANDIDATES[name])
        if value not in {choice.id for choice in choices}:
            raise GameError("请选择候选列表中的凶手、凶器和动机。", "INVALID_ACCUSATION_OPTION")


def _check_links(links, steps: tuple[str, ...], cited: tuple[str, ...]) -> None:
    pairs = [(link.step_id, link.evidence_id) for link in links]
    if len(pairs) != len(set(pairs)):
        raise GameError("步骤与证据的关联不能重复。", "INVALID_ACCUSATION_OPTION")
    for step_id, evidence_id in pairs:
        if step_id not in steps or evidence_id not in cited:
            raise GameError(
                "关联只能使用本次选择的步骤和本次引用的证据。", "INVALID_ACCUSATION_OPTION"
            )


def validate_accusation(case: Case, state: GameState, accusation: Accusation) -> None:
    _check_choices(case, accusation, ("culprit", "weapon", "motive"))
    if not accusation.steps or not set(accusation.steps) <= {c.id for c in case.process_steps}:
        raise GameError("至少选择一个有效的过程步骤。", "INVALID_ACCUSATION_OPTION")
    for values in (accusation.steps, accusation.cited_evidence_ids):
        if len(values) != len(set(values)):
            raise GameError("步骤和引用证据不能重复。", "INVALID_ACCUSATION_OPTION")
    for evidence_id in accusation.cited_evidence_ids:
        require_held(state, evidence_id)
    _check_links(accusation.evidence_links, accusation.steps, accusation.cited_evidence_ids)


def validate_draft(case: Case, state: GameState, draft: AccusationDraft) -> None:
    """A draft may stay partial, but every filled part must already be legal."""
    _check_choices(case, draft, ("culprit", "weapon", "motive"))
    if len(draft.steps) != len(set(draft.steps)) or not set(draft.steps) <= {
        c.id for c in case.process_steps
    }:
        raise GameError("过程步骤必须在候选列表中且不能重复。", "INVALID_ACCUSATION_OPTION")
    if len(draft.cited_evidence_ids) != len(set(draft.cited_evidence_ids)):
        raise GameError("引用证据不能重复。", "INVALID_ACCUSATION_OPTION")
    for evidence_id in draft.cited_evidence_ids:
        require_held(state, evidence_id)
    _check_links(draft.evidence_links, draft.steps, draft.cited_evidence_ids)


def current_statement(
    case: Case, state: GameState, npc_id: str, *, ignore_evasion: bool = False
) -> str:
    """What the NPC says now: the evasion line, each chain's current line, or the default.

    The memory fingerprint computes this with ignore_evasion=True so that mood alone
    never looks like an authorization change."""
    npc = state.npcs[npc_id]
    if not ignore_evasion and evading(case, npc):
        return case.interrogation.evade_reply
    chains = [chain for chain in case.lie_chains if chain.npc_id == npc_id]
    if not chains:
        character = next(c for c in case.characters if c.id == npc_id)
        return character.default_reply or ""
    lines = []
    for chain in chains:
        current = next((lid for lid in chain.lie_ids if npc.lies[lid] != LieStage.ADMITTED), None)
        lie = next(lie for lie in case.lies if lie.id == (current or chain.lie_ids[-1]))
        if current is None:
            lines.append(lie.statements.admitted)
        else:
            lines.append(getattr(lie.statements, npc.lies[current].value.lower()))
    return "\n".join(lines)


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
    npc_name: str,
    leave: str = "结束审讯",
) -> tuple[str, str, str]:
    """(reason code, summary, reply) for an outcome code. `label` is the move's own words for
    codes without a fixed summary. Costs are described, never shown as numbers."""
    policy = case.interrogation
    if code == "NPC_EVADING":
        return code, f"{npc_name}在回避，暂时问不出什么；{leave}后再来。", policy.evade_reply
    if code == "EVASION_STARTED":
        summary = f"{label}连续的无关操作让{npc_name}开始回避；{leave}后再来。"
        return "NPC_EVADING", summary, policy.evade_reply
    if code == "IRRELEVANT_MOVE":
        after_npc = after.npcs[after.active_npc_id] if after.active_npc_id else None
        before_npc = before.npcs[before.active_npc_id] if before.active_npc_id else None
        if after_npc is not None and before_npc is not None and after_npc.trust < before_npc.trust:
            label += f"{npc_name}对你更戒备了。"
        return code, label, policy.irrelevant_reply
    return code, FIXED_SUMMARIES.get(code, label), reply


def fixed_review(case: Case, verdict: Verdict) -> str:
    lines = [f"结案：{verdict.category} · {verdict.score}/100"]
    lines.extend(f"{c.label} {c.points}/{c.maximum}：{c.explanation}" for c in verdict.criteria)
    lines.extend(["案情复盘", case.truth.explanation])
    lines.append("复盘不会补发遗漏证据，证词与调查记录已经冻结。")
    return "\n".join(lines)
