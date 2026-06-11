"""Signal thresholds and severity levels.

Centralized so the agent layer (or a judge during the demo) can tune detection
without touching query logic. Values calibrated for the Indian market after a
Gemini review: thresholds avoid both alert-fatigue (everything red) and
silence (nothing fires) on a realistic portfolio.
"""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    NONE = "none"
    WATCH = "watch"
    ALERT = "alert"


# Trailing window (trading days) for baselines used in z-score / ratio checks.
BASELINE_WINDOW = 20

# --- F&O ban / MWPL --------------------------------------------------------
# Ban triggers at 95% MWPL; we warn earlier.
MWPL_ALERT_PCT = 90.0
MWPL_WATCH_PCT = 80.0

# --- Delivery % collapse ---------------------------------------------------
# A genuine distribution signal needs delivery DROPPING while volume RISES.
DELIVERY_ALERT_DROP = 0.40   # today < (1-0.40) * 20d avg delivery%
DELIVERY_WATCH_DROP = 0.25
VOLUME_CONFIRM_RATIO = 1.0   # today volume must exceed 20d avg to confirm

# --- Block / bulk deals ----------------------------------------------------
# Flat rupee floor is noise for large caps; we scale by traded turnover.
BLOCK_LOOKBACK_DAYS = 7
BLOCK_MIN_VALUE_INR = 50_000_000          # 5 cr absolute floor (regulatory min)
BLOCK_ALERT_TURNOVER_RATIO = 0.30         # deal value >= 30% of 20d avg turnover
BLOCK_WATCH_TURNOVER_RATIO = 0.10

# --- MTF leverage surge ----------------------------------------------------
MTF_ALERT_RATIO = 1.50       # today MTF value >= 1.5x 20d avg
MTF_WATCH_RATIO = 1.25

# --- SLBM short-demand spike ----------------------------------------------
SLBM_ALERT_RATIO = 2.00      # lending fee rate >= 2x 20d avg
SLBM_WATCH_RATIO = 1.50

# --- Pledge disclosures ----------------------------------------------------
PLEDGE_LOOKBACK_DAYS = 120   # how far back to surface disclosure text
PLEDGE_MAX_SNIPPETS = 5
