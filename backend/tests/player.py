"""A tiny HTTP player that tracks the last known version, like the web client does."""

import uuid

from fastapi.testclient import TestClient

from backend.application.case import load_case

CASE_VERSION = load_case().version

CORRECT = {
    "suspect_character_id": "NPC01",
    "weapon_option_id": "W01",
    "motive_option_id": "M01",
    "ordered_process_step_ids": ["P_ENTER", "P_ATTACK", "P_STAGE"],
    "cited_evidence_ids": ["E01", "E02", "E03"],
    "step_evidence_links": [
        {"step_id": "P_ENTER", "evidence_id": "E01"},
        {"step_id": "P_ATTACK", "evidence_id": "E02"},
        {"step_id": "P_STAGE", "evidence_id": "E03"},
    ],
    "explanation": "",
}


class Player:
    def __init__(self, client: TestClient):
        self.client = client
        self.session_id: str | None = None
        self.version: int | None = None
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

    def investigate(self, action_id: str, **kwargs):
        return self.write(
            "POST", self.path("/scenes/S01/investigations"), {"action_id": action_id}, **kwargs
        )

    def talk(self, npc_id="NPC01", **kwargs):
        return self.write("PUT", self.path("/interrogation"), {"npc_id": npc_id}, **kwargs)

    def present(self, evidence_id: str, npc_id="NPC01", **kwargs):
        return self.write(
            "POST",
            self.path(f"/npcs/{npc_id}/evidence-presentations"),
            {"evidence_id": evidence_id},
            **kwargs,
        )

    def ask_topic(self, topic_id: str, npc_id="NPC01", **kwargs):
        return self.write(
            "POST", self.path(f"/npcs/{npc_id}/questions"), {"topic_id": topic_id}, **kwargs
        )

    def contradict(self, knowledge_id: str, evidence_id: str, npc_id="NPC01", **kwargs):
        return self.write(
            "POST",
            self.path(f"/npcs/{npc_id}/contradictions"),
            {"knowledge_id": knowledge_id, "evidence_id": evidence_id},
            **kwargs,
        )

    def leave(self, **kwargs):
        return self.write("DELETE", self.path("/interrogation"), **kwargs)

    def accuse(self, **kwargs):
        return self.write("PUT", self.path("/accusation-preparation"), {}, **kwargs)

    def submit(self, content=None, confirm=True, **kwargs):
        body = {"content": content or CORRECT, "confirm": confirm}
        return self.write("POST", self.path("/accusation"), body, **kwargs)

    def load(self):
        response = self.client.get(self.path(""))
        assert response.status_code == 200, response.text
        return response.json()
