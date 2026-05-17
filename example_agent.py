"""Mock forecast agent server.

A minimal FastAPI agent that receives events and returns a valid (but
fake) probability distribution. Stripped from the original Anthropic-
backed example_agent.py — no LLM, no API keys, no external calls.

Useful for end-to-end testing the Prophet Hacks /submit-endpoint
form's optional health + forecast checks: deploy this to Render, paste
the URL into the form, and the forecast check should come back green.

Usage:
    pip install -r requirements.txt
    python example_agent.py
    # or:
    uvicorn example_agent:app --host 0.0.0.0 --port 8000

Then:
    curl http://localhost:8000/health
    curl -X POST http://localhost:8000/predict \\
        -H "Content-Type: application/json" \\
        -d '{"event_ticker":"x","market_ticker":"x","title":"t",
             "category":"c","close_time":"2026-06-30T23:59:59Z",
             "outcomes":["A","B","C","D"]}'
"""

import hashlib
import logging
import os
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="Mock Forecast Agent")


# ---------------------------------------------------------------------------
# Request / Response models — identical to ai-prophet's example_agent.py so
# this drops in as a behavior-compatible substitute.
# ---------------------------------------------------------------------------

class EventRequest(BaseModel):
    event_ticker: str
    market_ticker: str
    title: str
    subtitle: str | None = None
    description: str | None = None
    category: str
    rules: str | None = None
    close_time: str
    outcomes: list[str] | None = None
    # The real evaluator sends a `resolved_outcome` field too (nullable).
    # Allow but ignore it so strict pydantic configs don't trip.
    resolved_outcome: str | None = None


class MarketProbability(BaseModel):
    market: str
    probability: float


class PredictionResponse(BaseModel):
    probabilities: list[MarketProbability]


# ---------------------------------------------------------------------------
# Mock forecasting — deterministic seeded distribution over the requested
# outcomes. Every probability sits strictly in (0, 1) and the list sums
# to exactly 1.0, matching the strict validation in run_forecast.py.
# ---------------------------------------------------------------------------

def _event_markets(event: EventRequest) -> list[str]:
    if event.outcomes:
        return list(event.outcomes)
    return [event.market_ticker]


def _seeded_weights(seed: str, n: int) -> list[float]:
    """One non-zero weight per outcome, deterministic for a given seed."""
    digest = hashlib.sha256(seed.encode()).digest()
    # 8 bytes -> uint64 -> [0, 1), per slot. We need n weights; reuse the
    # hash by re-hashing with a counter when more than 4 slots are needed.
    weights: list[float] = []
    counter = 0
    while len(weights) < n:
        if counter > 0:
            digest = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
        counter += 1
        for offset in range(0, 32, 8):
            if len(weights) >= n:
                break
            slot = int.from_bytes(digest[offset:offset + 8], "big")
            # Shift into [0.1, 1.1) so post-normalization probabilities
            # are always > 0 (the eval requires strict (0, 1)).
            weights.append(0.1 + (slot % 100_000) / 100_000)
    return weights


def mock_forecast(event: EventRequest) -> PredictionResponse:
    markets = _event_markets(event)
    if not markets:
        raise ValueError("Event has no markets/outcomes")

    seed = f"{event.event_ticker}|{','.join(markets)}"
    raw = _seeded_weights(seed, len(markets))
    total = sum(raw) or 1.0

    probabilities = [
        MarketProbability(market=m, probability=round(w / total, 6))
        for m, w in zip(markets, raw)
    ]

    # Renormalize so the (rounded) sum lands at exactly 1.0 — the eval
    # tolerates ±0.001 but it's free to be exact.
    drift = 1.0 - sum(p.probability for p in probabilities)
    if probabilities:
        probabilities[0].probability = round(probabilities[0].probability + drift, 6)
    return PredictionResponse(probabilities=probabilities)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "name": "mock forecast agent"}


@app.post("/predict", response_model=PredictionResponse)
async def predict_endpoint(event: EventRequest) -> PredictionResponse:
    logger.info("Forecasting %s: %s", event.market_ticker, event.title)
    return mock_forecast(event)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    uvicorn.run(
        "example_agent:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
    )


if __name__ == "__main__":
    main()
