"""Smart-Money Risk Radar — deterministic signal detectors.

Each public function takes a list of NSE symbols and returns a list of findings:
    {symbol, signal, severity, metrics{...}, summary}
Severity is computed here from hard thresholds (config.py); the agent layer adds
judgment + cross-signal narrative. All queries are batched (one round-trip per
signal) and read-only.
"""

from __future__ import annotations

from typing import Any

from . import config as C
from .config import Severity
from .db import query


def _norm(symbols: list[str]) -> list[str]:
    return [s.strip().upper() for s in symbols if s and s.strip()]


def _f(value: Any) -> float | None:
    return float(value) if value is not None else None


def _finding(symbol: str, signal: str, severity: Severity, summary: str,
             **metrics: Any) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "signal": signal,
        "severity": severity.value,
        "summary": summary,
        "metrics": metrics,
    }


# --------------------------------------------------------------------------
# 1. F&O ban / MWPL approaching
# --------------------------------------------------------------------------
def scan_fno_ban(symbols: list[str]) -> list[dict[str, Any]]:
    """Flag holdings in (or approaching) the F&O ban list via MWPL utilisation."""
    syms = _norm(symbols)
    if not syms:
        return []
    rows = query(
        """
        SELECT DISTINCT ON (symbol)
               symbol, in_ban, mwpl_percent, effective_date
        FROM scanx_fo_ban
        WHERE symbol = ANY(%s)
        ORDER BY symbol, effective_date DESC
        """,
        (syms,),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        mwpl = _f(r["mwpl_percent"]) or 0.0
        in_ban = bool(r["in_ban"])
        if in_ban or mwpl >= C.MWPL_ALERT_PCT:
            sev = Severity.ALERT
            msg = ("Already in F&O ban" if in_ban
                   else f"MWPL at {mwpl:.0f}% — ban triggers at 95%")
        elif mwpl >= C.MWPL_WATCH_PCT:
            sev, msg = Severity.WATCH, f"MWPL building at {mwpl:.0f}%"
        else:
            continue
        out.append(_finding(r["symbol"], "fno_ban", sev, msg,
                            in_ban=in_ban, mwpl_percent=mwpl,
                            effective_date=str(r["effective_date"])))
    return out


# --------------------------------------------------------------------------
# 2. Delivery % collapse (distribution signal: delivery down + volume up)
# --------------------------------------------------------------------------
def scan_delivery_collapse(symbols: list[str]) -> list[dict[str, Any]]:
    """Flag a drop in delivery%% vs its 20d average, confirmed by rising volume."""
    syms = _norm(symbols)
    if not syms:
        return []
    rows = query(
        """
        WITH d AS (
            SELECT symbol, trade_date, delivery_percent, traded_qty,
                   row_number() OVER w AS rn,
                   avg(delivery_percent) OVER w_prior AS avg20_deliv,
                   avg(traded_qty)       OVER w_prior AS avg20_vol
            FROM scanx_deliveries
            WHERE symbol = ANY(%s)
            WINDOW w AS (PARTITION BY symbol ORDER BY trade_date DESC),
                   w_prior AS (PARTITION BY symbol ORDER BY trade_date DESC
                               ROWS BETWEEN 1 FOLLOWING AND %s FOLLOWING)
        )
        SELECT symbol, trade_date, delivery_percent, avg20_deliv,
               traded_qty, avg20_vol
        FROM d WHERE rn = 1
        """,
        (syms, C.BASELINE_WINDOW),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        today = _f(r["delivery_percent"])
        avg = _f(r["avg20_deliv"])
        vol = _f(r["traded_qty"]) or 0.0
        avg_vol = _f(r["avg20_vol"]) or 0.0
        if not today or not avg or avg == 0:
            continue
        drop = 1.0 - (today / avg)
        vol_up = avg_vol > 0 and vol >= avg_vol * C.VOLUME_CONFIRM_RATIO
        if drop >= C.DELIVERY_ALERT_DROP and vol_up:
            sev = Severity.ALERT
            msg = (f"Delivery {today:.0f}% vs {avg:.0f}% avg "
                   f"(-{drop*100:.0f}%) on rising volume — distribution risk")
        elif drop >= C.DELIVERY_WATCH_DROP:
            sev = Severity.WATCH
            msg = f"Delivery softening: {today:.0f}% vs {avg:.0f}% avg"
        else:
            continue
        out.append(_finding(r["symbol"], "delivery_collapse", sev, msg,
                            delivery_percent=today, avg20_delivery=round(avg, 2),
                            drop_pct=round(drop * 100, 1),
                            volume_vs_avg=round(vol / avg_vol, 2) if avg_vol else None,
                            trade_date=str(r["trade_date"])))
    return out


# --------------------------------------------------------------------------
# 3. Large block / bulk sells (scaled by 20d turnover, with counterparty)
# --------------------------------------------------------------------------
def scan_block_deals(symbols: list[str]) -> list[dict[str, Any]]:
    """Surface recent large SELL block/bulk deals, scaled vs 20d avg turnover."""
    syms = _norm(symbols)
    if not syms:
        return []
    rows = query(
        """
        WITH ids AS (
            SELECT id FROM stocks WHERE nse_symbol = ANY(%s)
        ),
        turnover AS (
            SELECT stock_id, avg(close * volume) AS avg20_turnover
            FROM (
                SELECT o.stock_id, o.close, o.volume,
                       row_number() OVER (PARTITION BY o.stock_id
                                          ORDER BY o.date DESC) AS rn
                FROM daily_ohlcv o
                WHERE o.stock_id IN (SELECT id FROM ids)
                  AND o.date >= (CURRENT_DATE - INTERVAL '60 days')
            ) z
            WHERE rn <= %s
            GROUP BY stock_id
        )
        SELECT d.symbol, d.deal_type, d.buy_sell, d.client_name,
               d.quantity, d.price, d.deal_date,
               (d.quantity * d.price) AS value,
               t.avg20_turnover
        FROM scanx_deals d
        LEFT JOIN turnover t ON t.stock_id = d.stock_id
        WHERE d.symbol = ANY(%s)
          AND d.deal_date >= (CURRENT_DATE - (%s || ' days')::interval)
          AND upper(d.buy_sell) LIKE 'S%%'
        ORDER BY value DESC
        """,
        (syms, C.BASELINE_WINDOW, syms, C.BLOCK_LOOKBACK_DAYS),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        value = _f(r["value"]) or 0.0
        turnover = _f(r["avg20_turnover"])
        if value < C.BLOCK_MIN_VALUE_INR:
            continue
        ratio = (value / turnover) if turnover else None
        if ratio is not None and ratio >= C.BLOCK_ALERT_TURNOVER_RATIO:
            sev = Severity.ALERT
        elif ratio is not None and ratio >= C.BLOCK_WATCH_TURNOVER_RATIO:
            sev = Severity.WATCH
        elif ratio is None and value >= C.BLOCK_MIN_VALUE_INR * 4:
            sev = Severity.WATCH  # no turnover baseline; only very large
        else:
            continue
        cr = value / 1e7
        msg = (f"{r['client_name'] or 'Unknown'} SOLD ₹{cr:.1f}cr "
               f"({r['deal_type']})")
        if ratio:
            msg += f" — {ratio*100:.0f}% of avg daily turnover"
        out.append(_finding(r["symbol"], "block_sell", sev, msg,
                            counterparty=r["client_name"], deal_type=r["deal_type"],
                            value_inr=value, value_cr=round(cr, 2),
                            quantity=int(r["quantity"]), price=_f(r["price"]),
                            turnover_ratio=round(ratio, 3) if ratio else None,
                            deal_date=str(r["deal_date"])))
    return out


# --------------------------------------------------------------------------
# 4. MTF leverage surge
# --------------------------------------------------------------------------
def scan_mtf_surge(symbols: list[str]) -> list[dict[str, Any]]:
    """Flag a surge in margin-funded (MTF) value vs its 20d average."""
    syms = _norm(symbols)
    if not syms:
        return []
    rows = query(
        """
        WITH m AS (
            SELECT symbol, collection_date, mtf_value, mtf_quantity,
                   row_number() OVER w AS rn,
                   avg(mtf_value) OVER w_prior AS avg20
            FROM scanx_mtf
            WHERE symbol = ANY(%s)
            WINDOW w AS (PARTITION BY symbol ORDER BY collection_date DESC),
                   w_prior AS (PARTITION BY symbol ORDER BY collection_date DESC
                               ROWS BETWEEN 1 FOLLOWING AND %s FOLLOWING)
        )
        SELECT symbol, collection_date, mtf_value, avg20 FROM m WHERE rn = 1
        """,
        (syms, C.BASELINE_WINDOW),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        val = _f(r["mtf_value"]) or 0.0
        avg = _f(r["avg20"])
        if not avg or avg == 0:
            continue
        ratio = val / avg
        if ratio >= C.MTF_ALERT_RATIO:
            sev = Severity.ALERT
        elif ratio >= C.MTF_WATCH_RATIO:
            sev = Severity.WATCH
        else:
            continue
        out.append(_finding(r["symbol"], "mtf_surge", sev,
                            f"MTF leverage {ratio:.1f}x its 20d average — "
                            f"crowded long, higher unwind risk",
                            mtf_value=val, avg20_mtf=round(avg, 2),
                            ratio=round(ratio, 2),
                            collection_date=str(r["collection_date"])))
    return out


# --------------------------------------------------------------------------
# 5. SLBM short-demand spike
# --------------------------------------------------------------------------
def scan_slbm_spike(symbols: list[str]) -> list[dict[str, Any]]:
    """Flag a spike in stock-lending fee rate (proxy for short demand)."""
    syms = _norm(symbols)
    if not syms:
        return []
    rows = query(
        """
        WITH s AS (
            SELECT symbol, collection_date, lending_fee_rate, quantity_available,
                   row_number() OVER w AS rn,
                   avg(lending_fee_rate) OVER w_prior AS avg20
            FROM scanx_slbm
            WHERE symbol = ANY(%s)
            WINDOW w AS (PARTITION BY symbol ORDER BY collection_date DESC),
                   w_prior AS (PARTITION BY symbol ORDER BY collection_date DESC
                               ROWS BETWEEN 1 FOLLOWING AND %s FOLLOWING)
        )
        SELECT symbol, collection_date, lending_fee_rate, avg20 FROM s WHERE rn = 1
        """,
        (syms, C.BASELINE_WINDOW),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        fee = _f(r["lending_fee_rate"]) or 0.0
        avg = _f(r["avg20"])
        if not avg or avg == 0:
            continue
        ratio = fee / avg
        if ratio >= C.SLBM_ALERT_RATIO:
            sev = Severity.ALERT
        elif ratio >= C.SLBM_WATCH_RATIO:
            sev = Severity.WATCH
        else:
            continue
        out.append(_finding(r["symbol"], "slbm_spike", sev,
                            f"Stock-lending fee {ratio:.1f}x its 20d average — "
                            f"short-sell demand rising",
                            lending_fee_rate=fee, avg20_fee=round(avg, 3),
                            ratio=round(ratio, 2),
                            collection_date=str(r["collection_date"])))
    return out


# --------------------------------------------------------------------------
# 6. Promoter pledge disclosures (unstructured — for the LLM to parse)
# --------------------------------------------------------------------------
def get_pledge_disclosures(symbols: list[str]) -> list[dict[str, Any]]:
    """Return recent pledge-related disclosure TEXT for the agent to interpret.

    No structured pledge %% exists in the DB, so we surface raw LODR/news text
    mentioning pledges; the Gemini agent extracts the event, direction and size.
    """
    syms = _norm(symbols)
    if not syms:
        return []
    # Pledge rows in scanx_ssr_data carry stock_id (not symbol), so resolve
    # symbols through the stocks master (stocks.nse_symbol -> stocks.id).
    rows = query(
        """
        SELECT st.nse_symbol AS symbol, s.section, s.fetched_at,
               substring(s.data::text from '.{0,80}[Pp]ledg.{0,240}') AS snippet
        FROM scanx_ssr_data s
        JOIN stocks st ON st.id = s.stock_id
        WHERE st.nse_symbol = ANY(%s)
          AND s.section IN ('lodr', 'news')
          AND s.data::text ILIKE '%%pledg%%'
          AND s.fetched_at >= (now() - (%s || ' days')::interval)
        ORDER BY s.fetched_at DESC
        LIMIT %s
        """,
        (syms, C.PLEDGE_LOOKBACK_DAYS, C.PLEDGE_MAX_SNIPPETS * len(syms)),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        snippet = (r["snippet"] or "").replace("\n", " ").strip()
        if not snippet:
            continue
        out.append(_finding(r["symbol"], "pledge_disclosure", Severity.WATCH,
                            "Pledge-related disclosure found — needs LLM review",
                            source=r["section"], text=snippet,
                            disclosed_at=str(r["fetched_at"])))
    return out


# --------------------------------------------------------------------------
# Aggregator — one call the Monitor agent can use to scan a whole portfolio
# --------------------------------------------------------------------------
_DETECTORS = (
    scan_fno_ban,
    scan_delivery_collapse,
    scan_block_deals,
    scan_mtf_surge,
    scan_slbm_spike,
    get_pledge_disclosures,
)


def scan_portfolio(symbols: list[str]) -> dict[str, Any]:
    """Run all detectors over a portfolio and return grouped findings.

    Returns {findings: [...], by_symbol: {sym: [...]}, counts: {alert, watch}}.
    """
    syms = _norm(symbols)
    findings: list[dict[str, Any]] = []
    for detector in _DETECTORS:
        findings.extend(detector(syms))

    by_symbol: dict[str, list[dict[str, Any]]] = {}
    counts = {"alert": 0, "watch": 0}
    for f in findings:
        by_symbol.setdefault(f["symbol"], []).append(f)
        if f["severity"] in counts:
            counts[f["severity"]] += 1
    return {
        "scanned_symbols": syms,
        "counts": counts,
        "findings": findings,
        "by_symbol": by_symbol,
    }
