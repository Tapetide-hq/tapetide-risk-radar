"""Runtime configuration, sourced from environment (Secret Manager in prod)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# --- Tapetide risk API (the Cloudflare Worker = external data source) -------
WORKER_BASE_URL: str = _get("WORKER_BASE_URL", "https://ow-apis.tapetide.com")
WORKER_API_KEY: str = _get("WORKER_API_KEY")
WORKER_TIMEOUT_S: float = float(_get("WORKER_TIMEOUT_S", "45"))

# --- Vertex AI / Gemini -----------------------------------------------------
# ADK reads these; set GOOGLE_GENAI_USE_VERTEXAI=TRUE to use Vertex (not API key).
GCP_PROJECT: str = _get("GOOGLE_CLOUD_PROJECT")
GCP_LOCATION: str = _get("GOOGLE_CLOUD_LOCATION", "us-central1")
USE_VERTEX: bool = _get("GOOGLE_GENAI_USE_VERTEXAI", "TRUE").upper() == "TRUE"
GEMINI_MODEL: str = _get("GEMINI_MODEL", "gemini-2.5-flash")

# --- Firestore --------------------------------------------------------------
FIRESTORE_DATABASE: str = _get("FIRESTORE_DATABASE", "(default)")
RISK_REGISTER_COLLECTION: str = _get("RISK_REGISTER_COLLECTION", "risk_register")
SCAN_HISTORY_COLLECTION: str = _get("SCAN_HISTORY_COLLECTION", "scan_history")
PORTFOLIO_COLLECTION: str = _get("PORTFOLIO_COLLECTION", "portfolios")
