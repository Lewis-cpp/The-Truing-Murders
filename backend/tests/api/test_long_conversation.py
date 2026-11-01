"""v0.5 acceptance: a controllable model over 100 rounds keeps the input bounded and admissions."""

import json

import pytest
from conftest import make_client
from player import Player
from support.fakes import LLM_ENV, FakeGateway, install, ok

from backend.application.memory import estimate_tokens

pytestmark = [pytest.mark.api, pytest.mark.integration, pytest.mark.agent]

ADMITTED = "沈砚承认21:10至21:16进入过档案室"
DENIAL_QUESTION = "（承认之前的问题）"


@pytest.fixture
def client_all(db, migrated_url, monkeypatch):
    env = {**LLM_ENV, "LLM_ENABLED_NPCS": '["NPC01", "NPC02", "NPC03", "NPC04"]'}
    env["LLM_SESSION_CALL_LIMIT"] = "500"
    env["LLM_SESSION_TOKEN_LIMIT"] = "10000000"
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as client:
        yield client


def test_one_hundred_rounds_stay_bounded_and_never_forget_an_admission(client_all):
    gateway = FakeGateway(ok("我需要核对一下。" * 20))
    dispatcher = install(client_all, gateway)
    player = Player(client_all)
    player.start()
    player.investigate_all()
    player.talk("NPC01")
    for index in range(20):
        player.chat(f"{DENIAL_QUESTION}{index}" + "啊" * 100)
        dispatcher.run_all()
    for evidence in ("E01", "E03"):
        player.present(evidence)
        dispatcher.run_all()
    for index in range(78):
        if index in (30, 31):
            # Leave and come back: NPC01's memory must neither leak nor reset admitted facts.
            player.talk("NPC02")
            player.chat("你好")
            dispatcher.run_all()
            player.talk("NPC01")
        player.chat(f"承认之后的第{index}个问题" + "嗯" * 100)
        dispatcher.run_all()
        call = gateway.calls[-1]
        seen = json.dumps(list(call.messages), ensure_ascii=False)
        assert estimate_tokens(call.messages) <= 4000
        assert ADMITTED in call.messages[0]["content"]
        assert DENIAL_QUESTION not in seen
        assert sum(m["role"] == "assistant" for m in call.messages) <= 6
        assert "21:25我去档案室归还借阅簿" not in seen
    assert len(gateway.calls) >= 100
