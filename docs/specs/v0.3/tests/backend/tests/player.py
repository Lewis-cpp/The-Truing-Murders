"""A tiny HTTP player that tracks the last known version, like the web client does.

v0.3: scenes are resolved from the action ID, interrogation calls default to the active NPC.
"""

import uuid

from fastapi.testclient import TestClient

from backend.application.case import load_case

CASE = load_case()
CASE_VERSION = CASE.version
ACTION_SCENES = {a.id: s.id for s in CASE.scenes for a in s.actions}
ALL_ACTIONS = [a.id for s in CASE.scenes for a in s.actions]
NO_CONFESSION_ORDER = [f"A{i:02d}" for i in range(1, 13)]

CORRECT = {
    "suspect_character_id": "NPC01",
    "weapon_option_id": "W01",
    "motive_option_id": "M01",
    "ordered_process_step_ids": ["P_ENTER", "P_ATTACK", "P_STAGE"],
    "cited_evidence_ids": ["E01", "E02", "E03", "E08", "E11"],
    "step_evidence_links": [
        {"step_id": "P_ENTER", "evidence_id": "E01"},
        {"step_id": "P_ENTER", "evidence_id": "E11"},
        {"step_id": "P_ATTACK", "evidence_id": "E02"},
        {"step_id": "P_STAGE", "evidence_id": "E03"},
        {"step_id": "P_STAGE", "evidence_id": "E08"},
    ],
    "explanation": "",
}
EMPTY_DRAFT = {
    "suspect_character_id": None,
    "weapon_option_id": None,
    "motive_option_id": None,
    "ordered_process_step_ids": [],
    "cited_evidence_ids": [],
    "step_evidence_links": [],
    "explanation": "",
}


def content_from(accusation: dict, explanation: str = "") -> dict:
    """Converts a domain-shaped expectation (full_case_verdicts.json) into AccusationContent."""
    return {
        "suspect_character_id": accusation["culprit"],
        "weapon_option_id": accusation["weapon"],
        "motive_option_id": accusation["motive"],
        "ordered_process_step_ids": accusation["steps"],
        "cited_evidence_ids": accusation["cited_evidence_ids"],
        "step_evidence_links": accusation["evidence_links"],
        "explanation": explanation,
    }


class Player:
    def __init__(self, client: TestClient):
        self.client = client
        self.session_id: str | None = None
        self.version: int | None = None
        self.active_npc: str | None = None
        response = client.post("/api/v1/visitors", json={})
        assert response.status_code in (200, 201), response.text

    def write(self, method: str, path: str, body=None, *, key=None, version="auto"):
        headers = {"Idempotency-Key": str(key or uuid.uuid4())}
        if version == "auto":
            version = self.version
        if version is not None:
            headers["X-Expected-State-Version"] = str(version)
        response = self.client.request(method, path, json=body, headers=headers)
        if response.status_code < 300 and "result_state_version" in response.json():
            data = response.json()
            self.session_id = data["session_id"]
            self.version = data["result_state_version"]
            self.active_npc = data["active_npc_id_after"]
        return response

    def start(self):
        response = self.write(
            "POST",
            "/api/v1/sessions",
            {"case_id": "case_001", "case_version": CASE_VERSION},
            version=None,
        )
        assert response.status_code == 201, response.text
        return response

    def path(self, suffix: str) -> str:
        return f"/api/v1/sessions/{self.session_id}{suffix}"

    def get(self, suffix: str):
        return self.client.get(self.path(suffix))

    def investigate(self, action_id: str, scene_id: str | None = None, **kwargs):
        scene = scene_id or ACTION_SCENES.get(action_id, "S01")
        return self.write(
            "POST", self.path(f"/scenes/{scene}/investigations"), {"action_id": action_id}, **kwargs
        )

    def investigate_all(self, actions=NO_CONFESSION_ORDER):
        for action in actions:
            response = self.investigate(action)
            assert response.status_code == 201, response.text

    def talk(self, npc_id="NPC01", **kwargs):
        return self.write("PUT", self.path("/interrogation"), {"npc_id": npc_id}, **kwargs)

    def _npc(self, npc_id):
        return npc_id or self.active_npc or "NPC01"

    def present(self, evidence_id: str, npc_id=None, comment=None, **kwargs):
        body = {"evidence_id": evidence_id}
        if comment is not None:
            body["comment"] = comment
        return self.write(
            "POST", self.path(f"/npcs/{self._npc(npc_id)}/evidence-presentations"), body, **kwargs
        )

    def chat(self, message: str, npc_id=None, **kwargs):
        return self.write(
            "POST",
            self.path(f"/npcs/{self._npc(npc_id)}/conversations"),
            {"message": message},
            **kwargs,
        )

    def ask_topic(self, topic_id: str, npc_id=None, **kwargs):
        return self.write(
            "POST",
            self.path(f"/npcs/{self._npc(npc_id)}/questions"),
            {"topic_id": topic_id},
            **kwargs,
        )

    def contradict(self, knowledge_id: str, evidence_id: str, npc_id=None, **kwargs):
        return self.write(
            "POST",
            self.path(f"/npcs/{self._npc(npc_id)}/contradictions"),
            {"knowledge_id": knowledge_id, "evidence_id": evidence_id},
            **kwargs,
        )

    def leave(self, **kwargs):
        return self.write("DELETE", self.path("/interrogation"), **kwargs)

    def accuse(self, **kwargs):
        return self.write("PUT", self.path("/accusation-preparation"), {}, **kwargs)

    def cancel_accusation(self, **kwargs):
        return self.write("DELETE", self.path("/accusation-preparation"), **kwargs)

    def save_draft(self, content: dict, **kwargs):
        return self.write("PUT", self.path("/accusation-draft"), {"content": content}, **kwargs)

    def submit(self, content=None, confirm=True, **kwargs):
        body = {"content": content or CORRECT, "confirm": confirm}
        return self.write("POST", self.path("/accusation"), body, **kwargs)

    def finish(self, **kwargs):
        return self.write("PUT", self.path("/review-completion"), {}, **kwargs)

    def load(self):
        response = self.client.get(self.path(""))
        assert response.status_code == 200, response.text
        return response.json()

    def npc(self, npc_id: str) -> dict:
        return next(n for n in self.load()["npcs"] if n["npc_id"] == npc_id)
