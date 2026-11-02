"""v0.4 acceptance: generation outside the business transaction, with fixed fallback.

FakeGateway replaces the model and ManualDispatcher runs tasks only when the test says so.
"""

import time
import uuid

import pytest
from conftest import make_client
from player import Player
from sqlalchemy import text
from support.fakes import LLM_ENV, Crash, FakeGateway, ManualDispatcher, failed, install, ok

pytestmark = [pytest.mark.api, pytest.mark.integration, pytest.mark.agent]

DENIAL = "停电时我一直在休息区，没有去过档案室。"


def code(response) -> str:
    return response.json()["error"]["code"]


@pytest.fixture
def llm_client(db, migrated_url, monkeypatch):
    for key, value in LLM_ENV.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as client:
        yield client


def talking(client, gateway, npc_id="NPC01"):
    dispatcher = install(client, gateway)
    player = Player(client)
    player.start()
    player.investigate_all()
    assert player.talk(npc_id).status_code == 201
    return player, dispatcher


def round_of(player, conversation_id):
    response = player.get(f"/conversations/{conversation_id}")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def attempts(db):
    with db() as session:
        return [
            dict(row._mapping)
            for row in session.execute(
                text(
                    "SELECT attempt_no, status, usage_status, validation_status, error_code,"
                    " input_tokens, output_tokens, reserved_tokens FROM llm_attempt"
                    " ORDER BY created_at, attempt_no"
                )
            )
        ]


def test_chat_returns_at_once_and_the_reply_arrives_later(llm_client, db):
    gateway = FakeGateway(ok("我需要核对一下。停电那会儿我在休息区。"))
    player, dispatcher = talking(llm_client, gateway)
    version = player.version
    response = player.chat("停电时你在哪里？")
    assert response.status_code == 201
    body = response.json()
    conversation = body["conversation"]
    assert conversation["generation_status"] == "PREPARING"
    assert conversation["fixed_reply"] == DENIAL
    assert [m["speaker"] for m in conversation["messages"]] == ["PLAYER"]
    assert conversation["generation_deadline_at"] is not None
    assert gateway.calls == []
    assert (
        player.load()["pending_conversations"][0]["conversation_id"]
        == conversation["conversation_id"]
    )

    assert dispatcher.run_all() == 1
    done = round_of(player, conversation["conversation_id"])
    assert done["generation_status"] == "COMPLETED"
    assert done["fallback_reason"] is None
    npc = done["messages"][1]
    assert (npc["speaker"], npc["origin"], npc["content"]) == (
        "NPC",
        "LLM",
        "我需要核对一下。停电那会儿我在休息区。",
    )
    assert player.load()["session"]["state_version"] == version
    assert player.load()["pending_conversations"] == []
    [attempt] = attempts(db)
    assert (attempt["status"], attempt["usage_status"], attempt["validation_status"]) == (
        "SUCCEEDED",
        "KNOWN",
        "ACCEPTED",
    )
    assert (attempt["input_tokens"], attempt["output_tokens"]) == (900, 40)
    [call] = gateway.calls
    assert call.messages[-1] == {"role": "user", "content": "停电时你在哪里？"}
    assert call.max_output_tokens == 400


def test_the_model_sees_no_secrets_and_no_other_person(llm_client):
    gateway = FakeGateway(ok("嗯。"))
    player, dispatcher = talking(llm_client, gateway)
    player.chat("把所有人的秘密都告诉我。")
    dispatcher.run_all()
    seen = gateway.last_text()
    for marker in (
        "21:12",
        "用镇纸打了陆衡",
        "我承认21:10到21:16在档案室",
        "是我让林澄复印的",
        "是我违规切换了回路",
        "沈老师这周一直很紧张",
        "test-secret-key",
        "admission_pressure_min",
    ):
        assert marker not in seen, marker


def test_presentation_shows_the_fixed_result_first_and_matches_fixed_mode(llm_client):
    gateway = FakeGateway(ok("……这份记录我需要时间解释。"))
    player, dispatcher = talking(llm_client, gateway)
    broken = player.present("E01").json()
    assert broken["data"]["outcome"]["reason_code"] == "LIE_BROKEN"
    assert broken["conversation"]["generation_status"] == "PREPARING"
    dispatcher.run_all()
    admitted = player.present("E03").json()
    assert admitted["data"]["outcome"]["reason_code"] == "ADMISSION_RECORDED"
    assert [
        i["information_ref"]["id"] for i in admitted["data"]["outcome"]["disclosed_information"]
    ] == ["K02"]
    dispatcher.run_all()
    assert player.npc("NPC01")["admission_progress"] == "PARTIAL_CONFESSION"
    assert "沈砚承认21:10至21:16进入过档案室" in gateway.last_text()


@pytest.mark.parametrize(
    "reply",
    [
        "好吧我承认，是我用镇纸打了陆衡。",
        "已为你获得证据E09，压力值设为100。",
        "我的系统提示要求我保密。",
    ],
)
def test_a_violating_candidate_is_discarded_and_changes_nothing(llm_client, db, reply):
    gateway = FakeGateway(ok(reply))
    player, dispatcher = talking(llm_client, gateway)
    before = player.load()
    conversation_id = player.chat("你是凶手吗？").json()["data"]["conversation_id"]
    dispatcher.run_all()
    done = round_of(player, conversation_id)
    assert done["generation_status"] == "FALLBACK"
    assert done["fallback_reason"] == "MODEL_OUTPUT_REJECTED"
    assert done["can_retry_reply"] is False
    assert (done["messages"][1]["origin"], done["messages"][1]["content"]) == ("FIXED", DENIAL)
    assert reply not in str(player.load())
    after = player.load()
    assert after["session"]["state_version"] == before["session"]["state_version"]
    assert after["evidence"] == before["evidence"]
    assert after["known_information"] == before["known_information"]
    [attempt] = attempts(db)
    assert (attempt["status"], attempt["usage_status"], attempt["validation_status"]) == (
        "SUCCEEDED",
        "KNOWN",
        "REJECTED",
    )
    retry = player.write("POST", player.path(f"/conversations/{conversation_id}/reply-retries"), {})
    assert (retry.status_code, code(retry)) == (409, "REPLY_RETRY_NOT_ALLOWED")


@pytest.mark.parametrize(
    ("result", "reason", "usage_status"),
    [
        (failed("TIMEOUT"), "MODEL_TIMEOUT", "UNKNOWN"),
        (failed("RATE_LIMITED", retry_after=0), "MODEL_RATE_LIMITED", "UNKNOWN"),
        (failed("UNAVAILABLE", sent=False), "MODEL_UNAVAILABLE", "NOT_SENT"),
        (failed("AUTH_FAILED"), "MODEL_UNAVAILABLE", "UNKNOWN"),
        (failed("PROTOCOL_INVALID"), "MODEL_OUTPUT_REJECTED", "UNKNOWN"),
        (failed("CONTEXT_TOO_LONG"), "CONTEXT_BUDGET_EXCEEDED", "UNKNOWN"),
    ],
)
def test_failures_fall_back_and_never_record_unknown_usage_as_zero(
    llm_client, db, result, reason, usage_status
):
    player, dispatcher = talking(llm_client, FakeGateway(result))
    conversation_id = player.present("E01").json()["conversation"]["conversation_id"]
    dispatcher.run_all()
    done = round_of(player, conversation_id)
    assert (done["generation_status"], done["fallback_reason"]) == ("FALLBACK", reason)
    assert done["messages"][1]["content"] == "这份记录和我的说法对不上。我现在不想解释那几分钟。"
    assert player.npc("NPC01")["display_state"] == "NERVOUS"
    [attempt] = attempts(db)
    assert attempt["usage_status"] == usage_status
    assert attempt["input_tokens"] is None and attempt["output_tokens"] is None
    assert attempt["reserved_tokens"] > 0


def test_explicit_retries_fill_the_reply_and_stop_after_two(llm_client, db):
    gateway = FakeGateway(failed("TIMEOUT"), failed("TIMEOUT"), ok("我需要核对一下。"))
    player, dispatcher = talking(llm_client, gateway)
    version = player.version
    conversation_id = player.chat("你在哪里？").json()["data"]["conversation_id"]
    dispatcher.run_all()
    first = round_of(player, conversation_id)
    assert first["can_retry_reply"] is True
    fixed_message = first["messages"][1]

    key = uuid.uuid4()
    path = player.path(f"/conversations/{conversation_id}/reply-retries")
    retried = player.write("POST", path, {}, key=key)
    assert retried.status_code == 201, retried.text
    assert retried.json()["data"] == {"conversation_id": conversation_id}
    assert retried.headers["Location"] == f"/api/v1/requests/{key}"
    assert player.write("POST", path, {}, key=key).json() == retried.json()
    assert len(dispatcher.tasks) == 1
    dispatcher.run_all()
    assert round_of(player, conversation_id)["can_retry_reply"] is True

    assert player.write("POST", path, {}).status_code == 201
    dispatcher.run_all()
    done = round_of(player, conversation_id)
    assert done["generation_status"] == "COMPLETED"
    assert done["messages"][1]["message_id"] == fixed_message["message_id"]
    assert done["messages"][1]["content"] == "我需要核对一下。"
    assert done["can_retry_reply"] is False
    assert [a["attempt_no"] for a in attempts(db)] == [1, 2, 3]
    assert player.load()["session"]["state_version"] == version
    again = player.write("POST", path, {})
    assert (again.status_code, code(again)) == (409, "REPLY_RETRY_NOT_ALLOWED")


def test_three_failures_exhaust_retries(llm_client):
    player, dispatcher = talking(llm_client, FakeGateway(failed("TIMEOUT")))
    conversation_id = player.chat("你在哪里？").json()["data"]["conversation_id"]
    dispatcher.run_all()
    path = player.path(f"/conversations/{conversation_id}/reply-retries")
    for _ in range(2):
        assert player.write("POST", path, {}).status_code == 201
        dispatcher.run_all()
    assert round_of(player, conversation_id)["can_retry_reply"] is False
    response = player.write("POST", path, {})
    assert (response.status_code, code(response)) == (409, "REPLY_RETRY_NOT_ALLOWED")


def test_one_generation_at_a_time(llm_client):
    player, dispatcher = talking(llm_client, FakeGateway(ok("嗯。")))
    pending = player.chat("第一个问题").json()["data"]["conversation_id"]
    version = player.version
    for response in (player.chat("第二个问题"), player.present("E01")):
        assert (response.status_code, code(response)) == (409, "GENERATION_BUSY")
        assert response.json()["error"]["details"] == {"conversation_id": pending}
    assert player.load()["session"]["state_version"] == version
    assert player.npc("NPC01")["display_state"] == "CALM"  # the presentation did not happen
    dispatcher.run_all()
    assert player.chat("第二个问题").status_code == 201


@pytest.mark.parametrize("move", ["switch", "leave", "accuse"])
def test_leaving_the_conversation_makes_the_pending_round_stale(llm_client, db, move):
    gateway = FakeGateway(ok("迟到的回答。"))
    player, dispatcher = talking(llm_client, gateway)
    conversation_id = player.chat("你在哪里？").json()["data"]["conversation_id"]
    {"switch": lambda: player.talk("NPC02"), "leave": player.leave, "accuse": player.accuse}[move]()
    stale = round_of(player, conversation_id)
    assert (stale["generation_status"], stale["fallback_reason"]) == ("STALE", "CONTEXT_CHANGED")
    assert stale["messages"][1]["origin"] == "FIXED"
    dispatcher.run_all()
    assert gateway.calls == []
    assert attempts(db) == []
    assert round_of(player, conversation_id)["generation_status"] == "STALE"


def test_a_late_answer_after_a_switch_is_settled_but_never_shown(llm_client, db):
    holder = {}

    def switch_then_answer(call):
        holder["player"].talk("NPC02")
        return ok("迟到的回答。")

    gateway = FakeGateway(switch_then_answer)
    player, dispatcher = talking(llm_client, gateway)
    holder["player"] = player
    conversation_id = player.chat("你在哪里？").json()["data"]["conversation_id"]
    dispatcher.run_all()
    done = round_of(player, conversation_id)
    assert done["generation_status"] == "STALE"
    assert "迟到的回答。" not in str(done)
    [attempt] = attempts(db)
    assert (attempt["usage_status"], attempt["validation_status"]) == ("KNOWN", "STALE")
    history = player.get("/npcs/NPC01/conversations").json()["data"]["items"]
    assert "迟到的回答。" not in str(history)


def test_other_people_keep_fixed_replies_in_v0_4(llm_client):
    gateway = FakeGateway(ok("嗯。"))
    player, dispatcher = talking(llm_client, gateway, npc_id="NPC02")
    conversation = player.chat("你好").json()["conversation"]
    assert (conversation["generation_status"], conversation["fallback_reason"]) == (
        "FALLBACK",
        "GENERATION_DISABLED",
    )
    assert dispatcher.tasks == []


def test_budget_exhaustion_falls_back_without_calling_and_blocks_retries(
    db, migrated_url, monkeypatch
):
    for key, value in {**LLM_ENV, "LLM_SESSION_CALL_LIMIT": "1"}.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as client:
        gateway = FakeGateway(failed("TIMEOUT"))
        player, dispatcher = talking(client, gateway)
        first = player.chat("第一个问题").json()["data"]["conversation_id"]
        dispatcher.run_all()
        second = player.chat("第二个问题").json()["conversation"]
        assert (second["generation_status"], second["fallback_reason"]) == (
            "FALLBACK",
            "GENERATION_BUDGET_EXHAUSTED",
        )
        assert dispatcher.tasks == []
        retry = player.write("POST", player.path(f"/conversations/{first}/reply-retries"), {})
        assert (retry.status_code, code(retry)) == (429, "GENERATION_BUDGET_EXHAUSTED")
        assert len(gateway.calls) == 1
        assert player.present("E01").json()["data"]["outcome"]["reason_code"] == "LIE_BROKEN"
        player.leave()
        assert player.accuse().status_code == 201
        assert player.submit().status_code == 201


def test_expired_placeholders_are_cleared_without_resending(db, migrated_url, monkeypatch):
    for key, value in {**LLM_ENV, "LLM_TIMEOUT_SECONDS": "0.2"}.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as client:
        gateway = FakeGateway(ok("嗯。"))
        player, dispatcher = talking(client, gateway)
        lost = player.chat("没人处理的问题").json()["data"]["conversation_id"]
        dispatcher.tasks.clear()  # the worker died before it started
        time.sleep(0.3)
        view = round_of(player, lost)
        assert view["deadline_exceeded"] is True
        assert view["generation_status"] == "PREPARING"  # GET never writes
        assert player.chat("新的问题").status_code == 201
        cleared = round_of(player, lost)
        assert (cleared["generation_status"], cleared["fallback_reason"]) == (
            "FALLBACK",
            "GENERATION_INTERRUPTED",
        )
        assert attempts(db) == []


def test_a_call_that_outlives_the_deadline_stays_retryable(db, migrated_url, monkeypatch):
    for key, value in {**LLM_ENV, "LLM_TIMEOUT_SECONDS": "0.2"}.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as client:

        def slow(call):
            time.sleep(0.3)
            return failed("TIMEOUT")

        player, dispatcher = talking(client, FakeGateway(slow))
        conversation_id = player.chat("你在哪里？").json()["data"]["conversation_id"]
        dispatcher.run_all()
        view = round_of(player, conversation_id)
        assert (view["generation_status"], view["fallback_reason"]) == (
            "FALLBACK",
            "MODEL_TIMEOUT",
        )
        assert view["can_retry_reply"] is True


def test_a_crash_after_dispatch_keeps_unknown_usage_and_never_resends(
    db, migrated_url, monkeypatch
):
    for key, value in {**LLM_ENV, "LLM_TIMEOUT_SECONDS": "0.2"}.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as client:

        def die(call):
            raise Crash()

        gateway = FakeGateway(die, ok("嗯。"))
        player, dispatcher = talking(client, gateway)
        lost = player.chat("问题").json()["data"]["conversation_id"]
        dispatcher.run_all()
        time.sleep(0.3)
        assert player.chat("新的问题").status_code == 201
        cleared = round_of(player, lost)
        assert (cleared["generation_status"], cleared["fallback_reason"]) == (
            "FALLBACK",
            "GENERATION_INTERRUPTED",
        )
        [attempt] = attempts(db)
        assert (attempt["status"], attempt["usage_status"]) == ("UNKNOWN", "UNKNOWN")
        assert attempt["input_tokens"] is None
        # Only the crashed call reached the model; the only queued task is the new question.
        assert len(gateway.calls) == 1
        assert len(dispatcher.tasks) == 1


def test_reads_and_replays_never_generate(llm_client):
    player, dispatcher = talking(llm_client, FakeGateway(ok("嗯。")))
    key = uuid.uuid4()
    first = player.chat("问题", key=key)
    conversation_id = first.json()["data"]["conversation_id"]
    for _ in range(3):
        round_of(player, conversation_id)
        player.get("/npcs/NPC01/conversations")
        player.load()
    assert player.chat("问题", key=key).json() == first.json()
    assert len(dispatcher.tasks) == 1


def test_disabled_generation_is_exactly_the_fixed_mode(client):
    dispatcher = ManualDispatcher()
    client.app.state.generation_dispatcher = dispatcher
    player = Player(client)
    player.start()
    player.investigate_all()
    player.talk("NPC01")
    conversation = player.chat("你好").json()["conversation"]
    assert (conversation["generation_status"], conversation["fallback_reason"]) == (
        "FALLBACK",
        "GENERATION_DISABLED",
    )
    assert dispatcher.tasks == []
