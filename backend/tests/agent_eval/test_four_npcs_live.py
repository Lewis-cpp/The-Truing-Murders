"""v0.5 live evaluation of all four characters. Opt-in, with a hard call budget.

RUN_LIVE_LLM_TESTS=1 uv run pytest tests/agent_eval -m live_llm -q
"""

import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.application.case import load_case
from backend.application.conversation import check_reply, load_guard
from backend.application.memory import ContextBudget, build_context
from backend.config import Settings
from backend.domain import rules
from backend.domain.evidence import current_statement
from backend.domain.state_machine import transition
from backend.infrastructure.llm_client import LLMCall, LLMGateway

pytestmark = [
    pytest.mark.live_llm,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_LLM_TESTS") != "1",
        reason="live model evaluation is opt-in: set RUN_LIVE_LLM_TESTS=1 and LLM_* credentials",
    ),
]

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "tests/data/agent/four_npcs_eval.json").read_text(encoding="utf-8"))
REPEATS = 3
CASE = load_case()
SHOWN = {
    ("NPC01", "first_layer_admitted"): ["E01", "E03"],
    ("NPC01", "both_layers_admitted"): ["E01", "E03", "E02", "E08"],
    ("NPC02", "admitted"): ["E05", "E06"],
    ("NPC03", "admitted"): ["E10", "E11"],
}


def setup(npc_id, name):
    state = rules.new_game(CASE)
    for index in range(1, 13):
        state = rules.investigate(CASE, state, f"A{index:02d}")
    state = transition(state, "talk", npc_id)
    for evidence in SHOWN.get((npc_id, name), []):
        state = rules.present(CASE, state, npc_id, evidence)
    return state


def test_four_npcs_live_samples():
    settings = Settings()
    assert settings.llm_enabled, "set LLM_ENABLED=true with real LLM_* settings"
    gateway, guard = LLMGateway(settings), load_guard()
    limit = DATA["budget"]["max_calls"]
    rows, calls = [], 0
    for item in DATA["items"]:
        state = setup(item["npc"], item["state"])
        fixed = current_statement(CASE, state, item["npc"])
        context = build_context(CASE, state, item["npc"], [], item["input"], fixed, ContextBudget())
        for run in range(REPEATS):
            if calls >= limit:
                break
            calls += 1
            deadline = time.monotonic() + settings.llm_timeout_seconds
            result = gateway.generate(
                LLMCall(context.messages, settings.llm_max_output_tokens, deadline)
            )
            rejected = (
                check_reply(CASE, state, item["npc"], result.text, guard) if result.text else None
            )
            visible = result.text if result.text and rejected is None else fixed
            rows.append(
                {
                    "item": item["id"],
                    "npc": item["npc"],
                    "kind": item["kind"],
                    "run": run,
                    "error_code": result.error_code,
                    "guard": rejected,
                    "visible": visible,
                    "forbidden_hits": [p for p in item["must_not_contain"] if p in visible],
                    "usage": None if result.usage is None else vars(result.usage),
                    "latency_ms": result.latency_ms,
                    "human_review": None,
                }
            )
    attacks = [r for r in rows if r["kind"] == "attack"]
    normals = [r for r in rows if r["kind"] == "normal"]
    summary = {
        "model": settings.llm_model,
        "prompt_version": "npc-1",
        "calls": calls,
        "candidate_violations": Counter(r["guard"] for r in rows if r["guard"]),
        "visible_violations": sum(bool(r["forbidden_hits"]) for r in rows),
        "attack_success": sum(bool(r["forbidden_hits"]) for r in attacks),
        "normal_false_rejections": sum(r["guard"] is not None for r in normals),
        "fallbacks": Counter(
            r["error_code"] or r["guard"] for r in rows if r["error_code"] or r["guard"]
        ),
        "unknown_usage": sum(r["usage"] is None for r in rows),
        "rows": rows,
    }
    out = ROOT / "reports/agent_eval"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (out / f"four-npcs-{stamp}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    assert calls <= limit
    assert summary["visible_violations"] == 0
