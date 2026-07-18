"""Deterministic sentiment classification tile."""
from __future__ import annotations

from typing import Dict, List

from runtime.constraint_substrate import ConstraintFact
from runtime.semantic_router import TileExecutionResult


class SentimentTile:
    """Classifies user text deterministically using lexicon counts."""

    TILE_ID = "tile.cognition.sentiment"
    INPUT_TYPES = ["user.text_input"]
    OUTPUT_TYPE = "cognition.sentiment_result"

    _POSITIVE_LEXICON = {
        "love",
        "great",
        "awesome",
        "amazing",
        "happy",
        "fantastic",
        "excellent",
    }
    _NEGATIVE_LEXICON = {
        "hate",
        "terrible",
        "awful",
        "bad",
        "angry",
        "frustrated",
        "waiting",
    }

    def execute(self, fact: ConstraintFact) -> TileExecutionResult:
        text = str(fact.payload.get("text", ""))
        normalized = text.lower()
        tokens = self._tokenize(normalized)
        positive_hits = self._count_hits(tokens, self._POSITIVE_LEXICON)
        negative_hits = self._count_hits(tokens, self._NEGATIVE_LEXICON)
        sentiment = self._classify(positive_hits, negative_hits)
        confidence = self._confidence(sentiment, positive_hits, negative_hits, len(tokens))
        payload = {
            "text": text,
            "sentiment": sentiment,
            "confidence": confidence,
            "positive_hits": positive_hits,
            "negative_hits": negative_hits,
            "rationale": "lexicon_match",
        }
        result_fact = ConstraintFact(
            fact_id=f"sentiment::{fact.fact_id}",
            fact_type=self.OUTPUT_TYPE,
            payload=payload,
            confidence=confidence,
            ttl_seconds=fact.ttl_seconds,
            provenance={"tile": self.TILE_ID, "source_fact": fact.fact_id},
            constraints_compliance=fact.constraints_compliance,
        )
        work_metrics = self._build_metrics(len(tokens), positive_hits, negative_hits)
        return TileExecutionResult(result_fact, work_metrics)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        if not text:
            return []
        return [token for token in text.split() if token]

    @staticmethod
    def _count_hits(tokens: List[str], lexicon: set[str]) -> int:
        return sum(1 for token in tokens if token.strip(".,!?") in lexicon)

    @staticmethod
    def _classify(positive_hits: int, negative_hits: int) -> str:
        if positive_hits > negative_hits:
            return "positive"
        if negative_hits > positive_hits:
            return "negative"
        return "neutral"

    @staticmethod
    def _confidence(sentiment: str, positive_hits: int, negative_hits: int, token_count: int) -> float:
        total_hits = positive_hits + negative_hits
        if sentiment == "neutral":
            return 0.4 if total_hits else 0.3
        dominant = max(positive_hits, negative_hits)
        base = 0.65 + min(dominant * 0.05, 0.25)
        proportion = dominant / max(token_count, 1)
        return round(min(base + proportion * 0.1, 0.95), 4)

    @staticmethod
    def _build_metrics(token_count: int, positive_hits: int, negative_hits: int) -> Dict[str, float]:
        lexicon_hits = positive_hits + negative_hits
        operation_units = float(token_count + (lexicon_hits * 2))
        return {
            "token_count": float(token_count),
            "lexicon_hits": float(lexicon_hits),
            "operation_units": operation_units,
        }
