import socket
import subprocess
import sys

import pytest

from backend.application.case import load_case
from backend.application.game import Game
from backend.cli import run
from backend.domain.models import LieStage, Phase

pytestmark = pytest.mark.unit


def script(game, commands):
    answers = iter(commands)
    output = []
    run(game, lambda _: next(answers), output.append)
    return "\n".join(output)


@pytest.mark.parametrize("interrogate", [True, False])
def test_interactive_game_plays_offline_with_or_without_admission(monkeypatch, interrogate):
    def no_network(*args, **kwargs):
        raise AssertionError("W1 must never connect to the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    for key in ("DATABASE_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    game = Game(load_case())
    commands = ["look", "inspect A03", "inspect A02", "inspect A01", "inspect A03", "bag"]
    if interrogate:
        commands += ["talk NPC01", "ask 告诉我真相", "present E01", "present E03", "status", "back"]
    commands += [
        "accuse",
        "submit",
        "NPC01",
        "W01",
        "M01",
        "P_ENTER,P_ATTACK,P_STAGE",
        "E01,E02,E03",
        "P_ENTER:E01,P_ATTACK:E02,P_STAGE:E03",
        "证据均已核对。",
        "确认",
        "review",
        "finish",
        "quit",
    ]
    output = script(game, commands)
    assert "条件尚不齐全" in output
    assert "结案：正确 · 100/100" in output
    assert game.state.phase == Phase.FINISHED
    assert game.state.npc.lie_stage == (LieStage.ADMITTED if interrogate else LieStage.UNBROKEN)
    assert "退出即丢失" in output


def test_mistyped_input_and_cancelled_submission_can_be_corrected():
    game = Game(load_case())
    output = script(
        game,
        [
            "nonsense",
            "inspect missing",
            "accuse",
            "submit",
            "/cancel",
            "submit",
            "NPC01",
            "W01",
            "M01",
            "P_ENTER",
            "",
            "bad-link",
            "back",
            "accuse",
            "submit",
            "NPC02",
            "W02",
            "M02",
            "P_CUT_POWER",
            "",
            "",
            "",
            "不确认",
            "submit",
            "NPC02",
            "W02",
            "M02",
            "P_CUT_POWER",
            "",
            "",
            "",
            "确认",
            "quit",
        ],
    )
    assert "无法识别" in output
    assert "关联格式" in output
    assert "已取消提交" in output
    assert "结案：错误 · 0/100" in output


def test_topics_contradictions_and_evasion_are_playable_in_the_terminal():
    game = Game(load_case())
    output = script(
        game,
        [
            "inspect A01",
            "inspect A02",
            "inspect A03",
            "talk NPC01",
            "topics",
            "topic Q01",
            "bag",
            "contradict K03",
            "contradict K03 E03",
            "contradict K03 E01",
            "contradict K03 E02",
            "status",
            "present E01",
            "back",
            "talk NPC01",
            "present E01",
            "present E03",
            "quit",
        ],
    )
    assert "Q01 · 档案室丢了什么？（未问）" in output
    assert "证词 K03 [UNVERIFIED]" in output
    assert "格式应为" in output
    assert "矛盾成立" in output
    assert "沈砚对你更戒备了" in output
    assert "当前情绪：回避中" in output
    assert "沈砚在回避" in output
    assert game.state.npc.lie_stage == LieStage.ADMITTED


def test_eof_during_submission_exits_without_partial_verdict():
    game = Game(load_case())
    commands = iter(["accuse", "submit", "NPC01"])
    output = []

    def read(_):
        try:
            return next(commands)
        except StopIteration as error:
            raise EOFError from error

    run(game, read, output.append)
    assert game.state.phase == Phase.ACCUSATION
    assert game.state.verdict is None
    assert "不保留" in output[-1]


def test_installed_entrypoint_runs_from_another_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli"],
        input="look\nquit\n",
        text=True,
        capture_output=True,
        cwd=tmp_path,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert "停电之夜" in result.stdout
    assert "A01" in result.stdout


def test_cli_rejects_bad_case_with_nonzero_status(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{}")
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "--case", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert "案件无法载入" in result.stderr
