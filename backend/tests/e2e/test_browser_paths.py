"""v0.6 acceptance: real browser paths over the built frontend, fixed replies only."""

import pytest

pytestmark = pytest.mark.e2e

ACTIONS = [f"A{i:02d}" for i in range(1, 13)]
CORRECT_LINKS = [
    ("P_ENTER", "E01"),
    ("P_ENTER", "E11"),
    ("P_ATTACK", "E02"),
    ("P_STAGE", "E03"),
    ("P_STAGE", "E08"),
]


def start(page):
    page.get_by_test_id("start-game").click()
    page.get_by_test_id("action-A01").wait_for()


def investigate(page, actions=ACTIONS):
    for action in actions:
        button = page.get_by_test_id(f"action-{action}")
        button.click()
        page.locator(f'[data-testid="action-{action}"][data-completed="true"]').wait_for()
        page.get_by_test_id(f"evidence-E{action[1:]}").wait_for()


def present(page, evidence):
    page.get_by_test_id(f"present-{evidence}").click()
    page.get_by_test_id("conversation-log").filter(has_text=f"出示证据：{evidence}").wait_for()


def accuse(page, culprit, weapon, motive, steps, links):
    page.get_by_test_id("open-accusation").click()
    form = page.get_by_test_id("accusation-form")
    form.wait_for()
    for option in (culprit, weapon, motive):
        page.get_by_test_id(f"option-{option}").click()
    for step in steps:
        page.get_by_test_id(f"step-{step}").click()
    for evidence in sorted({e for _, e in links}):
        page.get_by_test_id(f"cite-check-{evidence}").click()
    for step, evidence in links:
        page.get_by_test_id(f"link-{step}-{evidence}").click()
    page.get_by_test_id("confirm-accusation").click()
    page.get_by_test_id("submit-accusation").click()
    page.get_by_test_id("review-panel").wait_for()


def test_no_confession_path_scores_full_marks(page):
    start(page)
    investigate(page)
    assert "深入调查" in page.get_by_test_id("phase").inner_text()
    accuse(page, "NPC01", "W01", "M01", ["P_ENTER", "P_ATTACK", "P_STAGE"], CORRECT_LINKS)
    assert page.get_by_test_id("verdict-category").inner_text().strip() == "正确"
    assert "100.00" in page.get_by_test_id("verdict-score").inner_text()
    assert "21:12" in page.get_by_test_id("review-panel").inner_text()
    page.get_by_test_id("finish-review").click()
    page.get_by_test_id("phase").filter(has_text="已结束").wait_for()


@pytest.mark.parametrize(
    ("culprit", "weapon", "motive", "steps", "category", "score"),
    [
        ("NPC01", "W02", "M03", ["P_CUT_POWER"], "部分正确", "30.00"),
        ("NPC03", "W01", "M01", ["P_ENTER", "P_ATTACK", "P_STAGE"], "错误", "70.00"),
    ],
)
def test_partial_and_wrong_verdicts(page, culprit, weapon, motive, steps, category, score):
    start(page)
    investigate(page)
    links = CORRECT_LINKS if category == "错误" else []
    accuse(page, culprit, weapon, motive, steps, links)
    assert page.get_by_test_id("verdict-category").inner_text().strip() == category
    assert score in page.get_by_test_id("verdict-score").inner_text()


def test_two_layer_confession_with_fixed_replies_and_reload(page):
    start(page)
    investigate(page)
    page.get_by_test_id("talk-NPC01").click()
    panel = page.get_by_test_id("interrogation-panel")
    panel.wait_for()
    for evidence in ("E01", "E03"):
        present(page, evidence)
    panel.filter(has_text="我只承认去过").wait_for()
    page.reload()
    page.get_by_test_id("interrogation-panel").filter(has_text="我只承认去过").wait_for()
    for evidence in ("E02", "E08"):
        present(page, evidence)
    page.get_by_test_id("interrogation-panel").filter(has_text="用镇纸打了陆衡").wait_for()
    assert "出示证据：E08" in page.get_by_test_id("conversation-log").inner_text()
    page.get_by_test_id("leave-interrogation").click()
    page.get_by_test_id("timeline-T07").wait_for()
    assert "时间未知" in page.get_by_test_id("timeline-T07").inner_text()
