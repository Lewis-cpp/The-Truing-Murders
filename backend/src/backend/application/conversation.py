"""The backstop check on model replies, driven by the case guard lists (spec section 5).

These checks only catch known wording; the minimal authorized context of
`application.memory` remains the primary defense. A hit means the whole
candidate is discarded: never shown, never stored, never re-sent as context.
"""

from pathlib import Path

from pydantic import BaseModel

from backend.domain.models import Case, GameState, LieStage


class GuardSecret(BaseModel):
    lie_id: str
    owner_phrases: tuple[str, ...] = ()
    other_phrases: tuple[str, ...] = ()
    denials: tuple[str, ...] = ()


class Guard(BaseModel):
    case_id: str
    version: str
    prompt_leak_phrases: tuple[str, ...] = ()
    state_claim_phrases: tuple[str, ...] = ()
    truth_phrases: tuple[str, ...] = ()
    secrets: tuple[GuardSecret, ...] = ()


def default_guard_path() -> Path:
    # Editable checkout and packaged wheel both carry the same versioned resource.
    package = Path(__file__).resolve().parents[1] / "case_data/case_001/v1/guard.json"
    if package.is_file():
        return package
    return Path(__file__).resolve().parents[3] / "assets/cases/case_001/v1/guard.json"


def load_guard(path: Path | None = None) -> Guard:
    return Guard.model_validate_json((path or default_guard_path()).read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    """Matching removes all whitespace and ignores case (spec section 5)."""
    return "".join(text.split()).casefold()


def check_reply(case: Case, state: GameState, npc_id: str, text: str, guard: Guard) -> str | None:
    """None means the reply may pass; otherwise the internal reason code."""
    needle = _norm(text)
    if any(_norm(phrase) in needle for phrase in guard.prompt_leak_phrases):
        return "PROMPT_LEAK"
    if any(_norm(phrase) in needle for phrase in guard.state_claim_phrases):
        return "STATE_CLAIM"
    if any(_norm(phrase) in needle for phrase in guard.truth_phrases):
        return "TRUTH_LEAK"
    npc = state.npcs[npc_id]
    for secret in guard.secrets:
        lie = next((item for item in case.lies if item.id == secret.lie_id), None)
        if lie is None or lie.npc_id == npc_id:
            continue
        if any(_norm(phrase) in needle for phrase in secret.other_phrases):
            return "SECRET_LEAK"
    for secret in guard.secrets:
        lie = next((item for item in case.lies if item.id == secret.lie_id), None)
        if lie is None or lie.npc_id != npc_id:
            continue
        admitted = npc.lies.get(lie.id) == LieStage.ADMITTED
        if not admitted and any(_norm(phrase) in needle for phrase in secret.owner_phrases):
            return "SECRET_LEAK"
        if admitted and any(_norm(phrase) in needle for phrase in secret.denials):
            return "RETRACTION"
    return None
