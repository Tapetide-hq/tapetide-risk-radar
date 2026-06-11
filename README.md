# Tapetide Smart-Money Risk Radar

An autonomous **multi-agent system** that monitors a stock portfolio for
institutional-flow risk and pushes alerts *before* a crash. Built for the
Google for Startups AI Agents Challenge (Track 1).

Given a portfolio, the system pulls smart-money risk signals, has Gemini
synthesize a cross-signal risk narrative, and writes durable alerts to a risk
register — on a schedule and on demand.

## Architecture (Google Cloud native)

```
Cloud Scheduler ─┐
   (08:15/17:00) │
                 ▼
            Cloud Run (ADK app)
            ┌──────────────────────────────────────────────┐
            │ Monitor ──A2A──► Catalyst ──A2A──► Analyst ──► Action │
            └──────────────────────────────────────────────┘
              │ tools          │ Google Search  │ Gemini      │ Firestore
              ▼                │ grounding       │ structured  ▼
   Tapetide Risk API          ▼                 ▼          risk_register
   (Cloudflare Worker)      Vertex AI Gemini 2.5 Flash      scan_history
```

- **Monitor** — calls the Tapetide Risk API for institutional-flow findings.
- **Catalyst** — Gemini + built-in Google Search grounding: *why* is a stock moving.
- **Analyst** — Gemini with a strict `output_schema`, producing a structured
  `PortfolioRiskAssessment` (parses raw pledge-disclosure text into events).
- **Action** — writes the risk register to Firestore (the tangible alert).

**GCP services:** Vertex AI (Gemini) · Cloud Run · Firestore · Secret Manager ·
Cloud Build · Artifact Registry · Cloud Scheduler · Google Search grounding.

The market data is consumed from the **Tapetide Risk API** — a separate,
API-key-authenticated service. No database credentials live in this app.

## API

| Method | Route | Body | Purpose |
|---|---|---|---|
| `GET`  | `/health` | — | liveness |
| `POST` | `/scan` | `{ "user_id", "symbols": [...] }` | on-demand pipeline run |
| `POST` | `/scheduled` | — | Cloud Scheduler target |
| `GET`  | `/risk-register/{user}` | — | read today's written alerts |

```bash
curl -X POST <service-url>/scan -H 'Content-Type: application/json' \
  -d '{"symbols":["ADANIENT","RELIANCE","RAYMOND"]}'
```

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # set WORKER_API_KEY, GOOGLE_CLOUD_PROJECT, ...
gcloud auth application-default login
.venv/bin/uvicorn app.main:app --port 8080
```

## Deploy (Cloud Run)

```bash
gcloud run deploy risk-radar --source . --region us-central1 \
  --set-env-vars "WORKER_BASE_URL=...,GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=...,GOOGLE_CLOUD_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash,FIRESTORE_DATABASE=(default)" \
  --set-secrets "WORKER_API_KEY=worker-api-key:latest"
```

The runtime service account needs: `roles/aiplatform.user`, `roles/datastore.user`,
`roles/secretmanager.secretAccessor`.

## Layout

- `risk_agent/` — the deployed ADK app (agents, pipeline, Firestore store, Worker client).
- `app/` — FastAPI entrypoint for Cloud Run.
- `risk_radar/` + `tests/` — the signal-SQL validation prototype (reference; the
  production signal logic now lives in the Tapetide Risk API service).

## Stack

Python · Google ADK · Vertex AI Gemini · FastAPI · Firestore · Cloud Run.
