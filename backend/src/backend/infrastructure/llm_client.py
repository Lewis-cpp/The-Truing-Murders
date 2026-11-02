"""The LLM gateway: the only module in the project allowed to import an HTTP client.

One `generate` call issues at most one request, never retries, never raises a
business exception, and classifies every failure into the error codes fixed by
the v0.4 spec (section 3). The API key never appears in results, logs or
exception messages, and model output carries no write path into game state.
"""

import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx2

MAX_BODY_BYTES = 64 * 1024
MAX_REPLY_CHARS = 1200

NPC_REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "minLength": 1, "maxLength": MAX_REPLY_CHARS},
    },
    "required": ["text"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMCall:
    messages: tuple[dict, ...]
    max_output_tokens: int
    deadline: float  # absolute time.monotonic() value


@dataclass(frozen=True)
class GatewayResult:
    text: str | None  # non-empty only on success
    error_code: str | None  # None means success
    sent: bool  # whether the request may have reached the provider
    usage: Usage | None  # None when missing or untrustworthy, never zero
    retry_after: float | None  # seconds
    provider_request_id: str | None
    model: str | None
    latency_ms: int


class _DeadlineExceeded(Exception):
    """The whole-call deadline ran out while reading the response body."""


def _reject_constant(name: str):
    raise ValueError(f"non-standard JSON constant: {name}")


def _object_without_duplicate_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"duplicate object key: {key}")
        seen.add(key)
    return dict(pairs)


def _strict_json(text: bytes | str):
    """Parse JSON refusing NaN/Infinity and duplicate keys; raises ValueError."""
    return json.loads(
        text, parse_constant=_reject_constant, object_pairs_hook=_object_without_duplicate_keys
    )


def _trustworthy_usage(raw) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    counts = (raw.get("prompt_tokens"), raw.get("completion_tokens"))
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in counts
    ):
        return None
    return Usage(input_tokens=counts[0], output_tokens=counts[1])


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        pass
    else:
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    try:
        target = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    return max(0.0, (target - datetime.now(UTC)).total_seconds())


class LLMGateway:
    def __init__(self, settings, transport: httpx2.BaseTransport | None = None):
        self._model = settings.llm_model
        self._api_key = settings.llm_api_key.get_secret_value()
        if transport is None:
            transport = httpx2.HTTPTransport(retries=0)
        self._client = httpx2.Client(
            base_url=settings.llm_base_url, transport=transport, follow_redirects=False
        )

    def generate(self, call: LLMCall) -> GatewayResult:
        started = time.monotonic()
        sent = False
        try:
            remaining = call.deadline - started
            if remaining <= 0:
                return self._result(started, error_code="TIMEOUT", sent=False)
            timeout = httpx2.Timeout(
                connect=min(3.0, remaining),
                pool=min(1.0, remaining),
                read=remaining,
                write=remaining,
            )
            request = self._client.build_request(
                "POST",
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": list(call.messages),
                    "max_tokens": call.max_output_tokens,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "npc_reply",
                            "strict": True,
                            "schema": NPC_REPLY_SCHEMA,
                        },
                    },
                },
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=timeout,
            )
            response = self._client.send(request, stream=True)
            sent = True
            try:
                return self._classify(response, call.deadline, started)
            finally:
                response.close()
        except (httpx2.ConnectError, httpx2.ConnectTimeout):
            return self._result(started, error_code="UNAVAILABLE", sent=False)
        except httpx2.TimeoutException:
            # Read/write/pool timeouts mean the request was already on the wire.
            return self._result(started, error_code="TIMEOUT", sent=True)
        except _DeadlineExceeded:
            return self._result(started, error_code="TIMEOUT", sent=True)
        except httpx2.HTTPError:
            return self._result(started, error_code="UNAVAILABLE", sent=sent)
        except Exception:
            # generate must never raise; an unexpected local failure is treated
            # like an unavailable provider.
            return self._result(started, error_code="UNAVAILABLE", sent=sent)

    def _result(self, started: float, **fields) -> GatewayResult:
        values = {
            "text": None,
            "error_code": None,
            "sent": False,
            "usage": None,
            "retry_after": None,
            "provider_request_id": None,
            "model": None,
        }
        values.update(fields)
        return GatewayResult(latency_ms=max(0, int((time.monotonic() - started) * 1000)), **values)

    def _read_body(self, response: httpx2.Response, deadline: float) -> tuple[bytes, bool]:
        """Read up to the size cap; returns (body, oversized). Honors the deadline."""
        pieces: list[bytes] = []
        size = 0
        # No chunk_size: yield whatever the wire delivers so a slow drip of tiny
        # chunks cannot quietly outlive the deadline between buffered reads.
        for chunk in response.iter_bytes():
            pieces.append(chunk)
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                return b"", True
            if time.monotonic() >= deadline:
                raise _DeadlineExceeded
        return b"".join(pieces), False

    def _classify(
        self, response: httpx2.Response, deadline: float, started: float
    ) -> GatewayResult:
        try:
            body, oversized = self._read_body(response, deadline)
        except httpx2.TimeoutException:
            return self._result(started, error_code="TIMEOUT", sent=True)

        status = response.status_code
        if status == 429:
            return self._result(
                started,
                error_code="RATE_LIMITED",
                sent=True,
                retry_after=_parse_retry_after(response.headers.get("Retry-After")),
            )
        if status in (401, 403):
            return self._result(started, error_code="AUTH_FAILED", sent=True)
        if status == 400 and self._error_code_is_context_length(body):
            return self._result(started, error_code="CONTEXT_TOO_LONG", sent=True)
        if 500 <= status <= 599:
            return self._result(started, error_code="UNAVAILABLE", sent=True)
        if oversized or not 200 <= status <= 299:
            # Other 4xx statuses, unfollowed redirects and oversized bodies are
            # all protocol violations.
            return self._result(started, error_code="PROTOCOL_INVALID", sent=True)
        return self._parse_completion(body, started)

    def _error_code_is_context_length(self, body: bytes) -> bool:
        try:
            parsed = _strict_json(body)
        except ValueError:
            return False
        error = parsed.get("error") if isinstance(parsed, dict) else None
        return isinstance(error, dict) and error.get("code") == "context_length_exceeded"

    def _parse_completion(self, body: bytes, started: float) -> GatewayResult:
        usage = None
        try:
            payload = _strict_json(body)
            if not isinstance(payload, dict):
                raise ValueError("the response body is not a JSON object")
            usage = _trustworthy_usage(payload.get("usage"))
            choices = payload.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("choices must hold exactly one entry")
            choice = choices[0]
            if not isinstance(choice, dict):
                raise ValueError("the choice is not an object")
            message = choice.get("message")
            if not isinstance(message, dict):
                raise ValueError("the message is not an object")
            if message.get("tool_calls"):
                raise ValueError("tool calls are not part of the protocol")
            refusal = message.get("refusal")
            finish_reason = choice.get("finish_reason")
            if (isinstance(refusal, str) and refusal) or finish_reason == "content_filter":
                return self._result(started, error_code="REFUSED", sent=True, usage=usage)
            if finish_reason == "length":
                return self._result(started, error_code="TRUNCATED", sent=True, usage=usage)
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("message.content must be a string")
            text = self._parse_reply_text(content)
        except ValueError:
            return self._result(started, error_code="PROTOCOL_INVALID", sent=True, usage=usage)
        model = payload.get("model")
        request_id = payload.get("id")
        return self._result(
            started,
            text=text,
            sent=True,
            usage=usage,
            provider_request_id=request_id if isinstance(request_id, str) else None,
            model=model if isinstance(model, str) else None,
        )

    def _parse_reply_text(self, content: str) -> str:
        try:
            reply = _strict_json(content)
        except ValueError:
            raise ValueError("message.content is not strict JSON") from None
        if not isinstance(reply, dict) or set(reply) != {"text"}:
            raise ValueError("the reply must be one object with exactly one text field")
        text = reply["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        if len(text) > MAX_REPLY_CHARS:
            raise ValueError("text is longer than 1200 characters")
        return text
