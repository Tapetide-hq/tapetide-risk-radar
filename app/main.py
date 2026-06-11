"""Cloud Run entrypoint for the Risk Radar agent.

Routes:
  GET  /health                 liveness
  POST /scan        {symbols}   on-demand pipeline run (the demo "Scan now")
  POST /scheduled               Cloud Scheduler target (08:15 & 17:00 IST)
  GET  /risk-register/{user}    read back the latest written alerts
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from risk_agent import settings, store
from risk_agent.pipeline import run_risk_radar

app = FastAPI(title="Tapetide Smart-Money Risk Radar")

_STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# Demo fallback portfolio when no stored portfolios exist yet.
DEFAULT_WATCHLIST = ["ADANIENT", "ADANIGREEN", "RELIANCE", "JPPOWER", "RAYMOND"]


class ScanRequest(BaseModel):
    user_id: str = "demo"
    symbols: list[str] = Field(min_length=1, max_length=100)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(os.path.join(_STATIC, "index.html"))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "risk-radar-agent", "model": settings.GEMINI_MODEL}


@app.post("/scan")
async def scan(req: ScanRequest) -> dict:
    return await run_risk_radar(req.user_id, req.symbols)


@app.post("/scheduled")
async def scheduled() -> dict:
    """Invoked by Cloud Scheduler. Scans every stored portfolio (demo fallback)."""
    results = [await run_risk_radar("demo", DEFAULT_WATCHLIST)]
    return {"ran": len(results), "results": results}


@app.get("/risk-register/{user_id}")
def risk_register(user_id: str) -> dict:
    db = store._db()  # read-only convenience for the demo UI
    docs = (
        db.collection(settings.RISK_REGISTER_COLLECTION)
        .where("user_id", "==", user_id)
        .where("trade_date", "==", store._today())
        .stream()
    )
    return {"user_id": user_id, "entries": [d.to_dict() for d in docs]}
