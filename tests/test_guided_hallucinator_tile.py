from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import io
import json
import urllib.error
import urllib.request

import pytest

from runtime.constraint_substrate import ConstraintFact
from runtime.guided_hallucinator_tile import (
    GuidedHallucinatorTile,
    TileExecutionState,
    TinyLlamaHttpClient,
    TinyLlamaContextOverflowError,
    TinyLlamaTimeoutError,
    TinyLlamaServerError,
)


@dataclass
class StubClient:
    responses: List[Any]

    def complete(self, request: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        if not self.responses:
            raise AssertionError("no stubbed responses remaining")
        action = self.responses.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def _build_fact(text: str = "Imagine a city of glass.", context: Optional[str] = None) -> ConstraintFact:
    payload: Dict[str, Any] = {"text": text}
    if context is not None:
        payload["context"] = context
    return ConstraintFact(
        fact_id="fact.conversation::demo",
        fact_type="conversation.turn",
        payload=payload,
        confidence=0.9,
        ttl_seconds=300,
        provenance={"tile": "tile.lang.semantic_router"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )


def test_guided_hallucinator_success() -> None:
    client = StubClient(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "content": "Hypothesis: build mirrored towers."
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 60},
            }
        ]
    )
    tile = GuidedHallucinatorTile(client=client)

    result = tile.execute(_build_fact())

    assert result.fact.payload["outcome"] == "success"
    assert result.fact.payload["hypothesis"]["summary"].startswith("Hypothesis")
    assert result.fact.payload["self_assessment"]["confidence"] > 0.5
    assert result.work_metrics["completion_tokens"] == 60.0
    telemetry = result.fact.payload["telemetry"]
    assert telemetry["dependency_evidence_refs"] == GuidedHallucinatorTile.DEPENDENCY_EVIDENCE_REFS
    assert telemetry["slot_contention_events"] == 0


def test_guided_hallucinator_timeout_retries_once_then_succeeds() -> None:
    client = StubClient(
        responses=[
            TinyLlamaTimeoutError("timeout"),
            {
                "choices": [
                    {
                        "message": {
                            "content": "Hypothesis: forge river domes."
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 40},
            },
        ]
    )
    tile = GuidedHallucinatorTile(client=client)

    result = tile.execute(_build_fact("Craft a deterministic plan."))

    telemetry = result.fact.payload["telemetry"]
    assert telemetry["timeout_expirations"] == 1
    assert result.fact.payload["outcome"] == "success"
    assert result.work_metrics["timeout_expirations"] == 1.0


def test_guided_hallucinator_context_overflow_refusal() -> None:
    client = StubClient(responses=[TinyLlamaContextOverflowError("context exceeded")])
    tile = GuidedHallucinatorTile(client=client)

    result = tile.execute(_build_fact())

    assert result.fact.payload["outcome"] == "terminal_refusal"
    assert result.fact.payload["reason"] == "context_overflow"
    assert result.fact.payload["self_assessment"]["confidence"] == 0.0
    telemetry = result.fact.payload["telemetry"]
    assert telemetry["context_overflow_refusals"] == 1


def test_guided_hallucinator_queue_full_refusal() -> None:
    state = TileExecutionState(
        in_flight=GuidedHallucinatorTile.MAX_CONCURRENT_REQUESTS,
        queue_depth=GuidedHallucinatorTile.QUEUE_CAPACITY,
    )
    tile = GuidedHallucinatorTile(client=StubClient(responses=[]), state=state)

    result = tile.execute(_build_fact())

    assert result.fact.payload["outcome"] == "structured_refusal"
    assert result.fact.payload["reason"] == "queue_full"
    assert result.fact.confidence == 0.0
    telemetry = result.fact.payload["telemetry"]
    assert telemetry["slot_contention_events"] == 0
    assert telemetry["queue_wait_duration_ms"] == 0


def test_guided_hallucinator_prompt_too_large_refusal() -> None:
    long_text = "word " * (GuidedHallucinatorTile.MAX_PROMPT_TOKENS + 10)
    tile = GuidedHallucinatorTile(client=StubClient(responses=[]))

    result = tile.execute(_build_fact(text=long_text))

    assert result.fact.payload["outcome"] == "terminal_refusal"
    assert result.fact.payload["reason"] == "prompt_too_large"
    telemetry = result.fact.payload["telemetry"]
    assert telemetry["slot_contention_events"] == 0
    assert result.work_metrics["prompt_tokens"] == float(
        GuidedHallucinatorTile.MAX_PROMPT_TOKENS + 10
    )


def test_guided_hallucinator_queue_waits_when_slots_busy() -> None:
    state = TileExecutionState(
        in_flight=GuidedHallucinatorTile.MAX_CONCURRENT_REQUESTS,
        queue_depth=1,
    )
    client = StubClient(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "content": "Hypothesis: queue waits then proceeds."
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 24},
            }
        ]
    )
    tile = GuidedHallucinatorTile(client=client, state=state)

    result = tile.execute(_build_fact("Queue behavior probe."))

    telemetry = result.fact.payload["telemetry"]
    assert telemetry["slot_contention_events"] == 1
    assert telemetry["queue_wait_duration_ms"] == 2 * GuidedHallucinatorTile.QUEUE_WAIT_STEP_MS
    assert result.fact.payload["outcome"] == "success"
    assert result.work_metrics["slot_contention_events"] == 1.0


def test_guided_hallucinator_timeout_terminal_refusal_after_retries() -> None:
    class AlwaysTimeoutClient:
        def complete(self, request: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
            raise TinyLlamaTimeoutError("timeout")

    tile = GuidedHallucinatorTile(client=AlwaysTimeoutClient())

    result = tile.execute(_build_fact("Timeout exhaustion probe."))

    expected_timeouts = GuidedHallucinatorTile.MAX_TIMEOUT_RETRIES + 2
    telemetry = result.fact.payload["telemetry"]
    assert result.fact.payload["outcome"] == "timeout"
    assert telemetry["timeout_expirations"] == expected_timeouts
    assert result.work_metrics["timeout_expirations"] == float(expected_timeouts)


def test_guided_hallucinator_request_includes_context() -> None:
    recorded: Dict[str, Any] = {}

    class RecordingClient:
        def complete(self, request: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
            recorded.update(request)
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Hypothesis: context respected."
                        }
                    }
                ],
                "usage": {"completion_tokens": 10},
            }

    tile = GuidedHallucinatorTile(client=RecordingClient())
    fact = _build_fact(text="Please respond.", context="Add prior context.")

    result = tile.execute(fact)

    user_message = recorded["messages"][1]["content"]
    assert "Add prior context." in user_message and "Please respond." in user_message
    assert result.fact.payload["hypothesis"]["summary"].startswith("Hypothesis")


def test_guided_hallucinator_handles_empty_completion_payload() -> None:
    client = StubClient(
        responses=[
            {
                "choices": [],
                "usage": {},
            }
        ]
    )
    tile = GuidedHallucinatorTile(client=client)

    result = tile.execute(_build_fact(text=""))

    assert result.fact.payload["outcome"] == "success"
    assert result.fact.payload["hypothesis"]["summary"] == ""
    assert result.fact.payload["self_assessment"]["confidence"] == 0.5


def test_tiny_llama_http_client_posts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    class DummyResponse:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> DummyResponse:
        captured["data"] = json.loads(request.data.decode("utf-8"))
        return DummyResponse({"choices": [], "usage": {"completion_tokens": 1}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = TinyLlamaHttpClient(base_url="http://example.test")

    result = client.complete({"foo": "bar"}, timeout_ms=1500)

    assert result["usage"]["completion_tokens"] == 1
    assert captured["data"] == {"foo": "bar"}


def test_tiny_llama_http_client_context_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> None:
        raise urllib.error.HTTPError(
            url=str(request.full_url),
            code=500,
            msg="context",
            hdrs=None,
            fp=io.BytesIO(b"Context size has been exceeded"),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = TinyLlamaHttpClient()

    with pytest.raises(TinyLlamaContextOverflowError):
        client.complete({"prompt": "text"}, timeout_ms=1000)


def test_tiny_llama_http_client_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> None:
        raise urllib.error.HTTPError(
            url=str(request.full_url),
            code=502,
            msg="boom",
            hdrs=None,
            fp=io.BytesIO(b"gateway failure"),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = TinyLlamaHttpClient()

    with pytest.raises(TinyLlamaServerError):
        client.complete({"prompt": "text"}, timeout_ms=1000)
