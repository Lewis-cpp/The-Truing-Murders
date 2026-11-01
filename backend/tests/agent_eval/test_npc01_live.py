"""v0.4 live evaluation of Shen Yan. Runs only with RUN_LIVE_LLM_TESTS=1 and real credentials.

    RUN_LIVE_LLM_TESTS=1 uv run pytest tests/agent_eval -m live_llm -q

Writes a JSON report to backend/reports/agent_eval/. A guard rejection is a candidate violation
(the player saw the fixed reply); an accepted reply containing a forbidden phrase is a visible
violation and fails the run. Human review of accepted replies is still required.
"""

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.application.conversation import check_reply, load_guard
from backend.application.memory import ContextBudget, build_context
from backend.infrastructure.llm_client import LLMCall, LLMGateway

from backend.application.case import load_case
from backend.config import Settings
from backend.domain import rules
from backend.domain.evidence import current_statement
from backend.domain.state_machine import transition

pytestmark = [
    pytest.mark.live_llm,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_LLM_TESTS") != "1",
        reason="live model evaluation is opt-in: set RUN_LIVE_LLM_TESTS=1 and LLM_* credentials",
    ),
]

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "tests/data/agent/npc01_eval.json").read_text(encoding="utf-8"))
REPEATS = 3
CASE = load_case()


def setup(name):
    state = rules.new_game(CASE)
    for index in range(1, 13):
        state = rules.investigate(CASE, state, f"A{index:02d}")
    state = transition(state, "talk", "NPC01")
    shown = {"fresh": [], "first_layer_admitted": ["E01", "E03"]}.get(
        name, ["E01", "E03", "E02", "E08"]
    )
    for evidence in shown:
        state = rules.present(CASE, state, "NPC01", evidence)
    return state


def test_npc01_live_samples():
    settings = Settings()
    assert settings.llm_enabled, (
        "set LLM_ENABLED=true with a real LLM_BASE_URL, LLM_MODEL and LLM_API_KEY"
    )
    gateway, guard = LLMGateway(settings), load_guard()
    limit = DATA["budget"]["max_calls"]
    assert len(DATA["items"]) * REPEATS <= limit
    rows, calls, visible_violations = [], 0, []
    for item in DATA["items"]:
        state = setup(item["state"])
        fixed = current_statement(CASE, state, "NPC01")
        context = build_context(CASE, state, "NPC01", [], item["input"], fixed, ContextBudget())
        for run in range(REPEATS):
            calls += 1
            result = gateway.generate(
                LLMCall(
                    context.messages,
                    settings.llm_max_output_tokens,
                    time.monotonic() + settings.llm_timeout_seconds,
                )
            )
            rejected = (
                check_reply(CASE, state, "NPC01", result.text, guard) if result.text else None
            )
            visible = result.text if result.text and rejected is None else fixed
            hits = [p for p in item["must_not_contain"] if p in visible]
            if hits:
                visible_violations.append((item["id"], run, hits))
            rows.append(
                {
                    "item": item["id"],
                    "kind": item["kind"],
                    "run": run,
                    "error_code": result.error_code,
                    "guard": rejected,
                    "visible": visible,
                    "forbidden_hits": hits,
                    "usage": None if result.usage is None else vars(result.usage),
                    "latency_ms": result.latency_ms,
                    "human_review": None,
                }
            )
    report_dir = ROOT / "reports/agent_eval"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (report_dir / f"npc01-{stamp}.json").write_text(
        json.dumps(
            {
                "model": settings.llm_model,
                "prompt_version": "npc-1",
                "calls": calls,
                "candidate_violations": sum(r["guard"] is not None for r in rows),
                "visible_violations": len(visible_violations),
                "fallbacks": sum(
                    r["error_code"] is not None or r["guard"] is not None for r in rows
                ),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    assert calls <= limit
    assert visible_violations == []
