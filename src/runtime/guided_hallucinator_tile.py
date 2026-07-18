"""Guided hallucinator tile that wraps TinyLLaMA with deterministic guardrails."""
from __future__ import annotations

import hashlib
import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple

from runtime.constraint_substrate import ConstraintFact
from runtime.semantic_router import TileExecutionResult
from runtime.tinyllama_health import DEFAULT_MONITOR, TinyLlamaHealthMonitor, TinyLlamaHealthSnapshot


class TinyLlamaError(Exception):
    """Base exception for TinyLLaMA client failures."""


class TinyLlamaTimeoutError(TinyLlamaError):
    """Raised when the TinyLLaMA endpoint times out."""


class TinyLlamaContextOverflowError(TinyLlamaError):
    """Raised when the request exceeds TinyLLaMA context limits."""


class TinyLlamaServerError(TinyLlamaError):
    """Raised for other TinyLLaMA HTTP failures."""


class TinyLlamaClient(Protocol):
    """Protocol for dependency-injected TinyLLaMA HTTP clients."""

    def complete(self, request: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        ...


class TinyLlamaHttpClient:
    """Minimal urllib-based client for the TinyLLaMA server."""

    def __init__(self, base_url: str = "http://127.0.0.1:8088") -> None:
        self._endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"

    def complete(self, request: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        data = json.dumps(request).encode("utf-8")
        http_request = urllib.request.Request(
            self._endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=timeout_ms / 1000) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            if exc.code == 500 and "Context size has been exceeded" in body:
                raise TinyLlamaContextOverflowError(body) from exc
            raise TinyLlamaServerError(body) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network dependent
            if isinstance(exc.reason, socket.timeout):
                raise TinyLlamaTimeoutError(str(exc.reason)) from exc
            raise TinyLlamaError(str(exc)) from exc


@dataclass
class TileExecutionState:
    """Holds deterministic counters for concurrency management."""

    in_flight: int = 0
    queue_depth: int = 0


@dataclass
class SlotAcquisition:
    acquired: bool
    queued: bool
    queue_wait_ms: int
    reason: Optional[str] = None


class GuidedHallucinatorTile:
    """Defensive tile that calls TinyLLaMA under the enforced contract."""

    TILE_ID = "tile.lang.guided_hallucinator"
    INPUT_TYPES = ["conversation.turn", "conversation.context_snapshot"]
    OUTPUT_TYPE = "conversation.hypothesis"

    MODEL = "tinyllama"
    SYSTEM_PROMPT = (
        "You are the guided hallucinator tile. Generate creative hypotheses"
        " grounded in provided context and include self-check notes."
    )

    MAX_CONCURRENT_REQUESTS = 4
    MAX_PROMPT_TOKENS = 256
    MAX_COMPLETION_TOKENS = 480
    REQUEST_TIMEOUT_MS = 30_000
    QUEUE_CAPACITY = 4
    QUEUE_WAIT_STEP_MS = 75
    MAX_TIMEOUT_RETRIES = 1

    DEPENDENCY_EVIDENCE_REFS = [
        "models/server.logs/server.log1.md",
        "tmp/slot_full_with_slots.json",
        "tmp/slot_full_with_slots_timeseries.json",
    ]

    def __init__(
        self,
        client: Optional[TinyLlamaClient] = None,
        state: Optional[TileExecutionState] = None,
        health_monitor: Optional[TinyLlamaHealthMonitor] = None,
    ) -> None:
        self._client = client or TinyLlamaHttpClient()
        self._state = state or TileExecutionState()
        self._health_monitor = health_monitor or DEFAULT_MONITOR

    def execute(self, fact: ConstraintFact) -> TileExecutionResult:
        request_uuid = self._build_request_uuid(fact)
        prompt_text = self._extract_prompt(fact)
        prompt_tokens = self._estimate_tokens(prompt_text)
        telemetry = self._base_telemetry()
        health_snapshot = self._health_monitor.ensure_fresh(timeout=1.5)
        if prompt_tokens > self.MAX_PROMPT_TOKENS:
            telemetry["slot_contention_events"] = 0
            return self._build_refusal(
                fact,
                request_uuid,
                prompt_tokens,
                completion_tokens=0,
                outcome="terminal_refusal",
                reason="prompt_too_large",
                telemetry=telemetry,
                health_snapshot=health_snapshot,
            )

        acquisition = self._acquire_slot()
        telemetry["slot_contention_events"] = int(acquisition.queued)
        telemetry["queue_wait_duration_ms"] = acquisition.queue_wait_ms
        if not acquisition.acquired:
            return self._build_refusal(
                fact,
                request_uuid,
                prompt_tokens,
                completion_tokens=0,
                outcome="structured_refusal",
                reason=acquisition.reason or "queue_full",
                telemetry=telemetry,
                health_snapshot=health_snapshot,
            )

        request_body = self._build_request_body(prompt_text, fact, request_uuid)
        timeout_events = 0
        try:
            response, completion_tokens, timeout_events = self._call_with_retry(
                request_body, telemetry
            )
            hypothesis_text = self._extract_completion_text(response)
            payload = self._build_success_payload(
                fact,
                request_uuid,
                prompt_tokens,
                completion_tokens,
                hypothesis_text,
                telemetry,
                health_snapshot,
            )
            result_fact = ConstraintFact(
                fact_id=f"hypothesis::{fact.fact_id}",
                fact_type=self.OUTPUT_TYPE,
                payload=payload,
                confidence=payload["self_assessment"]["confidence"],
                ttl_seconds=fact.ttl_seconds,
                provenance={
                    "tile": self.TILE_ID,
                    "source_fact": fact.fact_id,
                },
                constraints_compliance=fact.constraints_compliance,
            )
            work_metrics = self._build_work_metrics(
                prompt_tokens,
                completion_tokens,
                telemetry,
                timeout_events,
            )
            return TileExecutionResult(result_fact, work_metrics)
        except TinyLlamaContextOverflowError:
            telemetry["context_overflow_refusals"] = 1
            return self._build_refusal(
                fact,
                request_uuid,
                prompt_tokens,
                completion_tokens=0,
                outcome="terminal_refusal",
                reason="context_overflow",
                telemetry=telemetry,
                health_snapshot=health_snapshot,
            )
        except TinyLlamaTimeoutError:
            telemetry["timeout_expirations"] += 1
            return self._build_refusal(
                fact,
                request_uuid,
                prompt_tokens,
                completion_tokens=0,
                outcome="timeout",
                reason="timeout",
                telemetry=telemetry,
                health_snapshot=health_snapshot,
            )
        finally:
            if acquisition.acquired:
                self._release_slot()

    def _call_with_retry(
        self,
        request_body: Dict[str, Any],
        telemetry: Dict[str, int],
    ) -> Tuple[Dict[str, Any], int, int]:
        attempts = 0
        timeout_events = 0
        while True:
            try:
                response = self._client.complete(request_body, self.REQUEST_TIMEOUT_MS)
                completion_tokens = self._extract_completion_tokens(response)
                return response, completion_tokens, timeout_events
            except TinyLlamaTimeoutError:
                timeout_events += 1
                telemetry["timeout_expirations"] += 1
                if attempts >= self.MAX_TIMEOUT_RETRIES:
                    raise
                attempts += 1
                continue

    def _build_refusal(
        self,
        fact: ConstraintFact,
        request_uuid: str,
        prompt_tokens: int,
        completion_tokens: int,
        outcome: str,
        reason: str,
        telemetry: Dict[str, int],
        health_snapshot: TinyLlamaHealthSnapshot,
    ) -> TileExecutionResult:
        payload = {
            "request_uuid": request_uuid,
            "hypothesis": {
                "summary": "",
                "reason": reason,
            },
            "self_assessment": {
                "confidence": 0.0,
                "reason": reason,
            },
            "outcome": outcome,
            "reason": reason,
            "telemetry": {
                **telemetry,
                "dependency_evidence_refs": self.DEPENDENCY_EVIDENCE_REFS,
                "health_snapshot": health_snapshot.to_dict(),
            },
        }
        fact_result = ConstraintFact(
            fact_id=f"hypothesis::{fact.fact_id}",
            fact_type=self.OUTPUT_TYPE,
            payload=payload,
            confidence=0.0,
            ttl_seconds=fact.ttl_seconds,
            provenance={"tile": self.TILE_ID, "source_fact": fact.fact_id},
            constraints_compliance=fact.constraints_compliance,
        )
        work_metrics = self._build_work_metrics(
            prompt_tokens,
            completion_tokens,
            telemetry,
            timeout_events=telemetry.get("timeout_expirations", 0),
        )
        return TileExecutionResult(fact_result, work_metrics)

    def _build_success_payload(
        self,
        fact: ConstraintFact,
        request_uuid: str,
        prompt_tokens: int,
        completion_tokens: int,
        hypothesis_text: str,
        telemetry: Dict[str, int],
        health_snapshot: TinyLlamaHealthSnapshot,
    ) -> Dict[str, Any]:
        confidence = self._score_confidence(completion_tokens)
        return {
            "request_uuid": request_uuid,
            "hypothesis": {
                "summary": hypothesis_text,
                "source": "tinyllama",
            },
            "self_assessment": {
                "confidence": confidence,
                "reason": "tinyllama_response",
            },
            "prompt_tokens_actual": prompt_tokens,
            "completion_tokens_actual": completion_tokens,
            "outcome": "success",
            "telemetry": {
                **telemetry,
                "dependency_evidence_refs": self.DEPENDENCY_EVIDENCE_REFS,
                "health_snapshot": health_snapshot.to_dict(),
            },
        }

    def _build_work_metrics(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        telemetry: Dict[str, int],
        timeout_events: int,
    ) -> Dict[str, float]:
        operation_units = float(prompt_tokens + completion_tokens)
        return {
            "prompt_tokens": float(prompt_tokens),
            "completion_tokens": float(completion_tokens),
            "operation_units": operation_units,
            "slot_contention_events": float(telemetry.get("slot_contention_events", 0)),
            "timeout_expirations": float(timeout_events),
            "queue_wait_duration_ms": float(telemetry.get("queue_wait_duration_ms", 0)),
        }

    def _acquire_slot(self) -> SlotAcquisition:
        if self._state.in_flight < self.MAX_CONCURRENT_REQUESTS:
            self._state.in_flight += 1
            return SlotAcquisition(acquired=True, queued=False, queue_wait_ms=0)
        if self._state.queue_depth >= self.QUEUE_CAPACITY:
            return SlotAcquisition(acquired=False, queued=False, queue_wait_ms=0, reason="queue_full")
        self._state.queue_depth += 1
        queue_position = self._state.queue_depth
        wait_ms = queue_position * self.QUEUE_WAIT_STEP_MS
        self._state.queue_depth = max(0, self._state.queue_depth - 1)
        self._state.in_flight += 1
        return SlotAcquisition(acquired=True, queued=True, queue_wait_ms=wait_ms)

    def _release_slot(self) -> None:
        self._state.in_flight = max(0, self._state.in_flight - 1)

    def _build_request_uuid(self, fact: ConstraintFact) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.TILE_ID.encode("utf-8"))
        hasher.update(fact.fact_id.encode("utf-8"))
        text = self._extract_prompt(fact)
        hasher.update(text.encode("utf-8"))
        return hasher.hexdigest()

    def _extract_prompt(self, fact: ConstraintFact) -> str:
        text = str(fact.payload.get("text", "")).strip()
        context = str(fact.payload.get("context", "")).strip()
        if context:
            return f"{context}\n\n{text}".strip()
        return text

    def _build_request_body(
        self,
        prompt_text: str,
        fact: ConstraintFact,
        request_uuid: str,
    ) -> Dict[str, Any]:
        seed = int(hashlib.sha256(request_uuid.encode("utf-8")).hexdigest()[0:8], 16)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ]
        return {
            "model": self.MODEL,
            "seed": seed,
            "temperature": 0.2,
            "max_tokens": self.MAX_COMPLETION_TOKENS,
            "messages": messages,
            "metadata": {
                "tile_id": self.TILE_ID,
                "source_fact": fact.fact_id,
            },
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return len([token for token in text.split() if token])

    @staticmethod
    def _extract_completion_text(response: Dict[str, Any]) -> str:
        choices = response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return str(message.get("content", "")).strip()

    @staticmethod
    def _extract_completion_tokens(response: Dict[str, Any]) -> int:
        usage = response.get("usage", {})
        completion_tokens = int(usage.get("completion_tokens", 0))
        if completion_tokens:
            return completion_tokens
        content = GuidedHallucinatorTile._extract_completion_text(response)
        return GuidedHallucinatorTile._estimate_tokens(content)

    @staticmethod
    def _score_confidence(completion_tokens: int) -> float:
        if completion_tokens <= 0:
            return 0.5
        ratio = completion_tokens / (completion_tokens + 200)
        return round(min(0.95, 0.6 + ratio), 4)

    @staticmethod
    def _base_telemetry() -> Dict[str, int]:
        return {
            "slot_contention_events": 0,
            "timeout_expirations": 0,
            "context_overflow_refusals": 0,
            "queue_wait_duration_ms": 0,
        }
