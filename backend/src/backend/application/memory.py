"""The authorized context of one NPC: read-only assembly, no writes, no model calls.

Only what this character is allowed to know may reach the model (v0.4 spec
section 4): their own current statement, public knowledge, knowledge they have
already disclosed as the speaker, evidence shown to them, and the fixed result
of this round. No internal IDs, no other person's private text, no truth.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from backend.domain import rules
from backend.domain.evidence import current_statement
from backend.domain.models import Case, GameState
from backend.domain.state_machine import emotion, evading

PROMPT_VERSION = "npc-1"

# emotion() -> the wording the template uses for the current mood.
EMOTION_STYLE = {
    "CALM": "平静",
    "DEFENSIVE": "戒备",
    "NERVOUS": "紧张",
    "PRESSURED": "动摇",
    "EVADING": "回避",
}


@dataclass(frozen=True)
class HistoryRound:
    conversation_seq: int
    npc_id: str
    player_text: str
    npc_text: str
    status: str  # COMPLETED / FALLBACK / STALE / PREPARING / GENERATING
    memory_epoch: int = 0  # used from v0.5 on


@dataclass(frozen=True)
class ContextBudget:
    max_input_tokens: int = 4000
    max_output_tokens: int = 400
    max_history_rounds: int = 6


@dataclass(frozen=True)
class AuthorizedContext:
    messages: tuple[dict, ...]
    prompt_version: str
    context_digest: str  # sha256 of the canonical messages JSON
    estimated_input_tokens: int
    included_refs: tuple[str, ...]  # knowledge and evidence ids actually sent; server-side only
    history_seqs: tuple[int, ...]
    fixed_reply: str


class ContextOverBudget(Exception):
    """Not even the current input fits the budget; the round degrades, no call is made."""


def default_template_path() -> Path:
    # Editable checkout and packaged wheel both carry the same versioned resource.
    package = Path(__file__).resolve().parents[1] / "prompt_data/npc_system.v1.txt"
    if package.is_file():
        return package
    return Path(__file__).resolve().parents[3] / "assets/prompts/npc_system.v1.txt"


def estimate_tokens(messages) -> int:
    """All message content characters plus four per message (spec 4.3)."""
    return sum(len(message["content"]) for message in messages) + 4 * len(messages)


def _canonical(messages) -> str:
    return json.dumps(list(messages), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_context(
    case: Case,
    state: GameState,
    npc_id: str,
    history: list[HistoryRound],
    player_text: str,
    fixed_reply: str,
    budget: ContextBudget | None = None,
) -> AuthorizedContext:
    budget = budget or ContextBudget()
    character = next(c for c in case.characters if c.id == npc_id)
    npc = state.npcs[npc_id]
    lines: list[str] = []
    refs: list[str] = []

    lines.append(f"- 当前说法：{current_statement(case, state, npc_id)}")
    for knowledge in case.knowledge:
        if knowledge.disclosure == "PUBLIC":
            lines.append(f"- {knowledge.content}")
            refs.append(knowledge.id)
    disclosed = rules.citable_testimony(case, state, npc_id)
    for knowledge in case.knowledge:
        if knowledge.id in disclosed:
            lines.append(f"- {knowledge.content}")
            refs.append(knowledge.id)
    held = state.evidence_ids
    presented = npc.presented
    for evidence in case.evidence:
        if evidence.id in presented and evidence.id in held:
            lines.append(f"- 证据《{evidence.title}》：{evidence.content}")
            refs.append(evidence.id)
    lines.append(f"- 本轮结果：{fixed_reply}")

    system_text = _system_template().format(
        name=character.name,
        public_identity=character.public_identity,
        personality=character.personality or "",
        speech_style=character.speech_style or "",
        emotion_style=EMOTION_STYLE.get(_mood(case, npc), "平静"),
        authorized="\n".join(lines),
    )
    messages: list[dict] = [{"role": "system", "content": system_text}]
    rounds = sorted(
        (
            round_
            for round_ in history
            if round_.npc_id == npc_id and round_.status in {"COMPLETED", "FALLBACK"}
        ),
        key=lambda round_: round_.conversation_seq,
    )[-budget.max_history_rounds :]
    for round_ in rounds:
        messages.append({"role": "user", "content": round_.player_text})
        messages.append({"role": "assistant", "content": round_.npc_text})
    messages.append({"role": "user", "content": player_text})

    while len(rounds) and estimate_tokens(messages) > budget.max_input_tokens:
        rounds.pop(0)
        del messages[1:3]
    if estimate_tokens(messages) > budget.max_input_tokens:
        raise ContextOverBudget("授权内容加本轮输入已超出模型输入预算，本轮使用固定回复。")
    return AuthorizedContext(
        messages=tuple(messages),
        prompt_version=PROMPT_VERSION,
        context_digest=hashlib.sha256(_canonical(messages).encode("utf-8")).hexdigest(),
        estimated_input_tokens=estimate_tokens(messages),
        included_refs=tuple(dict.fromkeys(refs)),
        history_seqs=tuple(round_.conversation_seq for round_ in rounds),
        fixed_reply=fixed_reply,
    )


def _mood(case: Case, npc) -> str:
    return "EVADING" if evading(case, npc) else emotion(npc)


_TEMPLATE_CACHE: dict[Path, str] = {}


def _system_template() -> str:
    path = default_template_path()
    if path not in _TEMPLATE_CACHE:
        _TEMPLATE_CACHE[path] = path.read_text(encoding="utf-8")
    return _TEMPLATE_CACHE[path]
