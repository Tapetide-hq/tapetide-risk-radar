"""The Risk Radar pipeline — in-process multi-agent orchestration (A2A).

Monitor (code) -> Catalyst (Gemini + Google Search) -> Analyst (Gemini, structured)
-> Action (Firestore writer). Each stage hands its output to the next; the whole
thing runs in one Cloud Run container.
"""

from __future__ import annotations

import json
from typing import Any

from . import store
from .agents import analyst_agent, catalyst_agent, run_agent
from .schemas import PortfolioRiskAssessment
from .data_client import scan_portfolio

# Severities worth spending a grounding/LLM pass on.
_NOTABLE = {"alert", "watch"}


def _flagged_symbols(scan: dict[str, Any]) -> list[str]:
    return sorted({
        f["symbol"] for f in scan.get("findings", []) if f["severity"] in _NOTABLE
    })


async def run_risk_radar(
    user_id: str, symbols: list[str], *, persist: bool = True,
) -> dict[str, Any]:
    """Run the full pipeline for a portfolio and return the assessment + metadata."""
    # 1. MONITOR — pull smart-money findings from the risk API (deterministic).
    scan = scan_portfolio(symbols)
    flagged = _flagged_symbols(scan)

    if not flagged:
        result = {
            "user_id": user_id,
            "scanned_symbols": scan.get("scanned_symbols", symbols),
            "counts": scan.get("counts", {}),
            "assessment": {"portfolio_risk_score": 0,
                           "headline": "No notable smart-money risk signals today.",
                           "stocks": []},
            "scan_id": store.save_scan(user_id, symbols, scan) if persist else None,
        }
        return result

    # 2. CATALYST — ground "why are these moving" via Google Search.
    catalyst_notes = await run_agent(
        catalyst_agent, "Symbols: " + ", ".join(flagged)
    )

    # 3. ANALYST — structured cross-signal risk assessment (schema-constrained).
    analyst_prompt = (
        "FINDINGS (JSON):\n" + json.dumps(scan["findings"], default=str)
        + "\n\nCATALYST NOTES:\n" + catalyst_notes
        + "\n\nProduce the PortfolioRiskAssessment."
    )
    raw = await run_agent(analyst_agent, analyst_prompt)
    assessment = _parse_assessment(raw)

    # 4. ACTION — persist scan + write the risk register (the tangible act).
    scan_id = store.save_scan(user_id, symbols, scan) if persist else None
    register_ids = (
        store.save_assessment(user_id, assessment, scan["findings"]) if persist else []
    )

    return {
        "user_id": user_id,
        "scanned_symbols": scan.get("scanned_symbols", symbols),
        "counts": scan.get("counts", {}),
        "catalyst_notes": catalyst_notes,
        "assessment": assessment,
        "scan_id": scan_id,
        "risk_register_ids": register_ids,
    }


def _parse_assessment(raw: str) -> dict[str, Any]:
    """Validate the analyst's structured output; fall back gracefully."""
    try:
        return PortfolioRiskAssessment.model_validate_json(raw).model_dump()
    except Exception:
        try:
            return PortfolioRiskAssessment.model_validate(json.loads(raw)).model_dump()
        except Exception:
            return {"portfolio_risk_score": 0,
                    "headline": "Assessment unavailable (parse error).",
                    "stocks": []}
