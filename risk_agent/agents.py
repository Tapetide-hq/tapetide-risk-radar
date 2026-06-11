"""ADK agents: the Catalyst scout (grounded) and the Risk Analyst (structured).

Two distinct Gemini agents:
  - catalyst_agent: uses built-in Google Search grounding to find *why* a flagged
    stock is moving. (Grounding tools can't be mixed with output_schema, so it's
    its own agent.)
  - analyst_agent: constrained by `output_schema` to emit a PortfolioRiskAssessment,
    so the downstream Action writer can never break on malformed JSON.

A small async helper runs an agent once and returns its final text.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.genai import types

from . import settings
from .schemas import PortfolioRiskAssessment

_APP = "risk_radar"

catalyst_agent = LlmAgent(
    name="catalyst_scout",
    model=settings.GEMINI_MODEL,
    instruction=(
        "You research WHY Indian (NSE) stocks are moving. Given a list of symbols, "
        "use Google Search to find the most likely recent catalyst for each — "
        "news, results, regulatory action, promoter/ownership events, sector moves. "
        "Reply with one short line per symbol: 'SYMBOL: <catalyst or \"no clear catalyst\">'. "
        "Be factual and concise; do not give investment advice."
    ),
    tools=[google_search],
)

analyst_agent = LlmAgent(
    name="risk_analyst",
    model=settings.GEMINI_MODEL,
    instruction=(
        "You are a risk analyst for Indian equities. You receive (1) institutional "
        "smart-money risk findings for a portfolio and (2) optional catalyst notes. "
        "For every stock that has any non-trivial finding, write a cross-signal "
        "thesis explaining the risk by connecting the signals (e.g. a delivery "
        "collapse alongside a large counterparty block-sell and a fresh promoter "
        "pledge suggests distribution). Parse any pledge-disclosure TEXT into a "
        "concrete event in your thesis. Assign a 0-100 risk_score and a risk_level. "
        "Set recommended_review=true when the holder should look now. "
        "This is data and evidence for the user's own research — NEVER phrase it as "
        "advice, a recommendation, or a price target (SEBI-compliant)."
    ),
    output_schema=PortfolioRiskAssessment,
    output_key="assessment",
)


async def run_agent(agent: LlmAgent, prompt: str) -> str:
    """Run an agent once with a single user message; return its final text."""
    runner = InMemoryRunner(agent=agent, app_name=_APP)
    session = await runner.session_service.create_session(app_name=_APP, user_id="pipeline")
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final = ""
    async for event in runner.run_async(
        user_id="pipeline", session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final = event.content.parts[0].text or final
    return final
