"""Player-visible projections. Allowlists only: never serialize the case, rules or ORM rows."""

from datetime import datetime

from backend.domain.evidence import current_statement
from backend.domain.models import Case, LieStage, Phase
from backend.domain.state_machine import emotion, evading
from backend.infrastructure.database.models import CaseTemplate
from backend.infrastructure.database.repositories.session_repository import (
    CATEGORY_CODES,
    SavedGame,
)

INVESTIGATING = {Phase.INVESTIGATION, Phase.DEEP_INVESTIGATION}
AVAILABLE_ACTIONS = {
    Phase.INVESTIGATION: ["INVESTIGATE", "SET_INTERROGATION", "OPEN_ACCUSATION", "RESTART"],
    Phase.DEEP_INVESTIGATION: ["INVESTIGATE", "SET_INTERROGATION", "OPEN_ACCUSATION", "RESTART"],
    Phase.INTERROGATION: [
        "SET_INTERROGATION",
        "END_INTERROGATION",
        "CHAT",
        "ASK_TOPIC",
        "PRESENT_EVIDENCE",
        "POINT_CONTRADICTION",
        "OPEN_ACCUSATION",
        "RESTART",
    ],
    Phase.ACCUSATION: ["SUBMIT_ACCUSATION", "CANCEL_ACCUSATION", "RESTART"],
    Phase.REVIEW: ["FINISH_REVIEW", "RESTART"],
    Phase.FINISHED: ["RESTART"],
}


def iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def session_summary(template: CaseTemplate, saved: SavedGame, is_current: bool) -> dict:
    state = saved.state
    return {
        "session_id": str(saved.session_id),
        "case_id": template.case_id,
        "case_version": template.version,
        "title": template.title,
        "phase": state.phase.value,
        "state_version": state.version,
        "active_npc_id": state.active_npc_id,
        "is_current": is_current,
        "created_at": iso(saved.created_at),
        "saved_at": iso(saved.saved_at),
        "closed_at": iso(saved.closed_at),
        "finished_at": iso(saved.finished_at),
        "available_actions": AVAILABLE_ACTIONS[state.phase] if is_current else [],
    }


def evidence_view(case: Case, saved: SavedGame, evidence_id: str) -> dict:
    evidence = next(e for e in case.evidence if e.id == evidence_id)
    return {
        "evidence_id": evidence.id,
        "name": evidence.title,
        "content": evidence.content,
        "source": {"kind": "SCENE", "id": case.scene.id, "label": evidence.source},
        "credibility": evidence.credibility,
        "discovered_at": iso(saved.evidence_discovered_at[evidence.id]),
    }


def known_information(case: Case, saved: SavedGame, knowledge_id: str) -> dict:
    knowledge = next(k for k in case.knowledge if k.id == knowledge_id)
    source = (
        {"kind": "PUBLIC", "id": None, "label": "案件公开信息"}
        if knowledge.disclosure == "PUBLIC"
        else {"kind": "NPC", "id": case.npc.id, "label": case.npc.name}
    )
    return {
        "information_ref": {"kind": "KNOWLEDGE", "id": knowledge.id},
        "content": knowledge.content,
        "assertion_kind": "TESTIMONY",
        "source": source,
        "credibility": "UNVERIFIED",
        "discovered_at": iso(saved.knowledge_discovered_at.get(knowledge.id)),
    }


def npc_view(case: Case, saved: SavedGame) -> dict:
    """Emotion, admission and evasion only; pressure and trust are never shown as numbers."""
    state = saved.state
    npc = state.npc
    admitted = npc.lie_stage == LieStage.ADMITTED
    is_active = state.active_npc_id == case.npc.id
    is_evading = is_active and evading(case, npc)
    display_state = "CONFESSION" if admitted else emotion(npc)
    return {
        "npc_id": case.npc.id,
        "name": case.npc.name,
        "public_identity": case.npc.role,
        "is_contactable": True,
        "is_active": is_active,
        "is_evading": is_evading,
        "emotion": emotion(npc),
        "admission_progress": "CONFESSION" if admitted else "NONE",
        "display_state": "EVADING" if is_evading else display_state,
        "fixed_statement": current_statement(case, npc) if is_active else None,
        "presented_evidence_ids": sorted(npc.presented & state.evidence_ids),
        "topics": [
            {
                "topic_id": topic.id,
                "label": topic.label,
                "asked": topic.knowledge_id in state.disclosed_knowledge,
            }
            for topic in case.interrogation.topics
            if topic.npc_id == case.npc.id
        ],
    }


def scene_view(case: Case, saved: SavedGame) -> dict:
    state = saved.state
    actions = []
    for action in case.scene.actions:
        completed = action.id in state.completed_actions
        reason = None
        if state.phase not in INVESTIGATING:
            reason = "当前阶段不能调查。"
        elif not completed and not action.requires.satisfied(state.evidence_ids):
            reason = "核对条件尚不齐全。"
        actions.append(
            {
                "action_id": action.id,
                "label": action.label,
                "completed": completed,
                "enabled": reason is None,
                "disabled_reason": reason,
            }
        )
    return {
        "scene_id": case.scene.id,
        "name": case.scene.name,
        "description": case.scene.description,
        "visited": bool(state.completed_actions),
        "actions": actions,
    }


def accusation_options(case: Case) -> dict:
    return {
        **{
            name: [{"id": c.id, "label": c.label} for c in getattr(case, name)]
            for name in ("suspects", "weapons", "motives", "process_steps")
        },
        "process_constraints": {
            "min_steps": 1,
            "max_steps": len(case.process_steps),
            "allow_repeated_steps": False,
        },
    }


def session_view(case: Case, template: CaseTemplate, saved: SavedGame, is_current: bool) -> dict:
    state = saved.state
    visible = [
        k.id
        for k in case.knowledge
        if k.disclosure == "PUBLIC" or k.id in state.disclosed_knowledge
    ]
    return {
        "session": session_summary(template, saved, is_current),
        "intro_text": case.introduction,
        "scenes": [scene_view(case, saved)],
        "evidence": [
            evidence_view(case, saved, e.id) for e in case.evidence if e.id in state.evidence_ids
        ],
        "npcs": [npc_view(case, saved)],
        "known_information": [known_information(case, saved, k) for k in visible],
        "accusation_options": accusation_options(case),
    }


def accusation_view(saved: SavedGame) -> dict:
    verdict = saved.state.verdict
    if verdict is None:
        raise ValueError("Not closed.")
    accusation = verdict.accusation
    return {
        "content": {
            "suspect_character_id": accusation.culprit,
            "weapon_option_id": accusation.weapon,
            "motive_option_id": accusation.motive,
            "ordered_process_step_ids": list(accusation.steps),
            "cited_evidence_ids": list(accusation.cited_evidence_ids),
            "step_evidence_links": [link.model_dump() for link in accusation.evidence_links],
            "explanation": accusation.explanation,
        },
        "submitted_at": iso(saved.submitted_at),
        "submitted_state_version": saved.submitted_state_version,
        "case_version": verdict.case_version,
        "rules_version": verdict.rules_version,
        "verdict": {
            "category": CATEGORY_CODES[verdict.category],
            "score": f"{verdict.score:.2f}",
            "max_score": f"{sum(c.maximum for c in verdict.criteria):.2f}",
            "criteria": [
                {
                    "criterion_id": c.id,
                    "label": c.label,
                    "matched": c.points == c.maximum,
                    "score": f"{c.points:.2f}",
                    "max_score": f"{c.maximum:.2f}",
                    "explanation": c.explanation,
                }
                for c in verdict.criteria
            ],
        },
    }


def review_view(case: Case, saved: SavedGame) -> dict:
    """Full truth, only for a consistently closed game. Missed evidence is shown, never granted."""
    truth = case.truth
    labels = {
        c.id: c.label
        for name in ("suspects", "weapons", "motives", "process_steps")
        for c in getattr(case, name)
    }
    held = saved.state.evidence_ids

    def review_evidence(evidence) -> dict:
        return {
            "evidence_id": evidence.id,
            "name": evidence.title,
            "content": evidence.content,
            "source": {"kind": "SCENE", "id": case.scene.id, "label": evidence.source},
            "was_discovered": evidence.id in held,
        }

    return {
        "accusation": accusation_view(saved),
        "truth": {
            "suspect_character_id": truth.culprit,
            "weapon_option_id": truth.weapon,
            "motive_option_id": truth.motive,
            "ordered_process_step_ids": list(truth.steps),
            "labels": {
                key: labels[key]
                for key in (truth.culprit, truth.weapon, truth.motive, *truth.steps)
            },
            "explanation": truth.explanation,
        },
        "evidence_chain": [review_evidence(e) for e in case.evidence if e.id in held],
        "missed_evidence": [review_evidence(e) for e in case.evidence if e.id not in held],
        "fixed_review": saved.fixed_review,
    }
