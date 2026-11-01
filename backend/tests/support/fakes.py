"""Test doubles for model generation. No network, no threads.

FakeGateway answers from a script; ManualDispatcher keeps submitted tasks until the test runs them.
"""

import json
from collections.abc import Callable

from backend.infrastructure.llm_client import GatewayResult, LLMCall, Usage


def ok(text: str, input_tokens: int = 900, output_tokens: int = 40) -> GatewayResult:
    return GatewayResult(
        text=text,
        error_code=None,
        sent=True,
        usage=Usage(input_tokens, output_tokens),
        retry_after=None,
        provider_request_id="req-fake",
        model="fake-model",
        latency_ms=5,
    )


def failed(error_code: str, sent: bool = True, usage: Usage | None = None, retry_after=None):
    return GatewayResult(
        text=None,
        error_code=error_code,
        sent=sent,
        usage=usage,
        retry_after=retry_after,
        provider_request_id=None,
        model="fake-model",
        latency_ms=5,
    )


class FakeGateway:
    """Returns scripted results in order; the last one repeats. Records every call."""

    def __init__(self, *results: GatewayResult | Callable[[LLMCall], GatewayResult]):
        self.results = list(results) or [ok("我需要核对一下，再回答你。")]
        self.calls: list[LLMCall] = []

    def generate(self, call: LLMCall) -> GatewayResult:
        self.calls.append(call)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return result(call) if callable(result) else result

    def last_text(self) -> str:
        """Everything the model saw in the last call, for leak checks."""
        return json.dumps(list(self.calls[-1].messages), ensure_ascii=False)


class ManualDispatcher:
    def __init__(self):
        self.tasks: list[Callable[[], None]] = []

    def submit(self, task: Callable[[], None]) -> None:
        self.tasks.append(task)

    def run_all(self) -> int:
        count = 0
        while self.tasks:
            task = self.tasks.pop(0)
            try:
                task()
            except Crash:
                pass  # the process "died" mid-call; recovery is the code under test
            count += 1
        return count


class Crash(BaseException):
    """Raised by a scripted gateway to imitate the process dying after dispatch."""


LLM_ENV = {
    "LLM_ENABLED": "true",
    "LLM_ENABLED_NPCS": '["NPC01"]',
    "LLM_BASE_URL": "http://llm.invalid/v1",
    "LLM_MODEL": "fake-model",
    "LLM_API_KEY": "test-secret-key",
    "LLM_TIMEOUT_SECONDS": "30",
}


def install(client, gateway: FakeGateway, dispatcher: ManualDispatcher | None = None):
    dispatcher = dispatcher or ManualDispatcher()
    client.app.state.llm_gateway = gateway
    client.app.state.generation_dispatcher = dispatcher
    return dispatcher
