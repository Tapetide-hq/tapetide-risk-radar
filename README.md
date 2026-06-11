<div align="center">

# 🛰️ Tapetide Smart-Money Risk Radar

**An autonomous multi-agent system that reads the institutional money trail and flags portfolio risk _before_ the crash.**

Built for the **Google for Startups AI Agents Challenge** · Track 1 (Build)

[**▶ Live demo — radar.tapetide.com**](https://radar.tapetide.com) · Gemini · ADK · Cloud Run

</div>

---

## The problem

Indian retail investors lose money even in rising markets — not from picking bad
companies, but from missing the **institutional money trail**: promoters quietly
pledging shares, large counterparties dumping stock via block deals, leverage
piling up, stocks slipping toward F&O bans. These signals exist but are
scattered, unstructured, and invisible to most investors until the stock has
already fallen 20%.

## The solution

Hand the Risk Radar a portfolio. A team of AI agents pulls the smart-money
signals, grounds the *“why”* with live search, synthesizes a single
**cross-signal risk verdict** per stock, and writes durable alerts — autonomously,
twice a day, and on demand.

> **SEBI-aware by design:** the system surfaces *data and evidence* about
> institutional activity. It is not investment advice and gives no buy/sell calls.

## How it works — a 4-agent pipeline

```
Cloud Scheduler ─┐ (08:15 & 17:00 IST)
  on-demand UI  ─┤
                 ▼
            Cloud Run · ADK multi-agent app  (in-process A2A)
   ┌────────────────────────────────────────────────────────────┐
   │  Monitor ─►  Catalyst ─►  Analyst ─►  Action                 │
   └────────────────────────────────────────────────────────────┘
        │            │            │            │
   data-provider  Google      Gemini       Firestore
       API        Search    (structured)   + BigQuery
```

| Agent | Role |
|-------|------|
| **Monitor** | Pulls 6 institutional-flow signals for the portfolio from the data-provider API. |
| **Catalyst** | Gemini + **built-in Google Search grounding** — finds *why* a flagged stock is moving. |
| **Analyst** | Gemini constrained by an `output_schema` → a structured `PortfolioRiskAssessment`; **parses raw promoter-pledge disclosure text into concrete events**. |
| **Action** | Writes the risk register to **Firestore** (durable alerts) and mirrors to **BigQuery** (analytics). |

**Signals analyzed:** F&O ban / MWPL · delivery-% collapse · large block-sells (with counterparty) · MTF leverage surge · SLBM short-demand spike · promoter-pledge disclosures.

## Google Cloud stack

**Vertex AI (Gemini 2.5 Flash)** · **Google Search grounding** · **Cloud Run** ·
**Cloud Scheduler** · **Firestore** · **BigQuery** · **Secret Manager** ·
Cloud Build · Artifact Registry · **Agent Development Kit (ADK)** · A2A orchestration.

The market data is consumed from an **external, API-key-authenticated market data
provider** (`DATA_PROVIDER_BASE_URL`) covering ~8,200 NSE/BSE stocks. No database
credentials live in this app.

## Live demo

| | URL |
|---|---|
| **App / demo UI** | https://radar.tapetide.com |
| **Health** | https://radar.tapetide.com/health |

Open the UI, enter a portfolio (or pick a preset), and hit **Run Risk Scan** to
watch the agent pipeline produce a live verdict.

## API

| Method | Route | Body | Purpose |
|---|---|---|---|
| `GET`  | `/` | — | demo dashboard UI |
| `GET`  | `/health` | — | liveness |
| `POST` | `/scan` | `{ "user_id", "symbols": [...] }` | on-demand pipeline run |
| `POST` | `/scheduled` | — | Cloud Scheduler target (08:15 / 17:00 IST) |
| `GET`  | `/risk-register/{user}` | — | read today's written alerts |

```bash
curl -X POST https://radar.tapetide.com/scan \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["ADANIENT","ADANIGREEN","RELIANCE","JPPOWER","RAYMOND"]}'
```

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # set DATA_PROVIDER_API_KEY, GOOGLE_CLOUD_PROJECT, ...
gcloud auth application-default login
.venv/bin/uvicorn app.main:app --port 8080   # http://localhost:8080
```

## Deploy (Cloud Run)

```bash
gcloud run deploy risk-radar --source . --region us-central1 \
  --set-env-vars "DATA_PROVIDER_BASE_URL=...,GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=...,GOOGLE_CLOUD_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash,FIRESTORE_DATABASE=(default),BQ_DATASET=risk_radar,BQ_TABLE=risk_register" \
  --set-secrets "DATA_PROVIDER_API_KEY=data-provider-api-key:latest"
```

Runtime service account roles: `aiplatform.user`, `datastore.user`,
`bigquery.dataEditor`, `bigquery.jobUser`, `secretmanager.secretAccessor`.

## Project layout

```
risk_agent/        ADK app — agents, pipeline, Firestore+BigQuery store, data-provider client
  agents.py        Catalyst (grounded) + Analyst (structured) Gemini agents
  pipeline.py      Monitor → Catalyst → Analyst → Action orchestration (A2A)
  schemas.py       PortfolioRiskAssessment structured-output schema
  store.py         Firestore risk register + BigQuery mirror
app/               FastAPI entrypoint + demo UI (app/static)
docs/              architecture.svg
risk_radar/+tests/ local signal-computation prototype (reference)
```

## Disclaimer

For research and informational purposes only. Not investment advice. Signals
describe institutional activity; they are not buy/sell recommendations.
