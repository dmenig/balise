"""The SQL half of the honesty rule (docs/06).

`derive_status` decides what we *know*; this decides what a read query is allowed to *show*.
Both must agree, which is why the thresholds live in one place and are asserted by tests.
"""

from __future__ import annotations

MIN_DISPLAY_CONFIDENCE = 0.3
MIN_FREE_CONFIDENCE = 0.4
FREE_HARD_EXPIRY = "6 hours"
OCCUPIED_HARD_EXPIRY = "24 hours"

#: Collapses everything ambiguous to 'unknown'. There is no fifth state.
DISPLAY_STATE_SQL = f"""
CASE
  WHEN st.state IS NULL THEN 'unknown'
  WHEN st.confidence < {MIN_DISPLAY_CONFIDENCE} THEN 'unknown'
  WHEN st.state = 'free' AND st.confidence < {MIN_FREE_CONFIDENCE} THEN 'unknown'
  WHEN st.state = 'free' AND st.as_of < now() - interval '{FREE_HARD_EXPIRY}' THEN 'unknown'
  WHEN st.as_of < now() - interval '{OCCUPIED_HARD_EXPIRY}' THEN 'unknown'
  ELSE st.state::text
END
"""

DISPLAY_CONFIDENCE_SQL = f"""
CASE
  WHEN st.state IS NULL THEN 0
  WHEN ({DISPLAY_STATE_SQL}) = 'unknown' AND st.state::text <> 'unknown' THEN 0
  ELSE st.confidence
END
"""
