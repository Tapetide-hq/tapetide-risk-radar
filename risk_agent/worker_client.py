"""HTTP client for the Tapetide risk API (the Cloudflare Worker).

This is the agent's view of the data: a third-party API behind an API key.
No database credentials live here — only the Worker URL + key.
"""

from __future__ import annotations

from typing import Any

import httpx

from . import settings


class RiskAPIError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.WORKER_API_KEY:
        raise RiskAPIError("WORKER_API_KEY is not set")
    return {
        "Authorization": f"Bearer {settings.WORKER_API_KEY}",
        "Content-Type": "application/json",
    }


def scan_portfolio(symbols: list[str]) -> dict[str, Any]:
    """Run all risk detectors over a portfolio.

    Args:
        symbols: NSE stock symbols, e.g. ["ADANIENT", "RELIANCE"].

    Returns:
        {scanned_symbols, counts:{alert,watch}, findings:[...], by_symbol:{...}}
    """
    url = f"{settings.WORKER_BASE_URL}/v1/scan"
    with httpx.Client(timeout=settings.WORKER_TIMEOUT_S) as client:
        resp = client.post(url, headers=_headers(), json={"symbols": symbols})
    if resp.status_code != 200:
        raise RiskAPIError(f"scan failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def scan_signal(name: str, symbols: list[str]) -> dict[str, Any]:
    """Run a single named detector (fno_ban, block_sell, ...) over symbols."""
    url = f"{settings.WORKER_BASE_URL}/v1/signals/{name}"
    with httpx.Client(timeout=settings.WORKER_TIMEOUT_S) as client:
        resp = client.post(url, headers=_headers(), json={"symbols": symbols})
    if resp.status_code != 200:
        raise RiskAPIError(f"signal {name} failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()
