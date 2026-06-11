"""HTTP client for the market data provider API.

To this agent, the data is an external, API-key-authenticated provider. No
database credentials live here — only the provider's base URL and API key.
"""

from __future__ import annotations

from typing import Any

import httpx

from . import settings


class DataProviderError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.DATA_PROVIDER_API_KEY:
        raise DataProviderError("DATA_PROVIDER_API_KEY is not set")
    return {
        "Authorization": f"Bearer {settings.DATA_PROVIDER_API_KEY}",
        "Content-Type": "application/json",
    }


def scan_portfolio(symbols: list[str]) -> dict[str, Any]:
    """Run all risk detectors over a portfolio.

    Args:
        symbols: NSE stock symbols, e.g. ["ADANIENT", "RELIANCE"].

    Returns:
        {scanned_symbols, counts:{alert,watch}, findings:[...], by_symbol:{...}}
    """
    url = f"{settings.DATA_PROVIDER_BASE_URL}/v1/scan"
    with httpx.Client(timeout=settings.DATA_PROVIDER_TIMEOUT_S) as client:
        resp = client.post(url, headers=_headers(), json={"symbols": symbols})
    if resp.status_code != 200:
        raise DataProviderError(f"scan failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def scan_signal(name: str, symbols: list[str]) -> dict[str, Any]:
    """Run a single named detector (fno_ban, block_sell, ...) over symbols."""
    url = f"{settings.DATA_PROVIDER_BASE_URL}/v1/signals/{name}"
    with httpx.Client(timeout=settings.DATA_PROVIDER_TIMEOUT_S) as client:
        resp = client.post(url, headers=_headers(), json={"symbols": symbols})
    if resp.status_code != 200:
        raise DataProviderError(f"signal {name} failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()
