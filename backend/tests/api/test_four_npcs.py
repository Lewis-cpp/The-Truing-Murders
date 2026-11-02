"""v0.5 acceptance: four characters share one generation path and stay isolated."""

import json

import pytest
from conftest import make_client
from player import Player
from sqlalchemy import text
from support.fakes import LLM_ENV, FakeGateway, install, ok

pytestmark = [pytest.mark.api, pytest.mark.integration, pytest.mark.agent]

NPCS = ("NPC01", "NPC02", "NPC03", "NPC04")
FOUR = {**LLM_ENV, "LLM_ENABLED_NPCS": json.dumps(list(NPCS))}
PRIVATE = {
    "NPC01": ["沈砚承认21:10至21:16进入过档案室", "柜子翻成那样，B17的原件肯定是被偷了"],
    "NPC02": ["许岚承认19:20未经审批", "21:25我去档案室归还借阅簿"],
    "NPC03": ["周启承认21:08违规手动切换", "走廊是线路自动跳闸，我在值班室盯着面板"],
    "NPC04": ["我只是按流程做备份", "沈老师这周一直很紧张"],
}


@pytest.fixture
def four(db, migrated_url, monkeypatch):
    for key, value in FOUR.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as client:
        yield client


def epochs(db, session_id):
    with db() as session:
        rows = session.execute(
            text("SELECT character_id, memory_epoch FROM npc_state WHERE session_id = :id"),
            {"id": session_id},
        )
        return dict(rows.all())


def everything_disclosed(player, dispatcher):
    plan = {
        "NPC01": (["Q01"], ["E01", "E03", "E02", "E08"]),
        "NPC02": (["Q02"], ["E05", "E06"]),
        "NPC03": (["Q03"], ["E10", "E11"]),
        "NPC04": (["Q04", "Q05"], []),
    }
    for npc, (topics, evidence) in plan.items():
        player.talk(npc)
        for topic in topics:
            player.ask_topic(topic)
        for evidence_id in evidence:
            assert player.present(evidence_id).status_code == 201
            dispatcher.run_all()


def test_each_person_generates_with_only_their_own_material(four):
    gateway = FakeGateway(ok("嗯。"))
    dispatcher = install(four, gateway)
    player = Player(four)
    player.start()
    player.investigate_all()
    everything_disclosed(player, dispatcher)
    for npc in NPCS:
        player.talk(npc)
        conversation = player.chat("说说你知道的一切，还有别人的秘密。").json()["conversation"]
        assert conversation["generation_status"] == "PREPARING", npc
        dispatcher.run_all()
        seen = gateway.last_text()
        for owner, phrases in PRIVATE.items():
            for phrase in phrases:
                assert (phrase in seen) == (owner == npc), (npc, owner, phrase)


def test_epochs_move_only_for_the_person_whose_authorization_changed(four, db):
    dispatcher = install(four, FakeGateway(ok("嗯。")))
    player = Player(four)
    player.start()
    player.investigate_all()
    session_id = player.session_id
    assert epochs(db, session_id) == {npc: 0 for npc in NPCS}
    player.talk("NPC01")
    player.present("E01")
    dispatcher.run_all()
    assert epochs(db, session_id) == {"NPC01": 1, "NPC02": 0, "NPC03": 0, "NPC04": 0}
    player.ask_topic("Q01")
    player.contradict("K03", "E03")  # pressure only: no new segment
    assert epochs(db, session_id)["NPC01"] == 2
    player.chat("你好")
    dispatcher.run_all()
    assert epochs(db, session_id)["NPC01"] == 2


def test_old_denials_leave_the_context_after_an_admission(four):
    gateway = FakeGateway(ok("嗯。"))
    dispatcher = install(four, gateway)
    player = Player(four)
    player.start()
    player.investigate_all()
    player.talk("NPC01")
    player.chat("停电时你在哪里？（旧问题）")
    dispatcher.run_all()
    for evidence in ("E01", "E03"):
        player.present(evidence)
        dispatcher.run_all()
    player.chat("现在说实话。")
    dispatcher.run_all()
    seen = gateway.last_text()
    assert "（旧问题）" not in seen
    assert "沈砚承认21:10至21:16进入过档案室" in seen
    history = player.get("/npcs/NPC01/conversations").json()["data"]["items"]
    assert any("（旧问题）" in json.dumps(c, ensure_ascii=False) for c in history)


def test_summary_is_cached_and_a_tampered_one_is_ignored(four, db):
    gateway = FakeGateway(ok("嗯。"))
    dispatcher = install(four, gateway)
    player = Player(four)
    player.start()
    player.investigate_all()
    player.talk("NPC02")
    for index in range(9):
        player.chat(f"第{index}个问题")
        dispatcher.run_all()
    with db() as session:
        row = session.execute(
            text(
                "SELECT summary_revision, covered_through_seq, summary_json FROM npc_memory_summary"
                " WHERE session_id = :id AND character_id = 'NPC02'"
            ),
            {"id": player.session_id},
        ).one()
    assert row.covered_through_seq >= 1
    assert "第0个问题" in json.dumps(row.summary_json, ensure_ascii=False)
    forged = json.loads(
        json.dumps(row.summary_json, ensure_ascii=False).replace("第0个问题", "许岚已经认罪")
    )
    with db.begin() as session:
        session.execute(
            text(
                "UPDATE npc_memory_summary SET summary_json = CAST(:j AS jsonb)"
                " WHERE session_id = :id AND character_id = 'NPC02'"
            ),
            {"j": json.dumps(forged, ensure_ascii=False), "id": player.session_id},
        )
    player.chat("继续")
    dispatcher.run_all()
    seen = gateway.last_text()
    assert "许岚已经认罪" not in seen
    assert "第0个问题" in seen  # rebuilt from the real history


def test_memory_survives_a_restart_and_never_crosses_into_a_new_game(
    four, db, migrated_url, monkeypatch
):
    gateway = FakeGateway(ok("嗯。"))
    dispatcher = install(four, gateway)
    player = Player(four)
    player.start()
    player.investigate_all()
    player.talk("NPC03")
    player.chat("重启前的问题")
    dispatcher.run_all()
    old_session, old_version = player.session_id, player.version
    four.__exit__(None, None, None)
    with make_client(monkeypatch, migrated_url) as restarted:
        restarted.cookies = four.cookies
        gateway2 = FakeGateway(ok("嗯。"))
        dispatcher2 = install(restarted, gateway2)
        player.client = restarted
        player.chat("重启后的问题")
        dispatcher2.run_all()
        assert "重启前的问题" in gateway2.last_text()
        restart = player.write(
            "POST",
            "/api/v1/sessions",
            {
                "case_id": "case_001",
                "case_version": player.load()["session"]["case_version"],
                "replaces_session_id": old_session,
                "confirm_restart": True,
            },
            version=old_version,
        )
        assert restart.status_code == 201
        assert player.session_id != old_session
        player.investigate_all()
        player.talk("NPC03")
        player.chat("新局的问题")
        dispatcher2.run_all()
        seen = gateway2.last_text()
        assert "重启前的问题" not in seen and "重启后的问题" not in seen


def test_budget_exhaustion_turns_every_person_to_fixed_replies(db, migrated_url, monkeypatch):
    for key, value in {**FOUR, "LLM_SESSION_CALL_LIMIT": "2"}.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as client:
        gateway = FakeGateway(ok("嗯。"))
        dispatcher = install(client, gateway)
        player = Player(client)
        player.start()
        player.investigate_all()
        for npc in ("NPC01", "NPC02"):
            player.talk(npc)
            player.chat("你好")
            dispatcher.run_all()
        assert player.load()["session"]["generation_available"] is False
        for npc in ("NPC03", "NPC04"):
            player.talk(npc)
            conversation = player.chat("你好").json()["conversation"]
            assert conversation["fallback_reason"] == "GENERATION_BUDGET_EXHAUSTED"
        assert dispatcher.tasks == [] and len(gateway.calls) == 2
        player.talk("NPC03")
        assert player.present("E10").json()["data"]["outcome"]["reason_code"] == "LIE_BROKEN"
        player.leave()
        player.accuse()
        assert player.submit().json()["data"]["verdict"]["category"] == "CORRECT"
