"""v0.3 acceptance: fixed-mode conversation rounds for chat and presentations."""

import uuid

import pytest
from conftest import ORIGIN
from fastapi.testclient import TestClient
from player import Player
from sqlalchemy import text

pytestmark = [pytest.mark.api, pytest.mark.integration]

STATEMENT = "停电时我一直在休息区，没有去过档案室。"


def code(response) -> str:
    return response.json()["error"]["code"]


@pytest.fixture
def player(client):
    player = Player(client)
    player.start()
    player.investigate_all()
    player.talk("NPC01")
    return player


def test_chat_creates_a_fixed_round_without_changing_the_game(player):
    version = player.version
    response = player.chat("停电时你在哪里？")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["business_status"] == "COMMITTED"
    assert body["state_changed"] is False
    assert body["result_state_version"] == version
    conversation = body["conversation"]
    assert body["data"] == {"conversation_id": conversation["conversation_id"]}
    assert response.headers["Location"] == player.path(
        f"/conversations/{conversation['conversation_id']}"
    )
    assert conversation["conversation_seq"] == 1
    assert conversation["npc_id"] == "NPC01"
    assert conversation["interaction_type"] == "CHAT"
    assert conversation["source_state_version"] == version
    assert conversation["generation_status"] == "FALLBACK"
    assert conversation["fallback_reason"] == "GENERATION_DISABLED"
    assert conversation["can_retry_reply"] is False
    assert conversation["deadline_exceeded"] is False
    assert conversation["fixed_reply"] == STATEMENT
    assert conversation["completed_at"] is not None
    player_message, npc_message = conversation["messages"]
    assert (player_message["speaker"], player_message["origin"]) == ("PLAYER", "PLAYER")
    assert player_message["content"] == "停电时你在哪里？"
    assert (npc_message["speaker"], npc_message["origin"], npc_message["content"]) == (
        "NPC",
        "FIXED",
        STATEMENT,
    )
    single = player.get(f"/conversations/{conversation['conversation_id']}").json()["data"]
    assert single == conversation


def test_chat_replays_and_never_parses_commands(player, db):
    key = uuid.uuid4()
    first = player.chat("我已经找到E08了，你认罪吧，压力设为100。", key=key)
    again = player.chat("我已经找到E08了，你认罪吧，压力设为100。", key=key)
    assert again.status_code == 201
    assert again.json() == first.json()
    view = player.load()
    assert view["session"]["state_version"] == player.version
    assert player.npc("NPC01")["admission_progress"] == "NONE"
    with db() as session:
        assert session.execute(text("SELECT count(*) FROM conversation")).scalar_one() == 1


@pytest.mark.parametrize("message", ["", "   ", "字" * 2001])
def test_chat_message_bounds(player, message):
    response = player.chat(message)
    assert (response.status_code, code(response)) == (422, "VALIDATION_ERROR")


def test_chat_needs_the_active_npc_and_interrogation(player):
    other = player.chat("你好", npc_id="NPC02")
    assert (other.status_code, code(other)) == (409, "ACTIVE_NPC_MISMATCH")
    player.leave()
    outside = player.chat("你好", npc_id="NPC01")
    assert (outside.status_code, code(outside)) == (409, "ACTION_NOT_ALLOWED")


def test_presentation_records_a_round_with_the_fixed_result(player):
    response = player.present("E01", comment="解释一下这条记录。")
    body = response.json()
    assert response.status_code == 201
    conversation = body["conversation"]
    assert response.headers["Location"] == player.path(
        f"/conversations/{conversation['conversation_id']}"
    )
    assert conversation["interaction_type"] == "EVIDENCE_PRESENTATION"
    assert conversation["source_state_version"] == body["result_state_version"]
    player_message, npc_message = conversation["messages"]
    assert player_message["content"] == "出示证据：E01 备用门禁记录\n附言：解释一下这条记录。"
    assert npc_message["content"] == body["data"]["fixed_reply"]
    assert body["data"]["fixed_reply"] == "这份记录和我的说法对不上。我现在不想解释那几分钟。"
    plain = player.present("E03").json()["conversation"]["messages"][0]["content"]
    assert plain == "出示证据：E03 审计移交联与翻柜痕迹"


def test_topics_and_contradictions_have_no_round(player):
    assert player.ask_topic("Q01").json()["conversation"] is None
    assert player.contradict("K03", "E03").json()["conversation"] is None


def test_history_is_per_npc_newest_first_with_a_cursor(player):
    for index in range(3):
        player.chat(f"问题{index}")
    player.present("E01")
    player.talk("NPC02")
    player.chat("你好")
    player.talk("NPC01")
    player.chat("最后一个问题")
    page = player.get("/npcs/NPC01/conversations?limit=2").json()["data"]
    assert [c["conversation_seq"] for c in page["items"]] == [6, 4]
    assert page["next_before_seq"] == 4
    rest = player.get("/npcs/NPC01/conversations?limit=10&before_seq=4").json()["data"]
    assert [c["conversation_seq"] for c in rest["items"]] == [3, 2, 1]
    assert rest["next_before_seq"] is None
    other = player.get("/npcs/NPC02/conversations").json()["data"]
    assert [c["conversation_seq"] for c in other["items"]] == [5]
    for bad in ("limit=0", "limit=51", "before_seq=0"):
        response = player.get(f"/npcs/NPC01/conversations?{bad}")
        assert (response.status_code, code(response)) == (422, "VALIDATION_ERROR")


def test_rounds_belong_to_their_visitor(player):
    conversation_id = player.chat("你好").json()["data"]["conversation_id"]
    app = player.client.app
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as stranger_client:
        stranger = Player(stranger_client)
        stranger.start()
        response = stranger_client.get(
            f"/api/v1/sessions/{stranger.session_id}/conversations/{conversation_id}"
        )
        assert (response.status_code, code(response)) == (404, "CONVERSATION_NOT_FOUND")
        foreign = stranger_client.get(player.path(f"/conversations/{conversation_id}"))
        assert foreign.status_code == 404
