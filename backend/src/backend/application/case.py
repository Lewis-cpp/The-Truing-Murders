import hashlib
import json
from itertools import permutations
from pathlib import Path

from pydantic import ValidationError

from backend.domain.models import Case, GameState, LieStage, NPCState, Phase
from backend.domain.rules import present


def default_case_path() -> Path:
    # Editable checkout and packaged wheel both carry the same versioned resource.
    package = Path(__file__).resolve().parents[1] / "case_data/case_001/v1/slice.json"
    if package.is_file():
        return package
    return Path(__file__).resolve().parents[3] / "assets/cases/case_001/v1/slice.json"


def _unique(values, label: str) -> set[str]:
    items = list(values)
    if len(items) != len(set(items)):
        raise ValueError(f"{label} 含有重复 ID。")
    return set(items)


def validate_case(case: Case) -> None:
    evidence_ids = _unique((e.id for e in case.evidence), "证据")
    _unique((a.id for a in case.scene.actions), "调查动作")
    suspects = _unique((c.id for c in case.suspects), "嫌疑人")
    weapons = _unique((c.id for c in case.weapons), "凶器")
    motives = _unique((c.id for c in case.motives), "动机")
    steps = _unique((c.id for c in case.process_steps), "步骤")
    knowledge_ids = _unique((k.id for k in case.knowledge), "知识")
    _unique((c.id for c in case.scoring.criteria), "评分项")
    _unique((e.evidence_id for e in case.lie.effects), "出示效果")
    if len(evidence_ids) != 3:
        raise ValueError("W1 切片必须恰好包含 3 条证据。")
    if case.npc.id not in suspects or case.lie.npc_id != case.npc.id:
        raise ValueError("NPC 或谎言的角色引用不存在。")
    if (
        case.truth.culprit not in suspects
        or case.truth.weapon not in weapons
        or case.truth.motive not in motives
        or not case.truth.steps
        or not set(case.truth.steps) <= steps
    ):
        raise ValueError("真相必须引用合法的候选项和非空步骤。")
    _unique(case.truth.steps, "真相步骤")
    dependencies = [a.requires for a in case.scene.actions]
    dependencies += [case.lie.counterevidence, case.lie.admission_presented]
    for dep in dependencies:
        refs = _unique(dep.all_of, "all_of") | _unique(dep.any_of, "any_of")
        if not refs <= evidence_ids:
            raise ValueError("证据依赖引用不存在。")
    for action in case.scene.actions:
        if action.evidence_id not in evidence_ids:
            raise ValueError("调查动作授予的证据不存在。")
    for effect in case.lie.effects:
        if effect.evidence_id not in evidence_ids:
            raise ValueError("出示效果引用的证据不存在。")
    for knowledge in case.knowledge:
        if not knowledge.known_by or not set(knowledge.known_by) <= suspects:
            raise ValueError("知识归属缺失或角色不存在。")
    if case.lie.admitted_knowledge_id not in knowledge_ids:
        raise ValueError("承认披露的知识不存在。")
    for knowledge in case.knowledge:
        if knowledge.disclosure == "ADMITTED" and (
            knowledge.id != case.lie.admitted_knowledge_id or case.npc.id not in knowledge.known_by
        ):
            raise ValueError("切片的私有知识必须由本 NPC 的谎言披露。")
    admitted = next(k for k in case.knowledge if k.id == case.lie.admitted_knowledge_id)
    if admitted.disclosure != "ADMITTED" or case.npc.id not in admitted.known_by:
        raise ValueError("承认条目必须是本 NPC 的私有知识。")
    if not (case.lie.counterevidence.all_of or case.lie.counterevidence.any_of):
        raise ValueError("谎言必须具有反证硬门槛。")
    if case.lie.admission_pressure_min is None and case.lie.admission_trust_min is None:
        raise ValueError("承认必须显式启用至少一条心理门槛。")

    # Fixed-point reachability respects all/any, including cycles with an external entry.
    reached: frozenset[str] = frozenset()
    while True:
        next_reached = reached | {
            a.evidence_id for a in case.scene.actions if a.requires.satisfied(reached)
        }
        if next_reached == reached:
            break
        reached = next_reached
    if reached != evidence_ids:
        raise ValueError("存在不可达证据或阻断通关的循环依赖。")

    scoring = case.scoring
    if not 0 < scoring.partial_min < scoring.correct_min <= 100:
        raise ValueError("评分阈值必须满足 0 < 部分正确 < 正确 <= 100。")
    if sum(c.points for c in scoring.criteria) != 100:
        raise ValueError("评分权重总和必须为 100。")
    for kind in ("culprit", "weapon", "motive", "process"):
        if sum(c.kind == kind for c in scoring.criteria) != 1:
            raise ValueError("凶手、凶器、动机和过程必须各有一个评分项。")
    for criterion in scoring.criteria:
        _unique(criterion.evidence_ids, "评分证据")
        if criterion.kind == "support":
            if (
                criterion.step_id not in case.truth.steps
                or not criterion.evidence_ids
                or not set(criterion.evidence_ids) <= evidence_ids
            ):
                raise ValueError("证据评分必须引用正确步骤和非空的有效证据。")
            if any(
                e.credibility != "VERIFIED" for e in case.evidence if e.id in criterion.evidence_ids
            ):
                raise ValueError("评分所需证据必须有核验来源。")
        elif criterion.step_id is not None or criterion.evidence_ids:
            raise ValueError("答案评分不能夹带证据条件。")
    unsupported_max = sum(c.points for c in scoring.criteria if c.kind != "support")
    if unsupported_max >= scoring.correct_min:
        raise ValueError("无证据的猜测不能达到正确阈值。")

    # Three pieces of evidence: search up to six orders for an attainable admission.
    for order in permutations(case.evidence):
        state = GameState(
            npc=NPCState(case.npc.initial_pressure, case.npc.initial_trust),
            phase=Phase.INTERROGATION,
            active_npc_id=case.npc.id,
            evidence_ids=reached,
        )
        for evidence in order:
            state = present(case, state, case.npc.id, evidence.id)
        if state.npc.lie_stage == LieStage.ADMITTED:
            break
    else:
        raise ValueError("反证、可信度或数值门槛使承认不可达。")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"案件文件含有重复的 JSON 键：{', '.join(duplicates)}")
    return dict(pairs)


def parse_case(text: str) -> Case:
    try:
        # JSON parsers silently keep the last duplicate; a reviewed case must be unambiguous.
        json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        case = Case.model_validate_json(text)
    except (ValidationError, json.JSONDecodeError) as error:
        raise ValueError(f"案件文件结构校验失败：{error}") from error
    validate_case(case)
    return case


def load_case(path: Path | None = None) -> Case:
    try:
        text = (path or default_case_path()).read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"案件文件读取失败：{error}") from error
    return parse_case(text)


def _canonical(value):
    if isinstance(value, dict):
        result = {key: _canonical(item) for key, item in value.items()}
        for key in ("all_of", "any_of", "known_by"):
            if key in result:
                result[key] = sorted(result[key])
        return result
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def content_hash(case: Case) -> str:
    """SHA-256 of the canonical definition: sorted keys and ID sets, ordered steps kept."""
    data = _canonical(case.model_dump(mode="json"))
    data["knowledge"] = sorted(data["knowledge"], key=lambda item: item["id"])
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()
