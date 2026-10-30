"""Maps the validated slice definition to static tables and assembles it back."""

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
    EvidenceDependency,
    LieRule,
    Scene,
)


def _split_label(label: str) -> tuple[str, str]:
    name, _, identity = label.partition(" · ")
    return name, identity or name


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
            synopsis=case.introduction,
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
                "present_effects": [
                    {"lie_rule_id": case.lie.id, **effect.model_dump(mode="json")}
                    for effect in case.lie.effects
                ],
                "interrogation": case.interrogation.model_dump(mode="json"),
            },
            public_knowledge_json=[
                k.model_dump(mode="json") for k in case.knowledge if k.disclosure == "PUBLIC"
            ],
            created_at=now,
        )
        self._db.add(template)
        self._db.flush()

        for order, choice in enumerate(case.suspects):
            npc = case.npc if choice.id == case.npc.id else None
            name, identity = _split_label(choice.label)
            self._db.add(
                Character(
                    template_id=template_id,
                    character_id=choice.id,
                    name=npc.name if npc else name,
                    role="SUSPECT",
                    public_identity=npc.role if npc else identity,
                    sort_order=order,
                    is_interrogatable=npc is not None,
                    initial_pressure=npc.initial_pressure if npc else None,
                    initial_trust=npc.initial_trust if npc else None,
                )
            )
        self._db.add(
            Scene(
                template_id=template_id,
                scene_id=case.scene.id,
                name=case.scene.name,
                description=case.scene.description,
                sort_order=0,
                actions_json=[
                    {"id": a.id, "label": a.label, "evidence_id": a.evidence_id}
                    for a in case.scene.actions
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
                    source_scene_id=case.scene.id,
                    source_character_id=None,
                    initial_credibility=evidence.credibility,
                    sort_order=order,
                )
            )
        for knowledge in case.knowledge:
            if knowledge.disclosure == "PUBLIC":
                continue
            self._db.add(
                CharacterSecret(
                    template_id=template_id,
                    secret_id=knowledge.id,
                    character_id=knowledge.known_by[0],
                    content=knowledge.content,
                    known_by_json=list(knowledge.known_by),
                    assertion_kind="TESTIMONY",
                    initial_credibility="UNVERIFIED",
                    disclosure=knowledge.disclosure,
                )
            )
        self._db.flush()

        # The slice keeps dependencies on actions; the table keys them by granted evidence.
        dependencies: dict[str, tuple] = {}
        for action in case.scene.actions:
            key = (tuple(action.requires.all_of), tuple(action.requires.any_of))
            if dependencies.setdefault(action.evidence_id, key) != key:
                raise ValueError("授予同一证据的调查动作必须使用相同的前置证据。")
        for evidence_id, (all_of, any_of) in dependencies.items():
            for mode, refs in (("ALL", all_of), ("ANY", any_of)):
                for required in refs:
                    self._db.add(
                        EvidenceDependency(
                            template_id=template_id,
                            evidence_id=evidence_id,
                            dependency_mode=mode,
                            required_evidence_id=required,
                        )
                    )
        lie = case.lie
        self._db.add(
            LieRule(
                template_id=template_id,
                lie_rule_id=lie.id,
                character_id=lie.npc_id,
                priority=0,
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
        self._db.flush()
        return template

    def load_case(self, template: CaseTemplate) -> Case:
        """Assemble the domain definition from the tables; the database is authoritative."""
        tid = template.template_id

        def rows(table, *order):
            return list(
                self._db.scalars(select(table).where(table.template_id == tid).order_by(*order))
            )

        characters = rows(Character, Character.sort_order)
        scenes = rows(Scene, Scene.sort_order, Scene.scene_id)
        evidence = rows(Evidence, Evidence.sort_order)
        secrets = rows(CharacterSecret, CharacterSecret.secret_id)
        lies = rows(LieRule, LieRule.priority, LieRule.lie_rule_id)
        dependencies = rows(
            EvidenceDependency,
            EvidenceDependency.evidence_id,
            EvidenceDependency.dependency_mode,
            EvidenceDependency.required_evidence_id,
        )
        npcs = [c for c in characters if c.is_interrogatable]
        if len(scenes) != 1 or len(npcs) != 1 or len(lies) != 1:
            raise ValueError("切片定义必须恰好包含 1 个场景、1 个可审讯角色和 1 层谎言。")
        scene, npc, lie = scenes[0], npcs[0], lies[0]

        def requires(evidence_id: str) -> dict:
            group = {"ALL": [], "ANY": []}
            for dependency in dependencies:
                if dependency.evidence_id == evidence_id:
                    group[dependency.dependency_mode].append(dependency.required_evidence_id)
            return {"all_of": group["ALL"], "any_of": group["ANY"]}

        effects = [
            {k: v for k, v in effect.items() if k != "lie_rule_id"}
            for effect in template.rules_json["present_effects"]
            if effect["lie_rule_id"] == lie.lie_rule_id
        ]
        admission = lie.admission_condition_json
        knowledge = list(template.public_knowledge_json) + [
            {
                "id": s.secret_id,
                "content": s.content,
                "known_by": s.known_by_json,
                "disclosure": s.disclosure,
            }
            for s in secrets
        ]
        definition = {
            "schema_version": template.definition_schema_version,
            "scope": template.definition_scope,
            "case_id": template.case_id,
            "version": template.version,
            "rules_version": template.rules_version,
            "title": template.title,
            "introduction": template.synopsis,
            "review_status": template.review_status,
            "scene": {
                "id": scene.scene_id,
                "name": scene.name,
                "description": scene.description,
                "actions": [
                    {**action, "requires": requires(action["evidence_id"])}
                    for action in scene.actions_json
                ],
            },
            "npc": {
                "id": npc.character_id,
                "name": npc.name,
                "role": npc.public_identity,
                "initial_pressure": npc.initial_pressure,
                "initial_trust": npc.initial_trust,
            },
            **template.accusation_options_json,
            "evidence": [
                {
                    "id": e.evidence_id,
                    "title": e.name,
                    "content": e.content,
                    "source": e.source_label,
                    "credibility": e.initial_credibility,
                }
                for e in evidence
            ],
            "knowledge": knowledge,
            "lie": {
                "id": lie.lie_rule_id,
                "npc_id": lie.character_id,
                "counterevidence": lie.counterevidence_json,
                "admission_presented": admission["presented"],
                "admission_pressure_min": admission["pressure_min"],
                "admission_trust_min": admission["trust_min"],
                "statements": lie.statements_json,
                "admitted_knowledge_id": lie.on_admitted_json["knowledge_id"],
                "effects": effects,
            },
            "interrogation": template.rules_json["interrogation"],
            "truth": template.truth_json,
            "scoring": template.scoring_policy_json,
        }
        return Case.model_validate_json(json.dumps(definition, ensure_ascii=False))
