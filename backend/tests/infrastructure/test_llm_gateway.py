"""v0.4 acceptance: the only LLM Gateway, exercised through a mock HTTP transport."""

import json
import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx2
import pytest

from backend.config import Settings
from backend.infrastructure.llm_client import LLMCall, LLMGateway

pytestmark = [pytest.mark.unit, pytest.mark.agent]

MESSAGES = (
    {"role": "system", "content": "你扮演沈砚。"},
    {"role": "user", "content": "停电时你在哪里？"},
)


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x_test")
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    monkeypatch.setenv("LLM_API_KEY", "test-secret-key")
    return Settings()


def completion(content, finish="stop", usage=None, **message):
    body = {
        "id": "chatcmpl-1",
        "model": "fake-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content, **message},
            }
        ],
        "usage": usage if usage is not None else {"prompt_tokens": 120, "completion_tokens": 30},
    }
    return body


class Recorder:
    def __init__(self, respond):
        self.requests: list[httpx2.Request] = []
        self.respond = respond

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.respond(request)


def gateway(settings, respond):
    recorder = Recorder(respond)
    return LLMGateway(settings, transport=httpx2.MockTransport(recorder)), recorder


def call(seconds=5.0):
    return LLMCall(messages=MESSAGES, max_output_tokens=400, deadline=time.monotonic() + seconds)


def test_success_parses_text_usage_and_sends_the_documented_request(settings):
    llm, recorder = gateway(
        settings, lambda r: httpx2.Response(200, json=completion('{"text": "我一直在休息区。"}'))
    )
    result = llm.generate(call())
    assert (result.text, result.error_code, result.sent) == ("我一直在休息区。", None, True)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)
    assert result.latency_ms >= 0
    [request] = recorder.requests
    assert request.method == "POST"
    assert str(request.url) == "http://llm.invalid/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-secret-key"
    body = json.loads(request.content)
    assert body["model"] == "fake-model"
    assert body["messages"] == list(MESSAGES)
    assert body["max_tokens"] == 400
    schema = body["response_format"]["json_schema"]
    assert body["response_format"]["type"] == "json_schema"
    assert schema["strict"] is True
    assert schema["schema"]["required"] == ["text"]
    assert schema["schema"]["additionalProperties"] is False
    assert "test-secret-key" not in repr(result)


@pytest.mark.parametrize(
    ("status", "headers", "body", "code"),
    [
        (500, {}, {"error": {"message": "boom"}}, "UNAVAILABLE"),
        (503, {}, {}, "UNAVAILABLE"),
        (429, {"Retry-After": "7"}, {"error": {"message": "slow down"}}, "RATE_LIMITED"),
        (401, {}, {"error": {"message": "bad key"}}, "AUTH_FAILED"),
        (403, {}, {}, "AUTH_FAILED"),
        (400, {}, {"error": {"code": "context_length_exceeded"}}, "CONTEXT_TOO_LONG"),
        (400, {}, {"error": {"code": "invalid_request"}}, "PROTOCOL_INVALID"),
        (404, {}, {}, "PROTOCOL_INVALID"),
    ],
)
def test_http_failures_are_classified_and_never_retried(settings, status, headers, body, code):
    llm, recorder = gateway(settings, lambda r: httpx2.Response(status, headers=headers, json=body))
    result = llm.generate(call())
    assert (result.text, result.error_code, result.sent) == (None, code, True)
    assert len(recorder.requests) == 1
    assert result.usage is None


def test_retry_after_seconds_date_and_garbage(settings):
    when = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    for header, low, high in (("12", 12, 12), (when, 25, 31), ("soon", None, None)):
        llm, _ = gateway(
            settings, lambda r, h=header: httpx2.Response(429, headers={"Retry-After": h})
        )
        result = llm.generate(call())
        if low is None:
            assert result.retry_after is None
        else:
            assert low <= result.retry_after <= high


@pytest.mark.parametrize(
    ("error", "code", "sent"),
    [
        (httpx2.ConnectError("refused"), "UNAVAILABLE", False),
        (httpx2.ConnectTimeout("slow connect"), "UNAVAILABLE", False),
        (httpx2.ReadTimeout("slow read"), "TIMEOUT", True),
    ],
)
def test_transport_errors(settings, error, code, sent):
    def respond(request):
        raise error

    llm, recorder = gateway(settings, respond)
    result = llm.generate(call())
    assert (result.error_code, result.sent, result.usage) == (code, sent, None)
    assert len(recorder.requests) == 1


class Drip(httpx2.SyncByteStream):
    """A body that keeps arriving in small pieces, each well inside any per-read timeout."""

    def __iter__(self):
        yield b'{"choices": ['
        for _ in range(100):
            time.sleep(0.02)
            yield b" "
        yield b"]}"


def test_a_dripping_body_cannot_outlive_the_deadline(settings):
    llm, _ = gateway(settings, lambda r: httpx2.Response(200, stream=Drip()))
    started = time.monotonic()
    result = llm.generate(call(seconds=0.3))
    assert result.error_code == "TIMEOUT"
    assert time.monotonic() - started < 1.5


def test_an_oversized_body_is_rejected(settings):
    huge = completion('{"text": "好"}')
    huge["padding"] = "x" * (70 * 1024)
    llm, _ = gateway(settings, lambda r: httpx2.Response(200, json=huge))
    assert llm.generate(call()).error_code == "PROTOCOL_INVALID"


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ('```json\n{"text": "好"}\n```', "PROTOCOL_INVALID"),
        ('{"text": "好"} 另外', "PROTOCOL_INVALID"),
        ('{"text": "好", "text": "坏"}', "PROTOCOL_INVALID"),
        ('{"text": "好", "actions": ["grant_evidence"]}', "PROTOCOL_INVALID"),
        ('{"text": 42}', "PROTOCOL_INVALID"),
        ('{"text": null}', "PROTOCOL_INVALID"),
        ('{"text": "   "}', "PROTOCOL_INVALID"),
        ('{"text": NaN}', "PROTOCOL_INVALID"),
        ('["好"]', "PROTOCOL_INVALID"),
        ("我一直在休息区。", "PROTOCOL_INVALID"),
        (json.dumps({"text": "字" * 1201}, ensure_ascii=False), "PROTOCOL_INVALID"),
    ],
)
def test_strict_reply_protocol(settings, content, code):
    llm, _ = gateway(settings, lambda r: httpx2.Response(200, json=completion(content)))
    result = llm.generate(call())
    assert (result.text, result.error_code) == (None, code)


def test_the_longest_allowed_reply_passes(settings):
    text = "字" * 1200
    content = json.dumps({"text": text}, ensure_ascii=False)
    llm, _ = gateway(settings, lambda r: httpx2.Response(200, json=completion(content)))
    assert llm.generate(call()).text == text


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (completion('{"text": "好"}', finish="length"), "TRUNCATED"),
        (completion('{"text": "好"}', finish="content_filter"), "REFUSED"),
        (completion(None, refusal="I can't help with that."), "REFUSED"),
        (
            completion(
                None,
                tool_calls=[
                    {
                        "id": "t",
                        "type": "function",
                        "function": {"name": "grant", "arguments": "{}"},
                    }
                ],
            ),
            "PROTOCOL_INVALID",
        ),
        ({"choices": [], "usage": {}}, "PROTOCOL_INVALID"),
        (
            {"choices": completion('{"text": "好"}')["choices"] * 2, "usage": {}},
            "PROTOCOL_INVALID",
        ),
    ],
)
def test_provider_markers(settings, body, code):
    llm, _ = gateway(settings, lambda r: httpx2.Response(200, json=body))
    result = llm.generate(call())
    assert (result.text, result.error_code) == (None, code)


@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"prompt_tokens": -1, "completion_tokens": 3},
        {"prompt_tokens": "12", "completion_tokens": 3},
        {"prompt_tokens": True, "completion_tokens": 3},
        {"prompt_tokens": 1.5, "completion_tokens": 3},
    ],
)
def test_untrustworthy_usage_is_unknown_not_zero(settings, usage):
    llm, _ = gateway(
        settings, lambda r: httpx2.Response(200, json=completion('{"text": "好"}', usage=usage))
    )
    result = llm.generate(call())
    assert result.text == "好"
    assert result.usage is None


def test_an_expired_deadline_sends_nothing(settings):
    llm, recorder = gateway(
        settings, lambda r: httpx2.Response(200, json=completion('{"text": "好"}'))
    )
    result = llm.generate(
        LLMCall(messages=MESSAGES, max_output_tokens=400, deadline=time.monotonic() - 1)
    )
    assert (result.error_code, result.sent) == ("TIMEOUT", False)
    assert recorder.requests == []
