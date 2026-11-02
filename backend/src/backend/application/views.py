"""Player-visible projections. Allowlists only: never serialize the case, rules or ORM rows."""

from backend.domain.evidence import current_statement
from backend.domain.models import Case, GameState, Phase
from backend.domain.state_machine import admission_progress, display_state, emotion, evading
from backend.infrastructure.database.models import CaseTemplate
from backend.infrastructure.database.repositories.session_repository import (
    CATEGORY_CODES,
    EMPTY_DRAFT,
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
    Phase.ACCUSATION: [
        "SAVE_ACCUSATION_DRAFT",
        "SUBMIT_ACCUSATION",
        "CANCEL_ACCUSATION",
        "RESTART",
    ],
    Phase.REVIEW: ["FINISH_REVIEW", "RESTART"],
    Phase.FINISHED: ["RESTART"],
}

PUBLIC_LABEL = "案件公开信息"


def iso(value) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _name_of(case: Case, character_id: str | None) -> str:
    return next((c.name for c in case.characters if c.id == character_id), character_id or "")


def _granting_scene(case: Case, evidence_id: str) -> str:
    return next(
        scene.id
        for scene in case.scenes
        for action in scene.actions
        if action.evidence_id == evidence_id
    )


def _public_source(case: Case, kind: str, source_id: str | None) -> dict:
    if kind == "PUBLIC":
        return {"kind": "PUBLIC", "id": None, "label": PUBLIC_LABEL}
    if kind == "EVIDENCE":
        evidence = next(e for e in case.evidence if e.id == source_id)
        return {"kind": "EVIDENCE", "id": source_id, "label": evidence.title}
    return {"kind": "NPC", "id": source_id, "label": _name_of(case, source_id)}


def session_summary(
    template: CaseTemplate, saved: SavedGame, is_current: bool, generation_available: bool = True
) -> dict:
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
        "generation_available": generation_available,
    }


def evidence_view(case: Case, saved: SavedGame, evidence_id: str) -> dict:
    evidence = next(e for e in case.evidence if e.id == evidence_id)
    return {
        "evidence_id": evidence.id,
        "name": evidence.title,
        "kind": evidence.kind,
        "content": evidence.content,
        "source": {
            "kind": "SCENE",
            "id": _granting_scene(case, evidence.id),
            "label": evidence.source,
        },
        "credibility": evidence.credibility,
        "discovered_at": iso(saved.evidence_discovered_at.get(evidence.id)),
        "key_badge": case.show_key_badges and evidence.is_key,
        "known_conflicts": [],
        "links": [],
    }


def known_information(case: Case, saved: SavedGame, knowledge_id: str) -> dict:
    knowledge = next(k for k in case.knowledge if k.id == knowledge_id)
    if knowledge.disclosure == "PUBLIC":
        source = {"kind": "PUBLIC", "id": None, "label": PUBLIC_LABEL}
    else:
        speaker = _speaker_of(case, knowledge_id)
        source = {"kind": "NPC", "id": speaker, "label": _name_of(case, speaker)}
    return {
        "information_ref": {"kind": "KNOWLEDGE", "id": knowledge.id},
        "content": knowledge.content,
        "assertion_kind": "TESTIMONY",
        "source": source,
        "credibility": "UNVERIFIED",
        "discovered_at": iso(saved.knowledge_discovered_at.get(knowledge.id)),
        "known_conflicts": [],
    }


def _speaker_of(case: Case, knowledge_id: str) -> str | None:
    from backend.domain.evidence import knowledge_speaker

    return knowledge_speaker(case, knowledge_id)


def npc_view(case: Case, saved: SavedGame, npc_id: str) -> dict:
    """Emotion, admission and evasion only; pressure and trust are never shown as numbers."""
    state = saved.state
    npc = state.npcs[npc_id]
    character = next(c for c in case.characters if c.id == npc_id)
    is_active = state.active_npc_id == npc_id
    is_evading = is_active and evading(case, npc)
    known_statements = [
        known_information(case, saved, k.id)
        for k in case.knowledge
        if k.disclosure != "PUBLIC"
        and k.id in state.disclosed_knowledge
        and _speaker_of(case, k.id) == npc_id
    ]
    return {
        "npc_id": npc_id,
        "name": character.name,
        "public_identity": character.public_identity,
        "is_contactable": True,
        "is_active": is_active,
        "is_evading": is_evading,
        "emotion": emotion(npc),
        "admission_progress": admission_progress(case, state, npc_id),
        "display_state": display_state(case, state, npc_id),
        "fixed_statement": current_statement(case, state, npc_id) if is_active else None,
        "presented_evidence_ids": sorted(npc.presented & state.evidence_ids),
        "known_statements": known_statements,
        "topics": [
            {
                "topic_id": topic.id,
                "label": topic.label,
                "asked": topic.knowledge_id in state.disclosed_knowledge,
            }
            for topic in case.interrogation.topics
            if topic.npc_id == npc_id
        ],
    }


def scene_view(case: Case, saved: SavedGame, scene) -> dict:
    state = saved.state
    actions = []
    for action in scene.actions:
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
        "scene_id": scene.id,
        "name": scene.name,
        "description": scene.description,
        "visited": bool(set(a.id for a in scene.actions) & state.completed_actions),
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


def accusation_content(content) -> dict:
    """Both AccusationDraft and Accusation project into the same public shape."""
    return {
        "suspect_character_id": content.culprit,
        "weapon_option_id": content.weapon,
        "motive_option_id": content.motive,
        "ordered_process_step_ids": list(content.steps),
        "cited_evidence_ids": list(content.cited_evidence_ids),
        "step_evidence_links": [
            {"step_id": link.step_id, "evidence_id": link.evidence_id}
            for link in content.evidence_links
        ],
        "explanation": content.explanation,
    }


def draft_view(saved: SavedGame) -> dict:
    return {
        "content": accusation_content(saved.state.draft) if saved.state.draft else dict(EMPTY_DRAFT)
    }


def visible_relationship_ids(case: Case, state: GameState) -> set[str]:
    held = state.evidence_ids
    disclosed = state.disclosed_knowledge
    return {
        relationship.id
        for relationship in case.relationships
        if (not relationship.reveal_evidence_ids and not relationship.reveal_knowledge_ids)
        or set(relationship.reveal_evidence_ids) & held
        or set(relationship.reveal_knowledge_ids) & disclosed
    }


def visible_timeline_ids(case: Case, state: GameState) -> set[str]:
    held = state.evidence_ids
    disclosed = state.disclosed_knowledge
    return {
        event.id
        for event in case.timeline
        if (not event.reveal_evidence_ids and not event.reveal_knowledge_ids)
        or set(event.reveal_evidence_ids) & held
        or set(event.reveal_knowledge_ids) & disclosed
    }


def relationship_graph(case: Case, saved: SavedGame) -> dict:
    state = saved.state
    visible = visible_relationship_ids(case, state)
    edges = []
    for relationship in case.relationships:
        if relationship.id not in visible:
            continue
        discovered = [
            saved.evidence_discovered_at.get(evidence_id)
            for evidence_id in relationship.reveal_evidence_ids
        ] + [
            saved.knowledge_discovered_at.get(knowledge_id)
            for knowledge_id in relationship.reveal_knowledge_ids
        ]
        known = [value for value in discovered if value is not None]
        edges.append(
            {
                "relationship_id": relationship.id,
                "from_character_id": relationship.from_id,
                "to_character_id": relationship.to_id,
                "relationship_type": relationship.type,
                "directed": relationship.directed,
                "description": relationship.description,
                "assertion_kind": relationship.assertion_kind,
                "source": _public_source(case, relationship.source_kind, relationship.source_id),
                "credibility": relationship.credibility,
                "discovered_at": iso(min(known)) if known else None,
                "known_conflicts": [],
            }
        )
    nodes = [
        {
            "character_id": character.id,
            "name": character.name,
            "role": character.role,
            "public_identity": character.public_identity,
        }
        for character in case.characters
    ]
    return {"nodes": nodes, "edges": edges}


def timeline_view(case: Case, saved: SavedGame) -> dict:
    state = saved.state
    visible = visible_timeline_ids(case, state)

    def order_key(event):
        if event.start_minutes is None:
            return (1, 0, 0, event.id)
        return (0, event.start_minutes, event.end_minutes or 0, event.id)

    items = []
    for event in sorted(case.timeline, key=order_key):
        if event.id not in visible:
            continue
        discovered = [
            saved.evidence_discovered_at.get(evidence_id)
            for evidence_id in event.reveal_evidence_ids
        ] + [
            saved.knowledge_discovered_at.get(knowledge_id)
            for knowledge_id in event.reveal_knowledge_ids
        ]
        known = [value for value in discovered if value is not None]
        conflicts = [
            {"kind": "TIMELINE_EVENT", "id": other}
            for other in event.conflicts_with
            if other in visible
        ]
        items.append(
            {
                "timeline_event_id": event.id,
                "title": event.title,
                "description": event.description,
                "scene_id": event.scene_id,
                "participant_ids": list(event.participant_ids),
                "time_precision": event.precision,
                "time_start_minutes": event.start_minutes,
                "time_end_minutes": event.end_minutes,
                "time_label": event.time_label,
                "assertion_kind": event.assertion_kind,
                "source": _public_source(case, event.source_kind, event.source_id),
                "credibility": event.credibility,
                "discovered_at": iso(min(known)) if known else None,
                "known_conflicts": conflicts,
            }
        )
    return {"origin_label": case.timeline_origin_label, "items": items}


def session_view(
    case: Case,
    template: CaseTemplate,
    saved: SavedGame,
    is_current: bool,
    pending_conversations: list[dict] | None = None,
    generation_available: bool = True,
) -> dict:
    from backend.domain.rules import open_scenes

    state = saved.state
    open_ids = set(open_scenes(case, state))
    visible = [
        k.id
        for k in case.knowledge
        if k.disclosure == "PUBLIC" or k.id in state.disclosed_knowledge
    ]
    return {
        "session": session_summary(template, saved, is_current, generation_available),
        "intro_text": case.introduction,
        "scenes": [scene_view(case, saved, scene) for scene in case.scenes if scene.id in open_ids],
        "evidence": [
            evidence_view(case, saved, e.id) for e in case.evidence if e.id in state.evidence_ids
        ],
        "npcs": [npc_view(case, saved, c.id) for c in case.characters if c.interrogatable],
        "known_information": [known_information(case, saved, k) for k in visible],
        "relationships": relationship_graph(case, saved),
        "timeline": timeline_view(case, saved),
        "accusation_options": accusation_options(case),
        "accusation_draft": draft_view(saved)["content"],
        "pending_conversations": pending_conversations or [],
    }


def accusation_view(saved: SavedGame) -> dict:
    verdict = saved.state.verdict
    if verdict is None:
        raise ValueError("Not closed.")
    accusation = verdict.accusation
    return {
        "content": accusation_content(accusation),
        "submitted_at": iso(saved.submitted_at),
        "submitted_state_version": saved.submitted_state_version,
        "case_version": verdict.case_version,
        "rules_version": verdict.rules_version,
        "verdict": {
            "category": CATEGORY_CODES[verdict.category],
            "score": f"{verdict.score:.2f}",
            "max_score": f"{sum(c.maximum for c in verdict.criteria):.2f}",
            "fixed_explanation": verdict.fixed_explanation,
            "criteria": [
                {
                    "criterion_id": c.id,
                    "label": c.label,
                    "matched": c.points == c.maximum,
                    "score": f"{c.points:.2f}",
                    "max_score": f"{c.maximum:.2f}",
                    "explanation": c.explanation,
                    "missing_evidence_ids": list(c.missing_evidence_ids),
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
            "source": {
                "kind": "SCENE",
                "id": _granting_scene(case, evidence.id),
                "label": evidence.source,
            },
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
