"""Tapetide Smart-Money Risk Radar — signal-detection tool layer.

Deterministic, read-only signal detectors over the Tapetide market database.
The math lives here (reliable); a Gemini/ADK agent layer consumes these as
tools and supplies judgment + narrative on top.
"""

from .tools import (
    scan_fno_ban,
    scan_delivery_collapse,
    scan_block_deals,
    scan_mtf_surge,
    scan_slbm_spike,
    get_pledge_disclosures,
    scan_portfolio,
)

__all__ = [
    "scan_fno_ban",
    "scan_delivery_collapse",
    "scan_block_deals",
    "scan_mtf_surge",
    "scan_slbm_spike",
    "get_pledge_disclosures",
    "scan_portfolio",
]
