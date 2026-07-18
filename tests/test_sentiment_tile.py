from __future__ import annotations

from runtime.constraint_substrate import ConstraintFact
from runtime.sentiment_tile import SentimentTile


def _build_text_fact(text: str) -> ConstraintFact:
    return ConstraintFact(
        fact_id="fact.user_text",
        fact_type="user.text_input",
        payload={"text": text},
        confidence=1.0,
        ttl_seconds=300,
        provenance={"source": "test"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )


def test_sentiment_positive_text() -> None:
    tile = SentimentTile()
    result = tile.execute(_build_text_fact("I love this fantastic product"))

    assert result.fact.payload["sentiment"] == "positive"
    assert result.fact.payload["positive_hits"] >= 2
    assert result.fact.payload["confidence"] > 0.7


def test_sentiment_negative_text() -> None:
    tile = SentimentTile()
    result = tile.execute(_build_text_fact("This service is awful and terrible"))

    assert result.fact.payload["sentiment"] == "negative"
    assert result.fact.payload["negative_hits"] >= 2
    assert result.fact.payload["confidence"] > 0.7


def test_sentiment_neutral_text() -> None:
    tile = SentimentTile()
    result = tile.execute(_build_text_fact("The meeting is scheduled for 3pm"))

    assert result.fact.payload["sentiment"] == "neutral"
    assert 0.2 < result.fact.payload["confidence"] <= 0.4


def test_sentiment_deterministic_outputs() -> None:
    tile = SentimentTile()
    fact = _build_text_fact("I am happy but waiting")
    first = tile.execute(fact)
    second = tile.execute(fact)

    assert first.fact.payload == second.fact.payload
    assert first.work_metrics == second.work_metrics


def test_sentiment_preserves_provenance() -> None:
    tile = SentimentTile()
    fact = _build_text_fact("I hate waiting")
    result = tile.execute(fact)

    assert result.fact.provenance == {
        "tile": SentimentTile.TILE_ID,
        "source_fact": fact.fact_id,
    }
    assert result.fact.fact_id == f"sentiment::{fact.fact_id}"
    assert result.fact.fact_type == SentimentTile.OUTPUT_TYPE


def test_sentiment_work_metrics_scale_with_length() -> None:
    tile = SentimentTile()
    short = tile.execute(_build_text_fact("love"))
    long = tile.execute(_build_text_fact("I love this awesome amazing product"))

    assert long.work_metrics["token_count"] > short.work_metrics["token_count"]
    assert long.work_metrics["operation_units"] > short.work_metrics["operation_units"]
