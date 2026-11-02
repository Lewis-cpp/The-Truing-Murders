"""v1.0 acceptance: viewports, zoom, keyboard, contrast and reduced motion in a real browser."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

AXE = Path(__file__).resolve().parents[3] / "frontend/node_modules/axe-core/axe.min.js"
VIEWPORTS = [(1366, 768), (1920, 1080), (390, 844)]


def no_horizontal_scroll(page) -> bool:
    return page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


def start_and_open_scene(page):
    page.get_by_test_id("start-game").click()
    page.get_by_test_id("action-A01").click()
    page.get_by_test_id("evidence-E01").wait_for()


@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
def test_layouts_fit_without_horizontal_scrolling(page, width, height):
    page.set_viewport_size({"width": width, "height": height})
    start_and_open_scene(page)
    assert no_horizontal_scroll(page)
    page.get_by_test_id("action-A02").wait_for()


def test_two_hundred_percent_zoom_keeps_everything_usable(page):
    page.set_viewport_size({"width": 683, "height": 384})  # 1366x768 at 200%
    start_and_open_scene(page)
    assert no_horizontal_scroll(page)
    page.get_by_test_id("action-A02").click()
    page.get_by_test_id("evidence-E02").wait_for()


def test_core_path_with_the_keyboard_only(page):
    def tab_to(test_id, limit=200):
        for _ in range(limit):
            page.keyboard.press("Tab")
            if page.evaluate(
                "(id) => document.activeElement?.closest(`[data-testid='${id}']`) !== null", test_id
            ):
                return
        raise AssertionError(f"could not reach {test_id} with Tab")

    tab_to("start-game")
    page.keyboard.press("Enter")
    page.get_by_test_id("action-A01").wait_for()
    for action, evidence in (("A01", "E01"), ("A02", "E02")):
        tab_to(f"action-{action}")
        page.keyboard.press("Enter")
        page.get_by_test_id(f"evidence-{evidence}").wait_for()
    tab_to("talk-NPC01")
    page.keyboard.press("Enter")
    page.get_by_test_id("interrogation-panel").wait_for()
    tab_to("present-E01")
    page.keyboard.press("Enter")
    page.get_by_test_id("conversation-log").filter(has_text="出示证据：E01").wait_for()
    tab_to("leave-interrogation")
    page.keyboard.press("Enter")
    tab_to("open-accusation")
    page.keyboard.press("Enter")
    page.get_by_test_id("accusation-form").wait_for()
    status = page.locator('[role="status"]').first
    assert status.get_attribute("aria-live") in ("polite", None)


def test_no_serious_accessibility_violations(page):
    assert AXE.is_file(), "install axe-core in frontend/ (npm ci)"
    start_and_open_scene(page)
    page.add_script_tag(path=str(AXE))
    result = page.evaluate("async () => await axe.run(document, {resultTypes: ['violations']})")
    serious = [
        (v["id"], len(v["nodes"]))
        for v in result["violations"]
        if v["impact"] in ("serious", "critical")
    ]
    assert serious == []


def test_reduced_motion_turns_motion_off(servers, db):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(reduced_motion="reduce")
        page = context.new_page()
        page.goto(servers)
        duration = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--tm-motion-duration').trim()"
        )
        assert duration in ("0ms", "0s")
        browser.close()
