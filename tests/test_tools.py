"""Integration tests for the Risk Radar detectors against the live (read-only) DB.

These tests discover currently-triggering symbols from the database, then assert
the matching detector flags them. This keeps tests meaningful without hard-coding
symbols whose live state changes daily. Requires DATABASE_URL (.env).
"""

from __future__ import annotations

import pytest

from risk_radar import (
    scan_fno_ban,
    scan_delivery_collapse,
    scan_block_deals,
    scan_mtf_surge,
    scan_slbm_spike,
    get_pledge_disclosures,
    scan_portfolio,
)
from risk_radar.config import Severity
from risk_radar.db import query

VALID_SEVERITIES = {s.value for s in Severity}
REQUIRED_KEYS = {"symbol", "signal", "severity", "summary", "metrics"}


def _well_formed(findings: list[dict]) -> bool:
    for f in findings:
        assert REQUIRED_KEYS <= set(f), f"missing keys in {f}"
        assert f["severity"] in VALID_SEVERITIES
        assert isinstance(f["metrics"], dict)
    return True


# --- empty input contract --------------------------------------------------
@pytest.mark.parametrize("fn", [
    scan_fno_ban, scan_delivery_collapse, scan_block_deals,
    scan_mtf_surge, scan_slbm_spike, get_pledge_disclosures,
])
def test_empty_symbols_returns_empty(fn):
    assert fn([]) == []
    assert fn(["", "  "]) == []


# --- F&O ban ---------------------------------------------------------------
def test_fno_ban_flags_currently_banned_symbol():
    banned = query(
        """
        SELECT DISTINCT ON (symbol) symbol FROM scanx_fo_ban
        WHERE in_ban = true ORDER BY symbol, effective_date DESC LIMIT 3
        """
    )
    if not banned:
        pytest.skip("no symbols currently in F&O ban")
    syms = [r["symbol"] for r in banned]
    out = scan_fno_ban(syms)
    _well_formed(out)
    flagged = {f["symbol"] for f in out if f["severity"] == Severity.ALERT.value}
    assert set(syms) & flagged, "expected at least one banned symbol flagged ALERT"


# --- block sells -----------------------------------------------------------
def test_block_deals_flags_recent_large_sell():
    big = query(
        """
        SELECT symbol FROM scanx_deals
        WHERE upper(buy_sell) LIKE 'S%%'
          AND deal_date >= CURRENT_DATE - 7
        ORDER BY quantity * price DESC LIMIT 3
        """
    )
    if not big:
        pytest.skip("no recent large block sells")
    syms = [r["symbol"] for r in big]
    out = scan_block_deals(syms)
    _well_formed(out)
    assert out, "expected at least one block-sell finding"
    assert any(f["metrics"].get("counterparty") for f in out)


# --- pledge disclosures ----------------------------------------------------
def test_pledge_disclosures_returns_text():
    rows = query(
        """
        SELECT st.nse_symbol AS symbol
        FROM scanx_ssr_data s JOIN stocks st ON st.id = s.stock_id
        WHERE s.section IN ('lodr','news') AND s.data::text ILIKE '%%pledg%%'
          AND s.fetched_at >= now() - interval '120 days'
          AND st.nse_symbol IS NOT NULL
        LIMIT 3
        """
    )
    if not rows:
        pytest.skip("no recent pledge disclosures")
    syms = [r["symbol"] for r in rows]
    out = get_pledge_disclosures(syms)
    _well_formed(out)
    assert out and all(f["metrics"].get("text") for f in out)


# --- structural contracts for ratio-based detectors -----------------------
@pytest.mark.parametrize("fn", [scan_delivery_collapse, scan_mtf_surge, scan_slbm_spike])
def test_ratio_detectors_well_formed(fn):
    # Use a broad liquid basket; assert structure regardless of whether it fires.
    out = fn(["RELIANCE", "TCS", "HDFCBANK", "INFY", "ADANIENT", "SBIN"])
    _well_formed(out)


# --- aggregator ------------------------------------------------------------
def test_scan_portfolio_aggregates_and_counts():
    res = scan_portfolio(["ADANIENT", "ADANIGREEN", "RELIANCE", "JPPOWER"])
    assert set(res) == {"scanned_symbols", "counts", "findings", "by_symbol"}
    _well_formed(res["findings"])
    # counts must equal the number of alert/watch findings
    alerts = sum(1 for f in res["findings"] if f["severity"] == "alert")
    watches = sum(1 for f in res["findings"] if f["severity"] == "watch")
    assert res["counts"]["alert"] == alerts
    assert res["counts"]["watch"] == watches
    # by_symbol grouping is consistent
    assert sum(len(v) for v in res["by_symbol"].values()) == len(res["findings"])
