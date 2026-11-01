"""Maps the validated case definition (schema 3) to static tables and assembles it back."""

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.models import Case
from backend.infrastructure.database.models import (
    CaseTemplate,
    Character,
    CharacterSecret,
    Evidence,
    LieChain,
    LieRule,
    Relationship,
    Scene,
    TimelineEvent,
)


def knowledge_speaker_of(case: Case, knowledge_id: str) -> str | None:
    """ASKED knowledge is spoken by its topic's NPC, ADMITTED by the layer that reveals it."""
    topic = next((t for t in case.interrogation.topics if t.knowledge_id == knowledge_id), None)
    if topic is not None:
        return topic.npc_id
    lie = next((lie for lie in case.lies if lie.admitted_knowledge_id == knowledge_id), None)
    if lie is not None:
        return lie.npc_id
    return None


class CaseRepository:
    def __init__(self, db: Session):
        self._db = db

    def find(self, case_id: str, version: str) -> CaseTemplate | None:
        return self._db.scalar(
            select(CaseTemplate).where(
                CaseTemplate.case_id == case_id, CaseTemplate.version == version
            )
        )

    def list_published(self) -> list[CaseTemplate]:
        return list(
            self._db.scalars(
                select(CaseTemplate)
                .where(CaseTemplate.status == "PUBLISHED")
                .order_by(CaseTemplate.case_id, CaseTemplate.published_at)
            )
        )

    def insert_draft(self, case: Case, rule_execution_version: str, now: datetime) -> CaseTemplate:
        template_id = uuid.uuid4()
        template = CaseTemplate(
            template_id=template_id,
            case_id=case.case_id,
            version=case.version,
            title=case.title,
            synopsis=case.synopsis,
            status="DRAFT",
            definition_schema_version=case.schema_version,
            definition_scope=case.scope,
            review_status=case.review_status,
            rules_version=case.rules_version,
            rule_execution_version=rule_execution_version,
            truth_json=case.truth.model_dump(mode="json"),
            accusation_options_json={
                name: [choice.model_dump(mode="json") for choice in getattr(case, name)]
                for name in ("suspects", "weapons", "motives", "process_steps")
            },
            scoring_policy_json=case.scoring.model_dump(mode="json"),
            rules_json={
                "interrogation": case.interrogation.model_dump(mode="json"),
                "present_effects": [
                    {"lie_rule_id": lie.id, **effect.model_dump(mode="json")}
                    for lie in case.lies
                    for effect in lie.effects
                ],
            },
            public_knowledge_json=[
                k.model_dump(mode="json") for k in case.knowledge if k.disclosure == "PUBLIC"
            ],
            timeline_origin_label=case.timeline_origin_label,
            show_key_badges=case.show_key_badges,
            deep_unlock_json=case.deep_unlock.model_dump(mode="json"),
            introduction=case.introduction,
            created_at=now,
        )
        self._db.add(template)
        self._db.flush()

        granting_scene = {
            action.evidence_id: scene.id for scene in case.scenes for action in scene.actions
        }
        for order, character in enumerate(case.characters):
            self._db.add(
                Character(
                    template_id=template_id,
                    character_id=character.id,
                    name=character.name,
                    role="SUSPECT" if character.interrogatable else "VICTIM",
                    public_identity=character.public_identity,
                    sort_order=order,
                    is_interrogatable=character.interrogatable,
                    initial_pressure=character.initial_pressure,
                    initial_trust=character.initial_trust,
                    role_label=character.role,
                    personality=character.personality,
                    speech_style=character.speech_style,
                    default_reply=character.default_reply,
                    core_lie_ids_json=list(character.core_lie_ids),
                )
            )
        for order, scene in enumerate(case.scenes):
            self._db.add(
                Scene(
                    template_id=template_id,
                    scene_id=scene.id,
                    name=scene.name,
                    description=scene.description,
                    sort_order=order,
                    unlock_json=scene.unlock.model_dump(mode="json"),
                    actions_json=[
                        {
                            "id": action.id,
                            "label": action.label,
                            "evidence_id": action.evidence_id,
                            "requires": action.requires.model_dump(mode="json"),
                        }
                        for action in scene.actions
                    ],
                )
            )
        self._db.flush()
        for order, evidence in enumerate(case.evidence):
            self._db.add(
                Evidence(
                    template_id=template_id,
                    evidence_id=evidence.id,
                    name=evidence.title,
                    content=evidence.content,
                    source_label=evidence.source,
                    source_type="SCENE",
                    source_scene_id=granting_scene[evidence.id],
                    source_character_id=None,
                    initial_credibility=evidence.credibility,
                    sort_order=order,
                    kind=evidence.kind,
                    is_key=evidence.is_key,
                )
            )
        for knowledge in case.knowledge:
            if knowledge.disclosure == "PUBLIC":
                continue
            self._db.add(
                CharacterSecret(
                    template_id=template_id,
                    secret_id=knowledge.id,
                    character_id=knowledge_speaker_of(case, knowledge.id),
                    content=knowledge.content,
                    known_by_json=list(knowledge.known_by),
                    assertion_kind="TESTIMONY",
                    initial_credibility="UNVERIFIED",
                    disclosure=knowledge.disclosure,
                )
            )
        chain_position = {
            lie_id: (chain.id, index)
            for chain in case.lie_chains
            for index, lie_id in enumerate(chain.lie_ids)
        }
        for order, chain in enumerate(case.lie_chains):
            self._db.add(
                LieChain(
                    template_id=template_id,
                    chain_id=chain.id,
                    character_id=chain.npc_id,
                    lie_ids_json=list(chain.lie_ids),
                    sort_order=order,
                )
            )
        for lie in case.lies:
            _, position = chain_position[lie.id]
            self._db.add(
                LieRule(
                    template_id=template_id,
                    lie_rule_id=lie.id,
                    character_id=lie.npc_id,
                    priority=position,
                    statements_json=lie.statements.model_dump(mode="json"),
                    counterevidence_json=lie.counterevidence.model_dump(mode="json"),
                    admission_condition_json={
                        "presented": lie.admission_presented.model_dump(mode="json"),
                        "pressure_min": lie.admission_pressure_min,
                        "trust_min": lie.admission_trust_min,
                    },
                    on_admitted_json={"knowledge_id": lie.admitted_knowledge_id},
                )
            )
        for order, relationship in enumerate(case.relationships):
            self._db.add(
                Relationship(
                    template_id=template_id,
                    relationship_id=relationship.id,
                    from_character_id=relationship.from_id,
                    to_character_id=relationship.to_id,
                    relationship_type=relationship.type,
                    directed=relationship.directed,
                    description=relationship.description,
                    assertion_kind=relationship.assertion_kind,
                    credibility=relationship.credibility,
                    source_kind=relationship.source_kind,
                    source_id=relationship.source_id,
                    reveal_evidence_ids_json=list(relationship.reveal_evidence_ids),
                    reveal_knowledge_ids_json=list(relationship.reveal_knowledge_ids),
                    sort_order=order,
                )
            )
        for order, event in enumerate(case.timeline):
            self._db.add(
                TimelineEvent(
                    template_id=template_id,
                    timeline_event_id=event.id,
                    title=event.title,
                    description=event.description,
                    scene_id=event.scene_id,
                    participant_ids_json=list(event.participant_ids),
                    precision=event.precision,
                    start_minutes=event.start_minutes,
                    end_minutes=event.end_minutes,
                    time_label=event.time_label,
                    assertion_kind=event.assertion_kind,
                    credibility=event.credibility,
                    source_kind=event.source_kind,
                    source_id=event.source_id,
                    reveal_evidence_ids_json=list(event.reveal_evidence_ids),
                    reveal_knowledge_ids_json=list(event.reveal_knowledge_ids),
                    conflicts_with_json=list(event.conflicts_with),
                    sort_order=order,
                )
            )
        self._db.flush()
        return template

    def load_case(self, template: CaseTemplate) -> Case:
        """Assemble the domain definition from the tables; the database is authoritative."""
        tid = template.template_id

        def rows(table, *order):
            return list(
                self._db.scalars(select(table).where(table.template_id == tid).order_by(*order))
            )

        characters = rows(Character, Character.sort_order, Character.character_id)
        scenes = rows(Scene, Scene.sort_order, Scene.scene_id)
        evidence = rows(Evidence, Evidence.sort_order, Evidence.evidence_id)
        secrets = rows(CharacterSecret, CharacterSecret.secret_id)
        chains = rows(LieChain, LieChain.sort_order, LieChain.chain_id)
        lies = rows(LieRule, LieRule.priority, LieRule.lie_rule_id)
        relationships = rows(Relationship, Relationship.sort_order, Relationship.relationship_id)
        timeline = rows(TimelineEvent, TimelineEvent.sort_order, TimelineEvent.timeline_event_id)

        definition = {
            "schema_version": template.definition_schema_version,
            "scope": template.definition_scope,
            "case_id": template.case_id,
            "version": template.version,
            "rules_version": template.rules_version,
            "title": template.title,
            "synopsis": template.synopsis,
            "introduction": template.introduction,
            "review_status": template.review_status,
            "timeline_origin_label": template.timeline_origin_label,
            "show_key_badges": template.show_key_badges,
            "characters": [
                {
                    "id": c.character_id,
                    "name": c.name,
                    "role": c.role_label,
                    "public_identity": c.public_identity,
                    "personality": c.personality,
                    "speech_style": c.speech_style,
                    "interrogatable": c.is_interrogatable,
                    "initial_pressure": c.initial_pressure,
                    "initial_trust": c.initial_trust,
                    "core_lie_ids": c.core_lie_ids_json or [],
                    "default_reply": c.default_reply,
                }
                for c in characters
            ],
            "scenes": [
                {
                    "id": scene.scene_id,
                    "name": scene.name,
                    "description": scene.description,
                    "unlock": scene.unlock_json,
                    "actions": scene.actions_json,
                }
                for scene in scenes
            ],
            "evidence": [
                {
                    "id": e.evidence_id,
                    "title": e.name,
                    "kind": e.kind,
                    "content": e.content,
                    "source": e.source_label,
                    "credibility": e.initial_credibility,
                    "is_key": e.is_key,
                }
                for e in evidence
            ],
            "knowledge": list(template.public_knowledge_json)
            + [
                {
                    "id": s.secret_id,
                    "content": s.content,
                    "known_by": s.known_by_json,
                    "disclosure": s.disclosure,
                }
                for s in secrets
            ],
            "lies": [
                {
                    "id": lie.lie_rule_id,
                    "npc_id": lie.character_id,
                    "counterevidence": lie.counterevidence_json,
                    "admission_presented": lie.admission_condition_json["presented"],
                    "admission_pressure_min": lie.admission_condition_json["pressure_min"],
                    "admission_trust_min": lie.admission_condition_json["trust_min"],
                    "statements": lie.statements_json,
                    "admitted_knowledge_id": lie.on_admitted_json["knowledge_id"],
                    "effects": [
                        {k: v for k, v in effect.items() if k != "lie_rule_id"}
                        for effect in template.rules_json["present_effects"]
                        if effect["lie_rule_id"] == lie.lie_rule_id
                    ],
                }
                for lie in lies
            ],
            "lie_chains": [
                {
                    "id": chain.chain_id,
                    "npc_id": chain.character_id,
                    "lie_ids": chain.lie_ids_json,
                }
                for chain in chains
            ],
            "interrogation": template.rules_json["interrogation"],
            "deep_unlock": template.deep_unlock_json,
            "relationships": [
                {
                    "id": r.relationship_id,
                    "from_id": r.from_character_id,
                    "to_id": r.to_character_id,
                    "type": r.relationship_type,
                    "directed": r.directed,
                    "description": r.description,
                    "assertion_kind": r.assertion_kind,
                    "credibility": r.credibility,
                    "source_kind": r.source_kind,
                    "source_id": r.source_id,
                    "reveal_evidence_ids": r.reveal_evidence_ids_json,
                    "reveal_knowledge_ids": r.reveal_knowledge_ids_json,
                }
                for r in relationships
            ],
            "timeline": [
                {
                    "id": t.timeline_event_id,
                    "title": t.title,
                    "description": t.description,
                    "scene_id": t.scene_id,
                    "participant_ids": t.participant_ids_json,
                    "precision": t.precision,
                    "start_minutes": t.start_minutes,
                    "end_minutes": t.end_minutes,
                    "time_label": t.time_label,
                    "assertion_kind": t.assertion_kind,
                    "credibility": t.credibility,
                    "source_kind": t.source_kind,
                    "source_id": t.source_id,
                    "reveal_evidence_ids": t.reveal_evidence_ids_json,
                    "reveal_knowledge_ids": t.reveal_knowledge_ids_json,
                    "conflicts_with": t.conflicts_with_json,
                }
                for t in timeline
            ],
            **template.accusation_options_json,
            "truth": template.truth_json,
            "scoring": template.scoring_policy_json,
        }
        return Case.model_validate_json(json.dumps(definition, ensure_ascii=False))
