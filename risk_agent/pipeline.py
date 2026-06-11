"""The Risk Radar pipeline — in-process multi-agent orchestration (A2A).

Monitor (code) -> Catalyst (Gemini + Google Search) -> Analyst (Gemini, structured)
-> Action (Firestore writer). Each stage hands its output to the next; the whole
thing runs in one Cloud Run container.

The pipeline is exposed as an async generator (`stream_risk_radar`) that emits a
progress event as each stage actually starts and finishes, so the UI can show
real progress instead of a guessed animation. `run_risk_radar` simply drains the
generator and returns the final result (used by the scheduled job and the plain
JSON endpoint).
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

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


def _clear_symbols(scanned: list[str], flagged: list[str]) -> list[str]:
    """Symbols that were checked but carry no notable smart-money signal."""
    flagged_set = set(flagged)
    seen: set[str] = set()
    out: list[str] = []
    for s in scanned:
        if s not in flagged_set and s not in seen:
            seen.add(s)
            out.append(s)
    return out


async def stream_risk_radar(
    user_id: str, symbols: list[str], *, persist: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Run the pipeline, yielding a progress event per stage + a final result.

    Event shapes:
      {"stage": "monitor", "status": "start"}
      {"stage": "monitor", "status": "done", "scanned": [...], "flagged": [...],
       "clear": [...], "counts": {...}}
      {"stage": "catalyst"|"analyst"|"action", "status": "start"|"done"|"skip"}
      {"stage": "result", "data": {...full assessment payload...}}
    """
    # 1. MONITOR — pull smart-money findings from the risk API (deterministic).
    yield {"stage": "monitor", "status": "start"}
    scan = scan_portfolio(symbols)
    scanned = scan.get("scanned_symbols", symbols)
    flagged = _flagged_symbols(scan)
    clear = _clear_symbols(scanned, flagged)
    counts = scan.get("counts", {})
    yield {
        "stage": "monitor", "status": "done",
        "scanned": scanned, "flagged": flagged, "clear": clear, "counts": counts,
    }

    # Nothing notable — skip the LLM stages, persist the clean scan, return early.
    if not flagged:
        for stage in ("catalyst", "analyst"):
            yield {"stage": stage, "status": "skip"}
        yield {"stage": "action", "status": "start"}
        scan_id = store.save_scan(user_id, symbols, scan) if persist else None
        yield {"stage": "action", "status": "done"}
        yield {"stage": "result", "data": {
            "user_id": user_id,
            "scanned_symbols": scanned,
            "clear_symbols": clear,
            "counts": counts,
            "assessment": {"portfolio_risk_score": 0,
                           "headline": "No notable smart-money risk signals today.",
                           "stocks": []},
            "scan_id": scan_id,
        }}
        return

    # 2. CATALYST — ground "why are these moving" via Google Search.
    yield {"stage": "catalyst", "status": "start"}
    catalyst_notes = await run_agent(
        catalyst_agent, "Symbols: " + ", ".join(flagged)
    )
    yield {"stage": "catalyst", "status": "done"}

    # 3. ANALYST — structured cross-signal risk assessment (schema-constrained).
    yield {"stage": "analyst", "status": "start"}
    analyst_prompt = (
        "FINDINGS (JSON):\n" + json.dumps(scan["findings"], default=str)
        + "\n\nCATALYST NOTES:\n" + catalyst_notes
        + "\n\nProduce the PortfolioRiskAssessment."
    )
    raw = await run_agent(analyst_agent, analyst_prompt)
    assessment = _parse_assessment(raw)
    yield {"stage": "analyst", "status": "done"}

    # 4. ACTION — persist scan + write the risk register (the tangible act).
    yield {"stage": "action", "status": "start"}
    scan_id = store.save_scan(user_id, symbols, scan) if persist else None
    register_ids = (
        store.save_assessment(user_id, assessment, scan["findings"]) if persist else []
    )
    yield {"stage": "action", "status": "done"}

    yield {"stage": "result", "data": {
        "user_id": user_id,
        "scanned_symbols": scanned,
        "clear_symbols": clear,
        "counts": counts,
        "catalyst_notes": catalyst_notes,
        "assessment": assessment,
        "scan_id": scan_id,
        "risk_register_ids": register_ids,
    }}


async def run_risk_radar(
    user_id: str, symbols: list[str], *, persist: bool = True,
) -> dict[str, Any]:
    """Run the full pipeline and return the final assessment payload."""
    result: dict[str, Any] = {}
    async for event in stream_risk_radar(user_id, symbols, persist=persist):
        if event.get("stage") == "result":
            result = event["data"]
    return result


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
