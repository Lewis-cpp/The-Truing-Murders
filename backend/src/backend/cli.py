"""Interactive, offline W1 adapter. All outcomes come from Game and domain rules."""

import argparse
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from backend.application.case import load_case
from backend.application.game import Game
from backend.domain.models import Accusation, GameError, Phase, StepEvidenceLink
from backend.domain.state_machine import emotion, guard

HELP = """命令（编号可在 look / bag / accuse 中查看）：
  look              查看场景、调查点与可审讯角色
  inspect A01       调查指定位置；可以自主选择顺序
  bag               查看已获得证据和已公开证词
  talk NPC01        进入沈砚的审讯
  ask 你的问题      获取当前固定说法；文字不产生数值收益
  present E01       向当前角色明确出示已持有证据
  back              结束审讯，或取消指控返回调查
  accuse            进入指控并查看所有候选项
  submit            逐项填写指控，确认后冻结本局
  review            结案后查看判定与真相
  finish            结束复盘；仍可重读结果
  status / help     查看阶段 / 帮助
  quit              退出；本周无存档，进度丢失"""


def _ids(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.replace("，", ",").split(",") if part.strip())


def _choices(game: Game) -> str:
    choices = game.view()["choices"]
    labels = {
        "suspects": "凶手候选",
        "weapons": "凶器候选",
        "motives": "动机候选",
        "process_steps": "过程候选",
    }
    return "\n".join(
        f"{label}：" + "；".join(f"{c['id']} {c['label']}" for c in choices[name])
        for name, label in labels.items()
    )


def _submit(game: Game, read: Callable[[str], str], write: Callable[[str], None]) -> None:
    guard(game.state, "submit")
    write(_choices(game))
    write("可不引用证据；未持有的证据不能引用。任一输入填 /cancel 可取消填写。")

    def answer(prompt: str) -> str:
        value = read(prompt).strip()
        if value == "/cancel":
            raise GameError("已取消填写，仍处于指控阶段；back 可返回调查。")
        return value

    culprit = answer("凶手编号：")
    weapon = answer("凶器编号：")
    motive = answer("动机编号：")
    steps = _ids(answer("过程编号，按发生顺序用逗号分隔："))
    cited = _ids(answer("引用的证据编号（可空）："))
    links = []
    for pair in _ids(answer("步骤证据关联，如 P_ENTER:E01，多项用逗号分隔（可空）：")):
        step_id, separator, evidence_id = pair.partition(":")
        if not separator or not step_id.strip() or not evidence_id.strip():
            raise GameError("关联格式应为 步骤编号:证据编号。")
        links.append(StepEvidenceLink(step_id=step_id.strip(), evidence_id=evidence_id.strip()))
    explanation = answer("补充解释（可空，不参与评分）：")
    accusation = Accusation(
        culprit=culprit,
        weapon=weapon,
        motive=motive,
        steps=steps,
        cited_evidence_ids=cited,
        evidence_links=tuple(links),
        explanation=explanation,
    )
    # Validate before the irreversible local submission, without running JUDGE.
    game.check_accusation(accusation)
    write(
        f"即将提交：{culprit} / {weapon} / {motive}；步骤 {', '.join(steps)}；"
        f"引用 {', '.join(cited) or '无'}。"
    )
    if answer("提交后无法继续调查。输入 确认 提交，其他输入取消：") != "确认":
        write("已取消提交。可以重新 submit，或 back 返回调查。")
        return
    game.submit(accusation)
    write(game.review())


def run(
    game: Game, read: Callable[[str], str] = input, write: Callable[[str], None] = print
) -> None:
    view = game.view()
    write(f"《{view['title']}》· W1 可玩切片（内容待人工审阅）")
    write("完全固定规则与台词，无 Agent、无模型调用、无需数据库。进度只在内存中，退出即丢失。")
    write(view["introduction"])
    write(HELP)
    while True:
        try:
            command, _, argument = read("\n调查> ").strip().partition(" ")
            argument = argument.strip()
            if command in {"quit", "exit"}:
                write("已退出；本局内存进度不保留。")
                return
            if command == "help":
                write(HELP)
            elif command == "look":
                view = game.view()
                write(f"{view['scene']['id']} {view['scene']['name']}：{view['scene']['text']}")
                for action in view["actions"]:
                    done = "已调查" if action["id"] in game.state.completed_actions else "待调查"
                    write(f"{action['id']} · {action['label']}（{done}）")
                write(f"可审讯：{view['npc']['id']} {view['npc']['name']} · {view['npc']['role']}")
            elif command == "inspect":
                write(game.inspect(argument))
            elif command == "bag":
                view = game.view()
                if not view["evidence"]:
                    write("尚未取得证据。")
                for evidence in view["evidence"]:
                    write(
                        f"{evidence['id']} · {evidence['title']} [{evidence['credibility']}]\n"
                        f"{evidence['content']}\n来源：{evidence['source']}"
                    )
                for knowledge in view["knowledge"]:
                    write(
                        f"证词 [{knowledge['credibility']}] {knowledge['source']}："
                        f"{knowledge['content']}"
                    )
            elif command == "talk":
                write(game.talk(argument))
            elif command == "ask":
                write(game.ask(argument))
            elif command == "present":
                write(game.present(game.state.active_npc_id or "", argument))
            elif command == "back":
                game.back()
                write("已返回调查。")
            elif command == "accuse":
                game.accuse()
                write(_choices(game))
                write("输入 submit 填写并确认，或 back 返回调查。无需招供也可结案。")
            elif command == "submit":
                _submit(game, read, write)
            elif command == "review":
                write(game.review())
            elif command == "finish":
                game.finish()
                write("本局已结束；review 可重读判定。")
            elif command == "status":
                write(f"阶段：{game.state.phase.value}；证据：{len(game.state.evidence_ids)}/3。")
                if game.state.phase == Phase.INTERROGATION:
                    write(
                        f"当前情绪：{emotion(game.state.npc)}；说法阶段：{game.state.npc.lie_stage.value}。"
                    )
            elif command:
                write("无法识别该命令。输入 help 查看操作。")
        except (EOFError, KeyboardInterrupt):
            write("\n已退出；本局内存进度不保留。")
            return
        except (GameError, ValidationError) as error:
            message = (
                "输入字段不合法，请检查编号、长度与格式。"
                if isinstance(error, ValidationError)
                else str(error)
            )
            write(f"操作未完成：{message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="《停电之夜》W1 离线命令行切片")
    parser.add_argument("--case", type=Path, help="载入另一个符合 W1 契约的切片文件")
    args = parser.parse_args()
    try:
        game = Game(load_case(args.case))
    except ValueError as error:
        parser.exit(2, f"案件无法载入：{error}\n")
    run(game)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
