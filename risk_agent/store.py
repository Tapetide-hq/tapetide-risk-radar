"""Firestore persistence: portfolios, scan history, and the risk register.

The risk register is the agent's tangible "action" — durable, queryable risk
alerts (also exportable to BigQuery via the Firestore extension for analytics).
Client is lazily initialized so importing this module needs no credentials.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import settings

_client = None


def _db():
    global _client
    if _client is None:
        from google.cloud import firestore  # imported lazily (needs creds)
        _client = firestore.Client(
            project=settings.GCP_PROJECT or None,
            database=settings.FIRESTORE_DATABASE,
        )
    return _client


def _today() -> str:
    return dt.date.today().isoformat()


def get_portfolio(user_id: str) -> list[str]:
    """Return a user's tracked symbols; empty list if none stored."""
    doc = _db().collection(settings.PORTFOLIO_COLLECTION).document(user_id).get()
    if doc.exists:
        return list(doc.to_dict().get("symbols", []))
    return []


def save_portfolio(user_id: str, symbols: list[str]) -> None:
    _db().collection(settings.PORTFOLIO_COLLECTION).document(user_id).set(
        {"symbols": symbols, "updated_at": dt.datetime.now(dt.timezone.utc)}
    )


def save_scan(user_id: str, symbols: list[str], scan_result: dict[str, Any]) -> str:
    """Persist a raw scan and return its document id."""
    ref = _db().collection(settings.SCAN_HISTORY_COLLECTION).document()
    ref.set({
        "user_id": user_id,
        "symbols": symbols,
        "counts": scan_result.get("counts", {}),
        "findings": scan_result.get("findings", []),
        "scanned_at": dt.datetime.now(dt.timezone.utc),
        "trade_date": _today(),
    })
    return ref.id


def save_assessment(
    user_id: str, assessment: dict[str, Any], findings: list[dict[str, Any]],
) -> list[str]:
    """Write one risk-register entry per assessed stock. Idempotent per day.

    Doc id = {user}_{symbol}_{date} so re-runs on the same day update rather
    than duplicate (alert dedupe).
    """
    written: list[str] = []
    findings_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        findings_by_symbol.setdefault(f["symbol"], []).append(f)

    col = _db().collection(settings.RISK_REGISTER_COLLECTION)
    now = dt.datetime.now(dt.timezone.utc)
    for stock in assessment.get("stocks", []):
        sym = stock["symbol"]
        doc_id = f"{user_id}_{sym}_{_today()}"
        col.document(doc_id).set({
            "user_id": user_id,
            "symbol": sym,
            "risk_level": stock.get("risk_level"),
            "risk_score": stock.get("risk_score"),
            "thesis": stock.get("thesis"),
            "key_signals": stock.get("key_signals", []),
            "catalyst": stock.get("catalyst", ""),
            "recommended_review": stock.get("recommended_review", False),
            "raw_findings": findings_by_symbol.get(sym, []),
            "trade_date": _today(),
            "created_at": now,
        })
        written.append(doc_id)
    return written
