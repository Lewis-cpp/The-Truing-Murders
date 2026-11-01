"""v0.5 acceptance: one gateway shared by real worker threads never mixes sessions or people."""

import json
import threading
import time

import pytest
from conftest import ORIGIN, make_client
from fastapi.testclient import TestClient
from player import Player
from support.fakes import LLM_ENV, ok

from backend.application.generation import ThreadDispatcher

pytestmark = [pytest.mark.integration, pytest.mark.agent]


class SlowEcho:
    """Answers with the last user message after a short delay, so calls overlap."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def generate(self, call):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.2)
        with self.lock:
            self.active -= 1
            self.calls.append(call)
        return ok("收到：" + call.messages[-1]["content"][:20])


def test_parallel_sessions_and_people_get_their_own_messages(db, migrated_url, monkeypatch):
    env = {**LLM_ENV, "LLM_ENABLED_NPCS": '["NPC01", "NPC02", "NPC03", "NPC04"]'}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as first_client:
        gateway = SlowEcho()
        dispatcher = ThreadDispatcher(max_workers=4)
        first_client.app.state.llm_gateway = gateway
        first_client.app.state.generation_dispatcher = dispatcher
        with TestClient(
            first_client.app, base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as second_client:
            players = []
            for client, npc in ((first_client, "NPC01"), (second_client, "NPC03")):
                player = Player(client)
                player.start()
                player.investigate_all()
                player.talk(npc)
                players.append((player, npc))
            ids = []
            for player, npc in players:
                ids.append(
                    player.chat(f"来自{player.session_id}给{npc}的问题").json()["data"][
                        "conversation_id"
                    ]
                )
            dispatcher.shutdown(wait=True)
            assert gateway.peak >= 2
            for (player, _npc), conversation_id in zip(players, ids, strict=True):
                done = player.get(f"/conversations/{conversation_id}").json()["data"]
                assert done["generation_status"] == "COMPLETED"
                assert player.session_id[:8] in done["messages"][1]["content"]
            for call in gateway.calls:
                seen = json.dumps(list(call.messages), ensure_ascii=False)
                owners = [p.session_id for p, _ in players if p.session_id in seen]
                assert len(owners) == 1
                if "给NPC01" in seen:
                    assert (
                        "沈砚" in call.messages[0]["content"]
                        and "周启" not in call.messages[0]["content"]
                    )
                else:
                    assert "周启" in call.messages[0]["content"] and "沈砚，公开身份" not in seen
