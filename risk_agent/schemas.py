"""Structured-output schemas for the Analyst agent.

Used as Gemini `response_schema` so the model is *physically constrained* to
emit this exact shape — the Action agent can rely on the keys existing.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StockRisk(BaseModel):
    symbol: str = Field(description="NSE symbol")
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100, description="0 = calm, 100 = severe")
    thesis: str = Field(
        description="One-paragraph cross-signal narrative explaining the risk, "
        "citing the specific signals (e.g. delivery collapse + block-sell + pledge)."
    )
    key_signals: list[str] = Field(
        default_factory=list,
        description="Short bullet labels of the signals that drove this score.",
    )
    catalyst: str = Field(
        default="",
        description="If known from grounding, the likely 'why' / news catalyst. Else empty.",
    )
    recommended_review: bool = Field(
        description="True if the holder should actively review this position now."
    )


class PortfolioRiskAssessment(BaseModel):
    portfolio_risk_score: int = Field(ge=0, le=100)
    headline: str = Field(description="One-line summary of the portfolio's risk today.")
    stocks: list[StockRisk] = Field(
        default_factory=list,
        description="One entry per stock that has any non-trivial risk signal.",
    )
