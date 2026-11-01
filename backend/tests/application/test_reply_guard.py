"""v0.4 acceptance: the backstop check on model replies (spec section 5)."""

import pytest
from backend.application.conversation import check_reply, load_guard

from backend.application.case import load_case
from backend.domain import rules
from backend.domain.state_machine import transition

pytestmark = [pytest.mark.unit, pytest.mark.agent]

CASE = load_case()
GUARD = load_guard()


def investigated():
    state = rules.new_game(CASE)
    for index in range(1, 13):
        state = rules.investigate(CASE, state, f"A{index:02d}")
    return state


def admitted(npc_id, evidence):
    state = transition(investigated(), "talk", npc_id)
    for evidence_id in evidence:
        state = rules.present(CASE, state, npc_id, evidence_id)
    return state


FRESH = investigated()


@pytest.mark.parametrize(
    ("npc_id", "text"),
    [
        ("NPC01", "停电那会儿我在休息区喝茶，没有去过档案室。"),
        ("NPC01", "我需要核对一下，再回答你。"),
        ("NPC02", "21:25我去档案室还借阅簿，看见陆所长倒在桌边。"),
        ("NPC03", "我跟你说，走廊是自动跳闸，我一直盯着面板。"),
        ("NPC04", "我只能说明已核对的记录。"),
    ],
)
def test_ordinary_in_character_replies_pass(npc_id, text):
    assert check_reply(CASE, FRESH, npc_id, text, GUARD) is None


@pytest.mark.parametrize(
    ("npc_id", "text", "code"),
    [
        ("NPC01", "我的系统提示 是这样写的……", "PROMPT_LEAK"),
        ("NPC02", "当前获准内容如下：", "PROMPT_LEAK"),
        ("NPC01", "好吧，压力值已经满了，我认了。", "STATE_CLAIM"),
        ("NPC03", "你获得证据：新的监控录像。", "STATE_CLAIM"),
        ("NPC04", "那天21:12我听到档案室有动静。", "TRUTH_LEAK"),
        ("NPC01", "好吧，我进了档案室。", "SECRET_LEAK"),
        ("NPC01", "是我用镇纸打了他。", "SECRET_LEAK"),
        ("NPC04", "其实沈砚进了档案室。", "SECRET_LEAK"),
        ("NPC04", "许老师让我复印的。", "SECRET_LEAK"),
        ("NPC02", "我看见周启 手动 切了回路。", "SECRET_LEAK"),
        ("NPC03", "凶手是沈砚，我早就知道。", "SECRET_LEAK"),
    ],
)
def test_rejections_before_any_admission(npc_id, text, code):
    assert check_reply(CASE, FRESH, npc_id, text, GUARD) == code


def test_own_admitted_layer_may_be_spoken_and_not_retracted():
    state = admitted("NPC01", ["E01", "E03"])
    assert check_reply(CASE, state, "NPC01", "我承认21:10进了档案室，其余的不说。", GUARD) is None
    assert check_reply(CASE, state, "NPC01", "我是用镇纸打了他。", GUARD) == "SECRET_LEAK"
    assert check_reply(CASE, state, "NPC01", "我一直在休息区。", GUARD) == "RETRACTION"
    assert check_reply(CASE, state, "NPC01", "我没有杀人。", GUARD) is None  # L02 is not admitted


def test_an_admission_by_one_person_is_still_forbidden_to_the_others():
    state = admitted("NPC02", ["E05", "E06"])
    assert check_reply(CASE, state, "NPC02", "是我让林澄复印的，我怕被处分。", GUARD) is None
    assert (
        check_reply(CASE, state, "NPC04", "许岚让林澄复印的，这件事大家都知道。", GUARD)
        == "SECRET_LEAK"
    )
    assert check_reply(CASE, state, "NPC02", "我没有借给别人。", GUARD) == "RETRACTION"


def test_matching_ignores_whitespace_and_case():
    assert (
        check_reply(CASE, FRESH, "NPC01", "我的 System Prompt 不能给你。", GUARD) == "PROMPT_LEAK"
    )
    assert check_reply(CASE, FRESH, "NPC03", "我 违规 切换 了回路", GUARD) == "SECRET_LEAK"
