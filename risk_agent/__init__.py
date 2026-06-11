"""Tapetide Smart-Money Risk Radar — ADK multi-agent application.

A Monitor -> Analyst -> Action agent pipeline that scans a stock portfolio for
institutional-flow risk signals (via the Tapetide risk API), has Gemini
synthesize a cross-signal risk narrative, and writes alerts to Firestore.
"""
